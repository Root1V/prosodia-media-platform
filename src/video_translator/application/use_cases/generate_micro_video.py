"""Caso de uso: GenerateMicroVideoUseCase.

Genera un micro-video vertical para redes sociales a partir de una imagen y
un texto: la imagen queda de fondo con un efecto Ken Burns (zoom lento), el
texto se narra con TTS (mismo `SpeechSynthesizer`/particionado en fragmentos
que `SynthesizeTextUseCase`) y se incrusta como captions sincronizados con la
narracion. No usa ningun modelo de generacion de imagen/video -- toda la
composicion es ffmpeg (`MediaProcessor`), ver RM-14 en docs/roadmap.md para
la alternativa con video generado por IA (RM-22).
"""

from __future__ import annotations

import re
from pathlib import Path

from video_translator.application.interfaces import MediaProcessor, SpeechSynthesizer
from video_translator.application.use_cases.text_chunking import split_into_chunks
from video_translator.domain.exceptions import InvalidVideoFileError, VideoTranslatorError
from video_translator.domain.models import (
    EmojiOverlay,
    GenerateMicroVideoRequest,
    GenerateMicroVideoResult,
    MicroVideoMediaItem,
    TextOverlay,
    TranslatedSegment,
)
from video_translator.utils.logging_config import get_logger
from video_translator.utils.timing import PipelineTimings

logger = get_logger(__name__)

DEFAULT_MAX_CHUNK_CHARS = 500
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
# Subconjunto de video de transcribe_media.SUPPORTED_EXTENSIONS (ver RM-36) --
# los mismos contenedores, sin los formatos de solo audio.
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
SUPPORTED_MEDIA_EXTENSIONS = SUPPORTED_IMAGE_EXTENSIONS | SUPPORTED_VIDEO_EXTENSIONS
# Piso de duracion de un segmento de imagen cuando los clips de video solos
# ya cubren toda la duracion pedida (ver execute) -- un segmento de 0s
# produce un mp4 de un frame que el demuxer concat no maneja bien.
MIN_IMAGE_SEGMENT_SECONDS = 1.0
# Dimensiones de salida por formato (ver RM-42). Hasta RM-42 esto era un par
# de constantes fijas en 9:16: el unico destino del micro-video era un short
# vertical. "vertical" sigue siendo el default (= lo que el pipeline hacia
# antes); lo que cambia es que `execute` las deriva del formato del request.
#
# OJO con los tamanos de fuente: los overlays y los captions se miden en
# pixeles sobre el ANCHO del video, asi que el mismo font_size se ve
# relativamente mas pequeño en "landscape" (1920 de ancho) que en los otros
# dos (1080). No se normaliza aqui a proposito: el editor divide por el ancho
# de ESTE mismo formato (ver TextOverlayCanvas en el frontend), asi que lo que
# se ve en el preview es lo que sale. Normalizar en un solo lado romperia esa
# correspondencia, que es lo unico que el usuario puede comprobar.
VIDEO_FORMATS: dict[str, tuple[int, int]] = {
    "vertical": (1080, 1920),  # 9:16 -- shorts, Reels, TikTok
    "square": (1080, 1080),  # 1:1 -- feed de LinkedIn y X
    "landscape": (1920, 1080),  # 16:9
}
DEFAULT_VIDEO_FORMAT = "vertical"
# Los fragmentos de TTS (hasta DEFAULT_MAX_CHUNK_CHARS) son del tamano
# correcto para sintetizar, pero un caption con cientos de caracteres
# aparece como un bloque estatico que cubre buena parte de la pantalla en
# vez de acompañar el habla. Los captions se generan aparte, mas cortos,
# repartiendo la duracion real de cada fragmento entre sus propios captions
# (ver _build_caption_segments).
CAPTION_MAX_CHARS = 50
# Estilo de los captions (ver _write_ass_captions): Alignment=2 (centrado,
# abajo), BorderStyle=3 (caja solida) porque texto blanco con solo contorno
# se pierde sobre una imagen de fondo clara/blanca -- una caja resaltada
# (color elegible por el usuario) garantiza contraste sin importar el fondo.
CAPTION_FONT_SIZE = 52
CAPTION_MARGIN_V = 160
# Opacidad de la caja de fondo (00 = opaco, FF = transparente en ASS).
# Probado en la practica: libass (via el filtro "ass" de ffmpeg) NO mezcla
# bien un BackColour semi-transparente con el video de fondo -- el resultado
# sale oscuro/incorrecto sin importar el color elegido, sea cual sea el
# alpha intermedio. Opaco evita ese problema y es igual de legible.
CAPTION_BG_ALPHA_HEX = "00"
# Duracion del fade in/out de un overlay con TextOverlay.fade=True (ver
# _build_overlay_style_and_dialogue), clampeada para videos muy cortos.
OVERLAY_FADE_MS = 500
# Set curado de PNGs de emoji bundleados (ver RM-32, docs/roadmap.md) --
# el pipeline ASS/libass de texto no puede renderizar emoji en este
# sistema, asi que se componen como imagen via MediaProcessor.overlay_emojis.
_EMOJI_ASSET_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "emojis"
# Tipografias bundleadas para los TextOverlay (ver RM-33) -- se le pasan a
# render_ass_captions como `fonts_dir` para que libass las encuentre sin
# necesitar que esten instaladas en el sistema (probado a mano).
_TEXT_ASSET_FONTS_DIR = Path(__file__).resolve().parent.parent.parent / "assets" / "fonts"

# "**palabra**" se resalta en negrita en el caption (no se lee en voz alta:
# ver _strip_bold_markers, usado para el texto que va al sintetizador).
_BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*")


def _strip_bold_markers(text: str) -> str:
    return _BOLD_PATTERN.sub(r"\1", text)


def _convert_bold_to_ass(text: str) -> str:
    return _BOLD_PATTERN.sub(r"{\\b1}\1{\\b0}", text)


def _hex_to_bgr(hex_color: str) -> str:
    """Convierte "#RRGGBB" a "BBGGRR" (orden de color de ASS). Si el valor no
    es un hex valido, cae a negro solido."""
    value = hex_color.lstrip("#")
    if len(value) != 6 or any(c not in "0123456789abcdefABCDEF" for c in value):
        value = "000000"
    rr, gg, bb = value[0:2], value[2:4], value[4:6]
    return f"{bb}{gg}{rr}"


def _hex_to_ass_color(hex_color: str) -> str:
    """Convierte "#RRGGBB" al color de una linea "Style:" de ASS:
    &HAABBGGRR (alpha primero, siempre opaco -- ver CAPTION_BG_ALPHA_HEX)."""
    return f"&H{CAPTION_BG_ALPHA_HEX}{_hex_to_bgr(hex_color)}"


def _hex_to_ass_inline_color(hex_color: str) -> str:
    """Convierte "#RRGGBB" a un override inline `{\\c...}` de ASS --
    &HBBGGRR&, SIN byte de alpha (el override `\\c` no lo lleva, a
    diferencia del campo de color de una linea "Style:")."""
    return f"&H{_hex_to_bgr(hex_color)}&"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Convierte "#RRGGBB" a (r, g, b). Mismo criterio de fallback a negro
    que _hex_to_bgr si el valor no es un hex valido."""
    value = hex_color.lstrip("#")
    if len(value) != 6 or any(c not in "0123456789abcdefABCDEF" for c in value):
        value = "000000"
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


# PrimaryColour totalmente transparente (alpha=FF) -- usado por el estilo
# "hollow" (ver _text_style_ass_params), donde el "relleno" real no se
# dibuja, solo el contorno.
_TRANSPARENT_ASS_COLOR = "&HFF000000"
_BLACK_ASS_OUTLINE = "&H00000000"


def _text_style_ass_params(overlay: TextOverlay) -> tuple[str, str, int, int, str]:
    """Devuelve (PrimaryColour, OutlineColour, Outline, Shadow, override_tag_extra)
    de la linea Style:/Dialogue: de un TextOverlay segun su text_style (ver
    RM-33) -- todos los valores probados a mano con el ffmpeg-full real.
    Un text_style no reconocido cae al comportamiento "flat" (mismo
    criterio que filter_preset/caption_highlight_style)."""
    fill = _hex_to_ass_color(overlay.color)
    accent = _hex_to_ass_color(overlay.accent_color)
    if overlay.text_style == "hard_shadow":
        return fill, _BLACK_ASS_OUTLINE, 2, 8, ""
    if overlay.text_style == "thick_outline":
        return fill, _BLACK_ASS_OUTLINE, 10, 1, ""
    if overlay.text_style == "long_shadow":
        # Shadow=0: el tag `Shadow` nativo de ASS es una UNICA copia solida
        # desplazada -- probado a mano con texto real, se ve como un
        # duplicado "flotando" al lado, no como una sombra. La cinta
        # diagonal se arma a mano en _build_overlay_style_and_dialogue con
        # varias copias solidas en negro (ver _LONG_SHADOW_STEPS).
        return fill, _BLACK_ASS_OUTLINE, 1, 0, ""
    if overlay.text_style == "hollow":
        # El color elegido por el usuario pasa al CONTORNO -- no hay
        # relleno real que mostrar.
        return _TRANSPARENT_ASS_COLOR, fill, 6, 0, ""
    if overlay.text_style == "neon_glow":
        return fill, accent, 4, 0, "\\blur6"
    if overlay.text_style == "colored_outline":
        return fill, accent, 6, 1, ""
    # "flat" y "gradient" (el degradado reemplaza el relleno via \1c en el
    # texto, no en la Style) -- comportamiento previo a RM-33.
    return fill, _BLACK_ASS_OUTLINE, 3, 1, ""


def _is_video_item(item: MicroVideoMediaItem) -> bool:
    """Un item es un clip de video (no una imagen con Ken Burns) segun su
    extension -- misma fuente de verdad que _validate_request, sin un campo
    `kind` aparte que pudiera contradecirla."""
    return item.path.suffix.lower() in SUPPORTED_VIDEO_EXTENSIONS


def _resolve_keep_ranges(item: MicroVideoMediaItem, real_duration: float) -> list[tuple[float, float]]:
    """Resuelve `item.keep_ranges` (ver RM-40) a una lista de rangos con
    valores concretos: `None` en el item entero se convierte en un unico
    rango [0, real_duration) (el clip completo, comportamiento previo a
    RM-40); el `end=None` del ULTIMO rango de una lista explicita se
    resuelve contra `real_duration`, con el mismo clamp que ya se hacia
    para clip_end en RM-36 (un end mas alla del final real dejaria el
    segmento mas corto de lo que asume el reparto de duracion)."""
    if item.keep_ranges is None:
        return [(0.0, real_duration)]
    resolved: list[tuple[float, float]] = []
    for start, end in item.keep_ranges:
        resolved_end = real_duration if end is None else min(end, real_duration)
        resolved.append((start, resolved_end))
    return resolved


def _apply_gradient_colors(text: str, start_hex: str, end_hex: str) -> str:
    """Interpola color por caracter entre start_hex y end_hex (ver RM-33,
    TextOverlay.text_style="gradient") -- ASS/libass no tiene un tag de
    relleno degradado nativo para texto, esto lo aproxima con un override
    `\\1c` por caracter (probado a mano: con textos de 5+ caracteres se ve
    como un degradado suave, discretizado por caracter). Preserva "\\N"
    (salto de linea, ya escapado por _escape_overlay_text) como una unidad
    sin colorear -- partirlo en "\\" y "N" por separado rompe el override."""
    start_rgb = _hex_to_rgb(start_hex)
    end_rgb = _hex_to_rgb(end_hex)
    glyphs: list[str] = []
    for token in re.split(r"(\\N)", text):
        if token == "\\N":
            glyphs.append(token)
        else:
            glyphs.extend(token)
    steps = max(1, sum(1 for g in glyphs if g != "\\N") - 1)
    parts: list[str] = []
    step = 0
    for glyph in glyphs:
        if glyph == "\\N":
            parts.append(glyph)
            continue
        t = step / steps
        r = round(start_rgb[0] + (end_rgb[0] - start_rgb[0]) * t)
        g = round(start_rgb[1] + (end_rgb[1] - start_rgb[1]) * t)
        b = round(start_rgb[2] + (end_rgb[2] - start_rgb[2]) * t)
        inline_color = _hex_to_ass_inline_color(f"#{r:02X}{g:02X}{b:02X}")
        parts.append("{\\1c" + inline_color + "}" + glyph)
        step += 1
    return "".join(parts)


class GenerateMicroVideoUseCase:
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

    def execute(self, request: GenerateMicroVideoRequest) -> GenerateMicroVideoResult:
        self._validate_request(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        workdir = request.output_dir / "_work"
        chunk_dir = workdir / "tts_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)

        report_path = request.output_dir / "pipeline_timings.json"
        timings = PipelineTimings(report_path=report_path)
        # Un formato desconocido cae al default en vez de romper: el valor
        # llega de `config`, que es JSON sin esquema, y un proyecto reanudado
        # via /resume puede no tener la clave.
        video_width, video_height = VIDEO_FORMATS.get(request.video_format, VIDEO_FORMATS[DEFAULT_VIDEO_FORMAT])

        # El objetivo sale del request y no del contenedor (que no lo ve),
        # pero se vuelca igual: es lo que permite preguntarle despues al
        # informe que perfil se uso de verdad en cada corrida (ver RM-42).
        timings.set_effective_config(
            **self._effective_config,
            objective=request.objective,
            video_format=f"{video_width}x{video_height}",
        )
        log = logger.bind(run_id=timings.run_id)
        log.info("generate_micro_video.start", chars=len(request.text))

        speaker_wav = request.speaker_reference_wav or self._default_speaker_wav

        chunks = split_into_chunks(request.text, self._max_chunk_chars)
        segments: list[tuple[float, Path, float]] = []
        cursor = 0.0
        with timings.stage("text_to_speech", num_chunks=len(chunks)):
            for i, chunk_text in enumerate(chunks):
                chunk_path = chunk_dir / f"chunk_{i:03d}.wav"
                self._synthesizer.synthesize_segment(
                    text=_strip_bold_markers(chunk_text),
                    output_path=chunk_path,
                    target_duration_seconds=0.0,
                    speaker_reference_wav=speaker_wav,
                    language=request.language,
                )
                chunk_duration = self._media.get_duration_seconds(chunk_path)
                segments.append((cursor, chunk_path, chunk_duration))
                cursor += chunk_duration
        log.info("generate_micro_video.narration_done", num_chunks=len(chunks))

        narration_path = workdir / "narration.wav"
        with timings.stage("audio_concatenation"):
            self._synthesizer.concatenate_segments(segments, cursor, narration_path)

        # Duracion fija elegida por el usuario (ver RM-14): si la narracion
        # se paso, se acelera el audio entero para que encaje (nunca se
        # recorta -- ver MediaProcessor.fit_audio_to_duration) y los
        # timestamps de los captions ya calculados se reescalan en la misma
        # proporcion para seguir sincronizados. Si la narracion es mas corta,
        # el video queda con la duracion fija igual (el Ken Burns sigue
        # corriendo en silencio el tiempo restante, ver render_image_video).
        video_duration = cursor
        if request.target_duration_seconds is not None:
            target = request.target_duration_seconds
            if cursor > target > 0:
                with timings.stage("narration_speedup", original_seconds=round(cursor, 2), target_seconds=target):
                    self._media.fit_audio_to_duration(narration_path, target)
                speed_factor = cursor / target
                segments = [(start / speed_factor, path, duration / speed_factor) for start, path, duration in segments]
                cursor = target
            video_duration = target

        # RM-36: un clip de video ocupa SU PROPIA duracion real en la linea de
        # tiempo (recortada si el usuario eligio un rango en el editor), nunca
        # una tajada igual -- un clip cortado a la mitad para "encajar"
        # pierde su sentido. El tiempo que queda se reparte en partes iguales
        # solo entre las IMAGENES (misma regla que RM-29, aplicada al
        # remanente). Si los clips solos ya cubren la duracion pedida, el
        # video se ESTIRA para que ninguno se recorte, y las imagenes caen al
        # piso de MIN_IMAGE_SEGMENT_SECONDS. Desde RM-40 un clip puede tener
        # VARIOS rangos conservados (tramos sueltos, con huecos eliminados
        # entre medio) -- su duracion total es la SUMA de esos rangos, y cada
        # uno se renderiza como su propio sub-segmento (ver el loop de abajo).
        clip_durations: dict[int, float] = {}
        resolved_ranges: dict[int, list[tuple[float, float]]] = {}
        for i, item in enumerate(request.media_items):
            if _is_video_item(item):
                real_end = self._media.get_duration_seconds(item.path)
                ranges = _resolve_keep_ranges(item, real_end)
                resolved_ranges[i] = ranges
                clip_durations[i] = sum(max(0.0, end - start) for start, end in ranges)

        num_images = len(request.media_items) - len(clip_durations)
        clips_total = sum(clip_durations.values())
        image_duration = 0.0
        if num_images:
            image_duration = max(MIN_IMAGE_SEGMENT_SECONDS, (video_duration - clips_total) / num_images)
        if clip_durations:
            # Solo se recalcula si hay clips -- sin ellos esto es exactamente
            # el video_duration de siempre, sin ida y vuelta por punto flotante.
            video_duration = clips_total + image_duration * num_images

        if request.narration_volume != 1.0:
            with timings.stage("narration_volume"):
                self._media.apply_volume(narration_path, request.narration_volume)

        final_audio_path = narration_path
        if request.background_music_path is not None:
            music_path = request.background_music_path
            # Rango elegido por el usuario dentro de la pista (ver RM-28): se
            # recorta una vez a un archivo aparte, que es lo que despues se
            # loopea/mezcla -- mix_background_music no cambia, solo recibe
            # ya el fragmento correcto en vez de la pista completa.
            if request.background_music_start > 0 or request.background_music_end is not None:
                music_range_path = workdir / "background_music_range.wav"
                with timings.stage("background_music_trim"):
                    self._media.extract_music_range(
                        music_path,
                        request.background_music_start,
                        request.background_music_end or self._media.get_duration_seconds(music_path),
                        music_range_path,
                    )
                music_path = music_range_path
            mixed_audio_path = workdir / "narration_with_music.wav"
            with timings.stage("background_music"):
                self._media.mix_background_music(
                    narration_path,
                    music_path,
                    mixed_audio_path,
                    duration_seconds=video_duration,
                    music_volume=request.background_music_volume,
                )
            final_audio_path = mixed_audio_path

        caption_segments = _build_caption_segments(
            [(chunk_text, start, duration) for chunk_text, (start, _path, duration) in zip(chunks, segments)]
        )
        captions_path = workdir / "captions.ass"
        with timings.stage("caption_writing"):
            _write_ass_captions(
                caption_segments,
                captions_path,
                video_width,
                video_height,
                request.caption_bg_color,
                request.caption_highlight_style,
                text_color=request.caption_text_color,
                overlays=request.text_overlays,
                duration=video_duration,
                caption_x=request.caption_x,
                caption_y=request.caption_y,
            )

        # Cada imagen se renderiza MUDA (audio_path=None) por su propia
        # porcion de la duracion restante, en partes iguales -- ver RM-29. Un
        # clip de video (ver RM-36) se renderiza mudo por SU PROPIA duracion
        # real (ver clip_durations arriba), no por esta porcion. Con una sola
        # imagen y ningun clip esto se reduce al comportamiento previo (un
        # unico segmento de toda la duracion). El audio se mezcla DESPUES,
        # sobre el video ya concatenado, para no depender de donde caen los
        # cortes entre items.
        segment_paths: list[Path] = []
        with timings.stage(
            "media_to_video", num_items=len(request.media_items), num_clips=len(clip_durations)
        ):
            for i, item in enumerate(request.media_items):
                segment_path = workdir / f"segment_{i:03d}.mp4"
                if i in clip_durations:
                    ranges = resolved_ranges[i]
                    if len(ranges) == 1:
                        start, end = ranges[0]
                        self._media.render_clip_video(
                            item.path,
                            segment_path,
                            duration_seconds=end - start,
                            start_seconds=start,
                            width=video_width,
                            height=video_height,
                            offset_x=item.offset_x,
                            offset_y=item.offset_y,
                            zoom=item.zoom,
                            filter_preset=item.filter_preset,
                        )
                    else:
                        # RM-40: varios tramos sueltos del mismo clip (con
                        # huecos eliminados entre medio) -- cada uno se
                        # renderiza como su propio sub-segmento normalizado
                        # (reusa render_clip_video tal cual) y despues se
                        # concatenan entre si para producir el UNICO
                        # segment_path de este item, antes de que ese archivo
                        # entre en el concat general de todos los items mas
                        # abajo. No hace falta nada nuevo en el MediaProcessor:
                        # el concat demuxer con -c copy ya es seguro porque
                        # todos los sub-segmentos salen del mismo
                        # render_clip_video (mismo codec/resolucion/fps).
                        sub_paths = []
                        for j, (start, end) in enumerate(ranges):
                            sub_path = workdir / f"segment_{i:03d}_part{j:02d}.mp4"
                            self._media.render_clip_video(
                                item.path,
                                sub_path,
                                duration_seconds=end - start,
                                start_seconds=start,
                                width=video_width,
                                height=video_height,
                                offset_x=item.offset_x,
                                offset_y=item.offset_y,
                                zoom=item.zoom,
                                filter_preset=item.filter_preset,
                            )
                            sub_paths.append(sub_path)
                        self._media.concatenate_videos(sub_paths, segment_path)
                else:
                    self._media.render_image_video(
                        item.path,
                        None,
                        segment_path,
                        duration_seconds=image_duration,
                        width=video_width,
                        height=video_height,
                        offset_x=item.offset_x,
                        offset_y=item.offset_y,
                        zoom=item.zoom,
                        filter_preset=item.filter_preset,
                    )
                segment_paths.append(segment_path)

        if len(segment_paths) > 1:
            silent_path = workdir / "background_silent.mp4"
            with timings.stage("media_concat"):
                self._media.concatenate_videos(segment_paths, silent_path)
        else:
            silent_path = segment_paths[0]

        background_path = workdir / "background.mp4"
        with timings.stage("audio_mux"):
            self._media.replace_audio_track(
                silent_path, final_audio_path, background_path, keep_original_as_secondary=False
            )

        fonts_dir = _TEXT_ASSET_FONTS_DIR if _TEXT_ASSET_FONTS_DIR.is_dir() else None
        output_video = request.output_dir / "micro_video.mp4"
        if request.emoji_overlays:
            captioned_path = workdir / "captioned.mp4"
            with timings.stage("caption_burn"):
                self._media.render_ass_captions(
                    background_path, captions_path, captioned_path, fonts_dir=fonts_dir
                )
            placements = _resolve_emoji_placements(request.emoji_overlays)
            with timings.stage("emoji_burn", num_emojis=len(placements)):
                self._media.overlay_emojis(
                    captioned_path, placements, output_video, video_width, video_duration
                )
        else:
            with timings.stage("caption_burn"):
                self._media.render_ass_captions(
                    background_path, captions_path, output_video, fonts_dir=fonts_dir
                )

        timings.set_outputs(video_bytes=output_video.stat().st_size)
        timings.write_report(report_path, final=True)
        log.info(
            "generate_micro_video.finished",
            total_seconds=round(timings.total_seconds, 1),
            timings_report=str(report_path),
        )

        return GenerateMicroVideoResult(
            output_video=output_video,
            duration_seconds=video_duration,
            timings=timings.as_dict(),
        )

    @staticmethod
    def _validate_request(request: GenerateMicroVideoRequest) -> None:
        if not request.text.strip():
            raise VideoTranslatorError("El texto a narrar esta vacio.")
        if not request.media_items:
            raise InvalidVideoFileError("Se necesita al menos una imagen o un video.")
        for item in request.media_items:
            if not item.path.exists():
                raise InvalidVideoFileError(f"No existe el archivo: {item.path}")
            if item.path.suffix.lower() not in SUPPORTED_MEDIA_EXTENSIONS:
                raise InvalidVideoFileError(
                    f"Extension no soportada '{item.path.suffix}'. "
                    f"Soportadas: {sorted(SUPPORTED_MEDIA_EXTENSIONS)}"
                )
            if item.zoom < 1.0:
                raise InvalidVideoFileError(f"zoom invalido ({item.zoom}): debe ser >= 1.0.")
            if _is_video_item(item) and item.keep_ranges is not None:
                ranges = item.keep_ranges
                if not ranges:
                    raise InvalidVideoFileError("keep_ranges no puede ser una lista vacia.")
                previous_end: float | None = 0.0
                for i, (start, end) in enumerate(ranges):
                    if start < 0:
                        raise InvalidVideoFileError(f"keep_ranges invalido: start ({start}) debe ser >= 0.")
                    if end is not None and end <= start:
                        raise InvalidVideoFileError(
                            f"Rango invalido en keep_ranges ({start}-{end}): end debe ser mayor que start."
                        )
                    if end is None and i != len(ranges) - 1:
                        raise InvalidVideoFileError(
                            "Solo el ultimo rango de keep_ranges puede dejar 'end' sin definir."
                        )
                    if previous_end is not None and start < previous_end:
                        raise InvalidVideoFileError(
                            f"keep_ranges debe venir en orden ascendente y sin solaparse "
                            f"(rango {i} empieza en {start}, antes de que termine el anterior en {previous_end})."
                        )
                    previous_end = end


def _distribute_duration(pieces: list[str], start: float, duration: float) -> list[tuple[str, float, float]]:
    """Reparte `duration` entre `pieces` en proporcion a su cantidad de
    caracteres, asumiendo ritmo de habla uniforme -- mismo criterio en dos
    niveles: fragmento de TTS -> caption (ver _build_caption_segments) y
    caption -> palabra (ver _build_karaoke_dialogues, RM-25). No hay
    timestamps reales de ningun nivel mas fino que el fragmento de TTS."""
    total_chars = sum(len(piece) for piece in pieces) or 1
    cursor = start
    result: list[tuple[str, float, float]] = []
    for piece in pieces:
        piece_duration = duration * (len(piece) / total_chars)
        result.append((piece, cursor, cursor + piece_duration))
        cursor += piece_duration
    return result


def _build_caption_segments(chunks_with_timing: list[tuple[str, float, float]]) -> list[TranslatedSegment]:
    """Convierte los fragmentos de TTS (texto, inicio, duracion) en captions
    mas cortos y con mas movimiento: cada fragmento se vuelve a partir en
    piezas de hasta CAPTION_MAX_CHARS, repartiendo la duracion real del
    fragmento entre sus piezas en proporcion a su cantidad de caracteres
    (ver _distribute_duration).

    No hay timestamps por palabra del motor de TTS -- esto es una
    aproximacion (asume ritmo de habla uniforme dentro de un mismo
    fragmento), pero alcanza para que los captions vayan apareciendo y
    desapareciendo con el habla en vez de mostrar todo el texto de un
    fragmento de golpe durante toda su duracion."""
    segments: list[TranslatedSegment] = []
    seg_id = 0
    for chunk_text, chunk_start, chunk_duration in chunks_with_timing:
        pieces = _split_caption_text(chunk_text, CAPTION_MAX_CHARS)
        for piece, piece_start, piece_end in _distribute_duration(pieces, chunk_start, chunk_duration):
            segments.append(
                TranslatedSegment(
                    id=seg_id,
                    start=piece_start,
                    end=piece_end,
                    source_text=piece,
                    translated_text=piece,
                )
            )
            seg_id += 1
    return segments


def _split_caption_text(text: str, max_chars: int) -> list[str]:
    """Como `split_into_chunks`, pero garantiza que ninguna pieza supere
    `max_chars`: esa funcion solo parte ENTRE oraciones, asi que una sola
    oracion larga (sin puntos internos) queda intacta aunque exceda el
    limite -- para un caption eso es exactamente el bug que se busca evitar
    (todo el texto en un solo cartel). Las piezas que aun excedan el limite
    se vuelven a partir por palabra, de forma codiciosa."""
    pieces: list[str] = []
    for sentence_piece in split_into_chunks(text, max_chars):
        if len(sentence_piece) <= max_chars:
            pieces.append(sentence_piece)
            continue
        words = sentence_piece.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip() if current else word
            if len(candidate) > max_chars and current:
                pieces.append(current)
                current = word
            else:
                current = candidate
        if current:
            pieces.append(current)
    return pieces


def _build_caption_style(highlight_style: str, color: str, text_color: str) -> str:
    """Arma la linea "Style:" de ASS segun el estilo de resaltado elegido:

    "background" (default): texto de `text_color` (blanco por defecto)
    sobre una caja opaca del color elegido (BorderStyle=3). OutlineColour
    se fija IGUAL a BackColour a proposito: probado en la practica, en
    BorderStyle=3 esta version de libass rellena la caja con OutlineColour,
    no con BackColour como sugiere la documentacion -- dejarlo en un color
    fijo (p.ej. negro) hacia que la caja saliera siempre negra sin importar
    el color elegido.

    "text_color": el texto queda del color elegido (`color`, no
    `text_color` -- este estilo nunca tuvo un color de caja separado), sin
    caja, solo un contorno negro (BorderStyle=1) para que se lea sobre
    cualquier fondo.

    "karaoke" (ver RM-25): mismo criterio visual que "text_color" (sin
    caja, con contorno), pero PrimaryColour queda FIJO en blanco -- es el
    color de las palabras que todavia no se dijeron/ya se dijeron; la
    palabra activa se pinta con un override inline por Dialogue (ver
    _build_karaoke_dialogues), no por este estilo.

    "karaoke_background": variante de "karaoke" -- en vez de que la palabra
    activa cambie de COLOR, se le resalta el FONDO (una caja opaca detras,
    solo de esa palabra). PrimaryColour usa `text_color` (blanco por
    defecto) para TODAS las palabras -- a diferencia de "karaoke", nunca
    cambia, ni siquiera la activa. OutlineColour arranca totalmente
    transparente (alpha FF) para que las palabras que no estan activas no
    muestren ninguna caja -- la palabra activa la prende con un override
    inline (ver _build_karaoke_dialogues). BorderStyle=3 (igual que
    "background"): probado a mano con el ffmpeg-full real que en ese modo
    la "caja" de OutlineColour se dibuja POR CADA TRAMO de texto con un
    override propio, no por todo el Dialogue -- eso es lo que permite que
    solo la palabra activa muestre caja.
    """
    ass_color = _hex_to_ass_color(color)
    ass_text_color = _hex_to_ass_color(text_color)
    if highlight_style == "text_color":
        # PrimaryColour, SecondaryColour, OutlineColour, BackColour
        colours = f"{ass_color},&H000000FF,&H00000000,&H00000000"
        border_style, outline, shadow = 1, 3, 1
    elif highlight_style == "karaoke":
        colours = "&H00FFFFFF,&H000000FF,&H00000000,&H00000000"
        border_style, outline, shadow = 1, 3, 1
    elif highlight_style == "karaoke_background":
        colours = f"{ass_text_color},&H000000FF,{_TRANSPARENT_ASS_COLOR},&H00000000"
        border_style, outline, shadow = 3, 8, 0
    else:
        colours = f"{ass_text_color},&H000000FF,{ass_color},{ass_color}"
        border_style, outline, shadow = 3, 2, 0
    return (
        f"Style: Default,Arial,{CAPTION_FONT_SIZE},{colours},"
        # Alignment=5 (centro): el \pos(x,y) de cada Dialogue (ver
        # _write_ass_captions) posiciona el CENTRO del caption, igual
        # criterio que los overlays de texto -- arrastrable en el editor.
        f"0,0,0,0,100,100,0,0,{border_style},{outline},{shadow},5,60,60,{CAPTION_MARGIN_V},1"
    )


def _build_karaoke_dialogues(
    segments: list[TranslatedSegment], pos_tag: str, color: str, highlight_style: str
) -> list[str]:
    """Arma los `Dialogue:` para los estilos "karaoke"/"karaoke_background"
    (ver RM-25): a diferencia de los otros dos estilos (un Dialogue por
    caption), esto emite VARIOS Dialogue por caption -- uno por palabra,
    cada uno mostrando el texto COMPLETO del caption pero con esa palabra
    envuelta en un override inline (el resto queda con el estilo fijo por
    `_build_caption_style`). El timing de cada palabra dentro del caption
    se estima con `_distribute_duration` (mismo criterio que ya usa
    `_build_caption_segments` un nivel mas arriba).

    "karaoke": la palabra activa cambia de COLOR (`\\c`, ver PrimaryColour).
    "karaoke_background": la palabra activa prende una caja de fondo
    (`\\3c`/`\\3a`, ver OutlineColour) en vez de cambiar de color -- el
    resto de las palabras quedan con la caja apagada (`\\3a&H00FF&`, mismo
    valor por default que ya fija `_build_caption_style`)."""
    inline_color = _hex_to_ass_inline_color(color)
    if highlight_style == "karaoke_background":
        tag_on, tag_off = "\\3c" + inline_color + "\\3a&H00&", "\\3a&HFF&"
    else:
        tag_on, tag_off = "\\c" + inline_color, "\\c"
    lines: list[str] = []
    for seg in segments:
        # Mismo criterio que el loop de los otros estilos: despojar llaves
        # literales ANTES de aplicar cualquier override tag propio.
        raw_text = seg.translated_text.replace("{", "").replace("}", "").replace("\n", " ")
        words = [word for word in raw_text.split(" ") if word]
        if not words:
            continue
        converted_words = [_convert_bold_to_ass(word) for word in words]
        windows = _distribute_duration(words, seg.start, seg.end - seg.start)
        for active_index, (_, word_start, word_end) in enumerate(windows):
            rendered = [
                "{" + tag_on + "}" + word + "{" + tag_off + "}" if i == active_index else word
                for i, word in enumerate(converted_words)
            ]
            text = pos_tag + " ".join(rendered)
            lines.append(
                f"Dialogue: 0,{_format_ass_timestamp(word_start)},{_format_ass_timestamp(word_end)},"
                f"Default,,0,0,0,,{text}"
            )
    return lines


def _write_ass_captions(
    segments: list[TranslatedSegment],
    output_path: Path,
    width: int,
    height: int,
    color: str,
    highlight_style: str,
    text_color: str = "#FFFFFF",
    overlays: list[TextOverlay] | None = None,
    duration: float = 0.0,
    caption_x: float = 0.5,
    caption_y: float = 0.85,
) -> Path:
    """Escribe los captions como .ass (no .srt) con un header propio que
    declara `PlayResX`/`PlayResY` igual al tamano real del video: sin esto,
    libass asume una resolucion de guion vieja (384x288) al renderizar un
    .srt "plano" y reescala el font al tamano real del video, lo que en un
    vertical de alta resolucion (1080x1920) termina en un texto gigante que
    cubre la pantalla.

    `overlays` (ver RM-28, textos libres posicionados a mano) se agregan al
    MISMO script: cada uno con su propio `Style:` (fuente/tamano/color/
    negrita propios) y una unica `Dialogue:` que dura todo el video, usando
    `\\pos(x,y)` para la posicion absoluta -- no hace falta ningun filtro de
    ffmpeg nuevo, `render_ass_captions` ya sabe renderizar esto tal cual."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    style = _build_caption_style(highlight_style, color, text_color)
    overlay_styles: list[str] = []
    overlay_dialogues: list[str] = []
    for i, overlay in enumerate(overlays or []):
        overlay_style, overlay_dialogue_lines = _build_overlay_style_and_dialogue(overlay, i, width, height, duration)
        overlay_styles.append(overlay_style)
        overlay_dialogues.extend(overlay_dialogue_lines)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        f"PlayResX: {width}",
        f"PlayResY: {height}",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        (
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
            "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"
        ),
        style,
        *overlay_styles,
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        # Los overlays van ANTES que los captions en la lista de eventos: en
        # el mismo Layer, libass dibuja en el orden declarado, asi que esto
        # deja los captions (la narracion) siempre por encima de un overlay
        # que pudiera superponerse en la misma zona de la pantalla.
        *overlay_dialogues,
    ]
    pos_tag = "{" + _ass_pos_tag(caption_x, caption_y, width, height) + "}"
    if highlight_style in ("karaoke", "karaoke_background"):
        lines.extend(_build_karaoke_dialogues(segments, pos_tag, color, highlight_style))
    else:
        for seg in segments:
            # Se despojan llaves literales ANTES de convertir "**negrita**" a
            # tags ASS ("{\b1}...{\b0}") -- de lo contrario un usuario que
            # escriba "{" a proposito podria inyectar sus propios overrides ASS.
            raw_text = seg.translated_text.replace("{", "").replace("}", "").replace("\n", " ")
            text = pos_tag + _convert_bold_to_ass(raw_text)
            lines.append(
                f"Dialogue: 0,{_format_ass_timestamp(seg.start)},{_format_ass_timestamp(seg.end)},"
                f"Default,,0,0,0,,{text}"
            )
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _escape_overlay_text(text: str) -> str:
    """Escapa el texto libre de un TextOverlay para el campo Text de un
    Dialogue ASS: quita llaves literales (evita que el usuario inyecte sus
    propios override tags) y convierte saltos de linea reales en el salto
    de linea nativo de ASS (\\N) -- a diferencia de los captions (generados
    automaticamente, nunca traen un salto de linea real), un overlay es
    texto libre donde preservar el salto que el usuario escribio importa."""
    return text.replace("{", "").replace("}", "").replace("\r\n", "\n").replace("\n", "\\N")


def _ass_pos_tag(x: float, y: float, width: int, height: int) -> str:
    """Fragmento de override tag `\\pos(x,y)` en pixeles absolutos, a partir
    de fracciones 0-1 del ancho/alto del video -- reusado por los overlays
    de texto y por los captions de la narracion (ambos "arrastrables" en el
    editor con el mismo criterio: el punto es el CENTRO del texto)."""
    return f"\\pos({round(x * width)},{round(y * height)})"


def _resolve_emoji_placements(
    overlays: list[EmojiOverlay],
) -> list[tuple[Path, float, float, float, bool]]:
    """Resuelve cada `EmojiOverlay.emoji_id` a la ruta real de su PNG
    bundleado (ver _EMOJI_ASSET_DIR) -- un id no reconocido simplemente se
    omite (sin validacion estricta, mismo criterio que `filter_preset`/
    `caption_highlight_style`), no rompe la generacion del video."""
    placements: list[tuple[Path, float, float, float, bool]] = []
    for overlay in overlays:
        asset_path = _EMOJI_ASSET_DIR / f"{overlay.emoji_id}.png"
        if not asset_path.is_file():
            continue
        placements.append((asset_path, overlay.x, overlay.y, overlay.size, overlay.fade))
    return placements


# Cuantas copias solidas en negro arma la cinta de "long_shadow" (ver
# _build_overlay_style_and_dialogue) -- desplazadas diagonalmente 1px, 2px,
# ..., hasta este valor, de mas lejos a mas cerca. Mismo numero de pasos
# que usa la aproximacion CSS del editor (TextOverlayCanvas.tsx) para que
# el preview y el video final se vean iguales.
_LONG_SHADOW_STEPS = 18


def _build_overlay_style_and_dialogue(
    overlay: TextOverlay, index: int, width: int, height: int, duration: float
) -> tuple[str, list[str]]:
    """Arma el `Style:`/`Dialogue:` de un TextOverlay: Alignment=5 (centro)
    para que `\\pos(x,y)` posicione el CENTRO del texto en (x,y) -- coincide
    con "donde se soltó el texto al arrastrarlo" en el editor. BorderStyle=1
    con contorno negro (mismo criterio que el estilo "text_color" de los
    captions) para que se lea sobre cualquier fondo sin importar el color
    elegido.

    Devuelve una LISTA de `Dialogue:` (no una unica linea): "long_shadow"
    necesita varias -- ver _LONG_SHADOW_STEPS y el comentario en
    _text_style_ass_params. Se arman como copias solidas en negro
    (`\\1c` + `\\bord0\\shad0`, sin usar el Outline/Shadow de la Style)
    desplazadas diagonalmente, declaradas ANTES que la copia de color
    normal -- mismo Layer, libass dibuja en el orden declarado (ver
    comentario en _write_ass_captions), asi que el texto de color queda
    arriba de toda la cinta."""
    style_name = f"Overlay{index}"
    bold_flag = -1 if overlay.bold else 0
    primary, outline_colour, outline, shadow, extra_tag = _text_style_ass_params(overlay)
    style = (
        f"Style: {style_name},{overlay.font_family},{overlay.font_size},"
        f"{primary},&H000000FF,{outline_colour},&H00000000,"
        f"{bold_flag},0,0,0,100,100,0,0,1,{outline},{shadow},5,0,0,0,1"
    )
    fade_tag = ""
    if overlay.fade:
        fade_ms = max(1, min(OVERLAY_FADE_MS, int(duration * 1000 / 4)))
        fade_tag = f"\\fad({fade_ms},{fade_ms})"
    escaped_text = _escape_overlay_text(overlay.text)
    body = (
        _apply_gradient_colors(escaped_text, overlay.color, overlay.accent_color)
        if overlay.text_style == "gradient"
        else escaped_text
    )

    dialogues: list[str] = []
    if overlay.text_style == "long_shadow":
        base_x = round(overlay.x * width)
        base_y = round(overlay.y * height)
        for step in range(_LONG_SHADOW_STEPS, 0, -1):
            ribbon_override = f"{{\\pos({base_x + step},{base_y + step}){fade_tag}\\1c&H000000&\\bord0\\shad0}}"
            dialogues.append(
                f"Dialogue: 0,{_format_ass_timestamp(0)},{_format_ass_timestamp(duration)},"
                f"{style_name},,0,0,0,,{ribbon_override}{body}"
            )

    override = "{" + _ass_pos_tag(overlay.x, overlay.y, width, height) + fade_tag + extra_tag + "}"
    dialogues.append(
        f"Dialogue: 0,{_format_ass_timestamp(0)},{_format_ass_timestamp(duration)},"
        f"{style_name},,0,0,0,,{override}{body}"
    )
    return style, dialogues


def _format_ass_timestamp(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    total_centis = round(seconds * 100)
    hours, rem = divmod(total_centis, 360_000)
    minutes, rem = divmod(rem, 6_000)
    secs, centis = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"
