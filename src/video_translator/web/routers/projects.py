"""Router de proyectos: creacion (upload multipart), listado, detalle, status, borrado."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path as FsPath
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from video_translator.web.config import WebSettings, load_web_settings
from video_translator.web.db.models import Project, ProjectStatus, User
from video_translator.web.deps import get_current_user, get_db_session
from video_translator.web.schemas.projects import ProjectListOut, ProjectOut, ProjectStatusOut
from video_translator.web.services import storage
from video_translator.web.services.status_reader import read_project_status
from video_translator.web.tasks.run_project import run_dubbing_project

# Nombres de archivo fijos que escribe el pipeline en `output_dir`, ver
# `application/use_cases/translate_video.py` (subtitulos siempre "es"/"en"
# sin importar el par de idiomas configurado; el video de salida no tiene
# nombre fijo -- se deriva del nombre del input -- por eso se busca por glob).
_SRT_SOURCE_FILENAME = "subtitles.en.srt"
_SRT_TARGET_FILENAME = "subtitles.es.srt"
# Nombres fijos que escribe `TranscribeMediaUseCase` (servicio de
# transcripcion standalone) -- distintos de los de arriba porque no hay
# traduccion, solo una transcripcion en el idioma original.
_TRANSCRIPT_SRT_FILENAME = "transcript.srt"
_TRANSCRIPT_TEXT_FILENAME = "transcript.txt"
# Solo existe si el proyecto se creo con include_summary=True.
_SUMMARY_TEXT_FILENAME = "summary.txt"
# Nombre fijo que escribe `SynthesizeTextUseCase` (servicio de TTS standalone).
_SPEECH_AUDIO_FILENAME = "speech.wav"
# El micro-video (servicio "micro_video") se descarga con el artefacto
# generico "video" (ver el glob mas abajo), no necesita su propio nombre fijo.

router = APIRouter(prefix="/projects", tags=["projects"])


def get_web_settings() -> WebSettings:
    return load_web_settings()


def _get_owned_project(project_id: uuid.UUID, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Proyecto no encontrado.")
    return project


def _to_project_out(project: Project) -> ProjectOut:
    """Completa total_seconds/run_id desde pipeline_timings.json (via el mismo
    lector que usa /status) para que el listado no tenga que pedirle a cada
    fila su propio /status por separado. Barato: si el archivo no existe
    todavia (proyecto recien creado/en cola), read_project_status cae al
    fallback de BD sin tocar el disco mas de una vez."""
    info = read_project_status(project)
    return ProjectOut.model_validate(project).model_copy(
        update={"total_seconds": info.get("total_seconds"), "run_id": info.get("run_id")}
    )


@router.post("", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
def create_project(
    name: str = Form(...),
    service_type: str = Form(...),
    output_mode: str = Form(...),
    # Opcional solo para el servicio "tts": ahi el archivo es una voz de
    # referencia OPCIONAL, no el contenido principal (que es `text`). Para
    # "micro_video" es la imagen o clip de video (obligatorio, ver RM-36).
    # Para el resto de servicios sigue siendo obligatorio (se valida abajo).
    file: UploadFile | None = File(None),
    # Solo para "micro_video": imagenes/clips de video adicionales, mas alla
    # del primero (`file`) -- ver RM-29, RM-36. El orden de este array ES el
    # orden en el que el video recorre el material.
    additional_media: list[UploadFile] = File([]),
    # Solo para "micro_video" cuando voice_option es "own": la voz de
    # referencia va aparte porque `file` ya esta ocupado por la imagen.
    voice_file: UploadFile | None = File(None),
    # URL para importar el media en vez de subirlo (ver
    # web/services/media_import.py) -- mutuamente excluyente con `file` para
    # los servicios que no son "tts"/"micro_video" (validado abajo).
    source_url: str | None = Form(None),
    text: str = Form(""),
    # Para "tts"/"micro_video": "public_female" (default, voz de locutora),
    # "public_male" (voz de locutor), o "own" (usa `file`/`voice_file` como
    # voz de referencia, segun el servicio).
    voice_option: str = Form("public_female"),
    context_prompt: str = Form(""),
    tone: str | None = Form(None),
    glossary: str = Form("{}"),
    source_lang: str = Form("en"),
    target_lang: str = Form("es"),
    diarize: bool = Form(False),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
    # Solo para "transcription": ademas de la transcripcion completa, genera
    # un resumen con los highlights vía LLM (ver TranscribeMediaUseCase).
    include_summary: bool = Form(False),
    # Solo para "micro_video": para que se hace el video (ver RM-42).
    # "product" (default, el comportamiento previo a RM-42) / "professional".
    objective: str = Form("product"),
    # Solo para "micro_video": relacion de aspecto de salida (ver RM-42).
    # "vertical" (default, 9:16, el comportamiento previo) / "square" / "landscape".
    video_format: str = Form("vertical"),
    # Solo para "micro_video": None/omitido = el video dura lo que tarda la
    # narracion; si se fija, GenerateMicroVideoUseCase acelera el audio si
    # hace falta o mantiene la imagen el tiempo restante (ver docs/roadmap.md).
    target_duration_seconds: float | None = Form(None),
    caption_bg_color: str = Form("#000000"),
    # "background" / "text_color" / "karaoke" / "karaoke_background" -- ver
    # GenerateMicroVideoRequest.caption_highlight_style.
    caption_highlight_style: str = Form("background"),
    # Solo tiene efecto en "background"/"karaoke_background" -- ver
    # GenerateMicroVideoRequest.caption_text_color.
    caption_text_color: str = Form("#FFFFFF"),
    # id (UUID) de una fila de MusicTrack (ver RM-26), o None/omitido = sin
    # musica de fondo.
    background_music: str | None = Form(None),
    # Rango [start, end) dentro de la pista elegida a usar como fuente del
    # loop de fondo (ver RM-28). end=None = hasta el final de la pista.
    background_music_start: float = Form(0.0),
    background_music_end: float | None = Form(None),
    # Volumen lineal (no dB) de cada pista al mezclar -- ver
    # GenerateMicroVideoRequest.background_music_volume/narration_volume.
    background_music_volume: float = Form(0.12),
    narration_volume: float = Form(1.0),
    # Posicion de los captions (fraccion 0-1, centro del caption) --
    # arrastrable en el editor igual que un overlay de texto.
    caption_x: float = Form(0.5),
    caption_y: float = Form(0.85),
    # Lista JSON de overlays de texto posicionables (ver RM-28,
    # domain.models.TextOverlay) -- mismo patron que `glossary`.
    text_overlays: str = Form("[]"),
    # Lista JSON de encuadres por item (ver RM-30, domain.models.MicroVideoMediaItem),
    # paralela a [file, *additional_media] por indice -- mismo patron que
    # `text_overlays`. En un item de video puede incluir tambien keep_ranges
    # (ver RM-36/RM-40).
    media_adjustments: str = Form("[]"),
    # Lista JSON de emojis posicionables (ver RM-32, domain.models.EmojiOverlay)
    # -- mismo patron que `text_overlays`.
    emoji_overlays: str = Form("[]"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    settings: WebSettings = Depends(get_web_settings),
) -> ProjectOut:
    try:
        glossary_dict = json.loads(glossary)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="glossary no es JSON valido."
        ) from exc
    if not isinstance(glossary_dict, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="glossary debe ser un objeto JSON.",
        )

    try:
        text_overlays_list = json.loads(text_overlays)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="text_overlays no es JSON valido."
        ) from exc
    if not isinstance(text_overlays_list, list) or not all(
        isinstance(item, dict) and "text" in item and "x" in item and "y" in item for item in text_overlays_list
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="text_overlays debe ser una lista de objetos con 'text', 'x' e 'y'.",
        )

    try:
        media_adjustments_list = json.loads(media_adjustments)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="media_adjustments no es JSON valido."
        ) from exc
    if not isinstance(media_adjustments_list, list) or not all(
        isinstance(item, dict) for item in media_adjustments_list
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="media_adjustments debe ser una lista de objetos.",
        )

    try:
        emoji_overlays_list = json.loads(emoji_overlays)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="emoji_overlays no es JSON valido."
        ) from exc
    if not isinstance(emoji_overlays_list, list) or not all(
        isinstance(item, dict) and "emoji_id" in item and "x" in item and "y" in item
        for item in emoji_overlays_list
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="emoji_overlays debe ser una lista de objetos con 'emoji_id', 'x' e 'y'.",
        )

    is_tts = service_type == "tts"
    is_micro_video = service_type == "micro_video"
    if is_tts:
        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="text es requerido para el servicio de TTS.",
            )
        if voice_option == "own" and file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="file es requerido cuando voice_option es 'own'.",
            )
    elif is_micro_video:
        if not text.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="text es requerido para el servicio de micro-video.",
            )
        if file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="file (la imagen o el video) es requerido para el servicio de micro-video.",
            )
        if voice_option == "own" and voice_file is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="voice_file es requerido cuando voice_option es 'own'.",
            )
    else:
        if file is None and not source_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="file o source_url es requerido para este servicio.",
            )
        if file is not None and source_url:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Envia file o source_url, no ambos.",
            )
        if source_url and urlsplit(source_url).scheme not in ("http", "https"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="source_url debe ser una URL http:// o https://.",
            )

    project_id = uuid.uuid4()
    config = {
        "context_prompt": context_prompt,
        "tone": tone,
        "glossary": glossary_dict,
        "source_lang": source_lang,
        "target_lang": target_lang,
        "diarize": diarize,
        "min_speakers": min_speakers,
        "max_speakers": max_speakers,
        "include_summary": include_summary,
    }

    project = Project(
        id=project_id,
        user_id=current_user.id,
        name=name,
        service_type=service_type,
        source_type="url" if (not is_tts and not is_micro_video and source_url) else "upload",
        source_url=source_url.strip() if (not is_tts and not is_micro_video and source_url) else None,
        input_video_path="",  # se completa abajo (upload/texto) o en la tarea Celery (URL)
        output_dir=str(storage.output_dir_for(project_id, settings)),
        output_mode=output_mode,
        config=config,
        status=ProjectStatus.QUEUED,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    if is_tts:
        project.input_video_path = str(storage.save_text(text, project.id, settings))
        project.config = {**project.config, "voice_option": voice_option}
        if voice_option == "own" and file is not None:
            voice_path = storage.save_upload(file, project.id, settings)
            project.config = {**project.config, "speaker_reference_wav": str(voice_path)}
    elif is_micro_video and file is not None:
        # file (validado arriba) es la imagen o el clip de video (ver RM-36)
        # -- el texto de narracion no tiene un "archivo principal" propio, va
        # en config (mismo criterio que context_prompt: texto libre, sin
        # limite de tamano relevante para este caso de uso).
        project.input_video_path = str(storage.save_upload(file, project.id, settings))
        additional_media_paths = [
            str(storage.save_indexed_upload(item, i + 1, project.id, settings))
            for i, item in enumerate(additional_media)
            if item.filename
        ]
        project.config = {
            **project.config,
            "narration_text": text,
            "objective": objective,
            "video_format": video_format,
            "voice_option": voice_option,
            "target_duration_seconds": target_duration_seconds,
            "caption_bg_color": caption_bg_color,
            "caption_highlight_style": caption_highlight_style,
            "caption_text_color": caption_text_color,
            "background_music": background_music,
            "background_music_start": background_music_start,
            "background_music_end": background_music_end,
            "background_music_volume": background_music_volume,
            "narration_volume": narration_volume,
            "caption_x": caption_x,
            "caption_y": caption_y,
            "text_overlays": text_overlays_list,
            "additional_media_paths": additional_media_paths,
            "media_adjustments": media_adjustments_list,
            "emoji_overlays": emoji_overlays_list,
        }
        if voice_option == "own" and voice_file is not None:
            voice_path = storage.save_upload(voice_file, project.id, settings)
            project.config = {**project.config, "speaker_reference_wav": str(voice_path)}
    elif file is not None:
        project.input_video_path = str(storage.save_upload(file, project.id, settings))
    # si vino source_url, input_video_path se queda en "" -- la descarga
    # ocurre dentro de la tarea Celery (ver tasks/run_project.py), no aca,
    # porque puede tardar minutos y no debe bloquear esta request HTTP.
    db.commit()

    task = run_dubbing_project.delay(str(project.id))
    project.celery_task_id = task.id
    db.commit()
    db.refresh(project)

    return _to_project_out(project)


@router.get("", response_model=ProjectListOut)
def list_projects(
    status_filter: str | None = Query(None, alias="status"),
    service_type: str | None = Query(None),
    q: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ProjectListOut:
    stmt = select(Project).where(Project.user_id == current_user.id)
    if status_filter is not None:
        stmt = stmt.where(Project.status == status_filter)
    if service_type is not None:
        stmt = stmt.where(Project.service_type == service_type)
    # Busca en el servidor y no en el cliente: el listado viene paginado, asi
    # que filtrar la pagina actual buscaria en 20 proyectos de N y diria "no
    # hay" de los que estan en la pagina siguiente.
    if q is not None and q.strip():
        # `%` y `_` son comodines de LIKE: sin escaparlos, buscar "clip_2min"
        # traeria tambien "clipX2min".
        patron = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Project.name.ilike(f"%{patron}%", escape="\\"))

    total = db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()

    stmt = stmt.order_by(Project.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list(db.execute(stmt).scalars().all())

    return ProjectListOut(
        items=[_to_project_out(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{project_id}", response_model=ProjectOut)
def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ProjectOut:
    return _to_project_out(_get_owned_project(project_id, current_user, db))


@router.get("/{project_id}/status", response_model=ProjectStatusOut)
def get_project_status(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ProjectStatusOut:
    project = _get_owned_project(project_id, current_user, db)
    return ProjectStatusOut(**read_project_status(project))


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> None:
    project = _get_owned_project(project_id, current_user, db)

    # input_video_path vive en su propia carpeta por proyecto
    # (STORAGE_ROOT/uploads/{project_id}/...) -- se borra la carpeta entera,
    # no solo el archivo, para no dejar directorios vacios huerfanos.
    upload_dir = FsPath(project.input_video_path).parent if project.input_video_path else None
    for path_str_or_path in (upload_dir, project.output_dir):
        if not path_str_or_path:
            continue
        try:
            path = FsPath(path_str_or_path)
            if path.is_dir():
                shutil.rmtree(path)
            elif path.is_file():
                path.unlink()
        except OSError:
            pass

    db.delete(project)
    db.commit()


@router.post("/{project_id}/resume", response_model=ProjectOut)
def resume_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> ProjectOut:
    project = _get_owned_project(project_id, current_user, db)

    # Una corrida interrumpida (ver RM-44) tambien se puede relanzar, aunque la
    # fila siga diciendo "running": el worker que la procesaba murio y nadie
    # la va a marcar como fallida, asi que exigir "failed" la dejaba sin salida.
    # Se comprueba AQUI y no se confia en lo que diga el cliente: relanzar algo
    # que de verdad esta corriendo pondria dos workers a escribir en el mismo
    # directorio de salida.
    interrumpido = (
        project.status == ProjectStatus.RUNNING and read_project_status(project)["interrupted"]
    )
    if project.status != ProjectStatus.FAILED and not interrumpido:
        if project.status == ProjectStatus.RUNNING:
            detalle = (
                "El proyecto se esta procesando ahora mismo. Espera a que termine o falle."
            )
        else:
            detalle = (
                "Solo se puede reintentar un proyecto que fallo o cuya ejecucion se interrumpio."
            )
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detalle)

    project.status = ProjectStatus.QUEUED
    project.error_message = None
    db.commit()

    task = run_dubbing_project.delay(str(project.id), resume=True)
    project.celery_task_id = task.id
    db.commit()
    db.refresh(project)
    return _to_project_out(project)


@router.get("/{project_id}/download/{artifact}")
def download_project_artifact(
    project_id: uuid.UUID,
    artifact: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> FileResponse:
    project = _get_owned_project(project_id, current_user, db)
    output_dir = FsPath(project.output_dir)

    if artifact == "srt_source":
        file_path = output_dir / _SRT_SOURCE_FILENAME
    elif artifact == "srt_target":
        file_path = output_dir / _SRT_TARGET_FILENAME
    elif artifact == "transcript_srt":
        file_path = output_dir / _TRANSCRIPT_SRT_FILENAME
    elif artifact == "transcript_text":
        file_path = output_dir / _TRANSCRIPT_TEXT_FILENAME
    elif artifact == "summary_text":
        file_path = output_dir / _SUMMARY_TEXT_FILENAME
    elif artifact == "speech_audio":
        file_path = output_dir / _SPEECH_AUDIO_FILENAME
    elif artifact == "video":
        matches = sorted(output_dir.glob("*.mp4")) if output_dir.is_dir() else []
        if not matches:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video no disponible todavia.")
        file_path = matches[0]
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Artefacto desconocido: {artifact}")

    if not file_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Archivo no disponible todavia.")
    return FileResponse(path=file_path, filename=file_path.name)
