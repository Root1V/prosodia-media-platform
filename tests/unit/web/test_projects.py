"""Tests de /api/projects: creacion (multipart), listado, detalle, status, borrado,
y aislamiento por usuario (ownership)."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from video_translator.web.db.models import Project, ProjectStatus, User
from video_translator.web.services import status_reader
from video_translator.web.tasks.run_project import run_dubbing_project


@dataclass
class _FakeAsyncResult:
    id: str = "fake-task-id"


@pytest.fixture(autouse=True)
def _stub_celery_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Los tests de este router no deben depender de un broker Redis real: se
    # reemplaza el despacho de la tarea (no la tarea en si, que se prueba
    # aparte en test_run_project.py) por un doble que solo devuelve un id.
    monkeypatch.setattr(run_dubbing_project, "delay", lambda *args, **kwargs: _FakeAsyncResult())


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _create_project(client: TestClient, headers: dict[str, str], **overrides: Any) -> Any:
    data = {
        "name": "My dubbing project",
        "service_type": "dubbing",
        "output_mode": "dubbed",
        "context_prompt": "",
        "source_lang": "en",
        "target_lang": "es",
        "diarize": "false",
        **overrides,
    }
    files = {"file": ("clip.mp4", b"fake-video-bytes", "video/mp4")}
    return client.post("/api/projects", data=data, files=files, headers=headers)


def test_create_project_success(client: TestClient, make_user: Callable[..., User]) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = _create_project(client, headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "My dubbing project"
    assert body["service_type"] == "dubbing"
    assert body["output_mode"] == "dubbed"
    assert body["status"] == "queued"
    assert body["celery_task_id"] == "fake-task-id"
    assert body["input_video_path"]
    assert body["output_dir"]


def test_create_project_requires_auth(client: TestClient) -> None:
    resp = _create_project(client, headers={})
    assert resp.status_code == 401


def test_create_project_rejects_invalid_glossary_json(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = _create_project(client, headers, glossary="not-json")

    assert resp.status_code == 422


def test_get_project_and_list(client: TestClient, make_user: Callable[..., User]) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    get_resp = client.get(f"/api/projects/{created['id']}", headers=headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == created["id"]

    list_resp = client.get("/api/projects", headers=headers)
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["total"] == 1
    assert body["page"] == 1
    assert body["page_size"] == 20
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == created["id"]


def test_get_project_status(client: TestClient, make_user: Callable[..., User]) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    resp = client.get(f"/api/projects/{created['id']}/status", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["db_status"] == "queued"
    assert body["stages"] is None


def test_list_and_get_include_total_seconds_and_run_id(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pipeline_timings.json").write_text(
        json.dumps({"run_id": "abc123def456", "total_seconds": 305.76, "completed": True})
    )

    get_resp = client.get(f"/api/projects/{created['id']}", headers=headers)
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["run_id"] == "abc123def456"
    assert body["total_seconds"] == 305.76


def test_create_project_with_source_url_instead_of_file(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    data = {
        "name": "Doblaje desde URL",
        "service_type": "dubbing",
        "output_mode": "dubbed",
        "context_prompt": "",
        "source_lang": "en",
        "target_lang": "es",
        "diarize": "false",
        "source_url": "https://example.com/video.mp4",
    }
    resp = client.post("/api/projects", data=data, headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["source_type"] == "url"
    assert body["source_url"] == "https://example.com/video.mp4"
    # La descarga real ocurre en la tarea Celery, no en este request -- el
    # input_video_path se queda vacio hasta que el worker la complete.
    assert body["input_video_path"] == ""


def test_create_project_requires_file_or_source_url(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    # _create_project() siempre adjunta 'file'; para probar la ausencia de
    # ambos (file y source_url) se arma el request a mano.
    data = {
        "name": "Sin fuente",
        "service_type": "dubbing",
        "output_mode": "dubbed",
        "context_prompt": "",
        "source_lang": "en",
        "target_lang": "es",
        "diarize": "false",
    }
    resp = client.post("/api/projects", data=data, headers=headers)

    assert resp.status_code == 422


def test_create_project_rejects_both_file_and_source_url(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = _create_project(client, headers, source_url="https://example.com/video.mp4")

    assert resp.status_code == 422


def test_create_project_rejects_non_http_source_url(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    data = {
        "name": "URL invalida",
        "service_type": "dubbing",
        "output_mode": "dubbed",
        "context_prompt": "",
        "source_lang": "en",
        "target_lang": "es",
        "diarize": "false",
        "source_url": "ftp://example.com/video.mp4",
    }
    resp = client.post("/api/projects", data=data, headers=headers)

    assert resp.status_code == 422


def test_project_not_found(client: TestClient, make_user: Callable[..., User]) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.get("/api/projects/00000000-0000-0000-0000-000000000000", headers=headers)

    assert resp.status_code == 404


def test_ownership_isolation_returns_404_not_403(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    make_user(email="bob@example.com", password="secret456")
    alice_headers = _auth_headers(client, "alice@example.com", "hunter2")
    bob_headers = _auth_headers(client, "bob@example.com", "secret456")

    created = _create_project(client, alice_headers).json()

    # Bob no puede ver el proyecto de Alice: 404 (no 403), para no filtrar
    # que el proyecto existe.
    get_resp = client.get(f"/api/projects/{created['id']}", headers=bob_headers)
    assert get_resp.status_code == 404

    status_resp = client.get(f"/api/projects/{created['id']}/status", headers=bob_headers)
    assert status_resp.status_code == 404

    delete_resp = client.delete(f"/api/projects/{created['id']}", headers=bob_headers)
    assert delete_resp.status_code == 404

    # Bob no ve el proyecto de Alice en su listado.
    list_resp = client.get("/api/projects", headers=bob_headers)
    assert list_resp.json()["total"] == 0


def test_delete_project(client: TestClient, make_user: Callable[..., User]) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    upload_dir = Path(created["input_video_path"]).parent
    assert upload_dir.is_dir()

    delete_resp = client.delete(f"/api/projects/{created['id']}", headers=headers)
    assert delete_resp.status_code == 204

    get_resp = client.get(f"/api/projects/{created['id']}", headers=headers)
    assert get_resp.status_code == 404

    # No debe quedar el directorio de subida vacio huerfano en disco.
    assert not upload_dir.exists()


def test_resume_requires_failed_status(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    # Recien creado esta "queued", no "failed": reintentar debe rechazarse.
    resp = client.post(f"/api/projects/{created['id']}/resume", headers=headers)
    assert resp.status_code == 409


def test_resume_failed_project_reenqueues(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    project = db_session.get(Project, uuid.UUID(created["id"]))
    assert project is not None
    project.status = ProjectStatus.FAILED
    project.error_message = "algo salio mal"
    db_session.commit()

    resp = client.post(f"/api/projects/{created['id']}/resume", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    assert body["error_message"] is None
    assert body["celery_task_id"] == "fake-task-id"


def test_resume_interrupted_running_project_reenqueues(
    client: TestClient,
    make_user: Callable[..., User],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Una corrida interrumpida (RM-44) sigue diciendo "running" porque el worker
    # que debia marcarla como fallida es el que murio. Sin esto se quedaba sin
    # salida posible: el endpoint exigia "failed" y devolvia 409 para siempre.
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    project = db_session.get(Project, uuid.UUID(created["id"]))
    assert project is not None
    project.status = ProjectStatus.RUNNING
    project.celery_task_id = "task-muerta"
    db_session.commit()
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: False)

    resp = client.post(f"/api/projects/{created['id']}/resume", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_resume_refuses_a_project_that_is_really_running(
    client: TestClient,
    make_user: Callable[..., User],
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # La proteccion que importa: relanzar algo que SI esta corriendo pondria dos
    # workers a escribir en el mismo directorio de salida. El estado de la fila
    # es identico al del test anterior -- lo unico que cambia es que la tarea
    # sigue viva, y eso lo decide Celery, no el cliente.
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    project = db_session.get(Project, uuid.UUID(created["id"]))
    assert project is not None
    project.status = ProjectStatus.RUNNING
    project.celery_task_id = "task-viva"
    db_session.commit()
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: True)

    resp = client.post(f"/api/projects/{created['id']}/resume", headers=headers)

    assert resp.status_code == 409
    assert "ahora mismo" in resp.json()["detail"]


def test_download_artifact_not_ready_returns_404(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    resp = client.get(f"/api/projects/{created['id']}/download/video", headers=headers)
    assert resp.status_code == 404


def test_download_artifact_unknown_kind_returns_400(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    resp = client.get(f"/api/projects/{created['id']}/download/nonsense", headers=headers)
    assert resp.status_code == 400


def test_download_artifact_serves_existing_file(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers).json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "subtitles.es.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHola\n")

    resp = client.get(f"/api/projects/{created['id']}/download/srt_target", headers=headers)

    assert resp.status_code == 200
    assert resp.content == b"1\n00:00:00,000 --> 00:00:01,000\nHola\n"


def test_create_tts_project_without_voice_file_succeeds(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi audio",
            "service_type": "tts",
            "output_mode": "subtitles_only",
            "text": "Hola, esto es una prueba.",
            "target_lang": "es",
        },
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["service_type"] == "tts"
    assert body["input_video_path"].endswith("input.txt")
    assert "speaker_reference_wav" not in body["config"]


def test_create_tts_project_requires_text(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={"name": "Mi audio", "service_type": "tts", "output_mode": "subtitles_only", "text": "   "},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_tts_project_with_voice_file_saves_speaker_reference(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi audio",
            "service_type": "tts",
            "output_mode": "subtitles_only",
            "text": "Hola.",
            "voice_option": "own",
        },
        files={"file": ("voice.wav", b"fake-wav-bytes", "audio/wav")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["speaker_reference_wav"].endswith("voice.wav")


def test_create_tts_project_requires_file_when_voice_option_is_own(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi audio",
            "service_type": "tts",
            "output_mode": "subtitles_only",
            "text": "Hola.",
            "voice_option": "own",
        },
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_tts_project_defaults_voice_option_to_public_female(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={"name": "Mi audio", "service_type": "tts", "output_mode": "subtitles_only", "text": "Hola."},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["voice_option"] == "public_female"


def test_create_project_without_file_rejects_for_non_tts_service(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={"name": "Sin archivo", "service_type": "dubbing", "output_mode": "dubbed"},
        headers=headers,
    )

    assert resp.status_code == 422


def test_download_speech_audio_artifact_serves_existing_file(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = client.post(
        "/api/projects",
        data={"name": "Mi audio", "service_type": "tts", "output_mode": "subtitles_only", "text": "Hola."},
        headers=headers,
    ).json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "speech.wav").write_bytes(b"fake-speech-audio")

    resp = client.get(f"/api/projects/{created['id']}/download/speech_audio", headers=headers)

    assert resp.status_code == 200
    assert resp.content == b"fake-speech-audio"


def test_download_transcript_artifacts_serves_existing_files(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(client, headers, service_type="transcription").json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "transcript.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nHello\n")
    (output_dir / "transcript.txt").write_text("Hello")

    srt_resp = client.get(f"/api/projects/{created['id']}/download/transcript_srt", headers=headers)
    text_resp = client.get(f"/api/projects/{created['id']}/download/transcript_text", headers=headers)

    assert srt_resp.status_code == 200
    assert srt_resp.content == b"1\n00:00:00,000 --> 00:00:01,000\nHello\n"
    assert text_resp.status_code == 200
    assert text_resp.content == b"Hello"


def test_create_transcription_project_defaults_include_summary_false(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    created = _create_project(client, headers, service_type="transcription").json()

    assert created["config"]["include_summary"] is False


def test_create_transcription_project_with_include_summary_true(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    created = _create_project(
        client, headers, service_type="transcription", include_summary="true"
    ).json()

    assert created["config"]["include_summary"] is True


def test_download_summary_text_artifact_serves_existing_file(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    created = _create_project(
        client, headers, service_type="transcription", include_summary="true"
    ).json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.txt").write_text("Puntos clave del video.")

    resp = client.get(f"/api/projects/{created['id']}/download/summary_text", headers=headers)

    assert resp.status_code == 200
    assert resp.content == b"Puntos clave del video."


def test_create_micro_video_project_requires_text(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={"name": "Mi micro-video", "service_type": "micro_video", "output_mode": "subtitles_only", "text": "   "},
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_requires_a_media_file(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_saves_image_and_narration_text(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "target_lang": "es",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["service_type"] == "micro_video"
    assert body["input_video_path"].endswith("photo.jpg")
    assert body["config"]["narration_text"] == "Un texto cualquiera."
    assert body["config"]["voice_option"] == "public_female"
    assert "speaker_reference_wav" not in body["config"]
    # Sin duracion fija elegida (comportamiento por defecto: dura lo que
    # tarda la narracion) y color de fondo por defecto.
    assert body["config"]["target_duration_seconds"] is None
    assert body["config"]["caption_bg_color"] == "#000000"


def test_create_micro_video_project_with_fixed_duration_and_bg_color(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "target_duration_seconds": "30",
            "caption_bg_color": "#FF0000",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["config"]["target_duration_seconds"] == 30.0
    assert body["config"]["caption_bg_color"] == "#FF0000"


def test_create_micro_video_project_defaults_highlight_style_to_background(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["caption_highlight_style"] == "background"


def test_create_micro_video_project_with_text_color_highlight_style(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "caption_highlight_style": "text_color",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["caption_highlight_style"] == "text_color"


def test_create_micro_video_project_defaults_to_no_background_music(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["background_music"] is None


def test_create_micro_video_project_with_background_music_track(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "background_music": "backbeat",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["background_music"] == "backbeat"


def test_create_micro_video_project_defaults_music_range_and_overlays(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    config = resp.json()["config"]
    assert config["background_music_start"] == 0.0
    assert config["background_music_end"] is None
    assert config["text_overlays"] == []
    assert config["background_music_volume"] == 0.12
    assert config["narration_volume"] == 1.0
    assert config["caption_x"] == 0.5
    assert config["caption_y"] == 0.85


def test_create_micro_video_project_with_volume_and_caption_position(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "background_music_volume": "0.4",
            "narration_volume": "0.0",
            "caption_x": "0.2",
            "caption_y": "0.1",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    config = resp.json()["config"]
    assert config["background_music_volume"] == 0.4
    assert config["narration_volume"] == 0.0
    assert config["caption_x"] == 0.2
    assert config["caption_y"] == 0.1


def test_create_micro_video_project_with_music_range_and_text_overlays(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    overlays = [{"text": "Hola", "x": 0.5, "y": 0.2, "bold": True}]

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "background_music": "backbeat",
            "background_music_start": "10.0",
            "background_music_end": "20.0",
            "text_overlays": json.dumps(overlays),
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    config = resp.json()["config"]
    assert config["background_music_start"] == 10.0
    assert config["background_music_end"] == 20.0
    assert config["text_overlays"] == overlays


def test_create_micro_video_project_with_additional_media(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files=[
            ("file", ("photo.jpg", b"fake-image-bytes", "image/jpeg")),
            ("additional_media", ("photo2.jpg", b"fake-image-bytes-2", "image/jpeg")),
            ("additional_media", ("photo3.jpg", b"fake-image-bytes-3", "image/jpeg")),
        ],
        headers=headers,
    )

    assert resp.status_code == 201
    config = resp.json()["config"]
    assert len(config["additional_media_paths"]) == 2
    assert config["additional_media_paths"][0].endswith("photo2.jpg")
    assert config["additional_media_paths"][1].endswith("photo3.jpg")


def test_create_micro_video_project_with_additional_media_mixing_images_and_videos(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files=[
            ("file", ("photo.jpg", b"fake-image-bytes", "image/jpeg")),
            ("additional_media", ("clip.mp4", b"fake-video-bytes", "video/mp4")),
            ("additional_media", ("photo3.jpg", b"fake-image-bytes-3", "image/jpeg")),
        ],
        headers=headers,
    )

    assert resp.status_code == 201
    config = resp.json()["config"]
    # El orden del array ES el orden de la linea de tiempo -- se preserva
    # entre imagenes y clips de video sin distincion (ver RM-36).
    assert config["additional_media_paths"][0].endswith("clip.mp4")
    assert config["additional_media_paths"][1].endswith("photo3.jpg")
    assert "media_1_clip.mp4" in config["additional_media_paths"][0]


def test_create_micro_video_project_with_clip_trim_in_media_adjustments(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    adjustments = [{}, {"clip_start": 2.0, "clip_end": 5.0}]

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "media_adjustments": json.dumps(adjustments),
        },
        files=[
            ("file", ("photo.jpg", b"fake-image-bytes", "image/jpeg")),
            ("additional_media", ("clip.mp4", b"fake-video-bytes", "video/mp4")),
        ],
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["media_adjustments"] == adjustments


def test_create_micro_video_project_defaults_additional_media_to_empty(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["additional_media_paths"] == []


def test_create_micro_video_project_defaults_media_adjustments_to_empty(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["media_adjustments"] == []


def test_create_micro_video_project_with_media_adjustments(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    adjustments = [{"offset_x": 0.2, "offset_y": 0.8, "zoom": 1.5}]

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "media_adjustments": json.dumps(adjustments),
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["media_adjustments"] == adjustments


def test_create_micro_video_project_rejects_invalid_media_adjustments_json(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "media_adjustments": "not-json",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_rejects_media_adjustments_not_a_list(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "media_adjustments": json.dumps({"offset_x": 0.5}),
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_defaults_emoji_overlays_to_empty(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["emoji_overlays"] == []


def test_create_micro_video_project_with_emoji_overlays(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    overlays = [{"emoji_id": "fuego", "x": 0.25, "y": 0.75, "size": 0.2, "fade": True}]

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "emoji_overlays": json.dumps(overlays),
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 201
    assert resp.json()["config"]["emoji_overlays"] == overlays


def test_create_micro_video_project_rejects_invalid_emoji_overlays_json(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "emoji_overlays": "not-json",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_rejects_emoji_overlays_missing_required_fields(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "emoji_overlays": json.dumps([{"emoji_id": "fuego"}]),
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_rejects_invalid_text_overlays_json(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "text_overlays": "not-json",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_rejects_text_overlays_missing_required_keys(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "text_overlays": json.dumps([{"text": "Hola"}]),  # falta x/y
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_requires_voice_file_when_voice_option_is_own(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "voice_option": "own",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    )

    assert resp.status_code == 422


def test_create_micro_video_project_with_own_voice_saves_speaker_reference(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
            "voice_option": "own",
        },
        files={
            "file": ("photo.jpg", b"fake-image-bytes", "image/jpeg"),
            "voice_file": ("voice.wav", b"fake-wav-bytes", "audio/wav"),
        },
        headers=headers,
    )

    assert resp.status_code == 201
    body = resp.json()
    assert body["input_video_path"].endswith("photo.jpg")
    assert body["config"]["speaker_reference_wav"].endswith("voice.wav")


def test_download_micro_video_uses_generic_video_artifact(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    created = client.post(
        "/api/projects",
        data={
            "name": "Mi micro-video",
            "service_type": "micro_video",
            "output_mode": "subtitles_only",
            "text": "Un texto cualquiera.",
        },
        files={"file": ("photo.jpg", b"fake-image-bytes", "image/jpeg")},
        headers=headers,
    ).json()

    output_dir = Path(created["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "micro_video.mp4").write_bytes(b"fake-mp4-bytes")

    resp = client.get(f"/api/projects/{created['id']}/download/video", headers=headers)

    assert resp.status_code == 200
    assert resp.content == b"fake-mp4-bytes"
