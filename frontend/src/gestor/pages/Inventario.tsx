import React from 'react'
import { Search, SlidersHorizontal } from 'lucide-react'
import AjusteStockModal from '@/admin/components/AjusteStockModal'
import { useProductos } from '@/api/queries'
import type { Producto } from '@/api/types'
import { Badge, EmptyState, ErrorBanner, Spinner } from '@/shared/components/ui'

export default function Inventario() {
  const productos = useProductos()
  const [buscar, setBuscar] = React.useState('')
  const [seleccionado, setSeleccionado] = React.useState<Producto | null>(null)
  const filtrados = (productos.data ?? []).filter(p =>
    `${p.sku} ${p.nombre} ${p.nombre_categoria ?? ''}`.toLowerCase().includes(buscar.trim().toLowerCase()),
  )

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="card flex flex-wrap items-center gap-3 p-4">
        <div className="relative min-w-0 flex-[1_1_15rem]">
          <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
          <input className="input !pl-9" value={buscar} onChange={e => setBuscar(e.target.value)}
            placeholder="Buscar por SKU, producto o categoría" />
        </div>
        <span className="text-xs text-muted-foreground">{filtrados.length} productos</span>
      </div>
      <div className="card min-h-0 flex-1 overflow-auto">
        {productos.isLoading ? <Spinner label="Cargando inventario..." /> : productos.error ? (
          <div className="p-4"><ErrorBanner error={productos.error} onRetry={() => productos.refetch()} /></div>
        ) : filtrados.length === 0 ? <EmptyState title="No se encontraron productos." /> : (
          <table className="w-full border-collapse text-[13px]">
            <thead className="sticky top-0">
              <tr className="border-b-2 border-border bg-muted">
                {['SKU', 'Producto', 'Categoría', 'Stock', 'Mínimo', 'Estado', ''].map(h =>
                  <th key={h} className="th">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {filtrados.map((p, i) => (
                <tr key={p.id_producto} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                  <td className="td font-mono text-xs text-muted-foreground">{p.sku}</td>
                  <td className="td font-semibold">{p.nombre}</td>
                  <td className="td text-muted-foreground">{p.nombre_categoria ?? '—'}</td>
                  <td className="td font-bold">{p.stock_actual}</td>
                  <td className="td text-muted-foreground">{p.stock_minimo}</td>
                  <td className="td"><Badge>{p.estado}</Badge></td>
                  <td className="td">
                    <button className="btn-muted !px-3 !py-1.5 text-xs" onClick={() => setSeleccionado(p)}>
                      <SlidersHorizontal size={13} /> Ajustar
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {seleccionado && <AjusteStockModal producto={seleccionado} onClose={() => setSeleccionado(null)} />}
    </div>
  )
}
