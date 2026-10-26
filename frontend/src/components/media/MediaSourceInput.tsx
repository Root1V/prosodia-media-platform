import { useState } from 'react'
import { useDropzone } from 'react-dropzone'
import type { Accept } from 'react-dropzone'
import { ArrowLeft, Clapperboard, FileVideo, Link, UploadCloud, X } from 'lucide-react'
import { Card, CardContent } from '../ui/Card'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { cn } from '../../lib/cn'
import { formatBytes } from '../../lib/format'
import { MediaUrlPreview } from './MediaUrlPreview'
import { YoutubeSearchPanel } from './YoutubeSearchPanel'

type SourceMode = 'upload' | 'url' | 'search'

interface MediaSourceInputProps {
  file: File | null
  onFileChange: (file: File | null) => void
  sourceUrl: string | null
  onSourceUrlChange: (url: string | null) => void
  /** Si la URL pegada ya se confirmo alcanzable/descargable -- ver
   * MediaUrlPreview. El formulario que envuelve a este componente debe
   * exigir esto (ademas de `sourceUrl` no vacio) antes de dejar enviar. */
  onSourceUrlValidatedChange: (validated: boolean) => void
  accept: Accept
  dropTitle: string
  dropSubtitle: string
  uploadProgress?: number | null
  disabled?: boolean
  /** Pestana con la que abre cuando no hay nada elegido todavia. Depende de
   * la pagina: a doblar o subtitular se suele venir con un enlace, pero a
   * transcribir se viene con un archivo propio -- una reunion, una entrevista
   * -- y ahi abrir en el buscador de YouTube esconde lo que hace falta. */
  defaultMode?: SourceMode
}

/**
 * Elige el media de entrada de un proyecto de tres formas equivalentes y
 * mutuamente excluyentes -- elegir una limpia las otras: subir un archivo
 * (drag-and-drop, comportamiento sin cambios respecto a antes de esta
 * feature), pegar una URL (descarga directa o un sitio soportado por
 * yt-dlp como YouTube, con previsualizacion), o buscar en YouTube dentro de
 * la propia pagina y elegir un resultado con un clic.
 */
export function MediaSourceInput({
  file,
  onFileChange,
  sourceUrl,
  onSourceUrlChange,
  onSourceUrlValidatedChange,
  accept,
  dropTitle,
  dropSubtitle,
  uploadProgress,
  disabled,
  defaultMode = 'search',
}: MediaSourceInputProps) {
  const [activeTab, setActiveTab] = useState<SourceMode>(() => {
    if (sourceUrl) return 'url'
    if (file) return 'upload'
    return defaultMode
  })
  // Si la URL actual vino de elegir un resultado de busqueda, se ofrece un
  // "volver a los resultados" en la pestaña URL -- se apaga en cuanto el
  // usuario edita la URL a mano, porque ya no representa esa seleccion.
  const [urlFromSearch, setUrlFromSearch] = useState(false)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept,
    multiple: false,
    disabled,
    onDrop: (acceptedFiles) => {
      const selected = acceptedFiles[0]
      if (!selected) return
      onSourceUrlChange(null)
      onSourceUrlValidatedChange(false)
      onFileChange(selected)
    },
  })

  function selectSearchResult(url: string) {
    onFileChange(null)
    onSourceUrlChange(url)
    setUrlFromSearch(true)
    setActiveTab('url')
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex border-b border-border">
        {(
          [
            { mode: 'search' as const, label: 'Buscar en YouTube', icon: Clapperboard },
            { mode: 'upload' as const, label: 'Subir archivo', icon: UploadCloud },
            { mode: 'url' as const, label: 'Pegar URL', icon: Link },
          ]
        ).map(({ mode, label, icon: Icon }) => (
          <button
            key={mode}
            type="button"
            onClick={() => setActiveTab(mode)}
            className={cn(
              'flex items-center gap-2 border-b-2 px-4 py-2 text-sm font-medium transition-colors',
              activeTab === mode
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <div className={activeTab === 'upload' ? undefined : 'hidden'}>
        {!file ? (
          <div
            {...getRootProps()}
            className={cn(
              'flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed border-border bg-secondary/30 px-6 py-14 text-center transition-colors',
              isDragActive && 'border-primary bg-primary/5',
            )}
          >
            <input {...getInputProps()} />
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <UploadCloud className="h-6 w-6" />
            </div>
            <div>
              <p className="font-medium">{dropTitle}</p>
              <p className="mt-1 text-sm text-muted-foreground">{dropSubtitle}</p>
            </div>
          </div>
        ) : (
          <Card>
            <CardContent className="flex items-center gap-4 p-4">
              <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <FileVideo className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{file.name}</p>
                <p className="text-sm text-muted-foreground">{formatBytes(file.size)}</p>
              </div>
              {!disabled && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  onClick={() => onFileChange(null)}
                  aria-label="Quitar archivo"
                >
                  <X className="h-4 w-4" />
                </Button>
              )}
            </CardContent>
            {uploadProgress !== null && uploadProgress !== undefined && (
              <CardContent className="pt-0">
                <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
                  <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${uploadProgress}%` }}
                  />
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {uploadProgress < 100
                    ? `Subiendo… ${uploadProgress}%`
                    : 'Subida completa, creando proyecto…'}
                </p>
              </CardContent>
            )}
          </Card>
        )}
      </div>

      <div className={activeTab === 'url' ? undefined : 'hidden'}>
        <div className="flex flex-col gap-3">
          {urlFromSearch && (
            <button
              type="button"
              onClick={() => setActiveTab('search')}
              className="flex w-fit items-center gap-1.5 text-sm font-medium text-muted-foreground hover:text-foreground"
            >
              <ArrowLeft className="h-4 w-4" />
              Volver a los resultados de búsqueda
            </button>
          )}
          <Input
            type="url"
            value={sourceUrl ?? ''}
            onChange={(e) => {
              const value = e.target.value
              onFileChange(null)
              onSourceUrlChange(value || null)
              onSourceUrlValidatedChange(false)
              setUrlFromSearch(false)
            }}
            placeholder="https://... (video de YouTube u otro sitio, o enlace directo a un archivo)"
            disabled={disabled}
          />
          {sourceUrl && (
            <MediaUrlPreview url={sourceUrl} onValidatedChange={onSourceUrlValidatedChange} />
          )}
        </div>
      </div>

      <div className={activeTab === 'search' ? undefined : 'hidden'}>
        <YoutubeSearchPanel onSelect={selectSearchResult} />
      </div>
    </div>
  )
}
