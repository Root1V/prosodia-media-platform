import type { DashboardStats, ServiceStats } from '../types/dashboard'
import { SERVICE_TYPE_LABELS } from './labels'
import { formatSecondsDuration } from './format'
import type { ServiceType } from '../types/project'

export type InsightTone = 'warning' | 'info'

export interface Insight {
  id: string
  tone: InsightTone
  title: string
  detail: string
  /** A dónde ir para actuar. Un insight que no lleva a ningún sitio es una
   * estadística más. */
  to?: string
  linkLabel?: string
}

/** Por debajo de esto un porcentaje de fallos no significa nada: con 2
 * corridas, una fallida ya es el 50%. */
const MIN_CORRIDAS_PARA_JUZGAR = 3
/** A partir de aquí la tasa de fallos deja de ser mala suerte. */
const UMBRAL_FALLOS = 0.3

function etiqueta(servicio: string): string {
  return SERVICE_TYPE_LABELS[servicio as ServiceType] ?? servicio
}

/** Frases a partir de los datos que hay, y solo de esos.
 *
 * Cada regla exige la evidencia que la sostiene: sin corridas suficientes no
 * se habla de tasas, y sin factor de tiempo real no se habla de cuánto tarda.
 * Un panel que rellena huecos con cifras que no significan nada enseña a
 * ignorarlo.
 */
export function construirInsights(stats: DashboardStats | undefined): Insight[] {
  if (!stats) return []
  const insights: Insight[] = []

  if (stats.active_now > 0) {
    insights.push({
      id: 'en-marcha',
      tone: 'info',
      title: `${stats.active_now} ${stats.active_now === 1 ? 'proyecto' : 'proyectos'} en marcha`,
      detail: 'Se están procesando ahora mismo.',
      to: '/projects',
      linkLabel: 'Ver cuáles',
    })
  }

  // El peor servicio primero: si algo falla la mitad de las veces, es lo
  // unico que importa de esta pantalla.
  const problematicos = stats.by_service
    .filter((s) => s.total >= MIN_CORRIDAS_PARA_JUZGAR && s.failed / s.total >= UMBRAL_FALLOS)
    .sort((a, b) => b.failed / b.total - a.failed / a.total)

  for (const servicio of problematicos) {
    const pct = Math.round((servicio.failed / servicio.total) * 100)
    insights.push({
      id: `fallos-${servicio.service_type}`,
      tone: 'warning',
      // "71% de tus doblaje fallan" no se sostiene, y pluralizar etiquetas
      // genericas tampoco ("Voz y clonacion" no tiene plural util). Esta
      // forma funciona con las cinco sin inventar morfologia.
      title: `${etiqueta(servicio.service_type)} falla el ${pct}% de las veces`,
      detail: `${servicio.failed} de ${servicio.total} corridas terminaron en error. Abre una fallida para ver en qué etapa se cortó.`,
      to: '/projects',
      linkLabel: 'Revisar',
    })
  }

  // Cuánto cuesta cada cosa, para poder planificar. Solo donde el factor
  // existe: micro-video y voz no parten de audio, así que no hay con qué
  // comparar.
  const conFactor = stats.by_service
    .filter((s) => s.avg_realtime_factor !== null && s.completed >= MIN_CORRIDAS_PARA_JUZGAR)
    .sort((a, b) => (b.avg_realtime_factor ?? 0) - (a.avg_realtime_factor ?? 0))

  const masLento = conFactor[0]
  if (masLento && (masLento.avg_realtime_factor ?? 0) >= 1) {
    insights.push({
      id: `coste-${masLento.service_type}`,
      tone: 'info',
      title: `${etiqueta(masLento.service_type)} tarda ${masLento.avg_realtime_factor!.toFixed(1)}× lo que dura el material`,
      detail: `Media de ${masLento.completed} corridas completadas. Un video de 10 minutos te llevará cerca de ${formatSecondsDuration(600 * masLento.avg_realtime_factor!)}.`,
    })
  }

  const { quality } = stats

  if (quality.runs_tts_on_cpu > 0) {
    insights.push({
      id: 'tts-en-cpu',
      tone: 'warning',
      title: `${quality.runs_tts_on_cpu} ${quality.runs_tts_on_cpu === 1 ? 'corrida sintetizó' : 'corridas sintetizaron'} la voz en CPU`,
      detail:
        'Sin GPU la síntesis tarda varias veces más, y es con diferencia la etapa más cara. Revisa la configuración del worker.',
    })
  }

  if (quality.runs_with_trimmed_segments > 0) {
    insights.push({
      id: 'segmentos-recortados',
      tone: 'warning',
      title: `${quality.runs_with_trimmed_segments} ${quality.runs_with_trimmed_segments === 1 ? 'doblaje recortó' : 'doblajes recortaron'} frases para encajar`,
      detail:
        'La traducción no cabía en el hueco del original y hubo que cortarla: ese doblaje dice menos que el video de partida. Un contexto o un glosario más ajustado suele acortar la traducción.',
    })
  }

  if (quality.runs_with_warnings > 0) {
    insights.push({
      id: 'avisos',
      tone: 'info',
      title: `${quality.runs_with_warnings} ${quality.runs_with_warnings === 1 ? 'corrida terminó' : 'corridas terminaron'} con avisos`,
      detail: 'Terminaron bien, pero el pipeline dejó anotado algo. Están en el detalle de cada proyecto.',
    })
  }

  if (stats.total_projects > 0 && stats.activity.length === 0) {
    insights.push({
      id: 'sin-actividad',
      tone: 'info',
      title: 'Sin actividad en los últimos 30 días',
      detail: 'Tus proyectos siguen ahí; el gráfico se llena en cuanto vuelvas a procesar algo.',
    })
  }

  return insights
}

/** Los 30 días, con los huecos rellenos a cero.
 *
 * La API manda solo los días CON actividad -- no tiene por qué saber cuántos
 * se van a pintar. Las claves se construyen en UTC porque es en UTC como
 * agrupa el servidor; usar la fecha local correría las barras un día para
 * quien no esté en UTC.
 */
export function serieDeActividad(
  stats: DashboardStats | undefined,
  dias = 30,
): { day: string; count: number }[] {
  const porDia = new Map((stats?.activity ?? []).map((p) => [p.day, p.count]))
  const hoy = new Date()
  return Array.from({ length: dias }, (_, i) => {
    const fecha = new Date(
      Date.UTC(hoy.getUTCFullYear(), hoy.getUTCMonth(), hoy.getUTCDate() - (dias - 1 - i)),
    )
    const clave = fecha.toISOString().slice(0, 10)
    return { day: clave, count: porDia.get(clave) ?? 0 }
  })
}

export function tasaDeExito(servicio: ServiceStats): number | null {
  // Lo que no termino ni bien ni mal (una corrida viva) no cuenta para una
  // tasa de exito: todavia no se sabe en que acabara.
  const terminadas = servicio.completed + servicio.failed
  return terminadas > 0 ? servicio.completed / terminadas : null
}

/** Corridas terminadas y cuántas salieron bien, sumando todos los servicios.
 * Las que siguen vivas no cuentan: todavía no se sabe en qué acabarán. */
export function totalesDeCorridas(stats: DashboardStats | undefined): {
  terminadas: number
  completadas: number
} {
  const terminadas = (stats?.by_service ?? []).reduce((n, s) => n + s.completed + s.failed, 0)
  const completadas = (stats?.by_service ?? []).reduce((n, s) => n + s.completed, 0)
  return { terminadas, completadas }
}
