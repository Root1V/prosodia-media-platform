import { Link, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  AudioLines,
  Captions,
  Clapperboard,
  Clock,
  FileText,
  Globe,
  Mic,
  FolderKanban,
  Volume2,
} from 'lucide-react'
import { fetchProjects } from '../api/projects'
import { fetchDashboardStats } from '../api/dashboard'
import type { DashboardStats } from '../types/dashboard'
import { Card, CardContent } from '../components/ui/Card'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/Table'
import { formatDateTime, formatSecondsDuration } from '../lib/format'
import { PROJECT_STATUS_BADGE_VARIANT, PROJECT_STATUS_LABELS } from '../lib/status'
import { SERVICE_TYPE_LABELS } from '../lib/labels'

interface StatCard {
  label: string
  value: string
  icon: typeof FolderKanban
}

function buildStats(stats: DashboardStats | undefined): StatCard[] {
  return [
    { label: 'Proyectos', value: stats ? String(stats.total_projects) : '—', icon: FolderKanban },
    {
      label: 'Tiempo procesado',
      value: stats ? formatSecondsDuration(stats.total_seconds_processed) : '—',
      icon: Clock,
    },
    { label: 'Idiomas', value: stats ? String(stats.distinct_languages) : '—', icon: Globe },
    // Fijo en 0 hasta que exista la libreria de voces (P1.5) -- ver
    // schemas/dashboard.py::DashboardStatsOut.saved_voices.
    { label: 'Voces guardadas', value: stats ? String(stats.saved_voices) : '—', icon: Mic },
  ]
}

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

export function DashboardHomePage() {
  const navigate = useNavigate()
  const { data, isLoading } = useQuery({
    queryKey: ['projects', { page_size: 5 }],
    queryFn: () => fetchProjects({ page_size: 5 }),
  })
  const { data: dashboardStats } = useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: fetchDashboardStats,
  })

  const projects = data?.items ?? []
  const stats = buildStats(dashboardStats)

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.label}>
            <CardContent className="flex items-center justify-between p-5">
              <div>
                <p className="text-sm text-muted-foreground">{stat.label}</p>
                <p className="mt-1 text-2xl font-semibold">{stat.value}</p>
              </div>
              <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <stat.icon className="h-5 w-5" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

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
                    <p className="mt-1 text-sm text-muted-foreground">
                      {service.description}
                    </p>
                  </div>
                  <ArrowRight className="mt-1 h-4 w-4 shrink-0 text-muted-foreground" />
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      </div>

      <div>
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-lg font-semibold">Proyectos recientes</h2>
          {projects.length > 0 && (
            <Link
              to="/projects"
              className="text-sm font-medium text-primary hover:underline"
            >
              Ver todos
            </Link>
          )}
        </div>
        <Card>
          <CardContent className="p-0">
            {isLoading ? (
              <p className="p-6 text-sm text-muted-foreground">Cargando…</p>
            ) : projects.length === 0 ? (
              <div className="flex flex-col items-center gap-3 py-12 text-center">
                <p className="text-sm text-muted-foreground">
                  Aún no tienes proyectos
                </p>
                <Button onClick={() => navigate('/dubbing/new')}>
                  Crear tu primer proyecto
                </Button>
              </div>
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
                          {PROJECT_STATUS_LABELS[project.status]}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDateTime(project.created_at)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
