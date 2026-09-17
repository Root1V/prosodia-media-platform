import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { createDubbingProject } from '../api/projects'
import { Card, CardContent } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Textarea } from '../components/ui/Textarea'
import { Select } from '../components/ui/Select'
import { Switch } from '../components/ui/Switch'
import { Alert } from '../components/ui/Alert'
import { GlossaryEditor } from '../components/GlossaryEditor'
import type { GlossaryRow } from '../components/GlossaryEditor'
import { MediaSourceInput } from '../components/media/MediaSourceInput'
import { getErrorMessage } from '../lib/errors'

const TONE_OPTIONS = [
  { value: '', label: 'Sin preferencia' },
  { value: 'formal', label: 'Formal' },
  { value: 'informal', label: 'Informal' },
  { value: 'tecnico', label: 'Técnico' },
]

function stripExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  return lastDot > 0 ? filename.slice(0, lastDot) : filename
}

export function NewDubbingProjectPage() {
  const navigate = useNavigate()

  const [file, setFile] = useState<File | null>(null)
  const [sourceUrl, setSourceUrl] = useState<string | null>(null)
  const [sourceUrlValidated, setSourceUrlValidated] = useState(false)
  const [name, setName] = useState('')
  const [contextPrompt, setContextPrompt] = useState('')
  const [tone, setTone] = useState('')
  const [glossaryRows, setGlossaryRows] = useState<GlossaryRow[]>([])
  const [diarize, setDiarize] = useState(false)
  const [minSpeakers, setMinSpeakers] = useState<number>(2)
  const [maxSpeakers, setMaxSpeakers] = useState<number>(4)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  function handleFileChange(selected: File | null) {
    setFile(selected)
    if (selected && !name) {
      setName(stripExtension(selected.name))
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!file && !sourceUrl) {
      setError('Selecciona un archivo de video o pega una URL para continuar.')
      return
    }
    if (sourceUrl && !sourceUrlValidated) {
      setError('Espera a que la URL se valide antes de continuar.')
      return
    }
    if (!name.trim()) {
      setError('Ingresa un nombre para el proyecto.')
      return
    }

    setError(null)
    setIsSubmitting(true)
    setUploadProgress(0)

    const glossary = glossaryRows.reduce<Record<string, string>>((acc, row) => {
      if (row.term.trim()) {
        acc[row.term.trim()] = row.translation
      }
      return acc
    }, {})

    try {
      const project = await createDubbingProject(
        {
          name: name.trim(),
          file: file ?? undefined,
          source_url: sourceUrl ?? undefined,
          context_prompt: contextPrompt,
          tone,
          glossary,
          diarize,
          min_speakers: diarize ? minSpeakers : undefined,
          max_speakers: diarize ? maxSpeakers : undefined,
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
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">Nuevo doblaje de video</h1>
        <p className="text-sm text-muted-foreground">
          Sube un video para traducirlo y doblarlo automáticamente.
        </p>
      </div>

      {error && <Alert variant="error" onDismiss={() => setError(null)}>{error}</Alert>}

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        <MediaSourceInput
          file={file}
          onFileChange={handleFileChange}
          sourceUrl={sourceUrl}
          onSourceUrlChange={setSourceUrl}
          onSourceUrlValidatedChange={setSourceUrlValidated}
          accept={{ 'video/*': [] }}
          dropTitle="Arrastra tu video aquí o haz clic para seleccionarlo"
          dropSubtitle="Formatos de video compatibles (MP4, MOV, MKV, etc.)"
          uploadProgress={uploadProgress}
          disabled={isSubmitting}
        />

        <Card>
          <CardContent className="flex flex-col gap-5 p-6">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="name" className="text-sm font-medium">
                Nombre del proyecto
              </label>
              <Input
                id="name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Mi video doblado"
                required
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="context" className="text-sm font-medium">
                Contexto
              </label>
              <Textarea
                id="context"
                value={contextPrompt}
                onChange={(e) => setContextPrompt(e.target.value)}
                placeholder="Describe el tema o contexto del video para mejorar la traducción…"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="tone" className="text-sm font-medium">
                Tono
              </label>
              <Select
                id="tone"
                value={tone}
                onChange={(e) => setTone(e.target.value)}
              >
                {TONE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            </div>

            <div className="flex flex-col gap-1.5">
              <span className="text-sm font-medium">Glosario</span>
              <p className="text-xs text-muted-foreground">
                Define términos que deben traducirse siempre de la misma forma.
              </p>
              <GlossaryEditor rows={glossaryRows} onChange={setGlossaryRows} />
            </div>

            <div className="flex items-center justify-between rounded-xl border border-border p-4">
              <div>
                <p className="text-sm font-medium">
                  Detectar múltiples hablantes (diarización)
                </p>
                <p className="text-xs text-muted-foreground">
                  Identifica distintos hablantes y asigna una voz a cada uno.
                </p>
              </div>
              <Switch checked={diarize} onCheckedChange={setDiarize} />
            </div>

            {diarize && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="min-speakers" className="text-sm font-medium">
                    Mínimo de hablantes
                  </label>
                  <Input
                    id="min-speakers"
                    type="number"
                    min={1}
                    value={minSpeakers}
                    onChange={(e) => setMinSpeakers(Number(e.target.value))}
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="max-speakers" className="text-sm font-medium">
                    Máximo de hablantes
                  </label>
                  <Input
                    id="max-speakers"
                    type="number"
                    min={1}
                    value={maxSpeakers}
                    onChange={(e) => setMaxSpeakers(Number(e.target.value))}
                  />
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        <div className="flex justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate('/')}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={isSubmitting || (Boolean(sourceUrl) && !sourceUrlValidated)}
          >
            {isSubmitting ? 'Creando proyecto…' : 'Iniciar doblaje'}
          </Button>
        </div>
      </form>
    </div>
  )
}
