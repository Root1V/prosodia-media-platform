"""Tests de GenerateMicroVideoUseCase usando fakes en memoria (mismo patron
que test_synthesize_text_use_case.py)."""

from __future__ import annotations

import re
from itertools import pairwise
from pathlib import Path

import pytest

from video_translator.application.use_cases.generate_micro_video import GenerateMicroVideoUseCase
from video_translator.domain.exceptions import InvalidVideoFileError, VideoTranslatorError
from video_translator.domain.models import (
    EmojiOverlay,
    GenerateMicroVideoRequest,
    MicroVideoMediaItem,
    TextOverlay,
)


class FakeMediaProcessor:
    """Solo implementa lo que GenerateMicroVideoUseCase necesita de
    MediaProcessor. get_duration_seconds devuelve una duracion fija por
    caracter para que el timing de los segmentos sea verificable."""

    def __init__(self, clip_durations: dict[str, float] | None = None):
        self.render_calls: list[dict] = []
        self.clip_render_calls: list[dict] = []
        self.caption_calls: list[dict] = []
        self.emoji_calls: list[dict] = []
        self.fit_calls: list[dict] = []
        self.music_calls: list[dict] = []
        self.music_range_calls: list[dict] = []
        self.volume_calls: list[dict] = []
        self.mux_calls: list[dict] = []
        self.concat_calls: list[dict] = []
        # Duracion "real" por NOMBRE de archivo, para los clips de video (ver
        # RM-36) -- los fragmentos de narracion siguen durando 1.0s fijo, que
        # es lo que hace deterministas los tests de timing preexistentes.
        self._clip_durations = clip_durations or {}

    def get_duration_seconds(self, media_path: Path) -> float:
        return self._clip_durations.get(media_path.name, 1.0)

    def extract_audio(self, video_path: Path, output_wav: Path) -> Path:
        raise NotImplementedError("no usado por GenerateMicroVideoUseCase")

    def extract_audio_clip(self, audio_path: Path, start: float, end: float, output_path: Path) -> Path:
        raise NotImplementedError("no usado por GenerateMicroVideoUseCase")

    def burn_subtitles(self, video_path: Path, srt_path: Path, output_path: Path) -> Path:
        raise NotImplementedError("no usado por GenerateMicroVideoUseCase")

    def attach_soft_subtitles(self, video_path: Path, srt_path: Path, output_path: Path, lang_code: str = "spa") -> Path:
        raise NotImplementedError("no usado por GenerateMicroVideoUseCase")

    def clean_music_track(self, input_path: Path, output_wav: Path) -> Path:
        raise NotImplementedError("no usado por GenerateMicroVideoUseCase")

    def extract_music_range(self, track_path: Path, start: float, end: float, output_path: Path) -> Path:
        self.music_range_calls.append({"track_path": track_path, "start": start, "end": end})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-music-range")
        return output_path

    def apply_volume(self, audio_path: Path, volume: float) -> None:
        self.volume_calls.append({"audio_path": audio_path, "volume": volume})

    def replace_audio_track(
        self, video_path: Path, new_audio_path: Path, output_path: Path, keep_original_as_secondary: bool = True
    ) -> Path:
        self.mux_calls.append(
            {
                "video_path": video_path,
                "new_audio_path": new_audio_path,
                "keep_original_as_secondary": keep_original_as_secondary,
            }
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-background-video")
        return output_path

    def render_image_video(
        self, image_path: Path, audio_path: Path | None, output_path: Path, duration_seconds: float,
        width: int = 1080, height: int = 1920,
        offset_x: float = 0.5, offset_y: float = 0.5, zoom: float = 1.0,
        filter_preset: str = "none",
    ) -> Path:
        self.render_calls.append(
            {
                "image_path": image_path,
                "audio_path": audio_path,
                "duration_seconds": duration_seconds,
                "width": width,
                "height": height,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "zoom": zoom,
                "filter_preset": filter_preset,
            }
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-segment-video")
        return output_path

    def render_clip_video(
        self, video_path: Path, output_path: Path, duration_seconds: float, start_seconds: float = 0.0,
        width: int = 1080, height: int = 1920,
        offset_x: float = 0.5, offset_y: float = 0.5, zoom: float = 1.0,
        filter_preset: str = "none",
    ) -> Path:
        self.clip_render_calls.append(
            {
                "video_path": video_path,
                "duration_seconds": duration_seconds,
                "start_seconds": start_seconds,
                "width": width,
                "height": height,
                "offset_x": offset_x,
                "offset_y": offset_y,
                "zoom": zoom,
                "filter_preset": filter_preset,
            }
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-clip-segment-video")
        return output_path

    def concatenate_videos(self, video_paths: list[Path], output_path: Path) -> Path:
        self.concat_calls.append({"video_paths": list(video_paths)})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-concatenated-video")
        return output_path

    def render_ass_captions(
        self, video_path: Path, ass_path: Path, output_path: Path, fonts_dir: Path | None = None
    ) -> Path:
        self.caption_calls.append({"video_path": video_path, "ass_path": ass_path, "fonts_dir": fonts_dir})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-final-video")
        return output_path

    def overlay_emojis(
        self,
        video_path: Path,
        placements: list[tuple[Path, float, float, float, bool]],
        output_path: Path,
        width: int,
        duration_seconds: float,
    ) -> Path:
        self.emoji_calls.append(
            {
                "video_path": video_path,
                "placements": placements,
                "width": width,
                "duration_seconds": duration_seconds,
            }
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-final-video-with-emojis")
        return output_path

    def fit_audio_to_duration(self, audio_path: Path, target_seconds: float) -> bool:
        self.fit_calls.append({"audio_path": audio_path, "target_seconds": target_seconds})
        return True

    def mix_background_music(
        self, narration_path: Path, music_path: Path, output_path: Path,
        duration_seconds: float, music_volume: float = 0.12,
    ) -> Path:
        self.music_calls.append(
            {
                "narration_path": narration_path,
                "music_path": music_path,
                "duration_seconds": duration_seconds,
                "music_volume": music_volume,
            }
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-mixed-audio")
        return output_path


class FakeSpeechSynthesizer:
    def __init__(self):
        self.calls: list[dict] = []
        self.concatenated: list[tuple] = []

    def synthesize_segment(self, text, output_path, target_duration_seconds, speaker_reference_wav=None, language="es"):
        self.calls.append({"text": text, "speaker_reference_wav": speaker_reference_wav, "language": language})
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-wav")
        return output_path

    def concatenate_segments(self, segment_audio_paths, total_duration, output_path):
        self.concatenated.append((list(segment_audio_paths), total_duration))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-narration-wav")
        return output_path


DEFAULT_VOICE = Path("/fake/default_voice.wav")


def _make_use_case(media=None, synthesizer=None, max_chunk_chars=500):
    return GenerateMicroVideoUseCase(
        speech_synthesizer=synthesizer or FakeSpeechSynthesizer(),
        media_processor=media or FakeMediaProcessor(),
        default_speaker_reference_wav=DEFAULT_VOICE,
        max_chunk_chars=max_chunk_chars,
    )


def _make_image(tmp_path: Path) -> Path:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    return image_path


def _make_clip(tmp_path: Path, name: str = "clip.mp4") -> Path:
    clip_path = tmp_path / name
    clip_path.write_bytes(b"fake-clip-bytes")
    return clip_path


_DIALOGUE_RE = re.compile(
    r"^Dialogue: \d+,(?P<start>[\d:.]+),(?P<end>[\d:.]+),Default,,0,0,0,,(?P<text>.*)$"
)


def _ass_timestamp_to_seconds(value: str) -> float:
    hours, minutes, rest = value.split(":")
    secs, centis = rest.split(".")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs) + int(centis) / 100


_LEADING_OVERRIDE_TAG_RE = re.compile(r"^\{[^}]*\}")


def _read_ass_dialogues(ass_path: Path) -> list[tuple[float, float, str]]:
    dialogues = []
    for line in ass_path.read_text(encoding="utf-8").splitlines():
        match = _DIALOGUE_RE.match(line)
        if match:
            # Todo caption ahora arranca con un override tag "{\pos(x,y)}"
            # (ver _ass_pos_tag) -- se descarta para estos tests, que
            # verifican el TEXTO/timing de los captions, no su posicion.
            text = _LEADING_OVERRIDE_TAG_RE.sub("", match.group("text"))
            dialogues.append(
                (
                    _ass_timestamp_to_seconds(match.group("start")),
                    _ass_timestamp_to_seconds(match.group("end")),
                    text,
                )
            )
    return dialogues


def test_execute_produces_video_using_default_voice(tmp_path: Path):
    media = FakeMediaProcessor()
    synthesizer = FakeSpeechSynthesizer()
    use_case = _make_use_case(media=media, synthesizer=synthesizer)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola mundo.", output_dir=tmp_path / "out")

    result = use_case.execute(request)

    assert result.output_video == tmp_path / "out" / "micro_video.mp4"
    assert result.output_video.exists()
    assert synthesizer.calls[0]["speaker_reference_wav"] == DEFAULT_VOICE
    assert media.render_calls[0]["image_path"] == image_path
    # render_ass_captions debe recibir el video de fondo que produjo render_image_video.
    assert media.caption_calls[0]["video_path"].name == "background.mp4"


def test_execute_uses_own_speaker_reference_when_provided(tmp_path: Path):
    synthesizer = FakeSpeechSynthesizer()
    use_case = _make_use_case(synthesizer=synthesizer)
    image_path = _make_image(tmp_path)
    own_voice = tmp_path / "my_voice.wav"
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola mundo.", output_dir=tmp_path / "out", speaker_reference_wav=own_voice
    )

    use_case.execute(request)

    assert synthesizer.calls[0]["speaker_reference_wav"] == own_voice


def test_execute_writes_ass_captions_with_video_resolution(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    ass_path = media.caption_calls[0]["ass_path"]
    content = ass_path.read_text(encoding="utf-8")
    # PlayResX/PlayResY deben coincidir con el video real -- sin esto libass
    # reescala el font (bug original: el texto cubria toda la pantalla).
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content


def test_execute_writes_captions_matching_narration_chunks(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media, max_chunk_chars=20)
    image_path = _make_image(tmp_path)
    long_text = "Primera oracion corta. Segunda oracion tambien corta. Tercera oracion mas."
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text=long_text, output_dir=tmp_path / "out")

    use_case.execute(request)

    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    assert len(dialogues) > 1
    # Los segmentos de captions no deben solaparse ni dejar huecos (cada uno
    # dura 1.0s segun FakeMediaProcessor).
    for i, (start, end, _text) in enumerate(dialogues):
        assert start == pytest.approx(float(i), abs=0.01)
        assert end == pytest.approx(float(i) + 1.0, abs=0.01)


def test_execute_splits_a_single_narration_chunk_into_several_short_captions(tmp_path: Path):
    # max_chunk_chars grande -> todo el texto entra en UN solo fragmento de
    # TTS (una sola llamada al sintetizador), pero el texto es mas largo que
    # CAPTION_MAX_CHARS: debe verse igual dividido en varios captions cortos,
    # no como un unico cartel con todo el texto durante los 3s enteros.
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media, max_chunk_chars=500)
    image_path = _make_image(tmp_path)
    long_text = (
        "Esta es una oracion bastante larga que deberia partirse en varios "
        "captions cortos en vez de mostrarse entera de una sola vez."
    )
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text=long_text, output_dir=tmp_path / "out")

    use_case.execute(request)

    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    assert len(dialogues) > 1
    for _start, _end, text in dialogues:
        assert len(text) <= 50
    # Deben cubrir en fila la duracion total del fragmento de TTS (1.0s segun
    # FakeMediaProcessor), sin solaparse ni dejar huecos.
    assert dialogues[0][0] == pytest.approx(0.0, abs=0.01)
    assert dialogues[-1][1] == pytest.approx(1.0, abs=0.01)
    for prev, nxt in pairwise(dialogues):
        assert prev[1] == pytest.approx(nxt[0], abs=0.01)


def test_execute_does_not_mix_music_by_default(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    assert media.music_calls == []
    # render_image_video renderiza MUDO (audio_path=None) -- el audio se
    # mezcla despues, sobre el video ya concatenado, via replace_audio_track.
    assert media.render_calls[0]["audio_path"] is None
    assert media.mux_calls[0]["new_audio_path"].name == "narration.wav"


def test_execute_mixes_background_music_when_requested(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"fake-music-bytes")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,
        background_music_path=music_path,
    )

    use_case.execute(request)

    assert len(media.music_calls) == 1
    assert media.music_calls[0]["music_path"] == music_path
    assert media.music_calls[0]["narration_path"].name == "narration.wav"
    # Se mezcla usando la duracion FINAL del video (la fija elegida), no la
    # duracion cruda de la narracion.
    assert media.music_calls[0]["duration_seconds"] == pytest.approx(5.0)
    # render_image_video renderiza MUDO -- el audio YA MEZCLADO se mezcla
    # despues via replace_audio_track, no la narracion sola.
    assert media.render_calls[0]["audio_path"] is None
    assert media.mux_calls[0]["new_audio_path"].name == "narration_with_music.wav"


def test_execute_renders_at_vertical_resolution(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    assert media.render_calls[0]["width"] == 1080
    assert media.render_calls[0]["height"] == 1920


def test_execute_uses_default_frame_when_image_has_no_adjustment(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    assert media.render_calls[0]["offset_x"] == 0.5
    assert media.render_calls[0]["offset_y"] == 0.5
    assert media.render_calls[0]["zoom"] == 1.0
    assert media.render_calls[0]["filter_preset"] == "none"


def test_execute_passes_each_image_own_filter_preset(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_paths = _make_images(tmp_path, 2)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=image_paths[0], filter_preset="sepia"),
            MicroVideoMediaItem(path=image_paths[1], filter_preset="dramatic"),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    assert media.render_calls[0]["filter_preset"] == "sepia"
    assert media.render_calls[1]["filter_preset"] == "dramatic"


def test_execute_passes_each_image_own_offset_and_zoom(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_paths = _make_images(tmp_path, 2)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=image_paths[0], offset_x=0.2, offset_y=0.8, zoom=1.5),
            MicroVideoMediaItem(path=image_paths[1], offset_x=0.9, offset_y=0.1, zoom=2.0),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    assert media.render_calls[0]["offset_x"] == 0.2
    assert media.render_calls[0]["offset_y"] == 0.8
    assert media.render_calls[0]["zoom"] == 1.5
    assert media.render_calls[1]["offset_x"] == 0.9
    assert media.render_calls[1]["offset_y"] == 0.1
    assert media.render_calls[1]["zoom"] == 2.0


def test_execute_rejects_zoom_below_one(tmp_path: Path):
    use_case = _make_use_case()
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path, zoom=0.5)], text="Hola.", output_dir=tmp_path / "out"
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_strips_bold_markers_from_narration_but_keeps_them_for_captions(tmp_path: Path):
    media = FakeMediaProcessor()
    synthesizer = FakeSpeechSynthesizer()
    use_case = _make_use_case(media=media, synthesizer=synthesizer)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Esto **es lo mejor** de la industria.", output_dir=tmp_path / "out"
    )

    use_case.execute(request)

    # El sintetizador no debe recibir los asteriscos (no se los debe "leer").
    assert "**" not in synthesizer.calls[0]["text"]
    assert "es lo mejor" in synthesizer.calls[0]["text"]
    # El caption si debe convertir el texto resaltado a negrita ASS.
    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    full_caption_text = " ".join(text for _s, _e, text in dialogues)
    assert r"{\b1}es lo mejor{\b0}" in full_caption_text
    assert "**" not in full_caption_text


def test_execute_writes_chosen_caption_background_color(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", caption_bg_color="#FF0000"
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    # "#FF0000" (rojo) en ASS es BGR, opaco: &H000000FF.
    assert "&H000000FF" in content
    # Estilo "background" (default): sin pasar caption_highlight_style, debe
    # quedar el texto blanco y BorderStyle=3 (caja).
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    assert style_line.split(",")[3] == "&H00FFFFFF"  # PrimaryColour blanco
    assert style_line.split(",")[15] == "3"  # BorderStyle


def test_execute_writes_chosen_caption_text_color_for_background_style(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        caption_bg_color="#FF0000",
        caption_text_color="#0000FF",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # "#0000FF" (azul) en ASS es BGR, opaco: &H00FF0000 -- PrimaryColour (el
    # texto) ya no queda fijo en blanco, y la caja sigue siendo la elegida
    # por separado en caption_bg_color ("#FF0000" -> &H000000FF).
    assert fields[3] == "&H00FF0000"
    assert fields[5] == "&H000000FF"
    assert fields[15] == "3"  # BorderStyle=3 (caja)


def test_execute_writes_text_color_highlight_style_without_a_box(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="text_color",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # "#00FF00" (verde) en ASS es BGR, opaco: &H0000FF00 -- ahora en
    # PrimaryColour (el texto), no en BackColour/OutlineColour.
    assert fields[3] == "&H0000FF00"
    assert fields[15] == "1"  # BorderStyle=1 (sin caja, solo contorno)


def test_execute_writes_karaoke_highlight_style_fixed_white_primary_colour(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="karaoke",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # El color elegido NO va en la linea de Style (va inline por palabra) --
    # PrimaryColour queda fijo en blanco, sin caja.
    assert fields[3] == "&H00FFFFFF"
    assert fields[15] == "1"  # BorderStyle=1 (sin caja, solo contorno)


def test_execute_writes_one_karaoke_dialogue_per_word(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Uno dos tres.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="karaoke",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    # "Uno dos tres." -- 3 palabras, un Dialogue por palabra (no uno por caption).
    assert len(dialogue_lines) == 3
    # "#00FF00" (verde) inline, sin byte de alpha: &H00FF00&.
    for line in dialogue_lines:
        assert line.count("{\\c&H00FF00&}") == 1
        assert line.count("{\\c}") == 1
    # Cada Dialogue cubre una ventana de tiempo distinta y en orden.
    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    starts = [start for start, _end, _text in dialogues]
    assert starts == sorted(starts)
    assert starts[0] == pytest.approx(0.0, abs=0.01)


def test_execute_writes_karaoke_background_style_fixed_white_primary_colour(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="karaoke_background",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # El color elegido NO va en la linea de Style (va inline por palabra) --
    # PrimaryColour queda fijo en blanco. OutlineColour (la "caja" en
    # BorderStyle=3, ver _build_caption_style) arranca totalmente
    # transparente para que las palabras sin resaltar no muestren caja.
    assert fields[3] == "&H00FFFFFF"
    assert fields[5] == "&HFF000000"
    assert fields[15] == "3"  # BorderStyle=3 (caja, no contorno)


def test_execute_writes_one_karaoke_background_dialogue_per_word(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Uno dos tres.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="karaoke_background",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    # "Uno dos tres." -- 3 palabras, un Dialogue por palabra (no uno por caption).
    assert len(dialogue_lines) == 3
    # La palabra activa prende la caja (\3c + \3a&H00&, opaca) y la vuelve a
    # apagar despues (\3a&HFF&, transparente) -- nunca cambia \c (color de texto).
    for line in dialogue_lines:
        assert line.count("{\\3c&H00FF00&\\3a&H00&}") == 1
        assert line.count("{\\3a&HFF&}") == 1
        assert "\\c" not in line
    # Cada Dialogue cubre una ventana de tiempo distinta y en orden.
    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    starts = [start for start, _end, _text in dialogues]
    assert starts == sorted(starts)
    assert starts[0] == pytest.approx(0.0, abs=0.01)


def test_execute_writes_chosen_caption_text_color_for_karaoke_background_style(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Uno dos.",
        output_dir=tmp_path / "out",
        caption_bg_color="#00FF00",
        caption_highlight_style="karaoke_background",
        caption_text_color="#0000FF",
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style:"))
    fields = style_line.split(",")
    # "#0000FF" (azul) en ASS es BGR, opaco: &H00FF0000 -- PrimaryColour (el
    # texto, todas las palabras, activa o no) ya no queda fijo en blanco. La
    # caja de resaltado sigue siendo caption_bg_color por separado, y arranca
    # transparente en la Style (ver test_..._fixed_white_primary_colour).
    assert fields[3] == "&H00FF0000"
    dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    for line in dialogue_lines:
        assert line.count("{\\3c&H00FF00&\\3a&H00&}") == 1
        assert "\\c" not in line


def test_execute_holds_the_image_when_narration_is_shorter_than_target_duration(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)  # cada fragmento dura 1.0s (FakeMediaProcessor)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", target_duration_seconds=10.0
    )

    result = use_case.execute(request)

    # El video dura la duracion elegida (10s), no se acelera el audio (mas
    # corto que su hueco -- se mantiene la imagen el resto del tiempo).
    assert result.duration_seconds == pytest.approx(10.0)
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(10.0)
    assert media.fit_calls == []


def test_execute_speeds_up_narration_when_longer_than_target_duration(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media, max_chunk_chars=20)  # fuerza varios fragmentos de 1.0s c/u
    image_path = _make_image(tmp_path)
    long_text = "Primera oracion corta. Segunda oracion tambien corta. Tercera oracion mas."
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text=long_text, output_dir=tmp_path / "out", target_duration_seconds=1.5
    )

    result = use_case.execute(request)

    assert len(media.fit_calls) == 1
    assert media.fit_calls[0]["target_seconds"] == pytest.approx(1.5)
    assert result.duration_seconds == pytest.approx(1.5)
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(1.5)
    # Los captions deben quedar reescalados dentro de la duracion final, no
    # seguir apuntando a los timestamps originales (mas largos).
    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    assert dialogues[-1][1] <= 1.5 + 0.05


def test_execute_rejects_empty_text(tmp_path: Path):
    use_case = _make_use_case()
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="   ", output_dir=tmp_path / "out")

    with pytest.raises(VideoTranslatorError):
        use_case.execute(request)


def test_execute_rejects_missing_image(tmp_path: Path):
    use_case = _make_use_case()
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=tmp_path / "does_not_exist.jpg")], text="Hola.", output_dir=tmp_path / "out"
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_rejects_unsupported_media_extension(tmp_path: Path):
    use_case = _make_use_case()
    bad_file = tmp_path / "photo.gif"
    bad_file.write_bytes(b"not-a-supported-format")
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=bad_file)], text="Hola.", output_dir=tmp_path / "out")

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_without_overlays_adds_no_overlay_style_or_dialogue(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    assert "Overlay0" not in content


def test_execute_without_emoji_overlays_does_not_call_overlay_emojis(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    result = use_case.execute(request)

    # Sin emojis, no se gasta un paso de ffmpeg de mas -- el video final es
    # el que ya produjo caption_burn directamente.
    assert media.emoji_calls == []
    assert result.output_video.exists()


def test_execute_passes_resolved_emoji_placements(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    emoji = EmojiOverlay(emoji_id="fuego", x=0.25, y=0.75, size=0.2, fade=True)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        emoji_overlays=[emoji],
    )

    result = use_case.execute(request)

    assert len(media.emoji_calls) == 1
    placements = media.emoji_calls[0]["placements"]
    assert len(placements) == 1
    asset_path, x, y, size, fade = placements[0]
    assert asset_path.name == "fuego.png"
    assert asset_path.is_file()
    assert (x, y, size, fade) == (0.25, 0.75, 0.2, True)
    assert media.emoji_calls[0]["width"] == 1080
    # El video final con emojis lo produce overlay_emojis, no caption_burn
    # directamente.
    assert result.output_video.read_bytes() == b"fake-final-video-with-emojis"


def test_execute_omits_unrecognized_emoji_id(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    emoji = EmojiOverlay(emoji_id="no-existe-este-emoji", x=0.5, y=0.5)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        emoji_overlays=[emoji],
    )

    result = use_case.execute(request)

    # Un id no reconocido no rompe la generacion -- simplemente se omite
    # esa capa (mismo criterio que filter_preset/caption_highlight_style).
    assert media.emoji_calls[0]["placements"] == []
    assert result.output_video.exists()


def test_execute_writes_overlay_position_bold_color_and_font(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(
        text="Hola mundo",
        x=0.25,
        y=0.5,
        bold=True,
        font_family="Impact",
        font_size=64,
        color="#00FF00",
    )
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        text_overlays=[overlay],
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    # Style: negrita (-1), tipografia y tamano elegidos.
    style_line = next(line for line in content.splitlines() if line.startswith("Style: Overlay0"))
    fields = style_line.split(",")
    assert fields[1] == "Impact"
    assert fields[2] == "64"
    assert fields[7] == "-1"  # Bold
    # x=0.25*1080=270, y=0.5*1920=960 (formato vertical, ver VIDEO_FORMATS).
    dialogue_line = next(line for line in content.splitlines() if line.startswith("Dialogue: 0,0:00:00.00"))
    assert "\\pos(270,960)" in dialogue_line
    assert "Hola mundo" in dialogue_line
    assert "\\fad(" not in dialogue_line


def test_execute_writes_default_outline_and_shadow_for_flat_style(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Hola", x=0.5, y=0.5)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    style_line = next(line for line in content.splitlines() if line.startswith("Style: Overlay0"))
    fields = style_line.split(",")
    assert fields[16] == "3"  # Outline
    assert fields[17] == "1"  # Shadow


def test_execute_writes_hard_shadow_and_thick_outline_styles(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlays = [
        TextOverlay(text="Sombra", x=0.5, y=0.3, text_style="hard_shadow"),
        TextOverlay(text="Contorno", x=0.5, y=0.6, text_style="thick_outline"),
    ]
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=overlays
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    shadow_fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    outline_fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay1")).split(",")
    assert (shadow_fields[16], shadow_fields[17]) == ("2", "8")
    assert (outline_fields[16], outline_fields[17]) == ("10", "1")


def test_execute_writes_long_shadow_style(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Largo", x=0.5, y=0.5, text_style="long_shadow")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    # Shadow=0: el tag `Shadow` nativo de ASS es una UNICA copia solida
    # desplazada (probado a mano con texto real: se ve como un duplicado
    # "flotando" al lado, no como una sombra) -- la cinta diagonal se arma
    # a mano con copias `Dialogue:` (ver abajo), no con este tag.
    assert (fields[16], fields[17]) == ("1", "0")

    overlay_dialogues = [
        line for line in content.splitlines() if line.startswith("Dialogue: 0,0:00:00.00") and ",Overlay0," in line
    ]
    # _LONG_SHADOW_STEPS copias solidas en negro desplazadas diagonalmente
    # + la copia de color normal encima, al final.
    assert len(overlay_dialogues) == 19
    ribbon_lines, main_line = overlay_dialogues[:-1], overlay_dialogues[-1]
    assert all("\\1c&H000000&\\bord0\\shad0" in line for line in ribbon_lines)
    # x=0.5*1080=540, y=0.5*1920=960 (formato vertical, ver VIDEO_FORMATS en
    # _make_use_case) -- offsets diagonales decrecientes: la primera copia
    # (mas lejos) es +18,+18, la ultima del ribbon (mas cerca) es +1,+1.
    assert "\\pos(558,978)" in ribbon_lines[0]
    assert "\\pos(541,961)" in ribbon_lines[-1]
    # La copia final (encima de la cinta) usa la posicion real del overlay,
    # sin forzar el color a negro.
    assert "\\pos(540,960)" in main_line
    assert "\\1c&H000000&" not in main_line


def test_execute_writes_hollow_style_with_transparent_fill(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Hollow", x=0.5, y=0.5, text_style="hollow", color="#00FF00")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    # PrimaryColour totalmente transparente (sin relleno real)...
    assert fields[3] == "&HFF000000"
    # ... y el color elegido por el usuario pasa al OutlineColour (verde, BGR &H0000FF00&... con alpha "00").
    assert fields[5] == "&H0000FF00"
    assert (fields[16], fields[17]) == ("6", "0")


def test_execute_writes_neon_glow_style_with_blur_and_accent_outline(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(
        text="Neon", x=0.5, y=0.5, text_style="neon_glow", color="#FFFFFF", accent_color="#FF00FF"
    )
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    assert fields[5] == "&H00FF00FF"  # OutlineColour = accent_color (magenta, BGR)
    assert (fields[16], fields[17]) == ("4", "0")
    dialogue_line = next(line for line in content.splitlines() if line.startswith("Dialogue: 0,0:00:00.00"))
    assert "\\blur6" in dialogue_line


def test_execute_writes_colored_outline_style(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(
        text="Outline", x=0.5, y=0.5, text_style="colored_outline", color="#FFFFFF", accent_color="#00CCFF"
    )
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    assert fields[3] == "&H00FFFFFF"  # PrimaryColour = color (fill blanco, opaco)
    assert fields[5] == "&H00FFCC00"  # OutlineColour = accent_color (BGR de #00CCFF)
    assert (fields[16], fields[17]) == ("6", "1")


def test_execute_passes_fonts_dir_to_render_ass_captions(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    fonts_dir = media.caption_calls[0]["fonts_dir"]
    assert fonts_dir is not None
    assert fonts_dir.name == "fonts"
    assert fonts_dir.is_dir()


def test_execute_writes_unrecognized_text_style_as_flat(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Hola", x=0.5, y=0.5, text_style="no-existe-este-estilo")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    fields = next(line for line in content.splitlines() if line.startswith("Style: Overlay0")).split(",")
    assert (fields[16], fields[17]) == ("3", "1")


def test_execute_writes_gradient_colors_per_character(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(
        text="AB", x=0.5, y=0.5, text_style="gradient", color="#FF0000", accent_color="#0000FF"
    )
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_line = next(line for line in content.splitlines() if line.startswith("Dialogue: 0,0:00:00.00"))
    # "A" -> color de arranque (rojo, BGR &H0000FF&), "B" -> color final (azul, BGR &HFF0000&).
    assert "{\\1c&H0000FF&}A" in dialogue_line
    assert "{\\1c&HFF0000&}B" in dialogue_line


def test_execute_preserves_line_break_in_gradient_text(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(
        text="A\nB", x=0.5, y=0.5, text_style="gradient", color="#FF0000", accent_color="#0000FF"
    )
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", text_overlays=[overlay]
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_line = next(line for line in content.splitlines() if line.startswith("Dialogue: 0,0:00:00.00"))
    # Si "\N" se partiera en "\\" y "N" coloreados por separado, este
    # substring literal ya no aparecería intacto en la linea.
    assert "\\N" in dialogue_line


def test_execute_writes_overlay_fade_when_requested(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Con fade", x=0.5, y=0.1, fade=True)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,  # suficientemente largo para no clampear el fade de 500ms
        text_overlays=[overlay],
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_line = next(line for line in content.splitlines() if "Con fade" in line)
    assert "\\fad(500,500)" in dialogue_line


def test_execute_clamps_overlay_fade_duration_for_short_videos(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    # FakeMediaProcessor.get_duration_seconds -> 1.0s de narracion (un solo
    # chunk): sin clamp, un fade de 500ms in + 500ms out excederia el video.
    overlay = TextOverlay(text="Corto", x=0.5, y=0.1, fade=True)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        text_overlays=[overlay],
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    dialogue_line = next(line for line in content.splitlines() if "Corto" in line)
    assert "\\fad(250,250)" in dialogue_line


def test_execute_escapes_overlay_braces_and_preserves_line_breaks(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    overlay = TextOverlay(text="Linea 1\nLinea {2}", x=0.5, y=0.5)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        text_overlays=[overlay],
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    assert "Linea 1\\NLinea 2" in content
    assert "{2}" not in content


def test_execute_does_not_extract_music_range_when_using_full_track(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"fake-music-bytes")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,
        background_music_path=music_path,
    )

    use_case.execute(request)

    assert media.music_range_calls == []
    assert media.music_calls[0]["music_path"] == music_path


def test_execute_extracts_music_range_before_mixing_when_requested(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"fake-music-bytes")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,
        background_music_path=music_path,
        background_music_start=10.0,
        background_music_end=20.0,
    )

    use_case.execute(request)

    assert len(media.music_range_calls) == 1
    assert media.music_range_calls[0]["track_path"] == music_path
    assert media.music_range_calls[0]["start"] == pytest.approx(10.0)
    assert media.music_range_calls[0]["end"] == pytest.approx(20.0)
    # mix_background_music debe recibir el RECORTE, no la pista original.
    assert media.music_calls[0]["music_path"] != music_path
    assert media.music_calls[0]["music_path"].name == "background_music_range.wav"


def test_execute_does_not_apply_narration_volume_by_default(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    assert media.volume_calls == []


def test_execute_applies_narration_volume_when_requested(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", narration_volume=0.5
    )

    use_case.execute(request)

    assert len(media.volume_calls) == 1
    assert media.volume_calls[0]["audio_path"].name == "narration.wav"
    assert media.volume_calls[0]["volume"] == pytest.approx(0.5)


def test_execute_applies_narration_volume_even_without_background_music(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", narration_volume=1.5
    )

    use_case.execute(request)

    assert media.music_calls == []
    assert len(media.volume_calls) == 1
    assert media.volume_calls[0]["volume"] == pytest.approx(1.5)


def test_execute_passes_background_music_volume_to_mix(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"fake-music-bytes")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        background_music_path=music_path,
        background_music_volume=0.3,
    )

    use_case.execute(request)

    assert media.music_calls[0]["music_volume"] == pytest.approx(0.3)


def test_execute_writes_captions_at_default_position(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    # default caption_x=0.5, caption_y=0.85 sobre 1080x1920.
    assert "\\pos(540,1632)" in content


def test_execute_writes_captions_at_custom_position(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out", caption_x=0.25, caption_y=0.5
    )

    use_case.execute(request)

    content = media.caption_calls[0]["ass_path"].read_text(encoding="utf-8")
    assert "\\pos(270,960)" in content


def _make_images(tmp_path: Path, n: int) -> list[Path]:
    paths = []
    for i in range(n):
        p = tmp_path / f"photo_{i}.jpg"
        p.write_bytes(b"fake-image-bytes")
        paths.append(p)
    return paths


def test_execute_single_image_renders_one_silent_segment_and_skips_concat(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(media_items=[MicroVideoMediaItem(path=image_path)], text="Hola.", output_dir=tmp_path / "out")

    use_case.execute(request)

    assert len(media.render_calls) == 1
    assert media.render_calls[0]["image_path"] == image_path
    assert media.render_calls[0]["audio_path"] is None
    assert media.concat_calls == []  # atajo: una sola imagen no necesita concatenar
    assert media.mux_calls[0]["video_path"].name == "segment_000.mp4"


def test_execute_splits_duration_equally_across_multiple_images(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_paths = _make_images(tmp_path, 2)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=p) for p in image_paths],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    assert len(media.render_calls) == 2
    assert media.render_calls[0]["image_path"] == image_paths[0]
    assert media.render_calls[1]["image_path"] == image_paths[1]
    for call in media.render_calls:
        assert call["audio_path"] is None
        assert call["duration_seconds"] == pytest.approx(5.0)  # 10s / 2 imagenes


def test_execute_concatenates_segments_in_order_for_multiple_images(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_paths = _make_images(tmp_path, 3)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=p) for p in image_paths],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=9.0,
    )

    use_case.execute(request)

    assert len(media.concat_calls) == 1
    concatenated = media.concat_calls[0]["video_paths"]
    assert [p.name for p in concatenated] == ["segment_000.mp4", "segment_001.mp4", "segment_002.mp4"]
    # El audio final se mezcla sobre el video YA CONCATENADO, no sobre un segmento suelto.
    assert media.mux_calls[0]["video_path"].name == "background_silent.mp4"


def test_execute_rejects_empty_image_list(tmp_path: Path):
    use_case = _make_use_case()
    request = GenerateMicroVideoRequest(media_items=[], text="Hola.", output_dir=tmp_path / "out")

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


# --- RM-36: clips de video como items del micro-video -----------------------


def test_execute_renders_a_video_clip_with_its_own_duration(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 4.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path), MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    assert len(media.clip_render_calls) == 1
    assert media.clip_render_calls[0]["duration_seconds"] == pytest.approx(4.0)
    assert len(media.render_calls) == 1
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(6.0)


def test_execute_splits_only_the_remaining_time_among_images(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 4.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_paths = _make_images(tmp_path, 2)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=clip_path),
            MicroVideoMediaItem(path=image_paths[0]),
            MicroVideoMediaItem(path=image_paths[1]),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    assert len(media.render_calls) == 2
    for call in media.render_calls:
        assert call["duration_seconds"] == pytest.approx(3.0)  # (10 - 4) / 2


def test_execute_uses_the_trimmed_clip_duration_for_the_split(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 10.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=clip_path, keep_ranges=[(2.0, 5.0)]),
            MicroVideoMediaItem(path=image_path),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    assert media.clip_render_calls[0]["duration_seconds"] == pytest.approx(3.0)
    assert media.clip_render_calls[0]["start_seconds"] == pytest.approx(2.0)
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(7.0)  # 10 - 3


def test_execute_clamps_clip_end_to_the_real_clip_duration(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 3.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, 99.0)]),
            MicroVideoMediaItem(path=image_path),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    assert media.clip_render_calls[0]["duration_seconds"] == pytest.approx(3.0)


def test_execute_extends_the_video_when_clips_exceed_the_target_duration(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 12.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path), MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,
    )

    result = use_case.execute(request)

    # La imagen cae al piso (MIN_IMAGE_SEGMENT_SECONDS=1.0), el video se
    # extiende para no recortar el clip.
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(1.0)
    assert result.duration_seconds == pytest.approx(13.0)


def test_execute_extending_the_video_propagates_to_music_and_captions(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 12.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    image_path = _make_image(tmp_path)
    music_path = tmp_path / "track.mp3"
    music_path.write_bytes(b"fake-music-bytes")
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path), MicroVideoMediaItem(path=image_path)],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=5.0,
        background_music_path=music_path,
    )

    use_case.execute(request)

    assert media.music_calls[0]["duration_seconds"] == pytest.approx(13.0)
    dialogues = _read_ass_dialogues(media.caption_calls[0]["ass_path"])
    assert dialogues[-1][1] <= 13.0 + 0.05


def test_execute_with_only_clips_renders_no_image_segments(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip_0.mp4": 4.0, "clip_1.mp4": 6.0})
    use_case = _make_use_case(media=media)
    clip_paths = [_make_clip(tmp_path, "clip_0.mp4"), _make_clip(tmp_path, "clip_1.mp4")]
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=p) for p in clip_paths],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    result = use_case.execute(request)

    assert media.render_calls == []
    assert len(media.clip_render_calls) == 2
    assert result.duration_seconds == pytest.approx(10.0)


def test_execute_concatenates_mixed_image_and_clip_segments_in_order(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 3.0})
    use_case = _make_use_case(media=media)
    image_paths = _make_images(tmp_path, 2)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(path=image_paths[0]),
            MicroVideoMediaItem(path=clip_path),
            MicroVideoMediaItem(path=image_paths[1]),
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=9.0,
    )

    use_case.execute(request)

    concatenated = media.concat_calls[0]["video_paths"]
    assert [p.name for p in concatenated] == ["segment_000.mp4", "segment_001.mp4", "segment_002.mp4"]
    assert len(media.render_calls) == 2  # indices 0 y 2
    assert len(media.clip_render_calls) == 1  # indice 1


def test_execute_passes_clip_framing_and_filter_preset(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 4.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[
            MicroVideoMediaItem(
                path=clip_path, offset_x=0.2, offset_y=0.8, zoom=1.5, filter_preset="sepia"
            )
        ],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    call = media.clip_render_calls[0]
    assert call["offset_x"] == 0.2
    assert call["offset_y"] == 0.8
    assert call["zoom"] == 1.5
    assert call["filter_preset"] == "sepia"


def test_execute_rejects_clip_end_not_after_clip_start(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(5.0, 5.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_rejects_negative_clip_start(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(-1.0, 5.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_ignores_trim_set_on_an_image_item(tmp_path: Path):
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    image_path = _make_image(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=image_path, keep_ranges=[(2.0, 3.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
        target_duration_seconds=10.0,
    )

    use_case.execute(request)

    # Sin clips de video, el reparto es el de siempre -- el recorte en un
    # item de imagen se ignora silenciosamente.
    assert media.render_calls[0]["duration_seconds"] == pytest.approx(10.0)


# --- RM-40: cortar y eliminar varios tramos sueltos de un clip --------------


def test_execute_sums_duration_across_multiple_kept_ranges(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 10.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, 2.0), (5.0, 8.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    result = use_case.execute(request)

    # (2-0) + (8-5) = 5s -- el hueco [2,5) quedo afuera de la duracion total.
    assert result.duration_seconds == pytest.approx(5.0)


def test_execute_renders_multiple_kept_ranges_as_separate_sub_segments_then_concats(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 10.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, 2.0), (5.0, 8.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    # Cada rango conservado se renderiza como su propio sub-segmento...
    assert len(media.clip_render_calls) == 2
    assert media.clip_render_calls[0]["start_seconds"] == pytest.approx(0.0)
    assert media.clip_render_calls[0]["duration_seconds"] == pytest.approx(2.0)
    assert media.clip_render_calls[1]["start_seconds"] == pytest.approx(5.0)
    assert media.clip_render_calls[1]["duration_seconds"] == pytest.approx(3.0)
    # ...y se concatenan entre si en un unico segmento para ese item, ANTES
    # del (inexistente aca, porque es el unico item) concat general.
    assert len(media.concat_calls) == 1
    sub_concat_names = [p.name for p in media.concat_calls[0]["video_paths"]]
    assert sub_concat_names == ["segment_000_part00.mp4", "segment_000_part01.mp4"]


def test_execute_single_kept_range_does_not_trigger_a_sub_concat(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 10.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(1.0, 4.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    assert len(media.clip_render_calls) == 1
    assert media.concat_calls == []


def test_execute_rejects_empty_keep_ranges_list(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_rejects_overlapping_keep_ranges(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, 5.0), (3.0, 8.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_rejects_non_ascending_keep_ranges(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(5.0, 8.0), (0.0, 2.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_rejects_open_end_not_on_last_range(tmp_path: Path):
    use_case = _make_use_case()
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, None), (5.0, 8.0)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    with pytest.raises(InvalidVideoFileError):
        use_case.execute(request)


def test_execute_allows_open_end_on_the_last_range(tmp_path: Path):
    media = FakeMediaProcessor(clip_durations={"clip.mp4": 10.0})
    use_case = _make_use_case(media=media)
    clip_path = _make_clip(tmp_path)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=clip_path, keep_ranges=[(0.0, 2.0), (5.0, None)])],
        text="Hola.",
        output_dir=tmp_path / "out",
    )

    result = use_case.execute(request)

    # (2-0) + (10-5) = 7s -- el end=None del ultimo rango se resuelve
    # contra la duracion real del archivo (10s).
    assert result.duration_seconds == pytest.approx(7.0)


def test_execute_defaults_to_the_vertical_format(tmp_path: Path) -> None:
    # El default tiene que seguir siendo 9:16: es lo que el pipeline hacia
    # antes de RM-42 y lo que un proyecto reanudado sin la clave tiene que
    # producir. Si esto cambia, todos los micro-videos existentes cambian de
    # forma sin que nadie lo haya pedido.
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=_make_image(tmp_path))],
        text="Hola mundo.",
        output_dir=tmp_path / "out",
    )

    use_case.execute(request)

    assert (media.render_calls[0]["width"], media.render_calls[0]["height"]) == (1080, 1920)


def test_execute_square_format_changes_the_dimensions_given_to_the_processor(tmp_path: Path) -> None:
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=_make_image(tmp_path))],
        text="Hola mundo.",
        output_dir=tmp_path / "out",
        video_format="square",
    )

    use_case.execute(request)

    assert (media.render_calls[0]["width"], media.render_calls[0]["height"]) == (1080, 1080)


def test_execute_unknown_format_falls_back_to_vertical(tmp_path: Path) -> None:
    # El formato llega de `config`, que es JSON sin esquema -- un valor que no
    # esta en VIDEO_FORMATS no puede tirar la corrida entera.
    media = FakeMediaProcessor()
    use_case = _make_use_case(media=media)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=_make_image(tmp_path))],
        text="Hola mundo.",
        output_dir=tmp_path / "out",
        video_format="no-existe",
    )

    use_case.execute(request)

    assert (media.render_calls[0]["width"], media.render_calls[0]["height"]) == (1080, 1920)


# --- Reanudacion de la sintesis (RM-46) --------------------------------------
#
# text_to_speech se lleva el 93% de la corrida, asi que es la unica etapa que
# se reanuda. El riesgo no es no reusar: es reusar audio que ya no corresponde
# al texto, porque eso no falla -- genera un video que suena bien y dice otra
# cosa.


def _run(tmp_path: Path, text: str, *, resume: bool, synthesizer=None):
    synth = synthesizer or FakeSpeechSynthesizer()
    use_case = _make_use_case(synthesizer=synth)
    request = GenerateMicroVideoRequest(
        media_items=[MicroVideoMediaItem(path=_make_image(tmp_path))],
        text=text,
        output_dir=tmp_path / "out",
        resume=resume,
    )
    use_case.execute(request)
    return synth


def test_resume_reuses_already_synthesized_chunks(tmp_path: Path) -> None:
    primera = _run(tmp_path, "Hola mundo.", resume=False)
    assert len(primera.calls) == 1

    segunda = _run(tmp_path, "Hola mundo.", resume=True)

    assert segunda.calls == []  # no volvio a sintetizar nada


def test_resume_resynthesizes_when_the_text_changed(tmp_path: Path) -> None:
    # El caso peligroso. Si se reusara, el video narraria el texto viejo sin
    # que nada falle.
    _run(tmp_path, "Texto original.", resume=False)

    segunda = _run(tmp_path, "Texto corregido.", resume=True)

    assert len(segunda.calls) == 1
    assert segunda.calls[0]["text"] == "Texto corregido."


def test_without_resume_nothing_is_reused(tmp_path: Path) -> None:
    # Una corrida normal sintetiza todo: reusar audio sin que nadie lo pida
    # convierte un directorio de trabajo sucio en un resultado viejo.
    _run(tmp_path, "Hola mundo.", resume=False)

    segunda = _run(tmp_path, "Hola mundo.", resume=False)

    assert len(segunda.calls) == 1


def test_resume_ignores_an_empty_chunk_file(tmp_path: Path) -> None:
    # Un .wav de 0 bytes es justo lo que deja una corrida que murio mientras
    # escribia ese fragmento.
    _run(tmp_path, "Hola mundo.", resume=False)
    for wav in (tmp_path / "out").rglob("chunk_*.wav"):
        wav.write_bytes(b"")

    segunda = _run(tmp_path, "Hola mundo.", resume=True)

    assert len(segunda.calls) == 1


def test_resume_without_a_previous_run_synthesizes_everything(tmp_path: Path) -> None:
    primera = _run(tmp_path, "Hola mundo.", resume=True)

    assert len(primera.calls) == 1
