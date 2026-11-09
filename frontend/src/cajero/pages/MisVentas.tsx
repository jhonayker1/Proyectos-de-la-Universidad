/** Reportes del cajero: solo sus propias ventas (el backend filtra por usuario). */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Download } from 'lucide-react'
import { ventasApi } from '@/api/endpoints'
import { keys } from '@/api/queries'
import RespaldoVentas from '@/shared/components/RespaldoVentas'
import { useTasas } from '@/shared/components/productos'
import { Badge, EmptyState, QueryState, StatBox, errorText, useToast } from '@/shared/components/ui'
import { fmtHora, todayIso } from '@/shared/lib/dates'
import { fmtMoneda, usd } from '@/shared/lib/money'
import { pdfHistorialDia, totalesVentas } from '@/shared/lib/pdf'

export default function MisVentas() {
  const toast = useToast()
  const { tasas } = useTasas()
  const hoy = todayIso()
  const ventas = useQuery({ queryKey: [...keys.ventas, 'dia', hoy], queryFn: () => ventasApi.list({ dia: hoy, limite: 500 }) })
  const [pdf, setPdf] = React.useState(false)
  const t = totalesVentas(ventas.data ?? [])

  const descargar = async () => {
    setPdf(true)
    try { await pdfHistorialDia(ventas.data ?? [], tasas.VES) } catch (e) { toast(errorText(e), 'error') } finally { setPdf(false) }
  }

  return (
    <div className="flex flex-col gap-6 pb-6">
      <section>
        <div className="mb-3.5 flex items-center justify-between gap-3">
          <h2 className="m-0 text-lg font-bold">Mis ventas de hoy</h2>
          <button className="btn-primary" disabled={t.ventas === 0 || pdf} onClick={descargar}>
            <Download size={15} /> {pdf ? 'Generando PDF...' : 'Descargar historial PDF'}
          </button>
        </div>
        <div className="card overflow-hidden !rounded-[14px]">
          <div className="grid grid-cols-3 gap-3 border-b border-border p-4">
            <StatBox label="Ventas completadas" value={t.ventas} color="#10b981" />
            <StatBox label="Artículos vendidos" value={t.articulos} color="#4f46e5" />
            <StatBox label="Total facturado" value={usd(t.usd)} color="#06b6d4" />
          </div>
          <QueryState query={ventas}>
            {data => data.length === 0 ? <EmptyState title="Aún no se han registrado ventas hoy." /> : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-[13px]">
                  <thead>
                    <tr className="border-b-2 border-border bg-muted">
                      {['Factura', 'Hora', 'Producto', 'Cantidad', 'Precio unit.', 'Subtotal USD', 'Pago', 'Estado'].map(h => <th key={h} className="th !py-2.5">{h}</th>)}
                    </tr>
                  </thead>
                  <tbody>
                    {data.flatMap(v => v.detalles.map((d, i) => (
                      <tr key={`${v.id_venta}-${d.id_detalle}`} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'} ${v.estado === 'Anulada' ? 'opacity-60' : ''}`}>
                        <td className="td !py-2.5 font-bold whitespace-nowrap text-primary">{v.numero_factura}</td>
                        <td className="td !py-2.5 whitespace-nowrap text-muted-foreground">{fmtHora(v.fecha_venta)}</td>
                        <td className="td !py-2.5 min-w-60 font-medium">{d.nombre_producto_snapshot}</td>
                        <td className="td !py-2.5 font-bold">{d.cantidad}</td>
                        <td className="td !py-2.5 whitespace-nowrap text-muted-foreground">{usd(d.precio_unitario_usd)}</td>
                        <td className="td !py-2.5 font-extrabold whitespace-nowrap text-success">{usd(d.subtotal_usd)}</td>
                        <td className="td !py-2.5 whitespace-nowrap text-muted-foreground">{i === 0 ? fmtMoneda(v.monto_total_moneda, v.codigo_moneda_pago) : ''}</td>
                        <td className="td !py-2.5">{i === 0 && <Badge>{v.estado}</Badge>}</td>
                      </tr>
                    )))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryState>
        </div>
      </section>
      <RespaldoVentas titulo="Respaldo de mis ventas por semana / mes" />
    </div>
  )
}
