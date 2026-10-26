"""Router de analitica de negocio: agregados sobre Project + ProjectMetrics.

Alcance de negocio, no de progreso en vivo: `services/status_reader.py` sigue
siendo la fuente para el detalle de un proyecto individual (polling de
`/projects/{id}/status`); este router responde "cuanto ha procesado este
usuario en total", para el home del dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from video_translator.web.db.models import Project, ProjectMetrics, ProjectStatus, User
from video_translator.web.deps import get_current_user, get_db_session
from video_translator.web.schemas.dashboard import (
    ActivityPointOut,
    DashboardStatsOut,
    FailureReasonOut,
    OutcomesOut,
    PeriodComparisonOut,
    QualityOut,
    ServiceStatsOut,
    StageBreakdownOut,
)
from video_translator.web.services.dashboard_metrics import (
    reparto_de_tiempo,
    senales_de_calidad,
)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_LANGUAGE_CONFIG_KEYS = ("source_lang", "target_lang")

# Ventana del grafico de actividad. 30 dias entra en una fila de barras sin
# que cada una quede en un pixel, y es el horizonte en el que uno se pregunta
# "¿que he estado haciendo?".
_ACTIVITY_DAYS = 30

# Cuantos motivos de fallo distintos se listan. Mas de cinco deja de ser un
# ranking y pasa a ser el log de errores, que ya esta en cada proyecto.
_MAX_MOTIVOS = 5
# Los mensajes del pipeline son largos y acaban en detalles irrepetibles
# (rutas, puertos, trazas). Agrupar por el principio junta las causas iguales
# sin fundir dos distintas.
_LARGO_MOTIVO = 90


@router.get("/stats", response_model=DashboardStatsOut)
def get_dashboard_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session),
) -> DashboardStatsOut:
    total_projects = db.execute(
        select(func.count()).select_from(Project).where(Project.user_id == current_user.id)
    ).scalar_one()

    total_seconds_processed = db.execute(
        select(func.coalesce(func.sum(ProjectMetrics.input_duration_seconds), 0.0)).where(
            ProjectMetrics.user_id == current_user.id
        )
    ).scalar_one()

    configs = db.execute(select(Project.config).where(Project.user_id == current_user.id)).scalars().all()
    languages = {
        config[key]
        for config in configs
        for key in _LANGUAGE_CONFIG_KEYS
        if config and config.get(key)
    }

    active_now = db.execute(
        select(func.count())
        .select_from(Project)
        .where(
            Project.user_id == current_user.id,
            Project.status.in_(
                [ProjectStatus.QUEUED, ProjectStatus.DOWNLOADING, ProjectStatus.RUNNING]
            ),
        )
    ).scalar_one()

    # Los promedios se calculan SOLO sobre las completadas: una corrida que
    # fallo a los 10 segundos no dice nada de lo que cuesta el servicio, y
    # mezclarla haria que mas fallos parecieran mas rapidez.
    completadas = ProjectMetrics.status == "completed"
    filas = db.execute(
        select(
            ProjectMetrics.service_type,
            func.count(),
            func.sum(case((completadas, 1), else_=0)),
            func.sum(case((ProjectMetrics.status == "failed", 1), else_=0)),
            func.avg(case((completadas, ProjectMetrics.total_seconds))),
            func.avg(case((completadas, ProjectMetrics.realtime_factor))),
        )
        .where(ProjectMetrics.user_id == current_user.id)
        .group_by(ProjectMetrics.service_type)
        .order_by(func.count().desc())
    ).all()

    by_service = [
        ServiceStatsOut(
            service_type=service_type,
            total=total,
            completed=int(completed or 0),
            failed=int(failed or 0),
            avg_seconds=float(avg_seconds) if avg_seconds is not None else None,
            avg_realtime_factor=float(avg_factor) if avg_factor is not None else None,
        )
        for service_type, total, completed, failed, avg_seconds, avg_factor in filas
    ]

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    desde = ahora - timedelta(days=_ACTIVITY_DAYS)
    dia = func.date(ProjectMetrics.created_at)
    actividad = db.execute(
        select(
            dia,
            func.count(),
            func.sum(case((completadas, 1), else_=0)),
            func.sum(case((ProjectMetrics.status == "failed", 1), else_=0)),
        )
        .where(ProjectMetrics.user_id == current_user.id, ProjectMetrics.created_at >= desde)
        .group_by(dia)
        .order_by(dia)
    ).all()

    # Los 30 dias anteriores a los 30 actuales, para poder decir "mas o menos
    # que antes" en vez de dar un numero suelto que no compara con nada.
    anterior = db.execute(
        select(func.count())
        .select_from(ProjectMetrics)
        .where(
            ProjectMetrics.user_id == current_user.id,
            ProjectMetrics.created_at >= ahora - timedelta(days=_ACTIVITY_DAYS * 2),
            ProjectMetrics.created_at < desde,
        )
    ).scalar_one()

    # Los motivos salen de Project, no de las metricas: el mensaje de error no
    # se copia a ProjectMetrics, asi que esta lista solo cubre los proyectos
    # que siguen existiendo.
    motivo = func.substr(Project.error_message, 1, _LARGO_MOTIVO)
    motivos = db.execute(
        select(motivo, func.count())
        .where(
            Project.user_id == current_user.id,
            Project.status == ProjectStatus.FAILED,
            Project.error_message.isnot(None),
        )
        .group_by(motivo)
        .order_by(func.count().desc())
        .limit(_MAX_MOTIVOS)
    ).all()

    # Las columnas JSON se agregan en Python: `stats` guarda listas y sumarlas
    # en SQL seria ilegible (ver services/dashboard_metrics.py).
    metricas = list(
        db.execute(
            select(ProjectMetrics).where(ProjectMetrics.user_id == current_user.id)
        ).scalars()
    )
    reparto = reparto_de_tiempo(metricas)

    return DashboardStatsOut(
        total_projects=total_projects,
        total_seconds_processed=float(total_seconds_processed or 0.0),
        distinct_languages=len(languages),
        active_now=active_now,
        by_service=by_service,
        # `func.date` devuelve date en Postgres y str en SQLite: se normaliza
        # a ISO aqui para que el contrato no dependa del motor.
        activity=[
            ActivityPointOut(day=str(d), count=n, completed=int(ok or 0), failed=int(ko or 0))
            for d, n, ok, ko in actividad
        ],
        stage_breakdown=StageBreakdownOut(**reparto) if reparto else None,
        quality=QualityOut(**senales_de_calidad(metricas)),
        outcomes=OutcomesOut(
            completed=sum(s.completed for s in by_service),
            failed=sum(s.failed for s in by_service),
            active=active_now,
        ),
        failure_reasons=[FailureReasonOut(reason=r, count=n) for r, n in motivos],
        runs_vs_previous=PeriodComparisonOut(
            current=sum(n for _, n, _, _ in actividad),
            previous=anterior,
        ),
    )
