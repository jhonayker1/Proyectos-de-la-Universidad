/** Inicio del gestor: accesos directos, resumen del día y alertas de stock (sin datos financieros). */
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AlertTriangle, ClipboardList, PackagePlus, SlidersHorizontal, Truck, Wallet } from 'lucide-react'
import { comprasApi, reportesApi } from '@/api/endpoints'
import { keys } from '@/api/queries'
import { Badge, EmptyState, KpiCard, QueryState, cx } from '@/shared/components/ui'
import { fmtFecha, parseLocal } from '@/shared/lib/dates'
import { usd } from '@/shared/lib/money'

const ACCESOS = [
  { to: '/gestor/entradas?nueva=1', label: 'Registrar entrada', icon: PackagePlus, color: 'bg-success/15 text-success' },
  { to: '/gestor/inventario', label: 'Ajustar stock', icon: SlidersHorizontal, color: 'bg-accent/15 text-accent' },
  { to: '/gestor/proveedores', label: 'Proveedores', icon: Truck, color: 'bg-primary/10 text-primary' },
  { to: '/gestor/reportes', label: 'Reportes', icon: ClipboardList, color: 'bg-warning/15 text-warning' },
]

export default function Dashboard() {
  const resumen = useQuery({ queryKey: [...keys.reportes, 'gestor', 'resumen'], queryFn: reportesApi.resumenGestor, refetchInterval: 60_000 })
  const entradas = useQuery({ queryKey: [...keys.compras, 'entradas-recientes'], queryFn: () => comprasApi.entradasRecientes(8) })

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {ACCESOS.map(({ to, label, icon: Icon, color }) => (
          <Link key={to} to={to} className="card flex items-center gap-3 px-4 py-3.5 text-foreground no-underline transition-shadow hover:shadow-md">
            <span className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', color)}><Icon size={18} /></span>
            <span className="font-display text-sm font-bold">{label}</span>
          </Link>
        ))}
      </div>

      <QueryState query={resumen} label="Cargando actividad del día...">
        {r => (
          <>
            <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
              <KpiCard label="Ventas de hoy" value={String(r.ventas_hoy)} color="#10b981"
                sub={`${r.articulos_hoy} artículos · ${usd(r.monto_hoy_usd)}`} />
              <KpiCard label="Entradas de hoy" value={`${r.unidades_entrada_hoy} uds.`} color="#06b6d4"
                sub={`${r.compras_hoy} compra(s) a proveedores`} />
              <KpiCard label="Ajustes de stock hoy" value={String(r.ajustes_hoy)} color="#4f46e5"
                sub="Con motivo y observación" />
              <KpiCard label="Stock crítico" value={String(r.productos_agotados + r.productos_bajo_stock)} color="#f59e0b"
                up={r.productos_agotados + r.productos_bajo_stock === 0}
                sub={`${r.productos_agotados} agotados · ${r.productos_bajo_stock} bajos`} />
            </div>

            <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1.2fr_1fr]">
              <div className="card overflow-hidden">
                <div className="flex items-center justify-between border-b border-border px-4 py-3">
                  <h2 className="m-0 flex items-center gap-2 text-sm font-bold"><AlertTriangle size={16} className="text-warning" /> Alertas de stock</h2>
                  <Link to="/gestor/inventario" className="text-xs font-semibold text-primary">Ver inventario →</Link>
                </div>
                {r.stock_critico.length === 0 ? <EmptyState title="Todo el inventario está sobre su mínimo." /> : (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse text-[13px]">
                      <thead><tr className="bg-muted">{['SKU', 'Producto', 'Stock', 'Mínimo', 'Estado'].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
                      <tbody>
                        {r.stock_critico.map(p => (
                          <tr key={p.id_producto} className="border-t border-border">
                            <td className="td !py-2 text-xs text-muted-foreground">{p.sku}</td>
                            <td className="td !py-2 font-semibold">{p.nombre}</td>
                            <td className={cx('td !py-2 font-bold', p.stock_actual === 0 ? 'text-danger' : 'text-warning')}>{p.stock_actual}</td>
                            <td className="td !py-2 text-muted-foreground">{p.stock_minimo}</td>
                            <td className="td !py-2"><Badge>{p.estado}</Badge></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              <div className="flex flex-col gap-4">
                <div className="card overflow-hidden">
                  <div className="flex items-center justify-between border-b border-border px-4 py-3">
                    <h2 className="m-0 flex items-center gap-2 text-sm font-bold"><PackagePlus size={16} className="text-success" /> Últimas entradas de mercancía</h2>
                    <Link to="/gestor/entradas" className="text-xs font-semibold text-primary">Entradas →</Link>
                  </div>
                  <QueryState query={entradas}>
                    {lista => lista.length === 0 ? <EmptyState title="Aún no hay entradas registradas." /> : (
                      <div className="divide-y divide-border">
                        {lista.map((e, i) => (
                          <div key={`${e.id_compra}-${e.id_producto}-${i}`} className="flex items-center gap-3 px-4 py-2.5 text-[13px]">
                            <span className="font-bold text-success">+{e.cantidad}</span>
                            <span className="min-w-0 flex-1 truncate">{e.nombre_producto}</span>
                            <span className="truncate text-xs text-muted-foreground">{e.nombre_proveedor}</span>
                            <span className="w-24 text-right text-[11px] text-muted-foreground">{fmtFecha(parseLocal(e.fecha))}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </QueryState>
                </div>
                <Link to="/gestor/reportes?tab=pagar" className="card flex items-center gap-3 px-4 py-3.5 text-foreground no-underline hover:shadow-md">
                  <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-danger/10 text-danger"><Wallet size={18} /></span>
                  <span className="flex-1">
                    <span className="block text-xs text-muted-foreground">Cuentas por pagar a proveedores</span>
                    <span className="font-display text-lg font-extrabold">{usd(r.cuentas_por_pagar_usd)}</span>
                  </span>
                  <span className="text-xs text-muted-foreground">{r.cuentas_por_pagar_cantidad} compra(s)</span>
                </Link>
              </div>
            </div>
          </>
        )}
      </QueryState>
    </div>
  )
}
