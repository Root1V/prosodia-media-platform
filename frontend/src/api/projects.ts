import { apiClient } from './client'
import type {
  CreateDubbingProjectInput,
  CreateMicroVideoProjectInput,
  CreateSubtitlesProjectInput,
  CreateTranscriptionProjectInput,
  CreateTtsProjectInput,
  DownloadArtifact,
  Project,
  ProjectListParams,
  ProjectListResponse,
  ProjectStatusResponse,
} from '../types/project'

export async function fetchProjects(
  params: ProjectListParams,
): Promise<ProjectListResponse> {
  const { data } = await apiClient.get<ProjectListResponse>('/projects', {
    params,
  })
  return data
}

export async function fetchProject(id: string): Promise<Project> {
  const { data } = await apiClient.get<Project>(`/projects/${id}`)
  return data
}

export async function fetchProjectStatus(
  id: string,
): Promise<ProjectStatusResponse> {
  const { data } = await apiClient.get<ProjectStatusResponse>(
    `/projects/${id}/status`,
  )
  return data
}

export async function deleteProject(id: string): Promise<void> {
  await apiClient.delete(`/projects/${id}`)
}

export async function resumeProject(id: string): Promise<Project> {
  const { data } = await apiClient.post<Project>(`/projects/${id}/resume`)
  return data
}

/**
 * Reads an artifact's raw text content for inline display (as opposed to
 * `downloadProjectArtifact`, which saves it to disk) -- only meaningful for
 * text artifacts like `summary_text`.
 */
export async function fetchProjectArtifactText(
  id: string,
  artifact: DownloadArtifact,
): Promise<string> {
  const { data } = await apiClient.get<string>(`/projects/${id}/download/${artifact}`, {
    responseType: 'text',
  })
  return data
}

const ARTIFACT_FILENAME_FALLBACK: Record<DownloadArtifact, string> = {
  video: 'video.mp4',
  srt_source: 'subtitles.en.srt',
  srt_target: 'subtitles.es.srt',
  transcript_srt: 'transcript.srt',
  transcript_text: 'transcript.txt',
  summary_text: 'summary.txt',
  speech_audio: 'speech.wav',
}

/**
 * Downloads an artifact through the authenticated axios instance (a plain
 * `<a href="/api/...">` can't carry the Bearer token) and saves it via a
 * temporary object URL + anchor click.
 */
export async function downloadProjectArtifact(
  id: string,
  artifact: DownloadArtifact,
): Promise<void> {
  const response = await apiClient.get(`/projects/${id}/download/${artifact}`, {
    responseType: 'blob',
  })
  const contentDisposition = String(response.headers['content-disposition'] ?? '')
  const filenameMatch = /filename="?([^"]+)"?/.exec(contentDisposition)
  const filename = filenameMatch?.[1] ?? ARTIFACT_FILENAME_FALLBACK[artifact]

  const blobUrl = window.URL.createObjectURL(response.data as Blob)
  const link = document.createElement('a')
  link.href = blobUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.URL.revokeObjectURL(blobUrl)
}

export async function createDubbingProject(
  input: CreateDubbingProjectInput,
  onUploadProgress?: (percent: number) => void,
): Promise<Project> {
  const formData = new FormData()
  formData.set('name', input.name)
  formData.set('service_type', 'dubbing')
  formData.set('output_mode', 'dubbed')
  if (input.file) formData.set('file', input.file)
  if (input.source_url) formData.set('source_url', input.source_url)
  formData.set('context_prompt', input.context_prompt ?? '')
  formData.set('tone', input.tone ?? '')
  formData.set('glossary', JSON.stringify(input.glossary ?? {}))
  formData.set('source_lang', input.source_lang ?? 'en')
  formData.set('target_lang', input.target_lang ?? 'es')
  formData.set('diarize', String(input.diarize ?? false))
  if (input.diarize) {
    if (input.min_speakers !== undefined) {
      formData.set('min_speakers', String(input.min_speakers))
    }
    if (input.max_speakers !== undefined) {
      formData.set('max_speakers', String(input.max_speakers))
    }
  }

  const { data } = await apiClient.post<Project>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}

export async function createSubtitlesProject(
  input: CreateSubtitlesProjectInput,
  onUploadProgress?: (percent: number) => void,
): Promise<Project> {
  const formData = new FormData()
  formData.set('name', input.name)
  formData.set('service_type', 'subtitles')
  formData.set('output_mode', input.output_mode)
  if (input.file) formData.set('file', input.file)
  if (input.source_url) formData.set('source_url', input.source_url)
  formData.set('context_prompt', input.context_prompt ?? '')
  formData.set('tone', input.tone ?? '')
  formData.set('glossary', JSON.stringify(input.glossary ?? {}))
  formData.set('source_lang', input.source_lang ?? 'en')
  formData.set('target_lang', input.target_lang ?? 'es')

  const { data } = await apiClient.post<Project>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}

export async function createTtsProject(
  input: CreateTtsProjectInput,
  onUploadProgress?: (percent: number) => void,
): Promise<Project> {
  const formData = new FormData()
  formData.set('name', input.name)
  formData.set('service_type', 'tts')
  // Sin significado para TTS (no renderiza video) -- solo satisface la
  // columna NOT NULL, igual que hace la transcripcion standalone.
  formData.set('output_mode', 'subtitles_only')
  formData.set('text', input.text)
  formData.set('target_lang', input.target_lang ?? 'es')
  formData.set('voice_option', input.voice_option)
  if (input.voice_option === 'own' && input.voiceFile) {
    formData.set('file', input.voiceFile)
  }

  const { data } = await apiClient.post<Project>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}

export async function createTranscriptionProject(
  input: CreateTranscriptionProjectInput,
  onUploadProgress?: (percent: number) => void,
): Promise<Project> {
  const formData = new FormData()
  formData.set('name', input.name)
  formData.set('service_type', 'transcription')
  // No hay un output_mode propio para transcripcion (el pipeline no renderiza
  // video en este flujo) -- se usa "subtitles_only" solo para satisfacer la
  // columna NOT NULL; project_mapper.py no lo lee para este service_type.
  formData.set('output_mode', 'subtitles_only')
  if (input.file) formData.set('file', input.file)
  if (input.source_url) formData.set('source_url', input.source_url)
  formData.set('context_prompt', '')
  formData.set('glossary', '{}')
  // Vacio explicito (no se omite el campo) para que el backend lo trate como
  // "detectar automaticamente" en vez de caer en el default "en" del form.
  formData.set('source_lang', input.source_lang ?? '')
  formData.set('include_summary', String(input.include_summary ?? false))

  const { data } = await apiClient.post<Project>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}

export async function createMicroVideoProject(
  input: CreateMicroVideoProjectInput,
  onUploadProgress?: (percent: number) => void,
): Promise<Project> {
  const formData = new FormData()
  formData.set('name', input.name)
  formData.set('service_type', 'micro_video')
  // Sin significado para micro-video (no hay traduccion/doblaje) -- solo
  // satisface la columna NOT NULL, mismo patron que TTS/transcripcion.
  formData.set('output_mode', 'subtitles_only')
  // `file` es la imagen o el clip de video (obligatorio, ver RM-36) -- a
  // diferencia de TTS, aca no es una voz de referencia opcional. El orden
  // de `additional_media` ES el orden de la linea de tiempo.
  formData.set('file', input.mediaFiles[0])
  input.mediaFiles.slice(1).forEach((f) => formData.append('additional_media', f))
  formData.set('text', input.text)
  formData.set('target_lang', input.target_lang)
  formData.set('voice_option', input.voice_option)
  if (input.voice_option === 'own' && input.voiceFile) {
    formData.set('voice_file', input.voiceFile)
  }
  if (input.target_duration_seconds != null) {
    formData.set('target_duration_seconds', String(input.target_duration_seconds))
  }
  formData.set('caption_bg_color', input.caption_bg_color)
  formData.set('caption_highlight_style', input.caption_highlight_style)
  formData.set('caption_text_color', input.caption_text_color)
  if (input.background_music) {
    formData.set('background_music', input.background_music)
    if (input.background_music_start != null) {
      formData.set('background_music_start', String(input.background_music_start))
    }
    if (input.background_music_end != null) {
      formData.set('background_music_end', String(input.background_music_end))
    }
    if (input.background_music_volume != null) {
      formData.set('background_music_volume', String(input.background_music_volume))
    }
  }
  if (input.narration_volume != null) {
    formData.set('narration_volume', String(input.narration_volume))
  }
  if (input.caption_x != null) {
    formData.set('caption_x', String(input.caption_x))
  }
  if (input.caption_y != null) {
    formData.set('caption_y', String(input.caption_y))
  }
  if (input.text_overlays && input.text_overlays.length > 0) {
    formData.set(
      'text_overlays',
      JSON.stringify(
        input.text_overlays.map((overlay) => ({
          text: overlay.text,
          x: overlay.x,
          y: overlay.y,
          bold: overlay.bold,
          font_family: overlay.font_family,
          font_size: overlay.font_size,
          color: overlay.color,
          fade: overlay.fade,
          text_style: overlay.text_style,
          accent_color: overlay.accent_color,
        })),
      ),
    )
  }
  if (input.media_adjustments && input.media_adjustments.length > 0) {
    formData.set(
      'media_adjustments',
      JSON.stringify(
        input.media_adjustments.map((adjustment) => ({
          offset_x: adjustment.offset_x,
          offset_y: adjustment.offset_y,
          zoom: adjustment.zoom,
          filter_preset: adjustment.filter_preset,
          // Solo en clips de video (ver RM-36/RM-40) -- en un proyecto de
          // puras imagenes el payload queda identico al de antes.
          ...(adjustment.keep_ranges && adjustment.keep_ranges.length > 0
            ? { keep_ranges: adjustment.keep_ranges }
            : {}),
        })),
      ),
    )
  }
  if (input.emoji_overlays && input.emoji_overlays.length > 0) {
    formData.set(
      'emoji_overlays',
      JSON.stringify(
        input.emoji_overlays.map((overlay) => ({
          emoji_id: overlay.emoji_id,
          x: overlay.x,
          y: overlay.y,
          size: overlay.size,
          fade: overlay.fade,
        })),
      ),
    )
  }

  const { data } = await apiClient.post<Project>('/projects', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (!onUploadProgress || !event.total) return
      onUploadProgress(Math.round((event.loaded / event.total) * 100))
    },
  })
  return data
}
