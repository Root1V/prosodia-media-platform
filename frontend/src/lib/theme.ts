import type { Theme, ThemePreference } from '../context/theme-context'

export const THEME_STORAGE_KEY = 'prosodia-theme'

/** El tema que pide el sistema operativo o el navegador.
 *
 * Reemplaza al heuristico por hora del dia que habia hasta RM-43 (de 6:00 a
 * 17:59 claro, de noche oscuro): adivinaba lo que el SO ya sabe, y encima
 * contradecia a quien tiene el modo oscuro puesto todo el dia.
 */
export function getSystemTheme(): Theme {
  // matchMedia no existe en algunos entornos sin navegador (y una consulta no
  // soportada devuelve matches=false), asi que el claro es el ultimo recurso.
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function getStoredPreference(): ThemePreference | null {
  // Los valores "light"/"dark" guardados antes de RM-43 siguen siendo
  // preferencias validas: quien eligio uno explicitamente lo conserva. Lo que
  // cambia es que no haber elegido nada ahora significa "sistema".
  const stored = localStorage.getItem(THEME_STORAGE_KEY)
  return stored === 'light' || stored === 'dark' || stored === 'system' ? stored : null
}

export const DEFAULT_PREFERENCE: ThemePreference = 'system'

export function getInitialPreference(): ThemePreference {
  return getStoredPreference() ?? DEFAULT_PREFERENCE
}

/** Preferencia -> tema que se pinta. "system" es la unica que depende de algo
 * externo, y por eso es la unica que hay que recalcular cuando el SO cambia. */
export function resolveTheme(preference: ThemePreference): Theme {
  return preference === 'system' ? getSystemTheme() : preference
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle('dark', theme === 'dark')
}
