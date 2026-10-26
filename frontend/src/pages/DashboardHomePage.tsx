import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  AlertTriangle,
  ArrowRight,
  AudioLines,
  Captions,
  Clapperboard,
  Clock,
  FileText,
  FolderKanban,
  Gauge,
  Info,
  Volume2,
} from 'lucide-react'
import { fetchProjects } from '../api/projects'
import { fetchDashboardStats } from '../api/dashboard'
import type { DashboardStats, ServiceStats, StageBreakdown } from '../types/dashboard'
import type { ServiceType } from '../types/project'
import { Card, CardContent } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/Table'
import { cn } from '../lib/cn'
import { formatRelativeTime, formatDateTime, formatSecondsDuration } from '../lib/format'
import {
  construirInsights,
  serieDeActividad,
  tasaDeExito,
  totalesDeCorridas,
} from '../lib/dashboardInsights'
import { PROJECT_STATUS_BADGE_VARIANT, PROJECT_STATUS_LABELS, isActiveStatus } from '../lib/status'
import { SERVICE_TYPE_LABELS, getStageLabel } from '../lib/labels'

const services = [
  {
    to: '/dubbing/new',
    title: 'Doblaje de Video',
    description: 'Traduce y dobla un video completo a otro idioma.',
    icon: AudioLines,
  },
  {
    to: '/subtitles/new',
    title: 'Traducción y Subtítulos',
    description: 'Genera subtítulos traducidos en distintos formatos.',
    icon: Captions,
  },
  {
    to: '/transcription/new',
    title: 'Transcripción',
    description: 'Obtén la transcripción del audio en su idioma original.',
    icon: FileText,
  },
  {
    to: '/tts/new',
    title: 'Voz y Clonación',
    description: 'Convierte texto en audio narrado, con una voz pública o clonando la tuya.',
    icon: Volume2,
  },
  {
    to: '/micro-video',
    title: 'Micro-Video',
    description: 'Sube una imagen y un texto: genera un video corto narrado para redes sociales.',
    icon: Clapperboard,
  },
]

function Cifra({
  label,
  value,
  icon: Icon,
  title,
}: {
  label: string
  value: string
  icon: typeof FolderKanban
  title?: string
}) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between p-5">
        <div className="min-w-0">
          <p className="text-sm text-muted-foreground" title={title}>
            {label}
          </p>
          <p className="mt-1 truncate text-xl font-semibold sm:text-2xl">{value}</p>
        </div>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
          <Icon className="h-5 w-5" />
        </div>
      </CardContent>
    </Card>
  )
}

/** Barras de los últimos 30 días, dibujadas con divs.
 *
 * Sin librería de gráficos: para una serie de 30 enteros, traerse una
 * dependencia de cientos de kilobytes cuesta más de lo que resuelve. */
function GraficoActividad({ stats }: { stats: DashboardStats | undefined }) {
  const serie = serieDeActividad(stats)
  const maximo = Math.max(...serie.map((p) => p.count), 1)
  const total = serie.reduce((suma, p) => suma + p.count, 0)

  return (
    <Card>
      <CardContent className="flex h-full flex-col gap-4 p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold">Actividad</h2>
          <p className="text-xs text-muted-foreground">
            {total === 0
              ? 'Nada en los últimos 30 días'
              : `${total} ${total === 1 ? 'corrida' : 'corridas'} en los últimos 30 días`}
          </p>
        </div>

        <div className="flex min-h-44 flex-1 items-end gap-[3px]">
          {serie.map((punto) => (
            <div
              key={punto.day}
              // El título lleva el dato exacto: la altura de una barra se lee
              // de un vistazo, pero no se lee con precisión.
              title={`${punto.day}: ${punto.count} ${punto.count === 1 ? 'corrida' : 'corridas'}`}
              className="flex h-full flex-1 items-end"
            >
              <div
                className={cn(
                  'w-full rounded-sm transition-colors',
                  punto.count > 0 ? 'bg-primary' : 'bg-secondary',
                )}
                // Las barras vacías conservan una franja mínima: un día sin
                // nada sigue siendo un día, y verlo da la escala del hueco.
                style={{ height: punto.count > 0 ? `${(punto.count / maximo) * 100}%` : '3px' }}
              />
            </div>
          ))}
        </div>

        <div className="flex justify-between text-xs text-muted-foreground">
          <span>hace 30 días</span>
          <span>hoy</span>
        </div>
      </CardContent>
    </Card>
  )
}

/** Los colores de las fases, en el orden en que se usan. Son de la paleta de
 * la app (primary/accent) y no un arcoiris: las fases no son categorias
 * independientes, son trozos de una misma barra. */
const COLORES_FASE = [
  'bg-primary',
  'bg-accent',
  'bg-primary/55',
  'bg-accent/55',
  'bg-muted-foreground/40',
]

/** En qué se va el tiempo del servicio más pesado.
 *
 * Es la respuesta a "por qué tarda tanto", que el total solo plantea. */
function RepartoDelTiempo({ reparto }: { reparto: StageBreakdown }) {
  const total = reparto.phases.reduce((suma, f) => suma + f.avg_seconds, 0)

  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="text-base font-semibold">En qué se va el tiempo</h2>
          <p className="text-xs text-muted-foreground">
            {SERVICE_TYPE_LABELS[reparto.service_type as ServiceType] ?? reparto.service_type} ·
            media de {reparto.runs} {reparto.runs === 1 ? 'corrida' : 'corridas'}
          </p>
        </div>

        <div className="flex h-3 w-full overflow-hidden rounded-full">
          {reparto.phases.map((fase, i) => (
            <div
              key={fase.phase}
              className={cn(COLORES_FASE[i % COLORES_FASE.length])}
              style={{ width: `${(fase.avg_seconds / total) * 100}%` }}
              title={`${getStageLabel(fase.phase)}: ${formatSecondsDuration(fase.avg_seconds)}`}
            />
          ))}
        </div>

        <ul className="flex flex-col gap-2.5">
          {reparto.phases.map((fase, i) => (
            <li key={fase.phase} className="flex items-center gap-3 text-sm">
              <span
                className={cn(
                  'h-2.5 w-2.5 shrink-0 rounded-full',
                  COLORES_FASE[i % COLORES_FASE.length],
                )}
              />
              <span className="min-w-0 flex-1 truncate">{getStageLabel(fase.phase)}</span>
              <span className="shrink-0 tabular-nums text-muted-foreground">
                {formatSecondsDuration(fase.avg_seconds)}
              </span>
              <span className="w-12 shrink-0 text-right font-medium tabular-nums">
                {Math.round((fase.avg_seconds / total) * 100)}%
              </span>
            </li>
          ))}
        </ul>

        <p className="text-xs leading-relaxed text-muted-foreground">
          Media total: {formatSecondsDuration(reparto.avg_total_seconds)} por corrida. Acortar la
          etapa de arriba es lo único que mueve la aguja.
        </p>
      </CardContent>
    </Card>
  )
}

function TablaPorServicio({ filas }: { filas: ServiceStats[] }) {
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-baseline justify-between gap-3 px-6 pb-2 pt-6">
          <h2 className="text-base font-semibold">Qué usas y cuánto cuesta</h2>
          <p className="text-xs text-muted-foreground">Media de las corridas completadas</p>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Servicio</TableHead>
              <TableHead className="text-right">Corridas</TableHead>
              <TableHead className="text-right">Éxito</TableHead>
              <TableHead className="text-right">Tiempo medio</TableHead>
              <TableHead className="text-right">Factor</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filas.map((fila) => {
              const exito = tasaDeExito(fila)
              return (
                <TableRow key={fila.service_type}>
                  <TableCell className="font-medium">
                    {SERVICE_TYPE_LABELS[fila.service_type as ServiceType] ?? fila.service_type}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">{fila.total}</TableCell>
                  <TableCell className="text-right">
                    {exito === null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      <span
                        className={cn(
                          exito < 0.7 ? 'font-medium text-destructive' : 'text-muted-foreground',
                        )}
                        title={`${fila.completed} completadas, ${fila.failed} fallidas`}
                      >
                        {Math.round(exito * 100)}%
                      </span>
                    )}
                  </TableCell>
                  <TableCell className="text-right text-muted-foreground">
                    {fila.avg_seconds === null ? '—' : formatSecondsDuration(fila.avg_seconds)}
                  </TableCell>
                  <TableCell
                    className="text-right text-muted-foreground"
                    // El guion no es un cero: en micro-video y voz no hay
                    // duracion de entrada contra la que medir.
                    title={
                      fila.avg_realtime_factor === null
                        ? 'No aplica: este servicio no parte de un audio o video'
                        : 'Veces que el proceso tarda lo que dura el material'
                    }
                  >
                    {fila.avg_realtime_factor === null
                      ? '—'
                      : `${fila.avg_realtime_factor.toFixed(1)}×`}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export function DashboardHomePage() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['projects', { page_size: 5 }],
    queryFn: () => fetchProjects({ page_size: 5 }),
  })
  const { data: stats } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: fetchDashboardStats,
    // Mientras haya algo corriendo, estos numeros cambian solos.
    refetchInterval: (query) => (query.state.data?.active_now ? 10000 : false),
  })

  const projects = data?.items ?? []
  const insights = construirInsights(stats)
  const { terminadas, completadas } = totalesDeCorridas(stats)
  const sinNada = stats !== undefined && stats.total_projects === 0

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      {sinNada ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-14 text-center">
            <FolderKanban className="h-7 w-7 text-muted-foreground" />
            <div>
              <p className="font-medium">Todavía no has procesado nada</p>
              <p className="mt-1 text-sm text-muted-foreground">
                En cuanto lances tu primera corrida, aquí verás cuánto tarda cada servicio y qué
                se te está fallando.
              </p>
            </div>
          </CardContent>
        </Card>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Cifra
              label="Proyectos"
              value={stats ? String(stats.total_projects) : '—'}
              icon={FolderKanban}
            />
            <Cifra
              label="Corridas"
              value={terminadas > 0 ? String(terminadas) : '—'}
              icon={Gauge}
              title="Corridas terminadas, incluidas las de proyectos que ya borraste: las métricas sobreviven al borrado"
            />
            <Cifra
              label="Salen bien"
              value={terminadas > 0 ? `${Math.round((completadas / terminadas) * 100)}%` : '—'}
              icon={Gauge}
              title={`${completadas} completadas de ${terminadas} terminadas`}
            />
            <Cifra
              label="Material procesado"
              value={stats ? formatSecondsDuration(stats.total_seconds_processed) : '—'}
              icon={Clock}
              title="Duración del audio y video que has pasado por Prosodia. No incluye la voz generada a partir de texto, que no parte de un material con duración."
            />
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            {/* Los insights en una sola tarjeta y en lista: antes eran tres
                tarjetas enormes para tres frases, y la pantalla parecia vacia
                teniendo datos de sobra. */}
            {insights.length > 0 && (
              <Card>
                <CardContent className="flex flex-col gap-1 p-6">
                  <h2 className="mb-2 text-base font-semibold">Qué conviene mirar</h2>
                  {insights.map((insight, i) => (
                    <div
                      key={insight.id}
                      className={cn(
                        'flex items-start gap-3 py-3',
                        i > 0 && 'border-t border-border',
                      )}
                    >
                      <div
                        className={cn(
                          'mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg',
                          insight.tone === 'warning'
                            ? 'bg-destructive/10 text-destructive'
                            : 'bg-primary/10 text-primary',
                        )}
                      >
                        {insight.tone === 'warning' ? (
                          <AlertTriangle className="h-3.5 w-3.5" />
                        ) : (
                          <Info className="h-3.5 w-3.5" />
                        )}
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-medium">{insight.title}</p>
                        <p className="mt-0.5 text-sm leading-relaxed text-muted-foreground">
                          {insight.detail}
                          {insight.to && (
                            <>
                              {' '}
                              <Link
                                to={insight.to}
                                className="font-medium text-primary hover:underline"
                              >
                                {insight.linkLabel ?? 'Ver'} →
                              </Link>
                            </>
                          )}
                        </p>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            {stats?.stage_breakdown && <RepartoDelTiempo reparto={stats.stage_breakdown} />}
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <GraficoActividad stats={stats} />
            {stats && stats.by_service.length > 0 && (
              <TablaPorServicio filas={stats.by_service} />
            )}
          </div>
        </>
      )}

      <div>
        <h2 className="mb-3 text-lg font-semibold">Servicios</h2>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {services.map((service) => (
            <Link key={service.to} to={service.to}>
              <Card className="h-full transition-shadow hover:shadow-md">
                <CardContent className="flex items-start gap-4 p-5">
                  <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <service.icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1">
                    <p className="font-medium">{service.title}</p>
                    <p className="mt-1 text-sm text-muted-foreground">{service.description}</p>
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      {projects.length > 0 && (
        <div>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Proyectos recientes</h2>
            <Link to="/projects" className="text-sm font-medium text-primary hover:underline">
              Ver todos
            </Link>
          </div>
          <Card>
            <CardContent className="p-0">
              {isLoading ? (
                <p className="p-6 text-sm text-muted-foreground">Cargando…</p>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nombre</TableHead>
                      <TableHead>Servicio</TableHead>
                      <TableHead>Estado</TableHead>
                      <TableHead>Creado</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {projects.map((project) => (
                      <TableRow
                        key={project.id}
                        className="cursor-pointer"
                        onClick={() => navigate(`/projects/${project.id}`)}
                      >
                        <TableCell className="font-medium">{project.name}</TableCell>
                        <TableCell>{SERVICE_TYPE_LABELS[project.service_type]}</TableCell>
                        <TableCell>
                          <Badge variant={PROJECT_STATUS_BADGE_VARIANT[project.status]}>
                            <span className="flex items-center gap-1.5">
                              {isActiveStatus(project.status) && (
                                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
                              )}
                              {PROJECT_STATUS_LABELS[project.status]}
                            </span>
                          </Badge>
                        </TableCell>
                        <TableCell
                          className="whitespace-nowrap text-muted-foreground"
                          title={formatDateTime(project.created_at)}
                        >
                          {formatRelativeTime(project.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  )
}
