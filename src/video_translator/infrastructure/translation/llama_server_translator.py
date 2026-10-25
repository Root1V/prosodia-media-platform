"""Implementacion de Translator para servidores con API compatible con OpenAI.

Cubre ``llama-server`` (llama.cpp), pero tambien sirve para cualquier otro
runtime que exponga ``POST /v1/chat/completions`` con el formato de OpenAI
(vLLM, LM Studio, text-generation-webui en modo openai, etc.).

Ejemplo de uso: correr localmente un modelo GGUF cuantizado como
``gpt-oss-20b-mxfp4`` con:

    llama-server -m gpt-oss-20b-mxfp4.gguf --port 8080 -c 8192

y apuntar ``LLAMA_SERVER_HOST=http://localhost:8080`` en la configuracion.

La logica de prompting (system prompt con contexto/glosario, formato numerado,
parseo de la respuesta) es identica a ``OllamaTranslator`` y vive en
``prompting.py`` — solo cambia el transporte HTTP.
"""

from __future__ import annotations

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from video_translator.domain.exceptions import TranslationError
from video_translator.domain.models import TranscriptSegment, TranslationContext
from video_translator.infrastructure.translation.prompting import (
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


class LlamaServerTranslator:
    def __init__(
        self,
        host: str = "http://localhost:8080",
        model: str = "gpt-oss-20b-mxfp4",
        temperature: float = 0.2,
        timeout_seconds: float = 180.0,
        max_tokens: int = 4096,
        api_key: str | None = None,
    ) -> None:
        self._host = host.rstrip("/")
        # llama-server solo tiene un modelo cargado; el campo "model" del payload
        # normalmente se ignora, pero se envia por compatibilidad con el schema
        # de OpenAI y para que quede claro en logs que modelo se esta usando.
        self._model = model
        self._temperature = temperature
        self._timeout = timeout_seconds
        self._max_tokens = max_tokens
        self._api_key = api_key

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
            "temperature": self._temperature,
            "max_tokens": self._max_tokens,
            "stream": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                response = client.post(
                    f"{self._host}/v1/chat/completions", json=payload, headers=headers
                )
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise TranslationError(
                f"Error de comunicacion con llama-server en {self._host}: {exc}. "
                "Verifica que el servidor este activo, p.ej.: "
                f"'llama-server -m {self._model}.gguf --port 8080'."
            ) from exc

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise TranslationError(
                f"Respuesta inesperada de llama-server (formato OpenAI no reconocido): {data}"
            ) from exc

        if not content or not content.strip():
            raise TranslationError("llama-server devolvio una respuesta vacia.")
        return content
