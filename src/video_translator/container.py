"""Contenedor de inyeccion de dependencias (composition root).

Este es el UNICO lugar del proyecto donde se conocen simultaneamente la capa
de aplicacion (casos de uso) y las implementaciones concretas de infraestructura.
Facilita cambiar de motor (p.ej. otro LLM, otro backend de TTS) editando solo
este archivo.
"""

from __future__ import annotations

import os
import platform
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import cast

from video_translator.application.interfaces import (
    MediaProcessor,
    ScriptWriter,
    SpeechSynthesizer,
    Summarizer,
    Transcriber,
    Translator,
)
from video_translator.application.use_cases.generate_micro_video import GenerateMicroVideoUseCase
from video_translator.application.use_cases.synthesize_text import SynthesizeTextUseCase
from video_translator.application.use_cases.transcribe_media import TranscribeMediaUseCase
from video_translator.application.use_cases.translate_video import TranslateVideoUseCase
from video_translator.application.use_cases.write_micro_video_script import (
    WriteMicroVideoScriptUseCase,
)
from video_translator.config import Settings
from video_translator.domain.exceptions import ConfigurationError
from video_translator.infrastructure.media.ffmpeg_processor import FFmpegMediaProcessor
from video_translator.infrastructure.subtitles.srt_writer import SrtSubtitleWriter
from video_translator.infrastructure.transcription.faster_whisper_transcriber import (
    FasterWhisperTranscriber,
)
from video_translator.infrastructure.translation.llama_server_translator import (
    LlamaServerTranslator,
)
from video_translator.infrastructure.translation.ollama_translator import OllamaTranslator
from video_translator.utils.logging_config import get_logger

logger = get_logger(__name__)

# Tope de workers paralelos auto-detectados: cada uno carga su propia copia
# del modelo de TTS en memoria (unos 4-6GB con IndexTTS-2.5), asi que en
# maquinas con poca RAM crear demasiados puede ser contraproducente. VALIDADO
# en un M4 Max (16 nucleos, 128GB RAM) con el batching real de GPT (ver
# IndexTTS2Synthesizer.synthesize_batch): en clips cortos (~14 jobs) mas
# workers seguia ganando hasta usar uno por job, pero en videos largos (44 a
# 269 jobs, de 10 a 60 min) el optimo real fue 8 workers -- 4 midio 17.7s/job,
# 8 midio 14.3-17.3s/job (el mejor de los tres), 12 midio 18.3s/job (peor que
# 8). Con menos hilos por worker de los que hay a partir de ~10 workers en 16
# nucleos, la contencion empieza a pesar mas que el paralelismo ganado. En
# maquinas con RAM limitada, baja esto explicitamente con TTS_PARALLEL_WORKERS.
_AUTO_MAX_TTS_WORKERS = 8

# Nucleos reservados para el subprocess de diarizacion cuando corre EN
# PARALELO con la transcripcion (ver TranslateVideoUseCase._transcribe_and_diarize):
# ambos son CPU-bound, y CTranslate2 con cpu_threads="auto" reclama la maquina
# entera por defecto, dejando a pyannote compitiendo por los mismos nucleos
# fisicos. Medido en una corrida real: la diarizacion (232s) tardo mas que la
# transcripcion (202s) en un clip de 3 min con 1 solo hablante, muy por encima
# de lo esperable sin contencion.
_CORES_RESERVED_FOR_DIARIZATION = 4


def _build_translator(settings: Settings) -> Translator:
    """Selecciona el adaptador de traduccion segun TRANSLATION_BACKEND.

    Ambos adaptadores implementan el mismo Protocol ``Translator``, por lo que
    el resto del pipeline (TranslateVideoUseCase) no necesita saber cual se usa.
    """
    backend = settings.translation_backend.lower()
    if backend == "ollama":
        return OllamaTranslator(
            host=settings.ollama_host,
            model=settings.ollama_model,
            temperature=settings.ollama_temperature,
            timeout_seconds=settings.ollama_timeout_seconds,
        )
    if backend == "llama_server":
        return LlamaServerTranslator(
            host=settings.llama_server_host,
            model=settings.llama_server_model,
            temperature=settings.ollama_temperature,
            timeout_seconds=settings.ollama_timeout_seconds,
            max_tokens=settings.llama_server_max_tokens,
            api_key=settings.llama_server_api_key,
        )
    raise ConfigurationError(
        f"TRANSLATION_BACKEND='{settings.translation_backend}' no reconocido. "
        "Usa 'ollama' o 'llama_server'."
    )


def build_translate_video_use_case(
    settings: Settings,
    enable_dubbing: bool = False,
    enable_diarization: bool = False,
    resume: bool = False,
) -> TranslateVideoUseCase:
    media_processor = FFmpegMediaProcessor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        audio_sample_rate=settings.audio_sample_rate,
    )
    transcriber = _build_transcriber(settings, enable_diarization)
    translator = _build_translator(settings)
    subtitle_writer = SrtSubtitleWriter()

    speech_synthesizer = None
    tts_notes: dict = {}
    if enable_dubbing:
        speech_synthesizer, tts_notes = _build_synthesizer(settings)

    speaker_diarizer = None
    gender_classifier = None
    if enable_diarization:
        from video_translator.infrastructure.diarization.subprocess_diarizer import (
            SubprocessDiarizer,
        )

        speaker_diarizer = SubprocessDiarizer(
            python_bin=settings.diarization_python_bin,
            worker_script=settings.diarization_worker_script,
            model_name=settings.diarization_model,
            hf_token=settings.hf_token,
            device=settings.diarization_device,
            dyld_library_path=settings.diarization_dyld_library_path,
        )
        if settings.gender_detection_enabled:
            from video_translator.infrastructure.diarization.subprocess_gender_classifier import (
                SubprocessGenderClassifier,
            )

            gender_classifier = SubprocessGenderClassifier(
                python_bin=settings.diarization_python_bin,
                worker_script=settings.diarization_worker_script,
            )

    # Configuracion EFECTIVA (modelos/devices/workers con los que realmente se
    # ejecutara el pipeline): se persiste en pipeline_timings.json para que dos
    # corridas sean comparables entre si.
    effective_config: dict = {
        "whisper_backend": settings.whisper_backend,
        "whisper_model": (
            settings.mlx_whisper_model
            if settings.whisper_backend.lower() == "mlx"
            else settings.whisper_model_size
        ),
        "whisper_device": settings.whisper_device if settings.whisper_backend.lower() != "mlx" else "mps",
        "whisper_compute_type": (
            settings.whisper_compute_type if settings.whisper_backend.lower() != "mlx" else None
        ),
        "whisper_cpu_threads": (
            _resolve_whisper_cpu_threads(settings, enable_diarization)
            if settings.whisper_backend.lower() != "mlx"
            else None
        ),
        "translation_backend": settings.translation_backend,
        "llm_model": (
            settings.llama_server_model
            if settings.translation_backend == "llama_server"
            else settings.ollama_model
        ),
        "diarize_enabled": enable_diarization,
        "diarization_model": settings.diarization_model if enable_diarization else None,
        "gender_detection": settings.gender_detection_enabled if enable_diarization else None,
    }
    if enable_dubbing:
        effective_config.update(
            {
                "tts_backend": settings.tts_backend,
                "tts_workers": tts_notes.get("tts_workers"),
                "tts_device_forced_cpu": tts_notes.get("tts_device_forced_cpu", False),
            }
        )

    return TranslateVideoUseCase(
        media_processor=media_processor,
        transcriber=transcriber,
        translator=translator,
        subtitle_writer=subtitle_writer,
        speech_synthesizer=speech_synthesizer,
        speaker_diarizer=speaker_diarizer,
        gender_classifier=gender_classifier,
        translation_batch_max_chars=settings.translation_batch_max_chars,
        context_window_segments=settings.translation_context_window_segments,
        group_segments_for_synthesis=settings.tts_group_segments,
        group_max_gap_seconds=settings.tts_group_max_gap_seconds,
        group_max_chars=settings.tts_group_max_chars,
        resume=resume,
        effective_config=effective_config,
    )


def build_transcribe_media_use_case(
    settings: Settings, include_summary: bool = False
) -> TranscribeMediaUseCase:
    """Construye el caso de uso de transcripcion standalone (sin traduccion ni
    doblaje) -- solo necesita `MediaProcessor` + `Transcriber`, a diferencia de
    `build_translate_video_use_case` que siempre arma tambien un `Translator`
    y un `SubtitleWriter` para el pipeline completo.

    `include_summary` arma ademas un `Summarizer` (solo si hace falta, para no
    exigirle configuracion de LLM a un caso de uso que por defecto no la
    necesita). `OllamaTranslator`/`LlamaServerTranslator` ya implementan
    `summarize()` (ver infrastructure/translation/) ademas de
    `translate_batch()`, asi que el mismo backend de `_build_translator` sirve
    tal cual -- se castea a `Summarizer` en vez de duplicar el switch
    ollama/llama_server, para que ambas construcciones no puedan divergir."""
    media_processor = FFmpegMediaProcessor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        audio_sample_rate=settings.audio_sample_rate,
    )
    transcriber = _build_transcriber(settings, enable_diarization=False)
    subtitle_writer = SrtSubtitleWriter()
    summarizer = cast(Summarizer, _build_translator(settings)) if include_summary else None

    effective_config: dict = {
        "whisper_backend": settings.whisper_backend,
        "whisper_model": (
            settings.mlx_whisper_model
            if settings.whisper_backend.lower() == "mlx"
            else settings.whisper_model_size
        ),
        "whisper_device": settings.whisper_device if settings.whisper_backend.lower() != "mlx" else "mps",
    }

    return TranscribeMediaUseCase(
        media_processor=media_processor,
        transcriber=transcriber,
        subtitle_writer=subtitle_writer,
        summarizer=summarizer,
        effective_config=effective_config,
    )


# Voces de referencia publicas para el TTS standalone (ver
# `build_synthesize_text_use_case` y `web/services/project_mapper.py`) --
# ambos backends de TTS son de clonacion zero-shot pura, ninguno tiene una voz
# "de fabrica" propia, asi que hace falta un .wav real empaquetado con el
# proyecto para cada opcion seleccionable.
_DEFAULT_VOICES_DIR = Path(__file__).resolve().parent / "assets" / "default_voices"
PUBLIC_VOICE_MALE_WAV = _DEFAULT_VOICES_DIR / "locutor.wav"
PUBLIC_VOICE_FEMALE_WAV = _DEFAULT_VOICES_DIR / "locutora.wav"
DEFAULT_TTS_VOICE_WAV = PUBLIC_VOICE_FEMALE_WAV

# Set curado de PNGs de emoji bundleados (ver RM-32) -- el pipeline
# ASS/libass de texto no puede renderizar emoji en este sistema, asi que se
# componen como imagen. Usado tanto por `application/use_cases/
# generate_micro_video.py` (resolver emoji_id -> ruta real al generar el
# video) como por `web/routers/samples.py` (servirlos al editor).
EMOJI_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "emojis"

def build_music_track_media_processor(settings: Settings) -> MediaProcessor:
    """MediaProcessor para limpiar una pista de musica recien subida al
    catalogo (ver RM-26, `web/services/music_tracks.py`) -- misma
    implementacion que el resto, expuesta aparte porque este caller no
    necesita ningun otro caso de uso."""
    return FFmpegMediaProcessor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        audio_sample_rate=settings.audio_sample_rate,
    )


def build_synthesize_text_use_case(settings: Settings) -> SynthesizeTextUseCase:
    """Construye el caso de uso de TTS standalone (texto -> audio). A
    diferencia de `_build_synthesizer` (usado para doblaje, donde vale la pena
    paralelizar decenas/cientos de segmentos), aca siempre se fuerza un solo
    worker: una sintesis de texto suelto rara vez tiene tantos fragmentos como
    para justificar el costo de levantar varios procesos con su propia copia
    del modelo en memoria cada uno."""
    media_processor = FFmpegMediaProcessor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        audio_sample_rate=settings.audio_sample_rate,
    )
    notes: dict = {}
    speech_synthesizer = _synthesizer_factory(settings, num_workers=1, notes=notes)()

    effective_config: dict = {
        "tts_backend": settings.tts_backend,
        "tts_device_forced_cpu": notes.get("tts_device_forced_cpu", False),
    }

    return SynthesizeTextUseCase(
        speech_synthesizer=speech_synthesizer,
        media_processor=media_processor,
        default_speaker_reference_wav=DEFAULT_TTS_VOICE_WAV,
        effective_config=effective_config,
    )


def build_generate_micro_video_use_case(settings: Settings) -> GenerateMicroVideoUseCase:
    """Construye el caso de uso de micro-video (imagen + texto -> video
    vertical narrado con captions, ver RM-14). Mismo criterio de un solo
    worker de TTS que `build_synthesize_text_use_case` -- el texto de un
    micro-video social es corto, no amerita procesos paralelos."""
    media_processor = FFmpegMediaProcessor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        audio_sample_rate=settings.audio_sample_rate,
    )
    notes: dict = {}
    speech_synthesizer = _synthesizer_factory(settings, num_workers=1, notes=notes)()

    effective_config: dict = {
        "tts_backend": settings.tts_backend,
        "tts_device_forced_cpu": notes.get("tts_device_forced_cpu", False),
    }

    return GenerateMicroVideoUseCase(
        speech_synthesizer=speech_synthesizer,
        media_processor=media_processor,
        default_speaker_reference_wav=DEFAULT_TTS_VOICE_WAV,
        effective_config=effective_config,
    )


def _synthesizer_factory(
    settings: Settings, num_workers: int, notes: dict | None = None
) -> Callable[[], SpeechSynthesizer]:
    """Devuelve una funcion SIN ARGUMENTOS que construye una instancia nueva
    del motor de TTS configurado.

    Se usa tanto para construir directamente (modo secuencial, un solo
    proceso) como para pasarsela a ``ParallelTTSPool``, que la ejecuta una
    vez POR CADA proceso worker (cada worker termina con su propia copia del
    modelo cargada en memoria, no se comparte entre procesos). Debe ser
    "picklable" para poder cruzar el limite de proceso; ``functools.partial``
    sobre una clase con argumentos simples (str/bool) lo es.
    """
    backend = settings.tts_backend.lower()
    if backend == "index_tts2":
        from video_translator.infrastructure.synthesis.index_tts2_synthesizer import (
            IndexTTS2Synthesizer,
        )

        device = settings.index_tts2_device or None
        if device is None and num_workers > 1 and platform.system() == "Darwin":
            # SEGURIDAD: IndexTTS2 autodetecta MPS (Metal) si no se le dice
            # lo contrario. Varios PROCESOS tomando Metal a la vez de forma
            # concurrente es una combinacion conocida por ser inestable en
            # macOS — puede crashear el driver de GPU y reiniciar el sistema
            # por completo (no es un simple error de Python). Se fuerza CPU
            # automaticamente para los workers paralelos en Mac, salvo que
            # el usuario fije INDEX_TTS2_DEVICE explicitamente (bajo su
            # propio riesgo). Con un solo worker (num_workers<=1) no aplica:
            # MPS en un unico proceso es el uso soportado oficialmente.
            device = "cpu"
            if notes is not None:
                notes["tts_device_forced_cpu"] = True
            logger.warning(
                "container.forcing_cpu_for_parallel_tts_on_macos",
                num_workers=num_workers,
                reason=(
                    "Varios procesos usando Metal (MPS) a la vez pueden crashear el driver "
                    "de GPU en macOS y reiniciar el sistema. Se fuerza CPU para los workers "
                    "paralelos. Para usar GPU, corre con --tts-workers 1, o fija "
                    "INDEX_TTS2_DEVICE=mps explicitamente si aceptas el riesgo."
                ),
            )

        return partial(
            IndexTTS2Synthesizer,
            model_dir=settings.index_tts2_model_dir,
            cfg_path=settings.index_tts2_cfg_path,
            use_bf16=settings.index_tts2_use_bf16,
            use_torch_compile=settings.index_tts2_use_torch_compile,
            num_beams=settings.index_tts2_num_beams,
            gpt_batch_size=settings.index_tts2_gpt_batch_size,
            ffmpeg_binary=settings.ffmpeg_binary,
            device=device,
        )
    if backend == "coqui_xtts":
        from video_translator.infrastructure.synthesis.coqui_tts_synthesizer import (
            CoquiTTSSynthesizer,
        )

        return partial(
            CoquiTTSSynthesizer,
            model_name=settings.tts_model_name,
            device=settings.tts_device,
            ffmpeg_binary=settings.ffmpeg_binary,
        )
    raise ConfigurationError(
        f"TTS_BACKEND='{settings.tts_backend}' no reconocido. Usa 'index_tts2' o 'coqui_xtts'."
    )


def _build_transcriber(settings: Settings, enable_diarization: bool) -> Transcriber:
    """Selecciona el adaptador de transcripcion segun WHISPER_BACKEND.

    Ambos adaptadores implementan el mismo Protocol ``Transcriber``. En Mac,
    "faster_whisper" (CTranslate2) esta limitado a CPU -- no soporta Metal;
    "mlx" usa la GPU via el framework MLX de Apple y suele ser bastante mas
    rapido en Apple Silicon.
    """
    backend = settings.whisper_backend.lower()
    if backend == "mlx":
        from video_translator.infrastructure.transcription.mlx_whisper_transcriber import (
            MlxWhisperTranscriber,
        )

        return MlxWhisperTranscriber(model_repo=settings.mlx_whisper_model)
    if backend == "faster_whisper":
        return FasterWhisperTranscriber(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
            beam_size=settings.whisper_beam_size,
            vad_filter=settings.whisper_vad_filter,
            cpu_threads=_resolve_whisper_cpu_threads(settings, enable_diarization),
            num_workers=settings.whisper_num_workers,
        )
    raise ConfigurationError(
        f"WHISPER_BACKEND='{settings.whisper_backend}' no reconocido. Usa 'faster_whisper' o 'mlx'."
    )


def _resolve_whisper_cpu_threads(settings: Settings, enable_diarization: bool) -> int:
    """Resuelve cuantos hilos de CPU usara CTranslate2 para la transcripcion.

    Si el usuario fijo WHISPER_CPU_THREADS explicitamente, se respeta tal
    cual (0 = "auto" para CTranslate2, es decir, ``os.cpu_count()`` dentro de
    ``FasterWhisperTranscriber``). Solo cuando esta en auto Y la diarizacion
    va a correr EN PARALELO con la transcripcion (ver
    ``TranslateVideoUseCase._transcribe_and_diarize``) se reserva un margen de
    nucleos para el subprocess de pyannote, en vez de dejar que whisper
    reclame la maquina entera y ambas etapas se frenen mutuamente.
    """
    if settings.whisper_cpu_threads > 0 or not enable_diarization:
        return settings.whisper_cpu_threads
    cpu_count = os.cpu_count() or 8
    return max(1, cpu_count - _CORES_RESERVED_FOR_DIARIZATION)


def _resolve_tts_worker_count(configured: int) -> int:
    """0/negativo = auto-detectar: hasta un worker por nucleo, con un tope
    (cada worker carga su propia copia del modelo en memoria)."""
    if configured > 0:
        return configured
    cpu_count = os.cpu_count() or 4
    return max(1, min(_AUTO_MAX_TTS_WORKERS, cpu_count))


def _build_synthesizer(settings: Settings) -> tuple[SpeechSynthesizer, dict]:
    """Construye el motor de TTS para doblaje segun TTS_BACKEND, envuelto en
    un pool de procesos paralelos si TTS_PARALLEL_WORKERS lo amerita.

    Devuelve ``(synthesizer, notes)``: ``notes`` es un dict con datos de la
    decision de construccion (p.ej. ``tts_workers`` resuelto, si se forzo CPU
    en macOS) que acaba en la configuracion efectiva del reporte de timings.

    Import perezoso en cada rama: evita requerir las dependencias pesadas
    (torch, TTS, indextts) cuando el doblaje no se usa.
    """
    num_workers = _resolve_tts_worker_count(settings.tts_parallel_workers)
    notes: dict = {"tts_workers": num_workers}
    factory = _synthesizer_factory(settings, num_workers, notes)

    if num_workers <= 1:
        return factory(), notes

    from video_translator.infrastructure.synthesis.parallel_tts_pool import ParallelTTSPool

    pool = ParallelTTSPool(
        synthesizer_factory=factory, num_workers=num_workers, ffmpeg_binary=settings.ffmpeg_binary
    )
    return pool, notes


def build_write_micro_video_script_use_case(settings: Settings) -> WriteMicroVideoScriptUseCase:
    """Construye el caso de uso que convierte una idea en guion (ver RM-42).

    Reusa el mismo backend de LLM que la traduccion, estrechado al puerto
    ScriptWriter -- mismo patron que el Summarizer de RM-18
    (`build_transcribe_media_use_case`): los dos backends ya saben hablar con el
    modelo, y lo unico que cambia es el prompt.
    """
    return WriteMicroVideoScriptUseCase(
        script_writer=cast(ScriptWriter, _build_translator(settings)),
    )
