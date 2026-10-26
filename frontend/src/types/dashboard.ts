export interface ServiceStats {
  service_type: string
  total: number
  completed: number
  failed: number
  /** Promedio SOLO de las completadas -- ver schemas/dashboard.py. */
  avg_seconds: number | null
  /** null donde no aplica: micro-video y TTS no parten de audio/video, asi
   * que no hay duracion de entrada contra la que comparar. */
  avg_realtime_factor: number | null
}

export interface ActivityPoint {
  day: string
  count: number
}

export interface DashboardStats {
  total_projects: number
  total_seconds_processed: number
  distinct_languages: number
  /** En cola o corriendo ahora mismo. */
  active_now: number
  by_service: ServiceStats[]
  /** Solo los dias CON actividad de los ultimos 30; los huecos los rellena
   * quien pinta el grafico. */
  activity: ActivityPoint[]
}
