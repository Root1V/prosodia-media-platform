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
  CheckCircle2,
  Gauge,
  Info,
  Volume2,
} from 'lucide-react'
import { fetchProjects } from '../api/projects'
import { fetchDashboardStats } from '../api/dashboard'
import type { DashboardStats, ServiceStats, StageBreakdown } from '../types/dashboard'
import { Sparkline } from '../components/charts/Sparkline'
import { AreaChart } from '../components/charts/AreaChart'
import { Donut } from '../components/charts/Donut'
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
import {
  formatDateTime,
  formatDayShort,
  formatRelativeTime,
  formatSecondsDuration,
} from '../lib/format'
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
  nota,
  chispa,
  chispaColor,
}: {
  label: string
  value: string
  icon: typeof FolderKanban
  title?: string
  /** La línea de debajo: con qué se compara esa cifra. */
  nota?: string
  chispa?: number[]
  chispaColor?: string
}) {
  return (
    <Card>
      <CardContent className="flex flex-col gap-3 p-5">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="text-sm text-muted-foreground" title={title}>
              {label}
            </p>
            <p className="mt-1 truncate text-xl font-semibold sm:text-2xl">{value}</p>
            {nota && <p className="mt-0.5 text-xs text-muted-foreground">{nota}</p>}
          </div>
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
            <Icon className="h-4 w-4" />
          </div>
        </div>
        {chispa && chispa.length > 1 && <Sparkline values={chispa} className={chispaColor} />}
      </CardContent>
    </Card>
  )
}

/** Barras de los últimos 30 días, dibujadas con divs.
 *
 * Sin librería de gráficos: para una serie de 30 enteros, traerse una
 * dependencia de cientos de kilobytes cuesta más de lo que resuelve. */
/** Qué llegó cada día y cómo acabó.
 *
 * Tres series superpuestas y no apiladas: "completadas" y "fallidas" son
 * partes de "corridas", así que apilarlas contaría lo mismo dos veces. */
function Tendencia({ stats }: { stats: DashboardStats | undefined }) {
  const serie = serieDeActividad(stats)
  const total = serie.reduce((suma, p) => suma + p.count, 0)
  const etiquetas = serie.map((p) => formatDayShort(p.day))

  return (
    <Card>
      <CardContent className="flex h-full flex-col gap-4 p-6">
        <div>
          <h2 className="text-base font-semibold">Tendencia</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {total === 0
              ? 'Nada en los últimos 30 días.'
              : `Por día, en los últimos 30 días. Pasa el cursor por el gráfico para ver cada uno.`}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {[
            { label: 'Corridas', clase: 'bg-primary' },
            { label: 'Completadas', clase: 'bg-success' },
            { label: 'Fallidas', clase: 'bg-destructive' },
          ].map((s) => (
            <span
              key={s.label}
              className="flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs"
            >
              <span className={cn('h-2 w-2 rounded-full', s.clase)} />
              {s.label}
            </span>
          ))}
        </div>

        <div className="flex flex-1 items-center">
          <AreaChart
            labels={etiquetas}
            series={[
              {
                key: 'total',
                label: 'Corridas',
                className: 'text-primary',
                values: serie.map((p) => p.count),
              },
              {
                key: 'completed',
                label: 'Completadas',
                className: 'text-success',
                values: serie.map((p) => p.completed),
              },
              {
                key: 'failed',
                label: 'Fallidas',
                className: 'text-destructive',
                values: serie.map((p) => p.failed),
              },
            ]}
            tooltip={(i) =>
              `${formatDayShort(serie[i].day)}: ${serie[i].count} ${serie[i].count === 1 ? 'corrida' : 'corridas'} · ${serie[i].completed} ok · ${serie[i].failed} con error`
            }
          />
        </div>
      </CardContent>
    </Card>
  )
}

/** Cómo terminan, en anillo. */
function ComoTerminan({ stats }: { stats: DashboardStats }) {
  const { outcomes } = stats
  const segmentos = [
    { key: 'completed', label: 'Completadas', value: outcomes.completed, className: 'text-success' },
    { key: 'failed', label: 'Fallidas', value: outcomes.failed, className: 'text-destructive' },
    { key: 'active', label: 'En marcha', value: outcomes.active, className: 'text-muted-foreground' },
  ]
  const suma = segmentos.reduce((n, s) => n + s.value, 0)

  return (
    <Card>
      <CardContent className="flex flex-col gap-5 p-6">
        <div>
          <h2 className="text-base font-semibold">Cómo terminan</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Todas tus corridas, incluidas las de proyectos ya borrados.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <Donut segments={segmentos} total={suma} caption="corridas" />
          <ul className="flex min-w-[11rem] flex-1 flex-col gap-3">
            {segmentos.map((s) => (
              <li key={s.key} className="flex items-center gap-3 text-sm">
                <span className={cn('h-2.5 w-2.5 shrink-0 rounded-full bg-current', s.className)} />
                <span className="flex-1 truncate">{s.label}</span>
                <span className="font-medium tabular-nums">{s.value}</span>
                <span className="w-10 text-right tabular-nums text-muted-foreground">
                  {suma > 0 ? `${Math.round((s.value / suma) * 100)}%` : '—'}
                </span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  )
}

/** Por qué fallan, en ranking. */
function PorQueFallan({ stats }: { stats: DashboardStats }) {
  const motivos = stats.failure_reasons
  return (
    <Card>
      <CardContent className="flex flex-col gap-4 p-6">
        <div>
          <h2 className="text-base font-semibold">Por qué fallan</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {motivos.length === 0
              ? 'Ningún proyecto fallido conserva su mensaje de error.'
              : 'Los motivos más frecuentes, agrupados por el error del pipeline.'}
          </p>
        </div>

        {motivos.length > 0 && (
          <ol className="flex flex-col">
            {motivos.map((motivo, i) => (
              <li
                key={motivo.reason}
                className={cn('flex items-start gap-3 py-3', i > 0 && 'border-t border-border')}
              >
                <span className="w-4 shrink-0 text-sm tabular-nums text-muted-foreground">
                  {i + 1}
                </span>
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-destructive" />
                <span className="min-w-0 flex-1 text-sm leading-relaxed" title={motivo.reason}>
                  {motivo.reason}
                </span>
                <span className="shrink-0 text-sm font-medium tabular-nums">{motivo.count}</span>
              </li>
            ))}
          </ol>
        )}

        {/* El mensaje solo vive en el proyecto; las metricas no lo copian. */}
        <p className="text-xs leading-relaxed text-muted-foreground">
          Solo cuenta los proyectos que siguen existiendo: el mensaje de error no se guarda en las
          métricas, así que borrar un proyecto se lleva su motivo.
        </p>
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
            <li key={fase.phase} className="flex items-start gap-3 text-sm">
              <span
                className={cn(
                  'mt-1 h-2.5 w-2.5 shrink-0 rounded-full',
                  COLORES_FASE[i % COLORES_FASE.length],
                )}
              />
              {/* Envuelve en vez de truncar: en una columna estrecha,
                  "Sintesis de ..." perderia justo la palabra que la
                  identifica. */}
              <span className="min-w-0 flex-1 leading-tight">{getStageLabel(fase.phase)}</span>
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
  const serie = serieDeActividad(stats)
  const ultimos30 = stats?.runs_vs_previous.current ?? 0
  const previos = stats?.runs_vs_previous.previous ?? 0
  // Sin periodo anterior no se inventa un "+100%": se dice que no hay con
  // que comparar, que es lo que pasa el primer mes de uso.
  const notaComparacion =
    previos === 0
      ? 'sin periodo anterior con el que comparar'
      : `${ultimos30 >= previos ? '↑' : '↓'} ${Math.abs(Math.round(((ultimos30 - previos) / previos) * 100))}% vs. los 30 días previos`
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
          {/* 1. Las cifras, con su forma y con qué comparar. */}
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Cifra
              label="Corridas (30 días)"
              value={String(ultimos30)}
              icon={Gauge}
              nota={notaComparacion}
              chispa={serie.map((p) => p.count)}
            />
            <Cifra
              label="Salen bien"
              value={terminadas > 0 ? `${Math.round((completadas / terminadas) * 100)}%` : '—'}
              icon={CheckCircle2}
              nota={terminadas > 0 ? `${completadas} de ${terminadas} terminadas` : undefined}
              chispa={serie.map((p) => p.completed)}
              chispaColor="text-success"
            />
            <Cifra
              label="Proyectos"
              value={stats ? String(stats.total_projects) : '—'}
              icon={FolderKanban}
              nota={stats && stats.active_now > 0 ? `${stats.active_now} en marcha` : 'ninguno en marcha'}
            />
            <Cifra
              label="Material procesado"
              value={stats ? formatSecondsDuration(stats.total_seconds_processed) : '—'}
              icon={Clock}
              nota="audio y video de entrada"
              title="No incluye la voz generada a partir de texto, que no parte de un material con duración."
            />
          </div>

          {/* 2. Qué pasó: la tendencia manda, el desenlace la acompaña. */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[1.6fr_1fr]">
            <Tendencia stats={stats} />
            {stats && <ComoTerminan stats={stats} />}
          </div>

          {/* 3. Qué hacer con ello. */}
          {insights.length > 0 && (
            <Card>
              <CardContent className="flex flex-col gap-1 p-6">
                <h2 className="mb-2 text-base font-semibold">Qué conviene mirar</h2>
                <div className="grid grid-cols-1 gap-x-8 lg:grid-cols-2">
                  {insights.map((insight, i) => (
                    <div
                      key={insight.id}
                      className={cn(
                        'flex items-start gap-3 py-3',
                        i > 0 && 'border-t border-border lg:border-t-0',
                        i > 1 && 'lg:border-t',
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
                </div>
              </CardContent>
            </Card>
          )}

          {/* 4. El detalle: por qué falla, dónde se va el tiempo, qué usas. */}
          {/* La tabla se lleva dos columnas: con cinco columnas propias, en un
              tercio del ancho se le cortaba la ultima. */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-4">
            {stats && <PorQueFallan stats={stats} />}
            {stats?.stage_breakdown && <RepartoDelTiempo reparto={stats.stage_breakdown} />}
            {stats && stats.by_service.length > 0 && (
              <div className="xl:col-span-2">
                <TablaPorServicio filas={stats.by_service} />
              </div>
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
