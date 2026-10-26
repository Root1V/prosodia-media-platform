"""Tests de /api/dashboard/stats: agregados sobre Project + ProjectMetrics,
aislados por usuario."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from video_translator.web.db.models import (
    Project,
    ProjectMetrics,
    ProjectStatus,
    ServiceType,
    SourceType,
    User,
)


def _auth_headers(client: TestClient, email: str, password: str) -> dict[str, str]:
    resp = client.post("/api/auth/login", data={"username": email, "password": password})
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_project(db_session: Session, user: User, **overrides: object) -> Project:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "name": "Proyecto",
        "service_type": ServiceType.DUBBING,
        "source_type": SourceType.UPLOAD,
        "input_video_path": "/tmp/input.mp4",
        "output_dir": "/tmp/output",
        "output_mode": "dubbed",
        "config": {"source_lang": "en", "target_lang": "es"},
        "status": ProjectStatus.COMPLETED,
    }
    defaults.update(overrides)
    project = Project(**defaults)
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


def _make_metrics(db_session: Session, project: Project, **overrides: object) -> ProjectMetrics:
    defaults: dict[str, object] = {
        "project_id": project.id,
        "user_id": project.user_id,
        "project_name": project.name,
        "service_type": project.service_type.value,
        "status": "completed",
        "total_seconds": 10.0,
        "input_duration_seconds": 20.0,
        "realtime_factor": 0.5,
    }
    defaults.update(overrides)
    metrics = ProjectMetrics(**defaults)
    db_session.add(metrics)
    db_session.commit()
    return metrics


def test_dashboard_stats_requires_auth(client: TestClient) -> None:
    resp = client.get("/api/dashboard/stats")
    assert resp.status_code == 401


def test_dashboard_stats_empty_for_new_user(
    client: TestClient, make_user: Callable[..., User]
) -> None:
    make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    resp = client.get("/api/dashboard/stats", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body == {
        "total_projects": 0,
        "total_seconds_processed": 0.0,
        "distinct_languages": 0,
        "active_now": 0,
        "by_service": [],
        "activity": [],
        "outcomes": {"completed": 0, "failed": 0, "active": 0},
        "failure_reasons": [],
        "runs_vs_previous": {"current": 0, "previous": 0},
        # Sin ninguna corrida no hay de donde sacar un reparto de tiempo: el
        # panel enseña el estado inicial, no un grafico vacio.
        "stage_breakdown": None,
        "quality": {
            "runs_considered": 0,
            "runs_tts_on_cpu": 0,
            "runs_with_trimmed_segments": 0,
            "runs_with_warnings": 0,
        },
    }


def test_dashboard_stats_counts_projects_and_distinct_languages(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    user = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    _make_project(db_session, user, config={"source_lang": "en", "target_lang": "es"})
    _make_project(db_session, user, config={"source_lang": "en", "target_lang": "fr"})

    resp = client.get("/api/dashboard/stats", headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    assert body["total_projects"] == 2
    assert body["distinct_languages"] == 3  # en, es, fr


def test_dashboard_stats_sums_processed_seconds_from_metrics(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    user = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    project = _make_project(db_session, user)
    _make_metrics(db_session, project, input_duration_seconds=30.0)
    _make_metrics(db_session, project, input_duration_seconds=15.5)

    resp = client.get("/api/dashboard/stats", headers=headers)

    assert resp.status_code == 200
    assert resp.json()["total_seconds_processed"] == 45.5


def test_dashboard_stats_survives_project_deletion(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    user = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    project = _make_project(db_session, user)
    _make_metrics(db_session, project, input_duration_seconds=42.0)

    db_session.delete(project)
    db_session.commit()

    resp = client.get("/api/dashboard/stats", headers=headers)

    assert resp.status_code == 200
    # La fila de metricas sobrevive al borrado del proyecto (project_id
    # queda NULL via ondelete="SET NULL"), asi que sigue sumando.
    assert resp.json()["total_seconds_processed"] == 42.0
    assert resp.json()["total_projects"] == 0


def test_dashboard_stats_only_counts_current_user_projects(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    make_user(email="bob@example.com", password="secret456")
    _make_project(db_session, alice)

    bob_headers = _auth_headers(client, "bob@example.com", "secret456")
    resp = client.get("/api/dashboard/stats", headers=bob_headers)

    assert resp.status_code == 200
    assert resp.json()["total_projects"] == 0


def test_by_service_promedia_solo_las_completadas(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    """Una corrida que fallo a los 10s no dice lo que cuesta el servicio.

    Mezclarla en el promedio haria que mas fallos parecieran mas rapidez, que
    es exactamente la lectura contraria a la verdadera.
    """
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    proyecto = _make_project(db_session, alice)
    _make_metrics(db_session, proyecto, status="completed", total_seconds=600.0, realtime_factor=5.0)
    _make_metrics(db_session, proyecto, status="completed", total_seconds=400.0, realtime_factor=3.0)
    _make_metrics(db_session, proyecto, status="failed", total_seconds=10.0, realtime_factor=0.1)
    db_session.commit()

    body = client.get("/api/dashboard/stats", headers=headers).json()
    (fila,) = body["by_service"]

    assert fila["service_type"] == "dubbing"
    assert (fila["total"], fila["completed"], fila["failed"]) == (3, 2, 1)
    # (600 + 400) / 2 -- la fallida de 10s queda fuera.
    assert fila["avg_seconds"] == 500.0
    assert fila["avg_realtime_factor"] == 4.0


def test_by_service_deja_el_factor_en_none_donde_no_aplica(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    """Micro-video parte de una imagen: no hay duracion de entrada contra la
    que comparar, y un 0 ahi se leeria como "instantaneo"."""
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    proyecto = _make_project(db_session, alice)
    _make_metrics(
        db_session, proyecto, service_type="micro_video", status="completed",
        total_seconds=100.0, realtime_factor=None,
    )
    db_session.commit()

    (fila,) = client.get("/api/dashboard/stats", headers=headers).json()["by_service"]
    assert fila["avg_seconds"] == 100.0
    assert fila["avg_realtime_factor"] is None


def test_active_now_cuenta_los_que_siguen_en_marcha(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    _make_project(db_session, alice, status=ProjectStatus.RUNNING)
    _make_project(db_session, alice, status=ProjectStatus.QUEUED)
    _make_project(db_session, alice, status=ProjectStatus.COMPLETED)
    _make_project(db_session, alice, status=ProjectStatus.FAILED)
    db_session.commit()

    assert client.get("/api/dashboard/stats", headers=headers).json()["active_now"] == 2


def test_las_metricas_de_otro_usuario_no_se_mezclan(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    bob = make_user(email="bob@example.com", password="secret456")
    headers = _auth_headers(client, "bob@example.com", "secret456")

    proyecto = _make_project(db_session, alice)
    _make_metrics(db_session, proyecto, status="completed")
    _make_project(db_session, alice, status=ProjectStatus.RUNNING)
    db_session.commit()

    body = client.get("/api/dashboard/stats", headers=headers).json()
    assert body["by_service"] == []
    assert body["active_now"] == 0
    assert bob.id != alice.id


def test_reparto_de_tiempo_suma_las_listas_de_stats(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    """Una etapa que corre varias veces deja una entrada por invocacion.

    Quedarse con la primera subestimaria la fase: una transcripcion partida en
    tres tramos contaria solo el primero.
    """
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    proyecto = _make_project(db_session, alice)

    _make_metrics(
        db_session,
        proyecto,
        status="completed",
        total_seconds=100.0,
        stats={
            "transcription.model_load_and_inference_seconds": [5.0, 5.0],
            "tts.batch_wall_seconds": [80.0],
        },
    )
    db_session.commit()

    reparto = client.get("/api/dashboard/stats", headers=headers).json()["stage_breakdown"]
    fases = {f["phase"]: f["avg_seconds"] for f in reparto["phases"]}

    assert fases["transcription"] == 10.0
    assert fases["text_to_speech"] == 80.0
    # 100 - 90: lo que no cae en ninguna fase medida sigue contando, para que
    # las barras sumen el total en vez de dejar un hueco sin explicar.
    assert fases["other"] == 10.0


def test_senales_de_calidad_cuentan_lo_que_un_completado_esconde(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    proyecto = _make_project(db_session, alice)

    _make_metrics(
        db_session, proyecto, status="completed",
        effective_config={"tts_device_forced_cpu": True},
        stats={"counter.tts.overflow_trimmed_segments": 2},
        warnings_count=1,
    )
    _make_metrics(
        db_session, proyecto, status="completed",
        effective_config={"tts_device_forced_cpu": False}, stats={},
    )
    # Una fallida no cuenta: no llego a sintetizar nada.
    _make_metrics(
        db_session, proyecto, status="failed",
        effective_config={"tts_device_forced_cpu": True}, stats={},
    )
    db_session.commit()

    calidad = client.get("/api/dashboard/stats", headers=headers).json()["quality"]
    assert calidad == {
        "runs_considered": 2,
        "runs_tts_on_cpu": 1,
        "runs_with_trimmed_segments": 1,
        "runs_with_warnings": 1,
    }


def test_actividad_desglosa_por_desenlace(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    proyecto = _make_project(db_session, alice)

    _make_metrics(db_session, proyecto, status="completed")
    _make_metrics(db_session, proyecto, status="completed")
    _make_metrics(db_session, proyecto, status="failed")
    db_session.commit()

    body = client.get("/api/dashboard/stats", headers=headers).json()
    (punto,) = body["activity"]
    assert (punto["count"], punto["completed"], punto["failed"]) == (3, 2, 1)
    # El anillo mira TODAS las corridas, no solo las de los ultimos 30 dias.
    assert body["outcomes"] == {"completed": 2, "failed": 1, "active": 0}


def test_motivos_de_fallo_agrupan_el_mismo_error(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    """Los mensajes del pipeline acaban en detalles irrepetibles (puertos,
    rutas); agrupar por el principio junta las causas iguales."""
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")

    mismo = "Error de comunicacion con llama-server en http://localhost:8087"
    _make_project(db_session, alice, status=ProjectStatus.FAILED, error_message=f"{mismo}: errno 61")
    _make_project(db_session, alice, status=ProjectStatus.FAILED, error_message=f"{mismo}: errno 61")
    _make_project(db_session, alice, status=ProjectStatus.FAILED, error_message="Otro fallo distinto")
    # Un proyecto completado no es un motivo de fallo.
    _make_project(db_session, alice, status=ProjectStatus.COMPLETED)
    db_session.commit()

    motivos = client.get("/api/dashboard/stats", headers=headers).json()["failure_reasons"]
    assert [(m["reason"][: len(mismo)], m["count"]) for m in motivos] == [
        (mismo, 2),
        ("Otro fallo distinto", 1),
    ]


def test_sin_periodo_anterior_no_se_inventa_una_comparacion(
    client: TestClient, make_user: Callable[..., User], db_session: Session
) -> None:
    alice = make_user(email="alice@example.com", password="hunter2")
    headers = _auth_headers(client, "alice@example.com", "hunter2")
    _make_metrics(db_session, _make_project(db_session, alice), status="completed")
    db_session.commit()

    comparacion = client.get("/api/dashboard/stats", headers=headers).json()["runs_vs_previous"]
    assert comparacion == {"current": 1, "previous": 0}
