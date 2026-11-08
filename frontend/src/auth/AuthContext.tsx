import React from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { getToken, setToken, setUnauthorizedHandler } from '@/api/client'
import { authApi } from '@/api/endpoints'
import type { Usuario } from '@/api/types'

type AuthState = {
  user: Usuario | null
  /** true mientras se valida un token guardado al abrir la app. */
  checking: boolean
  /** Mensaje para el login (p. ej. "La sesión expiró"). */
  notice: string | null
  login: (correo: string, password: string) => Promise<Usuario>
  logout: (notice?: string) => void
}

const AuthContext = React.createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const qc = useQueryClient()
  const [user, setUser] = React.useState<Usuario | null>(null)
  const [checking, setChecking] = React.useState(() => getToken() !== null)
  const [notice, setNotice] = React.useState<string | null>(null)

  const logout = React.useCallback((message?: string) => {
    setToken(null)
    setUser(null)
    qc.clear()
    setNotice(message ?? null)
  }, [qc])

  React.useEffect(() => {
    setUnauthorizedHandler(() => logout('Su sesión expiró. Inicie sesión de nuevo.'))
    return () => setUnauthorizedHandler(null)
  }, [logout])

  // Al recargar la página, el token guardado se valida con /auth/me.
  React.useEffect(() => {
    if (!getToken()) return
    authApi.me()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setChecking(false))
  }, [])

  const login = React.useCallback(async (correo: string, password: string) => {
    const token = await authApi.login(correo, password)
    setToken(token.access_token)
    const me = await authApi.me()
    setNotice(null)
    setUser(me)
    return me
  }, [])

  const value = React.useMemo(() => ({ user, checking, notice, login, logout }), [user, checking, notice, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = React.useContext(AuthContext)
  if (!ctx) throw new Error('useAuth debe usarse dentro de AuthProvider')
  return ctx
}

/** El usuario autenticado; solo se usa dentro de rutas protegidas. */
export function useCurrentUser() {
  const { user } = useAuth()
  if (!user) throw new Error('No hay usuario autenticado')
  return user
}

export const homeFor = (rol: Usuario['rol']) => (rol === 'admin' ? '/admin' : '/cajero')
