import { useQuery } from '@tanstack/react-query'
import { reportesApi } from '@/api/endpoints'
import { keys } from '@/api/queries'
import { rangoPeriodo } from '@/shared/lib/dates'
import { num, usd } from '@/shared/lib/money'
import { Donut } from '@/shared/components/charts'
import { KpiCard, QueryState } from '@/shared/components/ui'

export default function Dashboard() {
  const mes = rangoPeriodo('Este Mes')
  const dash = useQuery({ queryKey: [...keys.reportes, 'dashboard'], queryFn: reportesApi.dashboard })
  const top = useQuery({ queryKey: [...keys.reportes, 'top', mes], queryFn: () => reportesApi.topProductos({ ...mes, limite: 7 }) })
  const stock = useQuery({ queryKey: [...keys.reportes, 'stock-cat'], queryFn: reportesApi.stockPorCategoria })

  return (
    <div className="flex flex-col gap-4">
      <QueryState query={dash} label="Cargando indicadores...">
        {d => {
          const mesActual = num(d.ventas_mes_usd)
          const mesAnterior = num(d.ventas_mes_anterior_usd)
          const variacion = mesAnterior > 0 ? ((mesActual - mesAnterior) / mesAnterior) * 100 : null
          return (
            <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-4">
              <KpiCard label="Ventas del mes" value={usd(d.ventas_mes_usd)} color="#4f46e5"
                up={variacion === null ? undefined : variacion >= 0}
                sub={variacion === null ? `Mes anterior: ${usd(d.ventas_mes_anterior_usd)}` : `${variacion >= 0 ? '+' : ''}${variacion.toFixed(0)}% vs mes anterior`} />
              <KpiCard label="Inventario" value={d.unidades_en_stock.toLocaleString('es-VE')} color="#06b6d4"
                up={d.productos_bajo_stock + d.productos_agotados === 0}
                sub={`${d.productos_bajo_stock} bajos · ${d.productos_agotados} agotados`} />
              <KpiCard label="Ventas hoy" value={usd(d.ventas_hoy_usd)} color="#10b981"
                sub={`${d.ventas_hoy_cantidad} ventas · ${d.articulos_hoy} artículos`} />
              <KpiCard label="Valor del inventario (costo)" value={usd(d.valor_inventario_usd)} color="#f59e0b"
                sub={`${d.productos_activos} productos activos`} />
            </div>
          )
        }}
      </QueryState>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <div className="card overflow-hidden">
          <div className="border-b border-border px-4 pt-4 pb-3">
            <h2 className="m-0 text-sm font-bold">Productos más vendidos · este mes</h2>
          </div>
          <div className="p-4">
            <QueryState query={top}>
              {rows => <Donut data={rows.map(r => ({ name: r.nombre_producto, value: r.unidades }))} format={v => `${v} uds.`} />}
            </QueryState>
          </div>
        </div>
        <div className="card overflow-hidden">
          <div className="border-b border-border px-4 pt-4 pb-3">
            <h2 className="m-0 text-sm font-bold">Unidades en stock por categoría</h2>
          </div>
          <div className="p-4">
            <QueryState query={stock}>
              {rows => <Donut data={rows.map(r => ({ name: r.nombre_categoria, value: r.unidades }))} format={v => `${v} uds.`} />}
            </QueryState>
          </div>
        </div>
      </div>
    </div>
  )
}
