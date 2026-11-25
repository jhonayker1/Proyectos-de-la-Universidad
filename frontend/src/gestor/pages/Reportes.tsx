/** Reportes operativos del gestor: movimientos de inventario, ventas por cajero, cuentas por
 * pagar y auditoría. No incluye utilidad ni márgenes (son exclusivos del administrador). */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { ChevronDown, FileSpreadsheet } from 'lucide-react'
import HistorialVentasDia from '@/admin/components/HistorialVentasDia'
import Auditoria from '@/admin/pages/Auditoria'
import { reportesApi } from '@/api/endpoints'
import { keys, useProductos } from '@/api/queries'
import type { MovimientoInventario } from '@/api/types'
import { Badge, EmptyState, QueryState, StatBox, Tabs, cx, errorText, useToast } from '@/shared/components/ui'
import { fmtFecha, fmtFechaHora, iso, parseLocal, todayIso } from '@/shared/lib/dates'
import { saveBlob } from '@/shared/lib/downloads'
import { usd } from '@/shared/lib/money'

const PESTANAS = ['Movimientos de inventario', 'Ventas por cajero', 'Cuentas por pagar', 'Auditoría'] as const
type Pestana = (typeof PESTANAS)[number]
const DESDE_URL: Record<string, Pestana> = { movimientos: PESTANAS[0], ventas: PESTANAS[1], pagar: PESTANAS[2], auditoria: PESTANAS[3] }
const TIPOS: Record<MovimientoInventario['tipo'], { etiqueta: string; tono: string }> = {
  entrada: { etiqueta: 'Entrada', tono: 'Disponible' },
  salida: { etiqueta: 'Salida', tono: 'Aceptado' },
  devolucion: { etiqueta: 'Devolución', tono: 'Bajo Stock' },
  ajuste: { etiqueta: 'Ajuste', tono: 'Inactivo' },
}

function Movimientos() {
  const hoy = new Date()
  const [desde, setDesde] = React.useState(iso(new Date(hoy.getFullYear(), hoy.getMonth(), 1)))
  const [hasta, setHasta] = React.useState(todayIso())
  const [idProducto, setIdProducto] = React.useState('')
  const [tipo, setTipo] = React.useState<'todos' | MovimientoInventario['tipo']>('todos')
  const [exportando, setExportando] = React.useState(false)
  const productos = useProductos()
  const toast = useToast()
  const kardex = useQuery({
    queryKey: [...keys.reportes, 'movimientos', desde, hasta, idProducto],
    queryFn: () => reportesApi.movimientos({ desde, hasta, id_producto: idProducto ? Number(idProducto) : undefined, limite: 5000 }),
  })
  const filas = (kardex.data?.movimientos ?? []).filter(m => tipo === 'todos' || m.tipo === tipo)
  const exportar = async () => {
    setExportando(true)
    try {
      const excel = await reportesApi.movimientosExcel({
        desde,
        hasta,
        id_producto: idProducto ? Number(idProducto) : undefined,
        tipo,
        limite: 5000,
      })
      await saveBlob(excel, `movimientos_${desde}_${hasta}.xlsx`)
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      setExportando(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <label><span className="label-caps">Desde</span><input type="date" className="input" value={desde} max={hasta} onChange={e => e.target.value && setDesde(e.target.value)} /></label>
        <label><span className="label-caps">Hasta</span><input type="date" className="input" value={hasta} min={desde} max={todayIso()} onChange={e => e.target.value && setHasta(e.target.value)} /></label>
        <label className="min-w-60 flex-1"><span className="label-caps">Producto</span>
          <select className="input" value={idProducto} onChange={e => setIdProducto(e.target.value)}>
            <option value="">Todos los productos</option>
            {productos.data?.map(p => <option key={p.id_producto} value={p.id_producto}>{p.sku} · {p.nombre}</option>)}
          </select></label>
        <label><span className="label-caps">Tipo</span>
          <select className="input" value={tipo} onChange={e => setTipo(e.target.value as typeof tipo)}>
            <option value="todos">Todos</option>
            {Object.entries(TIPOS).map(([k, v]) => <option key={k} value={k}>{v.etiqueta}</option>)}
          </select></label>
        <button className="btn-muted" disabled={filas.length === 0 || exportando} onClick={exportar}>
          <FileSpreadsheet size={14} /> {exportando ? 'Exportando…' : 'Descarga Excel'}
        </button>
      </div>
      <QueryState query={kardex} label="Cargando movimientos...">
        {k => (
          <>
            <div className="grid grid-cols-2 gap-3.5 md:grid-cols-4">
              <StatBox className="!bg-card" label="Entradas (compras)" value={`+${k.entradas}`} color="#10b981" />
              <StatBox className="!bg-card" label="Salidas (ventas)" value={`−${k.salidas}`} color="#4f46e5" />
              <StatBox className="!bg-card" label="Devoluciones (anulaciones)" value={`+${k.devoluciones}`} color="#f59e0b" />
              <StatBox className="!bg-card" label="Ajustes (neto)" value={k.ajustes > 0 ? `+${k.ajustes}` : k.ajustes} color="#06b6d4" />
            </div>
            <div className="card overflow-hidden">
              {filas.length === 0 ? <EmptyState title="Sin movimientos en el período." /> : (
                <div className="max-h-[560px] overflow-auto">
                  <table className="w-full min-w-[820px] border-collapse text-[13px]">
                    <thead className="sticky top-0"><tr className="border-b-2 border-border bg-muted">{['Fecha', 'Tipo', 'Producto', 'Cantidad', 'Referencia', 'Usuario'].map(h => <th key={h} className="th">{h}</th>)}</tr></thead>
                    <tbody>
                      {filas.map((m, i) => (
                        <tr key={i} className={`border-b border-border ${i % 2 ? 'bg-muted' : 'bg-card'}`}>
                          <td className="td font-mono text-xs whitespace-nowrap text-muted-foreground">{fmtFechaHora(m.fecha)}</td>
                          <td className="td"><Badge tone={TIPOS[m.tipo].tono}>{TIPOS[m.tipo].etiqueta}</Badge></td>
                          <td className="td"><div className="font-semibold">{m.producto}</div><div className="text-[11px] text-muted-foreground">{m.sku}</div></td>
                          <td className={cx('td font-bold', m.cantidad >= 0 ? 'text-success' : 'text-danger')}>{m.cantidad > 0 ? `+${m.cantidad}` : m.cantidad}</td>
                          <td className="td text-xs">{m.referencia}{m.detalle && <div className="text-muted-foreground">{m.detalle}</div>}</td>
                          <td className="td text-xs text-muted-foreground">{m.usuario ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {k.truncado && <div className="border-t border-border px-4 py-2 text-[11px] text-muted-foreground">Se muestran los 5000 más recientes; acote las fechas para ver el resto.</div>}
            </div>
          </>
        )}
      </QueryState>
    </div>
  )
}

function VentasPorCajero() {
  const [dia, setDia] = React.useState(todayIso())
  const [cajero, setCajero] = React.useState<number | undefined>(undefined)
  const reporte = useQuery({ queryKey: [...keys.reportes, 'ventas-dia', dia], queryFn: () => reportesApi.ventasDia(dia) })
  return (
    <div className="flex flex-col gap-4">
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <label><span className="label-caps">Día</span>
          <input type="date" className="input" value={dia} max={todayIso()} onChange={e => { if (e.target.value) { setDia(e.target.value); setCajero(undefined) } }} /></label>
        <p className="m-0 flex-1 text-xs text-muted-foreground">El turno es la jornada de cada cajero. Seleccione un cajero para ver solo sus ventas.</p>
      </div>
      <QueryState query={reporte}>
        {r => (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[340px_1fr]">
            <div className="card overflow-hidden">
              <div className="grid grid-cols-2 gap-2.5 p-4">
                <StatBox label="Ventas" value={r.cantidad_ventas} color="#10b981" />
                <StatBox label="Anuladas" value={r.ventas_anuladas} color={r.ventas_anuladas ? '#dc2626' : undefined} />
              </div>
              <button onClick={() => setCajero(undefined)}
                className={cx('flex w-full cursor-pointer items-center justify-between border-0 border-t border-border px-4 py-3 text-left text-[13px]', cajero === undefined ? 'bg-primary/10 font-bold text-primary' : 'bg-card')}>
                Todos los cajeros <span>{usd(r.monto_total_usd)}</span>
              </button>
              {r.por_usuario.length === 0 ? <EmptyState title="Sin ventas ese día." /> : r.por_usuario.map(u => (
                <button key={u.id_usuario} onClick={() => setCajero(u.id_usuario)}
                  className={cx('flex w-full cursor-pointer items-center justify-between gap-2 border-0 border-t border-border px-4 py-3 text-left text-[13px]', cajero === u.id_usuario ? 'bg-primary/10 font-bold text-primary' : 'bg-card hover:bg-[#f0f0ff]')}>
                  <span><span className="block font-semibold">{u.nombre_completo}</span><span className="text-[11px] text-muted-foreground">{u.cantidad_ventas} venta(s)</span></span>
                  <span className="font-display font-bold">{usd(u.monto_total_usd)}</span>
                </button>
              ))}
            </div>
            <HistorialVentasDia key={`${dia}-${cajero ?? 'todos'}`} dia={dia} idUsuario={cajero} />
          </div>
        )}
      </QueryState>
    </div>
  )
}

function CuentasPorPagar() {
  const cuentas = useQuery({ queryKey: [...keys.reportes, 'cuentas-por-pagar'], queryFn: reportesApi.cuentasPorPagar })
  const [abierto, setAbierto] = React.useState<number | null>(null)
  return (
    <QueryState query={cuentas}>
      {c => (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-[repeat(auto-fit,minmax(190px,1fr))] gap-3.5">
            <StatBox className="!bg-card" label="Total por pagar" value={usd(c.total_usd)} color={c.compras ? '#dc2626' : '#10b981'} />
            <StatBox className="!bg-card" label="Compras pendientes" value={c.compras} color="#4f46e5" />
            <StatBox className="!bg-card" label="Proveedores con deuda" value={c.proveedores.length} color="#06b6d4" />
          </div>
          <p className="m-0 text-xs text-muted-foreground">Registrar los pagos es tarea del administrador; aquí se consulta lo pendiente.</p>
          {c.proveedores.length === 0 ? <div className="card"><EmptyState title="No hay compras pendientes de pago." /></div> : c.proveedores.map(p => {
            const open = abierto === p.id_proveedor
            return (
              <div key={p.id_proveedor} className="card overflow-hidden !rounded-[14px]">
                <button aria-expanded={open} onClick={() => setAbierto(open ? null : p.id_proveedor)}
                  className="flex w-full cursor-pointer flex-wrap items-center gap-3.5 border-none bg-transparent px-[18px] py-3.5 text-left">
                  <span className="min-w-[200px] flex-1">
                    <span className="block font-display text-[15px] font-bold text-foreground">{p.proveedor}</span>
                    <span className="text-xs text-muted-foreground">{[p.rif, p.telefono, `desde ${fmtFecha(parseLocal(p.mas_antigua))}`].filter(Boolean).join(' · ')}</span>
                  </span>
                  <span className="text-right"><span className="block text-[11px] text-muted-foreground">{p.compras} compra(s)</span><span className="font-display font-bold text-red-600">{usd(p.monto_usd)}</span></span>
                  <ChevronDown size={18} className={cx('text-muted-foreground transition-transform', open && 'rotate-180')} />
                </button>
                {open && (
                  <div className="overflow-x-auto">
                    <table className="w-full border-collapse border-t border-border text-[13px]">
                      <thead><tr className="bg-muted">{['Factura', 'Fecha', 'Antigüedad', 'Monto'].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
                      <tbody>
                        {p.detalle.map(d => (
                          <tr key={d.id_compra} className="border-t border-border">
                            <td className="td !py-2 font-semibold">{d.numero_factura ?? `Compra #${d.id_compra}`}</td>
                            <td className="td !py-2 text-muted-foreground">{fmtFecha(parseLocal(d.fecha))}</td>
                            <td className={cx('td !py-2', d.dias > 30 ? 'font-semibold text-danger' : 'text-muted-foreground')}>{d.dias} día(s)</td>
                            <td className="td !py-2 font-bold">{usd(d.monto_usd)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </QueryState>
  )
}

export default function Reportes() {
  const [params, setParams] = useSearchParams()
  const pestana = DESDE_URL[params.get('tab') ?? ''] ?? PESTANAS[0]
  const cambiar = (p: Pestana) => setParams({ tab: Object.keys(DESDE_URL).find(k => DESDE_URL[k] === p)! }, { replace: true })
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 pb-6">
      <Tabs value={pestana} options={PESTANAS} onChange={cambiar} />
      {pestana === 'Movimientos de inventario' && <Movimientos />}
      {pestana === 'Ventas por cajero' && <VentasPorCajero />}
      {pestana === 'Cuentas por pagar' && <CuentasPorPagar />}
      {pestana === 'Auditoría' && <Auditoria />}
    </div>
  )
}
