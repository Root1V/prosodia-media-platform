import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Textarea } from '../../ui/Textarea'
import { Button } from '../../ui/Button'
import { writeMicroVideoScript } from '../../../api/microVideo'
import { getErrorMessage } from '../../../lib/errors'
import type { Objective } from '../../../lib/objectives'
import { Select } from '../../ui/Select'
import { cn } from '../../../lib/cn'
import { LANGUAGE_NAMES } from '../../../lib/labels'

const LANGUAGE_OPTIONS = Object.entries(LANGUAGE_NAMES).map(([code, name]) => ({
  value: code,
  label: name.charAt(0).toUpperCase() + name.slice(1),
}))

// Duraciones estándar de video corto por plataforma: 15s (viral en Reels),
// 30s (Reels/TikTok), 60s (TikTok/Shorts), 90s (máximo recomendado en
// Facebook Reels). "Automático" (null) mantiene el comportamiento previo:
// el video dura lo que tarda la narración.
const DURATION_OPTIONS: { value: number | null; label: string }[] = [
  { value: null, label: 'Automático' },
  { value: 15, label: '15s' },
  { value: 30, label: '30s' },
  { value: 60, label: '60s' },
  { value: 90, label: '90s' },
]

interface NarrationPanelProps {
  text: string
  onTextChange: (text: string) => void
  /** Para que es el video (ver RM-42): orienta el tono del guion generado. */
  objective: Objective
  targetLang: string
  onTargetLangChange: (lang: string) => void
  targetDuration: number | null
  onTargetDurationChange: (duration: number | null) => void
  narrationVolume: number
  onNarrationVolumeChange: (volume: number) => void
}

export function NarrationPanel({
  text,
  onTextChange,
  objective,
  targetLang,
  onTargetLangChange,
  targetDuration,
  onTargetDurationChange,
  narrationVolume,
  onNarrationVolumeChange,
}: NarrationPanelProps) {
  const [idea, setIdea] = useState('')
  const [generando, setGenerando] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const generar = async () => {
    setGenerando(true)
    setError(null)
    try {
      const script = await writeMicroVideoScript({ idea, objective, target_seconds: targetDuration })
      // Se escribe en el campo editable, no se usa directamente: el guion es
      // una propuesta y el usuario tiene que poder corregirla antes de generar.
      onTextChange(script)
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo generar el guion.'))
    } finally {
      setGenerando(false)
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor="idea" className="text-sm font-medium">
          ¿Cuál es tu idea?
        </label>
        <Textarea
          id="idea"
          value={idea}
          onChange={(e) => setIdea(e.target.value)}
          placeholder="Una línea basta. Ej: los equipos pequeños entregan más rápido que los grandes."
          rows={2}
        />
        <Button
          type="button"
          variant="secondary"
          onClick={generar}
          disabled={generando || idea.trim().length === 0}
        >
          <Sparkles className="h-4 w-4" />
          {generando ? 'Escribiendo…' : 'Escribir el guion'}
        </Button>
        {error ? <p className="text-xs text-destructive">{error}</p> : null}
        <p className="text-xs text-muted-foreground">
          Escribe la propuesta abajo, para que la corrijas antes de generar. También puedes
          saltarte esto y escribir el texto tú mismo.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="text" className="text-sm font-medium">
          Texto a narrar
        </label>
        <Textarea
          id="text"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          placeholder="Escribe aquí el texto que se va a narrar sobre la imagen…"
          rows={8}
        />
        <p className="text-xs text-muted-foreground">
          Tip: envolvé una palabra o frase entre <code>**así**</code> para que aparezca en{' '}
          <strong>negrita</strong> en los captions (no se narra en voz alta).
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="target-lang" className="text-sm font-medium">
          Idioma de la narración
        </label>
        <Select id="target-lang" value={targetLang} onChange={(e) => onTargetLangChange(e.target.value)}>
          {LANGUAGE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
      </div>

      <div className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Duración del video</span>
        <div className="grid grid-cols-3 gap-2">
          {DURATION_OPTIONS.map((option) => (
            <button
              key={option.label}
              type="button"
              onClick={() => onTargetDurationChange(option.value)}
              className={cn(
                'rounded-xl border p-2 text-center text-sm font-medium transition-colors',
                targetDuration === option.value
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:bg-secondary/50',
              )}
            >
              {option.label}
            </button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Automático: el video dura lo que tarda la narración. Con una duración fija, la narración se
          acelera si es más larga o se mantiene la imagen si es más corta.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <label htmlFor="narration-volume" className="text-sm font-medium">
          Volumen de la narración
        </label>
        <div className="flex items-center gap-2">
          <input
            id="narration-volume"
            type="range"
            min={0}
            max={1}
            step={0.01}
            value={narrationVolume}
            onChange={(event) => onNarrationVolumeChange(Number(event.target.value))}
            className="flex-1 accent-primary"
          />
          <span className="w-10 text-right text-xs text-muted-foreground">
            {Math.round(narrationVolume * 100)}%
          </span>
        </div>
      </div>
    </div>
  )
}
