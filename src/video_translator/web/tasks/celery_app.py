"""App Celery del dashboard web."""

from __future__ import annotations

# El worker es un PROCESO APARTE: no hereda nada de la API (ver RM-41). Sin
# esta llamada, encolar produce una traza y procesar produce otra, y la unidad
# de trabajo queda partida en dos justo donde cruza la cola.
#
# En el proceso de la API esto tambien se ejecuta (el router importa la tarea)
# y es inofensivo: `init()` es idempotente y `main.py` ya la llamo antes con la
# identidad de la API.
import argus

argus.init()

from celery import Celery

from video_translator.web.config import load_web_settings

_settings = load_web_settings()

celery_app = Celery(
    "prosodia_web",
    broker=_settings.redis_url,
    backend=_settings.redis_url,
)

# Import explicito (en vez de autodiscover_tasks, pensado para layouts tipo
# Django) para que el modulo quede registrado en este app de Celery.
import video_translator.web.tasks.run_project  # noqa: F401
