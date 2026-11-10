import React from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { LogIn } from 'lucide-react'
import logoImg from '@/assets/logo.jpeg'
import { errorText, PasswordInput, Spinner } from '@/shared/components/ui'
import { homeFor, useAuth } from './AuthContext'

export default function LoginPage() {
  const { user, checking, notice, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  // Al volver de "Restablecer contraseña" llega un aviso y el correo ya escrito.
  const desdeRecuperar = location.state as { aviso?: string; correo?: string } | null
  const [correo, setCorreo] = React.useState(desdeRecuperar?.correo ?? '')
  const [password, setPassword] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  if (checking) return <Spinner label="Verificando sesión..." className="h-screen" />
  if (user) return <Navigate to={homeFor(user.rol)} replace />

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const me = await login(correo.trim(), password)
      const from = (location.state as { from?: string } | null)?.from
      const destino = homeFor(me.rol)
      navigate(from?.startsWith(destino) ? from : destino, { replace: true })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary p-4">
      <form onSubmit={submit} className="w-full max-w-sm rounded-2xl bg-card p-8 shadow-2xl">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img src={logoImg} alt="Cauchos Rey" className="h-16 w-16 rounded-2xl bg-black object-cover" />
          <div>
            <h1 className="m-0 text-xl font-bold">Representaciones July Cauchos Rey</h1>
            <p className="mt-1 text-xs text-muted-foreground">Sistema de inventario y ventas</p>
          </div>
        </div>
        {desdeRecuperar?.aviso && <div className="mb-4 rounded-lg bg-success/15 px-3 py-2 text-xs font-semibold text-success">{desdeRecuperar.aviso}</div>}
        {notice && <div className="mb-4 rounded-lg bg-warning/15 px-3 py-2 text-xs font-semibold text-warning">{notice}</div>}
        <label className="mb-4 block">
          <span className="label">Correo</span>
          <input className="input" type="email" autoComplete="username" required autoFocus value={correo} onChange={e => setCorreo(e.target.value)} />
        </label>
        <label className="mb-5 block">
          <span className="label">Contraseña</span>
          <PasswordInput autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} />
        </label>
        {error && <div role="alert" className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-xs font-semibold text-danger">{error}</div>}
        <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy}>
          <LogIn size={15} /> {busy ? 'Ingresando...' : 'Ingresar'}
        </button>
        <Link to="/recuperar" className="mt-4 block text-center text-xs font-semibold text-primary no-underline hover:underline">
          ¿Olvidaste tu contraseña?
        </Link>
      </form>
    </div>
  )
}
