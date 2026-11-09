import { Navigate, Outlet, useLocation } from 'react-router-dom'
import type { Rol } from '@/api/types'
import { Spinner } from '@/shared/components/ui'
import { homeFor, useAuth } from './AuthContext'

/** Deja pasar solo al rol indicado; si es otro rol lo manda a su propio panel. */
export default function RequireRole({ rol }: { rol: Rol }) {
  const { user, checking } = useAuth()
  const location = useLocation()
  if (checking) return <Spinner label="Verificando sesión..." className="h-screen" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />
  if (user.rol !== rol) return <Navigate to={homeFor(user.rol)} replace />
  return <Outlet />
}
