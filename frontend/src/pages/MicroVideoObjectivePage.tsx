import { useNavigate } from 'react-router-dom'
import { Clapperboard, Briefcase } from 'lucide-react'
import { Card, CardContent } from '../components/ui/Card'
import { OBJECTIVES, VIDEO_FORMATS_LABEL_BY_OBJECTIVE } from '../lib/objectives'
import type { Objective } from '../lib/objectives'
import { cn } from '../lib/cn'

const ICONS: Record<Objective, typeof Clapperboard> = {
  product: Clapperboard,
  professional: Briefcase,
}

/**
 * Elegir para que es el video, antes de entrar al editor (ver RM-42).
 *
 * Es una pantalla propia y no un selector dentro del editor porque el objetivo
 * siembra los valores por defecto: ofrecerlo DENTRO, cuando esos valores ya
 * estan puestos y quiza tocados a mano, obligaria a decidir cuales pisar. Aqui
 * la respuesta es que no hay nada que pisar todavia.
 */
export function MicroVideoObjectivePage() {
  const navigate = useNavigate()

  const elegir = (objective: Objective) => {
    navigate(`/micro-video/new?objective=${objective}`)
  }

  const entries = Object.entries(OBJECTIVES) as [Objective, (typeof OBJECTIVES)[Objective]][]

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Micro-Video</h1>
        <p className="text-sm text-muted-foreground">
          ¿Para qué es este video? Las herramientas son las mismas; lo que cambia es lo que te
          proponemos por defecto. Puedes ajustarlo todo después en el editor.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {entries.map(([objective, profile]) => {
          const Icon = ICONS[objective]
          return (
            <button
              key={objective}
              type="button"
              onClick={() => elegir(objective)}
              className={cn(
                'text-left transition-colors',
                'rounded-xl border border-border hover:border-primary hover:bg-primary/5',
              )}
            >
              <Card className="h-full border-0 bg-transparent shadow-none">
                <CardContent className="flex h-full flex-col gap-3 p-6">
                  <Icon className="h-6 w-6 text-primary" aria-hidden />
                  <div className="flex flex-col gap-1">
                    <span className="text-base font-medium">{profile.label}</span>
                    <span className="text-sm text-muted-foreground">{profile.description}</span>
                  </div>
                  {/* Lo que el perfil cambia, dicho antes de elegir: si no se
                      ve aqui, la eleccion parece no tener consecuencias y la
                      primera reaccion es "no ha cambiado nada". */}
                  <ul className="mt-auto flex flex-col gap-1 pt-2 text-xs text-muted-foreground">
                    <li>{VIDEO_FORMATS_LABEL_BY_OBJECTIVE[objective]}</li>
                    <li>
                      {profile.targetDuration === null
                        ? 'Dura lo que dure la narración'
                        : `${profile.targetDuration} segundos`}
                    </li>
                  </ul>
                </CardContent>
              </Card>
            </button>
          )
        })}
      </div>
    </div>
  )
}
