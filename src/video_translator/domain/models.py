"""Modelos de dominio: entidades y value objects puros, sin dependencias de infraestructura."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class OutputMode(str, Enum):
    """Modo de salida del video traducido."""

    SUBTITLES_ONLY = "subtitles_only"       # Solo genera .srt (EN y ES)
    BURN_SUBTITLES = "burn_subtitles"       # Incrusta subtitulos ES en el video
    SOFT_SUBTITLES = "soft_subtitles"       # Adjunta subtitulos ES como pista seleccionable
    DUBBED = "dubbed"                       # Reemplaza el audio por voz sintetizada en ES


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """Un segmento de audio transcrito en el idioma original."""

    id: int
    start: float          # segundos
    end: float             # segundos
    text: str
    language: str = "en"
    speaker_id: str | None = None  # p.ej. "SPEAKER_00", asignado por diarizacion

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class TranslatedSegment:
    """Un segmento ya traducido, conserva el timing original para sincronizar subtitulos/audio."""

    id: int
    start: float
    end: float
    source_text: str
    translated_text: str
    speaker_id: str | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(frozen=True, slots=True)
class DiarizationSegment:
    """Un turno de habla detectado por el pipeline de diarizacion (quien habla y cuando)."""

    start: float
    end: float
    speaker_label: str

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


@dataclass(slots=True)
class SpeakerProfile:
    """Perfil de un hablante detectado: su etiqueta, genero estimado y clip de referencia
    (usado para clonar su timbre de voz en el doblaje)."""

    speaker_id: str
    gender: str | None = None  # "male" | "female" | "unknown"
    reference_wav: Path | None = None


@dataclass(slots=True)
class TranslationContext:
    """Contexto proporcionado por el usuario para guiar y mejorar la calidad de la traduccion.

    Este es el mecanismo central que permite mejorar la salida del LLM: un prompt en
    lenguaje natural describiendo dominio, tono, audiencia, y un glosario opcional de
    terminos que deben traducirse (o no) de forma consistente.
    """

    prompt: str = ""
    glossary: dict[str, str] = field(default_factory=dict)
    source_lang: str = "en"
    target_lang: str = "es"
    tone: str | None = None  # p.ej. "formal", "informal", "tecnico"
    speaker_genders: dict[str, str] = field(default_factory=dict)  # speaker_id -> "male"/"female"/"unknown"

    def is_empty(self) -> bool:
        return not self.prompt and not self.glossary


@dataclass(slots=True)
class TranslateVideoRequest:
    """Solicitud de traduccion de un video, entrada principal del caso de uso."""

    input_video: Path
    output_dir: Path
    context: TranslationContext
    output_mode: OutputMode = OutputMode.SOFT_SUBTITLES
    keep_original_audio_track: bool = True
    speaker_reference_wav: Path | None = None  # voz unica de referencia (fallback sin diarizacion)
    source_lang_hint: str | None = "en"
    diarize: bool = False               # activa deteccion de multiples hablantes
    min_speakers: int | None = None
    max_speakers: int | None = None


@dataclass(slots=True)
class TranslateVideoResult:
    """Resultado del pipeline completo."""

    output_video: Path | None
    subtitles_source_path: Path
    subtitles_target_path: Path
    segments: list[TranslatedSegment]
    duration_seconds: float
    speakers: list[SpeakerProfile] = field(default_factory=list)
    timings: dict = field(default_factory=dict)


@dataclass(slots=True)
class TranscribeMediaRequest:
    """Solicitud de transcripcion standalone (sin traduccion ni doblaje):
    entrada principal de ``TranscribeMediaUseCase``."""

    input_media: Path
    output_dir: Path
    source_lang_hint: str | None = None
    include_summary: bool = False


@dataclass(slots=True)
class TranscribeMediaResult:
    """Resultado de una transcripcion standalone."""

    transcript_srt_path: Path
    transcript_text_path: Path
    segments: list[TranscriptSegment]
    duration_seconds: float
    timings: dict = field(default_factory=dict)
    summary_text: str | None = None


@dataclass(slots=True)
class SynthesizeTextRequest:
    """Solicitud de sintesis de voz standalone (texto -> audio), entrada
    principal de ``SynthesizeTextUseCase``."""

    text: str
    output_dir: Path
    language: str = "es"
    speaker_reference_wav: Path | None = None  # None = usa la voz por defecto


@dataclass(slots=True)
class SynthesizeTextResult:
    """Resultado de una sintesis de voz standalone."""

    audio_path: Path
    duration_seconds: float
    timings: dict = field(default_factory=dict)


@dataclass(slots=True)
class TextOverlay:
    """Un texto libre superpuesto al micro-video (ver RM-28), posicionado a
    mano por el usuario en un editor drag & drop. `x`/`y` son fracciones
    0-1 del ancho/alto del video -- el CENTRO del texto, no la esquina
    (coincide con "donde soltaste el texto al arrastrarlo")."""

    text: str
    x: float
    y: float
    bold: bool = False
    font_family: str = "Arial"
    font_size: int = 48
    color: str = "#FFFFFF"  # hex "#RRGGBB"
    fade: bool = False  # aparece/desaparece gradual en vez de un corte seco
    # Estilo visual adicional (ver RM-33) -- "flat" (default, comportamiento
    # previo), "hard_shadow", "thick_outline", "long_shadow", "hollow"
    # (solo contorno, sin relleno), "neon_glow", "colored_outline", o
    # "gradient" (degradado de color, ver accent_color). Sin validacion
    # estricta (mismo criterio que filter_preset): un valor no reconocido
    # cae a "flat".
    text_style: str = "flat"
    # Segundo color, su significado depende de text_style: color FINAL del
    # degradado ("gradient"), color del brillo ("neon_glow"), o color del
    # contorno ("colored_outline"). Ignorado en cualquier otro text_style.
    accent_color: str = "#FFFFFF"


@dataclass(slots=True)
class MicroVideoMediaItem:
    """Una imagen o clip de video del micro-video con el encuadre elegido
    por el usuario en el editor (ver RM-30). `offset_x`/`offset_y` son
    fracciones 0-1 de cuanto se desplaza la ventana de recorte (0 = borde
    superior/izquierdo visible, 1 = borde inferior/derecho visible);
    `zoom` >= 1.0 acerca la imagen/clip antes de recortarlo. Los defaults
    reproducen el comportamiento previo a RM-30 (recorte centrado, sin
    zoom manual adicional). `filter_preset` (ver RM-31) es un estilo de
    color preestablecido -- "none" (default), "sepia", "bw", "cool",
    "warm" o "dramatic"; sin validacion estricta (mismo criterio que
    `caption_highlight_style`), un valor no reconocido simplemente no
    aplica ningun filtro.

    `keep_ranges` (ver RM-40) solo tiene efecto cuando `path` es un clip de
    video (extension en SUPPORTED_VIDEO_EXTENSIONS): rango(s) [start, end)
    DENTRO del clip a conservar en la linea de tiempo, en orden cronologico
    y sin solaparse -- lo que queda AFUERA de estos rangos se descarta (p.ej.
    un tramo del medio que el usuario decidio cortar). `None` = el clip
    completo (un unico rango implicito [0, duracion_real)). `end=None` en
    el ULTIMO rango de la lista significa "hasta el final real del
    archivo". Se ignora en un item de imagen -- mismo criterio de
    tolerancia que `filter_preset`."""

    path: Path
    offset_x: float = 0.5
    offset_y: float = 0.5
    zoom: float = 1.0
    filter_preset: str = "none"
    keep_ranges: list[tuple[float, float | None]] | None = None


@dataclass(slots=True)
class EmojiOverlay:
    """Un emoji superpuesto al micro-video (ver RM-32), posicionado a mano
    por el usuario -- mismo criterio que TextOverlay (x/y son el CENTRO,
    fracciones 0-1 del ancho/alto del video). No es texto libre: `emoji_id`
    referencia uno de un set curado de imagenes bundleadas (ver
    assets/emojis/), porque este sistema no puede renderizar emoji via el
    pipeline ASS/libass que usa el texto -- se compone como imagen con el
    filtro `overlay` de ffmpeg en su lugar (ver MediaProcessor.overlay_emojis)."""

    emoji_id: str
    x: float
    y: float
    size: float = 0.15  # fraccion del ANCHO del video (el emoji es cuadrado)
    fade: bool = False  # aparece/desaparece gradual, mismo criterio que TextOverlay.fade


@dataclass(slots=True)
class GenerateMicroVideoRequest:
    """Solicitud de generacion de un micro-video (imagen(es) + texto -> video
    vertical narrado con captions), entrada principal de
    ``GenerateMicroVideoUseCase``."""

    # Al menos un item, imagen o clip de video (validado en
    # _validate_request). Si hay mas de uno (ver RM-29, RM-36), el video
    # los recorre en orden. Cada clip de video ocupa su propia duracion
    # real (la suma de sus keep_ranges si el usuario corto tramos, ver
    # RM-40) en la linea de tiempo; el tiempo restante se reparte en
    # partes iguales solo entre las imagenes, cada una con su propio
    # efecto Ken Burns. Si los clips
    # solos ya cubren o superan la duracion pedida, el video se extiende
    # (nunca se recorta un clip a la fuerza) -- ver GenerateMicroVideoUseCase.
    media_items: list[MicroVideoMediaItem]
    text: str
    output_dir: Path
    language: str = "es"
    # Para que se hace el video (ver RM-42). No cambia lo que el pipeline
    # SABE hacer -- cambia lo que la app propone antes de llegar aqui
    # (formato, duracion, estilo de captions, musica, tono del guion). Llega
    # hasta aca para quedar en effective_config y poder preguntar despues
    # "que perfil se usa de verdad".
    # "product" = promocionar algo, el unico objetivo que la app servia hasta
    # RM-42 y por tanto el default: un proyecto viejo o reanudado via /resume
    # no tiene la clave y tiene que seguir comportandose igual.
    # "professional" = posicionar un perfil profesional (LinkedIn, X).
    # String y no enum, mismo criterio que caption_highlight_style y
    # filter_preset: un valor no reconocido cae al default en vez de romper.
    objective: str = "product"
    speaker_reference_wav: Path | None = None  # None = usa la voz por defecto
    # None = el video dura lo que tarda la narracion (comportamiento previo).
    # Si se fija: narracion mas larga se acelera (atempo) para encajar;
    # narracion mas corta deja el Ken Burns corriendo el tiempo restante.
    target_duration_seconds: float | None = None
    caption_bg_color: str = "#000000"  # hex "#RRGGBB", ver caption_highlight_style
    # "background" = caja de fondo opaca de ese color detras del texto blanco
    # (comportamiento previo). "text_color" = el texto queda de ese color en
    # vez de blanco, sin caja (solo contorno para legibilidad). "karaoke" =
    # la palabra que se esta narrando cambia de color (ver RM-25).
    # "karaoke_background" = igual que "karaoke" pero la palabra activa
    # prende una caja de fondo en vez de cambiar de color.
    caption_highlight_style: str = "background"
    # Color del texto -- solo tiene efecto en "background" y
    # "karaoke_background" (ahi el texto no toma el valor de
    # `caption_bg_color`, que en esos dos estilos es pura y exclusivamente
    # el color de la caja/resaltado). En "text_color"/"karaoke" el texto
    # sigue tomando `caption_bg_color` como antes, este campo se ignora.
    caption_text_color: str = "#FFFFFF"
    # None = sin musica de fondo (comportamiento previo). Si se fija, se
    # mezcla en volumen bajo debajo de la narracion (nunca debe taparla) y
    # se ajusta (loop/recorte) a la duracion final del video.
    background_music_path: Path | None = None
    # Rango [start, end) DENTRO de background_music_path a usar como fuente
    # del loop (ver RM-28) -- None en end = hasta el final de la pista.
    # Ignorado si background_music_path es None.
    background_music_start: float = 0.0
    background_music_end: float | None = None
    # Volumen lineal (no dB) de la musica de fondo al mezclarla -- mismo
    # default que el que ya tenia mix_background_music. Ignorado si
    # background_music_path es None.
    background_music_volume: float = 0.12
    # Volumen lineal (no dB) de la narracion, 1.0 = sin cambios. Se aplica
    # SIEMPRE (haya o no musica de fondo) -- ver GenerateMicroVideoUseCase.
    narration_volume: float = 1.0
    # Textos superpuestos posicionables (ver RM-28) -- lista vacia = sin
    # overlays, comportamiento previo (solo captions de la narracion).
    text_overlays: list[TextOverlay] = field(default_factory=list)
    # Posicion de los captions de la narracion (fraccion 0-1 del ancho/alto
    # del video, CENTRO del caption -- mismo criterio que TextOverlay.x/y,
    # arrastrable en el editor igual que un overlay de texto).
    caption_x: float = 0.5
    caption_y: float = 0.85
    # Emojis superpuestos posicionables (ver RM-32) -- lista vacia = sin
    # emojis, comportamiento previo.
    emoji_overlays: list[EmojiOverlay] = field(default_factory=list)


@dataclass(slots=True)
class GenerateMicroVideoResult:
    """Resultado de una generacion de micro-video."""

    output_video: Path
    duration_seconds: float
    timings: dict = field(default_factory=dict)
