import { useId } from 'react'

export interface Serie {
  key: string
  label: string
  /** Clase de Tailwind que fija `color`; el trazo y el relleno usan
   * currentColor, así la serie se tiñe entera con una sola clase. */
  className: string
  values: number[]
}

interface AreaChartProps {
  series: Serie[]
  /** Una por punto, en el mismo orden que `values`. */
  labels: string[]
  /** Qué poner en el tooltip de cada punto; recibe el índice. */
  tooltip: (indice: number) => string
}

const ALTO = 150
const ANCHO = 600
/** Hueco a la izquierda para los números del eje. */
const MARGEN_IZQ = 26
const MARGEN_INF = 18

type Punto = readonly [number, number]

/** Catmull-Rom convertido a bezier cubica: curva que pasa por todos los
 * puntos, en vez de aproximarlos.
 *
 * Los puntos de control se recortan a la banda del grafico porque una serie
 * que toca el cero y vuelve a subir genera tangentes que se van por debajo
 * de la linea base, y el area quedaria con una panza fuera del eje. */
function curva(puntos: Punto[], base: number): string {
  if (puntos.length < 2) return ''
  const limitar = (y: number) => Math.max(0, Math.min(base, y))
  let d = `M${puntos[0][0].toFixed(1)} ${puntos[0][1].toFixed(1)}`
  for (let i = 0; i < puntos.length - 1; i++) {
    const p0 = puntos[i === 0 ? 0 : i - 1]
    const p1 = puntos[i]
    const p2 = puntos[i + 1]
    const p3 = puntos[i + 2] ?? p2
    const c1x = p1[0] + (p2[0] - p0[0]) / 6
    const c1y = limitar(p1[1] + (p2[1] - p0[1]) / 6)
    const c2x = p2[0] - (p3[0] - p1[0]) / 6
    const c2y = limitar(p2[1] - (p3[1] - p1[1]) / 6)
    d += ` C${c1x.toFixed(1)} ${c1y.toFixed(1)}, ${c2x.toFixed(1)} ${c2y.toFixed(1)}, ${p2[0].toFixed(1)} ${p2[1].toFixed(1)}`
  }
  return d
}

function ruta(values: number[], maximo: number): { linea: string; area: string } {
  const util = ANCHO - MARGEN_IZQ
  const base = ALTO - MARGEN_INF
  const puntos: Punto[] = values.map((v, i) => [
    MARGEN_IZQ + (i / Math.max(values.length - 1, 1)) * util,
    base * (1 - v / maximo),
  ])
  const linea = curva(puntos, base)
  const area = `${linea} L${puntos[puntos.length - 1][0].toFixed(1)} ${base} L${puntos[0][0].toFixed(1)} ${base} Z`
  return { linea, area }
}

/** Varias series por día, como áreas superpuestas.
 *
 * Superpuestas y no apiladas a propósito: "completadas" y "fallidas" son
 * partes de "corridas", así que apilarlas contaría dos veces lo mismo y la
 * altura total mentiría. */
export function AreaChart({ series, labels, tooltip }: AreaChartProps) {
  const id = useId()
  const maximo = Math.max(...series.flatMap((s) => s.values), 1)
  // Tres marcas bastan: la del máximo, la de la mitad y el cero.
  const marcas = [maximo, Math.round(maximo / 2), 0]
  const util = ANCHO - MARGEN_IZQ

  return (
    <div className="w-full">
      <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="w-full" role="img">
        <defs>
          {series.map((s, i) => (
            <linearGradient key={s.key} id={`${id}-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="currentColor" stopOpacity="0.25" />
              <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>

        {marcas.map((marca) => {
          const y = (ALTO - MARGEN_INF) * (1 - marca / maximo)
          return (
            <g key={marca} className="text-border">
              <line
                x1={MARGEN_IZQ}
                y1={y}
                x2={ANCHO}
                y2={y}
                stroke="currentColor"
                strokeDasharray="3 4"
                strokeWidth="1"
              />
              <text x={0} y={y + 3} className="fill-muted-foreground text-[9px]">
                {marca}
              </text>
            </g>
          )
        })}

        {series.map((s, i) => {
          const { linea, area } = ruta(s.values, maximo)
          return (
            <g key={s.key} className={s.className}>
              <path d={area} fill={`url(#${id}-${i})`} />
              <path
                d={linea}
                fill="none"
                stroke="currentColor"
                strokeWidth="1.75"
                strokeLinejoin="round"
                vectorEffect="non-scaling-stroke"
              />
            </g>
          )
        })}

        {/* Una banda invisible por día: da el tooltip nativo sin añadir ni
            una línea de JavaScript ni estado. */}
        {labels.map((etiqueta, i) => (
          <rect
            key={etiqueta}
            x={MARGEN_IZQ + (i / Math.max(labels.length, 1)) * util}
            y={0}
            width={util / Math.max(labels.length, 1)}
            height={ALTO - MARGEN_INF}
            fill="transparent"
          >
            <title>{tooltip(i)}</title>
          </rect>
        ))}
      </svg>

      <div className="flex justify-between px-1 text-xs text-muted-foreground">
        <span>{labels[0]}</span>
        <span>{labels[Math.floor(labels.length / 2)]}</span>
        <span>{labels[labels.length - 1]}</span>
      </div>
    </div>
  )
}
