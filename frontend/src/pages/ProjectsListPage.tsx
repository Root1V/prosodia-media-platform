import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AudioLines,
  Captions,
  ChevronLeft,
  ChevronRight,
  ChevronRight as ChevronAbrir,
  Clapperboard,
  FileText,
  FolderOpen,
  Plus,
  Search,
  Volume2,
  X,
} from 'lucide-react'
import { fetchProjects } from '../api/projects'
import type { ProjectStatus, ServiceType } from '../types/project'
import { Card, CardContent } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Select } from '../components/ui/Select'
import { Input } from '../components/ui/Input'
import { Button } from '../components/ui/Button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/Table'
import { cn } from '../lib/cn'
import { formatDateTime, formatRelativeTime, formatSecondsDuration } from '../lib/format'
import {
  isActiveStatus,
  PROJECT_STATUS_BADGE_VARIANT,
  PROJECT_STATUS_LABELS,
} from '../lib/status'
import { OUTPUT_MODE_LABELS, SERVICE_TYPE_LABELS } from '../lib/labels'

const PAGE_SIZE = 20

/** Cada cuanto se vuelve a pedir el listado MIENTRAS haya algo corriendo.
 * Sin esto la fila decia "Procesando" para siempre: el listado no se
 * refrescaba solo y habia que recargar la pagina para ver si termino. */
const REFRESCO_ACTIVO_MS = 5000

/** Los cinco servicios, con la ruta donde empieza cada uno. Antes el boton
 * "Nuevo proyecto" iba derecho a /dubbing/new: elegia doblaje por ti, y los
 * otros cuatro solo se alcanzaban desde el menu lateral. */
const SERVICIOS = [
  { to: '/dubbing/new', label: 'Doblaje de video', icon: AudioLines },
  { to: '/subtitles/new', label: 'Traducción y subtítulos', icon: Captions },
  { to: '/transcription/new', label: 'Transcripción', icon: FileText },
  { to: '/tts/new', label: 'Voz y clonación', icon: Volume2 },
  { to: '/micro-video', label: 'Micro-video', icon: Clapperboard },
]

const STATUS_FILTER_OPTIONS: { value: ProjectStatus | ''; label: string }[] = [
  { value: '', label: 'Todos los estados' },
  { value: 'queued', label: PROJECT_STATUS_LABELS.queued },
  { value: 'downloading', label: PROJECT_STATUS_LABELS.downloading },
  { value: 'running', label: PROJECT_STATUS_LABELS.running },
  { value: 'completed', label: PROJECT_STATUS_LABELS.completed },
  { value: 'failed', label: PROJECT_STATUS_LABELS.failed },
]

const SERVICE_FILTER_OPTIONS: { value: ServiceType | ''; label: string }[] = [
  { value: '', label: 'Todos los servicios' },
  { value: 'dubbing', label: SERVICE_TYPE_LABELS.dubbing },
  { value: 'subtitles', label: SERVICE_TYPE_LABELS.subtitles },
  { value: 'transcription', label: SERVICE_TYPE_LABELS.transcription },
  { value: 'tts', label: SERVICE_TYPE_LABELS.tts },
  { value: 'micro_video', label: SERVICE_TYPE_LABELS.micro_video },
]

export function ProjectsListPage() {
  const navigate = useNavigate()
  const [status, setStatus] = useState<ProjectStatus | ''>('')
  const [serviceType, setServiceType] = useState<ServiceType | ''>('')
  const [busqueda, setBusqueda] = useState('')
  const [busquedaAplicada, setBusquedaAplicada] = useState('')
  const [page, setPage] = useState(1)

  // Se espera a que el usuario deje de escribir antes de preguntar al
  // servidor: una consulta por tecla serian ocho busquedas para escribir
  // "clip_2min", y las respuestas pueden llegar desordenadas.
  useEffect(() => {
    const id = setTimeout(() => {
      setBusquedaAplicada(busqueda.trim())
      setPage(1)
    }, 300)
    return () => clearTimeout(id)
  }, [busqueda])

  const { data, isLoading } = useQuery({
    queryKey: [
      'projects',
      { status, service_type: serviceType, q: busquedaAplicada, page, page_size: PAGE_SIZE },
    ],
    queryFn: () =>
      fetchProjects({
        status: status || undefined,
        service_type: serviceType || undefined,
        q: busquedaAplicada || undefined,
        page,
        page_size: PAGE_SIZE,
      }),
    // Solo se sondea cuando hay algo que pueda cambiar solo.
    refetchInterval: (query) =>
      query.state.data?.items.some((p) => isActiveStatus(p.status))
        ? REFRESCO_ACTIVO_MS
        : false,
  })

  const projects = data?.items ?? []
  const total = data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const hayFiltros = status !== '' || serviceType !== '' || busquedaAplicada !== ''
  const activos = projects.filter((p) => isActiveStatus(p.status)).length

  function limpiarFiltros() {
    setStatus('')
    setServiceType('')
    setBusqueda('')
    setPage(1)
  }

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Proyectos</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {isLoading
              ? 'Cargando…'
              : total === 0 && !hayFiltros
                ? 'Todavía no has creado ninguno.'
                : `${total} ${total === 1 ? 'proyecto' : 'proyectos'}${
                    activos > 0 ? ` · ${activos} en marcha` : ''
                  }`}
          </p>
        </div>
        <MenuNuevoProyecto />
      </div>

      {/* Sin un solo proyecto no hay nada que buscar ni que filtrar: tres
          controles muertos en la primera pantalla que ve alguien nuevo. */}
      {(total > 0 || hayFiltros) && (
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-[16rem] flex-1">
          <Search className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
          <Input
            value={busqueda}
            onChange={(e) => setBusqueda(e.target.value)}
            placeholder="Buscar por nombre"
            aria-label="Buscar por nombre"
            className="h-11 pl-10"
          />
        </div>
        <Select
          value={status}
          aria-label="Filtrar por estado"
          onChange={(e) => {
            setStatus(e.target.value as ProjectStatus | '')
            setPage(1)
          }}
          className="h-11 w-48"
        >
          {STATUS_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Select
          value={serviceType}
          aria-label="Filtrar por servicio"
          onChange={(e) => {
            setServiceType(e.target.value as ServiceType | '')
            setPage(1)
          }}
          className="h-11 w-48"
        >
          {SERVICE_FILTER_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        {hayFiltros && (
          <Button type="button" variant="ghost" className="h-11" onClick={limpiarFiltros}>
            <X className="h-4 w-4" />
            Limpiar
          </Button>
        )}
      </div>
      )}

      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <p className="p-6 text-sm text-muted-foreground">Cargando…</p>
          ) : projects.length === 0 ? (
            // Dos vacios distintos: no tener proyectos no es lo mismo que que
            // los filtros no encuentren nada. Antes ambos hablaban de filtros,
            // asi que la primera vez la pagina culpaba de un filtro que el
            // usuario no habia puesto.
            hayFiltros ? (
              <div className="flex flex-col items-center gap-3 py-14 text-center">
                <p className="text-sm text-muted-foreground">
                  Ningún proyecto coincide con lo que buscas.
                </p>
                <Button type="button" variant="outline" onClick={limpiarFiltros}>
                  Limpiar los filtros
                </Button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 py-14 text-center">
                <FolderOpen className="h-7 w-7 text-muted-foreground" />
                <div>
                  <p className="font-medium">Aquí verás todo lo que hayas creado</p>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Cada doblaje, subtítulo o transcripción queda guardado con su resultado.
                  </p>
                </div>
                <div className="mt-2">
                  <MenuNuevoProyecto etiqueta="Crear el primero" />
                </div>
              </div>
            )
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nombre</TableHead>
                  {/* "Tipo" no decia de que: la columna muestra el resultado
                      que deja el proyecto, no el servicio que lo creo. */}
                  <TableHead>Resultado</TableHead>
                  <TableHead>Estado</TableHead>
                  {/* Antes "Duracion", que junto a "Creado" se leia como la
                      duracion del video. Es lo que tardo el pipeline. */}
                  <TableHead>Procesado en</TableHead>
                  <TableHead>Creado</TableHead>
                  <TableHead className="w-10" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((project) => (
                  <TableRow
                    key={project.id}
                    className="group cursor-pointer"
                    onClick={() => navigate(`/projects/${project.id}`)}
                  >
                    <TableCell className="font-medium">{project.name}</TableCell>
                    <TableCell className="text-muted-foreground">
                      {/* output_mode solo significa algo donde el usuario lo
                          elige: doblaje y subtitulos. En los demas es un
                          sentinel ("subtitles_only"), y la regla al reves
                          -- listar las excepciones -- hacia que un
                          micro-video apareciera como "Solo subtitulos". */}
                      {project.service_type === 'dubbing' || project.service_type === 'subtitles'
                        ? OUTPUT_MODE_LABELS[project.output_mode]
                        : SERVICE_TYPE_LABELS[project.service_type]}
                    </TableCell>
                    <TableCell>
                      <Badge variant={PROJECT_STATUS_BADGE_VARIANT[project.status]}>
                        <span className="flex items-center gap-1.5">
                          {/* Un punto latiendo: en una tabla quieta, "Procesando"
                              se lee igual que un estado final. */}
                          {isActiveStatus(project.status) && (
                            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                          )}
                          {PROJECT_STATUS_LABELS[project.status]}
                        </span>
                      </Badge>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {project.total_seconds != null
                        ? formatSecondsDuration(project.total_seconds)
                        : '—'}
                    </TableCell>
                    <TableCell
                      className="whitespace-nowrap text-muted-foreground"
                      title={formatDateTime(project.created_at)}
                    >
                      {formatRelativeTime(project.created_at)}
                    </TableCell>
                    <TableCell>
                      {/* La fila siempre fue clicable, pero nada lo decia. */}
                      <ChevronAbrir className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-foreground" />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-muted-foreground">
          <span>
            Página {page} de {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
              Anterior
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Siguiente
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

/** "Nuevo proyecto" despliega los cinco servicios en vez de llevar a uno.
 * Prosodia no hace "proyectos" a secas: hace doblajes, subtitulos,
 * transcripciones, voces y micro-videos, y cual de ellos es la primera
 * decision, no una que se pueda tomar por el usuario. */
function MenuNuevoProyecto({ etiqueta = 'Nuevo proyecto' }: { etiqueta?: string }) {
  const navigate = useNavigate()
  const [abierto, setAbierto] = useState(false)
  const contenedor = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!abierto) return
    function alClicarFuera(event: MouseEvent) {
      if (!contenedor.current?.contains(event.target as Node)) setAbierto(false)
    }
    function alPulsarEscape(event: KeyboardEvent) {
      if (event.key === 'Escape') setAbierto(false)
    }
    document.addEventListener('mousedown', alClicarFuera)
    document.addEventListener('keydown', alPulsarEscape)
    return () => {
      document.removeEventListener('mousedown', alClicarFuera)
      document.removeEventListener('keydown', alPulsarEscape)
    }
  }, [abierto])

  return (
    <div ref={contenedor} className="relative">
      <Button
        type="button"
        className="h-11"
        aria-haspopup="menu"
        aria-expanded={abierto}
        onClick={() => setAbierto((v) => !v)}
      >
        <Plus className="h-4 w-4" />
        {etiqueta}
      </Button>

      {abierto && (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-2 w-64 overflow-hidden rounded-xl border border-border bg-card p-1 shadow-lg"
        >
          {SERVICIOS.map(({ to, label, icon: Icon }) => (
            <button
              key={to}
              type="button"
              role="menuitem"
              onClick={() => {
                setAbierto(false)
                navigate(to)
              }}
              className={cn(
                'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm',
                'transition-colors hover:bg-secondary',
              )}
            >
              <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
              {label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
