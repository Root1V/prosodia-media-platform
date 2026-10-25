/**
 * Relacion de aspecto del video de salida (ver RM-42).
 *
 * Tiene que coincidir con VIDEO_FORMATS de
 * src/video_translator/application/use_cases/generate_micro_video.py: el
 * lienzo del editor es un preview del render, y si las dimensiones no son las
 * mismas lo que se arrastra no cae donde se ve.
 *
 * Deliberadamente separado de lib/objectives.ts: el lienzo dibuja un formato y
 * no tiene por que saber que objetivo lo eligio.
 */
export type VideoFormat = 'vertical' | 'square' | 'landscape'

export const VIDEO_FORMATS: Record<VideoFormat, { width: number; height: number; label: string }> = {
  vertical: { width: 1080, height: 1920, label: 'Vertical 9:16' },
  square: { width: 1080, height: 1080, label: 'Cuadrado 1:1' },
  landscape: { width: 1920, height: 1080, label: 'Horizontal 16:9' },
}

export const DEFAULT_VIDEO_FORMAT: VideoFormat = 'vertical'

/**
 * Tamanos en pixeles sobre el ancho del video -> fraccion del ancho del
 * contenedor (`cqw`).
 *
 * Los font_size de los overlays y los grosores de contorno/sombra se guardan
 * en pixeles del video, pero el lienzo se dibuja al ancho que haya en
 * pantalla. `cqw` es lo que hace que el preview escale igual que el render en
 * vez de quedarse en pixeles fijos.
 *
 * OJO: el divisor es el ancho del FORMATO, no 1080 fijo. En "landscape"
 * (1920 de ancho) el mismo font_size ocupa relativamente menos, igual que en
 * el render -- el backend mide sobre su propio ancho y no normaliza, asi que
 * normalizar aqui romperia la correspondencia entre preview y resultado, que
 * es lo unico que el usuario puede comprobar.
 */
export function pxToCqw(px: number, videoWidth: number): string {
  return `${(px / videoWidth) * 100}cqw`
}
