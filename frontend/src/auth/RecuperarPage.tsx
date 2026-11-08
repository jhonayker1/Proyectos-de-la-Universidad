/**
 * "¿Olvidaste tu contraseña?": el backend escribe un código de 6 dígitos en la consola del
 * servidor; con ese código se define la contraseña nueva.
 */
import React from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, KeyRound, Terminal } from 'lucide-react'
import logoImg from '@/assets/logo.jpeg'
import { authApi } from '@/api/endpoints'
import { errorText } from '@/shared/components/ui'

export default function RecuperarPage() {
  const navigate = useNavigate()
  const [paso, setPaso] = React.useState<'correo' | 'codigo'>('correo')
  const [correo, setCorreo] = React.useState('')
  const [codigo, setCodigo] = React.useState('')
  const [password, setPassword] = React.useState('')
  const [password2, setPassword2] = React.useState('')
  const [error, setError] = React.useState<string | null>(null)
  const [busy, setBusy] = React.useState(false)

  const solicitar = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await authApi.solicitarCodigo(correo.trim())
      setPaso('codigo')
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  const confirmar = async (e: React.FormEvent) => {
    e.preventDefault()
    if (password.length < 8) return setError('La contraseña debe tener al menos 8 caracteres.')
    if (password !== password2) return setError('Las contraseñas no coinciden.')
    setBusy(true)
    setError(null)
    try {
      await authApi.confirmarCodigo(correo.trim(), codigo.trim(), password)
      navigate('/login', { replace: true, state: { aviso: 'Contraseña actualizada. Ya puede iniciar sesión.', correo: correo.trim() } })
    } catch (err) {
      setError(errorText(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-secondary p-4">
      <div className="w-full max-w-sm rounded-2xl bg-card p-8 shadow-2xl">
        <div className="mb-6 flex flex-col items-center gap-3 text-center">
          <img src={logoImg} alt="Cauchos Rey" className="h-16 w-16 rounded-2xl bg-black object-cover" />
          <div>
            <h1 className="m-0 text-xl font-bold">Restablecer contraseña</h1>
            <p className="mt-1 text-xs text-muted-foreground">
              {paso === 'correo' ? 'Paso 1 de 2 · indique su correo' : 'Paso 2 de 2 · código y nueva contraseña'}
            </p>
          </div>
        </div>

        {paso === 'correo' ? (
          <form onSubmit={solicitar}>
            <label className="mb-4 block">
              <span className="label">Correo</span>
              <input className="input" type="email" autoComplete="username" required autoFocus value={correo} onChange={e => setCorreo(e.target.value)} />
            </label>
            <p className="mb-5 text-xs text-muted-foreground">
              Por seguridad, el código no se envía por correo: aparece en la ventana donde está corriendo el servidor del sistema.
            </p>
            {error && <div role="alert" className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-xs font-semibold text-danger">{error}</div>}
            <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy}>
              <KeyRound size={15} /> {busy ? 'Generando...' : 'Generar código'}
            </button>
          </form>
        ) : (
          <form onSubmit={confirmar}>
            <div className="mb-4 flex gap-2.5 rounded-xl border border-primary/25 bg-primary/5 p-3 text-xs">
              <Terminal size={16} className="mt-0.5 shrink-0 text-primary" />
              <div>
                Si <b>{correo}</b> pertenece a un usuario activo, en la ventana del servidor (la terminal donde corre
                <code className="mx-1 rounded bg-muted px-1">run.py</code>) apareció un <b>código de 6 dígitos</b>. Vence en 10 minutos.
              </div>
            </div>
            <label className="mb-3.5 block">
              <span className="label">Código</span>
              <input className="input text-center font-display !text-xl font-bold tracking-[0.4em]" inputMode="numeric" autoComplete="one-time-code"
                maxLength={6} required autoFocus value={codigo} onChange={e => setCodigo(e.target.value.replace(/\D/g, ''))} />
            </label>
            <label className="mb-3.5 block">
              <span className="label">Nueva contraseña</span>
              <input className="input" type="password" autoComplete="new-password" required placeholder="Mínimo 8 caracteres" value={password} onChange={e => setPassword(e.target.value)} />
            </label>
            <label className="mb-5 block">
              <span className="label">Repita la contraseña</span>
              <input className="input" type="password" autoComplete="new-password" required value={password2} onChange={e => setPassword2(e.target.value)} />
            </label>
            {error && <div role="alert" className="mb-4 rounded-lg bg-danger/10 px-3 py-2 text-xs font-semibold text-danger">{error}</div>}
            <button type="submit" className="btn-primary w-full !py-2.5" disabled={busy || codigo.length !== 6}>
              {busy ? 'Guardando...' : 'Cambiar contraseña'}
            </button>
            <button type="button" className="mt-3 w-full cursor-pointer border-none bg-transparent text-xs font-semibold text-primary" onClick={() => solicitar()} disabled={busy}>
              ¿No aparece el código? Generar otro
            </button>
          </form>
        )}

        <Link to="/login" className="mt-5 flex items-center justify-center gap-1.5 text-xs font-semibold text-muted-foreground no-underline hover:text-foreground">
          <ArrowLeft size={13} /> Volver al inicio de sesión
        </Link>
      </div>
    </div>
  )
}
