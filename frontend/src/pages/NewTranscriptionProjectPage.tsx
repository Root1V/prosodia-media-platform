import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createTranscriptionProject } from '../api/projects'
import { Card, CardContent } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Switch } from '../components/ui/Switch'
import { Alert } from '../components/ui/Alert'
import { MediaSourceInput } from '../components/media/MediaSourceInput'
import { getErrorMessage } from '../lib/errors'
import { LANGUAGE_NAMES } from '../lib/labels'
import { nombreDesdeOrigen } from '../lib/projectName'

const LANGUAGE_OPTIONS = [
  { value: '', label: 'Detectar automáticamente' },
  ...Object.entries(LANGUAGE_NAMES).map(([code, name]) => ({
    value: code,
    label: name.charAt(0).toUpperCase() + name.slice(1),
  })),
]

export function NewTranscriptionProjectPage() {
  const navigate = useNavigate()

  const [file, setFile] = useState<File | null>(null)
  const [sourceUrl, setSourceUrl] = useState<string | null>(null)
  const [sourceUrlValidated, setSourceUrlValidated] = useState(false)
  const [name, setName] = useState('')
  const [sourceLang, setSourceLang] = useState('')
  const [includeSummary, setIncludeSummary] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const hayOrigen = Boolean(file || sourceUrl)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!hayOrigen) {
      setError('Selecciona un archivo de audio/video o pega una URL para continuar.')
      return
    }
    if (sourceUrl && !sourceUrlValidated) {
      setError('Espera a que la URL se valide antes de continuar.')
      return
    }

    setError(null)
    setIsSubmitting(true)
    setUploadProgress(0)

    try {
      const project = await createTranscriptionProject(
        {
          name: name.trim() || nombreDesdeOrigen(file, sourceUrl, 'Transcripción'),
          file: file ?? undefined,
          source_url: sourceUrl ?? undefined,
          source_lang: sourceLang,
          include_summary: includeSummary,
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

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nueva transcripción</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sube un audio o video y obtén su texto en el idioma original.
        </p>
      </div>

      {error && (
        <Alert variant="error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* El origen ocupa el ancho y los ajustes se van al lado: elegir QUE se
          transcribe es el paso grande, y los otros tres campos tienen buenos
          valores por defecto. */}
      <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0">
          <MediaSourceInput
            file={file}
            onFileChange={setFile}
            sourceUrl={sourceUrl}
            onSourceUrlChange={setSourceUrl}
            onSourceUrlValidatedChange={setSourceUrlValidated}
            accept={{ 'video/*': [], 'audio/*': [] }}
            dropTitle="Arrastra tu archivo aquí o haz clic para seleccionarlo"
            dropSubtitle="Video o audio (MP4, MOV, MKV, MP3, WAV, M4A, FLAC…)"
            uploadProgress={uploadProgress}
            disabled={isSubmitting}
            // A transcribir se viene casi siempre con un archivo propio, no a
            // buscar en YouTube; abrir en el buscador escondia el area de
            // subida detras de una pestaña.
            defaultMode="upload"
          />
        </div>

        <aside className="flex min-w-0 flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div className="flex flex-col gap-2">
                <label htmlFor="source-lang" className="text-sm font-medium">
                  Idioma del audio
                </label>
                <Select
                  id="source-lang"
                  value={sourceLang}
                  onChange={(e) => setSourceLang(e.target.value)}
                  className="h-11"
                >
                  {LANGUAGE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
                <p className="text-xs text-muted-foreground">
                  Decirlo acierta más que detectarlo, sobre todo si hay ruido o acentos
                  marcados.
                </p>
              </div>

              <div className="flex items-start justify-between gap-3 rounded-xl border border-border p-4">
                <div>
                  <p className="text-sm font-medium">Incluir un resumen</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Además del texto completo, un resumen con lo más importante. Añade una
                    etapa al final.
                  </p>
                </div>
                <Switch checked={includeSummary} onCheckedChange={setIncludeSummary} />
              </div>

              <div className="flex flex-col gap-2">
                <label htmlFor="name" className="text-sm font-medium">
                  Nombre del proyecto
                </label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={hayOrigen ? nombreDesdeOrigen(file, sourceUrl, 'Transcripción') : 'Se toma del archivo'}
                  className="h-11"
                />
                <p className="text-xs text-muted-foreground">
                  Opcional. Solo sirve para reconocerlo en tu lista.
                </p>
              </div>
            </CardContent>
          </Card>

          <div className="flex flex-col gap-2">
            <Button
              type="submit"
              className="h-12 w-full text-base"
              disabled={isSubmitting || !hayOrigen || (Boolean(sourceUrl) && !sourceUrlValidated)}
            >
              {isSubmitting ? 'Creando proyecto…' : 'Transcribir'}
            </Button>
            <Button
              type="button"
              variant="ghost"
              className="w-full"
              onClick={() => navigate('/')}
              disabled={isSubmitting}
            >
              Cancelar
            </Button>
          </div>
        </aside>
      </form>
    </div>
  )
}
