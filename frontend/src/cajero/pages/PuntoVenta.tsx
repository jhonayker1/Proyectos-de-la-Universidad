import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Download, Package, PowerOff, Search, ShoppingCart, Trash2 } from 'lucide-react'
import { ventasApi } from '@/api/endpoints'
import { keys, useApiMutation, useMonedas } from '@/api/queries'
import type { Venta } from '@/api/types'
import { useAuth, useCurrentUser } from '@/auth/AuthContext'
import { useTasas } from '@/shared/components/productos'
import { EmptyState, ErrorBanner, Field, Modal, QueryState, StatBox, cx, errorText, useToast } from '@/shared/components/ui'
import { fmtHora, todayIso } from '@/shared/lib/dates'
import { fmtMoneda, fmtTasa, usd } from '@/shared/lib/money'
import { pdfTicket } from '@/shared/lib/pdf'
import { useCart } from '../CartContext'

function FinalizarModal({ onClose, onDone }: { onClose: () => void; onDone: (v: Venta) => void }) {
  const cart = useCart()
  const monedas = useMonedas()
  const { tasas } = useTasas()
  const [moneda, setMoneda] = React.useState('USD')
  const [referencia, setReferencia] = React.useState('')
  const tasa = moneda === 'USD' ? 1 : tasas[moneda as 'VES' | 'COP'] ?? null
  const vender = useApiMutation(() => ventasApi.create({
    codigo_moneda_pago: moneda,
    referencia_pago: referencia.trim() || null,
    detalles: cart.lineas.map(l => ({ id_producto: l.producto.id_producto, cantidad: l.cantidad })),
  }), [keys.ventas, keys.productos], v => { cart.vaciar(); onDone(v) })

  return (
    <Modal title="Finalizar venta" subtitle={`${cart.unidades} artículo(s) · ${usd(cart.totalUsd)}`} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose} disabled={vender.isPending}>Cancelar</button>
      <button className="btn-success" disabled={tasa === null || vender.isPending} onClick={() => vender.mutate(undefined)}>
        <ShoppingCart size={14} /> {vender.isPending ? 'Registrando...' : 'Confirmar venta'}
      </button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Moneda de pago">
          <div className="grid grid-cols-3 gap-2">
            {(monedas.data ?? []).map(m => {
              const c = m.codigo.trim()
              return (
                <button key={c} type="button" onClick={() => setMoneda(c)}
                  className={cx('btn', moneda === c ? 'bg-primary text-white' : 'border border-border bg-muted text-foreground')}>
                  {m.simbolo ?? ''} {c}
                </button>
              )
            })}
          </div>
        </Field>
        <div className="rounded-xl border border-border bg-muted px-4 py-3">
          <div className="text-[11px] font-semibold text-muted-foreground uppercase">Total a cobrar</div>
          <div className="font-display text-[28px] font-extrabold text-primary">
            {tasa === null ? 'Sin tasa registrada' : fmtMoneda(cart.totalUsd * tasa, moneda)}
          </div>
          {moneda !== 'USD' && tasa !== null && (
            <div className="text-xs text-muted-foreground">{usd(cart.totalUsd)} × {fmtTasa(tasa, moneda)} {moneda}/USD · el monto exacto lo confirma el servidor</div>
          )}
          {tasa === null && <div className="text-xs text-danger">Un administrador debe registrar la tasa de {moneda} antes de cobrar en esa moneda.</div>}
        </div>
        <Field label="Referencia de pago (opcional)" hint="N.º de pago móvil, transferencia o punto de venta.">
          <input className="input" maxLength={50} value={referencia} onChange={e => setReferencia(e.target.value)} />
        </Field>
        {vender.error && <ErrorBanner error={vender.error} />}
      </div>
    </Modal>
  )
}

function CierreTurno({ onClose }: { onClose: () => void }) {
  const { logout } = useAuth()
  const resumen = useQuery({ queryKey: [...keys.ventas, 'mi-resumen', todayIso()], queryFn: () => ventasApi.miResumen() })
  return (
    <Modal title="Cerrar turno" subtitle="Corte de caja del día" onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Seguir vendiendo</button>
      <button className="btn-danger" onClick={() => logout('Turno cerrado. ¡Hasta luego!')}><PowerOff size={14} /> Cerrar turno y salir</button>
    </>}>
      <QueryState query={resumen}>
        {r => (
          <div className="flex flex-col gap-3">
            <div className="grid grid-cols-3 gap-2.5">
              <StatBox label="Ventas" value={r.cantidad_ventas} color="#10b981" />
              <StatBox label="Artículos" value={r.articulos_vendidos} color="#4f46e5" />
              <StatBox label="Total USD" value={usd(r.monto_total_usd)} color="#06b6d4" />
            </div>
            <div className="rounded-xl border border-border">
              <div className="border-b border-border bg-muted px-3 py-2 text-[11px] font-semibold text-muted-foreground">Cobrado por moneda</div>
              {r.por_moneda.length === 0 ? <div className="p-3 text-xs text-muted-foreground">Sin cobros hoy.</div> : r.por_moneda.map(m => (
                <div key={m.codigo_moneda} className="flex justify-between border-b border-border px-3 py-2 text-[13px] last:border-b-0">
                  <span>{m.codigo_moneda} · {m.cantidad_ventas} venta(s)</span>
                  <b>{fmtMoneda(m.monto_total_moneda, m.codigo_moneda)}</b>
                </div>
              ))}
            </div>
          </div>
        )}
      </QueryState>
    </Modal>
  )
}

export default function PuntoVenta() {
  const user = useCurrentUser()
  const toast = useToast()
  const cart = useCart()
  const { tasas } = useTasas()
  const hoy = todayIso()
  const resumen = useQuery({ queryKey: [...keys.ventas, 'mi-resumen', hoy], queryFn: () => ventasApi.miResumen() })
  const ventas = useQuery({ queryKey: [...keys.ventas, 'dia', hoy], queryFn: () => ventasApi.list({ dia: hoy, limite: 500 }) })
  const [buscar, setBuscar] = React.useState('')
  const [finalizar, setFinalizar] = React.useState(false)
  const [cierre, setCierre] = React.useState(false)
  const [ultima, setUltima] = React.useState<Venta | null>(null)

  const imprimir = async (v: Venta) => {
    try { await pdfTicket(v, user.nombre_completo) } catch (e) { toast(errorText(e), 'error') }
  }
  const filtradas = (ventas.data ?? []).filter(v => {
    const q = buscar.trim().toLowerCase()
    return !q || v.numero_factura.toLowerCase().includes(q) || v.detalles.some(d => d.nombre_producto_snapshot.toLowerCase().includes(q))
  })

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex shrink-0 flex-wrap gap-4">
        <div className="card flex min-w-[320px] flex-1 flex-col gap-4 px-[22px] py-[18px]">
          <div className="flex items-center justify-between">
            <h3 className="m-0 text-[15px] font-bold">Panel de cajero</h3>
            <span className="rounded-full bg-success/15 px-3 py-0.5 text-[11px] font-bold text-success">Turno activo</span>
          </div>
          <div className="flex flex-wrap items-center gap-5">
            <div className="flex shrink-0 items-center gap-3.5">
              <div className="flex h-[54px] w-[54px] items-center justify-center rounded-full bg-primary font-display text-[22px] font-extrabold text-white">
                {user.nombre_completo.charAt(0).toUpperCase()}
              </div>
              <div>
                <div className="font-display text-base font-bold">{user.nombre_completo}</div>
                <div className="mt-0.5 text-xs text-muted-foreground">{user.correo}</div>
                <span className="mt-1 inline-block rounded-full bg-primary/10 px-2.5 py-0.5 text-[11px] font-bold text-primary">Cajero</span>
              </div>
            </div>
            <div className="h-[52px] w-px shrink-0 bg-border" />
            <div className="flex gap-3">
              <StatBox className="min-w-[120px] !py-2.5" label="Ventas hoy" value={resumen.data ? usd(resumen.data.monto_total_usd) : '…'} color="var(--primary)" />
              <StatBox className="min-w-[120px] !py-2.5" label="Pedidos procesados" value={resumen.data?.cantidad_ventas ?? '…'} color="#10b981" />
            </div>
            <div className="h-[52px] w-px shrink-0 bg-border" />
            <button className="btn-danger shrink-0" onClick={() => setCierre(true)}><PowerOff size={14} /> Cerrar turno</button>
          </div>
        </div>
        <div className="flex w-[180px] shrink-0 flex-col gap-2.5">
          {([['COP', 'Peso COP / USD', 'text-accent'], ['VES', 'Bolívares / USD', 'text-primary']] as const).map(([c, label, color]) => (
            <div key={c} className="card flex flex-1 flex-col justify-center px-[18px] py-3.5">
              <div className="label-caps">{label}</div>
              <div className={`font-display text-[22px] font-extrabold ${color}`}>{tasas[c] === null ? 'Sin tasa' : `${c === 'VES' ? 'Bs.' : 'COP'} ${fmtTasa(tasas[c]!, c)}`}</div>
            </div>
          ))}
        </div>
      </div>

      {ultima && (
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-success/40 bg-success/10 px-4 py-3 text-[13px]">
          <span className="font-semibold text-success">Venta {ultima.numero_factura} registrada · {fmtMoneda(ultima.monto_total_moneda, ultima.codigo_moneda_pago)}</span>
          <button className="btn-success !px-3 !py-1 text-xs" onClick={() => imprimir(ultima)}><Download size={12} /> Descargar ticket</button>
          <button className="ml-auto cursor-pointer border-none bg-transparent text-xs text-muted-foreground" onClick={() => setUltima(null)}>Cerrar</button>
        </div>
      )}

      <div className="grid min-h-[420px] flex-1 grid-cols-1 gap-4 xl:grid-cols-[1.6fr_1fr]">
        <div className="card flex min-h-0 flex-col">
          <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2.5">
              <h3 className="m-0 text-sm font-bold">Crear ticket de venta</h3>
              <span className={cx('rounded-full px-2.5 py-0.5 text-[11px] font-bold', cart.lineas.length ? 'bg-success/15 text-success' : 'bg-muted text-muted-foreground')}>
                {cart.lineas.length} ítem{cart.lineas.length !== 1 && 's'}
              </span>
            </div>
            <button className="btn-success !px-4 !py-1.5" disabled={cart.lineas.length === 0} onClick={() => setFinalizar(true)}>
              <ShoppingCart size={13} /> Finalizar
            </button>
          </div>
          <div className="flex flex-1 flex-col overflow-hidden">
            {cart.lineas.length === 0 ? (
              <Link to="/cajero/inventario" className="m-4 flex flex-1 flex-col items-center justify-center gap-2.5 rounded-xl border-2 border-dashed border-border text-muted-foreground no-underline transition-all hover:border-primary hover:bg-primary/5">
                <Package size={28} strokeWidth={1.3} className="opacity-40" />
                <div className="text-center">
                  <div className="text-[13px] font-semibold">No hay productos en el ticket</div>
                  <div className="mt-1 text-xs font-semibold text-primary underline">Ir al inventario →</div>
                </div>
              </Link>
            ) : (
              <div className="flex-1 overflow-y-auto">
                <table className="w-full border-collapse text-[13px]">
                  <thead><tr className="border-b border-border bg-muted">{['Producto', 'Cant.', 'Precio unit.', 'Subtotal', ''].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
                  <tbody>
                    {cart.lineas.map(({ producto: p, cantidad, subtotal }, i) => (
                      <tr key={p.id_producto} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                        <td className="td !py-2.5 font-semibold">{p.nombre}<div className="text-[11px] font-normal text-muted-foreground">{p.sku} · stock {p.stock_actual}</div></td>
                        <td className="td !py-2.5">
                          <div className="flex items-center gap-1.5">
                            <button aria-label="Restar" className="btn-icon !h-[22px] !w-[22px] font-bold" disabled={cantidad <= 1} onClick={() => cart.cambiar(p.id_producto, cantidad - 1)}>−</button>
                            <span className="min-w-5 text-center font-bold">{cantidad}</span>
                            <button aria-label="Sumar" className="btn-icon !h-[22px] !w-[22px] !border-primary !bg-primary font-bold !text-white" disabled={cantidad >= p.stock_actual}
                              onClick={() => cart.cambiar(p.id_producto, cantidad + 1)}>+</button>
                          </div>
                        </td>
                        <td className="td !py-2.5 text-muted-foreground">{usd(p.precio_usd)}</td>
                        <td className="td !py-2.5 font-bold text-primary">{usd(subtotal)}</td>
                        <td className="td !py-2.5"><button aria-label={`Quitar ${p.nombre}`} className="btn-icon border-none bg-transparent text-danger" onClick={() => cart.quitar(p.id_producto)}>✕</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <div className="flex shrink-0 items-center justify-between border-t border-border px-4 py-3.5">
            <div className="flex items-center gap-7">
              <div>
                <div className="label-caps !mb-0">Total USD</div>
                <div className="font-display text-2xl leading-tight font-extrabold text-primary">{usd(cart.totalUsd)}</div>
              </div>
              {tasas.VES !== null && (
                <div>
                  <div className="label-caps !mb-0">Total Bs.</div>
                  <div className="font-display text-2xl leading-tight font-extrabold text-[#6366f1]">{fmtMoneda(cart.totalUsd * tasas.VES, 'VES')}</div>
                </div>
              )}
            </div>
            <button className="btn-danger !rounded-xl !px-6 !py-2.5 !text-sm" disabled={cart.lineas.length === 0} onClick={cart.vaciar}><Trash2 size={15} /> Borrar</button>
          </div>
        </div>

        <div className="card flex min-h-0 flex-col overflow-hidden">
          <div className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div>
              <h3 className="m-0 text-sm font-bold">Historial de ventas</h3>
              <p className="mt-0.5 mb-0 text-[11px] text-muted-foreground">{ventas.data?.length ?? 0} transacciones hoy</p>
            </div>
            <div className="relative shrink-0">
              <Search size={14} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground" />
              <input aria-label="Buscar venta" className="input !w-40 !rounded-xl !py-1.5 !pl-8 text-xs" placeholder="Buscar venta..." value={buscar} onChange={e => setBuscar(e.target.value)} />
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-3.5">
            <QueryState query={ventas}>
              {() => filtradas.length === 0 ? <EmptyState title="No se encontraron ventas." /> : (
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {filtradas.map((v, i) => (
                    <button key={v.id_venta} onClick={() => imprimir(v)} title="Descargar ticket"
                      className={cx('flex cursor-pointer flex-col gap-1.5 rounded-xl border px-3.5 py-3 text-left', v.estado === 'Anulada' ? 'border-danger/30 bg-danger/5 opacity-70' : i === 0 ? 'border-success/30 bg-success/5' : 'border-border bg-muted')}>
                      <div className="flex items-start justify-between gap-1.5">
                        <span className="text-xs leading-snug font-bold">{v.detalles.map(d => d.nombre_producto_snapshot).join(', ')}</span>
                        <span className="shrink-0 font-display text-xs font-extrabold text-primary">{usd(v.monto_total_usd)}</span>
                      </div>
                      <span className="text-[11px] text-muted-foreground">{v.numero_factura} · {v.detalles.reduce((s, d) => s + d.cantidad, 0)} artículo(s){v.estado === 'Anulada' && ' · ANULADA'}</span>
                      <div className="flex items-center justify-between">
                        <span className="rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-bold text-[#6366f1]">{fmtMoneda(v.monto_total_moneda, v.codigo_moneda_pago)}</span>
                        <span className="text-[10px] font-medium text-muted-foreground">{fmtHora(v.fecha_venta)}</span>
                      </div>
                    </button>
                  ))}
                </div>
              )}
            </QueryState>
          </div>
        </div>
      </div>

      {finalizar && <FinalizarModal onClose={() => setFinalizar(false)} onDone={v => { setFinalizar(false); setUltima(v); toast(`Venta ${v.numero_factura} registrada.`) }} />}
      {cierre && <CierreTurno onClose={() => setCierre(false)} />}
    </div>
  )
}
