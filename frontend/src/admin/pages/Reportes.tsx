import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { comprasApi, productosApi, reportesApi } from '@/api/endpoints'
import { keys } from '@/api/queries'
import type { TopProducto } from '@/api/types'
import { AreaSerie, Donut, PALETTE } from '@/shared/components/charts'
import RespaldoVentas from '@/shared/components/RespaldoVentas'
import { Accordion, EmptyState, QueryState, StatBox, Tabs } from '@/shared/components/ui'
import { parseLocal, rangoPeriodo, type Periodo } from '@/shared/lib/dates'
import { num, usd } from '@/shared/lib/money'
import Facturas from '../components/Facturas'
import HistorialVentasDia from '../components/HistorialVentasDia'

const PERIODOS = ['Hoy', 'Esta Semana', 'Este Mes'] as const

function etiquetaPunto(etiqueta: string, periodo: Periodo) {
  if (periodo === 'Hoy') return `${Number(etiqueta)}h`
  const d = parseLocal(etiqueta)
  return periodo === 'Esta Semana' ? d.toLocaleDateString('es-VE', { weekday: 'short' }) : String(d.getDate())
}

/** Serie de ventas del período: unidades o monto en USD. */
function SerieVentas({ periodo, medida, color, id }: { periodo: Periodo; medida: 'unidades' | 'usd'; color: string; id: string }) {
  const rango = rangoPeriodo(periodo)
  const agrupar = periodo === 'Hoy' ? 'hora' : 'dia'
  const serie = useQuery({ queryKey: [...keys.reportes, 'serie', rango, agrupar], queryFn: () => reportesApi.serieVentas({ ...rango, agrupar }) })
  return (
    <QueryState query={serie}>
      {data => {
        const puntos = (agrupar === 'hora' ? data.filter(p => Number(p.etiqueta) >= 7 && Number(p.etiqueta) <= 20) : data)
          .map(p => ({ label: etiquetaPunto(p.etiqueta, periodo), value: medida === 'usd' ? num(p.monto_total_usd) : p.articulos_vendidos }))
        return <AreaSerie data={puntos} color={color} id={id} unit={medida === 'usd' ? ' USD' : ' uds.'} />
      }}
    </QueryState>
  )
}

function TopTabla({ rows }: { rows: TopProducto[] }) {
  if (rows.length === 0) return <EmptyState title="Sin ventas en el período." />
  const max = Math.max(...rows.map(r => r.unidades), 1)
  return (
    <table className="mt-3 w-full border-collapse text-xs">
      <thead><tr className="border-b border-border">{['#', 'Producto', 'Categoría', 'Unidades vendidas', 'Total'].map(h => <th key={h} className="th !px-2.5 !py-1.5">{h}</th>)}</tr></thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={r.id_producto} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
            <td className="px-2.5 py-2 font-bold text-primary">{i + 1}.</td>
            <td className="px-2.5 py-2 font-medium">{r.nombre_producto}</td>
            <td className="px-2.5 py-2 text-muted-foreground">{r.nombre_categoria ?? '—'}</td>
            <td className="px-2.5 py-2">
              <div className="flex items-center gap-2">
                <div className="h-1.5 flex-1 overflow-hidden rounded bg-muted"><div className="h-full rounded bg-primary" style={{ width: `${(r.unidades / max) * 100}%` }} /></div>
                <span className="min-w-7 font-bold">{r.unidades}</span>
              </div>
            </td>
            <td className="px-2.5 py-2 font-semibold text-success">{usd(r.monto_total_usd)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function TopProductos({ periodo, limite }: { periodo: Periodo; limite: number }) {
  const rango = rangoPeriodo(periodo)
  const top = useQuery({ queryKey: [...keys.reportes, 'top', rango, limite], queryFn: () => reportesApi.topProductos({ ...rango, limite }) })
  return <QueryState query={top}>{rows => <TopTabla rows={rows} />}</QueryState>
}

export default function Reportes() {
  const [periodoStock, setPeriodoStock] = React.useState<Periodo>('Este Mes')
  const [periodoVentas, setPeriodoVentas] = React.useState<Periodo>('Este Mes')
  const mes = rangoPeriodo('Este Mes')
  const dash = useQuery({ queryKey: [...keys.reportes, 'dashboard'], queryFn: reportesApi.dashboard })
  const mov = useQuery({ queryKey: [...keys.reportes, 'movimientos', mes], queryFn: () => reportesApi.movimientosStock(mes) })
  const entradas = useQuery({ queryKey: [...keys.compras, 'entradas'], queryFn: () => comprasApi.entradasRecientes(10) })
  const critico = useQuery({ queryKey: [...keys.productos, 'stock-bajo'], queryFn: productosApi.stockBajo })
  const porCategoria = useQuery({ queryKey: [...keys.reportes, 'ventas-cat', mes], queryFn: () => reportesApi.ventasPorCategoria(mes) })

  return (
    <div className="flex flex-col gap-6 pb-6">
      <section>
        <h2 className="m-0 mb-3.5 text-lg font-bold">Reportes de Productos y Stock</h2>
        <div className="flex flex-col gap-2.5">
          <Accordion title="Métricas clave de stock" defaultOpen>
            <div className="mt-4 grid grid-cols-1 gap-5 lg:grid-cols-[1fr_1.4fr]">
              <div className="flex flex-col gap-3">
                <StatBox label="Stock disponible total" value={dash.data ? dash.data.unidades_en_stock.toLocaleString('es-VE') : '…'} />
                <StatBox label="Productos en stock crítico" value={dash.data ? dash.data.productos_bajo_stock + dash.data.productos_agotados : '…'} color="#f43f5e" />
                <StatBox label="Ingresos de stock este mes" value={mov.data ? `${mov.data.entradas} uds.` : '…'} color="var(--primary)" />
              </div>
              <div className="rounded-xl border border-border bg-muted p-4">
                <div className="mb-2 text-xs font-semibold text-muted-foreground">Ingreso de stock (mes actual)</div>
                <QueryState query={mov}>
                  {m => <Donut size={130} data={m.ingresos_por_producto.map(i => ({ name: i.nombre_producto, value: i.unidades }))} format={v => `${v} uds.`} />}
                </QueryState>
              </div>
            </div>
          </Accordion>

          <Accordion title="Productos más vendidos">
            <Tabs className="mt-3.5" value={periodoStock} options={PERIODOS} onChange={setPeriodoStock} />
            <div className="mt-2.5 text-[13px] font-semibold">{periodoStock} — unidades vendidas</div>
            <SerieVentas periodo={periodoStock} medida="unidades" color="#4f46e5" id="grad-stock" />
            <div className="mt-3.5 font-display text-[13px] font-bold">Top 10 · {periodoStock.toLowerCase()}</div>
            <TopProductos periodo={periodoStock} limite={10} />
          </Accordion>

          <Accordion title="Registro de stock del mes">
            <div className="mt-3.5 text-[13px] text-muted-foreground">Unidades que entraron por compras y salieron por ventas durante el mes actual.</div>
            <QueryState query={mov}>
              {m => (
                <div className="mt-3.5 grid grid-cols-3 gap-3 text-center">
                  <StatBox label="Entradas" value={m.entradas} color="#10b981" />
                  <StatBox label="Salidas" value={m.salidas} color="#f43f5e" />
                  <StatBox label="Neto" value={`${m.neto > 0 ? '+' : ''}${m.neto}`} color="#4f46e5" />
                </div>
              )}
            </QueryState>
          </Accordion>

          <Accordion title="Registro de ingreso de stock reciente">
            <QueryState query={entradas}>
              {rows => rows.length === 0 ? <EmptyState title="Aún no hay compras registradas." hint="Regístrelas en Proveedores → Registrar compra." /> : (
                <div className="mt-3.5 overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]">
                    <thead><tr className="border-b-2 border-border bg-muted">{['Fecha', 'Artículo', 'Cantidad', 'Proveedor'].map(h => <th key={h} className="th !py-2.5">{h}</th>)}</tr></thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={`${r.id_compra}-${r.id_producto}-${i}`} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                          <td className="td !py-2.5 whitespace-nowrap text-muted-foreground">{parseLocal(r.fecha).toLocaleDateString('es-VE')}</td>
                          <td className="td !py-2.5 font-medium">{r.nombre_producto}</td>
                          <td className="td !py-2.5 font-bold text-primary">{r.cantidad}</td>
                          <td className="td !py-2.5 text-muted-foreground">{r.nombre_proveedor}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </QueryState>
          </Accordion>

          <Accordion title="Detalle de stock disponible crítico">
            <QueryState query={critico}>
              {rows => rows.length === 0 ? <EmptyState title="Ningún producto está por debajo de su stock mínimo." /> : (
                <div className="mt-3.5 overflow-x-auto">
                  <table className="w-full border-collapse text-[13px]">
                    <thead><tr className="border-b-2 border-border bg-muted">{['Artículo', 'Cantidad actual', 'Cantidad mínima', 'Ubicación'].map(h => <th key={h} className="th !py-2.5">{h}</th>)}</tr></thead>
                    <tbody>
                      {rows.map((r, i) => (
                        <tr key={r.id_producto} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                          <td className="td !py-2.5 font-medium">{r.nombre} <span className="text-[11px] text-muted-foreground">{r.sku}</span></td>
                          <td className="td !py-2.5"><span className="rounded-md bg-danger/10 px-2.5 py-0.5 font-bold text-danger">{r.stock_actual}</span></td>
                          <td className="td !py-2.5 font-semibold">{r.stock_minimo}</td>
                          <td className="td !py-2.5 text-muted-foreground">{r.ubicacion ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </QueryState>
          </Accordion>
        </div>
      </section>

      <section>
        <h2 className="m-0 mb-3.5 text-lg font-bold">Reportes de Administración</h2>
        <div className="flex flex-col gap-2.5">
          <Accordion title="Ventas por período" defaultOpen>
            <Tabs className="mt-3.5" value={periodoVentas} options={PERIODOS} onChange={setPeriodoVentas} />
            <div className="mt-2.5 text-[13px] font-semibold">{periodoVentas} — monto vendido (USD)</div>
            <SerieVentas periodo={periodoVentas} medida="usd" color="#06b6d4" id="grad-ventas" />
            <div className="mt-3.5 font-display text-[13px] font-bold">Top 3 · {periodoVentas.toLowerCase()}</div>
            <TopProductos periodo={periodoVentas} limite={3} />
          </Accordion>

          <HistorialVentasDia />
          <RespaldoVentas />

          <Accordion title="Resumen de ventas por categoría · este mes">
            <QueryState query={porCategoria}>
              {rows => rows.length === 0 ? <EmptyState title="Sin ventas este mes." /> : (
                <div className="mt-3.5 grid grid-cols-[repeat(auto-fit,minmax(180px,1fr))] gap-3">
                  {rows.map((k, i) => (
                    <div key={k.nombre_categoria} className="stat !p-4">
                      <div className="mb-2 h-2.5 w-2.5 rounded-full" style={{ background: PALETTE[i % PALETTE.length] }} />
                      <div className="mb-1 font-display text-sm font-bold">{k.nombre_categoria}</div>
                      <div className="font-display text-xl font-extrabold" style={{ color: PALETTE[i % PALETTE.length] }}>{k.unidades} uds.</div>
                      <div className="mt-1 text-xs text-muted-foreground">{usd(k.monto_total_usd)}</div>
                    </div>
                  ))}
                </div>
              )}
            </QueryState>
          </Accordion>
        </div>
      </section>

      <Facturas />
    </div>
  )
}
