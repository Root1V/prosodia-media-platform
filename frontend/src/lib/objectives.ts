import type { CaptionHighlightStyle } from '../types/project'
import type { MusicCategory } from '../types/musicTracks'

/**
 * Para que se hace el video (ver RM-42).
 *
 * El editor y el pipeline son los mismos para los dos: RM-42 no agrega
 * herramientas, agrega el objetivo que las orienta. Lo que cambia es lo que la
 * app PROPONE antes de que el usuario toque nada -- ninguna herramienta
 * desaparece, y todo lo de aqui se puede cambiar a mano en su panel.
 */
export type Objective = 'product' | 'professional'

export const DEFAULT_OBJECTIVE: Objective = 'product'

interface ObjectiveProfile {
  label: string
  /** Una linea, en segunda persona: es lo que se lee al elegir. */
  description: string
  /** null = el video dura lo que tarde la narracion. */
  targetDuration: number | null
  captionHighlightStyle: CaptionHighlightStyle
  /** Categoria de musica que se ofrece primero. NO preselecciona una pista:
   * "sin musica" sigue siendo el estado inicial de los dos perfiles, porque
   * elegir la banda sonora por el usuario es decidir, no proponer. */
  suggestedMusicCategory: MusicCategory | null
}

export const OBJECTIVES: Record<Objective, ObjectiveProfile> = {
  // IMPORTANTE: "product" tiene que reproducir EXACTAMENTE los defaults que la
  // app ya tenia antes de RM-42 -- es el unico objetivo que servia, asi que
  // cualquier desvio aqui degrada RM-14/RM-28 sin que nadie lo decida. Hay un
  // test que fija esos valores del lado del backend
  // (test_build_micro_video_use_case_and_request_defaults_are_the_product_profile).
  product: {
    label: 'Promocionar un producto',
    description: 'Vender algo en redes: el video engancha y termina en una llamada a la acción.',
    targetDuration: null,
    captionHighlightStyle: 'background',
    suggestedMusicCategory: null,
  },
  professional: {
    label: 'Posicionar tu perfil profesional',
    description: 'Publicar una idea en LinkedIn o X: no vendes, construyes criterio.',
    // Fija, y corta: en una red profesional el video compite con el texto del
    // post, no con otros videos. Sin tope, la narracion se alarga sola y el
    // resultado deja de servir para el sitio donde se va a publicar.
    targetDuration: 30,
    // Sin caja de color detras del texto: el karaoke y los fondos opacos leen
    // como contenido de entretenimiento. Solo cambia el color de la palabra.
    captionHighlightStyle: 'text_color',
    suggestedMusicCategory: 'commercials_professional',
  },
}

/** Tolerante a proposito: lo que venga de la URL es de fuera y no se puede
 * confiar en que sea un objetivo valido. Un valor desconocido cae al default
 * en vez de romper el editor, mismo criterio que el backend con este campo. */
export function parseObjective(raw: string | null | undefined): Objective {
  return raw && raw in OBJECTIVES ? (raw as Objective) : DEFAULT_OBJECTIVE
}
