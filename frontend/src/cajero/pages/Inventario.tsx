/** Inventario del cajero: solo lectura, con acción "agregar al ticket" (sin edición). */
import React from 'react'
import { useNavigate } from 'react-router-dom'
import { ShoppingCart } from 'lucide-react'
import { useProductos } from '@/api/queries'
import { CurrencySelect, FiltrosBar, StockCell, emojiCategoria, useFiltrosProductos, useTasas, type MonedaVista } from '@/shared/components/productos'
import { Badge, EmptyState, ErrorBanner, Pagination, Spinner, cx, useToast } from '@/shared/components/ui'
import { useCart } from '../CartContext'

export default function Inventario() {
  const toast = useToast()
  const navigate = useNavigate()
  const cart = useCart()
  const productos = useProductos()
  const { convertir } = useTasas()
  const [moneda, setMoneda] = React.useState<MonedaVista>('USD')
  const f = useFiltrosProductos(productos.data)

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <FiltrosBar filtros={f.filtros} setFiltros={f.setFiltros} limpiar={f.limpiar} />
      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-x-auto">
          {productos.isLoading ? <Spinner label="Cargando productos..." /> : productos.error ? <div className="p-4"><ErrorBanner error={productos.error} onRetry={() => productos.refetch()} /></div> : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-border bg-muted">
                  <th className="th" aria-label="Agregar" />
                  {['SKU', 'Producto', 'Categoría', 'Marca', 'Stock'].map(h => <th key={h} className="th">{h}</th>)}
                  <th className="th !py-2"><div className="flex flex-col gap-1">Precio en<CurrencySelect value={moneda} onChange={setMoneda} /></div></th>
                  <th className="th">Estado</th>
                </tr>
              </thead>
              <tbody>
                {f.paginados.map((p, i) => {
                  const enTicket = cart.cantidadDe(p.id_producto)
                  const sinStock = enTicket >= p.stock_actual
                  return (
                    <tr key={p.id_producto} className={`border-b border-border hover:bg-[#f0f0ff] ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                      <td className="td">
                        <button aria-label={`Agregar ${p.nombre} al ticket`} title={sinStock ? 'Sin stock disponible' : 'Añadir al pedido'} disabled={sinStock}
                          onClick={() => { if (!cart.agregar(p)) toast(`No hay más stock de ${p.nombre}.`, 'error') }}
                          className={cx('flex h-[26px] w-[26px] cursor-pointer items-center justify-center rounded-md border border-primary text-base leading-none font-bold disabled:cursor-not-allowed disabled:opacity-35',
                            enTicket ? 'bg-primary text-white' : 'bg-transparent text-primary')}>
                          {enTicket || '+'}
                        </button>
                      </td>
                      <td className="td font-medium whitespace-nowrap text-muted-foreground">{p.sku}</td>
                      <td className="td">
                        <div className="flex items-center gap-2.5">
                          <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg bg-muted text-lg">{emojiCategoria(p.nombre_categoria)}</div>
                          <span className="font-semibold">{p.nombre}</span>
                        </div>
                      </td>
                      <td className="td text-muted-foreground">{p.nombre_categoria}</td>
                      <td className="td text-muted-foreground">{p.nombre_marca ?? '—'}</td>
                      <td className="td"><StockCell p={p} /></td>
                      <td className="td font-bold whitespace-nowrap text-primary">{convertir(p.precio_usd, moneda)}</td>
                      <td className="td"><Badge>{p.estado}</Badge></td>
                    </tr>
                  )
                })}
                {f.paginados.length === 0 && <tr><td colSpan={8}><EmptyState title="No se encontraron productos." /></td></tr>}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-t border-border px-5 py-3.5">
          <Pagination page={f.pagina} total={f.totalPaginas} onChange={f.setPagina} />
          <button className="btn-primary ml-auto !px-5 shadow-md" disabled={cart.unidades === 0} onClick={() => navigate('/cajero')}>
            <ShoppingCart size={14} /> Continuar pedido {cart.unidades > 0 && `(${cart.unidades})`}
          </button>
        </div>
      </div>
    </div>
  )
}
