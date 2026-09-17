import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { createMicroVideoProject } from '../api/projects'
import { fetchMusicTracks } from '../api/musicTracks'
import { fetchEmojiSampleUrl, fetchMusicSampleUrl } from '../api/samples'
import { EMOJI_PALETTE } from '../lib/emojiPalette'
import { TextOverlayCanvas } from '../components/media/TextOverlayCanvas'
import type { CaptionPreview } from '../components/media/TextOverlayCanvas'
import { VideoSegmentTimeline } from '../components/media/VideoSegmentTimeline'
import { EditorBottomTracks } from '../components/microVideoEditor/EditorBottomTracks'
import { EditorLeftToolbar } from '../components/microVideoEditor/EditorLeftToolbar'
import { EditorRightPanel } from '../components/microVideoEditor/EditorRightPanel'
import { EditorTopBar } from '../components/microVideoEditor/EditorTopBar'
import type { EditorTool } from '../components/microVideoEditor/types'
import { Alert } from '../components/ui/Alert'
import { getErrorMessage } from '../lib/errors'
import { isVideoFile } from '../lib/mediaKind'
import type {
  CaptionHighlightStyle,
  EmojiOverlay,
  MediaAdjustment,
  TextOverlay,
  TtsVoiceOption,
} from '../types/project'

function makeMediaAdjustment(): MediaAdjustment {
  return { offset_x: 0.5, offset_y: 0.5, zoom: 1.0, filter_preset: 'none' }
}

function moveItem<T>(items: T[], from: number, to: number): T[] {
  const copy = [...items]
  const [moved] = copy.splice(from, 1)
  copy.splice(to, 0, moved)
  return copy
}

function makeOverlay(): TextOverlay {
  return {
    id: crypto.randomUUID(),
    text: '',
    x: 0.5,
    y: 0.5,
    bold: false,
    font_family: 'Arial',
    font_size: 64,
    color: '#FFFFFF',
    fade: false,
    text_style: 'flat',
    accent_color: '#FFFFFF',
  }
}

function makeEmojiOverlay(emojiId: string): EmojiOverlay {
  return { id: crypto.randomUUID(), emoji_id: emojiId, x: 0.5, y: 0.5, size: 0.15, fade: false }
}

export function NewMicroVideoProjectPage() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [targetLang, setTargetLang] = useState('es')
  const [mediaFiles, setMediaFiles] = useState<File[]>([])
  const [mediaAdjustments, setMediaAdjustments] = useState<MediaAdjustment[]>([])
  const [activeMediaIndex, setActiveMediaIndex] = useState(0)
  // Duracion real de cada clip de video (ver RM-36), sondeada por el
  // lienzo al cargar su metadata -- por REFERENCIA de archivo (no por
  // indice, que cambia al reordenar/quitar items). Las imagenes nunca
  // tienen entrada.
  const [clipDurationsByFile, setClipDurationsByFile] = useState<Map<File, number>>(new Map())
  const [voiceOption, setVoiceOption] = useState<TtsVoiceOption>('public_female')
  const [voiceFile, setVoiceFile] = useState<File | null>(null)
  const [targetDuration, setTargetDuration] = useState<number | null>(null)
  const [captionBgColor, setCaptionBgColor] = useState('#000000')
  const [captionTextColor, setCaptionTextColor] = useState('#FFFFFF')
  const [highlightStyle, setHighlightStyle] = useState<CaptionHighlightStyle>('background')
  const [backgroundMusic, setBackgroundMusic] = useState<string | null>(null)
  const [musicStart, setMusicStart] = useState(0)
  const [musicEnd, setMusicEnd] = useState<number | undefined>(undefined)
  const [musicPreviewUrl, setMusicPreviewUrl] = useState<string | null>(null)
  const [textOverlays, setTextOverlays] = useState<TextOverlay[]>([])
  const [selectedOverlayId, setSelectedOverlayId] = useState<string | null>(null)
  const [emojiOverlays, setEmojiOverlays] = useState<EmojiOverlay[]>([])
  const [selectedEmojiOverlayId, setSelectedEmojiOverlayId] = useState<string | null>(null)
  const [emojiImageUrls, setEmojiImageUrls] = useState<Record<string, string>>({})
  const [mediaUrl, setMediaUrl] = useState<string | null>(null)
  const [activeTool, setActiveTool] = useState<EditorTool>('media')
  // Panel de ajustes como hoja inferior en mobile/tablet (ver RM-20,
  // EditorRightPanel) -- irrelevante en desktop, ahi el panel siempre esta
  // visible sin importar esto. Arranca cerrado: recien se abre al tocar
  // una herramienta.
  const [mobilePanelOpen, setMobilePanelOpen] = useState(false)
  const [narrationVolume, setNarrationVolume] = useState(1.0)
  const [musicVolume, setMusicVolume] = useState(0.12)
  const [captionX, setCaptionX] = useState(0.5)
  const [captionY, setCaptionY] = useState(0.85)
  // Pedido puntual de salto de posicion en el preview (ver RM-40, doble
  // clic en VideoSegmentTimeline) -- `nonce` distinto en cada pedido para
  // que dos saltos al MISMO segundo tambien disparen el efecto en
  // TextOverlayCanvas.
  const [seekRequest, setSeekRequest] = useState<{ time: number; nonce: number } | null>(null)
  // Posicion actual de reproduccion del clip de video activo (ver RM-40) --
  // usada para dibujar el indicador movil en VideoSegmentTimeline.
  const [playheadTime, setPlayheadTime] = useState(0)

  const { data: musicTracks = [] } = useQuery({
    queryKey: ['music-tracks'],
    queryFn: () => fetchMusicTracks(),
  })

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  useEffect(() => {
    // El lienzo muestra el item ACTIVO (elegido en MediaPanel, ver RM-30)
    // como referencia para posicionar overlays/subtitulos (que son
    // globales, no por-item -- ver RM-29) y para ajustar su encuadre.
    const activeMedia = mediaFiles[activeMediaIndex]
    if (!activeMedia) {
      setMediaUrl(null)
      return
    }
    const url = URL.createObjectURL(activeMedia)
    setMediaUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [mediaFiles, activeMediaIndex])

  useEffect(() => {
    setMusicStart(0)
    setMusicEnd(undefined)
    if (!backgroundMusic) {
      setMusicPreviewUrl(null)
      return
    }
    let cancelled = false
    let objectUrl: string | null = null
    fetchMusicSampleUrl(backgroundMusic).then((url) => {
      if (cancelled) {
        URL.revokeObjectURL(url)
        return
      }
      objectUrl = url
      setMusicPreviewUrl(url)
    })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [backgroundMusic])

  useEffect(() => {
    // Precarga las URLs (blob) de TODO el set curado una sola vez -- son
    // pocas imagenes chicas (72x72), no vale la pena cargarlas bajo demanda
    // por emoji individual (ver RM-32).
    let cancelled = false
    const urls: string[] = []
    Promise.all(
      EMOJI_PALETTE.map(async (item) => {
        const url = await fetchEmojiSampleUrl(item.id)
        urls.push(url)
        return [item.id, url] as const
      }),
    ).then((entries) => {
      if (cancelled) {
        urls.forEach((url) => URL.revokeObjectURL(url))
        return
      }
      setEmojiImageUrls(Object.fromEntries(entries))
    })
    return () => {
      cancelled = true
      urls.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [])

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Ingresa un nombre para el proyecto.')
      return
    }
    if (mediaFiles.length === 0) {
      setError('Sube al menos una imagen o un video.')
      return
    }
    if (!text.trim()) {
      setError('Escribe el texto que quieres narrar.')
      return
    }
    if (voiceOption === 'own' && !voiceFile) {
      setError('Sube tu voz de referencia o elige una de las voces públicas.')
      return
    }

    setError(null)
    setIsSubmitting(true)
    setUploadProgress(0)

    try {
      const project = await createMicroVideoProject(
        {
          name: name.trim(),
          text: text.trim(),
          mediaFiles,
          target_lang: targetLang,
          voice_option: voiceOption,
          voiceFile: voiceFile ?? undefined,
          target_duration_seconds: targetDuration ?? undefined,
          caption_bg_color: captionBgColor,
          caption_highlight_style: highlightStyle,
          caption_text_color: captionTextColor,
          background_music: backgroundMusic ?? undefined,
          background_music_start: backgroundMusic ? musicStart : undefined,
          background_music_end: backgroundMusic ? musicEnd : undefined,
          background_music_volume: backgroundMusic ? musicVolume : undefined,
          narration_volume: narrationVolume,
          text_overlays: textOverlays,
          caption_x: captionX,
          caption_y: captionY,
          media_adjustments: mediaAdjustments,
          emoji_overlays: emojiOverlays,
        },
        setUploadProgress,
      )
      navigate(`/projects/${project.id}`)
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo crear el proyecto. Intenta de nuevo.'))
      setIsSubmitting(false)
      setUploadProgress(null)
    }
  }

  // Item de video activo (ver RM-36) -- undefined si es una imagen o no hay
  // ningun item todavia. `activeClipDuration` queda null hasta que el
  // lienzo sondea la duracion real (ver onMediaDurationLoaded mas abajo).
  const activeMediaFile = mediaFiles[activeMediaIndex]
  const activeIsVideoClip = activeMediaFile ? isVideoFile(activeMediaFile) : false
  const activeClipDuration = activeMediaFile ? clipDurationsByFile.get(activeMediaFile) ?? null : null
  const activeMediaAdjustment = mediaAdjustments[activeMediaIndex]
  // Tramo(s) conservados del clip activo (ver RM-40) -- sin ajuste todavia
  // (o duracion aun no sondeada), el clip completo es el unico tramo.
  const activeKeepRanges: [number, number][] =
    activeMediaAdjustment?.keep_ranges ?? (activeClipDuration != null ? [[0, activeClipDuration]] : [])

  const captionPreview: CaptionPreview | undefined = mediaUrl
    ? {
        x: captionX,
        y: captionY,
        text: text.trim() ? text.trim().slice(0, 40) : 'Así se ven tus subtítulos',
        bgColor: captionBgColor,
        textColor: captionTextColor,
        highlightStyle,
      }
    : undefined

  // Compartido por EditorLeftToolbar (riel de desktop y barra de mobile,
  // ver RM-20): tocar la herramienta YA activa cierra su hoja de ajustes
  // en mobile (no hace nada en desktop, ahi el panel siempre esta
  // visible); tocar cualquier otra la abre mostrando esa herramienta.
  function handleSelectTool(tool: EditorTool) {
    if (tool === activeTool && mobilePanelOpen) {
      setMobilePanelOpen(false)
    } else {
      setActiveTool(tool)
      setMobilePanelOpen(true)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex h-full flex-col pb-14 lg:pb-0">
      <EditorTopBar
        name={name}
        onNameChange={setName}
        onCancel={() => navigate('/')}
        isSubmitting={isSubmitting}
        uploadProgress={uploadProgress}
      />

      {error && (
        <div className="shrink-0 px-4 pt-3">
          <Alert variant="error" onDismiss={() => setError(null)}>
            {error}
          </Alert>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <EditorLeftToolbar activeTool={activeTool} onSelect={handleSelectTool} />

        <div className="flex flex-1 items-center justify-center overflow-y-auto p-6">
          {mediaUrl ? (
            <TextOverlayCanvas
              mediaUrl={mediaUrl}
              mediaKind={activeIsVideoClip ? 'video' : 'image'}
              overlays={textOverlays}
              selectedId={selectedOverlayId}
              onSelect={(id) => {
                setSelectedOverlayId(id)
                setActiveTool('text')
              }}
              onMove={(id, x, y) =>
                setTextOverlays((prev) => prev.map((o) => (o.id === id ? { ...o, x, y } : o)))
              }
              captionPreview={captionPreview}
              onCaptionMove={(x, y) => {
                setCaptionX(x)
                setCaptionY(y)
              }}
              mediaAdjustment={mediaAdjustments[activeMediaIndex]}
              onMediaPan={(offsetX, offsetY) =>
                setMediaAdjustments((prev) =>
                  prev.map((a, i) => (i === activeMediaIndex ? { ...a, offset_x: offsetX, offset_y: offsetY } : a)),
                )
              }
              onMediaDurationLoaded={(duration) => {
                const activeFile = mediaFiles[activeMediaIndex]
                if (!activeFile) return
                setClipDurationsByFile((prev) => new Map(prev).set(activeFile, duration))
              }}
              keepRanges={activeKeepRanges}
              seekRequest={seekRequest}
              onPlayheadChange={setPlayheadTime}
              emojiOverlays={emojiOverlays}
              emojiImageUrls={emojiImageUrls}
              selectedEmojiId={selectedEmojiOverlayId}
              onSelectEmoji={(id) => {
                setSelectedEmojiOverlayId(id)
                setActiveTool('emoji')
              }}
              onMoveEmoji={(id, x, y) =>
                setEmojiOverlays((prev) => prev.map((o) => (o.id === id ? { ...o, x, y } : o)))
              }
            />
          ) : (
            <p className="max-w-xs text-center text-sm text-muted-foreground">
              Sube una imagen o un video desde la herramienta "Media" (a la izquierda) para empezar a editar.
            </p>
          )}
        </div>

        <EditorRightPanel
          activeTool={activeTool}
          isSubmitting={isSubmitting}
          open={mobilePanelOpen}
          onClose={() => setMobilePanelOpen(false)}
          mediaFiles={mediaFiles}
          onMediaFilesAdded={(files) => {
            setMediaFiles((prev) => [...prev, ...files])
            setMediaAdjustments((prev) => [...prev, ...files.map(() => makeMediaAdjustment())])
          }}
          onMediaRemoveAt={(index) => {
            setMediaFiles((prev) => prev.filter((_, i) => i !== index))
            setMediaAdjustments((prev) => prev.filter((_, i) => i !== index))
            setActiveMediaIndex((prev) => {
              if (prev === index) return 0
              return prev > index ? prev - 1 : prev
            })
          }}
          activeMediaIndex={activeMediaIndex}
          onSelectActiveMedia={setActiveMediaIndex}
          mediaAdjustments={mediaAdjustments}
          onMediaZoomChange={(zoom) =>
            setMediaAdjustments((prev) => prev.map((a, i) => (i === activeMediaIndex ? { ...a, zoom } : a)))
          }
          onMediaFilterPresetChange={(filter_preset) =>
            setMediaAdjustments((prev) =>
              prev.map((a, i) => (i === activeMediaIndex ? { ...a, filter_preset } : a)),
            )
          }
          onMediaReorder={(from, to) => {
            setMediaFiles((prev) => moveItem(prev, from, to))
            setMediaAdjustments((prev) => moveItem(prev, from, to))
            setActiveMediaIndex((prev) => {
              if (prev === from) return to
              if (from < prev && to >= prev) return prev - 1
              if (from > prev && to <= prev) return prev + 1
              return prev
            })
          }}
          hasImage={Boolean(mediaUrl)}
          overlays={textOverlays}
          selectedOverlayId={selectedOverlayId}
          onAddOverlay={() => {
            const overlay = makeOverlay()
            setTextOverlays((prev) => [...prev, overlay])
            setSelectedOverlayId(overlay.id)
          }}
          onChangeOverlay={(updated) =>
            setTextOverlays((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
          }
          onRemoveOverlay={(id) => {
            setTextOverlays((prev) => prev.filter((o) => o.id !== id))
            setSelectedOverlayId(null)
          }}
          emojiOverlays={emojiOverlays}
          selectedEmojiOverlayId={selectedEmojiOverlayId}
          onAddEmojiOverlay={(emojiId) => {
            const overlay = makeEmojiOverlay(emojiId)
            setEmojiOverlays((prev) => [...prev, overlay])
            setSelectedEmojiOverlayId(overlay.id)
          }}
          onChangeEmojiOverlay={(updated) =>
            setEmojiOverlays((prev) => prev.map((o) => (o.id === updated.id ? updated : o)))
          }
          onRemoveEmojiOverlay={(id) => {
            setEmojiOverlays((prev) => prev.filter((o) => o.id !== id))
            setSelectedEmojiOverlayId(null)
          }}
          text={text}
          onTextChange={setText}
          targetLang={targetLang}
          onTargetLangChange={setTargetLang}
          targetDuration={targetDuration}
          onTargetDurationChange={setTargetDuration}
          narrationVolume={narrationVolume}
          onNarrationVolumeChange={setNarrationVolume}
          voiceOption={voiceOption}
          onVoiceOptionChange={setVoiceOption}
          voiceFile={voiceFile}
          onVoiceFileSelected={setVoiceFile}
          onRemoveVoiceFile={() => setVoiceFile(null)}
          musicTracks={musicTracks}
          backgroundMusic={backgroundMusic}
          onSelectMusic={setBackgroundMusic}
          highlightStyle={highlightStyle}
          onHighlightStyleChange={setHighlightStyle}
          captionBgColor={captionBgColor}
          onCaptionBgColorChange={setCaptionBgColor}
          captionTextColor={captionTextColor}
          onCaptionTextColorChange={setCaptionTextColor}
        />
      </div>

      {activeTool === 'media' && activeIsVideoClip && activeClipDuration != null && (
        <div className="shrink-0 border-t border-border bg-card p-3">
          <VideoSegmentTimeline
            key={activeMediaIndex}
            duration={activeClipDuration}
            keepRanges={activeKeepRanges}
            currentTime={playheadTime}
            disabled={isSubmitting}
            onChange={(ranges) =>
              setMediaAdjustments((prev) =>
                prev.map((a, i) => (i === activeMediaIndex ? { ...a, keep_ranges: ranges } : a)),
              )
            }
            onSeek={(time) => setSeekRequest({ time, nonce: Date.now() })}
          />
        </div>
      )}

      {activeTool === 'music' && (
        <EditorBottomTracks
          hasMusic={backgroundMusic !== null}
          musicPreviewUrl={musicPreviewUrl}
          musicKey={backgroundMusic}
          onRangeChange={(start, end) => {
            setMusicStart(start)
            setMusicEnd(end)
          }}
          musicVolume={musicVolume}
          onMusicVolumeChange={setMusicVolume}
        />
      )}
    </form>
  )
}
