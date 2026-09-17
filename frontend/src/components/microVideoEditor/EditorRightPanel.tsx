import { ChevronDown } from 'lucide-react'
import { MediaPanel } from './panels/MediaPanel'
import { TextPanel } from './panels/TextPanel'
import { EmojiPanel } from './panels/EmojiPanel'
import { NarrationPanel } from './panels/NarrationPanel'
import { VoicePanel } from './panels/VoicePanel'
import { MusicPanel } from './panels/MusicPanel'
import { SubtitlesPanel } from './panels/SubtitlesPanel'
import { cn } from '../../lib/cn'
import type { EditorTool } from './types'
import type {
  CaptionHighlightStyle,
  EmojiOverlay,
  MediaAdjustment,
  TextOverlay,
  TtsVoiceOption,
} from '../../types/project'
import type { MusicTrack } from '../../types/musicTracks'

interface EditorRightPanelProps {
  activeTool: EditorTool
  isSubmitting: boolean
  /** Solo importa por debajo de `lg` -- ver comentario de `open`/`onClose`
   * mas abajo en el componente. */
  open: boolean
  onClose: () => void

  mediaFiles: File[]
  onMediaFilesAdded: (files: File[]) => void
  onMediaRemoveAt: (index: number) => void
  activeMediaIndex: number
  onSelectActiveMedia: (index: number) => void
  mediaAdjustments: MediaAdjustment[]
  onMediaZoomChange: (zoom: number) => void
  onMediaFilterPresetChange: (preset: MediaAdjustment['filter_preset']) => void
  onMediaReorder: (fromIndex: number, toIndex: number) => void

  hasImage: boolean
  overlays: TextOverlay[]
  selectedOverlayId: string | null
  onAddOverlay: () => void
  onChangeOverlay: (overlay: TextOverlay) => void
  onRemoveOverlay: (id: string) => void

  emojiOverlays: EmojiOverlay[]
  selectedEmojiOverlayId: string | null
  onAddEmojiOverlay: (emojiId: string) => void
  onChangeEmojiOverlay: (overlay: EmojiOverlay) => void
  onRemoveEmojiOverlay: (id: string) => void

  text: string
  onTextChange: (text: string) => void
  targetLang: string
  onTargetLangChange: (lang: string) => void
  targetDuration: number | null
  onTargetDurationChange: (duration: number | null) => void
  narrationVolume: number
  onNarrationVolumeChange: (volume: number) => void

  voiceOption: TtsVoiceOption
  onVoiceOptionChange: (option: TtsVoiceOption) => void
  voiceFile: File | null
  onVoiceFileSelected: (file: File) => void
  onRemoveVoiceFile: () => void

  musicTracks: MusicTrack[]
  backgroundMusic: string | null
  onSelectMusic: (id: string | null) => void

  highlightStyle: CaptionHighlightStyle
  onHighlightStyleChange: (style: CaptionHighlightStyle) => void
  captionBgColor: string
  onCaptionBgColorChange: (color: string) => void
  captionTextColor: string
  onCaptionTextColorChange: (color: string) => void
}

const TOOL_TITLES: Record<EditorTool, string> = {
  media: 'Imagen o video',
  text: 'Texto',
  emoji: 'Emoji',
  narration: 'Narración',
  voice: 'Voz',
  music: 'Música de fondo',
  subtitles: 'Subtítulos',
}

/** El switch de paneles en si -- compartido entre el `<aside>` de desktop y
 * la hoja de abajo en mobile/tablet (ver EditorRightPanel) para no
 * duplicar la logica de "que panel va con que herramienta". */
function ToolPanelContent(props: EditorRightPanelProps) {
  return (
    <>
      {props.activeTool === 'media' && (
        <MediaPanel
          mediaFiles={props.mediaFiles}
          onFilesAdded={props.onMediaFilesAdded}
          onRemoveAt={props.onMediaRemoveAt}
          isSubmitting={props.isSubmitting}
          activeIndex={props.activeMediaIndex}
          onSelectActive={props.onSelectActiveMedia}
          mediaAdjustments={props.mediaAdjustments}
          onZoomChange={props.onMediaZoomChange}
          onFilterPresetChange={props.onMediaFilterPresetChange}
          onReorder={props.onMediaReorder}
        />
      )}

      {props.activeTool === 'text' && (
        <TextPanel
          hasImage={props.hasImage}
          overlays={props.overlays}
          selectedOverlayId={props.selectedOverlayId}
          onAddOverlay={props.onAddOverlay}
          onChangeOverlay={props.onChangeOverlay}
          onRemoveOverlay={props.onRemoveOverlay}
        />
      )}

      {props.activeTool === 'emoji' && (
        <EmojiPanel
          hasImage={props.hasImage}
          overlays={props.emojiOverlays}
          selectedOverlayId={props.selectedEmojiOverlayId}
          onAddOverlay={props.onAddEmojiOverlay}
          onChangeOverlay={props.onChangeEmojiOverlay}
          onRemoveOverlay={props.onRemoveEmojiOverlay}
        />
      )}

      {props.activeTool === 'narration' && (
        <NarrationPanel
          text={props.text}
          onTextChange={props.onTextChange}
          targetLang={props.targetLang}
          onTargetLangChange={props.onTargetLangChange}
          targetDuration={props.targetDuration}
          onTargetDurationChange={props.onTargetDurationChange}
          narrationVolume={props.narrationVolume}
          onNarrationVolumeChange={props.onNarrationVolumeChange}
        />
      )}

      {props.activeTool === 'voice' && (
        <VoicePanel
          voiceOption={props.voiceOption}
          onVoiceOptionChange={props.onVoiceOptionChange}
          voiceFile={props.voiceFile}
          onVoiceFileSelected={props.onVoiceFileSelected}
          onRemoveVoiceFile={props.onRemoveVoiceFile}
          isSubmitting={props.isSubmitting}
        />
      )}

      {props.activeTool === 'music' && (
        <MusicPanel
          musicTracks={props.musicTracks}
          backgroundMusic={props.backgroundMusic}
          onSelectMusic={props.onSelectMusic}
        />
      )}

      {props.activeTool === 'subtitles' && (
        <SubtitlesPanel
          highlightStyle={props.highlightStyle}
          onHighlightStyleChange={props.onHighlightStyleChange}
          captionBgColor={props.captionBgColor}
          onCaptionBgColorChange={props.onCaptionBgColorChange}
          captionTextColor={props.captionTextColor}
          onCaptionTextColorChange={props.onCaptionTextColorChange}
        />
      )}
    </>
  )
}

/** Panel de ajustes de la herramienta activa (ver EditorLeftToolbar).
 *
 * Dos layouts segun ancho (ver RM-20): en desktop (`lg` y mas ancho) es el
 * panel lateral fijo de siempre. Por debajo de eso no entra junto al
 * lienzo Y a la barra de herramientas (que ahi pasa a ser horizontal
 * abajo de todo, ver EditorLeftToolbar) -- se convierte en una hoja que
 * sube desde el fondo, apoyada justo arriba de esa barra (`bottom-14`),
 * con un fondo oscuro detras para poder cerrarla tocando afuera. Arranca
 * cerrada (`open=false`) y se abre al tocar una herramienta -- ver el
 * manejo de `open`/`activeTool` en NewMicroVideoProjectPage. */
export function EditorRightPanel(props: EditorRightPanelProps) {
  return (
    <>
      <aside className="hidden w-[340px] shrink-0 flex-col gap-4 overflow-y-auto border-l border-border bg-card p-4 lg:flex">
        <h2 className="text-sm font-semibold text-muted-foreground">{TOOL_TITLES[props.activeTool]}</h2>
        <ToolPanelContent {...props} />
      </aside>

      {props.open && (
        <div
          className="fixed inset-x-0 top-0 z-40 bottom-14 bg-black/50 lg:hidden"
          onClick={props.onClose}
          aria-hidden="true"
        />
      )}
      <div
        className={cn(
          'fixed inset-x-0 bottom-14 z-50 flex max-h-[70vh] flex-col gap-4 rounded-t-2xl border-t border-border bg-card p-4 shadow-lg transition-transform duration-200 lg:hidden',
          props.open ? 'translate-y-0' : 'translate-y-[calc(100%+3.5rem)]',
        )}
      >
        <div className="flex shrink-0 items-center justify-between">
          <h2 className="text-sm font-semibold text-muted-foreground">{TOOL_TITLES[props.activeTool]}</h2>
          <button
            type="button"
            onClick={props.onClose}
            className="rounded-lg p-1 text-muted-foreground hover:bg-secondary/50"
            aria-label="Cerrar panel"
          >
            <ChevronDown className="h-5 w-5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          <ToolPanelContent {...props} />
        </div>
      </div>
    </>
  )
}
