import { useId } from 'react'

interface SparklineProps {
  values: number[]
  /** Color de la línea. Se le aplica un degradado por debajo. */
  className?: string
}

/** Línea diminuta para acompañar una cifra: no lleva ejes ni valores porque
 * no se lee un número de ella, se lee una forma -- si sube, si baja, si hubo
 * un pico. El número exacto ya está al lado, en grande. */
export function Sparkline({ values, className = 'text-primary' }: SparklineProps) {
  const id = useId()
  if (values.length < 2) return null

  const ancho = 100
  const alto = 28
  const maximo = Math.max(...values, 1)
  const puntos = values.map((v, i) => {
    const x = (i / (values.length - 1)) * ancho
    // Se deja medio píxel de aire arriba y abajo para que una línea plana en
    // el máximo no se coma el borde del trazo.
    const y = alto - 1 - (v / maximo) * (alto - 2)
    return `${x.toFixed(2)},${y.toFixed(2)}`
  })

  return (
    <svg
      viewBox={`0 0 ${ancho} ${alto}`}
      preserveAspectRatio="none"
      className={`h-7 w-full ${className}`}
      aria-hidden
    >
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0.28" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon points={`0,${alto} ${puntos.join(' ')} ${ancho},${alto}`} fill={`url(#${id})`} />
      <polyline
        points={puntos.join(' ')}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
