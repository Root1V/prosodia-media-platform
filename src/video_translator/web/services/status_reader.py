"""Lee el progreso de un proyecto: primero intenta `pipeline_timings.json` en
disco (escrito incrementalmente por `PipelineTimings`, ver `utils/timing.py`),
y si no existe o esta corrupto/a medio escribir, cae al `status` de la fila
en base de datos.

En M1 la tarea Celery es un stub que nunca escribe ese archivo, asi que esta
funcion siempre cae al fallback de BD -- pero la logica de lectura de disco ya
esta completa para que M2 (tarea Celery real) no necesite tocar este archivo.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog

from video_translator.web.db.models import Project, ProjectStatus

logger = structlog.get_logger(__name__)

# Cuanto puede estar el informe sin actualizarse antes de que valga la pena
# preguntarle a Celery si la tarea sigue viva. NO es un umbral de muerte: una
# etapa puede tardar minutos legitimamente sin escribir nada (cargar el modelo
# de IndexTTS son ~10 GB), asi que darla por muerta por tiempo seria falso.
# Esto solo decide CUANDO se paga la pregunta; quien responde es Celery.
STALE_SECONDS = 60.0

# El frontend sondea el estado cada pocos segundos, y `inspect()` de Celery no
# es un plazo maximo sino una VENTANA DE RECOLECCION: siempre tarda lo que se
# le pida, aunque el worker conteste al instante. Sin cache, cada sondeo de un
# proyecto estancado costaba 2 s de broadcast, y varios en vuelo a la vez se
# pisaban y devolvian "nadie contesto" -- medido: la deteccion no se disparaba
# nunca mientras la pagina estaba abierta.
_LIVENESS_TTL = 15.0
_LIVENESS_LOCK = threading.Lock()
_liveness_cache: dict[str, tuple[float, bool | None]] = {}


def read_project_status(project: Project) -> dict[str, Any]:
    timings_path = Path(project.output_dir) / "pipeline_timings.json"
    timings = _read_timings_file(timings_path)
    if timings is not None:
        return {
            "db_status": project.status,
            "run_id": timings.get("run_id"),
            "completed": bool(timings.get("completed")),
            "current_stage": timings.get("current_stage"),
            "stages": timings.get("stages"),
            "total_seconds": timings.get("total_seconds"),
            "realtime_factor": timings.get("realtime_factor"),
            "warnings": timings.get("warnings"),
            "interrupted": _is_interrupted(project, timings),
        }

    return {
        "db_status": project.status,
        "run_id": None,
        "completed": project.status == ProjectStatus.COMPLETED or None,
        "current_stage": None,
        "stages": None,
        "total_seconds": None,
        "realtime_factor": None,
        "warnings": None,
        "interrupted": _is_interrupted(project, None),
    }


def _is_interrupted(project: Project, timings: dict[str, Any] | None) -> bool:
    """¿El proyecto dice "corriendo" pero ya no lo procesa nadie?

    Es el hueco que deja un worker que muere a mitad: la fila queda en RUNNING
    para siempre, porque el propio proceso que debia marcarla como fallida es
    el que murio. En la UI se ve identico a un trabajo que avanza.

    Se pregunta a Celery y no se deduce del tiempo: una etapa puede tardar
    minutos sin escribir nada. El tiempo solo decide cuando preguntar.
    """
    if project.status != ProjectStatus.RUNNING:
        return False
    if not _looks_stale(timings):
        return False
    alive = _celery_task_is_active(project.celery_task_id)
    # None = no se pudo averiguar (broker caido, nadie contesta). Ante la duda
    # NO se marca como interrumpido: decir "murio" de algo que sigue vivo es
    # peor que tardar en detectarlo, porque invita a relanzarlo por encima.
    return alive is False


def _looks_stale(timings: dict[str, Any] | None) -> bool:
    if timings is None:
        return True
    raw = timings.get("generated_at")
    if not isinstance(raw, str):
        return True
    try:
        generated = datetime.fromisoformat(raw)
    except ValueError:
        return True
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - generated).total_seconds() > STALE_SECONDS


def _celery_task_is_active(task_id: str | None) -> bool | None:
    """True/False si se pudo determinar, None si no.

    Import perezoso a proposito: este modulo lo usa tambien el worker, y
    `celery_app` arranca la telemetria al importarse.
    """
    if not task_id:
        return None

    ahora = time.monotonic()
    cacheado = _liveness_cache.get(task_id)
    if cacheado is not None and ahora - cacheado[0] < _LIVENESS_TTL:
        return cacheado[1]

    # Un solo broadcast en vuelo a la vez. Quien llegue mientras otro pregunta
    # se encuentra la respuesta ya puesta al entrar.
    with _LIVENESS_LOCK:
        cacheado = _liveness_cache.get(task_id)
        if cacheado is not None and time.monotonic() - cacheado[0] < _LIVENESS_TTL:
            return cacheado[1]
        resultado = _ask_celery(task_id)
        _liveness_cache[task_id] = (time.monotonic(), resultado)
        return resultado


def _ask_celery(task_id: str) -> bool | None:
    try:
        from video_translator.web.tasks.celery_app import celery_app

        activas = celery_app.control.inspect(timeout=2.0).active()
    except Exception as exc:  # noqa: BLE001
        logger.warning("status_reader.celery_inspect_failed", error=str(exc))
        return None
    if activas is None:
        # Ningun worker contesto. Puede ser que no haya ninguno (y entonces la
        # tarea no corre) o que esten saturados y no respondan al broadcast.
        # No se distingue, asi que no se afirma nada.
        return None
    return any(t.get("id") == task_id for tareas in activas.values() for t in tareas)


def read_full_timings_report(project: Project) -> dict[str, Any] | None:
    """Lee `pipeline_timings.json` completo, sin descartar `effective_config`/
    `stats`/`outputs` como hace `read_project_status` (que solo expone lo
    necesario para el polling de progreso en vivo). Usado por
    `web/tasks/run_project.py` al finalizar una corrida para persistir una
    foto de metricas de negocio (ver `db/models.py::ProjectMetrics`). None si
    el archivo no existe o esta corrupto -- p.ej. una corrida que fallo antes
    de escribir ninguna etapa."""
    timings_path = Path(project.output_dir) / "pipeline_timings.json"
    return _read_timings_file(timings_path)


def _read_timings_file(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return data
