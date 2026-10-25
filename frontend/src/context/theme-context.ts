import { createContext } from 'react'

/** El tema que se pinta. Siempre uno de los dos: "system" no es un tema, es
 * una forma de elegirlo. */
export type Theme = 'light' | 'dark'

/** Lo que el usuario eligio. "system" sigue al SO y cambia solo si el SO
 * cambia (ver RM-43). */
export type ThemePreference = Theme | 'system'

export interface ThemeContextValue {
  /** El tema efectivo, ya resuelto -- para decidir que icono o que colores
   * mostrar. Con preference "system" esto cambia cuando cambia el SO. */
  theme: Theme
  preference: ThemePreference
  setPreference: (preference: ThemePreference) => void
  /** Pasa a la siguiente opcion: claro -> oscuro -> sistema -> claro. */
  cycleTheme: () => void
}

export const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)
