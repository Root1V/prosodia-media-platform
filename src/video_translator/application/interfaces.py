"""Puertos (interfaces) de la capa de aplicacion.

Siguiendo el principio de inversion de dependencias (Arquitectura Hexagonal / Clean
Architecture), la capa de aplicacion depende solo de estos Protocols, nunca de
implementaciones concretas (faster-whisper, ffmpeg, ollama, etc.). Esto permite:
  - Sustituir cualquier motor de IA sin tocar la logica de negocio.
  - Testear el caso de uso con dobles de prueba (mocks/fakes) triviales.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from video_translator.domain.models import (
    DiarizationSegment,
    TranscriptSegment,
    TranslatedSegment,
    TranslationContext,
)

if TYPE_CHECKING:
    from video_translator.application.synthesis_job import SynthesisJob


class MediaProcessor(Protocol):
    """Operaciones sobre el contenedor de video/audio (implementado con ffmpeg)."""

    def get_duration_seconds(self, media_path: Path) -> float: ...

    def extract_audio(self, video_path: Path, output_wav: Path) -> Path:
        """Extrae la pista de audio a WAV mono PCM, listo para el modelo de STT."""
        ...

    def extract_audio_clip(self, audio_path: Path, start: float, end: float, output_path: Path) -> Path:
        """Recorta un fragmento del audio (usado para armar clips de referencia por hablante)."""
        ...

    def burn_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        """Incrusta (quema) subtitulos en el video, no seleccionables/desactivables."""
        ...

    def render_ass_captions(
        self, video_path: Path, ass_path: Path, output_path: Path, fonts_dir: Path | None = None
    ) -> Path:
        """Incrusta captions ya formateados como .ass (con su propio header
        de resolucion y estilo, ver GenerateMicroVideoUseCase) via el filtro
        `ass` de ffmpeg -- a diferencia de `burn_subtitles` (pensado para un
        .srt "plano"), aca el tamano de fuente y la posicion quedan
        explicitos en el propio archivo, sin depender del reescalado
        implicito que libass aplica a un .srt sin resolucion declarada
        (asume 384x288 y lo escala al tamano real del video, lo que en un
        vertical de 1080x1920 arma un font varias veces mas grande de lo
        pedido). `fonts_dir` (ver RM-33) agrega una carpeta de busqueda de
        fuentes SIN necesitar que esten instaladas en el sistema -- probado
        a mano que esto funciona incluso con la copia del sistema ausente."""
        ...

    def overlay_emojis(
        self,
        video_path: Path,
        placements: list[tuple[Path, float, float, float, bool]],
        output_path: Path,
        width: int,
        duration_seconds: float,
    ) -> Path:
        """Compone imagenes PNG con transparencia sobre el video via el
        filtro `overlay` de ffmpeg (ver RM-32) -- el pipeline ASS/libass de
        texto no puede renderizar emoji en este sistema (probado a mano:
        ni con la fuente por defecto ni pidiendo explicitamente una fuente
        de emoji instalada aparece nada, ver docs/roadmap.md). Cada
        `placements` es `(asset_path, x, y, size, fade)`: `x`/`y` fracciones
        0-1 del CENTRO del emoji, `size` fraccion del ancho del video (el
        emoji es cuadrado), `fade` = aparece/desaparece gradual a lo largo
        de `duration_seconds`. `placements` vacio = copia el video tal
        cual (no-op), sin gastar un paso de ffmpeg de mas."""
        ...

    def attach_soft_subtitles(
        self, video_path: Path, srt_path: Path, output_path: Path, lang_code: str = "spa"
    ) -> Path:
        """Adjunta subtitulos como pista independiente y seleccionable."""
        ...

    def replace_audio_track(
        self,
        video_path: Path,
        new_audio_path: Path,
        output_path: Path,
        keep_original_as_secondary: bool = True,
    ) -> Path:
        """Reemplaza (o agrega como segunda pista) el audio del video con el doblaje."""
        ...

    def render_image_video(
        self,
        image_path: Path,
        audio_path: Path | None,
        output_path: Path,
        duration_seconds: float,
        width: int = 1080,
        height: int = 1920,
        offset_x: float = 0.5,
        offset_y: float = 0.5,
        zoom: float = 1.0,
        filter_preset: str = "none",
    ) -> Path:
        """Renderiza un video vertical a partir de una imagen estatica (efecto
        Ken Burns: zoom lento y continuo) con `audio_path` como pista de
        audio, con una duracion igual a `duration_seconds`. `audio_path=None`
        renderiza el clip MUDO (ver RM-29: con varias imagenes, cada una se
        renderiza muda y se concatenan, el audio se mezcla despues sobre el
        video ya concatenado). `offset_x`/`offset_y`/`zoom` (ver RM-30,
        `domain.models.MicroVideoImage`) fijan el encuadre base ANTES del
        Ken Burns automatico -- defaults (0.5, 0.5, 1.0) reproducen el
        comportamiento previo a RM-30 (recorte centrado, sin zoom manual).
        `filter_preset` (ver RM-31) aplica un estilo de color preestablecido
        ("none", "sepia", "bw", "cool", "warm", "dramatic") -- "none" o un
        valor no reconocido no aplican ningun filtro."""
        ...

    def render_clip_video(
        self,
        video_path: Path,
        output_path: Path,
        duration_seconds: float,
        start_seconds: float = 0.0,
        width: int = 1080,
        height: int = 1920,
        offset_x: float = 0.5,
        offset_y: float = 0.5,
        zoom: float = 1.0,
        filter_preset: str = "none",
    ) -> Path:
        """Normaliza un clip de video existente (ver RM-36) al MISMO formato de
        salida que produce `render_image_video`, para que `concatenate_videos`
        pueda seguir haciendo stream copy sin recodificar: libx264, yuv420p,
        `width`x`height`, 30fps, SAR 1:1, sin audio. `start_seconds` +
        `duration_seconds` recortan el rango elegido por el usuario en el
        editor (mismo criterio que `extract_music_range` para la musica de
        fondo). `offset_x`/`offset_y`/`zoom` (RM-30) y `filter_preset` (RM-31)
        se aplican igual que en una imagen -- son filtros por frame,
        funcionan identico sobre un stream real.

        A diferencia de `render_image_video`, NO usa `-loop 1`, `-tune
        stillimage` ni `zoompan`: el clip ya trae sus propios frames.
        `zoompan` con `d=N` trata cada frame de ENTRADA como fuente de N
        frames de salida -- sobre video real duplica/congela frames en vez
        de hacer un Ken Burns. El clip ya se mueve solo, no necesita el
        efecto.

        `fps=30` y `setsar=1` son obligatorios, no cosmeticos: el demuxer
        concat con `-c copy` exige que todos los segmentos compartan frame
        rate y sample aspect ratio, y un clip de camara puede venir a
        24/25/60fps y/o con pixeles no cuadrados. Las imagenes ya salen a
        30fps y SAR 1:1. Siempre MUDO (`-an`): el audio final se mezcla
        despues sobre el video ya concatenado (ver GenerateMicroVideoUseCase)."""
        ...

    def concatenate_videos(self, video_paths: list[Path], output_path: Path) -> Path:
        """Concatena videos con el MISMO codec (p.ej. varios clips mudos de
        `render_image_video`, ver RM-29) via el demuxer concat de ffmpeg --
        stream copy, sin recodificar."""
        ...

    def fit_audio_to_duration(self, audio_path: Path, target_seconds: float) -> bool:
        """Ajusta (acelera, sin techo de compresion) el audio EN EL LUGAR
        para que quepa en `target_seconds` -- se prioriza preservar todo el
        contenido hablado sobre que no suene acelerado. Ver
        `infrastructure.synthesis.audio_mixing.fit_to_duration`, la misma
        logica que ya usa el doblaje para encajar cada segmento en su hueco
        de tiempo. Devuelve False si fallo (el archivo original queda
        intacto)."""
        ...

    def mix_background_music(
        self,
        narration_path: Path,
        music_path: Path,
        output_path: Path,
        duration_seconds: float,
        music_volume: float = 0.12,
    ) -> Path:
        """Mezcla `music_path` (en loop si hace falta) debajo de
        `narration_path`, en volumen bajo (`music_volume`, lineal, no dB)
        para que nunca tape la voz, recortado a `duration_seconds`."""
        ...

    def clean_music_track(self, input_path: Path, output_wav: Path) -> Path:
        """Prepara un archivo de musica recien subido para el catalogo (ver
        RM-26): detecta y recorta el silencio inicial, y convierte a WAV.
        Se corre una sola vez al agregar la pista, no en cada uso."""
        ...

    def extract_music_range(self, track_path: Path, start: float, end: float, output_path: Path) -> Path:
        """Recorta [start, end] de una pista de musica para usar solo ese
        fragmento como fuente del loop de fondo (ver RM-28). A diferencia de
        `extract_audio_clip` (pensado para voz/STT, fuerza mono 16kHz), esto
        preserva calidad de musica: 44.1kHz estereo, igual que
        `clean_music_track`."""
        ...

    def apply_volume(self, audio_path: Path, volume: float) -> None:
        """Ajusta el volumen de `audio_path` EN EL LUGAR (in-place), lineal
        (no dB, 1.0 = sin cambios) -- mismo patron in-place que
        `fit_audio_to_duration`. No-op si `volume == 1.0` (evita un pase de
        ffmpeg innecesario)."""
        ...


class Transcriber(Protocol):
    """Motor de Speech-to-Text (implementado con faster-whisper)."""

    def transcribe(
        self, audio_path: Path, language_hint: str | None = None
    ) -> Iterable[TranscriptSegment]:
        """Transcribe el audio devolviendo segmentos con timestamps."""
        ...


class Translator(Protocol):
    """Motor de traduccion asistido por LLM, sensible a contexto."""

    def translate_batch(
        self,
        segments: list[TranscriptSegment],
        context: TranslationContext,
        rolling_history: list[str],
    ) -> list[str]:
        """Traduce un lote de segmentos manteniendo coherencia con el historial reciente.

        Debe devolver exactamente ``len(segments)`` traducciones, en el mismo orden.
        """
        ...


class Summarizer(Protocol):
    """Resume un texto largo en sus puntos mas importantes, asistido por LLM."""

    def summarize(self, text: str) -> str:
        """Devuelve un resumen del texto, en el mismo idioma que el original."""
        ...


class ScriptWriter(Protocol):
    """Convierte una idea suelta en un guion narrable, asistido por LLM (RM-42).

    Puerto aparte de ``Summarizer`` por el mismo motivo por el que aquel se
    separo de ``Translator``: son tareas distintas con invariantes distintas.
    Resumir CONDENSA un texto que ya existe; esto GENERA uno que no existia, a
    partir de una idea de una linea, y el resultado tiene que caber en una
    duracion hablada concreta.
    """

    def write_script(self, idea: str, objective: str, target_seconds: float | None) -> str:
        """Devuelve un guion listo para narrar, en el mismo idioma que la idea.

        ``objective`` orienta el tono y la estructura (ver RM-42);
        ``target_seconds`` es la duracion hablada aproximada que debe ocupar, o
        None si no hay tope.
        """
        ...


class SpeechSynthesizer(Protocol):
    """Motor de Text-to-Speech para generar el doblaje (implementado con Coqui TTS)."""

    def synthesize_segment(
        self,
        text: str,
        output_path: Path,
        target_duration_seconds: float,
        speaker_reference_wav: Path | None = None,
        language: str = "es",
    ) -> Path:
        """Sintetiza voz para un segmento, ajustando el ritmo para encajar en el timing."""
        ...

    def concatenate_segments(
        self,
        segment_audio_paths: list[tuple[float, Path, float]],
        total_duration: float,
        output_path: Path,
    ) -> Path:
        """Compone la pista de audio final ubicando cada segmento en su timestamp.

        Cada tupla es ``(start_seconds, path, max_duration_seconds)``: la
        implementacion debe recortar cada clip a ``max_duration_seconds`` (el
        hueco real hasta el siguiente segmento) antes de mezclar, para
        garantizar que dos voces nunca se superponen en la pista final.
        """
        ...


class SubtitleWriter(Protocol):
    """Escritor de subtitulos (formato SRT)."""

    def write(self, segments: list[TranslatedSegment], output_path: Path, use_translation: bool) -> Path: ...


class BatchSpeechSynthesizer(Protocol):
    """Capacidad OPCIONAL de un SpeechSynthesizer: procesar muchas tareas de
    sintesis de una sola vez, potencialmente en paralelo.

    No todo SpeechSynthesizer la implementa (los mas simples solo saben
    generar un clip a la vez); el caso de uso la detecta con ``hasattr`` y,
    si esta disponible, construye TODAS las tareas por adelantado y las
    despacha juntas (p.ej. ``ParallelTTSPool`` las reparte entre varios
    procesos). Si no esta disponible, se cae al bucle secuencial de siempre
    llamando a ``synthesize_segment`` una por una.
    """

    def synthesize_batch(self, jobs: list[SynthesisJob]) -> None:
        """Ejecuta todas las tareas (en el orden que sea mas eficiente); no
        devuelve nada porque cada tarea ya sabe su propio ``output_path``."""
        ...


class SpeakerDiarizer(Protocol):
    """Deteccion de hablantes: quien habla y en que intervalos (implementado con pyannote.audio)."""

    def diarize(
        self, audio_path: Path, min_speakers: int | None = None, max_speakers: int | None = None
    ) -> list[DiarizationSegment]: ...


class GenderClassifier(Protocol):
    """Estima el genero de un hablante a partir de un clip de audio de referencia."""

    def classify(self, wav_path: Path) -> str:
        """Devuelve 'male', 'female' o 'unknown'."""
        ...
