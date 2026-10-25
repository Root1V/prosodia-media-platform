"""Tests de status_reader.read_project_status: disco (pipeline_timings.json)
vs. fallback a status de BD."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from video_translator.web.db.models import Project, ProjectStatus
from video_translator.web.services import status_reader
from video_translator.web.services.status_reader import read_project_status


def _make_project(output_dir: Path, status: ProjectStatus = ProjectStatus.RUNNING) -> Project:
    return Project(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Test project",
        service_type="dubbing",
        source_type="upload",
        input_video_path="/tmp/in.mp4",
        output_dir=str(output_dir),
        output_mode="dubbed",
        config={},
        status=status,
    )


def test_read_project_status_falls_back_to_db_when_file_missing(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "missing", status=ProjectStatus.RUNNING)

    result = read_project_status(project)

    assert result["db_status"] == ProjectStatus.RUNNING
    assert result["run_id"] is None
    assert result["completed"] is None
    assert result["current_stage"] is None
    assert result["stages"] is None
    assert result["total_seconds"] is None
    assert result["realtime_factor"] is None
    assert result["warnings"] is None


def test_read_project_status_falls_back_to_db_when_completed(tmp_path: Path) -> None:
    project = _make_project(tmp_path / "missing", status=ProjectStatus.COMPLETED)

    result = read_project_status(project)

    assert result["completed"] is True


def test_read_project_status_reads_pipeline_timings_file(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    fake_report = {
        "run_id": "abc123def456",
        "completed": False,
        "current_stage": {"name": "translation", "started_at": "2026-08-23T00:00:00+00:00"},
        "stages": [{"order": 1, "name": "transcription", "seconds": 12.3}],
        "total_seconds": 45.6,
        "realtime_factor": 1.5,
        "warnings": [{"source": "tts", "at": "2026-08-23T00:00:00+00:00"}],
    }
    (output_dir / "pipeline_timings.json").write_text(json.dumps(fake_report), encoding="utf-8")
    project = _make_project(output_dir, status=ProjectStatus.RUNNING)

    result = read_project_status(project)

    assert result["db_status"] == ProjectStatus.RUNNING
    assert result["run_id"] == "abc123def456"
    assert result["completed"] is False
    assert result["current_stage"] == fake_report["current_stage"]
    assert result["stages"] == fake_report["stages"]
    assert result["total_seconds"] == 45.6
    assert result["realtime_factor"] == 1.5
    assert result["warnings"] == fake_report["warnings"]


def test_read_project_status_falls_back_when_file_is_corrupt(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "pipeline_timings.json").write_text("{not valid json", encoding="utf-8")
    project = _make_project(output_dir, status=ProjectStatus.RUNNING)

    result = read_project_status(project)

    assert result["db_status"] == ProjectStatus.RUNNING
    assert result["run_id"] is None
    assert result["stages"] is None


# --- Deteccion de corrida interrumpida ---------------------------------------
#
# Un worker que muere a mitad deja la fila en RUNNING para siempre: el proceso
# que debia marcarla como fallida es el que murio. Estos tests fijan QUIEN
# decide (Celery) y quien no (el reloj).


def _timings(generated_at: str, **extra: object) -> dict:
    return {"run_id": "abc123", "completed": False, "generated_at": generated_at, **extra}


def _write(output_dir: Path, data: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pipeline_timings.json").write_text(json.dumps(data), encoding="utf-8")


def test_running_with_live_celery_task_is_not_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Informe viejo PERO la tarea sigue activa: es una etapa larga que no
    # escribe (cargar un modelo de 10 GB tarda minutos). No es interrumpida.
    _write(tmp_path, _timings("2020-01-01T00:00:00+00:00"))
    project = _make_project(tmp_path, status=ProjectStatus.RUNNING)
    project.celery_task_id = "task-1"
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: True)

    assert read_project_status(project)["interrupted"] is False


def test_running_with_dead_celery_task_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, _timings("2020-01-01T00:00:00+00:00"))
    project = _make_project(tmp_path, status=ProjectStatus.RUNNING)
    project.celery_task_id = "task-1"
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: False)

    assert read_project_status(project)["interrupted"] is True


def test_unknown_celery_state_is_not_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Nadie contesto al broadcast. Decir "murio" de algo que puede seguir vivo
    # es peor que tardar en detectarlo: invita a relanzarlo por encima.
    _write(tmp_path, _timings("2020-01-01T00:00:00+00:00"))
    project = _make_project(tmp_path, status=ProjectStatus.RUNNING)
    project.celery_task_id = "task-1"
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: None)

    assert read_project_status(project)["interrupted"] is False


def test_fresh_report_never_asks_celery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # El filtro por tiempo existe para NO pagar el broadcast en cada sondeo del
    # frontend. Si el informe esta fresco, ni se pregunta.
    _write(tmp_path, _timings(datetime.now(timezone.utc).isoformat()))
    project = _make_project(tmp_path, status=ProjectStatus.RUNNING)
    project.celery_task_id = "task-1"

    def _no_llamar(_id: str | None) -> bool:
        raise AssertionError("no deberia preguntarle a Celery con el informe fresco")

    monkeypatch.setattr(status_reader, "_celery_task_is_active", _no_llamar)

    assert read_project_status(project)["interrupted"] is False


def test_completed_project_is_never_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, _timings("2020-01-01T00:00:00+00:00", completed=True))
    project = _make_project(tmp_path, status=ProjectStatus.COMPLETED)
    monkeypatch.setattr(status_reader, "_celery_task_is_active", lambda _id: False)

    assert read_project_status(project)["interrupted"] is False
