/**
 * PDFs del sistema (historial del día, respaldo semanal/mensual, ticket y facturas).
 * Une los dos generadores que estaban duplicados en Admin/src/pdfLayout.ts y Cajero/InventoryApp.tsx.
 */
import logoPdf from '@/assets/logo-pdf.png'
import type { Venta } from '@/api/types'
import { fmtFechaLarga, fmtHora, iso, parseLocal } from './dates'
import { fmtMoneda, num } from './money'

type RGB = [number, number, number]
const NAVY: RGB = [15, 27, 61]
const GOLD: RGB = [245, 184, 0]
const INK: RGB = [31, 41, 55]
const MUTED: RGB = [107, 114, 128]

type Doc = InstanceType<typeof import('jspdf').jsPDF>

export function cargarImagen(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = reject
    img.src = src
  })
}

async function nuevoPdf(orientation: 'portrait' | 'landscape' = 'landscape', format: string | number[] = 'a4') {
  const { jsPDF } = await import('jspdf')
  return { pdf: new jsPDF({ orientation, unit: 'pt', format }), logo: await cargarImagen(logoPdf) }
}

/** Cabecera con logo; devuelve la coordenada Y donde empieza el contenido. */
function cabecera(pdf: Doc, logo: HTMLImageElement, titulo: string, subtitulo: string) {
  const W = pdf.internal.pageSize.getWidth()
  pdf.setFillColor(...NAVY); pdf.rect(0, 0, W, 84, 'F')
  pdf.setFillColor(...GOLD); pdf.rect(0, 84, W, 4, 'F')
  pdf.addImage(logo, 'PNG', 40, 14, 56, 56)
  pdf.setTextColor(255); pdf.setFont('helvetica', 'bold'); pdf.setFontSize(20)
  pdf.text(titulo, 112, 40)
  pdf.setFont('helvetica', 'normal'); pdf.setFontSize(9.5); pdf.setTextColor(200, 205, 220)
  pdf.text(subtitulo, 112, 58)
  pdf.setTextColor(...INK)
  return 108
}

function pies(pdf: Doc) {
  const W = pdf.internal.pageSize.getWidth()
  const H = pdf.internal.pageSize.getHeight()
  const n = pdf.getNumberOfPages()
  for (let i = 1; i <= n; i++) {
    pdf.setPage(i)
    pdf.setDrawColor(...GOLD); pdf.setLineWidth(1.2); pdf.line(40, H - 38, W - 40, H - 38)
    pdf.setFont('helvetica', 'normal'); pdf.setFontSize(8); pdf.setTextColor(...MUTED)
    pdf.text('Representaciones July Cauchos Rey  ·  Documento generado automaticamente', 40, H - 24)
    pdf.text(`Pagina ${i} de ${n}`, W - 40, H - 24, { align: 'right' })
  }
}

function tarjetas(pdf: Doc, y: number, stats: [string, string, RGB][]) {
  const W = pdf.internal.pageSize.getWidth()
  const M = 40
  const gap = 16
  const cw = (W - 2 * M - gap * (stats.length - 1)) / stats.length
  stats.forEach(([k, v, c], i) => {
    const x = M + i * (cw + gap)
    pdf.setFillColor(247, 249, 253); pdf.setDrawColor(232, 236, 245); pdf.setLineWidth(0.8)
    pdf.roundedRect(x, y, cw, 46, 7, 7, 'FD')
    pdf.setFont('helvetica', 'bold'); pdf.setFontSize(7.5); pdf.setTextColor(100, 116, 139)
    pdf.text(k, x + 14, y + 16)
    pdf.setFontSize(16); pdf.setTextColor(...c)
    pdf.text(v, x + 14, y + 36)
  })
  return y + 62
}

/** Tabla simple con cabecera repetida en cada página. */
function tabla(pdf: Doc, y: number, cols: { titulo: string; x: number }[], filas: string[][]) {
  const W = pdf.internal.pageSize.getWidth()
  const H = pdf.internal.pageSize.getHeight()
  const M = 40
  const head = (yy: number) => {
    pdf.setFillColor(79, 70, 229); pdf.roundedRect(M, yy, W - 2 * M, 28, 6, 6, 'F')
    pdf.setTextColor(255); pdf.setFont('helvetica', 'bold'); pdf.setFontSize(9.5)
    cols.forEach(c => pdf.text(c.titulo, M + c.x, yy + 18))
    return yy + 28
  }
  y = head(y)
  filas.forEach(fila => {
    if (y > H - 110) { pdf.addPage(); y = head(40) }
    pdf.setFont('helvetica', 'normal'); pdf.setFontSize(9); pdf.setTextColor(...INK)
    fila.forEach((txt, i) => {
      const next = cols[i + 1]?.x ?? W - 2 * M
      pdf.text(pdf.splitTextToSize(txt, next - cols[i].x - 8)[0] ?? '', M + cols[i].x, y + 19)
    })
    pdf.setDrawColor(238, 240, 246); pdf.setLineWidth(0.6); pdf.line(M, y + 28, W - M, y + 28)
    y += 29
  })
  return y
}

function totalFinal(pdf: Doc, y: number, texto: string) {
  const W = pdf.internal.pageSize.getWidth()
  const H = pdf.internal.pageSize.getHeight()
  y += 14
  if (y > H - 80) { pdf.addPage(); y = 40 }
  pdf.setFillColor(234, 241, 253); pdf.roundedRect(40, y, W - 80, 30, 6, 6, 'F')
  pdf.setFont('helvetica', 'bold'); pdf.setFontSize(11); pdf.setTextColor(43, 45, 130)
  pdf.text(texto, 56, y + 19)
}

const nombreCorto = (n: string | null) => {
  const [a, b] = (n ?? '').split(' ')
  return `${a ?? ''} ${b ? `${b[0]}.` : ''}`.trim()
}

/** Totales de ventas completadas (las anuladas no cuentan). */
export function totalesVentas(ventas: Venta[]) {
  const completadas = ventas.filter(v => v.estado !== 'Anulada')
  return {
    ventas: completadas.length,
    articulos: completadas.reduce((t, v) => t + v.detalles.reduce((s, d) => s + d.cantidad, 0), 0),
    usd: completadas.reduce((t, v) => t + num(v.monto_total_usd), 0),
  }
}

/** Historial de ventas del día: una fila por producto vendido. */
export async function pdfHistorialDia(ventas: Venta[], tasaBs: number | null) {
  const { pdf, logo } = await nuevoPdf()
  const ahora = new Date()
  const t = totalesVentas(ventas)
  let y = cabecera(pdf, logo, 'Historial de Ventas del Dia', `Emitido el ${fmtFechaLarga(ahora)}`)
  y = tarjetas(pdf, y, [
    ['VENTAS COMPLETADAS', String(t.ventas), [16, 185, 129]],
    ['ARTICULOS VENDIDOS', String(t.articulos), [79, 70, 229]],
    ['TOTAL FACTURADO', fmtMoneda(t.usd, 'USD'), [6, 182, 212]],
  ])
  const filas = [...ventas].reverse().filter(v => v.estado !== 'Anulada').flatMap(v =>
    v.detalles.map(d => [
      v.numero_factura, fmtHora(v.fecha_venta), d.nombre_producto_snapshot, String(d.cantidad),
      fmtMoneda(d.precio_unitario_usd, 'USD'), fmtMoneda(d.subtotal_usd, 'USD'), nombreCorto(v.nombre_usuario),
    ]),
  )
  y = tabla(pdf, y, [
    { titulo: 'Factura', x: 8 }, { titulo: 'Hora', x: 110 }, { titulo: 'Producto', x: 170 },
    { titulo: 'Cant.', x: 420 }, { titulo: 'Precio unit.', x: 475 }, { titulo: 'Subtotal', x: 565 },
    { titulo: 'Cajero', x: 650 },
  ], filas)
  const bs = tasaBs ? `  ·  ${fmtMoneda(t.usd * tasaBs, 'VES')}` : ''
  totalFinal(pdf, y, `Total facturado: ${fmtMoneda(t.usd, 'USD')}${bs}`)
  pies(pdf)
  pdf.save(`historial-ventas-${iso(ahora)}.pdf`)
}

export type DiaRespaldo = { fecha: Date; ventas: number; unidades: number; totalUSD: number }

/** Agrupa ventas completadas por día, incluyendo los días sin ventas del rango. */
export function ventasPorDia(ventas: Venta[], ini: Date, fin: Date): DiaRespaldo[] {
  const map = new Map<string, DiaRespaldo>()
  for (let d = new Date(ini); d <= fin; d.setDate(d.getDate() + 1)) {
    map.set(iso(d), { fecha: new Date(d), ventas: 0, unidades: 0, totalUSD: 0 })
  }
  for (const v of ventas) {
    if (v.estado === 'Anulada' || !v.fecha_venta) continue
    const dia = map.get(iso(parseLocal(v.fecha_venta)))
    if (!dia) continue
    dia.ventas += 1
    dia.unidades += v.detalles.reduce((s, d) => s + d.cantidad, 0)
    dia.totalUSD += num(v.monto_total_usd)
  }
  return [...map.values()]
}

export async function pdfRespaldo(modo: string, ini: Date, fin: Date, dias: DiaRespaldo[], tasaBs: number | null) {
  const { pdf, logo } = await nuevoPdf()
  const totalVentas = dias.reduce((t, d) => t + d.ventas, 0)
  const totalUnidades = dias.reduce((t, d) => t + d.unidades, 0)
  const totalUSD = dias.reduce((t, d) => t + d.totalUSD, 0)
  const subtitulo = modo === 'Semanal'
    ? `Periodo del ${fmtFechaLarga(ini)} al ${fmtFechaLarga(fin)}`
    : `Periodo: ${ini.toLocaleDateString('es-VE', { month: 'long', year: 'numeric' })}`
  let y = cabecera(pdf, logo, `Respaldo de Reportes ${modo}`, subtitulo)
  y = tarjetas(pdf, y, [
    ['VENTAS COMPLETADAS', String(totalVentas), [16, 185, 129]],
    ['ARTICULOS VENDIDOS', String(totalUnidades), [79, 70, 229]],
    ['TOTAL FACTURADO', fmtMoneda(totalUSD, 'USD'), [6, 182, 212]],
  ])
  y = tabla(pdf, y, [
    { titulo: 'Fecha', x: 8 }, { titulo: 'Ventas', x: 265 }, { titulo: 'Unidades', x: 375 },
    { titulo: 'Total USD', x: 500 }, ...(tasaBs ? [{ titulo: 'Total Bs.', x: 625 }] : []),
  ], dias.map(d => [
    d.fecha.toLocaleDateString('es-VE', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }),
    String(d.ventas), String(d.unidades), fmtMoneda(d.totalUSD, 'USD'),
    ...(tasaBs ? [fmtMoneda(d.totalUSD * tasaBs, 'VES')] : []),
  ]))
  const bs = tasaBs ? `  ·  ${fmtMoneda(totalUSD * tasaBs, 'VES')}` : ''
  totalFinal(pdf, y, `Total facturado: ${fmtMoneda(totalUSD, 'USD')}${bs}`)
  pies(pdf)
  pdf.save(`respaldo-${modo.toLowerCase()}-${iso(ini)}_${iso(fin)}.pdf`)
}

/** Ticket de venta en formato de recibo (80 mm) para el cliente. */
export async function pdfTicket(venta: Venta, cajero: string) {
  const ancho = 226 // 80 mm
  const alto = 230 + venta.detalles.length * 30
  const { pdf, logo } = await nuevoPdf('portrait', [ancho, alto])
  const cx = ancho / 2
  let y = 18
  pdf.addImage(logo, 'PNG', cx - 22, y, 44, 44)
  y += 58
  pdf.setFont('helvetica', 'bold'); pdf.setFontSize(10); pdf.setTextColor(...INK)
  pdf.text('Representaciones July Cauchos Rey', cx, y, { align: 'center' })
  y += 14
  pdf.setFont('helvetica', 'normal'); pdf.setFontSize(8); pdf.setTextColor(...MUTED)
  pdf.text(`${venta.numero_factura}  ·  ${venta.fecha_venta ? parseLocal(venta.fecha_venta).toLocaleString('es-VE') : ''}`, cx, y, { align: 'center' })
  y += 11
  pdf.text(`Cajero: ${cajero}`, cx, y, { align: 'center' })
  y += 10
  pdf.setDrawColor(200); pdf.setLineDashPattern([2, 2], 0); pdf.line(12, y, ancho - 12, y)
  y += 14
  pdf.setTextColor(...INK)
  for (const d of venta.detalles) {
    pdf.setFont('helvetica', 'bold'); pdf.setFontSize(8.5)
    pdf.text(pdf.splitTextToSize(d.nombre_producto_snapshot, ancho - 24)[0], 12, y)
    y += 11
    pdf.setFont('helvetica', 'normal'); pdf.setFontSize(8)
    pdf.text(`${d.cantidad} x ${fmtMoneda(d.precio_unitario_usd, 'USD')}`, 12, y)
    pdf.text(fmtMoneda(d.subtotal_usd, 'USD'), ancho - 12, y, { align: 'right' })
    y += 19
  }
  pdf.line(12, y - 8, ancho - 12, y - 8)
  y += 6
  pdf.setFont('helvetica', 'bold'); pdf.setFontSize(11)
  pdf.text('TOTAL USD', 12, y)
  pdf.text(fmtMoneda(venta.monto_total_usd, 'USD'), ancho - 12, y, { align: 'right' })
  if (venta.codigo_moneda_pago !== 'USD') {
    y += 15
    pdf.setFontSize(10)
    pdf.text(`TOTAL ${venta.codigo_moneda_pago}`, 12, y)
    pdf.text(fmtMoneda(venta.monto_total_moneda, venta.codigo_moneda_pago), ancho - 12, y, { align: 'right' })
    y += 12
    pdf.setFont('helvetica', 'normal'); pdf.setFontSize(7.5); pdf.setTextColor(...MUTED)
    pdf.text(`Tasa aplicada: ${num(venta.tasa_aplicada).toLocaleString('es-VE')} ${venta.codigo_moneda_pago}/USD`, 12, y)
  }
  if (venta.referencia_pago) {
    y += 11
    pdf.text(`Referencia de pago: ${venta.referencia_pago}`, 12, y)
  }
  y += 20
  pdf.setFontSize(8); pdf.setTextColor(...MUTED)
  pdf.text('Gracias por su compra', cx, y, { align: 'center' })
  pdf.save(`ticket-${venta.numero_factura}.pdf`)
}

/** Une las facturas (imágenes) del período en un solo PDF, una por página. */
export async function pdfFacturas(imagenes: { url: string; nombre: string }[], rango: string) {
  const { pdf, logo } = await nuevoPdf('portrait')
  const W = pdf.internal.pageSize.getWidth()
  const H = pdf.internal.pageSize.getHeight()
  for (let i = 0; i < imagenes.length; i++) {
    if (i > 0) pdf.addPage()
    const top = cabecera(pdf, logo, `FACTURA ${i + 1} DE ${imagenes.length}`, rango)
    const img = await cargarImagen(imagenes[i].url)
    const ratio = Math.min((W - 80) / img.width, (H - top - 64) / img.height)
    const w = img.width * ratio
    const h = img.height * ratio
    const x = (W - w) / 2
    pdf.setDrawColor(226, 229, 240); pdf.setLineWidth(1)
    pdf.roundedRect(x - 6, top - 6, w + 12, h + 12, 4, 4, 'S')
    pdf.addImage(img, 'JPEG', x, top, w, h)
  }
  pies(pdf)
  pdf.save(`facturas-${rango.replace(/\s+/g, '-')}.pdf`)
}
