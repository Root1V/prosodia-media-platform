import { NavLink } from 'react-router-dom'
import {
  AudioLines,
  Captions,
  Clapperboard,
  FileText,
  FolderOpen,
  LayoutGrid,
  Music,
  Users,
  Volume2,
  X,
} from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { cn } from '../../lib/cn'

interface NavItem {
  to: string
  label: string
  icon: typeof LayoutGrid
}

const mainNav: NavItem[] = [{ to: '/', label: 'Inicio', icon: LayoutGrid }]

const servicesNav: NavItem[] = [
  { to: '/dubbing/new', label: 'Doblaje de Video', icon: AudioLines },
  { to: '/subtitles/new', label: 'Subtítulos', icon: Captions },
  { to: '/transcription/new', label: 'Transcripción', icon: FileText },
  { to: '/tts/new', label: 'Voz y Clonación', icon: Volume2 },
  { to: '/micro-video/new', label: 'Micro-Video', icon: Clapperboard },
]

const libraryNav: NavItem[] = [
  { to: '/projects', label: 'Proyectos', icon: FolderOpen },
]

const adminNav: NavItem[] = [
  { to: '/users', label: 'Usuarios', icon: Users },
  { to: '/music-tracks', label: 'Música de fondo', icon: Music },
]

function NavSection({ title, items }: { title?: string; items: NavItem[] }) {
  return (
    <div className="flex flex-col gap-1">
      {title && (
        <span className="px-3 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-sidebar-foreground/50">
          {title}
        </span>
      )}
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground',
            )
          }
        >
          <item.icon className="h-4 w-4" />
          {item.label}
        </NavLink>
      ))}
    </div>
  )
}

interface SidebarProps {
  /** Solo importa por debajo de `lg` -- en desktop el sidebar siempre esta
   * visible en su lugar de siempre (ver clases `lg:static lg:translate-x-0`
   * mas abajo), asi que este prop no cambia nada ahi. */
  open: boolean
  onClose: () => void
}

/** Menu lateral de navegacion -- fijo en desktop (`lg` y mas ancho, igual
 * que siempre), y un drawer que se desliza desde la izquierda por debajo
 * de eso (RM-20: a ese ancho no entra junto al contenido de ninguna
 * pagina). Topbar.tsx tiene el boton de hamburguesa que lo abre; clickear
 * el fondo oscuro, la X, o cualquier link de navegacion lo cierra. */
export function Sidebar({ open, onClose }: SidebarProps) {
  const { user } = useAuth()

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={onClose} aria-hidden="true" />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex h-screen w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar px-4 py-6 text-sidebar-foreground transition-transform duration-200 lg:static lg:translate-x-0',
          open ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        <div className="mb-6 flex items-center justify-between gap-2 px-2">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="" className="h-8 w-8 object-contain" />
            <span className="text-lg font-semibold">Prosodia</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground lg:hidden"
            aria-label="Cerrar menú"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Cerrar el drawer al navegar (irrelevante en desktop, ahi el
         * sidebar ya esta siempre visible sin importar `open`). */}
        <nav className="flex flex-1 flex-col gap-4 overflow-y-auto" onClick={onClose}>
          <NavSection items={mainNav} />
          <NavSection title="Servicios" items={servicesNav} />
          <NavSection title="Biblioteca" items={libraryNav} />
          {user?.role === 'admin' && <NavSection title="Administración" items={adminNav} />}
        </nav>
      </aside>
    </>
  )
}
