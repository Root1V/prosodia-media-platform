import type { MouseEvent as ReactMouseEvent, TouchEvent as ReactTouchEvent } from 'react'

export type DragStartEvent = ReactMouseEvent | ReactTouchEvent

/** Posicion del puntero de un evento de mouse, o del primer dedo de un
 * evento de touch -- null si el touch ya no tiene ningun dedo activo (no
 * deberia pasar en touchstart, pero evita un crash si pasara). */
export function dragPoint(event: DragStartEvent): { clientX: number; clientY: number } | null {
  if ('touches' in event) {
    const touch = event.touches[0]
    return touch ? { clientX: touch.clientX, clientY: touch.clientY } : null
  }
  return { clientX: event.clientX, clientY: event.clientY }
}

/** Arranca a escuchar el resto de un gesto de arrastre (mouse O touch) en
 * `window`, llamando a `onMove` con cada posicion hasta soltar.
 *
 * Mouse y touch events nativos a proposito (no Pointer Events /
 * setPointerCapture): Safari tiene un bug de larga data donde, tras
 * setPointerCapture, pointermove/pointerup dejan de dispararse en cuanto el
 * cursor sale del elemento capturado -- incluso con los listeners puestos en
 * `window` (ver https://github.com/w3c/pointerevents/issues/407). Mouse y
 * touch events puros no tienen ese problema: el touch queda implicitamente
 * "capturado" por el elemento donde empezo sin necesidad de
 * setPointerCapture, asi que touchmove/touchend siguen llegando a `window`
 * sin importar donde se mueva el dedo en pantalla.
 *
 * El listener de touchmove necesita `{ passive: false }` para poder frenar
 * el scroll/zoom nativo de la pagina con preventDefault mientras dura el
 * arrastre -- los navegadores modernos tratan touchmove como pasivo por
 * defecto. */
export function trackDrag(onMove: (clientX: number, clientY: number) => void, onEnd?: () => void) {
  function handleMouseMove(event: MouseEvent) {
    onMove(event.clientX, event.clientY)
  }
  function handleTouchMove(event: TouchEvent) {
    const touch = event.touches[0]
    if (!touch) return
    event.preventDefault()
    onMove(touch.clientX, touch.clientY)
  }
  function stop() {
    window.removeEventListener('mousemove', handleMouseMove)
    window.removeEventListener('mouseup', stop)
    window.removeEventListener('touchmove', handleTouchMove)
    window.removeEventListener('touchend', stop)
    window.removeEventListener('touchcancel', stop)
    onEnd?.()
  }
  window.addEventListener('mousemove', handleMouseMove)
  window.addEventListener('mouseup', stop)
  window.addEventListener('touchmove', handleTouchMove, { passive: false })
  window.addEventListener('touchend', stop)
  window.addEventListener('touchcancel', stop)
}
