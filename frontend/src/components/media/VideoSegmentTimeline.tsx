import { useEffect, useMemo, useRef, useState } from 'react'
import type { MouseEvent as ReactMouseEvent } from 'react'
import { Redo2, Scissors, Trash2, Undo2 } from 'lucide-react'
import { Button } from '../ui/Button'
import { cn } from '../../lib/cn'
import { formatClockTime } from '../../lib/format'
import { dragPoint, trackDrag, type DragStartEvent } from '../../lib/dragEvents'

const MIN_SPAN_SECONDS = 0.2
// Arrastrar el cuerpo de un tramo hacia (o lejos de) un vecino tiene que
// superar esta distancia (en segundos, medida sobre la franja) antes de
// unir/separar -- evita que un clic tembloroso una o separe sin querer.
const JOIN_DRAG_THRESHOLD_SECONDS = 0.3

interface HistoryEntry {
  ranges: [number, number][]
  closedGaps: number[]
}

interface VideoSegmentTimelineProps {
  duration: number
  /** Tramo(s) conservados del clip, en orden cronologico y sin solaparse
   * (ver RM-40) -- lo que queda afuera de esta lista se descarta. Son
   * SIEMPRE posiciones reales en la fuente (no cambian al "juntar" dos
   * tramos, ver mas abajo). */
  keepRanges: [number, number][]
  onChange: (ranges: [number, number][]) => void
  /** Doble clic en la franja (ver mejora pedida tras probar RM-40): saltar
   * el preview a ese punto exacto para inspeccionarlo. */
  onSeek: (time: number) => void
  /** Posicion actual de reproduccion del preview (ver mejora pedida tras
   * probar RM-40) -- dibuja un indicador movil sobre la franja para saber
   * en que parte de TODO el clip (no solo de los tramos conservados) va la
   * reproduccion. */
  currentTime: number
  disabled?: boolean
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

/** Resta `cut` de cada rango de `ranges` -- parte un rango en dos si el
 * corte cae en el medio, lo acorta si cae en un borde, o lo elimina del
 * todo si el corte lo cubre por completo. */
function subtractRange(ranges: [number, number][], cut: [number, number]): [number, number][] {
  const [cutStart, cutEnd] = cut
  const result: [number, number][] = []
  for (const [start, end] of ranges) {
    if (cutEnd <= start || cutStart >= end) {
      result.push([start, end])
      continue
    }
    if (cutStart > start) result.push([start, cutStart])
    if (cutEnd < end) result.push([cutEnd, end])
  }
  return result
}

/** Calcula la posicion de cada tramo en el eje de PANTALLA de la franja --
 * coincide con su posicion real en la fuente (`keepRanges`) salvo que el
 * hueco anterior este en `closedGaps`, en cuyo caso ese tramo se dibuja
 * pegado al anterior (sin el espacio vacio de por medio). "Unir" dos
 * tramos (ver handleRangeBodyDrag) SOLO cambia esto -- nunca los valores
 * de `keepRanges` -- por eso ninguno de los dos pierde ni resamplea su
 * contenido original al juntarse. */
function computeDisplaySlots(ranges: [number, number][], closedGaps: number[]): [number, number][] {
  const slots: [number, number][] = []
  let cursor = ranges.length > 0 ? ranges[0][0] : 0
  for (let i = 0; i < ranges.length; i++) {
    const [start, end] = ranges[i]
    const span = end - start
    slots.push([cursor, cursor + span])
    cursor += span
    if (i < ranges.length - 1) {
      const gapWidth = ranges[i + 1][0] - end
      if (!closedGaps.includes(i)) cursor += gapWidth
    }
  }
  return slots
}

/** Convierte un punto en tiempo REAL de la fuente a su posicion en la
 * franja (inversa de `displayToSource`) -- usado para dibujar el
 * indicador movil de reproduccion y la seleccion pendiente del modo
 * corte, que manejan tiempo real de la fuente (el video no sabe de
 * huecos "cerrados"). */
function sourceToDisplay(
  sourceTime: number,
  ranges: [number, number][],
  slots: [number, number][],
): number {
  for (let i = 0; i < ranges.length; i++) {
    const [start, end] = ranges[i]
    if (sourceTime <= end) {
      const [displayStart] = slots[i]
      if (sourceTime >= start) return displayStart + (sourceTime - start)
      const prevEnd = i > 0 ? ranges[i - 1][1] : 0
      const prevDisplayEnd = i > 0 ? slots[i - 1][1] : 0
      return prevDisplayEnd + (sourceTime - prevEnd)
    }
  }
  if (ranges.length === 0) return sourceTime
  const last = ranges.length - 1
  const [, lastEnd] = ranges[last]
  const [, lastDisplayEnd] = slots[last]
  return lastDisplayEnd + (sourceTime - lastEnd)
}

/** Convierte una posicion en la franja (lo que el mouse toca) a tiempo
 * REAL de la fuente -- inversa de `sourceToDisplay`, usada por todas las
 * interacciones (doble clic, seleccion de corte, bordes) para que sigan
 * operando en tiempo real de la fuente aunque haya huecos cerrados
 * corriendo el resto de la franja hacia la izquierda. */
function displayToSource(
  displayTime: number,
  ranges: [number, number][],
  slots: [number, number][],
  duration: number,
): number {
  for (let i = 0; i < ranges.length; i++) {
    const [start] = ranges[i]
    const [displayStart, displayEnd] = slots[i]
    // `< displayEnd` (no `<=`) salvo en el ultimo tramo: cuando el hueco
    // siguiente esta cerrado, el fin de pantalla de este tramo coincide
    // exactamente con el inicio de pantalla del proximo (mismo pixel) --
    // ese punto debe resolverse como el INICIO del tramo siguiente (su
    // propio contenido), no como el final de este.
    const matches = i === ranges.length - 1 ? displayTime <= displayEnd : displayTime < displayEnd
    if (matches) {
      if (displayTime >= displayStart) return start + (displayTime - displayStart)
      const prevEnd = i > 0 ? ranges[i - 1][1] : 0
      const prevDisplayEnd = i > 0 ? slots[i - 1][1] : 0
      const gapDisplayWidth = displayStart - prevDisplayEnd
      if (gapDisplayWidth <= 0) return start
      const t = (displayTime - prevDisplayEnd) / gapDisplayWidth
      return prevEnd + t * (start - prevEnd)
    }
  }
  if (ranges.length === 0) return clamp(displayTime, 0, duration)
  const last = ranges.length - 1
  const [, lastEnd] = ranges[last]
  const [, lastDisplayEnd] = slots[last]
  return lastEnd + (displayTime - lastDisplayEnd)
}

/** Franja horizontal para elegir QUE tramos de un clip de video conservar
 * en la linea de tiempo del micro-video (ver RM-40) -- reemplaza el
 * recorte de un unico rango de RM-36: ahora se pueden quitar varios
 * tramos sueltos (uno cerca del inicio, otro del medio, otro del final) y
 * quedarse solo con el resto, en su orden cronologico original. Sin forma
 * de onda: el audio del clip se descarta siempre (ver
 * GenerateMicroVideoUseCase, render_clip_video es mudo).
 *
 * Interacciones (mejoradas tras probar la v1 y v2 de RM-40):
 * - Modo ESTANDAR (por defecto, cursor de manito): agarrar CUALQUIER punto
 *   del CUERPO de un tramo (no los bordes) y arrastrar hacia un vecino lo
 *   "junta" -- oculta el hueco entre ambos en la franja SIN tocar el
 *   contenido de ninguno de los dos (ninguno se resamplea ni se pierde,
 *   ver `computeDisplaySlots`) -- arrastrar en la direccion contraria
 *   vuelve a separarlos. El contenido que habia EN el hueco (lo que se
 *   corto) no vuelve por este medio -- para deshacer el corte original
 *   esta Cmd+Z, no "separar" de nuevo.
 * - Los bordes (franjas mas oscuras en los extremos de cada tramo, cursor
 *   de resize) SOLO responden si se hace clic justo en ellos (nunca desde
 *   el cuerpo) y solo permiten ACORTAR un tramo hacia su propio interior
 *   -- el borde que da a un hueco (el fin de un tramo con otro a la
 *   derecha, o el inicio de un tramo con otro a la izquierda) no puede
 *   estirarse HACIA el hueco: ese contenido ya fue eliminado por un corte
 *   y no se reclama arrastrando el borde (evita el bug ya reportado de
 *   "revivir" contenido cortado). Los bordes exteriores (el inicio del
 *   primer tramo, el fin del ultimo) no tienen hueco al costado y siguen
 *   totalmente libres, igual que en RM-36.
 * - Modo CORTE (activado con el boton de tijera, cursor de cruz): arrastrar
 *   DENTRO de un tramo marca una seleccion pendiente (contorno punteado),
 *   moviendo el preview EN VIVO al punto hasta el cual se va extendiendo
 *   (para ver que contenido se va a perder, no elegirlo a ciegas) -- el
 *   boton de tacho (o las teclas Delete/Backspace) la convierte en un
 *   corte real, partiendo el tramo, y el modo vuelve solo al estandar. Un
 *   corte nuevo siempre deshace cualquier union hecha antes (ver
 *   `commitDelete`) -- simplifica no tener que re-mapear que huecos
 *   seguian "cerrados" tras cambiar cuantos tramos hay.
 * - Doble clic en cualquier punto de la franja: salta el preview a ese
 *   punto exacto (pausado, para inspeccionar el frame) -- funciona sobre
 *   un tramo conservado o sobre un hueco ya eliminado por igual.
 * - Deshacer/Rehacer (botones + Cmd+Z / Cmd+Shift+Z, o Ctrl en no-Mac):
 *   un historial LOCAL a este componente (incluye que huecos estaban
 *   unidos, no solo los tramos) -- se reinicia solo porque la pagina lo
 *   remonta con `key={activeMediaIndex}` al cambiar de item, no persiste
 *   entre recargas.
 * - Un indicador movil (`currentTime`) marca en todo momento donde va la
 *   reproduccion del preview dentro de la duracion total del clip.
 *
 * "Unir" tramos es un concepto PURAMENTE VISUAL de este componente -- el
 * backend ya concatena los tramos conservados uno detras del otro sin
 * huecos al renderizar el video final (ver GenerateMicroVideoUseCase),
 * con o sin "union"; `keepRanges` (lo unico que sale de este componente)
 * nunca incluye que huecos estan unidos.
 *
 * Mouse y touch events puros (no Pointer Events/setPointerCapture): mismo
 * criterio que TextOverlayCanvas, evita un bug de larga data en Safari que
 * rompe pointermove/pointerup tras capturar el puntero (ver trackDrag en
 * lib/dragEvents.ts) -- funciona igual con mouse o con un dedo. */
export function VideoSegmentTimeline({
  duration,
  keepRanges,
  onChange,
  onSeek,
  currentTime,
  disabled,
}: VideoSegmentTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null)
  const [cutMode, setCutMode] = useState(false)
  const [pendingSelection, setPendingSelection] = useState<[number, number] | null>(null)
  const [closedGaps, setClosedGaps] = useState<number[]>([])
  const [past, setPast] = useState<HistoryEntry[]>([])
  const [future, setFuture] = useState<HistoryEntry[]>([])

  const slots = useMemo(() => computeDisplaySlots(keepRanges, closedGaps), [keepRanges, closedGaps])

  function fractionAt(clientX: number): number {
    const track = trackRef.current
    if (!track) return 0
    const rect = track.getBoundingClientRect()
    return clamp((clientX - rect.left) / rect.width, 0, 1)
  }

  function displayTimeAt(clientX: number): number {
    return fractionAt(clientX) * duration
  }

  function sourceTimeAt(clientX: number): number {
    return displayToSource(displayTimeAt(clientX), keepRanges, slots, duration)
  }

  function startDrag(onMove: (displayTime: number) => void, onEnd?: () => void) {
    trackDrag((clientX) => onMove(displayTimeAt(clientX)), onEnd)
  }

  // Un unico punto de entrada al historial -- SIEMPRE se llama con el
  // estado ANTES del cambio (una vez por gesto: al empezar un arrastre de
  // borde, al confirmar un borrado, o al unir/separar dos tramos), nunca
  // en cada paso intermedio de un drag, para que deshacer un gesto lo
  // deshaga entero de una.
  function pushHistory(previousRanges: [number, number][], previousClosedGaps: number[]) {
    setPast((p) => [...p, { ranges: previousRanges, closedGaps: previousClosedGaps }])
    setFuture([])
  }

  // `onChange` (que dispara un setState del componente PADRE) se llama
  // aca afuera de cualquier actualizador funcional de setState -- llamarlo
  // DENTRO de uno actualiza un componente distinto mientras React todavia
  // esta resolviendo el render de este, lo cual React marca como invalido
  // (advertencia real, confirmada en la practica). undo/redo se disparan
  // desde un evento discreto (click o atajo de teclado), no en cada paso
  // de un drag, asi que leer `past`/`future` directo del closure (sin
  // forma funcional) es seguro aca.
  function undo() {
    if (past.length === 0) return
    const previous = past[past.length - 1]
    setPast(past.slice(0, -1))
    setFuture([{ ranges: keepRanges, closedGaps }, ...future])
    setClosedGaps(previous.closedGaps)
    onChange(previous.ranges)
  }

  function redo() {
    if (future.length === 0) return
    const next = future[0]
    setFuture(future.slice(1))
    setPast([...past, { ranges: keepRanges, closedGaps }])
    setClosedGaps(next.closedGaps)
    onChange(next.ranges)
  }

  function commitDelete() {
    if (!pendingSelection || disabled) return
    const [start, end] = pendingSelection
    if (end - start < MIN_SPAN_SECONDS) {
      setPendingSelection(null)
      return
    }
    const next = subtractRange(keepRanges, [start, end])
    if (next.length === 0) {
      // No se puede borrar TODO lo que queda -- un item necesita conservar
      // al menos un tramo.
      setPendingSelection(null)
      return
    }
    pushHistory(keepRanges, closedGaps)
    // Un corte nuevo cambia cuantos tramos hay (y sus indices), lo que
    // invalidaria cualquier indice guardado en closedGaps -- en vez de
    // re-mapearlos, simplemente se pierden las uniones hechas antes (se
    // pueden rehacer con un arrastre mas, o deshacer este corte con
    // Cmd+Z si se prefiere recuperarlas).
    setClosedGaps([])
    onChange(next)
    setPendingSelection(null)
    // Una vez cortado, vuelve sola al modo estandar (mejora pedida tras
    // probar RM-40) -- cortar es una accion puntual, no un modo en el que
    // quedarse trabajado.
    setCutMode(false)
  }

  function toggleCutMode() {
    if (disabled) return
    setPendingSelection(null)
    setCutMode((prev) => !prev)
  }

  // Cmd+Z / Cmd+Shift+Z (Ctrl en no-Mac) deshace/rehace; Delete/Backspace
  // confirma una seleccion pendiente -- ignorado si el foco esta en un
  // campo de texto, para no pisar el undo nativo del navegador en otra
  // parte del editor.
  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const active = document.activeElement
      if (active instanceof HTMLElement && ['INPUT', 'TEXTAREA'].includes(active.tagName)) return
      const meta = event.metaKey || event.ctrlKey
      if (meta && event.key.toLowerCase() === 'z') {
        event.preventDefault()
        if (event.shiftKey) redo()
        else undo()
      } else if ((event.key === 'Delete' || event.key === 'Backspace') && pendingSelection) {
        event.preventDefault()
        commitDelete()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- undo/redo/commitDelete cierran sobre keepRanges/closedGaps/past/future/pendingSelection, listados aca
  }, [keepRanges, closedGaps, past, future, pendingSelection])

  // Borde IZQUIERDO del tramo `index` -- SOLO responde si se hace clic
  // justo en el (ver JSX, es un div de 10px aparte del cuerpo). Para el
  // primer tramo (sin hueco a la izquierda) es libre, igual que en RM-36.
  // Para cualquier otro, queda CONGELADO en su posicion actual como piso
  // -- nunca puede cruzar hacia el hueco (ese contenido ya fue cortado),
  // solo puede crecer hacia la DERECHA (acortar el propio tramo).
  function handleLeftEdgeDown(event: DragStartEvent, index: number) {
    if (disabled) return
    if (!('touches' in event)) event.preventDefault()
    event.stopPropagation()
    pushHistory(keepRanges, closedGaps)
    const [start, end] = keepRanges[index]
    const lowerBound = index > 0 ? start : 0
    startDrag((displayTime) => {
      const sourceTime = displayToSource(displayTime, keepRanges, slots, duration)
      const newStart = clamp(sourceTime, lowerBound, end - MIN_SPAN_SECONDS)
      const updated = keepRanges.map((r, i): [number, number] => (i === index ? [newStart, end] : r))
      onChange(updated)
    })
  }

  // Idem, para el borde DERECHO del tramo `index` -- libre solo si es el
  // ultimo tramo (sin hueco a la derecha); si no, congelado como techo, y
  // solo puede acortarse moviendose hacia la IZQUIERDA.
  function handleRightEdgeDown(event: DragStartEvent, index: number) {
    if (disabled) return
    if (!('touches' in event)) event.preventDefault()
    event.stopPropagation()
    pushHistory(keepRanges, closedGaps)
    const [start, end] = keepRanges[index]
    const upperBound = index < keepRanges.length - 1 ? end : duration
    startDrag((displayTime) => {
      const sourceTime = displayToSource(displayTime, keepRanges, slots, duration)
      const newEnd = clamp(sourceTime, start + MIN_SPAN_SECONDS, upperBound)
      const updated = keepRanges.map((r, i): [number, number] => (i === index ? [start, newEnd] : r))
      onChange(updated)
    })
  }

  // Modo ESTANDAR: agarrar el CUERPO de un tramo (nunca dispara si el clic
  // fue en un borde -- esos tienen su propio div y detienen la
  // propagacion) y arrastrar hacia un vecino lo "une" (oculta el hueco,
  // sin tocar contenido de ninguno de los dos); arrastrar en la direccion
  // contraria separa de nuevo un hueco ya unido. Se decide recien al
  // soltar el mouse (no en cada paso), comparando el desplazamiento neto
  // contra JOIN_DRAG_THRESHOLD_SECONDS -- asi un clic tembloroso no une o
  // separa por accidente.
  function handleRangeBodyDrag(event: DragStartEvent, index: number) {
    if (disabled) return
    if (!('touches' in event)) event.preventDefault()
    const start = dragPoint(event)
    if (!start) return
    const grabTime = displayTimeAt(start.clientX)
    let netDelta = 0
    startDrag(
      (displayTime) => {
        netDelta = displayTime - grabTime
      },
      () => {
        const hasRightNeighbor = index < keepRanges.length - 1
        const hasLeftNeighbor = index > 0
        if (netDelta > JOIN_DRAG_THRESHOLD_SECONDS) {
          if (hasRightNeighbor && !closedGaps.includes(index)) {
            pushHistory(keepRanges, closedGaps)
            setClosedGaps([...closedGaps, index])
          } else if (hasLeftNeighbor && closedGaps.includes(index - 1)) {
            pushHistory(keepRanges, closedGaps)
            setClosedGaps(closedGaps.filter((g) => g !== index - 1))
          }
        } else if (netDelta < -JOIN_DRAG_THRESHOLD_SECONDS) {
          if (hasLeftNeighbor && !closedGaps.includes(index - 1)) {
            pushHistory(keepRanges, closedGaps)
            setClosedGaps([...closedGaps, index - 1])
          } else if (hasRightNeighbor && closedGaps.includes(index)) {
            pushHistory(keepRanges, closedGaps)
            setClosedGaps(closedGaps.filter((g) => g !== index))
          }
        }
      },
    )
  }

  // Modo CORTE: arrastrar dentro de un tramo marca una seleccion pendiente
  // a eliminar (ver commitDelete). Ademas, mueve el preview al punto HASTA
  // el cual se esta extendiendo la seleccion (mejora pedida tras probar
  // RM-40: sin esto, se elegia el tramo a borrar "a ciegas", sin ver que
  // contenido se iba a perder). Se throttlea a ~20 saltos/seg -- onSeek
  // dispara un setState en la pagina que re-renderiza el lienzo entero,
  // y mousemove nativo llega mucho mas seguido que eso durante un arrastre
  // rapido.
  function handleRangeBodySelect(event: DragStartEvent, range: [number, number]) {
    if (disabled) return
    if (!('touches' in event)) event.preventDefault()
    const start = dragPoint(event)
    if (!start) return
    const [rangeStart, rangeEnd] = range
    const anchor = clamp(sourceTimeAt(start.clientX), rangeStart, rangeEnd)
    setPendingSelection([anchor, anchor])
    onSeek(anchor)
    let lastSeekAt = 0
    startDrag((displayTime) => {
      const current = clamp(displayToSource(displayTime, keepRanges, slots, duration), rangeStart, rangeEnd)
      setPendingSelection([Math.min(anchor, current), Math.max(anchor, current)])
      const now = performance.now()
      if (now - lastSeekAt > 50) {
        lastSeekAt = now
        onSeek(current)
      }
    })
  }

  function handleTrackDoubleClick(event: ReactMouseEvent) {
    if (disabled) return
    onSeek(sourceTimeAt(event.clientX))
  }

  const totalKept = keepRanges.reduce((sum, [start, end]) => sum + (end - start), 0)
  const playheadDisplayTime = sourceToDisplay(currentTime, keepRanges, slots)
  const pendingSelectionDisplay = pendingSelection
    ? ([
        sourceToDisplay(pendingSelection[0], keepRanges, slots),
        sourceToDisplay(pendingSelection[1], keepRanges, slots),
      ] as const)
    : null

  return (
    <div className="flex flex-col gap-3 rounded-xl border border-border bg-secondary/30 p-4">
      <div className="flex items-center gap-3">
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{formatClockTime(0)}</span>
        <div
          ref={trackRef}
          onDoubleClick={handleTrackDoubleClick}
          className="relative h-14 flex-1 select-none rounded-lg bg-muted"
        >
          {keepRanges.map(([start, end], index) => {
            const [displayStart, displayEnd] = slots[index]
            const joinedWithNext = index < keepRanges.length - 1 && closedGaps.includes(index)
            return (
              <div
                key={`${start}-${end}`}
                onMouseDown={(event) =>
                  cutMode ? handleRangeBodySelect(event, [start, end]) : handleRangeBodyDrag(event, index)
                }
                onTouchStart={(event) =>
                  cutMode ? handleRangeBodySelect(event, [start, end]) : handleRangeBodyDrag(event, index)
                }
                className={cn(
                  'absolute inset-y-0 touch-none rounded-md bg-primary/20',
                  cutMode ? 'cursor-crosshair' : 'cursor-grab active:cursor-grabbing',
                  joinedWithNext && 'border-r-2 border-secondary',
                )}
                style={{
                  left: `${(displayStart / duration) * 100}%`,
                  width: `${((displayEnd - displayStart) / duration) * 100}%`,
                }}
              >
                <div
                  onMouseDown={(event) => handleLeftEdgeDown(event, index)}
                  onTouchStart={(event) => handleLeftEdgeDown(event, index)}
                  className="absolute inset-y-0 left-0 w-2.5 touch-none cursor-ew-resize rounded-l-md bg-primary"
                  aria-label={`Inicio del tramo ${index + 1}`}
                />
                <div
                  onMouseDown={(event) => handleRightEdgeDown(event, index)}
                  onTouchStart={(event) => handleRightEdgeDown(event, index)}
                  className="absolute inset-y-0 right-0 w-2.5 touch-none cursor-ew-resize rounded-r-md bg-primary"
                  aria-label={`Fin del tramo ${index + 1}`}
                />
              </div>
            )
          })}
          {pendingSelectionDisplay && (
            <div
              className="pointer-events-none absolute inset-y-0 rounded-md border-2 border-dashed border-destructive bg-destructive/10"
              style={{
                left: `${(pendingSelectionDisplay[0] / duration) * 100}%`,
                width: `${((pendingSelectionDisplay[1] - pendingSelectionDisplay[0]) / duration) * 100}%`,
              }}
            />
          )}
          {/* Indicador movil de la posicion actual de reproduccion (ver
           * mejora pedida tras probar RM-40) -- sobre TODA la duracion del
           * clip, no solo los tramos conservados, para ubicarse siempre
           * aunque el preview este pausado en un hueco (ver seekRequest en
           * TextOverlayCanvas). Convertido a posicion de PANTALLA por si
           * hay huecos unidos de por medio. */}
          <div
            className="pointer-events-none absolute inset-y-0 z-10 w-0.5 bg-foreground"
            style={{ left: `${clamp((playheadDisplayTime / duration) * 100, 0, 100)}%` }}
          >
            <div className="absolute -top-1 left-1/2 h-2 w-2 -translate-x-1/2 rotate-45 bg-foreground" />
          </div>
        </div>
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{formatClockTime(duration)}</span>
      </div>
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          {cutMode
            ? 'Arrastra dentro de un tramo para elegir que eliminar.'
            : 'Arrastra un tramo hacia un vecino para unirlos (o al reves para separarlos), o el borde para acortarlo. Doble clic para saltar a un punto.'}{' '}
          Dura {totalKept.toFixed(1)}s de {formatClockTime(duration)} en total.
        </p>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={undo}
            disabled={disabled || past.length === 0}
            aria-label="Deshacer"
            className="h-8 w-8"
          >
            <Undo2 className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={redo}
            disabled={disabled || future.length === 0}
            aria-label="Rehacer"
            className="h-8 w-8"
          >
            <Redo2 className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={toggleCutMode}
            disabled={disabled}
            aria-label={cutMode ? 'Desactivar herramienta de corte' : 'Activar herramienta de corte'}
            aria-pressed={cutMode}
            className={cn('h-8 w-8', cutMode && 'bg-primary/10 text-primary')}
          >
            <Scissors className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={commitDelete}
            disabled={disabled || !pendingSelection}
            aria-label="Eliminar el tramo seleccionado"
            className={cn('h-8 w-8', pendingSelection && 'text-destructive')}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}
