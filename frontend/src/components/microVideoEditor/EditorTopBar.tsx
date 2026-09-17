import { Input } from '../ui/Input'
import { Button } from '../ui/Button'

interface EditorTopBarProps {
  name: string
  onNameChange: (name: string) => void
  onCancel: () => void
  isSubmitting: boolean
  uploadProgress: number | null
}

/** Franja superior del editor: nombre del proyecto + acciones (Cancelar/
 * Generar). Reemplaza el input de nombre y los botones que antes vivian al
 * principio/final del formulario largo -- ver rediseño del editor. */
export function EditorTopBar({ name, onNameChange, onCancel, isSubmitting, uploadProgress }: EditorTopBarProps) {
  return (
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-border bg-card px-4 py-3">
      <Input
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="Nombre del proyecto"
        className="min-w-0 flex-1 sm:max-w-xs"
        required
      />

      <div className="flex flex-wrap items-center gap-3">
        {uploadProgress !== null && (
          <div className="flex items-center gap-2">
            <div className="h-2 w-32 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
            <span className="text-xs text-muted-foreground">
              {uploadProgress < 100 ? `${uploadProgress}%` : 'Creando…'}
            </span>
          </div>
        )}
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancelar
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Creando proyecto…' : 'Generar micro-video'}
        </Button>
      </div>
    </div>
  )
}
