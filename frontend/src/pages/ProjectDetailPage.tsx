import { useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, ArrowLeft, Download, Loader2, RotateCcw, Trash2 } from 'lucide-react'
import {
  deleteProject,
  downloadProjectArtifact,
  fetchProject,
  fetchProjectArtifactText,
  fetchProjectStatus,
  resumeProject,
} from '../api/projects'
import type { DownloadArtifact, ProjectStage } from '../types/project'
import { StageTimeline } from '../components/projects/StageTimeline'
import { Alert } from '../components/ui/Alert'
import { MediaPreview } from '../components/media/MediaPreview'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card'
import { CopyableValue } from '../components/ui/CopyableValue'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { formatDateTime, formatSecondsDuration } from '../lib/format'
import { PROJECT_STATUS_BADGE_VARIANT, PROJECT_STATUS_LABELS, isActiveStatus } from '../lib/status'
import {
  OUTPUT_MODE_LABELS,
  SERVICE_TYPE_LABELS,
  getExpectedStageNames,
  getStageLabel,
} from '../lib/labels'

function normalizeStages(
  stages: ProjectStage[] | Record<string, unknown> | null,
): ProjectStage[] {
  if (!stages) return []
  if (Array.isArray(stages)) return stages
  return Object.entries(stages).map(([name, value]) => ({
    name,
    ...(typeof value === 'object' && value !== null ? value : { status: String(value) }),
  }))
}

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()

  const projectQuery = useQuery({
    queryKey: ['projects', id],
    queryFn: () => fetchProject(id as string),
    enabled: Boolean(id),
  })

  const statusQuery = useQuery({
    queryKey: ['projects', id, 'status'],
    queryFn: () => fetchProjectStatus(id as string),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const dbStatus = query.state.data?.db_status
      // 1.5s (not 3s): short stages (a few seconds) can otherwise finish
      // entirely between two polls and never get sampled while active --
      // StageTimeline also holds a brief "in progress" reveal on top of
      // this so even a stage this still misses gets visual feedback.
      return dbStatus && isActiveStatus(dbStatus) ? 1500 : false
    },
  })

  const dbStatusForSummary = statusQuery.data?.db_status ?? projectQuery.data?.status
  const summaryQuery = useQuery({
    queryKey: ['projects', id, 'summary'],
    queryFn: () => fetchProjectArtifactText(id as string, 'summary_text'),
    enabled: Boolean(
      id &&
        projectQuery.data?.service_type === 'transcription' &&
        projectQuery.data?.config.include_summary &&
        dbStatusForSummary === 'completed',
    ),
  })

  const deleteMutation = useMutation({
    mutationFn: () => deleteProject(id as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] })
      navigate('/projects')
    },
  })

  const resumeMutation = useMutation({
    mutationFn: () => resumeProject(id as string),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects', id] })
    },
  })

  const [downloading, setDownloading] = useState<DownloadArtifact | null>(null)
  const [downloadError, setDownloadError] = useState<string | null>(null)

  async function handleDownload(artifact: DownloadArtifact) {
    setDownloading(artifact)
    setDownloadError(null)
    try {
      await downloadProjectArtifact(id as string, artifact)
    } catch {
      setDownloadError('No se pudo descargar el archivo. Intenta de nuevo.')
    } finally {
      setDownloading(null)
    }
  }

  function handleDelete() {
    if (window.confirm('¿Seguro que quieres eliminar este proyecto? Esta acción no se puede deshacer.')) {
      deleteMutation.mutate()
    }
  }

  if (projectQuery.isLoading) {
    return <p className="text-sm text-muted-foreground">Cargando proyecto…</p>
  }

  if (projectQuery.isError || !projectQuery.data) {
    return (
      <div className="flex flex-col items-center gap-3 py-12 text-center">
        <p className="text-sm text-muted-foreground">No se pudo cargar el proyecto.</p>
        <Button variant="outline" onClick={() => navigate('/projects')}>
          Volver a proyectos
        </Button>
      </div>
    )
  }

  const project = projectQuery.data
  const status = statusQuery.data
  const dbStatus = status?.db_status ?? project.status
  const stages = normalizeStages(status?.stages ?? null)
  const isTranscription = project.service_type === 'transcription'
  const isTts = project.service_type === 'tts'
  const isMicroVideo = project.service_type === 'micro_video'
  // TTS y micro-video standalone reciben texto/imagen, nunca una URL -- solo
  // dubbing/subtitles/transcription pueden haberse creado desde una URL (ver
  // MediaSourceInput).
  const hasSourceUrl = !isTts && !isMicroVideo && Boolean(project.source_url)
  // La transcripcion, el TTS y el micro-video standalone no traducen ni
  // dependen de output_mode -- su plan de etapas es fijo (ver
  // TranscribeMediaUseCase/SynthesizeTextUseCase/GenerateMicroVideoUseCase).
  const includesSummary = isTranscription && Boolean(project.config.include_summary)
  const expectedStageNames = isTranscription
    ? [
        ...(hasSourceUrl ? ['download'] : []),
        'audio_extraction',
        'transcription',
        ...(includesSummary ? ['summarization'] : []),
      ]
    : isTts
      ? ['text_to_speech', 'audio_concatenation']
      : isMicroVideo
        ? ['text_to_speech', 'audio_concatenation', 'caption_writing', 'media_to_video', 'caption_burn']
        : getExpectedStageNames(project.output_mode, Boolean(project.config.diarize), hasSourceUrl)
  // Solo doblaje/subtitulos con output_mode distinto de "subtitles_only"
  // producen un video real -- subtitles_only nunca renderiza (solo .srt).
  // Micro-video siempre produce un video (su propio output_mode es un valor
  // dummy, no tiene significado para este servicio).
  const hasVideoOutput =
    isMicroVideo || (!isTranscription && !isTts && project.output_mode !== 'subtitles_only')

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <button
        type="button"
        onClick={() => navigate('/projects')}
        className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Volver a proyectos
      </button>

      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold">{project.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge variant="secondary">{SERVICE_TYPE_LABELS[project.service_type]}</Badge>
            {/* output_mode es un valor interno sin significado para los servicios
                sin video (siempre "subtitles_only", solo para satisfacer la columna
                NOT NULL) -- mostrarlo confundiria mas de lo que aclara. */}
            {!isTranscription && !isTts && !isMicroVideo && (
              <Badge variant="outline">{OUTPUT_MODE_LABELS[project.output_mode]}</Badge>
            )}
            <Badge variant={PROJECT_STATUS_BADGE_VARIANT[dbStatus]}>
              {isActiveStatus(dbStatus) && <Loader2 className="mr-1 h-3 w-3 animate-spin" />}
              {PROJECT_STATUS_LABELS[dbStatus]}
            </Badge>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          {/* Tambien con una corrida interrumpida (RM-44/RM-45): la fila sigue
              diciendo "running", pero no hay nadie procesandola. Sin esto el
              proyecto se queda sin salida posible. */}
          {(dbStatus === 'failed' || status?.interrupted) && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
            >
              <RotateCcw className="h-4 w-4" />
              Reintentar
            </Button>
          )}
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
          >
            <Trash2 className="h-4 w-4" />
            Eliminar
          </Button>
        </div>
      </div>

      {status?.interrupted ? (
        <Alert variant="error">
          <div className="flex items-start gap-2">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="flex flex-col gap-1">
              <p className="font-medium">La ejecución se interrumpió</p>
              <p className="text-sm">
                {status.current_stage?.name
                  ? `Se cortó en la etapa "${getStageLabel(status.current_stage.name)}". `
                  : 'Se cortó antes de completar la primera etapa. '}
                El proceso que la ejecutaba dejó de responder, así que no va a avanzar sola.
                Usa <strong>Reintentar</strong> para lanzarla de nuevo.
              </p>
            </div>
          </div>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Progreso</CardTitle>
        </CardHeader>
        <CardContent>
          <StageTimeline
            expectedStageNames={expectedStageNames}
            stages={stages}
            currentStageName={status?.current_stage?.name}
            dbStatus={dbStatus}
            sourceLang={typeof project.config.source_lang === 'string' ? project.config.source_lang : undefined}
            targetLang={typeof project.config.target_lang === 'string' ? project.config.target_lang : undefined}
            errorMessage={project.error_message}
          />
        </CardContent>
      </Card>

      {dbStatus === 'completed' && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Descargas</CardTitle>
          </CardHeader>
          <CardContent>
            {isTts && (
              <div className="mb-4">
                <MediaPreview projectId={id as string} artifact="speech_audio" kind="audio" />
              </div>
            )}
            {hasVideoOutput && (
              <div className="mb-4">
                <MediaPreview projectId={id as string} artifact="video" kind="video" />
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              {isTranscription ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload('transcript_srt')}
                    disabled={downloading === 'transcript_srt'}
                  >
                    <Download className="h-4 w-4" />
                    Transcripción (SRT)
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload('transcript_text')}
                    disabled={downloading === 'transcript_text'}
                  >
                    <Download className="h-4 w-4" />
                    Transcripción (texto)
                  </Button>
                  {includesSummary && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDownload('summary_text')}
                      disabled={downloading === 'summary_text'}
                    >
                      <Download className="h-4 w-4" />
                      Resumen (texto)
                    </Button>
                  )}
                </>
              ) : isTts ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload('speech_audio')}
                  disabled={downloading === 'speech_audio'}
                >
                  <Download className="h-4 w-4" />
                  Audio (WAV)
                </Button>
              ) : isMicroVideo ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleDownload('video')}
                  disabled={downloading === 'video'}
                >
                  <Download className="h-4 w-4" />
                  Video
                </Button>
              ) : (
                <>
                  {project.output_mode !== 'subtitles_only' && (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => handleDownload('video')}
                      disabled={downloading === 'video'}
                    >
                      <Download className="h-4 w-4" />
                      Video
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload('srt_source')}
                    disabled={downloading === 'srt_source'}
                  >
                    <Download className="h-4 w-4" />
                    Subtítulos (original)
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => handleDownload('srt_target')}
                    disabled={downloading === 'srt_target'}
                  >
                    <Download className="h-4 w-4" />
                    Subtítulos (traducidos)
                  </Button>
                </>
              )}
            </div>
            {downloadError && <p className="mt-2 text-sm text-destructive">{downloadError}</p>}
            {includesSummary && (
              <div className="mt-4 border-t border-border pt-4">
                <p className="mb-2 text-xs uppercase tracking-wide text-muted-foreground">
                  Resumen
                </p>
                {summaryQuery.isLoading && (
                  <p className="text-sm text-muted-foreground">Cargando resumen…</p>
                )}
                {summaryQuery.isError && (
                  <p className="text-sm text-destructive">No se pudo cargar el resumen.</p>
                )}
                {summaryQuery.data && (
                  <p className="whitespace-pre-line text-sm">{summaryQuery.data}</p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Detalles</CardTitle>
        </CardHeader>
        <CardContent>
          <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Creado
              </dt>
              <dd className="mt-1 text-sm">{formatDateTime(project.created_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Iniciado
              </dt>
              <dd className="mt-1 text-sm">{formatDateTime(project.started_at)}</dd>
            </div>
            <div>
              <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                Completado
              </dt>
              <dd className="mt-1 text-sm">{formatDateTime(project.completed_at)}</dd>
            </div>
            {status?.total_seconds != null && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  Duración total
                </dt>
                <dd className="mt-1 text-sm">{formatSecondsDuration(status.total_seconds)}</dd>
              </div>
            )}
            {status && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  Factor tiempo real
                </dt>
                <dd className="mt-1 text-sm">
                  {status.realtime_factor !== null ? status.realtime_factor.toFixed(2) : '—'}
                </dd>
              </div>
            )}
            {status?.run_id && (
              <div>
                <dt className="text-xs uppercase tracking-wide text-muted-foreground">
                  ID de ejecución
                </dt>
                <dd className="mt-1 font-mono text-sm">
                  <CopyableValue value={status.run_id} />
                </dd>
              </div>
            )}
          </dl>

          {status?.warnings && status.warnings.length > 0 && (
            <div className="mt-4 flex flex-col gap-2">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                Advertencias
              </p>
              <ul className="list-inside list-disc text-sm text-warning">
                {status.warnings.map((warning, index) => {
                  const { source, ...details } = warning
                  const detailsText = Object.entries(details)
                    .map(([key, value]) => `${key}=${String(value)}`)
                    .join(', ')
                  return (
                    <li key={index}>
                      <span className="font-medium">{source}</span>
                      {detailsText && (
                        <span className="text-muted-foreground"> — {detailsText}</span>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
