/** Formato de montos. El backend envía los Decimal como string. */

export const num = (v: string | number | null | undefined) => {
  const n = typeof v === 'number' ? v : parseFloat(v ?? '0')
  return Number.isFinite(n) ? n : 0
}

const nf = (locale: string, digits: number) =>
  new Intl.NumberFormat(locale, { minimumFractionDigits: digits, maximumFractionDigits: digits })

const usdFmt = nf('en-US', 2)
const vesFmt = nf('es-VE', 2)
const copFmt = nf('es-CO', 0)

export const usd = (v: string | number | null | undefined) => `$${usdFmt.format(num(v))}`

/** Monto en la moneda indicada (USD, VES o COP). */
export function fmtMoneda(v: string | number | null | undefined, codigo: string) {
  const n = num(v)
  switch (codigo.trim().toUpperCase()) {
    case 'VES':
      return `Bs. ${vesFmt.format(n)}`
    case 'COP':
      return `COP ${copFmt.format(n)}`
    default:
      return `$${usdFmt.format(n)}`
  }
}

export const fmtTasa = (v: string | number, codigo: string) =>
  codigo === 'COP' ? copFmt.format(num(v)) : vesFmt.format(num(v))

/** Redondeo a centavos igual al del backend (ROUND_HALF_UP). */
export const round2 = (n: number) => Math.round((n + Number.EPSILON) * 100) / 100

/** Precio de venta = costo × (1 + margen/100). */
export const precioConMargen = (costo: number, margen: number) => round2(costo * (1 + margen / 100))

/** Convierte un texto con coma o punto decimal a número; NaN si no es válido. */
export const parseDecimal = (s: string) => Number(s.trim().replace(',', '.'))
