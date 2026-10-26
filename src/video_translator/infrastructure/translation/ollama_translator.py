"""Implementacion de Translator usando un LLM open source servido localmente por Ollama.

Se elige un LLM instructivo en lugar de un modelo NMT clasico (NLLB, M2M100) porque
el requisito central del proyecto es poder **guiar la traduccion con un prompt de
contexto en lenguaje natural** (dominio, tono, glosario, audiencia).

La logica de construccion de prompts y parseo de la respuesta vive en
``prompting.py`` y es compartida con otros backends (p.ej. ``LlamaServerTranslator``);
aqui solo se resuelve el transporte HTTP especifico de la API nativa de Ollama
(``POST /api/chat``).
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from video_translator.domain.exceptions import TranslationError
from video_translator.domain.models import TranscriptSegment, TranslationContext
from video_translator.infrastructure.translation.prompting import (
    NARRATION_DRAFT_PROMPT,
    NARRATION_POLISH_PROMPT,
    build_narration_draft_user_prompt,
    build_narration_polish_user_prompt,
    build_script_system_prompt,
    build_script_user_prompt,
    build_summary_system_prompt,
    build_summary_user_prompt,
    build_system_prompt,
    build_user_prompt,
    parse_numbered_lines,
    translate_batch_with_recovery,
)
from video_translator.utils.logging_config import get_logger

logger = get_logger(__name__)


class OllamaTranslator:
    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen2.5:14b-instruct",
        temperature: float = 0.2,
        timeout_seconds: float = 120.0,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._temperature = temperature
        self._timeout = timeout_seconds

    def translate_batch(
        self,
        segments: list[TranscriptSegment],
        context: TranslationContext,
        rolling_history: list[str],
    ) -> list[str]:
        if not segments:
            return []

        def _translate_subset(subset: list[TranscriptSegment]) -> list[str]:
            system_prompt = build_system_prompt(context)
            user_prompt = build_user_prompt(
                subset, rolling_history, speaker_genders=context.speaker_genders
            )
            raw_response = self._call_llm(system_prompt, user_prompt)
            return parse_numbered_lines(raw_response, expected=len(subset))

        return translate_batch_with_recovery(segments, _translate_subset)

    def summarize(self, text: str) -> str:
        return self._call_llm(build_summary_system_prompt(), build_summary_user_prompt(text))

    def write_script(self, idea: str, objective: str, target_seconds: float | None) -> str:
        return self._call_llm(
            build_script_system_prompt(objective),
            build_script_user_prompt(idea, target_seconds),
        ).strip()

    def draft_narration(self, idea: str, language: str) -> str:
        return self._call_llm(
            NARRATION_DRAFT_PROMPT,
            build_narration_draft_user_prompt(idea, language),
        ).strip()

    def polish_narration(self, text: str) -> str:
        return self._call_llm(
            NARRATION_POLISH_PROMPT,
            build_narration_polish_user_prompt(text),
        ).strip()

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        retry=retry_if_exception_type((httpx.HTTPError, TranslationError)),
    )
    def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "options": {"temperature": self._temperature},
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(f"{self._host}/api/chat", json=payload)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranslationError(
                f"Error de comunicacion con Ollama en {self._host}: {exc}. "
                "Verifica que 'ollama serve' este activo y el modelo descargado "
                f"('ollama pull {self._model}')."
            ) from exc

        data = response.json()
        content = data.get("message", {}).get("content", "")
        if not content.strip():
            raise TranslationError("Ollama devolvio una respuesta vacia.")
        return content
