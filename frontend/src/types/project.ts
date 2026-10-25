import type { VideoFormat } from '../lib/videoFormats'
import type { Objective } from '../lib/objectives'

export type ServiceType = 'dubbing' | 'subtitles' | 'transcription' | 'tts' | 'micro_video'

export type OutputMode =
  | 'subtitles_only'
  | 'burn_subtitles'
  | 'soft_subtitles'
  | 'dubbed'

export type ProjectStatus =
  | 'queued'
  | 'downloading'
  | 'running'
  | 'completed'
  | 'failed'

export interface Project {
  id: string
  user_id: string
  name: string
  service_type: ServiceType
  source_type: string
  source_url: string | null
  output_mode: OutputMode
  config: Record<string, unknown>
  status: ProjectStatus
  celery_task_id: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  /** Not a DB column -- filled in from pipeline_timings.json (see
   * status_reader.py) so the projects list doesn't need a second /status
   * call per row. Null until the run has actually written that file. */
  total_seconds: number | null
  run_id: string | null
}

export interface ProjectListResponse {
  items: Project[]
  total: number
  page: number
  page_size: number
}

export interface ProjectListParams {
  status?: ProjectStatus
  service_type?: ServiceType
  page?: number
  page_size?: number
}

/**
 * Shape of an individual pipeline stage as surfaced by `pipeline_timings.json`.
 * The backend stub for M1 will not populate this yet, so consumers must treat
 * every field here as possibly absent and render defensively.
 */
export interface ProjectStage {
  name: string
  status?: string
  seconds?: number
  [key: string]: unknown
}

/** Matches `PipelineTimings.as_dict()["current_stage"]` — present only while a
 * stage is in flight, absent (null) when idle/completed. It is an object
 * (`{name, started_at}`), not a bare stage name string. */
export interface CurrentStage {
  name: string
  started_at?: string
  [key: string]: unknown
}

/** Matches an entry in `PipelineTimings.as_dict()["warnings"]` (added via
 * `timings.add_warning(**w)`). Always has a `source`, plus arbitrary extra
 * fields that vary by warning type (e.g. `segment_index`, `overflow_seconds`
 * for `audio_mixing.overflow_after_compression`) — not a plain string. */
export interface PipelineWarning {
  source: string
  [key: string]: unknown
}

export interface ProjectStatusResponse {
  db_status: ProjectStatus
  run_id: string | null
  completed: boolean | null
  current_stage: CurrentStage | null
  stages: ProjectStage[] | Record<string, unknown> | null
  total_seconds: number | null
  realtime_factor: number | null
  warnings: PipelineWarning[] | null
}

export type DownloadArtifact =
  | 'video'
  | 'srt_source'
  | 'srt_target'
  | 'transcript_srt'
  | 'transcript_text'
  | 'summary_text'
  | 'speech_audio'

export interface GlossaryEntry {
  term: string
  translation: string
}

export interface CreateDubbingProjectInput {
  name: string
  /** Exactamente uno de `file`/`source_url` -- ver components/media/MediaSourceInput.tsx. */
  file?: File
  source_url?: string
  context_prompt?: string
  tone?: string
  glossary?: Record<string, string>
  source_lang?: string
  target_lang?: string
  diarize?: boolean
  min_speakers?: number
  max_speakers?: number
}

export interface CreateSubtitlesProjectInput {
  name: string
  /** Exactamente uno de `file`/`source_url` -- ver components/media/MediaSourceInput.tsx. */
  file?: File
  source_url?: string
  /** subtitles_only ".srt" / burn_subtitles (incrustados) / soft_subtitles
   * (pista seleccionable) -- "dubbed" no aplica a este servicio. */
  output_mode: Exclude<OutputMode, 'dubbed'>
  context_prompt?: string
  tone?: string
  glossary?: Record<string, string>
  source_lang?: string
  target_lang?: string
}

export interface CreateTranscriptionProjectInput {
  name: string
  /** Exactamente uno de `file`/`source_url` -- ver components/media/MediaSourceInput.tsx. */
  file?: File
  source_url?: string
  /** Vacio = detectar automaticamente (el backend lo trata como None, ver
   * `Transcriber.transcribe(language_hint=None)`). */
  source_lang?: string
  /** Ademas de la transcripcion completa, genera un resumen con los
   * highlights via LLM (ver TranscribeMediaUseCase). */
  include_summary?: boolean
}

export type TtsVoiceOption = 'public_female' | 'public_male' | 'own'

export interface CreateTtsProjectInput {
  name: string
  text: string
  /** Idioma en el que se sintetiza el audio. */
  target_lang?: string
  /** "public_female" (voz de locutora, por defecto) / "public_male" (voz de
   * locutor) / "own" (usa `voiceFile` como voz de referencia). */
  voice_option: TtsVoiceOption
  voiceFile?: File
}

export interface CreateMicroVideoProjectInput {
  name: string
  text: string
  /** Para que se hace el video (ver RM-42 y lib/objectives.ts). Condiciona lo
   * que el editor propone; el backend lo guarda para poder preguntar despues
   * que perfil se uso de verdad. */
  objective: Objective
  /** Relacion de aspecto de salida (ver RM-42 y lib/videoFormats). La elige el
   * objetivo; el lienzo del editor ya dibuja con esta misma forma. */
  video_format: VideoFormat
  /** Al menos un item, imagen o clip de video -- si hay varios, el video los
   * recorre en orden (ver RM-29, RM-36). Cada clip ocupa su propia duracion
   * real (recortada); las imagenes se reparten el tiempo restante. */
  mediaFiles: File[]
  /** Idioma en el que se narra el texto. Obligatorio a proposito: el valor
   * por defecto lo decide el editor (ver lib/objectives.ts), no esta capa.
   * Tenerlo tambien aqui como `?? 'es'` creaba dos fuentes de verdad, y al
   * condicionar los defaults por objetivo (RM-42) una de las dos quedaba
   * sin aplicar. Mismo criterio para los tres campos de caption de abajo. */
  target_lang: string
  /** "public_female" (voz de locutora, por defecto) / "public_male" (voz de
   * locutor) / "own" (usa `voiceFile` como voz de referencia). */
  voice_option: TtsVoiceOption
  voiceFile?: File
  /** undefined/null = el video dura lo que tarda la narracion. Si se fija,
   * el audio se acelera para encajar (mas largo) o se mantiene la imagen el
   * tiempo restante (mas corto). */
  target_duration_seconds?: number
  /** Color del resaltado de los captions, "#RRGGBB" -- ver caption_highlight_style. */
  caption_bg_color: string
  /** "background" (default) = caja de fondo de ese color detras del texto
   * blanco. "text_color" = el texto queda de ese color, sin caja. */
  caption_highlight_style: CaptionHighlightStyle
  /** Color del texto, "#RRGGBB" -- solo tiene efecto en "background" y
   * "karaoke_background" (ahi caption_bg_color es pura y exclusivamente el
   * color de la caja/resaltado, no del texto). Blanco por defecto. */
  caption_text_color: string
  /** Id de una pista de música (ver MUSIC_OPTIONS en NewMicroVideoProjectPage),
   * o undefined = sin música de fondo. */
  background_music?: string
  /** Rango [start, end) dentro de la pista a usar como fuente del loop de
   * fondo (ver RM-28) -- undefined = la pista completa. */
  background_music_start?: number
  background_music_end?: number
  /** Volumen lineal (no dB) de la música de fondo al mezclarla, 0-1. */
  background_music_volume?: number
  /** Volumen lineal (no dB) de la narración, 1.0 = sin cambios. */
  narration_volume?: number
  /** Textos superpuestos posicionables en el editor (ver RM-28). */
  text_overlays?: TextOverlay[]
  /** Posición del caption (fracción 0-1, centro), arrastrable en el editor
   * igual que un overlay de texto. */
  caption_x?: number
  caption_y?: number
  /** Encuadre (pan/zoom) elegido por el usuario para cada item, paralelo a
   * `mediaFiles` -- mismo orden, mismo índice (ver RM-30). En un item de
   * video puede incluir además `keep_ranges` (ver RM-36/RM-40). */
  media_adjustments?: MediaAdjustment[]
  /** Emojis superpuestos posicionables en el editor (ver RM-32). */
  emoji_overlays?: EmojiOverlay[]
}

export type CaptionHighlightStyle = 'background' | 'text_color' | 'karaoke' | 'karaoke_background'

/** Un texto libre superpuesto al micro-video, posicionado a mano por el
 * usuario (ver RM-28). `x`/`y` son fracciones 0-1 del ancho/alto del video
 * -- el CENTRO del texto, no la esquina. */
export interface TextOverlay {
  id: string
  text: string
  x: number
  y: number
  bold: boolean
  font_family: string
  font_size: number
  color: string
  fade: boolean
  /** Estilo visual adicional (ver RM-33) -- 'flat' = comportamiento previo. */
  text_style: TextStyle
  /** Segundo color, su significado depende de text_style: color final del
   * degradado ('gradient'), color del brillo ('neon_glow'), o color del
   * contorno ('colored_outline'). Ignorado en cualquier otro estilo. */
  accent_color: string
}

/** Estilos de texto preestablecidos (ver RM-33) -- basados en las
 * tendencias más comunes en contenido corto viral de 2026. */
export type TextStyle =
  | 'flat'
  | 'hard_shadow'
  | 'thick_outline'
  | 'gradient'
  | 'long_shadow'
  | 'hollow'
  | 'neon_glow'
  | 'colored_outline'

/** Un emoji superpuesto al micro-video, posicionado a mano por el usuario
 * (ver RM-32). `x`/`y` son fracciones 0-1 del ancho/alto del video -- el
 * CENTRO del emoji, mismo criterio que TextOverlay. No es texto libre:
 * `emoji_id` referencia uno de un set curado de imágenes bundleadas (este
 * sistema no puede renderizar emoji Unicode vía el pipeline de texto del
 * backend). */
export interface EmojiOverlay {
  id: string
  emoji_id: string
  x: number
  y: number
  size: number
  fade: boolean
}

/** Encuadre (pan/zoom) de una imagen o clip de video del micro-video,
 * elegido a mano por el usuario en el editor (ver RM-30). `offset_x`/
 * `offset_y` son fracciones 0-1 de cuánto se desplaza la ventana de recorte
 * (0 = borde superior/izquierdo visible, 1 = borde inferior/derecho
 * visible); `zoom` >= 1.0 acerca la imagen/clip antes de recortarlo.
 * Defaults (0.5, 0.5, 1.0) reproducen el recorte centrado sin zoom manual
 * (comportamiento previo). */
export interface MediaAdjustment {
  offset_x: number
  offset_y: number
  zoom: number
  /** Estilo de color preestablecido (ver RM-31) -- 'none' = imagen/clip original. */
  filter_preset: FilterPreset
  /** Solo para items de VIDEO (ver RM-36/RM-40): tramo(s) [start, end) del
   * clip a conservar en la línea de tiempo, en orden cronológico y sin
   * solaparse -- lo que queda afuera de estos rangos se descarta (p.ej. un
   * tramo del medio que el usuario decidió cortar). undefined = el clip
   * completo. El frontend siempre conoce la duración real una vez cargada
   * la metadata, así que nunca manda un `end` abierto -- eso solo lo
   * acepta el backend por robustez/compatibilidad con datos previos.
   * Ignorados en un item de imagen. */
  keep_ranges?: [number, number][]
}

/** Estilos de color preestablecidos para imágenes del micro-video (ver
 * RM-31) -- basados en los presets más usados en editores de video cortos
 * (VSCO/CapCut/Lightroom). */
export type FilterPreset = 'none' | 'sepia' | 'bw' | 'cool' | 'warm' | 'dramatic'
