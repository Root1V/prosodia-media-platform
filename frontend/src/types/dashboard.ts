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
  completed: number
  failed: number
}

export interface Outcomes {
  completed: number
  failed: number
  /** Siguen vivas: ni éxito ni fallo todavía. */
  active: number
}

export interface FailureReason {
  reason: string
  count: number
}

export interface PeriodComparison {
  current: number
  previous: number
}

export interface StagePhase {
  phase: string
  avg_seconds: number
}

export interface StageBreakdown {
  service_type: string
  runs: number
  avg_total_seconds: number
  phases: StagePhase[]
}

/** Lo que salio bien a medias y un "completado" no cuenta. */
export interface Quality {
  runs_considered: number
  runs_tts_on_cpu: number
  runs_with_trimmed_segments: number
  runs_with_warnings: number
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
  /** null si no hay ninguna corrida completada de la que sacarlo. */
  stage_breakdown: StageBreakdown | null
  quality: Quality
  outcomes: Outcomes
  /** Solo cubre proyectos que siguen existiendo: el mensaje de error no se
   * copia a las métricas, así que un proyecto borrado se lleva su motivo. */
  failure_reasons: FailureReason[]
  runs_vs_previous: PeriodComparison
}
