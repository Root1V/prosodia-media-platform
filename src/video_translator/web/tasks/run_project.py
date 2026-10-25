"""Tarea Celery que procesa un proyecto llamando al pipeline real.

Replica el flujo de `cli.py::translate`: construye `Settings`/
`TranslateVideoRequest` via `project_mapper`, llama
`TranslateVideoUseCase.execute()`, y refleja el resultado en el estado del
proyecto. El progreso en vivo NO pasa por aqui -- lo lee
`services.status_reader` directamente de `pipeline_timings.json`, que
`PipelineTimings` ya escribe de forma incremental (ver `utils/timing.py`);
esta tarea solo necesita marcar running/completed/failed en la fila de BD.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from celery import Task
from sqlalchemy.orm import Session

from video_translator.domain.exceptions import VideoTranslatorError
from video_translator.web.config import load_web_settings
from video_translator.web.db.models import Project, ProjectMetrics, ProjectStatus, ServiceType
from video_translator.web.db.session import SessionLocal
from video_translator.web.services.media_import import MediaImportError, download_media
from video_translator.web.services.project_mapper import (
    build_micro_video_use_case_and_request,
    build_synthesize_use_case_and_request,
    build_transcribe_use_case_and_request,
    build_use_case_and_request,
)
from video_translator.web.services.status_reader import read_full_timings_report
from video_translator.web.tasks.celery_app import celery_app


def _persist_metrics_snapshot(project: Project, session: Session, status_value: str) -> None:
    """Guarda una foto de `pipeline_timings.json` en `ProjectMetrics` al
    finalizar (exito o falla) -- ver el docstring de esa tabla en
    `db/models.py` para por que existe separada de `Project`. Si el archivo
    de timings no llego a escribirse (p.ej. fallo antes de la primera etapa),
    igual se guarda una fila minima: el conteo/estado de la corrida importa
    para el dashboard aunque no haya metricas de duracion que reportar."""
    report = read_full_timings_report(project) or {}
    input_data = report.get("input") or {}
    session.add(
        ProjectMetrics(
            project_id=project.id,
            user_id=project.user_id,
            project_name=project.name,
            service_type=project.service_type.value,
            status=status_value,
            total_seconds=report.get("total_seconds"),
            input_duration_seconds=input_data.get("duration_seconds"),
            realtime_factor=report.get("realtime_factor"),
            effective_config=report.get("effective_config") or {},
            stats=report.get("stats") or {},
            outputs=report.get("outputs") or {},
            warnings_count=len(report.get("warnings") or []),
        )
    )


@celery_app.task(bind=True, name="video_translator.web.run_project")
def run_dubbing_project(self: Task, project_id: str, resume: bool = False) -> None:
    session = SessionLocal()
    try:
        project = session.get(Project, uuid.UUID(project_id))
        if project is None:
            return
        if project.source_url and not project.input_video_path:
            try:
                project.status = ProjectStatus.DOWNLOADING
                session.commit()
                downloaded_path = download_media(project.source_url, project.id, load_web_settings())
                project.input_video_path = str(downloaded_path)
                session.commit()
            except MediaImportError as exc:
                project.status = ProjectStatus.FAILED
                project.error_message = str(exc)
                project.completed_at = datetime.now(timezone.utc)
                _persist_metrics_snapshot(project, session, ProjectStatus.FAILED.value)
                session.commit()
                raise

        try:
            project.status = ProjectStatus.RUNNING
            project.started_at = datetime.now(timezone.utc)
            project.error_message = None
            session.commit()

            if project.service_type == ServiceType.TRANSCRIPTION:
                transcribe_use_case, transcribe_request = build_transcribe_use_case_and_request(project)
                transcribe_use_case.execute(transcribe_request)
            elif project.service_type == ServiceType.TTS:
                tts_use_case, tts_request = build_synthesize_use_case_and_request(project)
                tts_use_case.execute(tts_request)
            elif project.service_type == ServiceType.MICRO_VIDEO:
                micro_video_use_case, micro_video_request = build_micro_video_use_case_and_request(
                    project, db=session, resume=resume
                )
                micro_video_use_case.execute(micro_video_request)
            else:
                dub_use_case, dub_request = build_use_case_and_request(project, resume=resume)
                dub_use_case.execute(dub_request)

            project.status = ProjectStatus.COMPLETED
            project.completed_at = datetime.now(timezone.utc)
            _persist_metrics_snapshot(project, session, ProjectStatus.COMPLETED.value)
            session.commit()
        except VideoTranslatorError as exc:
            project.status = ProjectStatus.FAILED
            project.error_message = str(exc)
            project.completed_at = datetime.now(timezone.utc)
            _persist_metrics_snapshot(project, session, ProjectStatus.FAILED.value)
            session.commit()
            raise
        except Exception as exc:
            project.status = ProjectStatus.FAILED
            project.error_message = f"Error inesperado: {exc}"
            project.completed_at = datetime.now(timezone.utc)
            _persist_metrics_snapshot(project, session, ProjectStatus.FAILED.value)
            session.commit()
            raise
    finally:
        session.close()
