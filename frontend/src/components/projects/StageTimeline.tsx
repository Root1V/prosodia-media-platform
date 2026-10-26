import { useEffect, useRef, useState } from 'react'
import { Check, Loader2, X } from 'lucide-react'
import { cn } from '../../lib/cn'
import { formatSecondsDuration, formatTime } from '../../lib/format'
import { getStageLabel, getStageSubtitle } from '../../lib/labels'
import type { ProjectStage, ProjectStatus, StageProgress } from '../../types/project'

/** How long a stage stays visually "in progress" after we first notice it's
 * done, so short stages (a few seconds or less) still get a moment of
 * spinner feedback instead of jumping straight from pending to a checkmark
 * -- with a 3s poll interval, a short stage can easily finish between two
 * polls and never get sampled while actually active. Purely cosmetic: it
 * doesn't delay real data, just how long the checkmark takes to appear. */
const REVEAL_DELAY_MS = 700

interface StageTimelineProps {
  /** Full predicted stage plan for this project (see getExpectedStageNames),
   * shown upfront so the user sees every step before it happens, not just
   * the ones that already ran. */
  expectedStageNames: string[]
  stages: ProjectStage[]
  currentStageName?: string | null
  /** Avance dentro de la etapa en curso (RM-56), si la reporta. */
  currentStageProgress?: StageProgress | null
  dbStatus: ProjectStatus
  /** Not part of any stage's own data, but relevant to show next to
   * subtitles_writing (which language pair the .srt files are actually in). */
  sourceLang?: string
  targetLang?: string
  /** Raw technical error from `project.error_message`, shown right under the
   * failed step's title instead of buried in the "Detalles" card below --
   * that's where the user is already looking when a step fails. */
  errorMessage?: string | null
}

type StepState = 'done' | 'active' | 'failed' | 'pending'

interface Step {
  key: string
  label: string
  state: StepState
  seconds?: number
  subtitle?: string | null
  progress?: StageProgress
}

/** `rendering_dubbed`'s own timer in translate_video.py wraps the whole
 * dubbed-rendering block, which internally times tts_synthesis and
 * audio_mixing_and_muxing AGAIN as their own stage entries -- so its
 * reported `seconds` includes theirs, not just the final mux step (a 2min
 * clip's "rendering_dubbed: 4m" is really ~4s of actual muxing plus the
 * ~4min TTS/mixing already shown as separate steps). Subtract the nested
 * children's time to show this step's own real, non-overlapping duration. */
const NESTED_STAGE_CHILDREN: Record<string, string[]> = {
  rendering_dubbed: ['tts_synthesis', 'audio_mixing_and_muxing'],
}

function resolveOwnSeconds(
  stage: ProjectStage,
  realByName: Map<string, ProjectStage>,
): number | undefined {
  if (typeof stage.seconds !== 'number') return undefined
  const children = NESTED_STAGE_CHILDREN[stage.name]
  if (!children) return stage.seconds
  const childrenTotal = children.reduce((sum, childName) => {
    const child = realByName.get(childName)
    return sum + (typeof child?.seconds === 'number' ? child.seconds : 0)
  }, 0)
  return Math.max(0, stage.seconds - childrenTotal)
}

/** Not every diarized speaker ends up with a usable voice-reference clip
 * (SpeakerProfile.reference_wav can be null -- too little clean audio, etc.),
 * and those get a fallback voice instead of their own. So "how many voices
 * are actually being mixed in" is `reference === true` count from
 * speaker_profile_building, NOT diarization's raw speaker headcount -- the
 * two can legitimately differ (e.g. 3 detected, only 1 usable). */
function countUsableVoices(speakerProfileStage: ProjectStage | undefined): number | null {
  const speakers = speakerProfileStage?.speakers
  if (!Array.isArray(speakers)) return null
  return speakers.filter(
    (speaker) => speaker && typeof speaker === 'object' && (speaker as Record<string, unknown>).reference === true,
  ).length
}

function buildSteps(
  expectedStageNames: string[],
  realStages: ProjectStage[],
  currentStageName: string | null | undefined,
  currentStageProgress: StageProgress | null | undefined,
  dbStatus: ProjectStatus,
  revealDelayKeys: Set<string>,
  sourceLang: string | undefined,
  targetLang: string | undefined,
): Step[] {
  const realByName = new Map(realStages.map((stage) => [stage.name, stage]))
  const subtitleContext = { sourceLang, targetLang }

  // "download" no es una etapa real del pipeline (nunca aparece en `stages`
  // ni como `currentStageName` -- pipeline_timings.json ni siquiera existe
  // todavia mientras se descarga, ver ProjectStatus.DOWNLOADING en
  // tasks/run_project.py), asi que su estado se deriva directamente de
  // `dbStatus` en vez del mapeo real/current de abajo.
  const hasDownloadStep = expectedStageNames[0] === 'download'
  const pipelineStageNames = hasDownloadStep ? expectedStageNames.slice(1) : expectedStageNames
  let downloadFailed = false

  const steps: Step[] = pipelineStageNames.map((name) => {
    const real = realByName.get(name)
    if (real) {
      // Held as "active" for a moment even though the backend already
      // reports it done -- see REVEAL_DELAY_MS.
      const state: StepState = revealDelayKeys.has(name) ? 'active' : 'done'
      return {
        key: name,
        label: getStageLabel(name),
        state,
        seconds: resolveOwnSeconds(real, realByName),
        subtitle: getStageSubtitle(real, subtitleContext),
      }
    }
    if (name === currentStageName) {
      return {
        key: name,
        label: getStageLabel(name),
        state: 'active',
        progress: currentStageProgress ?? undefined,
      }
    }
    return { key: name, label: getStageLabel(name), state: 'pending' }
  })

  // Real stages the predicted plan didn't anticipate (config mismatch, or a
  // future pipeline stage this list doesn't know about yet) still show up,
  // appended at the end, rather than silently disappearing.
  for (const real of realStages) {
    if (!expectedStageNames.includes(real.name)) {
      steps.push({
        key: real.name,
        label: getStageLabel(real.name),
        state: revealDelayKeys.has(real.name) ? 'active' : 'done',
        seconds: resolveOwnSeconds(real, realByName),
        subtitle: getStageSubtitle(real, subtitleContext),
      })
    }
  }

  // audio_mixing_and_muxing's own stage entry has no metadata of its own --
  // borrow speaker_profile_building's data to show how many distinct cloned
  // voices are actually going into the mix (see countUsableVoices above).
  const mixingStep = steps.find((step) => step.key === 'audio_mixing_and_muxing')
  if (mixingStep?.state === 'done') {
    const voiceCount = countUsableVoices(realByName.get('speaker_profile_building'))
    if (voiceCount !== null) {
      const label = `${voiceCount} ${voiceCount === 1 ? 'voz utilizada' : 'voces utilizadas'}`
      mixingStep.subtitle = mixingStep.subtitle ? `${mixingStep.subtitle} · ${label}` : label
    }
  }
  if (currentStageName && !steps.some((step) => step.key === currentStageName)) {
    steps.push({
      key: currentStageName,
      label: getStageLabel(currentStageName),
      state: 'active',
      progress: currentStageProgress ?? undefined,
    })
  }

  if (hasDownloadStep) {
    // No real pipeline stage/current-stage ever ran yet -- if the project
    // failed at this point, the download itself is what failed (a later
    // pipeline failure would have already produced at least one real stage
    // or a currentStageName).
    const pipelineStartedYet = realStages.length > 0 || Boolean(currentStageName)
    let downloadState: StepState
    if (dbStatus === 'downloading') {
      downloadState = 'active'
    } else if (dbStatus === 'failed' && !pipelineStartedYet) {
      downloadState = 'failed'
      downloadFailed = true
    } else if (dbStatus === 'queued') {
      downloadState = 'pending'
    } else {
      // running / completed, or failed after the real pipeline already began.
      downloadState = 'done'
    }
    steps.unshift({ key: 'download', label: getStageLabel('download'), state: downloadState })
  }

  // On failure, prefer the step still marked "active" (matches
  // currentStageName) as the point of failure -- the backend leaves
  // current_stage pointing at whichever stage was running when it raised
  // (see PipelineTimings.stage()), so that's the actual crash site, not
  // just a guess. Only fall back to "the stage right after the last
  // completed one" when there's no active step (e.g. it crashed between
  // stages, before the next one ever started). Skipped when the download
  // step already pinpointed the failure, so only one step ever shows as
  // failed at a time.
  if (dbStatus === 'failed' && !downloadFailed) {
    const activeIndex = steps.findIndex((step) => step.state === 'active')
    const targetIndex = activeIndex !== -1 ? activeIndex : steps.findIndex((step) => step.state === 'pending')
    if (targetIndex !== -1) {
      steps[targetIndex] = { ...steps[targetIndex], state: 'failed' }
    }
  }

  // The first and last steps are the only ones where "when exactly" is more
  // useful than a domain metric -- they mark when the whole run itself
  // started/finished, not just this one stage. Every stage already carries
  // started_at/ended_at; only the first/last actually need showing it.
  const first = steps[0]
  if (first?.state === 'done') {
    const startedAt = realByName.get(first.key)?.started_at
    if (typeof startedAt === 'string') {
      const label = `inicio ${formatTime(startedAt)}`
      first.subtitle = first.subtitle ? `${first.subtitle} · ${label}` : label
    }
  }
  const last = steps[steps.length - 1]
  if (last && last !== first && last.state === 'done') {
    const endedAt = realByName.get(last.key)?.ended_at
    if (typeof endedAt === 'string') {
      const label = `fin ${formatTime(endedAt)}`
      last.subtitle = last.subtitle ? `${last.subtitle} · ${label}` : label
    }
  }

  return steps
}

const CIRCLE_BASE =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full border-2 text-sm font-medium'

const CIRCLE_STATE: Record<StepState, string> = {
  done: 'border-primary bg-primary text-primary-foreground',
  active: 'border-primary bg-primary/10 text-primary',
  failed: 'border-destructive bg-destructive text-destructive-foreground',
  pending: 'border-border bg-background text-muted-foreground',
}

const LABEL_STATE: Record<StepState, string> = {
  done: 'text-foreground',
  active: 'font-semibold text-primary',
  failed: 'font-semibold text-destructive',
  pending: 'text-muted-foreground',
}

const LINE_STATE: Record<StepState, string> = {
  done: 'bg-primary',
  active: 'bg-primary/30',
  failed: 'bg-destructive/30',
  pending: 'bg-border',
}

export function StageTimeline({
  expectedStageNames,
  stages,
  currentStageName,
  currentStageProgress,
  dbStatus,
  sourceLang,
  targetLang,
  errorMessage,
}: StageTimelineProps) {
  const [revealDelayKeys, setRevealDelayKeys] = useState<Set<string>>(new Set())
  const seenDoneKeys = useRef<Set<string>>(new Set())
  const isFirstRun = useRef(true)

  useEffect(() => {
    const doneKeys = stages.map((stage) => stage.name)
    const newlyDone = doneKeys.filter((key) => !seenDoneKeys.current.has(key))
    doneKeys.forEach((key) => seenDoneKeys.current.add(key))

    // Never fake the "in progress" reveal for stages that were already done
    // the moment this component first mounted (e.g. opening an already-
    // completed or already-failed project) -- only for ones that finish
    // while the user is actually watching.
    if (isFirstRun.current) {
      isFirstRun.current = false
      return
    }
    if (newlyDone.length === 0) return

    setRevealDelayKeys((prev) => new Set([...prev, ...newlyDone]))
    const timers = newlyDone.map((key) =>
      setTimeout(() => {
        setRevealDelayKeys((prev) => {
          const next = new Set(prev)
          next.delete(key)
          return next
        })
      }, REVEAL_DELAY_MS),
    )
    return () => timers.forEach(clearTimeout)
  }, [stages])

  const steps = buildSteps(
    expectedStageNames,
    stages,
    currentStageName,
    currentStageProgress,
    dbStatus,
    revealDelayKeys,
    sourceLang,
    targetLang,
  )

  return (
    <ol className="flex flex-col">
      {steps.map((step, index) => {
        const isLast = index === steps.length - 1
        const duration = step.seconds === undefined ? null : formatSecondsDuration(step.seconds)
        return (
          <li key={step.key} className="relative flex gap-4 pb-6 last:pb-0">
            {!isLast && (
              <span
                aria-hidden
                className={cn(
                  'absolute left-4 top-8 h-[calc(100%-1.25rem)] w-0.5 -translate-x-1/2',
                  LINE_STATE[step.state],
                )}
              />
            )}
            <span className={cn(CIRCLE_BASE, CIRCLE_STATE[step.state])}>
              {step.state === 'done' && <Check className="h-4 w-4" />}
              {step.state === 'active' && <Loader2 className="h-4 w-4 animate-spin" />}
              {step.state === 'failed' && <X className="h-4 w-4" />}
              {step.state === 'pending' && <span className="h-2 w-2 rounded-full bg-current" />}
            </span>
            <div className="flex flex-1 items-start justify-between gap-3 pt-1">
              <div className="flex flex-col">
                <span className={cn('text-sm', LABEL_STATE[step.state])}>
                  {index + 1}. {step.label}
                </span>
                {step.subtitle && (
                  <span className="mt-0.5 text-xs text-muted-foreground/80">{step.subtitle}</span>
                )}
                {/* Lo que convierte "en curso" en "avanzando": sin esto, una
                    etapa de diez minutos se ve igual que una muerta. */}
                {step.progress && step.progress.total > 0 && (
                  <span className="mt-1.5 flex items-center gap-2">
                    <span className="h-1 w-24 overflow-hidden rounded-full bg-secondary">
                      <span
                        className="block h-full rounded-full bg-primary transition-[width] duration-500"
                        style={{
                          width: `${(step.progress.done / step.progress.total) * 100}%`,
                        }}
                      />
                    </span>
                    <span className="text-xs text-muted-foreground">
                      fragmento {Math.min(step.progress.done + 1, step.progress.total)} de{' '}
                      {step.progress.total}
                    </span>
                  </span>
                )}
                {step.state === 'failed' && errorMessage && (
                  <span className="mt-0.5 text-xs text-destructive/70">{errorMessage}</span>
                )}
              </div>
              {duration && (
                <span className="shrink-0 text-xs text-muted-foreground">{duration}</span>
              )}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
