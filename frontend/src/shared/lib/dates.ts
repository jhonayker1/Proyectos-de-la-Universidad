/** Fechas en hora local (la misma zona del negocio que usa el backend: America/Caracas). */

export const iso = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export const todayIso = () => iso(new Date())

/** Interpreta "2026-11-03" o "2026-11-03T14:20:00" como hora local (sin desplazar zona). */
export function parseLocal(s: string) {
  const [d, t = '00:00:00'] = s.split('T')
  const [y, m, day] = d.split('-').map(Number)
  const [hh, mm, ss] = t.split(':').map(x => Number(x.slice(0, 2)))
  return new Date(y, m - 1, day, hh || 0, mm || 0, ss || 0)
}

export function startOfWeek(d: Date) {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  x.setDate(x.getDate() + (x.getDay() === 0 ? -6 : 1 - x.getDay()))
  return x
}

export type Periodo = 'Hoy' | 'Esta Semana' | 'Este Mes'

export function rangoPeriodo(p: Periodo): { desde: string; hasta: string } {
  const hoy = new Date()
  if (p === 'Hoy') return { desde: iso(hoy), hasta: iso(hoy) }
  if (p === 'Esta Semana') return { desde: iso(startOfWeek(hoy)), hasta: iso(hoy) }
  return { desde: iso(new Date(hoy.getFullYear(), hoy.getMonth(), 1)), hasta: iso(hoy) }
}

export type ModoRespaldo = 'Semanal' | 'Mensual'

/** Semana (lun-dom) o mes, retrocediendo `offset` períodos desde el actual. */
export function rangoRespaldo(modo: ModoRespaldo, offset: number) {
  const hoy = new Date()
  hoy.setHours(0, 0, 0, 0)
  if (modo === 'Semanal') {
    const ini = startOfWeek(hoy)
    ini.setDate(ini.getDate() - 7 * offset)
    const fin = new Date(ini)
    fin.setDate(ini.getDate() + 6)
    return { ini, fin }
  }
  const ini = new Date(hoy.getFullYear(), hoy.getMonth() - offset, 1)
  const fin = new Date(ini.getFullYear(), ini.getMonth() + 1, 0)
  return { ini, fin }
}

export const fmtFecha = (d: Date) => d.toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric' })
export const fmtFechaLarga = (d: Date) => d.toLocaleDateString('es-VE', { day: 'numeric', month: 'long', year: 'numeric' })
export const fmtDia = (d: Date) => d.toLocaleDateString('es-VE', { weekday: 'short', day: '2-digit', month: 'short' })
export const fmtMes = (d: Date) => d.toLocaleDateString('es-VE', { month: 'long', year: 'numeric' })
export const fmtHora = (s: string | null) =>
  s ? parseLocal(s).toLocaleTimeString('es-VE', { hour: '2-digit', minute: '2-digit', hour12: false }) : ''
export const fmtFechaHora = (s: string | null) =>
  s ? `${parseLocal(s).toLocaleDateString('es-VE')} ${fmtHora(s)}` : ''
