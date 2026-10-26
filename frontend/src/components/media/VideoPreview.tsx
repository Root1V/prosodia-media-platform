interface VideoPreviewProps {
  src: string
}

export function VideoPreview({ src }: VideoPreviewProps) {
  return (
    // Con `w-full` a secas, un micro-video cuadrado (1080x1080) o vertical
    // (1080x1920) se comia la pantalla entera: el alto lo decidia el ancho
    // del contenedor. El tope es del ALTO, y el ancho sale de la relacion
    // de aspecto, que es lo que hace cualquier reproductor.
    <div className="flex justify-center rounded-xl border border-border bg-black">
      <video
        controls
        preload="metadata"
        className="max-h-[60vh] w-auto max-w-full rounded-xl"
        src={src}
      >
        Tu navegador no soporta la reproducción de video.
      </video>
    </div>
  )
}
