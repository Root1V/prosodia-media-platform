"""Ayuda con el texto a narrar de un proyecto de voz (RM-55).

Dos operaciones, no una: redactar un texto a partir de una idea cuando el
campo esta vacio, y corregir el que ya hay. El caso de uso existe para poner
los limites que el puerto no puede poner -- que haya algo que procesar, que no
sea tan largo que el prompt deje de tener sentido, y que un LLM que devuelve
vacio se note en vez de borrarle el texto al usuario.
"""

from __future__ import annotations

import structlog

from video_translator.application.interfaces import NarrationAssistant
from video_translator.domain.exceptions import VideoTranslatorError

logger = structlog.get_logger(__name__)

# Una idea no es el texto final: si llega algo largo, probablemente el usuario
# ya escribio lo que queria y no hay nada que redactar.
MAX_IDEA_CHARS = 2000
# Corregir si admite un texto largo -- es el caso normal -- pero no ilimitado:
# el modelo tiene una ventana de contexto y pasarse devuelve un texto truncado,
# que aqui significaria perderle media narracion al usuario.
MAX_TEXT_CHARS = 8000


class AssistNarrationTextUseCase:
    def __init__(self, assistant: NarrationAssistant) -> None:
        self._assistant = assistant

    def draft(self, idea: str, language: str) -> str:
        idea = idea.strip()
        if not idea:
            raise VideoTranslatorError("Escribe de que quieres que hable el audio.")
        if len(idea) > MAX_IDEA_CHARS:
            raise VideoTranslatorError(
                f"La idea es demasiado larga ({len(idea)} caracteres, maximo {MAX_IDEA_CHARS}). "
                "Si ya tienes el texto escrito, usa la opcion de mejorarlo."
            )
        log = logger.bind(language=language, idea_chars=len(idea))
        log.info("narration.draft.start")
        return self._validar(self._assistant.draft_narration(idea, language), log, "draft")

    def polish(self, text: str) -> str:
        text = text.strip()
        if not text:
            raise VideoTranslatorError("No hay texto que mejorar.")
        if len(text) > MAX_TEXT_CHARS:
            raise VideoTranslatorError(
                f"El texto es demasiado largo ({len(text)} caracteres, maximo {MAX_TEXT_CHARS}) "
                "para corregirlo de una vez."
            )
        log = logger.bind(text_chars=len(text))
        log.info("narration.polish.start")
        return self._validar(self._assistant.polish_narration(text), log, "polish")

    @staticmethod
    def _validar(resultado: str, log: structlog.BoundLogger, operacion: str) -> str:
        resultado = resultado.strip()
        if not resultado:
            # Un LLM puede devolver vacio sin fallar. Darlo por bueno dejaria el
            # campo en blanco -- y en `polish`, con el texto del usuario ya
            # borrado y sin saber si fue el o el modelo.
            raise VideoTranslatorError(
                "El modelo devolvio un texto vacio. Vuelve a intentarlo."
            )
        log.info(f"narration.{operacion}.done", result_chars=len(resultado))
        return resultado
