import React from 'react'
import { productosApi } from '@/api/endpoints'
import { keys, useApiMutation } from '@/api/queries'
import type { AjusteStockInput, Producto } from '@/api/types'
import { ErrorBanner, Field, Modal, useToast } from '@/shared/components/ui'

const MOTIVOS: { value: AjusteStockInput['motivo']; label: string }[] = [
  { value: 'conteo', label: 'Conteo físico' },
  { value: 'merma', label: 'Daño o merma' },
  { value: 'devolucion', label: 'Devolución' },
  { value: 'otro', label: 'Otro' },
]

export default function AjusteStockModal({ producto, onClose }: { producto: Producto; onClose: () => void }) {
  const toast = useToast()
  const [tipo, setTipo] = React.useState<AjusteStockInput['tipo']>('sumar')
  const [cantidad, setCantidad] = React.useState('1')
  const [motivo, setMotivo] = React.useState<AjusteStockInput['motivo']>('conteo')
  const [observacion, setObservacion] = React.useState('')
  const numero = Number(cantidad)
  const valido = Number.isInteger(numero) && numero >= 0 && (tipo === 'conteo' || numero > 0) &&
    observacion.trim().length >= 3
  const guardar = useApiMutation((data: AjusteStockInput) => productosApi.ajustar(producto.id_producto, data),
    [keys.productos, keys.ajustes, keys.reportes], ajuste => {
      toast(`Stock actualizado: ${ajuste.stock_anterior} → ${ajuste.stock_nuevo}.`)
      onClose()
    })

  return (
    <Modal title="Ajustar stock" subtitle={`${producto.sku} · ${producto.nombre} · stock actual: ${producto.stock_actual}`}
      onClose={onClose} width="max-w-lg" footer={<>
        <button className="btn-muted" onClick={onClose}>Cancelar</button>
        <button className="btn-primary" disabled={!valido || guardar.isPending}
          onClick={() => guardar.mutate({ tipo, cantidad: numero, motivo, observacion: observacion.trim() })}>
          {guardar.isPending ? 'Guardando...' : 'Guardar ajuste'}
        </button>
      </>}>
      <div className="flex flex-col gap-3.5">
        <Field label="Tipo de ajuste">
          <select className="input" value={tipo} onChange={e => setTipo(e.target.value as AjusteStockInput['tipo'])}>
            <option value="sumar">Sumar unidades</option>
            <option value="restar">Restar unidades</option>
            <option value="conteo">Establecer conteo físico</option>
          </select>
        </Field>
        <Field label={tipo === 'conteo' ? 'Stock contado' : 'Unidades'}>
          <input className="input" type="number" min={tipo === 'conteo' ? 0 : 1} step={1}
            value={cantidad} onChange={e => setCantidad(e.target.value)} />
        </Field>
        <Field label="Motivo">
          <select className="input" value={motivo} onChange={e => setMotivo(e.target.value as AjusteStockInput['motivo'])}>
            {MOTIVOS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </Field>
        <Field label="Observación" hint="Explique el motivo del ajuste (mínimo 3 caracteres).">
          <textarea className="input min-h-24 resize-y" maxLength={255} value={observacion}
            onChange={e => setObservacion(e.target.value)} />
        </Field>
        {guardar.error && <ErrorBanner error={guardar.error} />}
      </div>
    </Modal>
  )
}
