import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Ban, Download } from 'lucide-react'
import { ventasApi } from '@/api/endpoints'
import { keys, useApiMutation } from '@/api/queries'
import type { Venta } from '@/api/types'
import { useTasas } from '@/shared/components/productos'
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, QueryState, StatBox, errorText, useToast } from '@/shared/components/ui'
import { fmtHora, todayIso } from '@/shared/lib/dates'
import { fmtMoneda, usd } from '@/shared/lib/money'
import { pdfHistorialDia, totalesVentas } from '@/shared/lib/pdf'

export default function HistorialVentasDia() {
  const toast = useToast()
  const { tasas } = useTasas()
  const [dia, setDia] = React.useState(todayIso())
  const [pdf, setPdf] = React.useState(false)
  const [anular, setAnular] = React.useState<Venta | null>(null)
  const ventas = useQuery({ queryKey: [...keys.ventas, 'dia', dia], queryFn: () => ventasApi.list({ dia, limite: 1000 }) })
  const anulacion = useApiMutation((v: Venta) => ventasApi.anular(v.id_venta), [keys.ventas, keys.productos, keys.reportes], v => {
    toast(`Venta ${v.numero_factura} anulada; el stock fue devuelto.`); setAnular(null)
  })
  const t = totalesVentas(ventas.data ?? [])

  const descargar = async () => {
    setPdf(true)
    try { await pdfHistorialDia(ventas.data ?? [], tasas.VES) } catch (e) { toast(errorText(e), 'error') } finally { setPdf(false) }
  }

  return (
    <div className="mt-1.5">
      <div className="my-2.5 flex flex-wrap items-center justify-between gap-3">
        <h3 className="m-0 text-base font-bold">Historial de Ventas del Día</h3>
        <div className="flex items-center gap-2">
          <input aria-label="Día" type="date" className="input !w-auto !bg-card" value={dia} max={todayIso()} onChange={e => e.target.value && setDia(e.target.value)} />
          <button className="btn-primary shadow-md" onClick={descargar} disabled={pdf || t.ventas === 0}>
            <Download size={14} /> {pdf ? 'Generando...' : 'Descargar historial PDF'}
          </button>
        </div>
      </div>
      <div className="card overflow-hidden !rounded-[14px]">
        <div className="grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3.5 p-4">
          <StatBox label="Ventas completadas" value={t.ventas} color="#10b981" />
          <StatBox label="Artículos vendidos" value={t.articulos} color="#4f46e5" />
          <StatBox label="Total facturado" value={usd(t.usd)} color="#06b6d4" />
        </div>
        <QueryState query={ventas}>
          {data => data.length === 0 ? <EmptyState title="No hay ventas registradas ese día." /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[820px] border-collapse text-[13px]">
                <thead>
                  <tr className="border-t border-border bg-muted">
                    {['Factura', 'Hora', 'Productos', 'Pago', 'Total USD', 'Cajero', 'Estado', ''].map(h => <th key={h} className="th">{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {data.map(v => (
                    <tr key={v.id_venta} className={`border-t border-border ${v.estado === 'Anulada' ? 'opacity-60' : ''}`}>
                      <td className="td font-bold text-primary">{v.numero_factura}</td>
                      <td className="td text-muted-foreground">{fmtHora(v.fecha_venta)}</td>
                      <td className="td">
                        {v.detalles.map(d => <div key={d.id_detalle}><b>{d.cantidad}×</b> {d.nombre_producto_snapshot} <span className="text-muted-foreground">({usd(d.precio_unitario_usd)})</span></div>)}
                      </td>
                      <td className="td whitespace-nowrap text-muted-foreground">
                        {fmtMoneda(v.monto_total_moneda, v.codigo_moneda_pago)}
                        {v.referencia_pago && <div className="text-[11px]">Ref. {v.referencia_pago}</div>}
                      </td>
                      <td className="td font-bold text-success">{usd(v.monto_total_usd)}</td>
                      <td className="td text-[#6366f1]">{v.nombre_usuario}</td>
                      <td className="td"><Badge>{v.estado}</Badge></td>
                      <td className="td">
                        {v.estado !== 'Anulada' && (
                          <button className="btn-muted !px-2.5 !py-1 text-[11px] text-danger" onClick={() => setAnular(v)}><Ban size={12} /> Anular</button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </QueryState>
      </div>
      {anular && (
        <ConfirmDialog danger title={`Anular venta ${anular.numero_factura}`} confirmText="Anular venta" busy={anulacion.isPending}
          message={<>Se marcará como <b>Anulada</b> ({usd(anular.monto_total_usd)}) y las unidades vuelven al inventario. Esta acción no se puede deshacer.
            {anulacion.error && <div className="mt-3"><ErrorBanner error={anulacion.error} /></div>}</>}
          onConfirm={() => anulacion.mutate(anular)} onClose={() => { setAnular(null); anulacion.reset() }} />
      )}
    </div>
  )
}
