import { Monitor, Moon, Sun } from 'lucide-react'
import { useTheme } from '../../hooks/useTheme'
import type { ThemePreference } from '../../context/theme-context'
import { Button } from './Button'

/** Dice en que modo esta y a cual lleva el clic: con tres opciones, un
 * "cambiar a oscuro" a secas deja de ser suficiente. */
const THEME_LABELS: Record<ThemePreference, string> = {
  light: 'Tema: claro. Cambiar a oscuro',
  dark: 'Tema: oscuro. Cambiar a seguir el sistema',
  system: 'Tema: el del sistema. Cambiar a claro',
}

/** El control del tema vive en dos sitios (el topbar de la app y el login,
 * donde todavia no hay topbar). Es el mismo control, asi que es un solo
 * componente: duplicar el ciclo y las etiquetas es como se desincronizan. */
export function ThemeToggle({ className }: { className?: string }) {
  const { preference, cycleTheme } = useTheme()

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={cycleTheme}
      aria-label={THEME_LABELS[preference]}
      title={THEME_LABELS[preference]}
      className={className}
    >
      {/* El icono dice la PREFERENCIA, no el tema pintado: con "sistema"
          hay que poder ver que el control lo tiene el SO, y un sol o una
          luna ahi serian indistinguibles de haberlo elegido a mano. */}
      {preference === 'system' ? (
        <Monitor className="h-4 w-4" />
      ) : preference === 'dark' ? (
        <Moon className="h-4 w-4" />
      ) : (
        <Sun className="h-4 w-4" />
      )}
    </Button>
  )
}
