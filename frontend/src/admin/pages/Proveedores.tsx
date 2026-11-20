import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, ChevronDown, Mail, MapPin, Pencil, Phone, Plus, Search, ShoppingBag, Trash2 } from 'lucide-react'
import { comprasApi, proveedoresApi } from '@/api/endpoints'
import { keys, useApiMutation, useProductosAdmin, useProveedores } from '@/api/queries'
import type { Compra, Proveedor } from '@/api/types'
import { PALETTE } from '@/shared/components/charts'
import { Badge, ConfirmDialog, EmptyState, ErrorBanner, Field, Modal, Spinner, StatBox, Tabs, cx, errorText, useToast } from '@/shared/components/ui'
import { parseLocal, todayIso } from '@/shared/lib/dates'
import { num, parseDecimal, round2, usd } from '@/shared/lib/money'

type FormProv = { nombre: string; rif: string; contacto: string; telefono: string; correo: string; ciudad: string; condiciones: string }

// Mismas reglas que app/schemas/catalogo.py (el backend vuelve a validar).
const RIF_RE = /^([VEJPGC])[-\s]?(\d{5,9})(?:[-\s]?(\d))?$/

const VALIDAR: Partial<Record<keyof FormProv, (v: string) => string | null>> = {
  nombre: v => (v.trim() ? null : 'El nombre es obligatorio.'),
  rif: v => {
    const r = v.trim().toUpperCase()
    if (!r) return 'El RIF es obligatorio.'
    if (!/^[A-Z]/.test(r)) return 'El RIF debe comenzar con una letra (V, E, J, P, G o C).'
    if (!RIF_RE.test(r)) return 'Use una letra V, E, J, P, G o C seguida de los números. Ej.: J-12345678-9'
    return null
  },
  telefono: v => {
    const t = v.trim()
    if (!t) return 'El teléfono es obligatorio.'
    if (!/^[\d\s+()\-.]+$/.test(t)) return 'Solo números, espacios, +, -, ( y ).'
    const digitos = t.replace(/\D/g, '').length
    return digitos < 7 || digitos > 15 ? 'Debe tener entre 7 y 15 dígitos.' : null
  },
  correo: v => {
    const c = v.trim()
    if (!c) return 'El correo es obligatorio.'
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(c) ? null : 'Correo inválido. Ej.: ventas@proveedor.com'
  },
}

function ProveedorModal({ proveedor, onClose }: { proveedor: Proveedor | null; onClose: () => void }) {
  const toast = useToast()
  const [form, setForm] = React.useState<FormProv>({
    nombre: proveedor?.nombre ?? '', rif: proveedor?.rif ?? '', contacto: proveedor?.contacto ?? '',
    telefono: proveedor?.telefono ?? '', correo: proveedor?.correo ?? '', ciudad: proveedor?.ciudad ?? '',
    condiciones: proveedor?.condiciones ?? '',
  })
  // Los errores se muestran al salir del campo o al intentar guardar, no mientras se escribe.
  const [tocados, setTocados] = React.useState<Partial<Record<keyof FormProv, boolean>>>({})
  const [intentado, setIntentado] = React.useState(false)
  const set = (k: keyof FormProv) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: k === 'rif' ? e.target.value.toUpperCase() : e.target.value }))
  const errores = Object.fromEntries(
    (Object.keys(VALIDAR) as (keyof FormProv)[]).map(k => [k, VALIDAR[k]!(form[k])]),
  ) as Partial<Record<keyof FormProv, string | null>>
  const hayErrores = Object.values(errores).some(Boolean)
  const errorDe = (k: keyof FormProv) => (tocados[k] || intentado ? errores[k] ?? null : null)

  const guardar = useApiMutation(async () => {
    const data = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v.trim() || null])) as Partial<Proveedor>
    return proveedor ? proveedoresApi.update(proveedor.id_proveedor, data) : proveedoresApi.create(data)
  }, [keys.proveedores], p => { toast(`Proveedor ${p.nombre} guardado.`); onClose() })
  const submit = () => {
    setIntentado(true)
    if (!hayErrores) guardar.mutate(undefined)
  }

  const campo = (k: keyof FormProv, label: string, opts: { placeholder?: string; type?: string; className?: string; ayuda?: string; autoFocus?: boolean } = {}) => {
    const obligatorio = k in VALIDAR
    const error = errorDe(k)
    return (
      <Field key={k} label={`${label}${obligatorio ? ' *' : ''}`} className={opts.className}
        hint={error ? <span className="text-danger" role="alert">{error}</span> : opts.ayuda}>
        <input className={cx('input', error && '!border-danger')} placeholder={opts.placeholder} type={opts.type ?? 'text'}
          autoFocus={opts.autoFocus} value={form[k]} onChange={set(k)} aria-invalid={Boolean(error)}
          onBlur={() => setTocados(t => ({ ...t, [k]: true }))} />
      </Field>
    )
  }

  return (
    <Modal title={proveedor ? 'Editar proveedor' : 'Nuevo proveedor'} onClose={onClose} width="max-w-lg" footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={guardar.isPending} onClick={submit}>
        {guardar.isPending ? 'Guardando...' : 'Guardar'}
      </button>
    </>}>
      <div className="grid grid-cols-2 gap-3.5">
        {campo('nombre', 'Nombre', { className: 'col-span-2', autoFocus: true })}
        {campo('rif', 'RIF', { placeholder: 'J-12345678-9', ayuda: 'Letra V, E, J, P, G o C y los números.' })}
        {campo('contacto', 'Persona de contacto')}
        {campo('telefono', 'Teléfono', { placeholder: '0414-555-0141', type: 'tel' })}
        {campo('correo', 'Correo', { placeholder: 'ventas@proveedor.com', type: 'email' })}
        {campo('ciudad', 'Ciudad')}
        {campo('condiciones', 'Condiciones de pago', { placeholder: 'Crédito a 30 días' })}
        <p className="col-span-2 m-0 text-[11px] text-muted-foreground">* Campos obligatorios.</p>
        {intentado && hayErrores && (
          <div className="col-span-2 rounded-lg bg-danger/10 px-3 py-2 text-xs font-semibold text-danger">
            Revise los campos marcados en rojo antes de guardar.
          </div>
        )}
        {guardar.error && <div className="col-span-2"><ErrorBanner error={guardar.error} /></div>}
      </div>
    </Modal>
  )
}

type Linea = { id_producto: string; cantidad: string; costo: string }

function CompraModal({ proveedor, onClose }: { proveedor: Proveedor; onClose: () => void }) {
  const toast = useToast()
  const productos = useProductosAdmin()
  const [factura, setFactura] = React.useState('')
  const [fecha, setFecha] = React.useState(todayIso())
  const [descripcion, setDescripcion] = React.useState('')
  const [pagado, setPagado] = React.useState(false)
  const [actualizar, setActualizar] = React.useState(true)
  const [lineas, setLineas] = React.useState<Linea[]>([{ id_producto: '', cantidad: '1', costo: '' }])
  const setLinea = (i: number, l: Partial<Linea>) => setLineas(ls => ls.map((x, j) => (j === i ? { ...x, ...l } : x)))
  const activos = (productos.data ?? []).filter(p => p.estado !== 'Inactivo')
  const total = round2(lineas.reduce((t, l) => t + (Number(l.cantidad) || 0) * (parseDecimal(l.costo || '0') || 0), 0))
  const validas = lineas.every(l => l.id_producto && Number.isInteger(Number(l.cantidad)) && Number(l.cantidad) > 0 && parseDecimal(l.costo) >= 0)

  const guardar = useApiMutation(() => comprasApi.create({
    id_proveedor: proveedor.id_proveedor, numero_factura: factura.trim() || null, fecha,
    descripcion: descripcion.trim() || null, pagado, actualizar_costos: actualizar,
    detalles: lineas.map(l => ({ id_producto: Number(l.id_producto), cantidad: Number(l.cantidad), costo_unitario_usd: parseDecimal(l.costo).toFixed(2) })),
  }), [keys.compras, keys.productos, keys.reportes], c => {
    toast(`Compra registrada (${usd(c.monto_usd)}); stock actualizado.`); onClose()
  })

  return (
    <Modal title="Registrar compra" subtitle={`${proveedor.nombre} · las cantidades se suman al inventario`} onClose={onClose} width="max-w-2xl" footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={!validas || guardar.isPending} onClick={() => guardar.mutate(undefined)}>
        {guardar.isPending ? 'Registrando...' : `Registrar ${usd(total)}`}
      </button>
    </>}>
      <div className="grid grid-cols-3 gap-3.5">
        <Field label="N.º de factura"><input className="input" value={factura} onChange={e => setFactura(e.target.value)} placeholder="F-004512" /></Field>
        <Field label="Fecha"><input className="input" type="date" max={todayIso()} value={fecha} onChange={e => setFecha(e.target.value)} /></Field>
        <Field label="Descripción"><input className="input" value={descripcion} onChange={e => setDescripcion(e.target.value)} placeholder="40 cauchos 195/65 R15" /></Field>
      </div>
      <div className="mt-4 rounded-xl border border-border">
        <div className="grid grid-cols-[1fr_90px_120px_32px] gap-2 border-b border-border bg-muted px-3 py-2 text-[11px] font-semibold text-muted-foreground">
          <span>Producto</span><span>Cantidad</span><span>Costo unit. USD</span><span />
        </div>
        {lineas.map((l, i) => (
          <div key={i} className="grid grid-cols-[1fr_90px_120px_32px] items-center gap-2 border-b border-border px-3 py-2 last:border-b-0">
            <select aria-label="Producto" className="input !bg-card" value={l.id_producto}
              onChange={e => {
                const p = activos.find(x => String(x.id_producto) === e.target.value)
                setLinea(i, { id_producto: e.target.value, costo: l.costo || (p ? String(num(p.precio_distribuidor)) : '') })
              }}>
              <option value="">Seleccione...</option>
              {activos.map(p => <option key={p.id_producto} value={p.id_producto}>{p.sku} · {p.nombre}</option>)}
            </select>
            <input aria-label="Cantidad" className="input !bg-card" type="number" min={1} value={l.cantidad} onChange={e => setLinea(i, { cantidad: e.target.value })} />
            <input aria-label="Costo unitario" className="input !bg-card" inputMode="decimal" value={l.costo} onChange={e => setLinea(i, { costo: e.target.value })} />
            <button aria-label="Quitar línea" className="btn-icon text-danger" disabled={lineas.length === 1} onClick={() => setLineas(ls => ls.filter((_, j) => j !== i))}><Trash2 size={13} /></button>
          </div>
        ))}
        <div className="flex items-center justify-between px-3 py-2">
          <button className="btn-muted !px-3 !py-1 text-xs" onClick={() => setLineas(ls => [...ls, { id_producto: '', cantidad: '1', costo: '' }])}><Plus size={12} /> Agregar producto</button>
          <span className="text-[13px]">Total: <b className="font-display text-primary">{usd(total)}</b></span>
        </div>
      </div>
      <div className="mt-3.5 flex flex-col gap-2 text-[13px]">
        <label className="flex items-center gap-2"><input type="checkbox" checked={pagado} onChange={e => setPagado(e.target.checked)} /> Ya está pagada</label>
        <label className="flex items-center gap-2"><input type="checkbox" checked={actualizar} onChange={e => setActualizar(e.target.checked)} />
          Actualizar el costo (precio distribuidor) de cada producto con el de esta compra</label>
      </div>
      {guardar.error && <div className="mt-3"><ErrorBanner error={guardar.error} /></div>}
    </Modal>
  )
}

function HistorialCompras({ compras }: { compras: Compra[] }) {
  const toast = useToast()
  const pagar = useApiMutation((c: Compra) => comprasApi.setPagado(c.id_compra, !c.pagado), [keys.compras])
  if (compras.length === 0) return <EmptyState title="Sin compras registradas." />
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      {compras.map((c, i) => (
        <div key={c.id_compra} className={cx('flex items-center gap-2.5 px-3 py-2.5 text-xs', i > 0 && 'border-t border-border')}>
          <div className="min-w-0 flex-1">
            <div className="font-bold">{c.numero_factura ?? 'Sin n.º'} · {c.descripcion ?? c.detalles.map(d => `${d.cantidad} ${d.nombre_producto}`).join(', ')}</div>
            <div className="text-muted-foreground">{parseLocal(c.fecha).toLocaleDateString('es-VE', { day: '2-digit', month: 'short', year: 'numeric' })}</div>
          </div>
          <span className="font-display font-bold">{usd(c.monto_usd)}</span>
          <button title={c.pagado ? 'Marcar como pendiente' : 'Marcar como pagada'} className="cursor-pointer border-none bg-transparent p-0"
            onClick={() => pagar.mutate(c, { onError: e => toast(errorText(e), 'error') })}>
            <Badge tone={c.pagado ? 'Pagada' : 'Pendiente'}>{c.pagado ? 'Pagada' : 'Pendiente'}</Badge>
          </button>
        </div>
      ))}
    </div>
  )
}

/**
 * Eliminar proveedor: si tiene compras sin pagar se muestra la advertencia (y el backend
 * también lo impide). La eliminación es lógica: el historial de compras se conserva.
 */
function EliminarProveedor({ proveedor, pendientes, onClose }: { proveedor: Proveedor; pendientes: Compra[]; onClose: () => void }) {
  const toast = useToast()
  const eliminar = useApiMutation(() => proveedoresApi.remove(proveedor.id_proveedor), [keys.proveedores, keys.compras], () => {
    toast(`Proveedor ${proveedor.nombre} eliminado.`)
    onClose()
  })

  if (pendientes.length > 0) {
    const deuda = pendientes.reduce((t, c) => t + num(c.monto_usd), 0)
    return (
      <Modal title="No se puede eliminar este proveedor" onClose={onClose} footer={<button className="btn-primary" onClick={onClose}>Entendido</button>}>
        <div className="flex gap-3 rounded-xl border border-warning/40 bg-warning/10 p-3.5 text-[13px]">
          <AlertTriangle size={20} className="mt-0.5 shrink-0 text-warning" />
          <div>
            <b>{proveedor.nombre}</b> tiene <b>{pendientes.length} compra(s) pendiente(s) de pago</b> por <b>{usd(deuda)}</b>.
            Márquelas como pagadas en su historial de compras antes de eliminarlo.
          </div>
        </div>
        <div className="mt-3.5 overflow-hidden rounded-xl border border-border">
          {pendientes.map((c, i) => (
            <div key={c.id_compra} className={cx('flex items-center gap-2.5 px-3 py-2 text-xs', i > 0 && 'border-t border-border')}>
              <span className="flex-1">
                <b>{c.numero_factura ?? 'Sin n.º'}</b> · {parseLocal(c.fecha).toLocaleDateString('es-VE')}
              </span>
              <span className="font-display font-bold">{usd(c.monto_usd)}</span>
              <Badge tone="Pendiente">Pendiente</Badge>
            </div>
          ))}
        </div>
      </Modal>
    )
  }

  return (
    <ConfirmDialog danger title="Eliminar proveedor" confirmText="Eliminar" busy={eliminar.isPending}
      message={<>
        ¿Eliminar a <b>{proveedor.nombre}</b>? Dejará de aparecer en la lista y no se le podrán registrar compras nuevas.
        Su historial de compras y los productos que lo tienen asignado se conservan.
        {eliminar.error && <div className="mt-3"><ErrorBanner error={eliminar.error} /></div>}
      </>}
      onConfirm={() => eliminar.mutate(undefined)} onClose={onClose} />
  )
}

export default function Proveedores() {
  const proveedores = useProveedores()
  const compras = useQuery({ queryKey: keys.compras, queryFn: () => comprasApi.list({ limite: 1000 }) })
  const productos = useProductosAdmin()
  const [q, setQ] = React.useState('')
  const [cat, setCat] = React.useState('Todas')
  const [abierto, setAbierto] = React.useState<number | null>(null)
  const [editar, setEditar] = React.useState<{ p: Proveedor | null } | null>(null)
  const [comprar, setComprar] = React.useState<Proveedor | null>(null)
  const [eliminar, setEliminar] = React.useState<Proveedor | null>(null)

  // La base no guarda categoría del proveedor: se deduce de los productos que suministra.
  const suministros = React.useMemo(() => {
    const m = new Map<number, { productos: string[]; categorias: Set<string> }>()
    for (const p of productos.data ?? []) {
      if (p.id_proveedor === null || p.estado === 'Inactivo') continue
      const s = m.get(p.id_proveedor) ?? { productos: [], categorias: new Set<string>() }
      s.productos.push(p.nombre)
      if (p.nombre_categoria) s.categorias.add(p.nombre_categoria)
      m.set(p.id_proveedor, s)
    }
    return m
  }, [productos.data])
  const categorias = ['Todas', ...new Set([...suministros.values()].flatMap(s => [...s.categorias]))]
  const comprasDe = (id: number) => (compras.data ?? []).filter(c => c.id_proveedor === id)

  const lista = (proveedores.data ?? []).filter(p => {
    const s = suministros.get(p.id_proveedor)
    const texto = `${p.nombre} ${p.rif ?? ''} ${p.contacto ?? ''} ${s?.productos.join(' ') ?? ''}`.toLowerCase()
    return (cat === 'Todas' || s?.categorias.has(cat)) && texto.includes(q.trim().toLowerCase())
  })
  const totalCompras = lista.reduce((t, p) => t + comprasDe(p.id_proveedor).reduce((s, c) => s + num(c.monto_usd), 0), 0)
  const totalDeuda = lista.reduce((t, p) => t + comprasDe(p.id_proveedor).filter(c => !c.pagado).reduce((s, c) => s + num(c.monto_usd), 0), 0)

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3.5">
        <StatBox className="!bg-card" label="Proveedores" value={lista.length} color="#4f46e5" />
        <StatBox className="!bg-card" label="Total comprado" value={usd(totalCompras)} color="#06b6d4" />
        <StatBox className="!bg-card" label="Deuda pendiente" value={usd(totalDeuda)} color={totalDeuda > 0 ? '#dc2626' : '#10b981'} />
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <div className="relative min-w-60 flex-1">
          <Search size={15} className="absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
          <input className="input !bg-card !pl-9" value={q} onChange={e => setQ(e.target.value)} placeholder="Buscar por nombre, RIF, contacto o producto" />
        </div>
        <Tabs value={cat} options={categorias} onChange={setCat} />
        <button className="btn-primary" onClick={() => setEditar({ p: null })}><Plus size={14} /> Nuevo proveedor</button>
      </div>

      {proveedores.isLoading ? <Spinner /> : proveedores.error ? <ErrorBanner error={proveedores.error} onRetry={() => proveedores.refetch()} /> :
        lista.length === 0 ? <div className="card"><EmptyState title="No se encontraron proveedores con ese criterio." /></div> : lista.map((p, idx) => {
          const cs = comprasDe(p.id_proveedor)
          const comprado = cs.reduce((s, c) => s + num(c.monto_usd), 0)
          const deuda = cs.filter(c => !c.pagado).reduce((s, c) => s + num(c.monto_usd), 0)
          const s = suministros.get(p.id_proveedor)
          const open = abierto === p.id_proveedor
          return (
            <div key={p.id_proveedor} className="card overflow-hidden !rounded-[14px]">
              <div className="flex items-center">
                <button aria-expanded={open} onClick={() => setAbierto(open ? null : p.id_proveedor)}
                  className="flex flex-1 cursor-pointer flex-wrap items-center gap-3.5 border-none bg-transparent py-3.5 pr-2 pl-[18px] text-left">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: PALETTE[idx % PALETTE.length] }} />
                  <span className="min-w-[200px] flex-1">
                    <span className="block font-display text-[15px] font-bold text-foreground">{p.nombre}</span>
                    <span className="text-xs text-muted-foreground">{[p.rif, [...(s?.categorias ?? [])].join(', '), p.ciudad].filter(Boolean).join(' · ') || 'Sin datos de contacto'}</span>
                  </span>
                  <span className="text-right"><span className="block text-[11px] text-muted-foreground">Comprado</span><span className="font-display font-bold text-foreground">{usd(comprado)}</span></span>
                  <span className="min-w-[90px] text-right"><span className="block text-[11px] text-muted-foreground">Deuda</span><span className={cx('font-display font-bold', deuda > 0 ? 'text-red-600' : 'text-success')}>{usd(deuda)}</span></span>
                  <ChevronDown size={18} className={cx('text-muted-foreground transition-transform', open && 'rotate-180')} />
                </button>
                <button aria-label={`Eliminar ${p.nombre}`} title="Eliminar proveedor" className="btn-icon mr-[18px] !h-8 !w-8 text-danger"
                  onClick={() => setEliminar(p)}>
                  <Trash2 size={14} />
                </button>
              </div>
              {open && (
                <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] gap-5 border-t border-border p-[18px]">
                  <div className="flex flex-col gap-2 text-[13px]">
                    <div className="font-display text-[13px] font-bold">Contacto</div>
                    <div>{p.contacto ?? '—'}</div>
                    {p.telefono && <div className="flex items-center gap-2"><Phone size={14} /> {p.telefono}</div>}
                    {p.correo && <div className="flex items-center gap-2"><Mail size={14} /> {p.correo}</div>}
                    {p.ciudad && <div className="flex items-center gap-2"><MapPin size={14} /> {p.ciudad}</div>}
                    <div className="mt-2 font-display text-[13px] font-bold">Condiciones</div>
                    <div>{p.condiciones ?? '—'}</div>
                    <div className="mt-2 font-display text-[13px] font-bold">Productos que suministra</div>
                    <div className="flex flex-wrap gap-1.5">
                      {s?.productos.length ? s.productos.map(x => <span key={x} className="rounded-full border border-border bg-muted px-2.5 py-0.5 text-xs">{x}</span>)
                        : <span className="text-xs text-muted-foreground">Ningún producto tiene asignado este proveedor.</span>}
                    </div>
                    <div className="mt-2 flex gap-2">
                      <button className="btn-muted !px-3 !py-1.5 text-xs" onClick={() => setEditar({ p })}><Pencil size={12} /> Editar</button>
                      <button className="btn-primary !px-3 !py-1.5 text-xs" onClick={() => setComprar(p)}><ShoppingBag size={12} /> Registrar compra</button>
                    </div>
                  </div>
                  <div>
                    <div className="mb-2 font-display text-[13px] font-bold">Historial de compras</div>
                    {compras.isLoading ? <Spinner /> : <HistorialCompras compras={cs} />}
                  </div>
                </div>
              )}
            </div>
          )
        })}

      {editar && <ProveedorModal proveedor={editar.p} onClose={() => setEditar(null)} />}
      {comprar && <CompraModal proveedor={comprar} onClose={() => setComprar(null)} />}
      {eliminar && (
        <EliminarProveedor proveedor={eliminar} onClose={() => setEliminar(null)}
          pendientes={comprasDe(eliminar.id_proveedor).filter(c => !c.pagado)} />
      )}
    </div>
  )
}
