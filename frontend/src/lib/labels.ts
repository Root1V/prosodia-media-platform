import type { OutputMode, ProjectStage, ServiceType } from '../types/project'
import type { MusicCategory } from '../types/musicTracks'

export const MUSIC_CATEGORY_LABELS: Record<MusicCategory, string> = {
  calm_meditation: 'Calma y meditación',
  commercials_professional: 'Comerciales y profesional',
  energy_pop: 'Energía y pop',
  happy_romantic: 'Felicidad y romance',
  social_network: 'Redes sociales',
}

export const SERVICE_TYPE_LABELS: Record<ServiceType, string> = {
  dubbing: 'Doblaje',
  subtitles: 'Subtítulos',
  transcription: 'Transcripción',
  tts: 'Voz y clonación',
  micro_video: 'Micro-video',
}

export const OUTPUT_MODE_LABELS: Record<OutputMode, string> = {
  subtitles_only: 'Solo subtítulos',
  burn_subtitles: 'Subtítulos incrustados',
  soft_subtitles: 'Subtítulos seleccionables',
  dubbed: 'Doblado',
}

/** Human-readable Spanish names for the pipeline's internal stage
 * identifiers (see `utils/timing.py` / `application/use_cases/translate_video.py`). */
export const STAGE_LABELS: Record<string, string> = {
  download: 'Descarga del video',
  audio_extraction: 'Extracción de audio',
  transcription: 'Transcripción',
  diarization: 'Detección de hablantes',
  speaker_profile_building: 'Perfiles de hablantes',
  translation: 'Traducción',
  subtitles_writing: 'Generación de subtítulos',
  transcript_writing: 'Escritura de transcripción',
  summarization: 'Resumen',
  text_to_speech: 'Síntesis de voz',
  audio_concatenation: 'Concatenación de audio',
  tts_synthesis: 'Síntesis de voz',
  audio_mixing_and_muxing: 'Mezcla de audio',
  rendering_dubbed: 'Renderizado del video doblado',
  rendering_soft_subtitles: 'Adjuntando subtítulos',
  rendering_burn_subtitles: 'Incrustando subtítulos',
  caption_writing: 'Generación de captions',
  media_to_video: 'Renderizado del video (imágenes y clips)',
  caption_burn: 'Incrustando captions',
  // No es una etapa del pipeline: es el tiempo que no cae en ninguna de las
  // fases medidas (extraer audio, renderizar, mover archivos). Ver
  // services/dashboard_metrics.py::reparto_de_tiempo.
  other: 'Otras etapas',
}

/** Falls back to a humanized version of the raw stage name (e.g.
 * "some_new_stage" -> "Some new stage") for any stage not in the map above
 * yet, so a future pipeline stage never renders as a raw snake_case string. */
export function getStageLabel(name: string): string {
  if (STAGE_LABELS[name]) return STAGE_LABELS[name]
  const humanized = name.replace(/_/g, ' ')
  return humanized.charAt(0).toUpperCase() + humanized.slice(1)
}

const RENDERING_STAGE_BY_MODE: Partial<Record<OutputMode, string>> = {
  dubbed: 'rendering_dubbed',
  soft_subtitles: 'rendering_soft_subtitles',
  burn_subtitles: 'rendering_burn_subtitles',
  // subtitles_only never renders a video -- no stage.
}

function pluralize(count: number, singular: string, plural: string): string {
  return count === 1 ? singular : plural
}

export const LANGUAGE_NAMES: Record<string, string> = {
  en: 'inglés',
  es: 'español',
  fr: 'francés',
  de: 'alemán',
  it: 'italiano',
  pt: 'portugués',
  ja: 'japonés',
  zh: 'chino',
  ar: 'árabe',
  ko: 'coreano',
  ru: 'ruso',
  nl: 'neerlandés',
}

/** Falls back to the raw ISO code (uppercased) for a language this map
 * doesn't know about yet, rather than showing nothing. */
function getLanguageName(code: string): string {
  return LANGUAGE_NAMES[code.toLowerCase()] ?? code.toUpperCase()
}

const GENDER_LABELS: Record<string, string> = {
  male: 'hombre',
  female: 'mujer',
}

interface RawSpeaker {
  gender?: unknown
  reference?: unknown
  [key: string]: unknown
}

/** Summarizes the `speakers` array `speaker_profile_building` reports (see
 * `SpeakerProfile` in domain/models.py): how many of each estimated gender,
 * and how many didn't get a usable voice-reference clip -- both are
 * decision-relevant for a dubbing job (e.g. "why did speaker 2 keep the
 * fallback voice?"), not just a headcount. */
function summarizeSpeakers(speakers: RawSpeaker[]): string[] {
  const parts: string[] = []
  const genderCounts = new Map<string, number>()
  let missingReference = 0

  for (const speaker of speakers) {
    const gender = typeof speaker.gender === 'string' ? speaker.gender : 'unknown'
    genderCounts.set(gender, (genderCounts.get(gender) ?? 0) + 1)
    if (speaker.reference === false) missingReference += 1
  }

  const genderSummary = [...genderCounts.entries()]
    .filter(([gender]) => GENDER_LABELS[gender])
    .map(([gender, count]) => `${count} ${pluralize(count, GENDER_LABELS[gender], `${GENDER_LABELS[gender]}s`)}`)
  if (genderSummary.length > 0) parts.push(genderSummary.join(', '))

  const undetermined = genderCounts.get('unknown') ?? 0
  if (undetermined > 0) parts.push(`${undetermined} género no determinado`)
  if (missingReference > 0) {
    parts.push(`${missingReference} sin muestra de voz`)
  }
  return parts
}

interface StageSubtitleContext {
  sourceLang?: string
  targetLang?: string
}

/** Picks the most useful metrics out of a stage's raw metadata (see
 * `pipeline_timings.json`'s `stages[]` entries) and formats them as a short,
 * human-readable summary -- e.g. "38 segmentos · 2 lotes" for translation.
 * `context` carries project-level info (source/target language) that isn't
 * part of any single stage's own JSON but is still relevant to show next to
 * one (subtitles_writing). Returns null for stages that genuinely carry
 * nothing beyond timing bookkeeping (audio_extraction,
 * audio_mixing_and_muxing, rendering_*) -- that's expected, not a missing
 * case. */
export function getStageSubtitle(stage: ProjectStage, context: StageSubtitleContext = {}): string | null {
  const parts: string[] = []
  const num = (key: string): number | null => {
    const value = stage[key]
    return typeof value === 'number' ? value : null
  }

  switch (stage.name) {
    case 'transcription': {
      const segments = num('num_segments')
      if (segments !== null) parts.push(`${segments} ${pluralize(segments, 'segmento', 'segmentos')}`)
      break
    }
    case 'text_to_speech': {
      const chunks = num('num_chunks')
      if (chunks !== null) parts.push(`${chunks} ${pluralize(chunks, 'fragmento', 'fragmentos')}`)
      break
    }
    case 'diarization': {
      const speakers = num('num_speakers')
      const turns = num('num_turns')
      if (speakers !== null) parts.push(`${speakers} ${pluralize(speakers, 'hablante', 'hablantes')}`)
      if (turns !== null) parts.push(`${turns} ${pluralize(turns, 'turno', 'turnos')}`)
      break
    }
    case 'speaker_profile_building': {
      const speakers = stage.speakers
      if (Array.isArray(speakers) && speakers.length > 0) {
        parts.push(...summarizeSpeakers(speakers as RawSpeaker[]))
      } else {
        const count = num('num_speakers')
        if (count !== null) parts.push(`${count} ${pluralize(count, 'perfil', 'perfiles')}`)
      }
      break
    }
    case 'translation': {
      const segments = num('num_segments')
      const batches = num('num_batches')
      if (segments !== null) parts.push(`${segments} ${pluralize(segments, 'segmento', 'segmentos')}`)
      if (batches !== null) parts.push(`${batches} ${pluralize(batches, 'lote', 'lotes')}`)
      break
    }
    case 'tts_synthesis': {
      const inputSegments = num('num_segments_input')
      const groups = num('num_groups')
      const jobs = num('num_jobs')
      const reduction = num('grouping_reduction_pct')
      if (inputSegments !== null && groups !== null) {
        parts.push(`${inputSegments} → ${groups} ${pluralize(groups, 'grupo', 'grupos')}`)
      } else if (groups !== null) {
        parts.push(`${groups} ${pluralize(groups, 'grupo', 'grupos')}`)
      } else if (jobs !== null) {
        parts.push(`${jobs} ${pluralize(jobs, 'trabajo', 'trabajos')}`)
      }
      if (reduction !== null) parts.push(`${reduction.toFixed(1)}% menos llamadas`)
      break
    }
    case 'subtitles_writing': {
      if (context.sourceLang && context.targetLang) {
        parts.push(`${getLanguageName(context.sourceLang)} → ${getLanguageName(context.targetLang)}`)
      }
      break
    }
    // audio_extraction, audio_mixing_and_muxing, and the rendering_* stages
    // carry no metrics of their own beyond timing -- audio_mixing_and_muxing
    // gets a cross-referenced "voices used" subtitle instead, computed in
    // StageTimeline.tsx (it needs speaker_profile_building's data, not just
    // its own stage entry).
    default:
      break
  }

  if (stage.ran_concurrently) parts.push('en paralelo')

  return parts.length > 0 ? parts.join(' · ') : null
}

/** Predicts the full ordered list of stages this project WILL go through,
 * based on its mode/diarize config, mirroring
 * `application/use_cases/translate_video.py`'s real stage sequence. The
 * backend only ever reports stages that already started/finished (see
 * `pipeline_timings.json`), so this is what lets the UI show the whole plan
 * upfront and progressively fill it in, instead of stages only appearing
 * one by one as they happen. */
export function getExpectedStageNames(
  outputMode: OutputMode,
  diarize: boolean,
  hasSourceUrl = false,
): string[] {
  const names: string[] = []
  // Los proyectos importados desde una URL pasan por una descarga previa
  // (ver ProjectStatus.DOWNLOADING en tasks/run_project.py) antes de que
  // exista pipeline_timings.json -- se antepone como su propio paso para que
  // no desaparezca del plan visible mientras el proyecto esta "Descargando".
  if (hasSourceUrl) names.push('download')
  names.push('audio_extraction', 'transcription')
  if (diarize) {
    names.push('diarization', 'speaker_profile_building')
  }
  names.push('translation', 'subtitles_writing')
  if (outputMode === 'dubbed') {
    names.push('tts_synthesis', 'audio_mixing_and_muxing')
  }
  const renderingStage = RENDERING_STAGE_BY_MODE[outputMode]
  if (renderingStage) names.push(renderingStage)
  return names
}
