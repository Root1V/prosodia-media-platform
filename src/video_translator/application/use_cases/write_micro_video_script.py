"""Convierte una idea suelta en un guion narrable para un micro-video (RM-42).

Por que es un caso de uso APARTE y no un paso dentro de GenerateMicroVideoUseCase:
el guion tiene que existir ANTES de generar el video, porque el usuario lo lee y
lo corrige. GenerateMicroVideoUseCase corre en el worker, al final, cuando ya no
hay nadie mirando; meterlo ahi significaria generar el video con un texto que
nadie aprobo.
"""

from __future__ import annotations

import structlog

from video_translator.application.interfaces import ScriptWriter
from video_translator.domain.exceptions import VideoTranslatorError

logger = structlog.get_logger(__name__)

# Una idea no es un guion: si llega algo largo, probablemente el usuario pego el
# guion entero y no hay nada que generar. El tope evita mandarle al LLM un texto
# que no es lo que el prompt espera.
MAX_IDEA_CHARS = 2000


class WriteMicroVideoScriptUseCase:
    def __init__(self, script_writer: ScriptWriter) -> None:
        self._script_writer = script_writer

    def execute(self, idea: str, objective: str, target_seconds: float | None) -> str:
        idea = idea.strip()
        if not idea:
            raise VideoTranslatorError("La idea no puede estar vacia.")
        if len(idea) > MAX_IDEA_CHARS:
            raise VideoTranslatorError(
                f"La idea es demasiado larga ({len(idea)} caracteres, maximo {MAX_IDEA_CHARS}). "
                "Si ya tienes el guion escrito, pegalo directamente en el texto a narrar."
            )

        log = logger.bind(objective=objective, idea_chars=len(idea))
        log.info("write_script.start")
        script = self._script_writer.write_script(idea, objective, target_seconds)
        script = script.strip()
        if not script:
            # Un LLM puede devolver vacio sin fallar. Tratarlo como exito deja al
            # usuario con el campo en blanco y sin saber si fue el o el modelo.
            raise VideoTranslatorError(
                "El modelo devolvio un guion vacio. Intenta reformular la idea."
            )
        log.info("write_script.done", script_chars=len(script))
        return script
