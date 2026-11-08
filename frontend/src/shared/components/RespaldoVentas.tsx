/**
 * Respaldo de ventas por semana o mes, con PDF. El admin ve todas las ventas; el cajero,
 * solo las suyas (el backend filtra /ventas según el rol).
 */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { ChevronLeft, ChevronRight, DatabaseBackup, Download } from 'lucide-react'
import { keys } from '@/api/queries'
import { ventasApi } from '@/api/endpoints'
import { fmtDia, fmtFecha, fmtMes, iso, rangoRespaldo, type ModoRespaldo } from '@/shared/lib/dates'
import { fmtMoneda } from '@/shared/lib/money'
import { pdfRespaldo, ventasPorDia } from '@/shared/lib/pdf'
import { useTasas } from './productos'
import { ErrorBanner, Spinner, StatBox, Tabs, errorText, useToast } from './ui'

const MODOS = ['Semanal', 'Mensual'] as const

export default function RespaldoVentas({ titulo = 'Respaldo de Reportes por Semana / Mes' }: { titulo?: string }) {
  const [modo, setModo] = React.useState<ModoRespaldo>('Semanal')
  const [offset, setOffset] = React.useState(0)
  const [generando, setGenerando] = React.useState(false)
  const toast = useToast()
  const { tasas } = useTasas()
  const maxOffset = modo === 'Semanal' ? 51 : 11
  const { ini, fin } = rangoRespaldo(modo, offset)
  const desde = iso(ini)
  const hasta = iso(fin)

  const ventas = useQuery({
    queryKey: [...keys.ventas, 'rango', desde, hasta],
    queryFn: () => ventasApi.list({ desde, hasta, limite: 5000 }),
  })
  // ini/fin se recalculan en cada render; desde/hasta (texto) identifican el rango.
  const dias = React.useMemo(() => ventasPorDia(ventas.data ?? [], ini, fin), [ventas.data, desde, hasta])
  const totalVentas = dias.reduce((t, d) => t + d.ventas, 0)
  const totalUnidades = dias.reduce((t, d) => t + d.unidades, 0)
  const totalUSD = dias.reduce((t, d) => t + d.totalUSD, 0)
  const etiqueta = modo === 'Semanal' ? `Semana del ${fmtFecha(ini)} al ${fmtFecha(fin)}` : fmtMes(ini)

  const exportar = async () => {
    setGenerando(true)
    try {
      await pdfRespaldo(modo, ini, fin, dias, tasas.VES)
    } catch (e) {
      toast(`No se pudo generar el PDF: ${errorText(e)}`, 'error')
    } finally {
      setGenerando(false)
    }
  }

  return (
    <div className="card !rounded-[14px] p-[18px]">
      <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
        <DatabaseBackup size={18} className="text-primary" />
        <h3 className="m-0 text-base font-bold">{titulo}</h3>
        <Tabs className="ml-auto" value={modo} options={MODOS} onChange={m => { setModo(m); setOffset(0) }} />
      </div>

      <div className="mb-3.5 flex flex-wrap items-center gap-2">
        <button aria-label="Período anterior" className="btn-icon !h-8 !w-8" disabled={offset >= maxOffset} onClick={() => setOffset(o => Math.min(o + 1, maxOffset))}>
          <ChevronLeft size={16} />
        </button>
        <select aria-label="Período" className="input min-w-[220px] flex-1 font-display font-semibold" value={offset} onChange={e => setOffset(Number(e.target.value))}>
          {Array.from({ length: maxOffset + 1 }, (_, i) => {
            const r = rangoRespaldo(modo, i)
            const txt = modo === 'Semanal' ? `${fmtFecha(r.ini)} – ${fmtFecha(r.fin)}` : fmtMes(r.ini)
            return <option key={i} value={i}>{i === 0 ? `${modo === 'Semanal' ? 'Esta semana' : 'Este mes'} · ${txt}` : txt}</option>
          })}
        </select>
        <button aria-label="Período siguiente" className="btn-icon !h-8 !w-8" disabled={offset === 0} onClick={() => setOffset(o => Math.max(o - 1, 0))}>
          <ChevronRight size={16} />
        </button>
        <button className="btn-primary" onClick={exportar} disabled={generando || ventas.isLoading}>
          <Download size={14} /> {generando ? 'Generando PDF...' : 'Respaldo PDF'}
        </button>
      </div>

      <div className="mb-2.5 text-[13px] font-semibold capitalize">{etiqueta}</div>
      {ventas.error ? <ErrorBanner error={ventas.error} onRetry={() => ventas.refetch()} /> : ventas.isLoading ? <Spinner /> : <>
        <div className="mb-3.5 grid grid-cols-[repeat(auto-fit,minmax(160px,1fr))] gap-3">
          <StatBox label="Ventas" value={totalVentas} color="#10b981" />
          <StatBox label="Unidades" value={totalUnidades} color="#4f46e5" />
          <StatBox label="Total USD" value={fmtMoneda(totalUSD, 'USD')} color="#06b6d4" />
          {tasas.VES !== null && <StatBox label="Total Bs. (tasa actual)" value={fmtMoneda(totalUSD * tasas.VES, 'VES')} color="#f59e0b" />}
        </div>
        <div className="max-h-80 overflow-auto rounded-xl border border-border">
          <table className="w-full min-w-[520px] border-collapse text-[13px]">
            <thead className="sticky top-0 bg-muted">
              <tr>{['Día', 'Ventas', 'Unidades', 'Total USD', ...(tasas.VES !== null ? ['Total Bs.'] : [])].map(h => <th key={h} className="th !py-2.5">{h}</th>)}</tr>
            </thead>
            <tbody>
              {dias.map(d => (
                <tr key={iso(d.fecha)} className="border-t border-border">
                  <td className="td !py-2.5 font-semibold capitalize">{fmtDia(d.fecha)}</td>
                  <td className="td !py-2.5">{d.ventas}</td>
                  <td className="td !py-2.5">{d.unidades}</td>
                  <td className="td !py-2.5 font-bold text-success">{fmtMoneda(d.totalUSD, 'USD')}</td>
                  {tasas.VES !== null && <td className="td !py-2.5 text-muted-foreground">{fmtMoneda(d.totalUSD * tasas.VES, 'VES')}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-2 text-[11px] text-muted-foreground">
          Montos en USD tal como se registraron; el total en Bs. usa la tasa vigente. Las ventas anuladas no se incluyen.
        </div>
      </>}
    </div>
  )
}
