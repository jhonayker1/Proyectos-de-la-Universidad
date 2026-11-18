/** Entradas de mercancía (compras a proveedores), ajustes de stock justificados y facturas escaneadas. */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { PackagePlus, SlidersHorizontal } from 'lucide-react'
import AjusteStockModal from '@/admin/components/AjusteStockModal'
import Facturas from '@/admin/components/Facturas'
import { CompraModal } from '@/admin/pages/Proveedores'
import { comprasApi, productosApi } from '@/api/endpoints'
import { keys, useProductosAdmin, useProveedores } from '@/api/queries'
import type { ProductoAdmin, Proveedor } from '@/api/types'
import { Badge, EmptyState, Field, Modal, QueryState, StatBox, Tabs, cx } from '@/shared/components/ui'
import { fmtFecha, fmtFechaHora, parseLocal } from '@/shared/lib/dates'
import { usd } from '@/shared/lib/money'

const PESTANAS = ['Compras', 'Ajustes de stock', 'Facturas escaneadas'] as const
type Pestana = (typeof PESTANAS)[number]

function ElegirProveedor({ onElegir, onClose }: { onElegir: (p: Proveedor) => void; onClose: () => void }) {
  const proveedores = useProveedores()
  const [id, setId] = React.useState('')
  const elegido = proveedores.data?.find(p => String(p.id_proveedor) === id)
  return (
    <Modal title="Registrar entrada de mercancía" subtitle="Elija el proveedor de la compra." onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={!elegido} onClick={() => elegido && onElegir(elegido)}>Continuar</button>
    </>}>
      <Field label="Proveedor">
        <select className="input" autoFocus value={id} onChange={e => setId(e.target.value)}>
          <option value="">Seleccione…</option>
          {proveedores.data?.map(p => <option key={p.id_proveedor} value={p.id_proveedor}>{p.nombre}{p.rif ? ` · ${p.rif}` : ''}</option>)}
        </select>
      </Field>
    </Modal>
  )
}

function ElegirProducto({ onElegir, onClose }: { onElegir: (p: ProductoAdmin) => void; onClose: () => void }) {
  const productos = useProductosAdmin()
  const [q, setQ] = React.useState('')
  const lista = (productos.data ?? []).filter(p => `${p.sku} ${p.nombre}`.toLowerCase().includes(q.trim().toLowerCase())).slice(0, 40)
  return (
    <Modal title="Ajustar stock" subtitle="Busque el producto a ajustar." onClose={onClose} width="max-w-lg">
      <input aria-label="Buscar producto" className="input" autoFocus placeholder="SKU o nombre" value={q} onChange={e => setQ(e.target.value)} />
      <div className="mt-3 max-h-80 overflow-y-auto rounded-xl border border-border">
        {lista.length === 0 ? <EmptyState title="Sin resultados." /> : lista.map(p => (
          <button key={p.id_producto} onClick={() => onElegir(p)}
            className="flex w-full cursor-pointer items-center gap-3 border-0 border-b border-border bg-card px-3 py-2.5 text-left text-[13px] last:border-b-0 hover:bg-[#f0f0ff]">
            <span className="w-20 shrink-0 text-xs text-muted-foreground">{p.sku}</span>
            <span className="flex-1 font-semibold">{p.nombre}</span>
            <span className="text-xs">stock <b>{p.stock_actual}</b></span>
          </button>
        ))}
      </div>
    </Modal>
  )
}

export default function Entradas() {
  const [params, setParams] = useSearchParams()
  const [pestana, setPestana] = React.useState<Pestana>('Compras')
  const [elegirProveedor, setElegirProveedor] = React.useState(Boolean(params.get('nueva')))
  const [proveedor, setProveedor] = React.useState<Proveedor | null>(null)
  const [elegirProducto, setElegirProducto] = React.useState(false)
  const [ajustar, setAjustar] = React.useState<ProductoAdmin | null>(null)
  const compras = useQuery({ queryKey: [...keys.compras, 'recientes'], queryFn: () => comprasApi.list({ limite: 200 }) })
  const ajustes = useQuery({ queryKey: [...keys.ajustes, 'recientes'], queryFn: () => productosApi.ajustes({ limite: 300 }) })

  const pendientes = (compras.data ?? []).filter(c => !c.pagado)
  const unidades = (compras.data ?? []).reduce((t, c) => t + c.detalles.reduce((s, d) => s + d.cantidad, 0), 0)
  const cerrarProveedor = () => { setElegirProveedor(false); if (params.get('nueva')) setParams({}, { replace: true }) }

  return (
    <div className="flex flex-col gap-4 pb-6">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3.5">
        <StatBox className="!bg-card" label="Compras registradas (últimas 200)" value={compras.data?.length ?? '…'} color="#4f46e5" />
        <StatBox className="!bg-card" label="Unidades ingresadas" value={unidades} color="#10b981" />
        <StatBox className="!bg-card" label="Pendientes de pago" value={`${pendientes.length} · ${usd(pendientes.reduce((t, c) => t + Number(c.monto_usd), 0))}`} color={pendientes.length ? '#dc2626' : undefined} />
        <StatBox className="!bg-card" label="Ajustes de stock" value={ajustes.data?.length ?? '…'} color="#06b6d4" />
      </div>

      <div className="flex flex-wrap items-center gap-2.5">
        <Tabs value={pestana} options={PESTANAS} onChange={setPestana} />
        <div className="ml-auto flex gap-2">
          <button className="btn-muted" onClick={() => setElegirProducto(true)}><SlidersHorizontal size={14} /> Ajustar stock</button>
          <button className="btn-primary" onClick={() => setElegirProveedor(true)}><PackagePlus size={14} /> Registrar compra</button>
        </div>
      </div>

      {pestana === 'Compras' && (
        <div className="card overflow-hidden">
          <QueryState query={compras} label="Cargando compras...">
            {data => data.length === 0 ? <EmptyState title="No hay compras registradas." /> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-[13px]">
                  <thead><tr className="border-b-2 border-border bg-muted">{['Fecha', 'Proveedor', 'Factura', 'Productos', 'Monto', 'Pago'].map(h => <th key={h} className="th">{h}</th>)}</tr></thead>
                  <tbody>
                    {data.map((c, i) => (
                      <tr key={c.id_compra} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                        <td className="td whitespace-nowrap text-muted-foreground">{fmtFecha(parseLocal(c.fecha))}</td>
                        <td className="td font-semibold">{c.nombre_proveedor}</td>
                        <td className="td text-muted-foreground">{c.numero_factura ?? '—'}</td>
                        <td className="td text-xs">{c.detalles.map(d => <div key={d.id_detalle_compra}><b>{d.cantidad}×</b> {d.nombre_producto}</div>)}</td>
                        <td className="td font-bold whitespace-nowrap">{usd(c.monto_usd)}</td>
                        <td className="td"><Badge tone={c.pagado ? 'Pagada' : 'Pendiente'}>{c.pagado ? 'Pagada' : 'Pendiente'}</Badge></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryState>
        </div>
      )}

      {pestana === 'Ajustes de stock' && (
        <div className="card overflow-hidden">
          <QueryState query={ajustes} label="Cargando ajustes...">
            {data => data.length === 0 ? <EmptyState title="No hay ajustes de stock registrados." hint="Use “Ajustar stock” para corregir el inventario con un motivo." /> : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[760px] border-collapse text-[13px]">
                  <thead><tr className="border-b-2 border-border bg-muted">{['Fecha', 'Producto', 'Cambio', 'Stock', 'Motivo', 'Observación', 'Usuario'].map(h => <th key={h} className="th">{h}</th>)}</tr></thead>
                  <tbody>
                    {data.map((a, i) => (
                      <tr key={a.id_ajuste} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                        <td className="td font-mono text-xs whitespace-nowrap text-muted-foreground">{fmtFechaHora(a.fecha)}</td>
                        <td className="td"><div className="font-semibold">{a.nombre_producto}</div><div className="text-[11px] text-muted-foreground">{a.sku}</div></td>
                        <td className={cx('td font-bold', a.cantidad >= 0 ? 'text-success' : 'text-danger')}>{a.cantidad > 0 ? `+${a.cantidad}` : a.cantidad}</td>
                        <td className="td whitespace-nowrap text-muted-foreground">{a.stock_anterior} → <b className="text-foreground">{a.stock_nuevo}</b></td>
                        <td className="td"><Badge>{a.motivo_etiqueta}</Badge></td>
                        <td className="td text-xs">{a.observacion}</td>
                        <td className="td text-xs text-muted-foreground">{a.nombre_usuario}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </QueryState>
        </div>
      )}

      {pestana === 'Facturas escaneadas' && <Facturas />}

      {elegirProveedor && <ElegirProveedor onClose={cerrarProveedor} onElegir={p => { cerrarProveedor(); setProveedor(p) }} />}
      {proveedor && <CompraModal proveedor={proveedor} onClose={() => setProveedor(null)} />}
      {elegirProducto && <ElegirProducto onClose={() => setElegirProducto(false)} onElegir={p => { setElegirProducto(false); setAjustar(p) }} />}
      {ajustar && <AjusteStockModal producto={ajustar} onClose={() => setAjustar(null)} />}
    </div>
  )
}
