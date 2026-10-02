"""Configuracion centralizada de logging usando structlog.

Se expone una unica funcion ``configure_logging`` para que tanto el CLI como
las pruebas de integracion inicialicen el logging de forma consistente.

Cuando se pasa ``log_file``, CADA linea que se ve en la consola tambien se
escribe a ese archivo (sin codigos de color ANSI, para que quede legible en
un editor de texto plano) — asi el log completo de una corrida queda
persistido junto al resto de los artefactos de salida (subtitulos,
pipeline_timings.json, etc.), no solo visible mientras el proceso corre.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import IO

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

# Atributos que `logging.LogRecord` se reserva: pasarlos por `extra` es un
# TypeError, asi que se filtran antes de reenviar el evento al puente.
_RESERVED_LOGRECORD_KEYS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
        "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
        "pathname", "process", "processName", "relativeCreated", "stack_info",
        "taskName", "thread", "threadName",
    }
)

_LEVEL_BY_METHOD = {
    "critical": logging.CRITICAL,
    "exception": logging.ERROR,
    "error": logging.ERROR,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "info": logging.INFO,
    "debug": logging.DEBUG,
}


def _otel_logging_handler() -> logging.Handler | None:
    """Handler que SOLO exporta a OpenTelemetry, o None si no se puede.

    Devuelve None si OpenTelemetry no esta instalado (la CLI puede correr sin
    el extra "web") o si nadie configuro un proveedor todavia -- la API de
    OpenTelemetry devuelve en ese caso un proveedor que no hace nada, y
    engancharse a el solo agregaria trabajo inutil por cada linea de log.

    Nivel NOTSET a proposito: quien decide es el logger al que se enganche.
    """
    try:
        from opentelemetry._logs import get_logger_provider
        from opentelemetry.sdk._logs import LoggingHandler
    except ImportError:
        return None

    provider = get_logger_provider()
    if not hasattr(provider, "get_logger") or type(provider).__name__.startswith("NoOp"):
        return None

    return LoggingHandler(level=logging.NOTSET, logger_provider=provider)


def export_stdlib_loggers(names: Iterable[str]) -> list[str]:
    """Engancha el exportador de telemetria a loggers de stdlib AJENOS.

    Para componentes que no escriben por structlog y por tanto no pasan por
    _DualRenderer: hoy la API, cuyos registros de peticion y de error los
    emite uvicorn por sus propios loggers. Sin esto la API exporta trazas pero
    ni un solo registro.

    No toca `propagate` ni los handlers que ya hubiera: agrega uno que solo
    exporta, asi que la salida por consola de ese logger no cambia.

    CUIDADO CON EL MOMENTO: uvicorn configura su logging con `dictConfig`
    DESPUES de importar la app, y eso REEMPLAZA los handlers de
    `uvicorn.access` y `uvicorn.error`. Enganchar al importar no falla, se
    pierde en silencio -- comprobado. Hay que llamar a esto desde el arranque
    de la app (ver el lifespan de web/main.py).

    Devuelve los nombres a los que si se engancho, para poder registrarlo.
    """
    handler = _otel_logging_handler()
    if handler is None:
        return []

    enganchados = []
    for name in names:
        logger = logging.getLogger(name)
        if not any(isinstance(h, type(handler)) for h in logger.handlers):
            logger.addHandler(handler)
            enganchados.append(name)
    return enganchados


def _build_otel_bridge(level: int) -> logging.Logger | None:
    """Logger de stdlib enchufado SOLO al exportador de OpenTelemetry.

    El puente de logging de un SDK de observabilidad se engancha al logger
    raiz de stdlib, pero esta app escribe a consola/archivo directamente
    desde structlog (ver _DualRenderer) sin pasar nunca por stdlib -- asi
    que para el puente los logs del pipeline sencillamente no existen. Se
    midio: 21 minutos de doblaje real exportaron CERO registros.

    Este logger existe para cerrar ese hueco sin cambiar lo que se ve. Lleva
    `propagate = False` a proposito: no debe llegar a los handlers de consola
    del root, o cada linea del pipeline se imprimiria dos veces. Su unico
    handler exporta.

    Devuelve None si OpenTelemetry no esta instalado (la CLI no trae el extra
    "web") o si nadie configuro un proveedor todavia, en cuyo caso el
    comportamiento es identico al de antes.
    """
    handler = _otel_logging_handler()
    if handler is None:
        return None

    bridge = logging.getLogger("prosodia.pipeline")
    bridge.propagate = False
    # Nivel EXPLICITO, no heredado: el root de stdlib arranca en WARNING y
    # nadie lo baja (un SDK que respete la configuracion ajena solo lo toca
    # si estaba en NOTSET, y no lo esta). Heredandolo, todo lo que fuera INFO
    # se descartaba aqui sin llegar al exportador -- medido. Este logger es
    # nuestro, asi que sigue el nivel que la app ya eligio para structlog.
    bridge.setLevel(level)
    if not bridge.handlers:
        bridge.addHandler(handler)
    return bridge


class _DualRenderer:
    """Ultimo processor de la cadena: renderiza el evento DOS VECES (con
    color para la consola, en texto plano para el archivo) y escribe ambas
    copias directamente, en vez de dejar que structlog imprima una sola
    salida generica. Termina la cadena con ``DropEvent`` para que ningun
    processor/logger posterior vuelva a imprimir lo mismo.

    Si hay un exportador de OpenTelemetry configurado, reenvia ademas una
    TERCERA copia al puente (ver _build_otel_bridge): la version en texto
    plano como cuerpo, y los campos del evento como atributos estructurados.
    Esa copia no se imprime en ningun lado.
    """

    def __init__(
        self,
        console_stream: IO[str],
        file_stream: IO[str] | None,
        json_logs: bool,
        otel_bridge: logging.Logger | None = None,
    ) -> None:
        self._console_stream = console_stream
        self._file_stream = file_stream
        self._otel_bridge = otel_bridge
        self._console_renderer: Processor
        self._file_renderer: Processor
        if json_logs:
            self._console_renderer = structlog.processors.JSONRenderer()
            self._file_renderer = structlog.processors.JSONRenderer()
        else:
            self._console_renderer = structlog.dev.ConsoleRenderer(colors=True)
            self._file_renderer = structlog.dev.ConsoleRenderer(colors=False)

    def __call__(self, logger: WrappedLogger, method_name: str, event_dict: EventDict) -> None:
        console_line = self._console_renderer(logger, method_name, dict(event_dict))
        self._console_stream.write(str(console_line) + "\n")
        self._console_stream.flush()

        plain_line: str | None = None
        if self._file_stream is not None:
            plain_line = str(self._file_renderer(logger, method_name, dict(event_dict)))
            self._file_stream.write(plain_line + "\n")
            self._file_stream.flush()

        if self._otel_bridge is not None:
            # Sin color: el cuerpo termina en un almacen de logs, y los codigos
            # ANSI ahi solo son ruido.
            if plain_line is None:
                plain_line = str(self._file_renderer(logger, method_name, dict(event_dict)))
            attributes = {
                key: value
                for key, value in event_dict.items()
                if key not in _RESERVED_LOGRECORD_KEYS and key != "event"
            }
            self._otel_bridge.log(
                _LEVEL_BY_METHOD.get(method_name, logging.INFO), plain_line, extra=attributes
            )

        raise structlog.DropEvent


def configure_logging(level: str = "INFO", json_logs: bool = False, log_file: Path | None = None) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(format="%(message)s", level=numeric_level)

    file_handle: IO[str] | None = None
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Deliberadamente sin "with": este handle debe seguir abierto durante
        # TODA la corrida (se escribe una linea por cada evento de log), no
        # solo dentro de esta funcion de configuracion. Lo cierra el SO al
        # terminar el proceso.
        file_handle = open(log_file, "w", encoding="utf-8")  # noqa: SIM115

    processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        _DualRenderer(
            console_stream=sys.stdout,
            file_stream=file_handle,
            json_logs=json_logs,
            otel_bridge=_build_otel_bridge(numeric_level),
        ),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        # _DualRenderer ya escribio todo y corta la cadena con DropEvent;
        # este logger nunca llega a ejecutarse, pero structlog igual
        # requiere una factory valida.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
