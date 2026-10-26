"""Pruebas de la ayuda de texto de la pagina de voz (RM-55)."""

from __future__ import annotations

import pytest

from video_translator.application.use_cases.assist_narration_text import (
    MAX_IDEA_CHARS,
    MAX_TEXT_CHARS,
    AssistNarrationTextUseCase,
)
from video_translator.domain.exceptions import VideoTranslatorError


class AsistenteFalso:
    """Registra con que se le llamo y devuelve lo que se le diga."""

    def __init__(self, respuesta: str = "texto generado") -> None:
        self.respuesta = respuesta
        self.draft_llamado_con: tuple[str, str] | None = None
        self.polish_llamado_con: str | None = None

    def draft_narration(self, idea: str, language: str) -> str:
        self.draft_llamado_con = (idea, language)
        return self.respuesta

    def polish_narration(self, text: str) -> str:
        self.polish_llamado_con = text
        return self.respuesta


def test_draft_pasa_idea_e_idioma_y_devuelve_el_texto() -> None:
    asistente = AsistenteFalso("Hola, esto es una narracion.")
    caso = AssistNarrationTextUseCase(asistente)

    assert caso.draft("  habla de los Andes  ", "en") == "Hola, esto es una narracion."
    # La idea llega limpia de espacios, y el idioma elegido para el audio
    # viaja tal cual: en "draft" el idioma SI se impone.
    assert asistente.draft_llamado_con == ("habla de los Andes", "en")


def test_polish_no_recibe_idioma() -> None:
    """La firma es la garantia de que corregir no traduce."""
    asistente = AsistenteFalso("Texto corregido.")
    caso = AssistNarrationTextUseCase(asistente)

    assert caso.polish("  texto con herrores  ") == "Texto corregido."
    assert asistente.polish_llamado_con == "texto con herrores"

    import inspect

    firma = inspect.signature(type(asistente).polish_narration)
    assert "language" not in firma.parameters


@pytest.mark.parametrize("vacio", ["", "   ", "\n\t "])
def test_rechaza_entrada_vacia(vacio: str) -> None:
    caso = AssistNarrationTextUseCase(AsistenteFalso())
    with pytest.raises(VideoTranslatorError):
        caso.draft(vacio, "es")
    with pytest.raises(VideoTranslatorError):
        caso.polish(vacio)


def test_rechaza_entradas_demasiado_largas() -> None:
    caso = AssistNarrationTextUseCase(AsistenteFalso())
    with pytest.raises(VideoTranslatorError, match="demasiado larga"):
        caso.draft("x" * (MAX_IDEA_CHARS + 1), "es")
    with pytest.raises(VideoTranslatorError, match="demasiado largo"):
        caso.polish("x" * (MAX_TEXT_CHARS + 1))


def test_una_respuesta_vacia_del_modelo_es_un_error_no_un_exito() -> None:
    """Darla por buena en `polish` borraria el texto del usuario."""
    caso = AssistNarrationTextUseCase(AsistenteFalso("   \n  "))
    with pytest.raises(VideoTranslatorError, match="vacio"):
        caso.polish("un texto que el usuario escribio")
    with pytest.raises(VideoTranslatorError, match="vacio"):
        caso.draft("una idea", "es")
