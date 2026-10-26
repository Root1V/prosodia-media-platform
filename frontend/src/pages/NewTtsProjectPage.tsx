import { useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { FileAudio, Loader2, Sparkles, Undo2, UploadCloud, Wand2, X } from 'lucide-react'
import { createTtsProject } from '../api/projects'
import { assistNarrationText } from '../api/tts'
import type { NarrationMode } from '../api/tts'
import { fetchVoiceSampleUrl } from '../api/samples'
import { SamplePreviewButton } from '../components/media/SamplePreviewButton'
import { SelectableCard } from '../components/ui/SelectableCard'
import type { TtsVoiceOption } from '../types/project'
import { Card, CardContent } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Textarea } from '../components/ui/Textarea'
import { Select } from '../components/ui/Select'
import { Alert } from '../components/ui/Alert'
import { cn } from '../lib/cn'
import { getErrorMessage } from '../lib/errors'
import { formatBytes } from '../lib/format'
import { LANGUAGE_NAMES } from '../lib/labels'

const LANGUAGE_OPTIONS = Object.entries(LANGUAGE_NAMES).map(([code, name]) => ({
  value: code,
  label: name.charAt(0).toUpperCase() + name.slice(1),
}))

const VOICE_OPTIONS: { value: TtsVoiceOption; label: string; description: string }[] = [
  { value: 'public_female', label: 'Locutora', description: 'Voz pública femenina (por defecto)' },
  { value: 'public_male', label: 'Locutor', description: 'Voz pública masculina' },
  { value: 'own', label: 'Mi voz', description: 'Sube tu propia muestra de voz' },
]

/** Palabras por segundo al hablar. Es el mismo ritmo que usa el prompt del
 * guion en el backend (`build_script_user_prompt`), para que la estimacion de
 * aqui y el limite que se le pide al modelo no se contradigan. */
const PALABRAS_POR_SEGUNDO = 2.3

/** Lo que tarda la sintesis depende del texto y de la maquina, y en una medida
 * real fue de 130 s para un texto corto. No se promete un tiempo: se avisa de
 * que esto no es instantaneo a partir de un texto largo. */
const PALABRAS_TEXTO_LARGO = 300

function contarPalabras(texto: string): number {
  const limpio = texto.trim()
  return limpio ? limpio.split(/\s+/).length : 0
}

function duracionAproximada(palabras: number): string {
  const segundos = Math.round(palabras / PALABRAS_POR_SEGUNDO)
  if (segundos < 60) return `${segundos} s`
  return `${Math.floor(segundos / 60)} min ${segundos % 60} s`
}

/** El nombre del proyecto sale del texto si el usuario no escribe uno: es un
 * campo que solo sirve para reconocerlo luego en la lista, y pedirlo antes de
 * dejarle escribir lo que de verdad vino a escribir es puro tramite. */
function nombreDesdeTexto(texto: string): string {
  const limpio = texto.trim().replace(/\s+/g, ' ')
  if (!limpio) return 'Audio narrado'
  return limpio.length <= 48 ? limpio : `${limpio.slice(0, 48).trimEnd()}…`
}

export function NewTtsProjectPage() {
  const navigate = useNavigate()

  const [name, setName] = useState('')
  const [text, setText] = useState('')
  const [targetLang, setTargetLang] = useState('es')
  const [voiceOption, setVoiceOption] = useState<TtsVoiceOption>('public_female')
  const [voiceFile, setVoiceFile] = useState<File | null>(null)

  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [uploadProgress, setUploadProgress] = useState<number | null>(null)

  const [asistiendo, setAsistiendo] = useState<NarrationMode | null>(null)
  // Lo que habia antes de que la IA lo tocara. Sin esto, "mejorar" pisa lo que
  // el usuario escribio y no hay vuelta atras: la ayuda seria una apuesta.
  const [textoPrevio, setTextoPrevio] = useState<string | null>(null)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'audio/*': [] },
    multiple: false,
    onDrop: (acceptedFiles) => {
      const selected = acceptedFiles[0]
      if (selected) setVoiceFile(selected)
    },
  })

  const palabras = contarPalabras(text)

  async function pedirAyuda(mode: NarrationMode) {
    setError(null)
    setAsistiendo(mode)
    const anterior = text
    try {
      const resultado = await assistNarrationText({ text, mode, language: targetLang })
      setTextoPrevio(anterior)
      setText(resultado)
    } catch (err) {
      setError(getErrorMessage(err, 'No se pudo usar la ayuda de IA. Escribe el texto a mano.'))
    } finally {
      setAsistiendo(null)
    }
  }

  function deshacerAyuda() {
    if (textoPrevio === null) return
    setText(textoPrevio)
    setTextoPrevio(null)
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!text.trim()) {
      setError('Escribe el texto que quieres convertir a voz.')
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
      const project = await createTtsProject(
        {
          name: name.trim() || nombreDesdeTexto(text),
          text: text.trim(),
          target_lang: targetLang,
          voice_option: voiceOption,
          voiceFile: voiceFile ?? undefined,
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
        <h1 className="text-2xl font-semibold tracking-tight">Voz y clonación</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Escribe un texto y genera el audio, con una voz pública o clonando la tuya.
        </p>
      </div>

      {error && (
        <Alert variant="error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* El texto es lo que el usuario vino a escribir, asi que ocupa el ancho
          y los ajustes se van al lado. Antes el primer campo era el nombre del
          proyecto, un tramite por delante de lo unico que importa. */}
      <form onSubmit={handleSubmit} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card className="min-w-0">
          <CardContent className="flex flex-col gap-3 p-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <label htmlFor="text" className="text-sm font-medium">
                Texto a narrar
              </label>
              {/* Dos botones y no uno: con el campo lleno, solo el usuario sabe
                  si lo que hay es una IDEA o el texto final. Adivinarlo por la
                  longitud reescribiria un texto ya terminado. */}
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!text.trim() || asistiendo !== null}
                  onClick={() => pedirAyuda('draft')}
                  title="Toma lo escrito como una idea y redacta la narración"
                >
                  {asistiendo === 'draft' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Sparkles className="h-4 w-4" />
                  )}
                  Escribir desde la idea
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={!text.trim() || asistiendo !== null}
                  onClick={() => pedirAyuda('polish')}
                  title="Corrige y afina lo escrito, sin cambiar lo que dice ni el idioma"
                >
                  {asistiendo === 'polish' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Wand2 className="h-4 w-4" />
                  )}
                  Mejorar
                </Button>
              </div>
            </div>

            <Textarea
              id="text"
              value={text}
              onChange={(e) => {
                setText(e.target.value)
                // Editar a mano cierra la ventana de deshacer: a partir de
                // aqui el texto ya no es "lo que devolvio la IA".
                setTextoPrevio(null)
              }}
              placeholder="Escribe el texto que quieres narrar — o una idea («tres consejos para dormir mejor») y pulsa «Escribir desde la idea»."
              rows={14}
              disabled={asistiendo !== null}
              className="resize-y"
            />

            <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-muted-foreground">
              <span>
                {palabras === 0
                  ? 'Sin texto todavía'
                  : `${palabras} ${palabras === 1 ? 'palabra' : 'palabras'} · unos ${duracionAproximada(palabras)} de audio`}
              </span>
              {textoPrevio !== null && (
                <button
                  type="button"
                  onClick={deshacerAyuda}
                  className="flex items-center gap-1.5 font-medium text-foreground hover:underline"
                >
                  <Undo2 className="h-3.5 w-3.5" />
                  Deshacer el cambio de la IA
                </button>
              )}
            </div>

            {palabras >= PALABRAS_TEXTO_LARGO && (
              <p className="text-xs text-muted-foreground">
                Es un texto largo: sintetizarlo puede tardar varios minutos. Puedes cerrar la
                página, el proyecto sigue procesándose.
              </p>
            )}
          </CardContent>
        </Card>

        <aside className="flex min-w-0 flex-col gap-6">
          <Card>
            <CardContent className="flex flex-col gap-5 p-6">
              <div className="flex flex-col gap-2">
                <label htmlFor="target-lang" className="text-sm font-medium">
                  Idioma del audio
                </label>
                <Select
                  id="target-lang"
                  value={targetLang}
                  onChange={(e) => setTargetLang(e.target.value)}
                  className="h-11"
                >
                  {LANGUAGE_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </Select>
              </div>

              <div className="flex flex-col gap-2">
                <span className="text-sm font-medium">Voz</span>
                <div className="flex flex-col gap-2">
                  {VOICE_OPTIONS.map((option) => (
                    <SelectableCard
                      key={option.value}
                      selected={voiceOption === option.value}
                      onSelect={() => setVoiceOption(option.value)}
                    >
                      <div className="flex w-full items-center justify-between gap-2">
                        <span className="text-sm font-medium">{option.label}</span>
                        {option.value !== 'own' && (
                          <SamplePreviewButton
                            sampleKey={`voice-${option.value}`}
                            fetchUrl={() => fetchVoiceSampleUrl(option.value)}
                          />
                        )}
                      </div>
                      <span className="text-xs text-muted-foreground">{option.description}</span>
                    </SelectableCard>
                  ))}
                </div>

                {voiceOption === 'own' &&
                  (!voiceFile ? (
                    <div
                      {...getRootProps()}
                      className={cn(
                        'mt-1 flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border bg-secondary/30 px-4 py-6 text-center transition-colors',
                        isDragActive && 'border-primary bg-primary/5',
                      )}
                    >
                      <input {...getInputProps()} />
                      <UploadCloud className="h-5 w-5 text-primary" />
                      <p className="text-xs text-muted-foreground">
                        Arrastra un .wav/.mp3 o haz clic para elegirlo (6-15 s de la voz a
                        clonar)
                      </p>
                    </div>
                  ) : (
                    <div className="mt-1 flex items-center gap-3 rounded-xl border border-border p-3">
                      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                        <FileAudio className="h-4 w-4" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{voiceFile.name}</p>
                        <p className="text-xs text-muted-foreground">
                          {formatBytes(voiceFile.size)}
                        </p>
                      </div>
                      <SamplePreviewButton
                        key={`${voiceFile.name}-${voiceFile.size}`}
                        sampleKey="voice-own"
                        fetchUrl={() => Promise.resolve(URL.createObjectURL(voiceFile))}
                      />
                      {!isSubmitting && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          onClick={() => setVoiceFile(null)}
                          aria-label="Quitar voz de referencia"
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      )}
                    </div>
                  ))}
              </div>

              <div className="flex flex-col gap-2">
                <label htmlFor="name" className="text-sm font-medium">
                  Nombre del proyecto
                </label>
                <Input
                  id="name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={text.trim() ? nombreDesdeTexto(text) : 'Se toma del texto'}
                  className="h-11"
                />
                <p className="text-xs text-muted-foreground">
                  Opcional. Solo sirve para reconocerlo en tu lista.
                </p>
              </div>
            </CardContent>
          </Card>

          {uploadProgress !== null && (
            <div>
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
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Button type="submit" className="h-12 w-full text-base" disabled={isSubmitting}>
              {isSubmitting ? 'Creando proyecto…' : 'Generar audio'}
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
