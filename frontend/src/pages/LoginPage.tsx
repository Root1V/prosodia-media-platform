import { useState } from 'react'
import type { FormEvent, KeyboardEvent } from 'react'
import { Navigate, useLocation, useNavigate } from 'react-router-dom'
import axios from 'axios'
import { ArrowRight, Check, Clapperboard, Eye, EyeOff, Lock, Mail, ShieldCheck } from 'lucide-react'
import { useAuth } from '../hooks/useAuth'
import { Button } from '../components/ui/Button'
import { Input } from '../components/ui/Input'
import { Alert } from '../components/ui/Alert'
import { ThemeToggle } from '../components/ui/ThemeToggle'

/** Lo que se ve dentro del proyecto de ejemplo del panel. No es una lista de
 * funciones: es una corrida como las que el cliente va a mirar todos los
 * dias, para que el login muestre el producto en vez de describirlo. */
const PASOS_DE_EJEMPLO = [
  'Transcripción con marcas de tiempo',
  'Traducción revisada contra tu glosario',
  'Voz clonada, sincronizada al video',
]

/** Hasta ahora todo fallo decia "correo o contraseña incorrectos" o un
 * "intenta de nuevo" a secas. Son situaciones muy distintas y el cliente no
 * podia distinguirlas:
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
    <div className="min-h-screen lg:grid lg:grid-cols-[1.05fr_1fr]">
      {/* El panel no sigue el tema, igual que el menu lateral (ver el
          comentario de --sidebar en index.css): es superficie de marca, y en
          oscuro un violeta mas claro contrastaria peor con el blanco. */}
      <aside className="relative isolate flex flex-col justify-between gap-6 overflow-hidden bg-[hsl(246,47%,7%)] px-6 py-9 text-white lg:gap-16 lg:px-14 lg:py-14">
        {/* Rejilla tenue, desvanecida hacia los bordes: da textura de
            herramienta sin competir con el texto. */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-10 bg-[linear-gradient(to_right,rgba(255,255,255,0.05)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.05)_1px,transparent_1px)] bg-[length:48px_48px] [mask-image:radial-gradient(ellipse_at_28%_40%,black,transparent_72%)]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -left-32 top-16 -z-10 h-[34rem] w-[34rem] rounded-full bg-[hsl(243,80%,55%)] opacity-25 blur-[130px]"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -right-24 bottom-0 -z-10 h-[26rem] w-[26rem] rounded-full bg-[hsl(262,80%,55%)] opacity-20 blur-[120px]"
        />

        <div className="flex items-center gap-3">
          <img
            src="/logo.png"
            alt=""
            className="h-9 w-9 shrink-0 rounded-xl bg-white/10 object-contain p-1.5"
          />
          <span className="text-lg font-semibold tracking-tight">Prosodia</span>
        </div>

        <div className="max-w-xl">
          <span className="inline-flex items-center rounded-full border border-white/15 bg-white/5 px-3 py-1 text-xs font-medium text-white/70">
            Plataforma de doblaje y video
          </span>

          <h1 className="mt-5 text-2xl font-semibold leading-[1.15] tracking-tight lg:mt-6 lg:text-[2.6rem] lg:leading-[1.12]">
            Tu video en español,{' '}
            <span className="text-[hsl(246,90%,76%)]">con tu propia voz</span>.
          </h1>

          <p className="mt-4 max-w-md text-sm leading-relaxed text-white/60 lg:mt-5 lg:text-base">
            Súbelo una vez. Prosodia transcribe, traduce, dobla y subtitula — y
            te deja el corte corto listo para publicar.
          </p>

          {/* Una corrida de ejemplo. En movil no cabe sin empujar el
              formulario fuera de la pantalla, que es lo contrario de ayudar. */}
          <div className="relative mb-8 mt-10 hidden max-w-md lg:block">
            {/* El pb-10 no es decorativo: reserva la banda donde cae la
                tarjeta flotante, para que no se coma el ultimo paso. */}
            <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-5 pb-10 shadow-2xl shadow-black/40 backdrop-blur-sm">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold">Campaña Q1 · inglés → español</p>
                  <p className="mt-0.5 text-xs text-white/50">Doblaje · 2 min 14 s · hace 3 min</p>
                </div>
                <span className="shrink-0 rounded-full bg-emerald-400/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
                  Listo
                </span>
              </div>

              <ul className="mt-5 flex flex-col gap-3">
                {PASOS_DE_EJEMPLO.map((paso) => (
                  <li key={paso} className="flex items-center gap-2.5 text-sm text-white/75">
                    <Check className="h-4 w-4 shrink-0 text-emerald-400" />
                    {paso}
                  </li>
                ))}
              </ul>
            </div>

            <div className="absolute -bottom-7 right-2 flex items-center gap-3 rounded-xl border border-white/10 bg-[hsl(246,40%,12%)] px-4 py-3 shadow-xl shadow-black/50">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10">
                <Clapperboard className="h-4 w-4" />
              </span>
              <div>
                <p className="text-sm font-medium">Micro-video · 0:28</p>
                <p className="text-xs text-white/50">listo para LinkedIn y X</p>
              </div>
            </div>
          </div>
        </div>

        <p className="hidden max-w-md text-xs leading-relaxed text-white/40 lg:block">
          Tus videos y tus voces son tuyos. Se procesan para generar lo que pediste
          y nada más.
        </p>
      </aside>

      <main className="relative flex items-center justify-center px-6 py-10 lg:px-10 lg:py-14">
        <ThemeToggle className="absolute right-4 top-4 lg:right-6 lg:top-6" />

        <div className="flex w-full max-w-sm flex-col">
          <h2 className="text-3xl font-semibold tracking-tight">Bienvenido de nuevo</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Ingresa con tu correo y contraseña.
          </p>

          <form onSubmit={handleSubmit} className="mt-8 flex flex-col gap-5 lg:mt-10">
            {error && <Alert variant="error">{error}</Alert>}

            <div className="flex flex-col gap-2">
              <label htmlFor="email" className="text-sm font-medium">
                Correo
              </label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="nombre@empresa.com"
                  className="h-11 pl-10"
                />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              <label htmlFor="password" className="text-sm font-medium">
                Contraseña
              </label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3.5 top-3.5 h-4 w-4 text-muted-foreground" />
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
                  className="h-11 pl-10 pr-11"
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

            <Button type="submit" className="mt-2 h-12 w-full text-base" disabled={isSubmitting}>
              {isSubmitting ? (
                'Entrando…'
              ) : (
                <>
                  <ArrowRight className="h-4 w-4" />
                  Ingresar
                </>
              )}
            </Button>
          </form>

          <div className="mt-10 flex items-end justify-between gap-6 text-xs text-muted-foreground lg:mt-14">
            {/* No hay endpoint de recuperacion (routers/auth.py solo tiene
                login y me), asi que un enlace aqui seria un callejon sin
                salida: a quien olvido su contraseña hoy lo desatasca una
                persona. */}
            <p className="max-w-[16rem] leading-relaxed">
              ¿No puedes ingresar? Pide ayuda a quien administra Prosodia.
            </p>
            {/* Solo si de verdad lo es. Un candado en una pagina servida por
                http seria exactamente la clase de sello que no hay que creer. */}
            {window.location.protocol === 'https:' && (
              <span className="flex shrink-0 items-center gap-1.5">
                <ShieldCheck className="h-3.5 w-3.5" />
                Conexión segura
              </span>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}
