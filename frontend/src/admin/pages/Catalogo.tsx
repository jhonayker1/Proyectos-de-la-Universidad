/** Categorías y marcas: alta, edición y baja lógica (estado = 0) con reactivación. */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, Pencil, Plus, Power, Search } from 'lucide-react'
import { categoriasApi, marcasApi } from '@/api/endpoints'
import { keys, useApiMutation, useProductosAdmin } from '@/api/queries'
import type { Categoria, Marca, ProductoAdmin } from '@/api/types'
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, Field, Modal, Spinner, cx, errorText, useToast } from '@/shared/components/ui'
import { num, parseDecimal } from '@/shared/lib/money'

/** Cuántos productos activos usan cada categoría / marca, y cuáles tienen stock por categoría. */
function useConteos() {
  const productos = useProductosAdmin()
  return React.useMemo(() => {
    const cat = new Map<number, number>()
    const marca = new Map<number, number>()
    const stockCat = new Map<number, ProductoAdmin[]>()
    for (const p of productos.data ?? []) {
      if (p.estado === 'Inactivo') continue
      cat.set(p.id_categoria, (cat.get(p.id_categoria) ?? 0) + 1)
      if (p.id_marca !== null) marca.set(p.id_marca, (marca.get(p.id_marca) ?? 0) + 1)
      if (p.stock_actual > 0) stockCat.set(p.id_categoria, [...(stockCat.get(p.id_categoria) ?? []), p])
    }
    for (const lista of stockCat.values()) lista.sort((a, b) => b.stock_actual - a.stock_actual)
    return { cat, marca, stockCat }
  }, [productos.data])
}

/** Aviso cuando se intenta desactivar una categoría que todavía tiene productos con stock. */
function CategoriaConStock({ categoria, productos, onClose }: { categoria: Categoria; productos: ProductoAdmin[]; onClose: () => void }) {
  const unidades = productos.reduce((t, p) => t + p.stock_actual, 0)
  const visibles = productos.slice(0, 8)
  return (
    <Modal title="No se puede desactivar esta categoría" onClose={onClose} footer={<button className="btn-primary" onClick={onClose}>Entendido</button>}>
      <div className="flex gap-3 rounded-xl border border-warning/40 bg-warning/10 p-3.5 text-[13px]">
        <AlertTriangle size={20} className="mt-0.5 shrink-0 text-warning" />
        <div>
          <b>{categoria.nombre}</b> tiene <b>{productos.length} producto(s) con stock</b> ({unidades} unidades en total).
          Venda ese stock o cambie esos productos de categoría (en Inventario) antes de desactivarla.
        </div>
      </div>
      <div className="mt-3.5 overflow-hidden rounded-xl border border-border">
        {visibles.map((p, i) => (
          <div key={p.id_producto} className={cx('flex items-center gap-2.5 px-3 py-2 text-xs', i > 0 && 'border-t border-border')}>
            <span className="min-w-0 flex-1 truncate"><b>{p.sku}</b> · {p.nombre}</span>
            <span className="font-display font-bold">{p.stock_actual} uds.</span>
          </div>
        ))}
        {productos.length > visibles.length && (
          <div className="border-t border-border px-3 py-2 text-xs text-muted-foreground">y {productos.length - visibles.length} producto(s) más…</div>
        )}
      </div>
    </Modal>
  )
}

/** Marco común de cada panel: título, buscador, botón "Nueva" y lista. */
function Panel({ titulo, subtitulo, buscar, setBuscar, onNuevo, nuevoLabel, children }: {
  titulo: string; subtitulo: string; buscar: string; setBuscar: (v: string) => void
  onNuevo: () => void; nuevoLabel: string; children: React.ReactNode
}) {
  return (
    <div className="card flex min-h-[420px] flex-col overflow-hidden">
      <div className="flex shrink-0 flex-wrap items-center gap-3 border-b border-border px-[18px] py-3.5">
        <div className="mr-auto">
          <h3 className="m-0 text-sm font-bold">{titulo}</h3>
          <p className="mt-0.5 mb-0 text-[11px] text-muted-foreground">{subtitulo}</p>
        </div>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground" />
          <input aria-label={`Buscar en ${titulo}`} className="input !w-44 !py-1.5 !pl-8 text-xs" placeholder="Buscar..." value={buscar} onChange={e => setBuscar(e.target.value)} />
        </div>
        <button className="btn-primary !px-3 !py-1.5 text-xs" onClick={onNuevo}><Plus size={13} /> {nuevoLabel}</button>
      </div>
      <div className="max-h-[620px] flex-1 overflow-y-auto">{children}</div>
    </div>
  )
}

function Fila({ nombre, detalle, extra, activo, productos, unidades, onEditar, onToggle }: {
  nombre: string; detalle?: string | null; extra?: React.ReactNode; activo: boolean
  productos: number; unidades?: number; onEditar: () => void; onToggle: () => void
}) {
  return (
    <div className={cx('flex items-center gap-3 border-b border-border px-[18px] py-3', !activo && 'opacity-55')}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-display text-sm font-bold">{nombre}</span>
          {!activo && <Badge tone="Inactivo">Inactiva</Badge>}
        </div>
        {detalle && <div className="mt-0.5 truncate text-xs text-muted-foreground">{detalle}</div>}
      </div>
      {extra}
      <span className={cx('text-right text-xs text-muted-foreground', unidades === undefined ? 'w-20' : 'w-32')}>
        {productos} prod.{unidades !== undefined && <> · <span className={unidades > 0 ? 'font-semibold text-foreground' : undefined}>{unidades} uds.</span></>}
      </span>
      <button aria-label={`Editar ${nombre}`} className="btn-icon text-primary" onClick={onEditar}><Pencil size={13} /></button>
      <button aria-label={`${activo ? 'Desactivar' : 'Reactivar'} ${nombre}`} title={activo ? 'Desactivar' : 'Reactivar'}
        className={cx('btn-icon', activo ? 'text-danger' : 'text-success')} onClick={onToggle}>
        <Power size={13} />
      </button>
    </div>
  )
}

/** Sugerencia de código desde el nombre (Baterías -> BAT); el backend confirma que no se repita. */
const codigoDesdeNombre = (nombre: string) =>
  (nombre.normalize('NFD').replace(/[̀-ͯ]/g, '').toUpperCase().match(/[A-Z]+/)?.[0] ?? '').slice(0, 3)

function CategoriaModal({ categoria, onClose }: { categoria: Categoria | null; onClose: () => void }) {
  const toast = useToast()
  const [nombre, setNombre] = React.useState(categoria?.nombre ?? '')
  const [descripcion, setDescripcion] = React.useState(categoria?.descripcion ?? '')
  const [margen, setMargen] = React.useState(categoria ? String(num(categoria.margen_ganancia)) : '0')
  const [codigo, setCodigo] = React.useState(categoria?.prefijo_sku ?? '')
  // Mientras no lo edite a mano, el código sigue al nombre al crear una categoría.
  const [codigoManual, setCodigoManual] = React.useState(Boolean(categoria))
  const m = parseDecimal(margen || '0')
  const margenValido = m >= 0 && m <= 999.99
  const codigoValido = /^[A-Z]{2,5}$/.test(codigo)
  const cambiaCodigo = Boolean(categoria?.prefijo_sku) && codigo !== categoria?.prefijo_sku
  const guardar = useApiMutation(() => {
    const data = { nombre: nombre.trim(), descripcion: descripcion.trim() || null, margen_ganancia: String(m), prefijo_sku: codigo }
    return categoria ? categoriasApi.update(categoria.id_categoria, data) : categoriasApi.create(data)
  }, [keys.categorias, keys.productos], c => { toast(`Categoría ${c.nombre} guardada (código ${c.prefijo_sku}).`); onClose() })
  return (
    <Modal title={categoria ? 'Editar categoría' : 'Nueva categoría'} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={!nombre.trim() || !margenValido || !codigoValido || guardar.isPending} onClick={() => guardar.mutate(undefined)}>
        {guardar.isPending ? 'Guardando...' : 'Guardar'}
      </button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Nombre"><input className="input" autoFocus maxLength={100} value={nombre}
          onChange={e => { setNombre(e.target.value); if (!codigoManual) setCodigo(codigoDesdeNombre(e.target.value)) }} /></Field>
        <Field label="Código para el SKU"
          hint={<span className={!codigoValido && codigo ? 'text-danger' : cambiaCodigo ? 'text-warning' : undefined}>
            {!codigoValido && codigo ? 'De 2 a 5 letras, sin números ni acentos.'
              : cambiaCodigo ? `Solo los productos nuevos usarán ${codigo}; los existentes conservan su SKU (${categoria?.prefijo_sku}-…).`
                : `Los productos nuevos se numeran solos: ${codigo || 'XXX'}-0001, ${codigo || 'XXX'}-0002…`}
          </span>}>
          <input className={cx('input !w-32 font-mono font-semibold uppercase', codigo && !codigoValido && '!border-danger')} maxLength={5}
            value={codigo} onChange={e => { setCodigoManual(true); setCodigo(e.target.value.toUpperCase().replace(/[^A-Z]/g, '')) }} />
        </Field>
        <Field label="Descripción"><input className="input" maxLength={255} value={descripcion} onChange={e => setDescripcion(e.target.value)} /></Field>
        <Field label="Porcentaje de ganancia (%)"
          hint={<span className={m >= 100 ? 'text-red-600' : undefined}>
            {m >= 100 ? 'Advertencia: el porcentaje ingresado representa una cantidad desproporcionada.'
              : '0% = precios manuales. Si cambia, se recalculan los productos de la categoría sin margen propio.'}
          </span>}>
          <input className={cx('input !w-32', !margenValido && '!border-danger')} inputMode="decimal" value={margen} onChange={e => setMargen(e.target.value)} />
        </Field>
        {guardar.error && <ErrorBanner error={guardar.error} />}
      </div>
    </Modal>
  )
}

function MarcaModal({ marca, onClose }: { marca: Marca | null; onClose: () => void }) {
  const toast = useToast()
  const [nombre, setNombre] = React.useState(marca?.nombre ?? '')
  const [pais, setPais] = React.useState(marca?.pais_origen ?? '')
  const guardar = useApiMutation(() => {
    const data = { nombre: nombre.trim(), pais_origen: pais.trim() || null }
    return marca ? marcasApi.update(marca.id_marca, data) : marcasApi.create(data)
  }, [keys.marcas, keys.productos], m => { toast(`Marca ${m.nombre} guardada.`); onClose() })
  return (
    <Modal title={marca ? 'Editar marca' : 'Nueva marca'} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={!nombre.trim() || guardar.isPending} onClick={() => guardar.mutate(undefined)}>
        {guardar.isPending ? 'Guardando...' : 'Guardar'}
      </button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Nombre"><input className="input" autoFocus maxLength={100} value={nombre} onChange={e => setNombre(e.target.value)} /></Field>
        <Field label="País de origen"><input className="input" maxLength={50} value={pais} onChange={e => setPais(e.target.value)} /></Field>
        {guardar.error && <ErrorBanner error={guardar.error} />}
      </div>
    </Modal>
  )
}

type Baja = { tipo: 'categoria'; item: Categoria } | { tipo: 'marca'; item: Marca }

const coincide = (q: string, ...textos: (string | null)[]) => textos.some(t => (t ?? '').toLowerCase().includes(q.trim().toLowerCase()))

export default function Catalogo() {
  const toast = useToast()
  const conteos = useConteos()
  const categorias = useQuery({ queryKey: [...keys.categorias, 'todas'], queryFn: categoriasApi.listTodas })
  const marcas = useQuery({ queryKey: [...keys.marcas, 'todas'], queryFn: marcasApi.listTodas })
  const [buscarCat, setBuscarCat] = React.useState('')
  const [buscarMarca, setBuscarMarca] = React.useState('')
  const [editCat, setEditCat] = React.useState<{ c: Categoria | null } | null>(null)
  const [editMarca, setEditMarca] = React.useState<{ m: Marca | null } | null>(null)
  const [baja, setBaja] = React.useState<Baja | null>(null)
  const [conStock, setConStock] = React.useState<Categoria | null>(null)

  const desactivar = useApiMutation((b: Baja) => b.tipo === 'categoria' ? categoriasApi.remove(b.item.id_categoria) : marcasApi.remove(b.item.id_marca),
    [keys.categorias, keys.marcas], () => { toast('Desactivada. Ya no aparece al crear productos ni en los filtros.'); setBaja(null) })
  const reactivarCat = useApiMutation((c: Categoria) => categoriasApi.update(c.id_categoria, { estado: 1 }), [keys.categorias], c => toast(`${c.nombre} reactivada.`))
  const reactivarMarca = useApiMutation((m: Marca) => marcasApi.update(m.id_marca, { estado: 1 }), [keys.marcas], m => toast(`${m.nombre} reactivada.`))
  const onError = { onError: (e: unknown) => toast(errorText(e), 'error') }

  const cats = (categorias.data ?? []).filter(c => coincide(buscarCat, c.nombre, c.descripcion))
  const mars = (marcas.data ?? []).filter(m => coincide(buscarMarca, m.nombre, m.pais_origen))
  const productosDe = (b: Baja) => b.tipo === 'categoria' ? conteos.cat.get(b.item.id_categoria) ?? 0 : conteos.marca.get(b.item.id_marca) ?? 0
  const stockDe = (c: Categoria) => conteos.stockCat.get(c.id_categoria) ?? []
  const unidadesDe = (c: Categoria) => stockDe(c).reduce((t, p) => t + p.stock_actual, 0)
  // Una categoría con productos en stock no se desactiva: se muestra el aviso (el backend también lo impide).
  const desactivarCategoria = (c: Categoria) => stockDe(c).length > 0 ? setConStock(c) : setBaja({ tipo: 'categoria', item: c })

  return (
    <div className="grid grid-cols-1 gap-4 pb-6 xl:grid-cols-2">
      <Panel titulo="Categorías" subtitulo={`${categorias.data?.filter(c => c.estado === 1).length ?? 0} activas · margen de ganancia por categoría`}
        buscar={buscarCat} setBuscar={setBuscarCat} onNuevo={() => setEditCat({ c: null })} nuevoLabel="Nueva categoría">
        {categorias.isLoading ? <Spinner /> : categorias.error ? <div className="p-4"><ErrorBanner error={categorias.error} onRetry={() => categorias.refetch()} /></div> :
          cats.length === 0 ? <EmptyState title="No hay categorías con ese criterio." /> : cats.map(c => (
            <Fila key={c.id_categoria} nombre={c.nombre} detalle={c.descripcion} activo={c.estado === 1}
              productos={conteos.cat.get(c.id_categoria) ?? 0} unidades={unidadesDe(c)}
              extra={<>
                <span className="w-14 rounded-md border border-border bg-muted px-1.5 py-0.5 text-center font-mono text-[11px] font-bold text-primary"
                  title="Código para el SKU de los productos nuevos">{c.prefijo_sku ?? '—'}</span>
                <span className="w-20 text-right font-display text-sm font-bold text-primary" title="Margen de ganancia">
                  {num(c.margen_ganancia) === 0 ? 'Manual' : `${num(c.margen_ganancia)}%`}
                </span>
              </>}
              onEditar={() => setEditCat({ c })}
              onToggle={() => c.estado === 1 ? desactivarCategoria(c) : reactivarCat.mutate(c, onError)} />
          ))}
      </Panel>

      <Panel titulo="Marcas" subtitulo={`${marcas.data?.filter(m => m.estado === 1).length ?? 0} activas`}
        buscar={buscarMarca} setBuscar={setBuscarMarca} onNuevo={() => setEditMarca({ m: null })} nuevoLabel="Nueva marca">
        {marcas.isLoading ? <Spinner /> : marcas.error ? <div className="p-4"><ErrorBanner error={marcas.error} onRetry={() => marcas.refetch()} /></div> :
          mars.length === 0 ? <EmptyState title="No hay marcas con ese criterio." /> : mars.map(m => (
            <Fila key={m.id_marca} nombre={m.nombre} detalle={m.pais_origen} activo={m.estado === 1}
              productos={conteos.marca.get(m.id_marca) ?? 0}
              onEditar={() => setEditMarca({ m })}
              onToggle={() => m.estado === 1 ? setBaja({ tipo: 'marca', item: m }) : reactivarMarca.mutate(m, onError)} />
          ))}
      </Panel>

      {editCat && <CategoriaModal categoria={editCat.c} onClose={() => setEditCat(null)} />}
      {editMarca && <MarcaModal marca={editMarca.m} onClose={() => setEditMarca(null)} />}
      {conStock && <CategoriaConStock categoria={conStock} productos={stockDe(conStock)} onClose={() => setConStock(null)} />}
      {baja && (
        <ConfirmDialog danger title={`Desactivar ${baja.tipo === 'categoria' ? 'categoría' : 'marca'}`} confirmText="Desactivar" busy={desactivar.isPending}
          message={<>
            ¿Desactivar <b>{baja.item.nombre}</b>? Dejará de aparecer al crear productos y en los filtros. Se puede reactivar luego.
            {productosDe(baja) > 0 && <div className="mt-2 font-semibold text-warning">
              {baja.tipo === 'categoria'
                ? `${productosDe(baja)} producto(s) sin stock la usan; conservarán esta categoría.`
                : `${productosDe(baja)} producto(s) la usan; seguirán a la venta con esta marca.`}
            </div>}
            {desactivar.error && <div className="mt-3"><ErrorBanner error={desactivar.error} /></div>}
          </>}
          onConfirm={() => desactivar.mutate(baja)} onClose={() => { setBaja(null); desactivar.reset() }} />
      )}
    </div>
  )
}
