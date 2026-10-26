"""Esquemas de analitica de negocio (dashboard/stats)."""

from __future__ import annotations

from pydantic import BaseModel


class ServiceStatsOut(BaseModel):
    """Una fila por servicio usado, desde ProjectMetrics (RM-60).

    Los promedios salen SOLO de las corridas completadas: una que fallo a los
    10 segundos no dice nada de lo que cuesta el servicio, y mezclarlas haria
    que mas fallos parecieran mas rapidez.
    """

    service_type: str
    total: int
    completed: int
    failed: int
    avg_seconds: float | None
    # None donde no aplica: micro-video y TTS parten de texto/imagen, asi que
    # no hay una "duracion de entrada" contra la que comparar.
    avg_realtime_factor: float | None


class ActivityPointOut(BaseModel):
    day: str
    count: int


class StagePhaseOut(BaseModel):
    phase: str
    avg_seconds: float


class StageBreakdownOut(BaseModel):
    """Donde se va el tiempo del servicio mas pesado (RM-61)."""

    service_type: str
    runs: int
    avg_total_seconds: float
    phases: list[StagePhaseOut]


class QualityOut(BaseModel):
    """Lo que salio bien a medias y un "completado" no cuenta (RM-61)."""

    runs_considered: int
    runs_tts_on_cpu: int
    runs_with_trimmed_segments: int
    runs_with_warnings: int


class DashboardStatsOut(BaseModel):
    total_projects: int
    # Suma de la duracion de entrada de las corridas completadas/fallidas del
    # usuario (ver ProjectMetrics.input_duration_seconds) -- no cubre TTS
    # standalone, que no tiene un "input" de duracion (texto, no audio/video).
    total_seconds_processed: float
    distinct_languages: int
    # Proyectos en cola o corriendo AHORA (sobre Project, no sobre las
    # metricas: estas son la foto del final de una corrida).
    active_now: int
    by_service: list[ServiceStatsOut]
    # Un punto por dia con actividad en los ultimos 30 dias. Los dias vacios
    # no viajan: los rellena el frontend, que es quien sabe cuantos pintar.
    activity: list[ActivityPointOut]
    # None cuando no hay ninguna corrida completada de la que sacarlo.
    stage_breakdown: StageBreakdownOut | None
    quality: QualityOut
