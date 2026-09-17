import { useNavigate } from 'react-router-dom'
import { LogOut, Menu, Moon, Sun } from 'lucide-react'
import { useAuth } from '../../hooks/useAuth'
import { useTheme } from '../../hooks/useTheme'
import { Button } from '../ui/Button'

interface TopbarProps {
  /** Abre el drawer de Sidebar.tsx -- el boton solo se ve por debajo de
   * `lg`, en desktop el sidebar ya esta siempre visible. */
  onOpenSidebar: () => void
}

export function Topbar({ onOpenSidebar }: TopbarProps) {
  const { user, logout } = useAuth()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()

  function handleLogout() {
    logout()
    navigate('/login', { replace: true })
  }

  const firstName = user?.name?.split(' ')[0]

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-card px-4 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={onOpenSidebar}
          aria-label="Abrir menú"
          className="shrink-0 lg:hidden"
        >
          <Menu className="h-4 w-4" />
        </Button>
        <div className="min-w-0">
          <h1 className="truncate text-base font-semibold">
            {firstName ? `Hola, ${firstName}` : 'Hola'}
          </h1>
          <p className="truncate text-xs text-muted-foreground">
            Bienvenido de nuevo a Prosodia
          </p>
        </div>
      </div>

      <div className="flex shrink-0 items-center gap-3">
        <div className="hidden text-right sm:block">
          <p className="text-sm font-medium leading-tight">{user?.name}</p>
          <p className="text-xs text-muted-foreground">{user?.email}</p>
        </div>
        <Button
          variant="outline"
          size="icon"
          onClick={toggleTheme}
          aria-label={theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
          title={theme === 'dark' ? 'Cambiar a modo claro' : 'Cambiar a modo oscuro'}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
        </Button>
        <Button variant="outline" size="sm" onClick={handleLogout}>
          <LogOut className="h-4 w-4" />
          Salir
        </Button>
      </div>
    </header>
  )
}
