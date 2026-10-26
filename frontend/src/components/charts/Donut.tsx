export interface Segmento {
  key: string
  label: string
  value: number
  /** Clase de Tailwind que fija `color`; el arco usa currentColor. */
  className: string
}

interface DonutProps {
  segments: Segmento[]
  /** Lo que va en el centro. */
  total: number
  caption: string
  size?: number
}

/** Anillo de proporciones, dibujado con `stroke-dasharray` sobre un círculo.
 *
 * Sin arcos a mano: un círculo con el trazo segmentado da el mismo resultado
 * con una fracción del código, y no hay casos raros con un único segmento que
 * ocupa el 100% (que con paths de arco se dibuja al revés o no se dibuja). */
export function Donut({ segments, total, caption, size = 132 }: DonutProps) {
  const radio = 54
  const circunferencia = 2 * Math.PI * radio
  const suma = segments.reduce((n, s) => n + s.value, 0)

  let acumulado = 0
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg viewBox="0 0 132 132" className="h-full w-full -rotate-90">
        <circle
          cx="66"
          cy="66"
          r={radio}
          fill="none"
          strokeWidth="14"
          className="text-secondary"
          stroke="currentColor"
        />
        {suma > 0 &&
          segments
            .filter((s) => s.value > 0)
            .map((s) => {
              const largo = (s.value / suma) * circunferencia
              const offset = -acumulado
              acumulado += largo
              return (
                <circle
                  key={s.key}
                  cx="66"
                  cy="66"
                  r={radio}
                  fill="none"
                  strokeWidth="14"
                  strokeDasharray={`${largo} ${circunferencia - largo}`}
                  strokeDashoffset={offset}
                  className={s.className}
                  stroke="currentColor"
                >
                  <title>{`${s.label}: ${s.value}`}</title>
                </circle>
              )
            })}
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-2xl font-semibold leading-none">{total}</span>
        <span className="mt-1 text-[10px] uppercase tracking-wide text-muted-foreground">
          {caption}
        </span>
      </div>
    </div>
  )
}
