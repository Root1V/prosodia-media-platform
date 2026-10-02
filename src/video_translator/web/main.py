"""App FastAPI del dashboard web (Prosodia)."""

from __future__ import annotations

# Antes de importar los routers (ver RM-41): `init()` instala el puente de
# logging, y lo que se importe antes se queda con el handler viejo. La
# identidad y el destino salen del entorno (OTEL_*), asi que este fichero no
# cambia entre maquinas. Para no exportar nada hace falta ARGUS_DISABLED=1: sin
# OTEL_EXPORTER_OTLP_ENDPOINT el SDK no calla, cae al agente en localhost.
import argus

argus.init()

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from video_translator.utils.logging_config import export_stdlib_loggers
from video_translator.web.config import load_web_settings
from video_translator.web.routers import (
    auth,
    dashboard,
    media,
    music_tracks,
    projects,
    samples,
    users,
)

settings = load_web_settings()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Engancha los logs de la API al exportador de telemetria.

    Aqui y no al importar el modulo: uvicorn configura su logging con
    `dictConfig` despues de importar la app, y eso reemplaza los handlers de
    `uvicorn.access` y `uvicorn.error`. Enganchar antes no da error, se pierde
    sin avisar.

    Son los loggers de uvicorn y no los nuestros porque la API no escribe por
    structlog: sus unicos registros son los de peticion y los de error del
    servidor, y los emite uvicorn. Sin esto la API exporta trazas pero ni un
    solo registro -- se midio: 55 spans y cero logs.
    """
    enganchados = export_stdlib_loggers(("uvicorn.access", "uvicorn.error"))
    if enganchados:
        logging.getLogger("uvicorn.error").info(
            "argus.logs_bridged", extra={"loggers": ",".join(enganchados)}
        )
    yield


app = FastAPI(title="Prosodia Web API", lifespan=lifespan)

# Abre el span de servidor y adopta el contexto entrante segun
# ARGUS_TRUST_INBOUND (antes ARGUS_PROPAGATE, renombrada en el SDK porque
# chocaba de nombre con el modulo argus.propagate, que es otra cosa).
# Por defecto `never`: un llamante externo no puede inyectar el identificador
# con el que se registran sus peticiones.
app.add_middleware(argus.ASGIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(media.router, prefix="/api")
app.include_router(samples.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(music_tracks.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
