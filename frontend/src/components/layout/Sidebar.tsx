import { NavLink } from 'react-router-dom'
import {
  AudioLines,
  Captions,
  Clapperboard,
  FileText,
  FolderOpen,
  LayoutGrid,
  Music,
  PanelLeftClose,
  PanelLeftOpen,
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
  { to: '/micro-video', label: 'Micro-Video', icon: Clapperboard },
]

const libraryNav: NavItem[] = [
  { to: '/projects', label: 'Proyectos', icon: FolderOpen },
]

const adminNav: NavItem[] = [
  { to: '/users', label: 'Usuarios', icon: Users },
  { to: '/music-tracks', label: 'Música de fondo', icon: Music },
]

function NavSection({
  title,
  items,
  colapsado,
}: {
  title?: string
  items: NavItem[]
  colapsado: boolean
}) {
  return (
    <div className="flex flex-col gap-1">
      {/* Colapsado el titulo no cabe, pero la separacion entre grupos si
          tiene que seguir leyendose: una raya hace el mismo trabajo.
          Se esconde por CSS y no por JS: colapsar es cosa de `lg`, y el
          drawer del movil tiene que seguir mostrando los nombres. */}
      {title && (
        <>
          {colapsado && (
            <div className="mx-auto my-2 hidden h-px w-6 bg-sidebar-border lg:block" aria-hidden />
          )}
          <span
            className={cn(
              'px-3 pb-1 pt-3 text-xs font-semibold uppercase tracking-wide text-sidebar-foreground/50',
              colapsado && 'lg:hidden',
            )}
          >
            {title}
          </span>
        </>
      )}
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === '/'}
          // Colapsado el nombre es lo unico que identifica al icono, asi que
          // pasa al tooltip en vez de desaparecer sin mas.
          title={colapsado ? item.label : undefined}
          className={({ isActive }) =>
            cn(
              'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors',
              colapsado && 'lg:justify-center lg:gap-0 lg:px-0',
              isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-foreground',
            )
          }
        >
          <item.icon className="h-4 w-4 shrink-0" />
          <span className={cn(colapsado && 'lg:hidden')}>{item.label}</span>
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
  /** Al reves que `open`: solo importa en `lg` y mas ancho. En el drawer no
   * tiene sentido colapsar a iconos -- se abre entero o no se abre. */
  colapsado: boolean
  onToggleColapsado: () => void
}

/** Menu lateral de navegacion -- fijo en desktop (`lg` y mas ancho, igual
 * que siempre), y un drawer que se desliza desde la izquierda por debajo
 * de eso (RM-20: a ese ancho no entra junto al contenido de ninguna
 * pagina). Topbar.tsx tiene el boton de hamburguesa que lo abre; clickear
 * el fondo oscuro, la X, o cualquier link de navegacion lo cierra. */
export function Sidebar({ open, onClose, colapsado, onToggleColapsado }: SidebarProps) {
  const { user } = useAuth()

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-40 bg-black/50 lg:hidden" onClick={onClose} aria-hidden="true" />
      )}
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-50 flex h-screen w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar py-6 text-sidebar-foreground transition-transform duration-200 lg:static lg:translate-x-0 lg:transition-[width]',
          open ? 'translate-x-0' : '-translate-x-full',
          // El ancho reducido es solo de `lg` para arriba: el drawer se abre
          // entero siempre, ahi colapsar a iconos no ahorraria nada.
          colapsado ? 'px-4 lg:w-[4.5rem] lg:px-3' : 'px-4',
        )}
      >
        <div
          className={cn(
            'mb-6 flex items-center gap-2',
            colapsado ? 'justify-between px-2 lg:justify-center lg:px-0' : 'justify-between px-2',
          )}
        >
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="" className="h-8 w-8 shrink-0 object-contain" />
            <span className={cn('text-lg font-semibold', colapsado && 'lg:hidden')}>Prosodia</span>
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
          <NavSection items={mainNav} colapsado={colapsado} />
          <NavSection title="Servicios" items={servicesNav} colapsado={colapsado} />
          <NavSection title="Biblioteca" items={libraryNav} colapsado={colapsado} />
          {user?.role === 'admin' && (
            <NavSection title="Administración" items={adminNav} colapsado={colapsado} />
          )}
        </nav>

        {/* Abajo y no en la cabecera: ahi competiria con el logo, y aqui
            ocupa el hueco que el menu ya dejaba vacio. */}
        <button
          type="button"
          onClick={onToggleColapsado}
          title={colapsado ? 'Expandir el menú' : 'Colapsar el menú'}
          aria-label={colapsado ? 'Expandir el menú' : 'Colapsar el menú'}
          className={cn(
            'mt-4 hidden items-center rounded-xl py-2 text-sm font-medium text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground lg:flex',
            colapsado ? 'justify-center px-0' : 'gap-3 px-3',
          )}
        >
          {colapsado ? (
            <PanelLeftOpen className="h-4 w-4 shrink-0" />
          ) : (
            <>
              <PanelLeftClose className="h-4 w-4 shrink-0" />
              Colapsar
            </>
          )}
        </button>
      </aside>
    </>
  )
}
