"""Medicion de tiempo por etapa del pipeline: observabilidad/trazabilidad.

Envuelve cada fase (extraccion de audio, transcripcion, diarizacion,
traduccion, sintesis, mezcla...) con un cronometro, deja un log estructurado
de inicio/fin de cada una, y produce un resumen (tabla en CLI + reporte JSON
persistido en el directorio de salida) para poder comparar rendimiento entre
corridas — sin esto, "por que tardo tanto" es una pregunta sin respuesta
accionable.

El reporte JSON (`pipeline_timings.json`) se ACTUALIZA INCREMENTALMENTE: al
entrar y al salir de cada etapa se reescribe el archivo. Si el pipeline se
interrumpe a media carrera, el archivo queda como una foto parcial del progreso
(con `"completed": false` y la etapa en curso en `current_stage`), no un
archivo vacio o desactualizado.

Reanudacion (--resume): cuando el pipeline se relanza y salta etapas ya
completadas, NO las registra con 0.0s. Con `adopt_previous_report()` se cargan
las duraciones del reporte de la corrida anterior y `record_resumed()` conserva
el tiempo REAL que esa etapa costo originalmente (marcada con
`"status": "resumed"`), para que el reporte final siga siendo un perfil
fiel del trabajo total.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from video_translator.utils.logging_config import get_logger

logger = get_logger(__name__)

# Llaves reservadas del esquema de una etapa: el metadata de usuario no puede
# pisarlas (evita que p.ej. num_segments="x" rompa "order" o "seconds").
_RESERVED_STAGE_KEYS = frozenset(
    {"order", "name", "seconds", "percent_of_total", "status", "started_at", "ended_at"}
)

STATUS_COMPLETED = "completed"
STATUS_RESUMED = "resumed"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _utc_now_minus_iso(seconds: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=max(0.0, seconds))).isoformat(
        timespec="seconds"
    )


@dataclass(slots=True)
class StageTiming:
    name: str
    seconds: float
    status: str = STATUS_COMPLETED
    started_at: str | None = None
    ended_at: str | None = None
    metadata: dict = field(default_factory=dict)


class PipelineTimings:
    """Acumula la duracion de cada etapa durante UNA ejecucion del pipeline.

    Si se le da un ``report_path``, persiste el reporte JSON incrementalmente:
    cada vez que una etapa termina (y tambien cuando empieza, para dejar
    constancia de la etapa en curso), el archivo en disco se actualiza.
    """

    def __init__(self, run_id: str | None = None, report_path: Path | None = None) -> None:
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self._stages: list[StageTiming] = []
        self._concurrent_groups: list[list[str]] = []
        self._run_start = time.monotonic()
        self._started_at_iso = _utc_now_iso()
        self._report_path = Path(report_path) if report_path is not None else None
        # Duraciones reales heredadas del reporte de una corrida anterior
        # (clave: nombre de la etapa), usadas al reanudar.
        self._previous_stages: dict[str, dict] = {}
        self._resumed_run = False
        self._completed = False
        self._current_stage: dict | None = None
        self._input_video: str | None = None
        self._input_duration_seconds: float | None = None
        self._effective_config: dict = {}
        self._warnings: list[dict] = []
        self._stats: dict[str, list] = {}
        self._counters: dict[str, int] = {}
        self._outputs: dict = {}
        self._interrupted: dict | None = None
        self._pending_annotations: dict[str, dict] = {}
        # Cadena de runs que contribuyeron al trabajo total: en un --resume,
        # el reporte final conserva los run_id de TODAS las corridas (la
        # actual y las anteriores que hizo cada etapa), no solo el ultimo.
        self._run_ids: list[str] = [self.run_id]
        PipelineTimings.set_active(self)

    # ------------------------------------------------------------------
    # Registro de instancia activa: permite a un signal handler (cli.py)
    # marcar la corrida como interrumpida sin acoplar todo el codigo.
    _active: PipelineTimings | None = None

    @classmethod
    def set_active(cls, instance: PipelineTimings | None) -> None:
        cls._active = instance

    @classmethod
    def active(cls) -> PipelineTimings | None:
        return cls._active

    @property
    def report_path(self) -> Path | None:
        return self._report_path

    def set_report_path(self, path: Path) -> None:
        self._report_path = Path(path)

    def mark_resumed(self) -> None:
        """Marca esta corrida como reanudacion de una anterior (--resume)."""
        self._resumed_run = True

    def set_input(self, video: str | Path, duration_seconds: float) -> None:
        """Registra el video de entrada y su duracion; con ello el reporte puede
        derivar el ``realtime_factor`` (cuanto tardo el pipeline frente a la
        duracion real del video)."""
        self._input_video = str(video)
        self._input_duration_seconds = float(duration_seconds)

    def set_effective_config(self, **config: object) -> None:
        """Configuracion EFECTIVA con la que corre el pipeline (modelos, device,
        workers...). Sin esto, comparar reportes de dos corridas es imposible:
        no se sabria si una fue mas lenta por modelo distinto o por device."""
        self._effective_config.update({k: v for k, v in config.items() if v is not None})

    def add_warning(self, source: str, **details: object) -> None:
        """Registra una advertencia (calidad/entorno) para el reporte."""
        entry: dict[str, object] = {"source": source, "at": _utc_now_iso()}
        entry.update(details)
        self._warnings.append(entry)

    def mark_interrupted(self, signal_name: str) -> None:
        """Marca la corrida como interrumpida por una senal (SIGINT/SIGTERM).

        Escribe el snapshot inmediatamente: si el proceso tarda en morir
        (p.ej. ThreadPoolExecutor esperando futures en curso), el reporte ya
        documenta por que y cuando dejo de avanzar.
        """
        self._interrupted = {"signal": signal_name, "at": _utc_now_iso()}
        logger.warning(
            "pipeline.signal_received", signal=signal_name, run_id=self.run_id
        )
        self._flush_report()

    def annotate_stage(self, name: str, **kv: object) -> None:
        """Enriquece el metadata de una etapa DESPUES de haberla iniciado.

        Si la etapa aun no termino (no esta en el historial), la anotacion queda
        pendiente y se aplica al cerrarla; si ya termino, se aplica sobre su
        ultima entrada con ese nombre.
        """
        for stage in reversed(self._stages):
            if stage.name == name:
                stage.metadata.update(kv)
                break
        else:
            self._pending_annotations.setdefault(name, {}).update(kv)
        self._flush_report()

    def add_stats(self, stats: dict[str, list], counters: dict[str, int] | None = None) -> None:
        """Incorpora stats crudas recolectadas por la infraestructura."""
        for key, values in stats.items():
            self._stats.setdefault(key, []).extend(values)
        if counters:
            for key, n in counters.items():
                self._counters[key] = self._counters.get(key, 0) + n

    def set_outputs(self, **kv: object) -> None:
        """Registra artefactos generados (tamanos de video/subtitulos...)."""
        self._outputs.update({k: v for k, v in kv.items() if v is not None})

    def adopt_previous_report(self, path: Path) -> int:
        """Carga las etapas del reporte de la corrida anterior.

        Asi, cuando --resume salta etapas ya hechas, `record_resumed()` puede
        restaurar su duracion real en vez de anotar 0.0s. Devuelve cuantas
        etapas se adoptaron; si el archivo no existe o esta corrupto, adopta
        cero y la corrida sigue (con fallback a 0.0 solo si no hay dato).
        """
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
            stages = raw.get("stages") or []
            self._previous_stages = {
                s["name"]: s for s in stages if isinstance(s, dict) and "name" in s
            }
        except (OSError, json.JSONDecodeError, AttributeError):
            logger.warning("pipeline.timings_previous_unreadable", path=str(path))
            return 0
        # Los grupos de concurrencia tambien son parte del historial: si en la
        # corrida anterior transcription/diarization se solaparon, el reporte
        # reanudado debe seguir reflejando ese ahorro de tiempo.
        prev_groups = raw.get("concurrent_stage_groups") or []
        if prev_groups:
            self._concurrent_groups.extend(prev_groups)
        # Historial de runs: el reporte anterior puede traer la cadena ya
        # acumulada (campo nuevo "run_ids") o solo su "run_id" individual
        # (reportes viejos). Se preserva orden cronologico sin duplicados,
        # con la corrida actual siempre al final.
        prev_ids = raw.get("run_ids") or (
            [raw["run_id"]] if raw.get("run_id") else []
        )
        self._run_ids = list(dict.fromkeys([*prev_ids, *self._run_ids]))
        logger.info(
            "pipeline.timings_adopted_from_previous_run",
            stages=sorted(self._previous_stages),
            path=str(path),
        )
        return len(self._previous_stages)

    def report_progress(self, done: int, total: int) -> None:
        """Avance DENTRO de la etapa en curso (RM-56).

        Una etapa larga sin esto es indistinguible de una muerta: la sintesis
        de voz puede tardar diez minutos escribiendo tres lineas de log, que
        es exactamente lo que se ve cuando el worker muere a mitad.

        Se escribe sobre `current_stage`, que ya viaja a la UI en cada
        snapshot. Si no hay etapa en curso no hace nada: el progreso solo
        significa algo mientras algo corre.
        """
        if self._current_stage is None:
            return
        self._current_stage["progress"] = {"done": done, "total": total}
        self._flush_report()

    @contextmanager
    def stage(self, name: str, **metadata: object) -> Iterator[None]:
        """Cronometra un bloque de codigo como una etapa nombrada.

        Uso:
            with timings.stage("transcription"):
                ... trabajo real ...

        Cualquier ``metadata`` extra (p.ej. ``num_segments=39``) se loguea y
        se incluye en el reporte final, util para correlacionar duracion con
        volumen de trabajo entre corridas distintas.

        Al entrar escribe un snapshot del reporte (con ``current_stage``
        apuntando a esta etapa) y al salir escribe otro ya con su duracion.

        Si el bloque lanza una excepcion, la etapa NO se agrega como
        "completed" (no llego a terminar) -- ``current_stage`` se deja tal
        cual, apuntando a esta etapa, para que el reporte refleje donde se
        interrumpio realmente en vez de mostrarla como exitosa con una
        duracion que en los hechos midio hasta el punto del error.
        """
        log = logger.bind(run_id=self.run_id, stage=name, **metadata)
        log.info("pipeline.stage_started")
        start = time.monotonic()
        started_at = _utc_now_iso()
        self._current_stage = {"name": name, "started_at": started_at}
        self._flush_report()
        try:
            yield
        except BaseException:
            log.info("pipeline.stage_failed", seconds=round(time.monotonic() - start, 2))
            self._flush_report()
            raise
        else:
            elapsed = time.monotonic() - start
            self._current_stage = None
            self._append(
                StageTiming(
                    name=name,
                    seconds=elapsed,
                    status=STATUS_COMPLETED,
                    started_at=started_at,
                    ended_at=_utc_now_iso(),
                    metadata=dict(metadata),
                )
            )
            log.info("pipeline.stage_finished", seconds=round(elapsed, 2))
            self._flush_report()

    def record(self, name: str, seconds: float, **metadata: object) -> None:
        """Registra una duracion ya medida externamente (p.ej. una etapa que
        corrio en un hilo aparte, cronometrada a mano)."""
        self._append(
            StageTiming(
                name=name,
                seconds=seconds,
                status=STATUS_COMPLETED,
                started_at=_utc_now_minus_iso(seconds),
                ended_at=_utc_now_iso(),
                metadata=dict(metadata),
            )
        )
        logger.bind(run_id=self.run_id, stage=name, **metadata).info(
            "pipeline.stage_finished", seconds=round(seconds, 2)
        )
        self._flush_report()

    def record_resumed(self, name: str, **metadata: object) -> None:
        """Registra una etapa que --resume salto porque ya estaba hecha.

        Conserva la duracion REAL que tuvo en la corrida anterior (via
        `adopt_previous_report`) marcandola con ``status="resumed"``; si no
        hay dato previo cae a 0.0 para no inventar numeros. El metadata
        descriptivo de la corrida anterior (p.ej. ``num_segments``) se
        arrastra tambien, junto con cualquier metadata nueva.
        """
        prev = self._previous_stages.get(name) or {}
        seconds = float(prev.get("seconds") or 0.0)
        carried = {
            k: v for k, v in prev.items() if k not in _RESERVED_STAGE_KEYS and k != "resumed"
        }
        self._append(
            StageTiming(
                name=name,
                seconds=seconds,
                status=STATUS_RESUMED,
                started_at=prev.get("started_at"),
                ended_at=prev.get("ended_at"),
                metadata={**carried, **dict(metadata)},
            )
        )
        logger.bind(run_id=self.run_id, stage=name, resumed=True, **metadata).info(
            "pipeline.stage_resumed", previous_seconds=round(seconds, 2)
        )
        self._flush_report()

    def mark_concurrent(self, stage_names: list[str]) -> None:
        """Anota que estas etapas corrieron EN PARALELO (mismo tramo de
        tiempo real), para que el reporte final no de a entender que sus
        duraciones se suman al tiempo total — se solapan."""
        self._concurrent_groups.append(list(stage_names))

    @property
    def total_seconds(self) -> float:
        return time.monotonic() - self._run_start

    def _append(self, stage: StageTiming) -> None:
        stage.metadata = {
            k: v for k, v in stage.metadata.items() if k not in _RESERVED_STAGE_KEYS
        }
        pending = self._pending_annotations.pop(stage.name, None)
        if pending:
            pending = {k: v for k, v in pending.items() if k not in _RESERVED_STAGE_KEYS}
            stage.metadata.update(pending)
        self._stages.append(stage)

    def as_dict(self) -> dict:
        total = self.total_seconds
        # El % de cada etapa se calcula contra el TRABAJO TOTAL registrado
        # (incluyendo duraciones heredadas de una corrida anterior al
        # reanudar), no contra el tiempo de pared de esta corrida: con
        # --resume el tiempo de pared es menor que la suma y los porcentajes
        # saldrian >100%, enganosos.
        stages_seconds_sum = round(sum(s.seconds for s in self._stages), 2)
        stages = [
            self._stage_to_dict(s, order=i, work_total=stages_seconds_sum)
            for i, s in enumerate(self._stages, start=1)
        ]
        stages_total = round(sum(s["seconds"] for s in stages), 2)
        report: dict = {
            "run_id": self.run_id,
            "run_ids": list(self._run_ids),
            "started_at": self._started_at_iso,
            "generated_at": _utc_now_iso(),
            "completed": self._completed,
            "resumed_run": self._resumed_run,
            "total_seconds": round(total, 2),
            "num_stages": len(stages),
            "sum_of_stage_seconds": stages_total,
            "overhead_seconds": round(max(0.0, total - stages_total), 2),
            "parallel_time_saved_seconds": self._parallel_time_saved(),
            "concurrent_stage_groups": self._concurrent_groups,
        }
        if self._input_video is not None:
            duration = self._input_duration_seconds
            report["input"] = {
                "video": self._input_video,
                "duration_seconds": round(duration, 2) if duration is not None else None,
            }
            if duration and duration > 0:
                # x1.0 = tiempo real; x4.0 = el pipeline tardo 4 veces la duracion del video.
                report["realtime_factor"] = round(total / duration, 2)
        if self._effective_config:
            report["effective_config"] = dict(self._effective_config)
        if self._warnings:
            report["warnings"] = list(self._warnings)
        if self._stats or self._counters:
            report["stats"] = {
                **{k: list(v) for k, v in self._stats.items()},
                **{f"counter.{k}": n for k, n in self._counters.items()},
            }
        if self._outputs:
            report["outputs"] = dict(self._outputs)
        if self._interrupted:
            report["interrupted"] = dict(self._interrupted)
        report["stages"] = stages
        if self._current_stage is not None:
            report["current_stage"] = dict(self._current_stage)
        return report

    @staticmethod
    def _stage_to_dict(s: StageTiming, order: int, work_total: float) -> dict:
        return {
            "order": order,
            "name": s.name,
            "status": s.status,
            "seconds": round(s.seconds, 2),
            "percent_of_total": round(100 * s.seconds / work_total, 1) if work_total > 0 else 0.0,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            **s.metadata,
        }

    def _parallel_time_saved(self) -> float:
        """Segundos ahorrados por correr etapas en paralelo: por cada grupo
        concurrente, cuanto sobro del maximo (lo que se solapo)."""
        by_name = {s.name: s.seconds for s in self._stages}
        saved = 0.0
        for group in self._concurrent_groups:
            secs = [by_name.get(name, 0.0) for name in group]
            if len(secs) > 1:
                saved += sum(secs) - max(secs)
        return round(saved, 2)

    def write_report(self, output_path: Path, final: bool = False) -> Path:
        """Escribe el reporte JSON. Con ``final=True`` marca el snapshot como
        corrida completada (`"completed": true`); los snapshots incrementales
        intermedios quedan con ``false``."""
        if final:
            self._completed = True
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(self.as_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return output_path

    def _flush_report(self) -> None:
        """Snapshot incremental a disco (silencioso si no hay ruta configurada)."""
        if self._report_path is None:
            return
        try:
            self.write_report(self._report_path)
        except OSError as exc:
            logger.warning("pipeline.timings_write_failed", error=str(exc))
