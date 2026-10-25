/** Las marcas de tiempo de la API son UTC pero vienen SIN zona
 * ("2026-10-25T23:09:38.445708"): la columna es `timestamp without time
 * zone`, asi que el offset se pierde al guardar. JavaScript interpreta una
 * fecha sin zona como hora LOCAL, de modo que sin esto toda la app muestra
 * las fechas corridas el offset del usuario -- en UTC-5 una pista recien
 * subida decia "Agregada dentro de 5 horas".
 *
 * El arreglo de fondo es que la API diga la zona que quiere decir; mientras
 * tanto se asume UTC aqui, en el unico sitio por el que pasan todas. */
function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null
  const tieneZona = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value)
  const date = new Date(tieneZona ? value : `${value}Z`)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatDateTime(value: string | null | undefined): string {
  const date = parseApiDate(value)
  if (!date) return '—'
  return date.toLocaleString('es-ES', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })
}

export function formatRelativeTime(value: string | null | undefined): string {
  const date = parseApiDate(value)
  if (!date) return '—'

  const diffMs = date.getTime() - Date.now()
  const diffSeconds = Math.round(diffMs / 1000)
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ['year', 60 * 60 * 24 * 365],
    ['month', 60 * 60 * 24 * 30],
    ['day', 60 * 60 * 24],
    ['hour', 60 * 60],
    ['minute', 60],
  ]

  const rtf = new Intl.RelativeTimeFormat('es', { numeric: 'auto' })
  for (const [unit, secondsInUnit] of units) {
    if (Math.abs(diffSeconds) >= secondsInUnit) {
      return rtf.format(Math.round(diffSeconds / secondsInUnit), unit)
    }
  }
  return rtf.format(diffSeconds, 'second')
}

/** Time only (no date) -- used next to a stage's name, where the date is
 * already obvious from the surrounding run and repeating it would just be
 * noise. */
export function formatTime(value: string | null | undefined): string {
  const date = parseApiDate(value)
  if (!date) return '—'
  return date.toLocaleTimeString('es-ES', { timeStyle: 'medium' })
}

/** "4m 29s" / "268s" / "<1s" -- shared by the stage timeline and the overall
 * run duration so both use the same rounding/format. */
export function formatSecondsDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 1) return '<1s'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const minutes = Math.floor(seconds / 60)
  const rest = Math.round(seconds % 60)
  return `${minutes}m ${rest}s`
}

/** "0:05" / "4:29" / "1:02:03" -- mm:ss (or h:mm:ss) clock format for a media
 * player's scrubber, distinct from formatSecondsDuration's rounded "4m 29s"
 * summary style (that one collapses sub-second values to "<1s", which reads
 * wrong for a live playback position). */
export function formatClockTime(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const secs = total % 60
  const paddedSecs = String(secs).padStart(2, '0')
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${paddedSecs}`
  }
  return `${minutes}:${paddedSecs}`
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB']
  const exponent = Math.min(
    Math.floor(Math.log(bytes) / Math.log(1024)),
    units.length - 1,
  )
  const value = bytes / 1024 ** exponent
  return `${value.toFixed(exponent === 0 ? 0 : 1)} ${units[exponent]}`
}
