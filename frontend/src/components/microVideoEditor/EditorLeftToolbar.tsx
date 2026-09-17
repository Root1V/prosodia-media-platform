import { Captions, Image as ImageIcon, Mic, Music, Smile, Type, Volume2 } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '../../lib/cn'
import type { EditorTool } from './types'

const TOOLS: { id: EditorTool; label: string; icon: LucideIcon }[] = [
  { id: 'media', label: 'Media', icon: ImageIcon },
  { id: 'text', label: 'Texto', icon: Type },
  { id: 'emoji', label: 'Emoji', icon: Smile },
  { id: 'narration', label: 'Narración', icon: Mic },
  { id: 'voice', label: 'Voz', icon: Volume2 },
  { id: 'music', label: 'Música', icon: Music },
  { id: 'subtitles', label: 'Subtítulos', icon: Captions },
]

interface EditorLeftToolbarProps {
  activeTool: EditorTool
  onSelect: (tool: EditorTool) => void
}

function ToolButton({
  tool,
  active,
  onSelect,
  className,
}: {
  tool: (typeof TOOLS)[number]
  active: boolean
  onSelect: (tool: EditorTool) => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(tool.id)}
      className={cn(
        'flex shrink-0 flex-col items-center gap-1 rounded-xl py-2.5 text-[11px] font-medium transition-colors',
        active ? 'bg-primary/10 text-primary' : 'text-muted-foreground hover:bg-secondary/50',
        className,
      )}
    >
      <tool.icon className="h-5 w-5" />
      {tool.label}
    </button>
  )
}

/** Herramientas del editor -- cada icono cambia que panel se muestra en
 * EditorRightPanel. Mismo criterio visual del item activo que Sidebar.tsx
 * (bg-primary/10 text-primary).
 *
 * Dos layouts segun ancho (ver RM-20): en desktop (`lg` y mas ancho) es el
 * riel vertical de siempre a la izquierda del lienzo; por debajo de eso no
 * entra junto al lienzo Y al panel de ajustes a la vez, asi que se
 * convierte en una barra horizontal fija abajo de todo (con scroll lateral
 * si hace falta) -- EditorRightPanel se encarga de mostrarse como una hoja
 * que sube desde abajo en vez de como panel lateral en ese mismo ancho. */
export function EditorLeftToolbar({ activeTool, onSelect }: EditorLeftToolbarProps) {
  return (
    <>
      <nav className="hidden w-[72px] shrink-0 flex-col items-center gap-1 border-r border-border bg-card py-4 lg:flex">
        {TOOLS.map((tool) => (
          <ToolButton key={tool.id} tool={tool} active={activeTool === tool.id} onSelect={onSelect} className="w-16" />
        ))}
      </nav>
      <nav className="fixed inset-x-0 bottom-0 z-30 flex h-14 items-center gap-1 overflow-x-auto border-t border-border bg-card px-2 lg:hidden">
        {TOOLS.map((tool) => (
          <ToolButton
            key={tool.id}
            tool={tool}
            active={activeTool === tool.id}
            onSelect={onSelect}
            className="min-w-[60px] px-1 py-1"
          />
        ))}
      </nav>
    </>
  )
}
