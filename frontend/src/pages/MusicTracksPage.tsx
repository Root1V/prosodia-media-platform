import { useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useDropzone } from 'react-dropzone'
import { Music, Plus, Search, Trash2, UploadCloud, X } from 'lucide-react'
import { createMusicTrack, deleteMusicTrack, fetchMusicTracks } from '../api/musicTracks'
import { fetchMusicSampleUrl } from '../api/samples'
import { SamplePreviewButton } from '../components/media/SamplePreviewButton'
import { Card, CardContent } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Select } from '../components/ui/Select'
import { Alert } from '../components/ui/Alert'
import { cn } from '../lib/cn'
import { getErrorMessage } from '../lib/errors'
import { formatRelativeTime } from '../lib/format'
import { MUSIC_CATEGORY_LABELS } from '../lib/labels'
import type { MusicCategory, MusicTrack } from '../types/musicTracks'

const CATEGORIES = Object.keys(MUSIC_CATEGORY_LABELS) as MusicCategory[]

/** null = "todas". Es un filtro de la vista, no una categoria mas: meterla
 * en MusicCategory obligaria a contemplarla en el alta, donde no existe. */
type FiltroCategoria = MusicCategory | null

export function MusicTracksPage() {
  const queryClient = useQueryClient()
  const [error, setError] = useState<string | null>(null)
  const [exito, setExito] = useState<string | null>(null)
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<MusicCategory>('energy_pop')
  const [file, setFile] = useState<File | null>(null)
  // El alta arranca cerrada: a esta pagina se entra sobre todo a escuchar y
  // ordenar lo que ya hay, y el formulario abierto se comia la primera
  // pantalla entera antes de dejar ver una sola pista.
  const [formAbierto, setFormAbierto] = useState(false)
  const [busqueda, setBusqueda] = useState('')
  const [filtro, setFiltro] = useState<FiltroCategoria>(null)
  // Borrar un .wav no se deshace, asi que la papelera ya no borra: pide
  // confirmacion en la misma fila.
  const [porBorrar, setPorBorrar] = useState<string | null>(null)

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { 'audio/*': [] },
    multiple: false,
    onDrop: (acceptedFiles) => {
      const selected = acceptedFiles[0]
      if (selected) setFile(selected)
    },
  })

  const { data: tracks = [], isLoading } = useQuery({
    queryKey: ['music-tracks'],
    queryFn: () => fetchMusicTracks(),
  })

  const createMutation = useMutation({
    mutationFn: createMusicTrack,
    onSuccess: (track) => {
      queryClient.invalidateQueries({ queryKey: ['music-tracks'] })
      setExito(`«${track.title}» se agregó a ${MUSIC_CATEGORY_LABELS[track.category]}.`)
      setTitle('')
      setFile(null)
      setFormAbierto(false)
    },
    onError: (err) => setError(getErrorMessage(err, 'No se pudo agregar la pista.')),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteMusicTrack,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['music-tracks'] })
      setPorBorrar(null)
    },
    onError: (err) => {
      setError(getErrorMessage(err, 'No se pudo borrar la pista.'))
      setPorBorrar(null)
    },
  })

  const conteoPorCategoria = useMemo(() => {
    const conteo = {} as Record<MusicCategory, number>
    for (const c of CATEGORIES) conteo[c] = 0
    for (const t of tracks) conteo[t.category] += 1
    return conteo
  }, [tracks])

  const visibles = useMemo(() => {
    const texto = busqueda.trim().toLowerCase()
    return tracks.filter(
      (t) =>
        (filtro === null || t.category === filtro) &&
        (texto === '' || t.title.toLowerCase().includes(texto)),
    )
  }, [tracks, busqueda, filtro])

  /** Solo las categorias que tienen algo que mostrar. Antes se pintaba una
   * tarjeta por categoria aunque estuviera vacia: cinco bloques de los que
   * cuatro decian "sin pistas todavia". */
  const grupos = useMemo(
    () =>
      CATEGORIES.map((c) => ({ categoria: c, pistas: visibles.filter((t) => t.category === c) }))
        .filter((g) => g.pistas.length > 0),
    [visibles],
  )

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!title.trim() || !file) {
      setError('Ingresa un título y selecciona un archivo de audio.')
      return
    }
    setError(null)
    setExito(null)
    createMutation.mutate({ title: title.trim(), category, file })
  }

  const resumen =
    tracks.length === 0
      ? 'El catálogo está vacío.'
      : `${tracks.length} ${tracks.length === 1 ? 'pista' : 'pistas'} en ${
          CATEGORIES.filter((c) => conteoPorCategoria[c] > 0).length
        } de ${CATEGORIES.length} categorías.`

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Música de fondo</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isLoading ? 'Cargando el catálogo…' : resumen}
          </p>
        </div>
        <Button
          type="button"
          onClick={() => {
            setFormAbierto((abierto) => !abierto)
            setExito(null)
          }}
          variant={formAbierto ? 'outline' : 'primary'}
          className="h-11"
        >
          {formAbierto ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          {formAbierto ? 'Cancelar' : 'Agregar pista'}
        </Button>
      </div>

      {error && (
        <Alert variant="error" onDismiss={() => setError(null)}>
          {error}
        </Alert>
      )}
      {exito && (
        <Alert variant="success" onDismiss={() => setExito(null)}>
          {exito}
        </Alert>
      )}

      {formAbierto && (
        <Card>
          <CardContent className="p-6">
            <form onSubmit={handleSubmit} className="flex flex-col gap-5">
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <div className="flex flex-col gap-2">
                  <label htmlFor="track-title" className="text-sm font-medium">
                    Título
                  </label>
                  <Input
                    id="track-title"
                    value={title}
                    onChange={(e) => setTitle(e.target.value)}
                    placeholder="Nombre de la pista"
                    className="h-11"
                    autoFocus
                    required
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <label htmlFor="track-category" className="text-sm font-medium">
                    Categoría
                  </label>
                  <Select
                    id="track-category"
                    value={category}
                    onChange={(e) => setCategory(e.target.value as MusicCategory)}
                    className="h-11"
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c} value={c}>
                        {MUSIC_CATEGORY_LABELS[c]}
                      </option>
                    ))}
                  </Select>
                </div>
              </div>

              {!file ? (
                <div
                  {...getRootProps()}
                  className={cn(
                    'flex cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-2 border-dashed border-border bg-secondary/30 px-6 py-10 text-center transition-colors',
                    isDragActive && 'border-primary bg-primary/5',
                  )}
                >
                  <input {...getInputProps()} />
                  <UploadCloud className="h-6 w-6 text-primary" />
                  <p className="text-sm font-medium">
                    Arrastra un archivo de audio o haz clic para elegirlo
                  </p>
                  {/* Esto estaba en el subtitulo de la pagina, donde lo leia
                      todo el mundo y solo le importa a quien sube algo. */}
                  <p className="max-w-sm text-xs text-muted-foreground">
                    Se le recorta el silencio inicial y se convierte a WAV antes de guardarlo.
                  </p>
                </div>
              ) : (
                <div className="flex items-center gap-4 rounded-xl border border-border p-4">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Music className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium">{file.name}</p>
                  </div>
                  <Button type="button" variant="ghost" size="sm" onClick={() => setFile(null)}>
                    Quitar
                  </Button>
                </div>
              )}

              <div className="flex justify-end">
                <Button type="submit" className="h-11" disabled={createMutation.isPending}>
                  {createMutation.isPending ? 'Procesando…' : 'Guardar pista'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {tracks.length > 0 && (
        <div className="flex flex-col gap-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
            <Input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              placeholder="Buscar por título"
              aria-label="Buscar por título"
              className="h-11 pl-10"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <ChipCategoria
              activa={filtro === null}
              onClick={() => setFiltro(null)}
              etiqueta="Todas"
              conteo={tracks.length}
            />
            {CATEGORIES.map((c) => (
              <ChipCategoria
                key={c}
                activa={filtro === c}
                onClick={() => setFiltro(filtro === c ? null : c)}
                etiqueta={MUSIC_CATEGORY_LABELS[c]}
                conteo={conteoPorCategoria[c]}
              />
            ))}
          </div>
        </div>
      )}

      {isLoading ? (
        <p className="text-sm text-muted-foreground">Cargando…</p>
      ) : tracks.length === 0 ? (
        <div className="flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed border-border px-6 py-14 text-center">
          <Music className="h-7 w-7 text-muted-foreground" />
          <div>
            <p className="font-medium">Todavía no hay pistas en el catálogo</p>
            <p className="mt-1 text-sm text-muted-foreground">
              Las pistas que agregues aquí son las que se podrán elegir como música de un
              micro-video.
            </p>
          </div>
          <Button type="button" className="mt-2 h-11" onClick={() => setFormAbierto(true)}>
            <Plus className="h-4 w-4" />
            Agregar la primera
          </Button>
        </div>
      ) : grupos.length === 0 ? (
        <p className="rounded-2xl border border-border px-6 py-10 text-center text-sm text-muted-foreground">
          Ninguna pista coincide con lo que buscas.
        </p>
      ) : (
        <div className="flex flex-col gap-6">
          {grupos.map(({ categoria, pistas }) => (
            <div key={categoria} className="flex flex-col gap-2">
              <div className="flex items-baseline gap-2 px-1">
                <h2 className="text-sm font-semibold">{MUSIC_CATEGORY_LABELS[categoria]}</h2>
                <span className="text-xs text-muted-foreground">
                  {pistas.length} {pistas.length === 1 ? 'pista' : 'pistas'}
                </span>
              </div>
              {/* En una sola columna cada pista usaba un quinto del ancho y
                  dejaba el resto vacio. Los titulos son cortos: caben dos o
                  tres por fila, y se ven tres veces mas pistas de un vistazo. */}
              <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                {pistas.map((track) => (
                  <TarjetaPista
                    key={track.id}
                    track={track}
                    confirmando={porBorrar === track.id}
                    borrando={deleteMutation.isPending && porBorrar === track.id}
                    onPedirBorrado={() => setPorBorrar(track.id)}
                    onCancelar={() => setPorBorrar(null)}
                    onConfirmar={() => deleteMutation.mutate(track.id)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function ChipCategoria({
  activa,
  onClick,
  etiqueta,
  conteo,
}: {
  activa: boolean
  onClick: () => void
  etiqueta: string
  conteo: number
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      // Una categoria vacia se deja ver pero no se puede elegir: filtrar por
      // ella siempre daria una lista vacia, y esconderla haria creer que no
      // existe a la hora de clasificar una pista nueva.
      disabled={conteo === 0}
      aria-pressed={activa}
      className={cn(
        'flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition-colors',
        activa
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-border text-foreground hover:bg-secondary',
        conteo === 0 && 'cursor-not-allowed opacity-40 hover:bg-transparent',
      )}
    >
      {etiqueta}
      <span className={cn('text-xs', activa ? 'text-primary-foreground/70' : 'text-muted-foreground')}>
        {conteo}
      </span>
    </button>
  )
}

function TarjetaPista({
  track,
  confirmando,
  borrando,
  onPedirBorrado,
  onCancelar,
  onConfirmar,
}: {
  track: MusicTrack
  confirmando: boolean
  borrando: boolean
  onPedirBorrado: () => void
  onCancelar: () => void
  onConfirmar: () => void
}) {
  if (confirmando) {
    return (
      <div className="flex h-12 items-center justify-between gap-2 rounded-xl border border-destructive/30 bg-destructive/5 px-3">
        {/* El nombre se queda a la vista: entre decenas de tarjetas iguales,
            un "¿seguro?" sin decir de que es como no preguntar. */}
        <span className="min-w-0 truncate text-sm font-medium" title={track.title}>
          ¿Borrar «{track.title}»?
        </span>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={borrando}
            onClick={onConfirmar}
            title={`Borrar «${track.title}» y su archivo, sin vuelta atrás`}
          >
            {borrando ? 'Borrando…' : 'Borrar'}
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={onCancelar}>
            Cancelar
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-12 items-center gap-3 rounded-xl border border-border bg-card px-3">
      {/* Escuchar es la accion principal de esta pagina: dos pistas con
          nombres parecidos no se distinguen de ninguna otra forma. */}
      <SamplePreviewButton
        sampleKey={`music-${track.id}`}
        fetchUrl={() => fetchMusicSampleUrl(track.id)}
        className="h-8 w-8"
      />

      {/* La fecha pasa al tooltip: escrita era una segunda linea que decia
          "hace 2 meses" en las 33 pistas y doblaba el alto de cada fila. */}
      <p
        className="min-w-0 flex-1 truncate text-sm font-medium"
        title={`${track.title} · agregada ${formatRelativeTime(track.created_at)}`}
      >
        {track.title}
      </p>

      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={`Borrar ${track.title}`}
        title={`Borrar ${track.title}`}
        onClick={onPedirBorrado}
        className="h-8 w-8 shrink-0 text-muted-foreground hover:text-destructive"
      >
        <Trash2 className="h-4 w-4" />
      </Button>
    </div>
  )
}
