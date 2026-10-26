import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowRight, ChevronDown } from 'lucide-react'
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
import { cn } from '../lib/cn'
import { getErrorMessage } from '../lib/errors'
import { LANGUAGE_NAMES } from '../lib/labels'
import { nombreDesdeOrigen } from '../lib/projectName'

const TONE_OPTIONS = [
  { value: '', label: 'Sin preferencia' },
  { value: 'formal', label: 'Formal' },
  { value: 'informal', label: 'Informal' },
  { value: 'tecnico', label: 'Técnico' },
]

const LANGUAGE_OPTIONS = Object.entries(LANGUAGE_NAMES).map(([code, name]) => ({
  value: code,
  label: name.charAt(0).toUpperCase() + name.slice(1),
}))

export function NewDubbingProjectPage() {
  const navigate = useNavigate()

  const [file, setFile] = useState<File | null>(null)
  const [sourceUrl, setSourceUrl] = useState<string | null>(null)
  const [sourceUrlValidated, setSourceUrlValidated] = useState(false)
  const [name, setName] = useState('')
  // Igual que en subtitulos (RM-58): hasta ahora se mandaba "en"/"es" desde
  // api/projects.ts y la pagina no lo decia ni lo dejaba cambiar.
  const [sourceLang, setSourceLang] = useState('en')
  const [targetLang, setTargetLang] = useState('es')
  const [contextPrompt, setContextPrompt] = useState('')
  const [tone, setTone] = useState('')
  const [glossaryRows, setGlossaryRows] = useState<GlossaryRow[]>([])
  const [diarize, setDiarize] = useState(false)
  const [minSpeakers, setMinSpeakers] = useState<number>(2)
  const [maxSpeakers, setMaxSpeakers] = useState<number>(4)
  const [ajustesAbiertos, setAjustesAbiertos] = useState(false)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const hayOrigen = Boolean(file || sourceUrl)
  const terminosGlosario = glossaryRows.filter((row) => row.term.trim()).length
  const ajustesUsados =
    (contextPrompt.trim() ? 1 : 0) + (tone ? 1 : 0) + (terminosGlosario > 0 ? 1 : 0)
  const mismoIdioma = sourceLang === targetLang
  // Nadie comprobaba esto: ni la pagina ni el router. Un rango invertido
  // viajaba tal cual al subproceso de pyannote y fallaba tarde, cuando el
  // video ya estaba subido y el pipeline en marcha.
  const rangoHablantesInvalido = diarize && minSpeakers > maxSpeakers

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!hayOrigen) {
      setError('Selecciona un archivo de video o pega una URL para continuar.')
      return
    }
    if (sourceUrl && !sourceUrlValidated) {
      setError('Espera a que la URL se valide antes de continuar.')
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
          name: name.trim() || nombreDesdeOrigen(file, sourceUrl, 'Doblaje'),
          file: file ?? undefined,
          source_url: sourceUrl ?? undefined,
          context_prompt: contextPrompt,
          tone,
          glossary,
          source_lang: sourceLang,
          target_lang: targetLang,
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
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Nuevo doblaje de video</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Sube un video y obtenlo hablado en otro idioma.
        </p>
      </div>

      {error && (
        <Alert variant="error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <MediaSourceInput
            file={file}
            onFileChange={setFile}
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
            <CardContent className="p-0">
              <button
                type="button"
                onClick={() => setAjustesAbiertos((v) => !v)}
                aria-expanded={ajustesAbiertos}
                className="flex w-full items-center justify-between gap-3 p-6 text-left"
              >
                <div>
                  <p className="text-sm font-medium">Afinar la traducción</p>
                  <p className="mt-0.5 text-xs text-muted-foreground">
                    Contexto, tono y glosario. Opcional —{' '}
                    {ajustesUsados === 0
                      ? 'sin usar'
                      : `${ajustesUsados} de 3 en uso${terminosGlosario ? `, ${terminosGlosario} término${terminosGlosario === 1 ? '' : 's'}` : ''}`}
                    .
                  </p>
                </div>
                <ChevronDown
                  className={cn(
                    'h-4 w-4 shrink-0 text-muted-foreground transition-transform',
                    ajustesAbiertos && 'rotate-180',
                  )}
                />
              </button>

              {ajustesAbiertos && (
                <div className="flex flex-col gap-5 border-t border-border p-6">
                  <div className="flex flex-col gap-2">
                    <label htmlFor="context" className="text-sm font-medium">
                      Contexto
                    </label>
                    <Textarea
                      id="context"
                      value={contextPrompt}
                      onChange={(e) => setContextPrompt(e.target.value)}
                      placeholder="De qué trata el video. Ayuda a desambiguar: «entrevista sobre inversión en bolsa», «clase de anatomía»…"
                      rows={3}
                    />
                  </div>

                  <div className="flex flex-col gap-2">
                    <label htmlFor="tone" className="text-sm font-medium">
                      Tono
                    </label>
                    <Select
                      id="tone"
                      value={tone}
                      onChange={(e) => setTone(e.target.value)}
                      className="h-11"
                    >
                      {TONE_OPTIONS.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </Select>
                  </div>

                  <div className="flex flex-col gap-2">
                    <span className="text-sm font-medium">Glosario</span>
                    <p className="text-xs text-muted-foreground">
                      Términos que deben traducirse siempre igual — nombres de producto, jerga
                      del sector.
                    </p>
                    <GlossaryEditor rows={glossaryRows} onChange={setGlossaryRows} />
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <aside className="flex min-w-0 flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div className="flex flex-col gap-2">
                <span className="text-sm font-medium">Idiomas</span>
                <div className="flex items-center gap-2">
                  <Select
                    value={sourceLang}
                    aria-label="Idioma del video"
                    onChange={(e) => setSourceLang(e.target.value)}
                    className="h-11 min-w-0 flex-1"
                  >
                    {LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                  <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                  <Select
                    value={targetLang}
                    aria-label="Idioma del doblaje"
                    onChange={(e) => setTargetLang(e.target.value)}
                    className="h-11 min-w-0 flex-1"
                  >
                    {LANGUAGE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </div>
                {mismoIdioma && (
                  <p className="text-xs text-warning">
                    Origen y destino son el mismo idioma: se volvería a narrar sin traducir.
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-3 rounded-xl border border-border p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium">Varios hablantes</p>
                    <p className="mt-0.5 text-xs text-muted-foreground">
                      Identifica quién habla en cada momento y le da una voz distinta a cada
                      uno. Añade una etapa al proceso.
                    </p>
                  </div>
                  <Switch checked={diarize} onCheckedChange={setDiarize} />
                </div>

                {diarize && (
                  <div className="flex flex-col gap-2 border-t border-border pt-3">
                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex flex-col gap-1.5">
                        <label htmlFor="min-speakers" className="text-xs text-muted-foreground">
                          Mínimo
                        </label>
                        <Input
                          id="min-speakers"
                          type="number"
                          min={1}
                          value={minSpeakers}
                          onChange={(e) => setMinSpeakers(Number(e.target.value))}
                          className="h-10"
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label htmlFor="max-speakers" className="text-xs text-muted-foreground">
                          Máximo
                        </label>
                        <Input
                          id="max-speakers"
                          type="number"
                          min={1}
                          value={maxSpeakers}
                          onChange={(e) => setMaxSpeakers(Number(e.target.value))}
                          className="h-10"
                        />
                      </div>
                    </div>
                    {rangoHablantesInvalido ? (
                      <p className="text-xs text-destructive">
                        El mínimo no puede ser mayor que el máximo.
                      </p>
                    ) : (
                      <p className="text-xs text-muted-foreground">
                        Es una pista, no una orden: ayuda cuando ya sabes cuántas personas
                        hablan.
                      </p>
                    )}
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <label htmlFor="name" className="text-sm font-medium">
                  Nombre del proyecto
                </label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={
                    hayOrigen ? nombreDesdeOrigen(file, sourceUrl, 'Doblaje') : 'Se toma del video'
                  }
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
              disabled={
                isSubmitting ||
                !hayOrigen ||
                rangoHablantesInvalido ||
                (Boolean(sourceUrl) && !sourceUrlValidated)
              }
            >
              {isSubmitting ? 'Creando proyecto…' : 'Iniciar doblaje'}
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
            {/* Es el servicio mas pesado de todos -- transcribe, traduce,
                sintetiza y renderiza -- y la sintesis sola cuesta del orden de
                13 veces lo que dura el audio (ver RM-56). Decirlo antes evita
                que se de por colgado lo que solo va despacio. */}
            <p className="mt-1 text-center text-xs leading-relaxed text-muted-foreground">
              Doblar tarda varias veces lo que dura el video. Puedes cerrar la página: el
              proyecto sigue procesándose.
            </p>
          </div>
        </aside>
      </form>
    </div>
  )
}
