import React from 'react'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { productosApi } from '@/api/endpoints'
import { keys, useApiMutation, useCategorias, useMarcas, useProductosAdmin, useProveedores } from '@/api/queries'
import type { ProductoAdmin, ProductoInput } from '@/api/types'
import { CurrencySelect, FiltrosBar, StockCell, emojiCategoria, useFiltrosProductos, useTasas, type MonedaVista } from '@/shared/components/productos'
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, Field, Modal, Pagination, Spinner, errorText, useToast } from '@/shared/components/ui'
import { num, parseDecimal, precioConMargen, usd } from '@/shared/lib/money'

type Form = {
  sku: string; nombre: string; id_categoria: string; id_marca: string; id_proveedor: string
  stock_actual: string; stock_minimo: string; ubicacion: string
  precio_distribuidor: string; margen: string; precio_manual: string
}

function ProductoModal({ producto, onClose }: { producto: ProductoAdmin | null; onClose: () => void }) {
  const toast = useToast()
  const categorias = useCategorias()
  const marcas = useMarcas()
  const proveedores = useProveedores()
  const [form, setForm] = React.useState<Form>(() => ({
    sku: producto?.sku ?? '', nombre: producto?.nombre ?? '',
    id_categoria: String(producto?.id_categoria ?? ''), id_marca: String(producto?.id_marca ?? ''),
    id_proveedor: String(producto?.id_proveedor ?? ''),
    stock_actual: String(producto?.stock_actual ?? 0), stock_minimo: String(producto?.stock_minimo ?? 5),
    ubicacion: producto?.ubicacion ?? '',
    precio_distribuidor: producto ? String(num(producto.precio_distribuidor)) : '',
    margen: producto?.margen_pct != null ? String(num(producto.margen_pct)) : '',
    precio_manual: producto ? String(num(producto.precio_usd)) : '',
  }))
  const set = (k: keyof Form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => setForm(f => ({ ...f, [k]: e.target.value }))

  // Al crear, la primera categoría es la predeterminada.
  const idCategoria = form.id_categoria || String(categorias.data?.[0]?.id_categoria ?? '')
  const categoria = categorias.data?.find(c => String(c.id_categoria) === idCategoria)
  const margenCat = num(categoria?.margen_ganancia)
  const margenPropio = form.margen.trim() === '' ? null : parseDecimal(form.margen)
  const margen = margenPropio ?? margenCat
  const costo = parseDecimal(form.precio_distribuidor || '0')
  const manual = margen === 0 // 0% = precio de venta manual (no se calcula)
  const precioVenta = manual ? parseDecimal(form.precio_manual || '0') : precioConMargen(costo, margen)

  const errores = [
    !form.sku.trim() && 'SKU',
    !form.nombre.trim() && 'nombre',
    !idCategoria && 'categoría',
    !(costo >= 0) && 'precio distribuidor',
    margenPropio !== null && !(margenPropio >= 0 && margenPropio <= 999.99) && 'porcentaje de ganancia',
    !(precioVenta >= 0) && 'precio de venta',
    !(Number.isInteger(Number(form.stock_actual)) && Number(form.stock_actual) >= 0) && 'stock',
    !(Number.isInteger(Number(form.stock_minimo)) && Number(form.stock_minimo) >= 0) && 'stock mínimo',
  ].filter(Boolean)

  const guardar = useApiMutation(async () => {
    const data: ProductoInput = {
      sku: form.sku.trim(), nombre: form.nombre.trim(), id_categoria: Number(idCategoria),
      id_marca: form.id_marca ? Number(form.id_marca) : null,
      id_proveedor: form.id_proveedor ? Number(form.id_proveedor) : null,
      precio_distribuidor: costo.toFixed(2),
      margen_pct: margenPropio === null ? null : String(margenPropio),
      // Con margen > 0 el backend calcula el precio; con 0% se envía el precio manual.
      ...(manual ? { precio_usd: precioVenta.toFixed(2) } : {}),
      ubicacion: form.ubicacion.trim() || null,
      stock_actual: Number(form.stock_actual), stock_minimo: Number(form.stock_minimo),
    }
    return producto ? productosApi.update(producto.id_producto, data) : productosApi.create(data)
  }, [keys.productos, keys.reportes], p => { toast(`${p.nombre} guardado (${usd(p.precio_usd)}).`); onClose() })

  return (
    <Modal title={producto ? 'Editar producto' : 'Nuevo producto'} width="max-w-xl" onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={errores.length > 0 || guardar.isPending} onClick={() => guardar.mutate(undefined)}
        title={errores.length ? `Revise: ${errores.join(', ')}` : undefined}>
        {guardar.isPending ? 'Guardando...' : 'Guardar'}
      </button>
    </>}>
      <div className="grid grid-cols-2 gap-3.5">
        <Field label="SKU"><input className="input" value={form.sku} onChange={set('sku')} placeholder="CR-0001" autoFocus /></Field>
        <Field label="Categoría">
          <select className="input" value={idCategoria} onChange={set('id_categoria')}>
            {categorias.data?.map(c => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre}</option>)}
          </select>
        </Field>
        <Field label="Nombre" className="col-span-2"><input className="input" value={form.nombre} onChange={set('nombre')} /></Field>
        <Field label="Marca">
          <select className="input" value={form.id_marca} onChange={set('id_marca')}>
            <option value="">Sin marca</option>
            {marcas.data?.map(m => <option key={m.id_marca} value={m.id_marca}>{m.nombre}</option>)}
          </select>
        </Field>
        <Field label="Proveedor">
          <select className="input" value={form.id_proveedor} onChange={set('id_proveedor')}>
            <option value="">Sin proveedor</option>
            {proveedores.data?.map(p => <option key={p.id_proveedor} value={p.id_proveedor}>{p.nombre}</option>)}
          </select>
        </Field>
        <Field label="Stock"><input className="input" type="number" min={0} value={form.stock_actual} onChange={set('stock_actual')} /></Field>
        <Field label="Stock mínimo"><input className="input" type="number" min={0} value={form.stock_minimo} onChange={set('stock_minimo')} /></Field>
        <Field label="Precio distribuidor USD"><input className="input" inputMode="decimal" value={form.precio_distribuidor} onChange={set('precio_distribuidor')} placeholder="0.00" /></Field>
        <Field label="Ubicación"><input className="input" value={form.ubicacion} onChange={set('ubicacion')} placeholder="Estante A" /></Field>

        <div className="col-span-2 rounded-xl border border-border bg-muted p-3">
          <span className="label mb-1.5">Porcentaje de ganancia (%)</span>
          <div className="flex flex-wrap items-center gap-2.5">
            <input aria-label="Porcentaje de ganancia" className="input !w-24 !bg-card" inputMode="decimal" value={form.margen} placeholder={String(margenCat)} onChange={set('margen')} />
            <button type="button" className="btn-muted !bg-card !px-2.5 !py-1.5 text-xs" onClick={() => setForm(f => ({ ...f, margen: '' }))}>
              Usar % de {categoria?.nombre ?? 'la categoría'}
            </button>
            {manual ? (
              <label className="ml-auto flex items-center gap-2 text-xs text-muted-foreground">
                Venta USD:
                <input aria-label="Precio de venta manual" className="input !w-28 !bg-card font-display font-bold !text-primary" inputMode="decimal" value={form.precio_manual} onChange={set('precio_manual')} />
              </label>
            ) : (
              <span className="ml-auto text-xs text-muted-foreground">
                Venta: <b className="font-display text-sm text-primary">{usd(precioVenta)}</b>
              </span>
            )}
          </div>
          <div className={`mt-1.5 text-[11px] ${margen >= 100 ? 'text-red-600' : 'text-muted-foreground'}`}>
            {margen >= 100
              ? 'Advertencia: el porcentaje ingresado representa una cantidad desproporcionada.'
              : manual
                ? 'Margen 0%: el precio de venta se escribe a mano.'
                : `Déjalo vacío para usar el porcentaje de la categoría (${margenCat}%).`}
          </div>
        </div>
        {guardar.error && <div className="col-span-2"><ErrorBanner error={guardar.error} /></div>}
      </div>
    </Modal>
  )
}

export default function Inventario() {
  const toast = useToast()
  const productos = useProductosAdmin()
  const { convertir } = useTasas()
  const [moneda, setMoneda] = React.useState<MonedaVista>('USD')
  const f = useFiltrosProductos(productos.data)
  const [modal, setModal] = React.useState<{ producto: ProductoAdmin | null } | null>(null)
  const [baja, setBaja] = React.useState<ProductoAdmin | null>(null)
  const darBaja = useApiMutation((p: ProductoAdmin) => productosApi.remove(p.id_producto), [keys.productos, keys.reportes], () => {
    toast('Producto dado de baja.'); setBaja(null)
  })
  const reactivar = useApiMutation((p: ProductoAdmin) => productosApi.update(p.id_producto, { estado: 'Disponible' }),
    [keys.productos], p => toast(`${p.nombre} reactivado.`))

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <FiltrosBar filtros={f.filtros} setFiltros={f.setFiltros} limpiar={f.limpiar}>
        <button className="btn-primary" onClick={() => setModal({ producto: null })}><Plus size={14} /> Nuevo producto</button>
      </FiltrosBar>

      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-x-auto">
          {productos.isLoading ? <Spinner label="Cargando inventario..." /> : productos.error ? <div className="p-4"><ErrorBanner error={productos.error} onRetry={() => productos.refetch()} /></div> : (
            <table className="w-full border-collapse text-[13px]">
              <thead>
                <tr className="border-b-2 border-border bg-muted">
                  {['SKU', 'Producto', 'Categoría', 'Marca', 'Stock', 'Precio distribuidor'].map(h => <th key={h} className="th">{h}</th>)}
                  <th className="th !py-2"><div className="flex flex-col gap-1">Precio en<CurrencySelect value={moneda} onChange={setMoneda} /></div></th>
                  <th className="th">Margen</th><th className="th">Estado</th><th className="th">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {f.paginados.map((p, i) => (
                  <tr key={p.id_producto} className={`border-b border-border hover:bg-[#f0f0ff] ${i % 2 ? 'bg-muted' : 'bg-card'} ${p.estado === 'Inactivo' ? 'opacity-55' : ''}`}>
                    <td className="td font-medium whitespace-nowrap text-muted-foreground">{p.sku}</td>
                    <td className="td">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-[34px] w-[34px] shrink-0 items-center justify-center rounded-lg bg-muted text-lg">{emojiCategoria(p.nombre_categoria)}</div>
                        <div>
                          <div className="font-semibold">{p.nombre}</div>
                          {p.ubicacion && <div className="text-[11px] text-muted-foreground">{p.ubicacion}</div>}
                        </div>
                      </div>
                    </td>
                    <td className="td text-muted-foreground">{p.nombre_categoria}</td>
                    <td className="td text-muted-foreground">{p.nombre_marca ?? '—'}</td>
                    <td className="td"><StockCell p={p} /></td>
                    <td className="td font-semibold whitespace-nowrap text-muted-foreground">{convertir(p.precio_distribuidor, moneda)}</td>
                    <td className="td font-bold whitespace-nowrap text-primary">{convertir(p.precio_usd, moneda)}</td>
                    <td className="td whitespace-nowrap text-muted-foreground" title={p.margen_pct === null ? 'Margen de la categoría' : 'Margen propio'}>
                      {num(p.margen_efectivo) === 0 ? 'Manual' : `${num(p.margen_efectivo)}%`}{p.margen_pct !== null && ' *'}
                    </td>
                    <td className="td"><Badge>{p.estado}</Badge></td>
                    <td className="td">
                      <div className="flex gap-1.5">
                        <button aria-label={`Editar ${p.nombre}`} className="btn-icon !h-[30px] !w-[30px] text-primary" onClick={() => setModal({ producto: p })}><Pencil size={13} /></button>
                        {p.estado === 'Inactivo' ? (
                          <button className="btn-muted !px-2 !py-1 text-[11px]" onClick={() => reactivar.mutate(p, { onError: e => toast(errorText(e), 'error') })}>Reactivar</button>
                        ) : (
                          <button aria-label={`Dar de baja ${p.nombre}`} className="btn-icon !h-[30px] !w-[30px] text-danger" onClick={() => setBaja(p)}><Trash2 size={13} /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
                {f.paginados.length === 0 && <tr><td colSpan={10}><EmptyState title="No se encontraron productos." /></td></tr>}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-3.5">
          <span className="text-xs text-muted-foreground">{f.filtrados.length} productos · * margen propio</span>
          <Pagination page={f.pagina} total={f.totalPaginas} onChange={f.setPagina} />
        </div>
      </div>

      {modal && <ProductoModal producto={modal.producto} onClose={() => setModal(null)} />}
      {baja && (
        <ConfirmDialog danger title="Dar de baja producto" confirmText="Dar de baja" busy={darBaja.isPending}
          message={<>¿Dar de baja <b>{baja.nombre}</b> ({baja.sku})? Deja de aparecer para la venta, pero se conserva su historial. Se puede reactivar luego.
            {darBaja.error && <div className="mt-3"><ErrorBanner error={darBaja.error} /></div>}</>}
          onConfirm={() => darBaja.mutate(baja)} onClose={() => setBaja(null)} />
      )}
    </div>
  )
}
