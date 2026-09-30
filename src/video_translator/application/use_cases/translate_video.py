"""Caso de uso: TranslateVideoUseCase.

Orquesta el pipeline completo:
  1. Validar entrada
  2. Extraer audio (MediaProcessor)
  3. Transcribir (Transcriber) Y Diarizar (SpeakerDiarizer) EN PARALELO cuando
     ambas hacen falta: son independientes entre si (las dos solo necesitan
     el audio extraido), y en videos largos cada una puede tardar decenas de
     minutos por separado. Correrlas concurrentemente evita sumar sus tiempos.
  4. (Si hubo diarizacion) Construir perfil por hablante (voz + genero)
  5. Traducir por lotes con contexto, historial e info de hablante/genero (Translator)
  6. Generar subtitulos SRT (SubtitleWriter)
  7. (Opcional) Sintetizar doblaje, agrupando segmentos cercanos del mismo
     hablante para reducir llamadas, y despachando en paralelo si el motor
     de sintesis lo soporta (SpeechSynthesizer), y mezclar con el video
  8. (Opcional) Incrustar/adjuntar subtitulos al video final (MediaProcessor)

Cada etapa se cronometra (PipelineTimings) para trazabilidad: el reporte JSON
(`pipeline_timings.json`) se actualiza INCREMENTALMENTE tras cada fase (y al
entrar en ella), no solo al terminar — si el pipeline muere a mitad de camino,
el archivo refleja el progreso real. Al reanudar (--resume), las etapas
saltadas conservan la duracion real que tuvieron en la corrida anterior (se
adopta el reporte previo), en vez de anotar 0.0s.

Soporte de reanudacion (resume=True): cada etapa que produce datos intermedios
volatiles persiste su estado en un checkpoint JSON en el workdir. Si el
pipeline se interrumpe (corte de energia, Ctrl-C, crash), se puede relanzar
y saltar las etapas ya completadas, ahorrando horas de trabajo. Las etapas
basadas puramente en archivos (extraccion de audio, subtitulos SRT, archivos
WAV de TTS individuales, video final) se verifican comprobando existencia de
archivos, sin cargarlos al checkpoint.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path

from structlog.stdlib import BoundLogger

try:
    # Subclase del ThreadPoolExecutor de arriba que copia el contexto de
    # telemetria al hilo trabajador. Sin esto los logs que emiten transcripcion
    # y diarizacion salen sin TraceId: el contexto vive en un
    # contextvars.ContextVar y el pool no lo arrastra al hilo (ver RM-41).
    # Se pisa el nombre a proposito para que el sitio de uso no tenga
    # que saber cual de los dos le toco. El import de arriba queda como el
    # caso base: argus-obs-sdk esta en el extra "web" y la CLI corre este mismo
    # caso de uso sin el instalado, donde no hay contexto que propagar porque
    # nadie exporta nada.
    from argus.propagate import Executor as ThreadPoolExecutor
except ImportError:  # pragma: no cover
    pass

from video_translator.application.interfaces import (
    GenderClassifier,
    MediaProcessor,
    SpeakerDiarizer,
    SpeechSynthesizer,
    SubtitleWriter,
    Transcriber,
    Translator,
)
from video_translator.application.synthesis_job import SynthesisJob
from video_translator.domain.exceptions import InvalidVideoFileError, VideoTranslatorError
from video_translator.domain.models import (
    DiarizationSegment,
    OutputMode,
    SpeakerProfile,
    TranscriptSegment,
    TranslatedSegment,
    TranslateVideoRequest,
    TranslateVideoResult,
)
from video_translator.utils.checkpoint import (
    STAGE_AUDIO_EXTRACTED,
    STAGE_FINALIZED,
    STAGE_SPEAKERS_BUILT,
    STAGE_SUBTITLES_WRITTEN,
    STAGE_TRANSCRIBED,
    STAGE_TRANSLATED,
    STAGE_TTS_SYNTHESIZED,
    Checkpoint,
    CheckpointStore,
    restore_diarization_segments,
    restore_speaker_profiles,
    restore_transcript_segments,
    restore_translated_segments,
)
from video_translator.utils.diarization_alignment import (
    assign_speakers,
    select_reference_windows,
    unique_speaker_labels,
)
from video_translator.utils.logging_config import get_logger
from video_translator.utils.synthesis_grouping import SynthesisGroup, group_segments_for_synthesis
from video_translator.utils.text_batching import batch_segments
from video_translator.utils.timing import PipelineTimings
from video_translator.utils.warning_collector import drain_stats, drain_warnings, note_stat

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}


class TranslateVideoUseCase:
    def __init__(
        self,
        media_processor: MediaProcessor,
        transcriber: Transcriber,
        translator: Translator,
        subtitle_writer: SubtitleWriter,
        speech_synthesizer: SpeechSynthesizer | None = None,
        speaker_diarizer: SpeakerDiarizer | None = None,
        gender_classifier: GenderClassifier | None = None,
        translation_batch_max_chars: int = 1800,
        context_window_segments: int = 6,
        group_segments_for_synthesis: bool = True,
        group_max_gap_seconds: float = 0.5,
        group_max_chars: int = 200,
        resume: bool = False,
        effective_config: dict | None = None,
    ) -> None:
        self._media = media_processor
        self._transcriber = transcriber
        self._translator = translator
        self._subtitles = subtitle_writer
        self._synthesizer = speech_synthesizer
        self._diarizer = speaker_diarizer
        self._gender_classifier = gender_classifier
        self._batch_max_chars = translation_batch_max_chars
        self._context_window = context_window_segments
        self._group_segments = group_segments_for_synthesis
        self._group_max_gap = group_max_gap_seconds
        self._group_max_chars = group_max_chars
        self._resume = resume
        self._effective_config = dict(effective_config) if effective_config else {}

    def execute(self, request: TranslateVideoRequest) -> TranslateVideoResult:
        self._validate_request(request)
        request.output_dir.mkdir(parents=True, exist_ok=True)
        workdir = request.output_dir / "_work"
        workdir.mkdir(parents=True, exist_ok=True)

        report_path = request.output_dir / "pipeline_timings.json"
        timings = PipelineTimings(report_path=report_path)
        if self._effective_config:
            timings.set_effective_config(**self._effective_config)
        log = logger.bind(input=str(request.input_video), run_id=timings.run_id)
        log.info("pipeline.start", resume=self._resume)

        checkpoint_store = CheckpointStore(workdir)
        if self._resume:
            timings.mark_resumed()
            if report_path.exists():
                # Adoptar las duraciones reales de la corrida anterior: las
                # etapas que esta corrida salte por checkpoint se reportaran
                # con su tiempo original, no con 0.0s.
                timings.adopt_previous_report(report_path)
        checkpoint = self._load_checkpoint(checkpoint_store, request, log)

        duration = self._media.get_duration_seconds(request.input_video)
        timings.set_input(request.input_video, duration)
        log.info("pipeline.duration_detected", seconds=round(duration, 1))

        audio_wav = workdir / "audio_16k_mono.wav"
        if STAGE_AUDIO_EXTRACTED in checkpoint.completed_stages:
            log.info("pipeline.resume_skipping", stage=STAGE_AUDIO_EXTRACTED, reason="checkpoint")
            timings.record_resumed("audio_extraction")
        else:
            with timings.stage("audio_extraction"):
                self._media.extract_audio(request.input_video, audio_wav)
            checkpoint = self._mark_stage_done(checkpoint, request, STAGE_AUDIO_EXTRACTED)
            checkpoint_store.save(checkpoint)
        log.info("pipeline.audio_extracted", path=str(audio_wav))

        checkpoint, segments, diarization_segments = self._load_or_run_transcription(
            request, audio_wav, timings, checkpoint, checkpoint_store, log
        )
        if not segments:
            raise VideoTranslatorError("La transcripcion no produjo ningun segmento de texto.")
        log.info("pipeline.transcription_done", num_segments=len(segments))

        speaker_profiles: list[SpeakerProfile] = []
        if request.diarize:
            checkpoint, segments, speaker_profiles = self._load_or_build_speaker_profiles(
                segments, diarization_segments, audio_wav, workdir, timings,
                checkpoint, checkpoint_store, request, log,
            )
            request.context.speaker_genders = {
                p.speaker_id: p.gender for p in speaker_profiles if p.gender
            }
        else:
            checkpoint = self._mark_stage_done(checkpoint, request, STAGE_SPEAKERS_BUILT)
            checkpoint_store.save(checkpoint)

        if STAGE_TRANSLATED in checkpoint.completed_stages:
            restored = restore_translated_segments(checkpoint)
            if restored is None:
                raise VideoTranslatorError(
                    "El checkpoint marca 'translated' como completado pero no "
                    "contiene los segmentos traducidos; borra el checkpoint y reintenta."
                )
            translated_segments = restored
            log.info("pipeline.resume_skipping", stage=STAGE_TRANSLATED, reason="checkpoint")
            timings.record_resumed("translation", num_segments=len(segments))
        else:
            num_batches = len(batch_segments(segments, max_chars=self._batch_max_chars))
            with timings.stage(
                "translation", num_segments=len(segments), num_batches=num_batches
            ):
                translated_segments = self._translate_all(segments, request, log)
                checkpoint = self._update_checkpoint_data(
                    checkpoint, request,
                    transcript_segments=segments,
                    translated_segments=translated_segments,
                    speaker_profiles=speaker_profiles,
                )
                checkpoint = self._mark_stage_done(checkpoint, request, STAGE_TRANSLATED)
                checkpoint_store.save(checkpoint)
        log.info("pipeline.translation_done", num_translated=len(translated_segments))

        srt_es = request.output_dir / "subtitles.es.srt"
        srt_en = request.output_dir / "subtitles.en.srt"
        if STAGE_SUBTITLES_WRITTEN in checkpoint.completed_stages:
            log.info("pipeline.resume_skipping", stage=STAGE_SUBTITLES_WRITTEN, reason="checkpoint")
            timings.record_resumed("subtitles_writing")
        else:
            with timings.stage("subtitles_writing"):
                self._subtitles.write(translated_segments, srt_es, use_translation=True)
                self._subtitles.write(translated_segments, srt_en, use_translation=False)
                checkpoint = self._mark_stage_done(checkpoint, request, STAGE_SUBTITLES_WRITTEN)
                checkpoint_store.save(checkpoint)
        log.info("pipeline.subtitles_written", es=str(srt_es), en=str(srt_en))

        output_video: Path | None = None
        rendering_stage = f"rendering_{request.output_mode.value}"

        # Salto por resume: etapa FINALIZED marcada Y el video de salida de
        # este modo presente en disco. Se resuelve ANTES del bloque cronometrado
        # para que el salto se reporte como etapa "resumed" con su duracion
        # original, no como una etapa completada de ~0s.
        expected_render_output = self._expected_render_output(request)
        skip_rendering = (
            STAGE_FINALIZED in checkpoint.completed_stages
            and (expected_render_output is None or expected_render_output.exists())
        )

        if skip_rendering:
            log.info("pipeline.resume_skipping", stage=STAGE_FINALIZED, reason="checkpoint")
            timings.record_resumed(rendering_stage)
            output_video = expected_render_output
        elif request.output_mode == OutputMode.DUBBED:
            if self._synthesizer is None:
                raise VideoTranslatorError(
                    "OutputMode.DUBBED requiere un SpeechSynthesizer configurado "
                    "(instala un extra de doblaje y configura TTS_BACKEND)."
                )
            with timings.stage(rendering_stage):
                output_video = self._render_dubbed_video(
                    request, translated_segments, speaker_profiles, duration,
                    workdir, timings, checkpoint, checkpoint_store, log,
                )
        elif request.output_mode == OutputMode.BURN_SUBTITLES:
            output_video = self._expected_render_output(request)
            assert output_video is not None
            with timings.stage(rendering_stage):
                self._media.burn_subtitles(request.input_video, srt_es, output_video)
                checkpoint = self._mark_stage_done(checkpoint, request, STAGE_FINALIZED)
                checkpoint_store.save(checkpoint)

        elif request.output_mode == OutputMode.SOFT_SUBTITLES:
            output_video = self._expected_render_output(request)
            assert output_video is not None
            with timings.stage(rendering_stage):
                self._media.attach_soft_subtitles(request.input_video, srt_es, output_video)
                checkpoint = self._mark_stage_done(checkpoint, request, STAGE_FINALIZED)
                checkpoint_store.save(checkpoint)
        # OutputMode.SUBTITLES_ONLY -> no se genera video, solo los .srt

        # Red de seguridad: cualquier warning anotado por infraestructura fuera
        # de la fase de mezcla tambien acaba en el reporte.
        for w in drain_warnings():
            timings.add_warning(**w)
        timings.add_stats(*drain_stats())
        if output_video is not None and output_video.exists():
            timings.set_outputs(output_video=str(output_video), output_video_bytes=output_video.stat().st_size)
        timings.write_report(report_path, final=True)
        if self._resume:
            checkpoint_store.clear()
            log.info("pipeline.checkpoint_cleared", reason="pipeline completed successfully")
        log.info(
            "pipeline.finished",
            output_video=str(output_video) if output_video else None,
            total_seconds=round(timings.total_seconds, 1),
            timings_report=str(report_path),
        )

        return TranslateVideoResult(
            output_video=output_video,
            subtitles_source_path=srt_en,
            subtitles_target_path=srt_es,
            segments=translated_segments,
            duration_seconds=duration,
            speakers=speaker_profiles,
            timings=timings.as_dict(),
        )

    def _load_checkpoint(
        self, store: CheckpointStore, request: TranslateVideoRequest, log: BoundLogger
    ) -> Checkpoint:
        """Carga el checkpoint si existe y es valido para esta solicitud."""
        if not self._resume:
            stat = request.input_video.stat()
            return Checkpoint(
                input_video=str(request.input_video),
                input_size=stat.st_size,
                input_mtime=stat.st_mtime,
                source_lang_hint=request.source_lang_hint,
                diarize=request.diarize,
                output_mode=request.output_mode.value,
            )
        cp = store.load()
        if cp is None:
            log.info("pipeline.no_checkpoint_found", resume_enabled=True)
            stat = request.input_video.stat()
            return Checkpoint(
                input_video=str(request.input_video),
                input_size=stat.st_size,
                input_mtime=stat.st_mtime,
                source_lang_hint=request.source_lang_hint,
                diarize=request.diarize,
                output_mode=request.output_mode.value,
            )
        if not self._checkpoint_matches_request(cp, request):
            log.warning(
                "pipeline.checkpoint_mismatch",
                reason="el checkpoint no corresponde a esta solicitud (input, modo o diarizacion cambiados)",
                resume_enabled=True,
            )
            stat = request.input_video.stat()
            return Checkpoint(
                input_video=str(request.input_video),
                input_size=stat.st_size,
                input_mtime=stat.st_mtime,
                source_lang_hint=request.source_lang_hint,
                diarize=request.diarize,
                output_mode=request.output_mode.value,
            )
        log.info(
            "pipeline.resume_from_checkpoint",
            stages=cp.completed_stages,
            checkpoint_path=str(store.path),
        )
        return cp

    @staticmethod
    def _checkpoint_matches_request(cp: Checkpoint, request: TranslateVideoRequest) -> bool:
        """Verifica que el checkpoint corresponde al mismo video y configuracion."""
        try:
            stat = request.input_video.stat()
        except OSError:
            return False
        return (
            cp.input_video == str(request.input_video)
            and cp.input_size == stat.st_size
            and cp.source_lang_hint == request.source_lang_hint
            and cp.diarize == request.diarize
            and cp.output_mode == request.output_mode.value
        )

    @staticmethod
    def _mark_stage_done(checkpoint: Checkpoint, request: TranslateVideoRequest, stage: str) -> Checkpoint:
        """Devuelve un checkpoint actualizado con la etapa marcada como completada."""
        stages = list(checkpoint.completed_stages)
        if stage not in stages:
            stages.append(stage)
        return Checkpoint(
            input_video=checkpoint.input_video,
            input_size=checkpoint.input_size,
            input_mtime=checkpoint.input_mtime,
            source_lang_hint=checkpoint.source_lang_hint,
            diarize=checkpoint.diarize,
            output_mode=checkpoint.output_mode,
            completed_stages=stages,
            transcript_segments=checkpoint.transcript_segments,
            diarization_segments=checkpoint.diarization_segments,
            speaker_profiles=checkpoint.speaker_profiles,
            translated_segments=checkpoint.translated_segments,
            tts_job_count=checkpoint.tts_job_count,
        )

    @staticmethod
    def _update_checkpoint_data(
        checkpoint: Checkpoint,
        request: TranslateVideoRequest,
        *,
        transcript_segments: list[TranscriptSegment] | None = None,
        diarization_segments: list[DiarizationSegment] | None = None,
        speaker_profiles: list[SpeakerProfile] | None = None,
        translated_segments: list[TranslatedSegment] | None = None,
        tts_job_count: int | None = None,
    ) -> Checkpoint:
        """Devuelve un checkpoint con datos intermedios actualizados."""

        def _serialize_segments(
            segs: list[TranscriptSegment] | list[TranslatedSegment],
        ) -> list[dict]:
            return [asdict(s) if not isinstance(s, dict) else s for s in segs]

        def _serialize_profiles(profiles: list[SpeakerProfile]) -> list[dict]:
            return [
                {**asdict(p), "reference_wav": str(p.reference_wav) if p.reference_wav else None}
                for p in profiles
            ]

        return Checkpoint(
            input_video=checkpoint.input_video,
            input_size=checkpoint.input_size,
            input_mtime=checkpoint.input_mtime,
            source_lang_hint=checkpoint.source_lang_hint,
            diarize=checkpoint.diarize,
            output_mode=checkpoint.output_mode,
            completed_stages=list(checkpoint.completed_stages),
            transcript_segments=(
                _serialize_segments(transcript_segments)
                if transcript_segments is not None
                else checkpoint.transcript_segments
            ),
            diarization_segments=(
                [asdict(d) for d in diarization_segments]
                if diarization_segments is not None
                else checkpoint.diarization_segments
            ),
            speaker_profiles=(
                _serialize_profiles(speaker_profiles)
                if speaker_profiles is not None
                else checkpoint.speaker_profiles
            ),
            translated_segments=(
                _serialize_segments(translated_segments)
                if translated_segments is not None
                else checkpoint.translated_segments
            ),
            tts_job_count=tts_job_count if tts_job_count is not None else checkpoint.tts_job_count,
        )

    def _load_or_run_transcription(
        self,
        request: TranslateVideoRequest,
        audio_wav: Path,
        timings: PipelineTimings,
        checkpoint: Checkpoint,
        checkpoint_store: CheckpointStore,
        log: BoundLogger,
    ) -> tuple[Checkpoint, list[TranscriptSegment], list[DiarizationSegment] | None]:
        """Si la transcripcion esta en el checkpoint, la restaura; si no, la ejecuta."""
        if STAGE_TRANSCRIBED in checkpoint.completed_stages:
            segments = restore_transcript_segments(checkpoint)
            diarization_segments = restore_diarization_segments(checkpoint)
            log.info(
                "pipeline.resume_skipping",
                stage=STAGE_TRANSCRIBED,
                reason="checkpoint",
                num_segments=len(segments),
            )
            timings.record_resumed("transcription")
            if request.diarize:
                timings.record_resumed("diarization", num_speakers=len(
                    {d.speaker_label for d in diarization_segments}
                ) if diarization_segments else 0)
                # No hace falta volver a llamar mark_concurrent() aqui: si la
                # corrida original las marco como concurrentes,
                # adopt_previous_report() ya arrastro ese grupo a
                # self._concurrent_groups (ver timing.py). Repetir la llamada
                # duplicaria la entrada y doblaria parallel_time_saved_seconds.
            return checkpoint, segments, diarization_segments

        segments, diarization_segments = self._transcribe_and_diarize(request, audio_wav, timings)

        checkpoint = self._update_checkpoint_data(
            checkpoint, request,
            transcript_segments=segments,
            diarization_segments=diarization_segments,
        )
        checkpoint = self._mark_stage_done(checkpoint, request, STAGE_TRANSCRIBED)
        checkpoint_store.save(checkpoint)
        return checkpoint, segments, diarization_segments

    def _load_or_build_speaker_profiles(
        self,
        segments: list[TranscriptSegment],
        diarization_segments: list[DiarizationSegment] | None,
        audio_wav: Path,
        workdir: Path,
        timings: PipelineTimings,
        checkpoint: Checkpoint,
        checkpoint_store: CheckpointStore,
        request: TranslateVideoRequest,
        log: BoundLogger,
    ) -> tuple[Checkpoint, list[TranscriptSegment], list[SpeakerProfile]]:
        """Si los perfiles de hablantes estan en el checkpoint, los restaura; si no, los construye."""
        if STAGE_SPEAKERS_BUILT in checkpoint.completed_stages:
            profiles = restore_speaker_profiles(checkpoint)
            log.info(
                "pipeline.resume_skipping",
                stage=STAGE_SPEAKERS_BUILT,
                reason="checkpoint",
                num_speakers=len(profiles),
            )
            timings.record_resumed(
                "speaker_profile_building",
                num_speakers=len(profiles),
                speakers=[
                    {"id": p.speaker_id, "gender": p.gender, "reference": bool(p.reference_wav)}
                    for p in profiles
                ],
            )
            return checkpoint, segments, profiles

        assert diarization_segments is not None
        labels = unique_speaker_labels(diarization_segments)
        with timings.stage(
            "speaker_profile_building",
            num_speakers=len(labels),
        ):
            segments, profiles, speaker_details = self._build_speaker_profiles(
                segments, diarization_segments, audio_wav, workdir, log
            )
        # Ventana de referencia usada por hablante: util para auditar QUE
        # tramo de voz se clono (p.ej. si un hablante suena mal).
        timings.annotate_stage("speaker_profile_building", speakers=speaker_details)

        checkpoint = self._update_checkpoint_data(
            checkpoint, request,
            speaker_profiles=profiles,
            transcript_segments=segments,
        )
        checkpoint = self._mark_stage_done(checkpoint, request, STAGE_SPEAKERS_BUILT)
        checkpoint_store.save(checkpoint)
        return checkpoint, segments, profiles

    def _transcribe_and_diarize(
        self, request: TranslateVideoRequest, audio_wav: Path, timings: PipelineTimings
    ) -> tuple[list[TranscriptSegment], list[DiarizationSegment] | None]:
        """Corre transcripcion y (si aplica) diarizacion. Cuando ambas hacen
        falta, las corre EN PARALELO en dos hilos: son independientes entre
        si (ambas solo leen el mismo audio_wav), y no correrlas juntas
        significaria simplemente sumar sus tiempos por nada.

        faster-whisper (CTranslate2, C++ por debajo) y el subprocess de
        diarizacion (bloqueado esperando al proceso hijo) liberan el GIL
        mientras trabajan, asi que dos hilos alcanzan para paralelismo real
        aqui — no hace falta multiprocessing para este par.
        """
        if not request.diarize:
            start = time.monotonic()
            segments = list(
                self._transcriber.transcribe(audio_wav, language_hint=request.source_lang_hint)
            )
            timings.record("transcription", time.monotonic() - start, num_segments=len(segments))
            return segments, None

        assert self._diarizer is not None, (
            "request.diarize=True requiere un SpeakerDiarizer configurado "
            "(instala 'diarization' y define HF_TOKEN)."
        )
        # Cada Future anota su propio momento de finalizacion via
        # add_done_callback (se dispara en el hilo worker justo cuando la
        # tarea termina). Sin esto, si una de las dos tareas termina mucho
        # antes que la otra, medir "time.monotonic() - start" recien cuando
        # el hilo principal LLEGA a llamar su .result() (que esta bloqueado
        # esperando a la mas lenta) le atribuye de mas el tiempo de espera
        # ajeno -- se ve, p.ej., diarizacion "tardando" lo mismo que
        # transcripcion aunque haya terminado en una fraccion de ese tiempo.
        with ThreadPoolExecutor(max_workers=2) as pool:
            t_start = time.monotonic()
            transcript_finished_at: list[float] = []
            transcript_future = pool.submit(
                lambda: list(
                    self._transcriber.transcribe(audio_wav, language_hint=request.source_lang_hint)
                )
            )
            transcript_future.add_done_callback(lambda _f: transcript_finished_at.append(time.monotonic()))

            d_start = time.monotonic()
            diarization_finished_at: list[float] = []
            diarization_future = pool.submit(
                self._diarizer.diarize, audio_wav, request.min_speakers, request.max_speakers
            )
            diarization_future.add_done_callback(lambda _f: diarization_finished_at.append(time.monotonic()))

            segments = transcript_future.result()
            timings.record(
                "transcription",
                transcript_finished_at[0] - t_start,
                ran_concurrently=True,
                num_segments=len(segments),
            )

            diarization_segments = diarization_future.result()
            timings.record(
                "diarization",
                diarization_finished_at[0] - d_start,
                ran_concurrently=True,
                num_speakers=len({d.speaker_label for d in diarization_segments}),
                num_turns=len(diarization_segments),
            )

        timings.mark_concurrent(["transcription", "diarization"])
        return segments, diarization_segments

    def _translate_all(
        self, segments: list[TranscriptSegment], request: TranslateVideoRequest, log: BoundLogger
    ) -> list[TranslatedSegment]:
        translated_segments: list[TranslatedSegment] = []
        rolling_history: list[str] = []
        batches = batch_segments(segments, max_chars=self._batch_max_chars)
        log.info("pipeline.translation_batches", num_batches=len(batches))

        for i, batch in enumerate(batches, start=1):
            t_batch = time.monotonic()
            translations = self._translator.translate_batch(
                segments=batch,
                context=request.context,
                rolling_history=rolling_history[-self._context_window :],
            )
            batch_seconds = time.monotonic() - t_batch
            # Latencia por lote del LLM: permite ver degradaciones del server
            # (p.ej. primer lote incluye carga de modelo) entre corridas.
            note_stat("translation.batch_seconds", round(batch_seconds, 2))
            note_stat(
                "translation.batch_chars_per_second",
                round(sum(len(s.text) for s in batch) / batch_seconds, 1)
                if batch_seconds > 0
                else 0.0,
            )
            if len(translations) != len(batch):
                raise VideoTranslatorError(
                    f"El traductor devolvio {len(translations)} lineas para un lote de "
                    f"{len(batch)} segmentos (lote {i}/{len(batches)})."
                )
            for seg, text in zip(batch, translations):
                translated_segments.append(
                    TranslatedSegment(
                        id=seg.id,
                        start=seg.start,
                        end=seg.end,
                        source_text=seg.text,
                        translated_text=text,
                        speaker_id=seg.speaker_id,
                    )
                )
                rolling_history.append(text)
            log.info("pipeline.batch_translated", batch=i, of=len(batches))

        return translated_segments

    def _build_speaker_profiles(
        self,
        segments: list[TranscriptSegment],
        diarization_segments: list[DiarizationSegment] | None,
        audio_wav: Path,
        workdir: Path,
        log: BoundLogger,
    ) -> tuple[list[TranscriptSegment], list[SpeakerProfile], list[dict]]:
        assert diarization_segments is not None
        labels = unique_speaker_labels(diarization_segments)
        log.info("pipeline.diarization_done", num_speakers=len(labels), speakers=labels)

        segments_with_speakers = assign_speakers(segments, diarization_segments)

        # Clip de referencia de voz por hablante (para clonacion en doblaje) + genero estimado.
        reference_dir = workdir / "speaker_references"
        reference_dir.mkdir(parents=True, exist_ok=True)
        windows = select_reference_windows(diarization_segments)

        profiles: list[SpeakerProfile] = []
        details: list[dict] = []
        for label in labels:
            window = windows.get(label)
            reference_wav: Path | None = None
            gender: str | None = None
            if window is not None:
                start, end = window
                reference_wav = reference_dir / f"{label}.wav"
                self._media.extract_audio_clip(audio_wav, start, end, reference_wav)
                if self._gender_classifier is not None:
                    gender = self._gender_classifier.classify(reference_wav)
                details.append(
                    {"id": label, "gender": gender, "reference": True,
                     "ref_start": round(start, 2), "ref_end": round(end, 2)}
                )
            else:
                log.warning("pipeline.speaker_reference_too_short", speaker=label)
                details.append({"id": label, "gender": None, "reference": False})
            profiles.append(SpeakerProfile(speaker_id=label, gender=gender, reference_wav=reference_wav))

        log.info(
            "pipeline.speaker_profiles_built",
            profiles=[(p.speaker_id, p.gender, bool(p.reference_wav)) for p in profiles],
        )
        return segments_with_speakers, profiles, details

    def _expected_render_output(self, request: TranslateVideoRequest) -> Path | None:
        """Ruta del video de salida para este modo, DERIVADA del nombre del
        input (p.ej. ``lecture.dubbed.mp4``): dos traducciones de videos
        distintos en la misma carpeta ya no se pisan entre si. Devuelve None
        solo para SUBTITLES_ONLY (no se genera video).
        """
        suffix = {
            OutputMode.DUBBED: "dubbed",
            OutputMode.BURN_SUBTITLES: "dubbed_subs",
            OutputMode.SOFT_SUBTITLES: "soft_subs",
        }.get(request.output_mode)
        if suffix is None:
            return None
        return request.output_dir / f"{request.input_video.stem}.{suffix}.mp4"

    def _render_dubbed_video(
        self,
        request: TranslateVideoRequest,
        translated_segments: list[TranslatedSegment],
        speaker_profiles: list[SpeakerProfile],
        duration: float,
        workdir: Path,
        timings: PipelineTimings,
        checkpoint: Checkpoint,
        checkpoint_store: CheckpointStore,
        log: BoundLogger,
    ) -> Path:
        assert self._synthesizer is not None
        segment_dir = workdir / "tts_segments"
        segment_dir.mkdir(parents=True, exist_ok=True)

        reference_by_speaker: dict[str, Path] = {
            p.speaker_id: p.reference_wav for p in speaker_profiles if p.reference_wav is not None
        }
        # Ultimo recurso cuando un grupo no matcheo ningun turno de
        # diarizacion (speaker_id=None -- pasa cerca de bordes/huecos entre
        # turnos, sobre todo en videos largos) y tampoco hay --speaker-wav
        # explicito: si SOLO hay un hablante detectado en todo el video, casi
        # seguro que el segmento huerfano es suyo tambien. Sin esto, un solo
        # segmento sin turno asignado tira todo el doblaje.
        only_speaker_reference = (
            next(iter(reference_by_speaker.values())) if len(reference_by_speaker) == 1 else None
        )

        groups = self._group_translated_segments(translated_segments)
        log.info(
            "pipeline.synthesis_groups_built",
            num_groups=len(groups),
            num_segments=len(translated_segments),
            grouping_enabled=self._group_segments,
        )

        jobs: list[SynthesisJob] = []
        for i, group in enumerate(groups):
            job_path = segment_dir / f"group_{i:06d}.wav"
            own_reference = reference_by_speaker.get(group.speaker_id) if group.speaker_id else None
            speaker_wav = own_reference or request.speaker_reference_wav or only_speaker_reference
            if own_reference is None and speaker_wav is not None:
                log.warning(
                    "pipeline.synthesis_group_unmatched_speaker",
                    speaker_id=group.speaker_id,
                    group_index=i,
                    fallback_used=str(speaker_wav),
                )

            next_start = groups[i + 1].start if i + 1 < len(groups) else duration
            max_duration = max(0.05, next_start - group.start)

            jobs.append(
                SynthesisJob(
                    output_path=job_path,
                    text=group.text,
                    target_duration_seconds=max_duration,
                    speaker_reference_wav=speaker_wav,
                    language=request.context.target_lang,
                    start_seconds=group.start,
                    max_duration_seconds=max_duration,
                )
            )

        # Optimizacion de reanudacion: saltar archivos WAV de TTS ya generados.
        missing_jobs = [j for j in jobs if not _is_valid_wav(j.output_path)]
        if missing_jobs:
            log.info("pipeline.tts_resume", total_jobs=len(jobs), missing=len(missing_jobs))
        else:
            log.info("pipeline.tts_all_done", num_jobs=len(jobs))

        with timings.stage(
            "tts_synthesis",
            num_jobs=len(jobs),
            num_missing=len(missing_jobs),
            num_segments_input=len(translated_segments),
            num_groups=len(groups),
            grouping_reduction_pct=(
                round(100 * (1 - len(groups) / len(translated_segments)), 1)
                if translated_segments
                else 0.0
            ),
        ):
            if missing_jobs:
                if hasattr(self._synthesizer, "synthesize_batch"):
                    self._synthesizer.synthesize_batch(missing_jobs)
                else:
                    for job in missing_jobs:
                        self._synthesizer.synthesize_segment(
                            text=job.text,
                            output_path=job.output_path,
                            target_duration_seconds=job.target_duration_seconds,
                            speaker_reference_wav=job.speaker_reference_wav,
                            language=job.language,
                        )
        log.info("pipeline.tts_done", num_jobs=len(jobs))

        checkpoint = self._update_checkpoint_data(
            checkpoint, request, tts_job_count=len(jobs)
        )
        checkpoint = self._mark_stage_done(checkpoint, request, STAGE_TTS_SYNTHESIZED)
        checkpoint_store.save(checkpoint)

        rendered = [(job.start_seconds, job.output_path, job.max_duration_seconds) for job in jobs]

        with timings.stage("audio_mixing_and_muxing"):
            dubbed_audio = workdir / "dubbed_audio.wav"
            self._synthesizer.concatenate_segments(rendered, duration, dubbed_audio)

            output_video = self._expected_render_output(request)
            assert output_video is not None
            self._media.replace_audio_track(
                request.input_video,
                dubbed_audio,
                output_video,
                keep_original_as_secondary=request.keep_original_audio_track,
            )

        # La infraestructura (mezcla) pudo dejar advertencias de calidad
        # (p.ej. desbordes de duracion tras la compresion): llevarlas al reporte.
        for w in drain_warnings():
            timings.add_warning(**w)
        timings.add_stats(*drain_stats())

        # Tamanos de los artefactos producidos: util para comparar corridas
        # (p.ej. bitrate efectivo del doblaje) sin inspeccionar el disco.
        timings.set_outputs(
            dubbed_audio_wav_bytes=dubbed_audio.stat().st_size,
            output_video_bytes=output_video.stat().st_size,
            output_video=str(output_video),
        )

        checkpoint = self._mark_stage_done(checkpoint, request, STAGE_FINALIZED)
        checkpoint_store.save(checkpoint)
        return output_video

    def _group_translated_segments(
        self, translated_segments: list[TranslatedSegment]
    ) -> list[SynthesisGroup]:
        if self._group_segments and translated_segments:
            return group_segments_for_synthesis(
                translated_segments,
                max_gap_seconds=self._group_max_gap,
                max_group_chars=self._group_max_chars,
            )
        return [
            SynthesisGroup(
                start=s.start,
                end=s.end,
                speaker_id=s.speaker_id,
                text=s.translated_text,
                member_ids=(s.id,),
            )
            for s in translated_segments
        ]

    @staticmethod
    def _validate_request(request: TranslateVideoRequest) -> None:
        if not request.input_video.exists():
            raise InvalidVideoFileError(f"No existe el archivo: {request.input_video}")
        if request.input_video.suffix.lower() not in SUPPORTED_EXTENSIONS:
            raise InvalidVideoFileError(
                f"Extension no soportada '{request.input_video.suffix}'. "
                f"Soportadas: {sorted(SUPPORTED_EXTENSIONS)}"
            )


def _is_valid_wav(path: Path) -> bool:
    """Verifica que un archivo WAV existe y no esta vacio."""
    return path.exists() and path.stat().st_size > 0
