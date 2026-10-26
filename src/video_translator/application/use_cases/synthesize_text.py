"""Caso de uso: SynthesizeTextUseCase.

Sintesis de voz standalone: texto -> audio, sin video ni transcripcion de por
medio. Reusa `SpeechSynthesizer` y `MediaProcessor`, los mismos ports que
`TranslateVideoUseCase` usa para el doblaje -- `synthesize_segment()` ya es
"texto en, audio afuera" independiente de cualquier video.

Textos largos se dividen en fragmentos (por oracion) para no forzar al modelo
a generar un solo audio arbitrariamente largo en una sola pasada; cada
fragmento se sintetiza con `target_duration_seconds=0.0` (ritmo natural, sin
el ajuste de velocidad que usa el doblaje para encajar en el timing del video
original -- ver `fit_to_duration` / `_estimate_duration_factor`), y luego se
concatenan en orden con `concatenate_segments`, dandole a cada fragmento
exactamente su propia duracion real como "hueco" (sin solapamiento ni recorte).
"""

from __future__ import annotations

from pathlib import Path

from video_translator.application.interfaces import MediaProcessor, SpeechSynthesizer
from video_translator.application.use_cases.text_chunking import split_into_chunks
from video_translator.domain.exceptions import VideoTranslatorError
from video_translator.domain.models import SynthesizeTextRequest, SynthesizeTextResult
from video_translator.utils.logging_config import get_logger
from video_translator.utils.timing import PipelineTimings

logger = get_logger(__name__)

DEFAULT_MAX_CHUNK_CHARS = 500


class SynthesizeTextUseCase:
    def __init__(
        self,
        speech_synthesizer: SpeechSynthesizer,
        media_processor: MediaProcessor,
        default_speaker_reference_wav: Path,
        max_chunk_chars: int = DEFAULT_MAX_CHUNK_CHARS,
        effective_config: dict | None = None,
    ) -> None:
        self._synthesizer = speech_synthesizer
        self._media = media_processor
        self._default_speaker_wav = default_speaker_reference_wav
        self._max_chunk_chars = max_chunk_chars
        self._effective_config = dict(effective_config) if effective_config else {}

    def execute(self, request: SynthesizeTextRequest) -> SynthesizeTextResult:
        self._validate_request(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        workdir = request.output_dir / "_work"
        chunk_dir = workdir / "tts_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        report_path = request.output_dir / "pipeline_timings.json"
        timings = PipelineTimings(report_path=report_path)
        if self._effective_config:
            timings.set_effective_config(**self._effective_config)
        log = logger.bind(run_id=timings.run_id)
        log.info("synthesize_text.start", chars=len(request.text))

        speaker_wav = request.speaker_reference_wav or self._default_speaker_wav

        chunks = split_into_chunks(request.text, self._max_chunk_chars)
        segments: list[tuple[float, Path, float]] = []
        cursor = 0.0
        with timings.stage("text_to_speech", num_chunks=len(chunks)):
            # El progreso se reporta ANTES de empezar: con un solo fragmento
            # largo, esperar a terminarlo para decir "0 de 1" significaria
            # callar justo durante todo el rato que dura.
            timings.report_progress(0, len(chunks))
            for i, chunk_text in enumerate(chunks):
                chunk_path = chunk_dir / f"chunk_{i:03d}.wav"
                self._synthesizer.synthesize_segment(
                    text=chunk_text,
                    output_path=chunk_path,
                    target_duration_seconds=0.0,
                    speaker_reference_wav=speaker_wav,
                    language=request.language,
                )
                chunk_duration = self._media.get_duration_seconds(chunk_path)
                segments.append((cursor, chunk_path, chunk_duration))
                cursor += chunk_duration
                # Esta etapa es el 89% del tiempo de una corrida (ver RM-61):
                # callar aqui es callar casi todo el rato que el usuario
                # espera.
                timings.report_progress(i + 1, len(chunks))
                log.info("synthesize_text.chunk_done", chunk=i + 1, num_chunks=len(chunks))
        log.info("synthesize_text.chunks_done", num_chunks=len(chunks))

        audio_path = request.output_dir / "speech.wav"
        with timings.stage("audio_concatenation"):
            self._synthesizer.concatenate_segments(segments, cursor, audio_path)

        timings.set_outputs(audio_wav_bytes=audio_path.stat().st_size)
        timings.write_report(report_path, final=True)
        log.info(
            "synthesize_text.finished",
            total_seconds=round(timings.total_seconds, 1),
            timings_report=str(report_path),
        )

        return SynthesizeTextResult(
            audio_path=audio_path,
            duration_seconds=cursor,
            timings=timings.as_dict(),
        )

    @staticmethod
    def _validate_request(request: SynthesizeTextRequest) -> None:
        if not request.text.strip():
            raise VideoTranslatorError("El texto a sintetizar esta vacio.")
