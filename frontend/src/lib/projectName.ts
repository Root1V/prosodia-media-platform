function stripExtension(filename: string): string {
  const lastDot = filename.lastIndexOf('.')
  return lastDot > 0 ? filename.slice(0, lastDot) : filename
}

/** Nombre para un proyecto cuyo usuario no escribio ninguno.
 *
 * El nombre solo sirve para reconocerlo en la lista, asi que exigirlo antes
 * de dejar seguir es tramite: se saca de lo que ya se eligio. Antes cada
 * pagina lo resolvia a su manera -- y solo al subir un archivo, de modo que
 * quien pegaba una URL se topaba con un error por un campo que no habia
 * tenido motivo para mirar.
 */
export function nombreDesdeOrigen(
  file: File | null,
  sourceUrl: string | null,
  porDefecto: string,
): string {
  if (file) return stripExtension(file.name)
  if (sourceUrl) {
    try {
      const { hostname, pathname } = new URL(sourceUrl)
      const ultimo = pathname.split('/').filter(Boolean).pop()
      const host = hostname.replace(/^www\./, '')
      return ultimo ? `${host} · ${ultimo}` : host
    } catch {
      return porDefecto
    }
  }
  return porDefecto
}
