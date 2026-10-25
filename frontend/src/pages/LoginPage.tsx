import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { AudioLines, Captions, Clapperboard, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Alert } from '../components/ui/Alert'
import { ThemeToggle } from '../components/ui/ThemeToggle'

/** El login es la unica pantalla que ve alguien que todavia no entro, asi
 * que es el unico sitio donde cabe decir que hay adentro. Tres, no cinco:
 * la lista es para orientar, no para enumerar el menu. */
const CAPACIDADES = [
  { icon: AudioLines, text: 'Dobla tus videos del inglés al español, con voz natural' },
  { icon: Captions, text: 'Genera subtítulos traducidos, listos para publicar' },
  { icon: Clapperboard, text: 'Crea micro-videos para LinkedIn y X en menos de un minuto' },
]

/** Hasta ahora todo fallo decia "correo o contraseña incorrectos" o un
 * "intenta de nuevo" a secas. Son tres situaciones muy distintas y el
 * cliente no podia distinguirlas:
 *
 *   - la cuenta esta desactivada  -> reintentar no sirve, hay que avisar
 *   - el servidor no responde     -> el error no esta en lo que escribio
 *   - la contraseña esta mal      -> el unico caso donde reintentar sirve
 *
 * El backend ya mandaba el motivo en `detail` (routers/auth.py); lo que
 * faltaba era leerlo.
 */
function mensajeDeError(err: unknown): string {
  if (!axios.isAxiosError(err)) {
    return 'No se pudo iniciar sesión. Vuelve a intentarlo.'
  }
  // Sin `response` no hubo respuesta HTTP (no hay red). Y 502/503/504 son el
  // MISMO caso con la API apagada: quien contesta es el proxy que tiene
  // delante -- Vite en desarrollo, el servidor web en produccion -- no ella.
  // Decir "el servidor respondio" ahi es falso, y "reintenta" es mal consejo:
  // reintentar no levanta un proceso caido.
  if (!err.response || [502, 503, 504].includes(err.response.status)) {
    return 'No se pudo contactar al servidor de Prosodia. Puede estar apagado o reiniciándose; si sigue igual, avisa a quien lo administra.'
  }
  if (err.response.status === 401) {
    const detalle: unknown = err.response.data?.detail
    if (typeof detalle === 'string' && detalle.toLowerCase().includes('inactivo')) {
      return 'Tu cuenta está desactivada. Pídele a quien administra Prosodia que la reactive.'
    }
    return 'Correo o contraseña incorrectos.'
  }
  return `El servidor respondió con un error (${err.response.status}). Vuelve a intentarlo en un momento.`
}

export function LoginPage() {
  const { login, isAuthenticated } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [verContrasena, setVerContrasena] = useState(false)
  const [hayMayusculas, setHayMayusculas] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  if (isAuthenticated) {
    const redirectTo = (location.state as { from?: string } | null)?.from ?? '/'
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(mensajeDeError(err))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-2">
      {/* El degradado no sigue el tema, igual que el menu lateral (ver el
          comentario de --sidebar en index.css): es superficie de marca, y
          en oscuro un violeta mas claro contrastaria peor con el blanco. */}
      <aside className="flex flex-col justify-center gap-10 bg-[linear-gradient(140deg,hsl(243,75%,52%)_0%,hsl(258,72%,36%)_100%)] px-6 py-10 text-white lg:px-14 lg:py-16">
        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt=""
            className="h-10 w-10 shrink-0 rounded-xl bg-white/15 object-contain p-1.5"
          />
          <span className="text-xl font-semibold tracking-tight">Prosodia</span>
        </div>

        <div className="max-w-md">
          <h1 className="text-2xl font-semibold leading-snug lg:text-4xl">
            Tus videos, hablando español.
          </h1>
          <p className="mt-3 text-sm text-white/70 lg:text-base">
            Sube un video o una idea. Prosodia se encarga del resto.
          </p>
        </div>

        {/* En movil el panel es solo la cabecera: la lista empujaria el
            formulario fuera de la pantalla, que es lo contrario de ayudar. */}
        <ul className="hidden max-w-md flex-col gap-4 lg:flex">
          {CAPACIDADES.map(({ icon: Icon, text }) => (
            <li key={text} className="flex items-start gap-3 text-sm text-white/85">
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/15">
                <Icon className="h-4 w-4" />
              </span>
              <span className="pt-1.5">{text}</span>
            </li>
          ))}
        </ul>
      </aside>

      <main className="relative flex items-center justify-center px-6 py-12 lg:py-16">
        <ThemeToggle className="absolute right-4 top-4 lg:right-6 lg:top-6" />

        <div className="w-full max-w-sm">
          <h2 className="text-2xl font-semibold tracking-tight">Entra a tu cuenta</h2>
          <p className="mt-1.5 text-sm text-muted-foreground">
            Usa el correo con el que te dieron acceso.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5">
            {error && <Alert variant="error">{error}</Alert>}

            <div className="flex flex-col gap-1.5">
              <label htmlFor="email" className="text-sm font-medium">
                Correo electrónico
              </label>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                autoFocus
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@empresa.com"
                className="h-11"
              />
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="password" className="text-sm font-medium">
                Contraseña
              </label>
              <div className="relative">
                <Input
                  id="password"
                  type={verContrasena ? 'text' : 'password'}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  // Bloq Mayus es la causa silenciosa de medio "correo o
                  // contraseña incorrectos": el campo oculta lo escrito, asi
                  // que no hay forma de notarlo sin decirlo.
                  onKeyUp={(e: KeyboardEvent<HTMLInputElement>) =>
                    setHayMayusculas(e.getModifierState('CapsLock'))
                  }
                  placeholder="••••••••"
                  className="h-11 pr-11"
                />
                <button
                  type="button"
                  onClick={() => setVerContrasena((v) => !v)}
                  aria-label={verContrasena ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  title={verContrasena ? 'Ocultar contraseña' : 'Mostrar contraseña'}
                  className="absolute right-0 top-0 flex h-11 w-11 items-center justify-center rounded-r-xl text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {verContrasena ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
              {hayMayusculas && (
                <p className="text-xs text-warning">Tienes Bloq Mayús activado.</p>
              )}
            </div>

            <Button type="submit" size="lg" className="mt-1 w-full" disabled={isSubmitting}>
              {isSubmitting ? 'Entrando…' : 'Entrar'}
            </Button>
          </form>

          {/* No hay endpoint de recuperacion (routers/auth.py solo tiene
              login y me), asi que un enlace aqui seria un callejon sin
              salida. Mejor decir la verdad: a quien olvido su contraseña
              hoy lo desatasca una persona. */}
          <p className="mt-8 text-center text-xs leading-relaxed text-muted-foreground">
            ¿Olvidaste tu contraseña? Todavía no hay recuperación automática:
            escríbele a quien administra Prosodia.
          </p>
        </div>
      </main>
    </div>
  )
}
