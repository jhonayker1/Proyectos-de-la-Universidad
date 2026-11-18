/** Ajuste de stock justificado: sumar, restar o fijar el conteo físico, con motivo obligatorio. */
import React from 'react'
import { productosApi } from '@/api/endpoints'
import { keys, useApiMutation } from '@/api/queries'
import type { AjusteStockInput, MotivoAjuste, ProductoAdmin } from '@/api/types'
import { ErrorBanner, Field, Modal, cx, useToast } from '@/shared/components/ui'

const TIPOS: { clave: AjusteStockInput['tipo']; etiqueta: string; ayuda: string }[] = [
  { clave: 'sumar', etiqueta: 'Sumar', ayuda: 'Unidades que entran (devolución, hallazgo).' },
  { clave: 'restar', etiqueta: 'Restar', ayuda: 'Unidades que salen (daño, merma, pérdida).' },
  { clave: 'conteo', etiqueta: 'Conteo físico', ayuda: 'El stock real contado en el almacén.' },
]
const MOTIVOS: { clave: MotivoAjuste; etiqueta: string }[] = [
  { clave: 'conteo', etiqueta: 'Conteo físico' },
  { clave: 'merma', etiqueta: 'Daño o merma' },
  { clave: 'devolucion', etiqueta: 'Devolución' },
  { clave: 'otro', etiqueta: 'Otro' },
]

export default function AjusteStockModal({ producto, onClose }: { producto: ProductoAdmin; onClose: () => void }) {
  const toast = useToast()
  const [tipo, setTipo] = React.useState<AjusteStockInput['tipo']>('restar')
  const [cantidad, setCantidad] = React.useState('')
  const [motivo, setMotivo] = React.useState<MotivoAjuste>('merma')
  const [observacion, setObservacion] = React.useState('')

  const n = Number(cantidad)
  const valido = cantidad.trim() !== '' && Number.isInteger(n) && n >= 0 && (tipo === 'conteo' || n > 0)
  const nuevo = !valido ? null : tipo === 'conteo' ? n : tipo === 'sumar' ? producto.stock_actual + n : producto.stock_actual - n
  const errores = [
    !valido && 'cantidad',
    nuevo !== null && nuevo < 0 && 'el stock no puede quedar negativo',
    nuevo === producto.stock_actual && 'el stock no cambia',
    observacion.trim().length < 3 && 'explique el motivo',
  ].filter(Boolean) as string[]

  const guardar = useApiMutation(() => productosApi.ajustar(producto.id_producto, {
    tipo, cantidad: n, motivo, observacion: observacion.trim(),
  }), [keys.productos, keys.reportes, keys.ajustes], a => {
    toast(`Stock de ${a.nombre_producto}: ${a.stock_anterior} → ${a.stock_nuevo}.`)
    onClose()
  })

  return (
    <Modal title="Ajustar stock" subtitle={`${producto.sku} · ${producto.nombre} · stock actual ${producto.stock_actual}`} onClose={onClose} footer={<>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      <button className="btn-primary" disabled={errores.length > 0 || guardar.isPending} title={errores.length ? `Revise: ${errores.join(', ')}` : undefined}
        onClick={() => guardar.mutate(undefined)}>
        {guardar.isPending ? 'Guardando...' : 'Registrar ajuste'}
      </button>
    </>}>
      <div className="flex flex-col gap-3.5">
        <div className="grid grid-cols-3 gap-2" role="radiogroup" aria-label="Tipo de ajuste">
          {TIPOS.map(t => (
            <button key={t.clave} type="button" role="radio" aria-checked={tipo === t.clave}
              onClick={() => { setTipo(t.clave); if (t.clave === 'conteo') setMotivo('conteo') }}
              className={cx('btn !px-2', tipo === t.clave ? 'bg-primary text-white' : 'border border-border bg-muted text-foreground')}>
              {t.etiqueta}
            </button>
          ))}
        </div>
        <div className="text-[11px] text-muted-foreground">{TIPOS.find(t => t.clave === tipo)!.ayuda}</div>
        <div className="grid grid-cols-2 gap-3.5">
          <Field label={tipo === 'conteo' ? 'Stock contado' : 'Cantidad'}>
            <input className="input" type="number" min={0} value={cantidad} autoFocus onChange={e => setCantidad(e.target.value)} />
          </Field>
          <Field label="Motivo">
            <select className="input" value={motivo} onChange={e => setMotivo(e.target.value as MotivoAjuste)}>
              {MOTIVOS.map(m => <option key={m.clave} value={m.clave}>{m.etiqueta}</option>)}
            </select>
          </Field>
        </div>
        <Field label="Observación (obligatoria)" hint="Queda en el historial de ajustes y en la auditoría.">
          <input className="input" maxLength={255} value={observacion} placeholder="Ej.: 2 cauchos con defecto de fábrica" onChange={e => setObservacion(e.target.value)} />
        </Field>
        <div className={cx('rounded-xl border px-4 py-3 text-[13px]', nuevo !== null && nuevo < 0 ? 'border-danger/30 bg-danger/10 text-danger' : 'border-border bg-muted')}>
          Stock: <b>{producto.stock_actual}</b> → <b className="font-display text-base text-primary">{nuevo ?? '—'}</b>
          {nuevo !== null && nuevo < 0 && <span className="ml-2 font-semibold">No hay suficientes unidades.</span>}
        </div>
        {guardar.error && <ErrorBanner error={guardar.error} />}
      </div>
    </Modal>
  )
}
