"""Tests de project_mapper: Project (fila de BD) -> TranslateVideoRequest/use case.

No requiere GPU/modelos reales: se mockea `build_translate_video_use_case`
(container.py) para verificar solo el mapeo de datos, que es la
responsabilidad real de este modulo.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy.orm import Session

from video_translator.domain.models import OutputMode
from video_translator.web.db.models import (
    MusicTrack,
    Project,
    ProjectStatus,
    ServiceType,
    SourceType,
)
from video_translator.web.services import project_mapper


def _make_project(tmp_path: Path, **config_overrides: object) -> Project:
    config = {
        "context_prompt": "Video de prueba",
        "tone": "formal",
        "glossary": {"foo": "bar"},
        "source_lang": "en",
        "target_lang": "es",
        "diarize": False,
        "min_speakers": None,
        "max_speakers": None,
        **config_overrides,
    }
    return Project(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Proyecto de prueba",
        service_type=ServiceType.DUBBING,
        source_type=SourceType.UPLOAD,
        input_video_path=str(tmp_path / "input.mp4"),
        output_dir=str(tmp_path / "output"),
        output_mode=OutputMode.DUBBED.value,
        config=config,
        status=ProjectStatus.QUEUED,
    )


def test_build_use_case_and_request_maps_fields(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = _make_project(tmp_path, diarize=True, min_speakers=2, max_speakers=3)

    fake_use_case = MagicMock()
    build_mock = MagicMock(return_value=fake_use_case)
    monkeypatch.setattr(project_mapper, "build_translate_video_use_case", build_mock)

    use_case, request = project_mapper.build_use_case_and_request(project)

    assert use_case is fake_use_case
    assert request.input_video == Path(project.input_video_path)
    assert request.output_dir == Path(project.output_dir)
    assert request.output_dir.is_dir()  # se crea, igual que hace cli.py
    assert request.output_mode == OutputMode.DUBBED
    assert request.diarize is True
    assert request.min_speakers == 2
    assert request.max_speakers == 3
    assert request.context.prompt == "Video de prueba"
    assert request.context.tone == "formal"
    assert request.context.glossary == {"foo": "bar"}
    assert request.context.source_lang == "en"
    assert request.context.target_lang == "es"

    build_mock.assert_called_once()
    _, kwargs = build_mock.call_args
    assert kwargs["enable_dubbing"] is True
    assert kwargs["enable_diarization"] is True
    assert kwargs["resume"] is False


def test_build_use_case_and_request_subtitles_only_disables_dubbing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path)
    project.output_mode = OutputMode.SUBTITLES_ONLY.value

    build_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(project_mapper, "build_translate_video_use_case", build_mock)

    _, request = project_mapper.build_use_case_and_request(project)

    assert request.output_mode == OutputMode.SUBTITLES_ONLY
    _, kwargs = build_mock.call_args
    assert kwargs["enable_dubbing"] is False


def test_build_use_case_and_request_passes_resume_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path)
    build_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(project_mapper, "build_translate_video_use_case", build_mock)

    project_mapper.build_use_case_and_request(project, resume=True)

    _, kwargs = build_mock.call_args
    assert kwargs["resume"] is True


def test_build_use_case_and_request_applies_tts_workers_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_project(tmp_path, tts_workers=2)
    build_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(project_mapper, "build_translate_video_use_case", build_mock)

    project_mapper.build_use_case_and_request(project)

    (settings_arg, *_rest), _ = build_mock.call_args
    assert settings_arg.tts_parallel_workers == 2


def _make_transcription_project(tmp_path: Path, **config_overrides: object) -> Project:
    config = {"source_lang": "en", **config_overrides}
    return Project(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Proyecto de transcripcion",
        service_type=ServiceType.TRANSCRIPTION,
        source_type=SourceType.UPLOAD,
        input_video_path=str(tmp_path / "input.mp3"),
        output_dir=str(tmp_path / "output"),
        output_mode=OutputMode.SUBTITLES_ONLY.value,
        config=config,
        status=ProjectStatus.QUEUED,
    )


def test_build_transcribe_use_case_and_request_maps_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_transcription_project(tmp_path, source_lang="fr")

    fake_use_case = MagicMock()
    build_mock = MagicMock(return_value=fake_use_case)
    monkeypatch.setattr(project_mapper, "build_transcribe_media_use_case", build_mock)

    use_case, request = project_mapper.build_transcribe_use_case_and_request(project)

    assert use_case is fake_use_case
    assert request.input_media == Path(project.input_video_path)
    assert request.output_dir == Path(project.output_dir)
    assert request.output_dir.is_dir()
    assert request.source_lang_hint == "fr"
    build_mock.assert_called_once()


def test_build_transcribe_use_case_and_request_empty_source_lang_means_auto_detect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_transcription_project(tmp_path, source_lang="")
    monkeypatch.setattr(project_mapper, "build_transcribe_media_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_transcribe_use_case_and_request(project)

    assert request.source_lang_hint is None


def test_build_transcribe_use_case_and_request_include_summary_defaults_false(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_transcription_project(tmp_path)
    build_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(project_mapper, "build_transcribe_media_use_case", build_mock)

    _, request = project_mapper.build_transcribe_use_case_and_request(project)

    assert request.include_summary is False
    _, kwargs = build_mock.call_args
    assert kwargs["include_summary"] is False


def test_build_transcribe_use_case_and_request_include_summary_true(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_transcription_project(tmp_path, include_summary=True)
    build_mock = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(project_mapper, "build_transcribe_media_use_case", build_mock)

    _, request = project_mapper.build_transcribe_use_case_and_request(project)

    assert request.include_summary is True
    _, kwargs = build_mock.call_args
    assert kwargs["include_summary"] is True


def _make_tts_project(tmp_path: Path, text: str = "Hola mundo.", **config_overrides: object) -> Project:
    text_path = tmp_path / "input.txt"
    text_path.write_text(text, encoding="utf-8")
    config = {"target_lang": "es", **config_overrides}
    return Project(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Proyecto de TTS",
        service_type=ServiceType.TTS,
        source_type=SourceType.UPLOAD,
        input_video_path=str(text_path),
        output_dir=str(tmp_path / "output"),
        output_mode=OutputMode.SUBTITLES_ONLY.value,
        config=config,
        status=ProjectStatus.QUEUED,
    )


def test_build_synthesize_use_case_and_request_reads_text_and_maps_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_tts_project(tmp_path, text="Hola mundo.", target_lang="en")

    fake_use_case = MagicMock()
    build_mock = MagicMock(return_value=fake_use_case)
    monkeypatch.setattr(project_mapper, "build_synthesize_text_use_case", build_mock)

    use_case, request = project_mapper.build_synthesize_use_case_and_request(project)

    assert use_case is fake_use_case
    assert request.text == "Hola mundo."
    assert request.output_dir == Path(project.output_dir)
    assert request.output_dir.is_dir()
    assert request.language == "en"
    build_mock.assert_called_once()


def test_build_synthesize_use_case_and_request_defaults_to_public_female_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_tts_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_synthesize_text_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_synthesize_use_case_and_request(project)

    assert request.speaker_reference_wav == project_mapper.PUBLIC_VOICE_FEMALE_WAV


def test_build_synthesize_use_case_and_request_maps_public_male_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_tts_project(tmp_path, voice_option="public_male")
    monkeypatch.setattr(project_mapper, "build_synthesize_text_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_synthesize_use_case_and_request(project)

    assert request.speaker_reference_wav == project_mapper.PUBLIC_VOICE_MALE_WAV


def test_build_synthesize_use_case_and_request_own_voice_overrides_voice_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    voice_path = tmp_path / "voice.wav"
    project = _make_tts_project(
        tmp_path, voice_option="own", speaker_reference_wav=str(voice_path)
    )
    monkeypatch.setattr(project_mapper, "build_synthesize_text_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_synthesize_use_case_and_request(project)

    assert request.speaker_reference_wav == voice_path


def _make_micro_video_project(
    tmp_path: Path, narration_text: str = "Hola mundo.", **config_overrides: object
) -> Project:
    image_path = tmp_path / "photo.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    config = {"target_lang": "es", "narration_text": narration_text, **config_overrides}
    return Project(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="Proyecto de micro-video",
        service_type=ServiceType.MICRO_VIDEO,
        source_type=SourceType.UPLOAD,
        input_video_path=str(image_path),
        output_dir=str(tmp_path / "output"),
        output_mode=OutputMode.SUBTITLES_ONLY.value,
        config=config,
        status=ProjectStatus.QUEUED,
    )


def test_build_micro_video_use_case_and_request_maps_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, narration_text="Un texto cualquiera.", target_lang="en")

    fake_use_case = MagicMock()
    build_mock = MagicMock(return_value=fake_use_case)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", build_mock)

    use_case, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert use_case is fake_use_case
    assert [img.path for img in request.media_items] == [Path(project.input_video_path)]
    assert request.text == "Un texto cualquiera."
    assert request.output_dir == Path(project.output_dir)
    assert request.output_dir.is_dir()
    assert request.language == "en"
    build_mock.assert_called_once()


def test_build_micro_video_use_case_and_request_defaults_to_public_female_voice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.speaker_reference_wav == project_mapper.PUBLIC_VOICE_FEMALE_WAV


def test_build_micro_video_use_case_and_request_own_voice_overrides_voice_option(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    voice_path = tmp_path / "voice.wav"
    project = _make_micro_video_project(
        tmp_path, voice_option="own", speaker_reference_wav=str(voice_path)
    )
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.speaker_reference_wav == voice_path


def test_build_micro_video_use_case_and_request_defaults_duration_to_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.target_duration_seconds is None
    assert request.caption_bg_color == "#000000"


def test_build_micro_video_use_case_and_request_maps_duration_and_bg_color(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, target_duration_seconds=30.0, caption_bg_color="#FF0000")
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.target_duration_seconds == 30.0
    assert request.caption_bg_color == "#FF0000"


def test_build_micro_video_use_case_and_request_defaults_highlight_style_to_background(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.caption_highlight_style == "background"


def test_build_micro_video_use_case_and_request_maps_text_color_highlight_style(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, caption_highlight_style="text_color")
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.caption_highlight_style == "text_color"


def test_build_micro_video_use_case_and_request_defaults_to_no_music(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_path is None


def test_build_micro_video_use_case_and_request_resolves_background_music_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    track = MusicTrack(title="Backbeat", category="energy_pop", file_path=str(tmp_path / "backbeat.mp3"))
    db_session.add(track)
    db_session.commit()
    project = _make_micro_video_project(tmp_path, background_music=str(track.id))
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_path == Path(track.file_path)


def test_build_micro_video_use_case_and_request_ignores_unknown_music_track(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, background_music="does-not-exist")
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_path is None


def test_build_micro_video_use_case_and_request_defaults_to_full_music_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_start == 0.0
    assert request.background_music_end is None


def test_build_micro_video_use_case_and_request_maps_music_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, background_music_start=10.0, background_music_end=25.0)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_start == pytest.approx(10.0)
    assert request.background_music_end == pytest.approx(25.0)


def test_build_micro_video_use_case_and_request_defaults_to_no_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.text_overlays == []


def test_build_micro_video_use_case_and_request_maps_text_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    overlays = [
        {"text": "Hola", "x": 0.5, "y": 0.2, "bold": True, "color": "#FF0000"},
        {"text": "Chau", "x": 0.5, "y": 0.8},
    ]
    project = _make_micro_video_project(tmp_path, text_overlays=overlays)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert len(request.text_overlays) == 2
    assert request.text_overlays[0].text == "Hola"
    assert request.text_overlays[0].bold is True
    assert request.text_overlays[0].color == "#FF0000"
    assert request.text_overlays[1].text == "Chau"
    assert request.text_overlays[1].bold is False  # default del dataclass


def test_build_micro_video_use_case_and_request_defaults_emoji_overlays_to_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.emoji_overlays == []


def test_build_micro_video_use_case_and_request_maps_emoji_overlays(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    overlays = [
        {"emoji_id": "fuego", "x": 0.25, "y": 0.75, "size": 0.2, "fade": True},
        {"emoji_id": "corazon", "x": 0.5, "y": 0.5},
    ]
    project = _make_micro_video_project(tmp_path, emoji_overlays=overlays)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert len(request.emoji_overlays) == 2
    assert request.emoji_overlays[0].emoji_id == "fuego"
    assert request.emoji_overlays[0].size == pytest.approx(0.2)
    assert request.emoji_overlays[0].fade is True
    assert request.emoji_overlays[1].emoji_id == "corazon"
    assert request.emoji_overlays[1].size == pytest.approx(0.15)  # default del dataclass


def test_build_micro_video_use_case_and_request_defaults_volume_and_caption_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_volume == pytest.approx(0.12)
    assert request.narration_volume == pytest.approx(1.0)
    assert request.caption_x == pytest.approx(0.5)
    assert request.caption_y == pytest.approx(0.85)


def test_build_micro_video_use_case_and_request_maps_volume_and_caption_position(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(
        tmp_path,
        background_music_volume=0.3,
        narration_volume=0.0,
        caption_x=0.1,
        caption_y=0.0,
    )
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.background_music_volume == pytest.approx(0.3)
    assert request.narration_volume == pytest.approx(0.0)  # 0.0 es un valor real (silenciado), no "ausente"
    assert request.caption_x == pytest.approx(0.1)
    assert request.caption_y == pytest.approx(0.0)


def test_build_micro_video_use_case_and_request_defaults_to_only_primary_image(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert [img.path for img in request.media_items] == [Path(project.input_video_path)]


def test_build_micro_video_use_case_and_request_maps_additional_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    extra1 = str(tmp_path / "extra1.jpg")
    extra2 = str(tmp_path / "extra2.jpg")
    project = _make_micro_video_project(tmp_path, additional_media_paths=[extra1, extra2])
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert [img.path for img in request.media_items] == [Path(project.input_video_path), Path(extra1), Path(extra2)]


def test_build_micro_video_use_case_and_request_defaults_image_frame_without_adjustments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[0].offset_x == pytest.approx(0.5)
    assert request.media_items[0].offset_y == pytest.approx(0.5)
    assert request.media_items[0].zoom == pytest.approx(1.0)
    assert request.media_items[0].filter_preset == "none"


def test_build_micro_video_use_case_and_request_maps_image_filter_preset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    extra = str(tmp_path / "extra.jpg")
    adjustments = [{"filter_preset": "sepia"}, {"filter_preset": "dramatic"}]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[extra], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[0].filter_preset == "sepia"
    assert request.media_items[1].filter_preset == "dramatic"


def test_build_micro_video_use_case_and_request_maps_media_adjustments(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    extra = str(tmp_path / "extra.jpg")
    adjustments = [
        {"offset_x": 0.2, "offset_y": 0.8, "zoom": 1.5},
        {"offset_x": 0.9, "offset_y": 0.1, "zoom": 2.0},
    ]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[extra], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[0].offset_x == pytest.approx(0.2)
    assert request.media_items[0].offset_y == pytest.approx(0.8)
    assert request.media_items[0].zoom == pytest.approx(1.5)
    assert request.media_items[1].offset_x == pytest.approx(0.9)
    assert request.media_items[1].offset_y == pytest.approx(0.1)
    assert request.media_items[1].zoom == pytest.approx(2.0)


def test_build_micro_video_use_case_and_request_fills_missing_adjustment_with_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    extra = str(tmp_path / "extra.jpg")
    # Solo hay ajuste para la primera imagen -- la segunda (indice desalineado,
    # p.ej. imagen agregada despues sin haberla ajustado) usa los defaults.
    adjustments = [{"offset_x": 0.2, "offset_y": 0.8, "zoom": 1.5}]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[extra], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[1].offset_x == pytest.approx(0.5)
    assert request.media_items[1].offset_y == pytest.approx(0.5)
    assert request.media_items[1].zoom == pytest.approx(1.0)


def test_build_micro_video_use_case_and_request_maps_mixed_image_and_clip_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    clip = str(tmp_path / "clip.mp4")
    adjustments = [{}, {"keep_ranges": [[2.0, 5.0]]}]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[clip], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert [item.path for item in request.media_items] == [Path(project.input_video_path), Path(clip)]
    assert request.media_items[1].keep_ranges == [(2.0, 5.0)]


def test_build_micro_video_use_case_and_request_maps_multiple_keep_ranges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    # RM-40: varios tramos sueltos de un mismo clip, con un hueco eliminado
    # entre medio.
    clip = str(tmp_path / "clip.mp4")
    adjustments = [{}, {"keep_ranges": [[0.0, 2.0], [5.0, None]]}]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[clip], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[1].keep_ranges == [(0.0, 2.0), (5.0, None)]


def test_build_micro_video_use_case_and_request_falls_back_to_legacy_clip_start_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    # Proyecto armado con la version anterior a RM-40 (un unico
    # clip_start/clip_end, ver RM-36) -- sigue pudiendo reanudarse via
    # /resume sin perder el recorte ya elegido.
    clip = str(tmp_path / "clip.mp4")
    adjustments = [{}, {"clip_start": 2.0, "clip_end": 5.0}]
    project = _make_micro_video_project(tmp_path, additional_media_paths=[clip], media_adjustments=adjustments)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.media_items[1].keep_ranges == [(2.0, 5.0)]


def test_build_micro_video_use_case_and_request_falls_back_to_legacy_image_config_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    # Proyecto anterior a RM-36 (o un reintento via /resume de uno que fallo
    # antes de este cambio): las claves siguen siendo las viejas
    # "additional_image_paths"/"image_adjustments", no las nuevas.
    extra = str(tmp_path / "extra.jpg")
    project = _make_micro_video_project(
        tmp_path,
        additional_image_paths=[extra],
        image_adjustments=[{}, {"zoom": 1.5}],
    )
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert [item.path for item in request.media_items] == [Path(project.input_video_path), Path(extra)]
    assert request.media_items[1].zoom == pytest.approx(1.5)


def test_build_micro_video_use_case_and_request_defaults_are_the_product_profile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    # Red de seguridad de RM-42. El perfil "producto" se define como "los
    # defaults que la app ya tenia", asi que este test los fija TODOS en un
    # solo sitio: si alguno se desvia al agregar el segundo perfil, lo que ya
    # funcionaba (RM-14/RM-28) se degrada en silencio y nadie se entera.
    # Un `config` con lo minimo imprescindible -- lo que manda el editor si el
    # usuario no toca ningun panel.
    project = _make_micro_video_project(tmp_path)
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.objective == "product"  # el unico objetivo previo a RM-42
    assert request.target_duration_seconds is None  # dura lo que la narracion
    assert request.caption_bg_color == "#000000"
    assert request.caption_highlight_style == "background"
    assert request.caption_text_color == "#FFFFFF"
    assert request.background_music_path is None
    assert request.background_music_start == pytest.approx(0.0)
    assert request.background_music_end is None
    assert request.background_music_volume == pytest.approx(0.12)
    assert request.narration_volume == pytest.approx(1.0)
    assert request.caption_x == pytest.approx(0.5)
    assert request.caption_y == pytest.approx(0.85)
    assert request.text_overlays == []
    assert request.emoji_overlays == []


def test_build_micro_video_use_case_and_request_maps_objective(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    project = _make_micro_video_project(tmp_path, objective="professional")
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.objective == "professional"


def test_build_micro_video_use_case_and_request_empty_objective_falls_back_to_product(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, db_session: Session
) -> None:
    # Cadena vacia, no clave ausente: es lo que llega si el formulario manda
    # el campo sin valor. Tiene que caer al default igual que si faltara, o la
    # corrida se queda sin objetivo y el informe miente.
    project = _make_micro_video_project(tmp_path, objective="")
    monkeypatch.setattr(project_mapper, "build_generate_micro_video_use_case", MagicMock(return_value=MagicMock()))

    _, request = project_mapper.build_micro_video_use_case_and_request(project, db_session)

    assert request.objective == "product"
