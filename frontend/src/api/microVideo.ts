import { apiClient } from './client'
import type { Objective } from '../lib/objectives'

/** Genera un guion narrable a partir de una idea (ver RM-42).
 *
 * Es una ayuda del editor, no un paso del pipeline: el guion tiene que existir
 * ANTES de generar el video porque el usuario lo lee y lo corrige. Lo que
 * devuelve se escribe en el campo "Texto a narrar" como texto editable, nunca
 * se usa directamente.
 */
export async function writeMicroVideoScript(input: {
  idea: string
  objective: Objective
  target_seconds: number | null
}): Promise<string> {
  const { data } = await apiClient.post<{ script: string }>('/micro-video/script', input)
  return data.script
}
