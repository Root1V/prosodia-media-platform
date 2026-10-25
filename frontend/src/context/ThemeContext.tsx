import { useCallback, useEffect, useState } from 'react'
import type { ReactNode } from 'react'
import {
  applyTheme,
  getInitialPreference,
  resolveTheme,
  THEME_STORAGE_KEY,
} from '../lib/theme'
import { ThemeContext } from './theme-context'
import type { ThemePreference } from './theme-context'

/** El orden del boton del topbar. "sistema" al final para que un clic desde
 * cualquiera de los dos explicitos devuelva el control al SO. */
const CYCLE: ThemePreference[] = ['light', 'dark', 'system']

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [preference, setPreferenceState] = useState<ThemePreference>(() => {
    const initial = getInitialPreference()
    // Se aplica YA, en el inicializador y no en un efecto: en un efecto el
    // primer pintado saldria con el tema equivocado y se veria el parpadeo.
    applyTheme(resolveTheme(initial))
    return initial
  })
  const [theme, setTheme] = useState(() => resolveTheme(preference))

  const setPreference = useCallback((next: ThemePreference) => {
    localStorage.setItem(THEME_STORAGE_KEY, next)
    const resolved = resolveTheme(next)
    applyTheme(resolved)
    setPreferenceState(next)
    setTheme(resolved)
  }, [])

  const cycleTheme = useCallback(() => {
    setPreferenceState((current) => {
      const next = CYCLE[(CYCLE.indexOf(current) + 1) % CYCLE.length]
      localStorage.setItem(THEME_STORAGE_KEY, next)
      const resolved = resolveTheme(next)
      applyTheme(resolved)
      setTheme(resolved)
      return next
    })
  }, [])

  // Con "sistema" el tema no se elige una vez: hay que seguir al SO mientras
  // la app esta abierta. Sin esto, cambiar el Mac a oscuro no se nota hasta
  // recargar, que es justo lo que uno espera que NO pase al elegir "sistema".
  useEffect(() => {
    if (preference !== 'system') return
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    if (!media) return

    const alCambiar = (event: MediaQueryListEvent) => {
      const resolved = event.matches ? 'dark' : 'light'
      applyTheme(resolved)
      setTheme(resolved)
    }
    media.addEventListener('change', alCambiar)
    return () => media.removeEventListener('change', alCambiar)
  }, [preference])

  return (
    <ThemeContext.Provider value={{ theme, preference, setPreference, cycleTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}
