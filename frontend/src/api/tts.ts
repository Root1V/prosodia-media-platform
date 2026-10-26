import { apiClient } from './client'

export type NarrationMode = 'draft' | 'polish'

/** Ayuda con el texto a narrar (ver RM-55).
 *
 * `draft` redacta a partir de una idea y escribe en `language`, que es el
 * idioma elegido para el audio. `polish` corrige lo que ya hay y **no recibe
 * idioma**: corregir no es traducir.
 *
 * Lo que devuelve es texto editable que el usuario revisa antes de generar
 * nada; la ayuda es opcional, el texto no.
 */
export async function assistNarrationText(input: {
  text: string
  mode: NarrationMode
  language: string
}): Promise<string> {
  const { data } = await apiClient.post<{ text: string }>('/tts/narration-text', input)
  return data.text
}
