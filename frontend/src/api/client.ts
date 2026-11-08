/** Cliente HTTP del backend FastAPI: token JWT, errores legibles y sesión vencida. */

const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') || '/api'
const TOKEN_KEY = 'cauchos_rey_token'
const SIN_CONEXION =
  'No se pudo conectar con el servidor. Verifique que el backend esté encendido (python run.py).'

export class ApiError extends Error {
  readonly status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let onUnauthorized: (() => void) | null = null

/** AuthContext registra aquí qué hacer cuando el token vence o es inválido. */
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(TOKEN_KEY, token)
    else sessionStorage.removeItem(TOKEN_KEY)
  } catch {
    /* almacenamiento no disponible: la sesión dura lo que la pestaña */
  }
}

/** FastAPI responde {detail: string} o {detail: [{loc, msg}]} en los 422. */
function errorMessage(status: number, body: unknown): string {
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map(d => {
        const item = d as { loc?: unknown[]; msg?: string }
        const field = item.loc?.filter(p => p !== 'body').join('.')
        const msg = (item.msg ?? 'Dato inválido').replace(/^Value error, /, '')
        return field ? `${field}: ${msg}` : msg
      })
      .join(' · ')
  }
  if (status >= 500) return 'Error del servidor. Intente nuevamente en unos segundos.'
  return `Error ${status}`
}

type Query = Record<string, string | number | boolean | null | undefined>

function buildUrl(path: string, query?: Query) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== '') qs.set(k, String(v))
  }
  const s = qs.toString()
  return `${API_URL}${path}${s ? `?${s}` : ''}`
}

async function request<T>(method: string, path: string, opts: { query?: Query; body?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = {}
  const token = getToken()
  if (token) headers.Authorization = `Bearer ${token}`
  let body: BodyInit | undefined
  if (opts.body instanceof FormData) body = opts.body
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }

  let res: Response
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body })
  } catch {
    throw new ApiError(0, SIN_CONEXION)
  }

  if (res.status === 401 && token) onUnauthorized?.()
  if (res.status === 204) return undefined as T
  const isJson = res.headers.get('content-type')?.includes('application/json')
  // El proxy de Vite responde 502/503/504 sin JSON cuando el backend está apagado.
  if (!isJson && res.status >= 502 && res.status <= 504) throw new ApiError(res.status, SIN_CONEXION)
  const data = isJson ? await res.json().catch(() => null) : null
  if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, data))
  return data as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, { query }),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, { body }),
  put: <T>(path: string, body?: unknown) => request<T>('PUT', path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, { body }),
  delete: <T = void>(path: string) => request<T>('DELETE', path),
  /** Descarga un archivo protegido (p. ej. una factura) como Blob. */
  async blob(path: string): Promise<Blob> {
    const token = getToken()
    const res = await fetch(buildUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} })
    if (res.status === 401 && token) onUnauthorized?.()
    if (!res.ok) throw new ApiError(res.status, errorMessage(res.status, await res.json().catch(() => null)))
    return res.blob()
  },
}
