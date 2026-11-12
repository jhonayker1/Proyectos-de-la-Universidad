/** Bitácora de auditoría: solo consulta y exportación (no se puede editar ni borrar). */
import React from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { ChevronDown, Download, FileSpreadsheet, Lock, Search, X } from 'lucide-react'
import { saveBlob } from '@/api/client'
import { auditoriaApi } from '@/api/endpoints'
import type { FiltroAuditoria, RegistroAuditoria } from '@/api/types'
import { Badge, EmptyState, ErrorBanner, Pagination, Spinner, cx } from '@/shared/components/ui'
import { fmtFechaHora } from '@/shared/lib/dates'

const POR_PAGINA = 50

// Tono del distintivo según la acción (reutiliza los colores de los estados).
const TONO: Record<string, string> = {
  crear: 'Disponible', reactivar: 'Disponible', eliminar: 'Agotado', anular: 'Agotado',
  desactivar: 'Bajo Stock', contrasena: 'Bajo Stock', importar: 'Inactivo', exportar: 'Inactivo',
}

const VACIO = <span className="text-muted-foreground">—</span>

function Detalle({ r, verOperacion }: { r: RegistroAuditoria; verOperacion: (id: string) => void }) {
  // Al crear solo hay valores nuevos y al eliminar solo los anteriores: se muestra una columna.
  const conAntes = r.cambios.some(c => c.antes !== null)
  const conDespues = r.cambios.some(c => c.despues !== null)
  const dos = conAntes && conDespues
  return (
    <div className="grid gap-4 bg-muted/60 px-5 py-4 md:grid-cols-[1.6fr_1fr]">
      <div>
        <div className="label-caps">{dos ? 'Cambios' : conAntes ? 'Valores que tenía' : 'Valores registrados'}</div>
        {r.cambios.length === 0 ? <div className="text-xs text-muted-foreground">Sin detalle de campos.</div> : (
          <table className="w-full border-collapse overflow-hidden rounded-lg bg-card text-[12.5px]">
            <thead><tr className="bg-muted">
              {['Campo', ...(dos ? ['Antes', 'Después'] : ['Valor'])].map(h => <th key={h} className="th !py-1.5">{h}</th>)}
            </tr></thead>
            <tbody>
              {r.cambios.map(c => (
                <tr key={c.campo} className="border-t border-border">
                  <td className="td !py-1.5 font-semibold">{c.etiqueta}</td>
                  {dos ? <>
                    <td className="td !py-1.5">{c.antes === null ? VACIO : <span className="text-danger/80 line-through decoration-danger/40">{c.antes}</span>}</td>
                    <td className="td !py-1.5">{c.despues === null ? VACIO : <span className="font-semibold text-success">{c.despues}</span>}</td>
                  </> : (
                    <td className="td !py-1.5">{(conAntes ? c.antes : c.despues) ?? VACIO}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <dl className="m-0 grid grid-cols-[auto_1fr] content-start gap-x-3 gap-y-1.5 text-xs">
        {([
          ['Registro', r.referencia ? `${r.referencia} (${r.entidad} #${r.id_registro ?? '—'})` : r.entidad],
          ['Origen', r.origen],
          ['Ruta', r.ruta && <code className="font-mono">{r.ruta}</code>],
          ['IP', r.ip],
          ['Usuario', `${r.nombre_usuario}${r.rol ? ` · ${r.rol}` : ''}`],
        ] as [string, React.ReactNode][]).map(([k, v]) => (
          <React.Fragment key={k}>
            <dt className="font-semibold text-muted-foreground">{k}</dt>
            <dd className="m-0 break-words">{v || '—'}</dd>
          </React.Fragment>
        ))}
        {r.id_operacion && (
          <dd className="col-span-2 m-0 mt-1">
            <button className="btn-muted !bg-card !py-1 text-xs" onClick={() => verOperacion(r.id_operacion!)}>
              Ver todo lo que cambió en esta operación
            </button>
          </dd>
        )}
      </dl>
    </div>
  )
}

export default function Auditoria() {
  const [filtro, setFiltro] = React.useState<FiltroAuditoria>({})
  const [texto, setTexto] = React.useState('')
  const [pagina, setPagina] = React.useState(1)
  const [abierto, setAbierto] = React.useState<number | null>(null)
  const [exportando, setExportando] = React.useState<'' | 'xlsx' | 'csv'>('')
  const [errorExportar, setErrorExportar] = React.useState<unknown>(null)

  // La búsqueda se aplica al dejar de escribir.
  React.useEffect(() => {
    const t = window.setTimeout(() => cambiar({ buscar: texto.trim() || undefined }), 350)
    return () => window.clearTimeout(t)
  }, [texto])

  const opciones = useQuery({ queryKey: ['auditoria', 'filtros'], queryFn: auditoriaApi.filtros, staleTime: 60_000 })
  const datos = useQuery({
    queryKey: ['auditoria', filtro, pagina],
    queryFn: () => auditoriaApi.list({ ...filtro, pagina, por_pagina: POR_PAGINA }),
    placeholderData: keepPreviousData,
  })

  function cambiar(parcial: Partial<FiltroAuditoria>) {
    setFiltro(f => {
      const nuevo = { ...f, ...parcial }
      return JSON.stringify(nuevo) === JSON.stringify(f) ? f : nuevo
    })
  }
  // Solo si los filtros cambiaron de verdad se vuelve a la página 1 y se cierra el detalle.
  const claveFiltro = JSON.stringify(filtro)
  React.useEffect(() => { setPagina(1); setAbierto(null) }, [claveFiltro])
  const limpiar = () => { setTexto(''); setFiltro({}) }
  const hayFiltros = Object.values(filtro).some(v => v !== undefined && v !== '')

  async function exportar(formato: 'xlsx' | 'csv') {
    setExportando(formato); setErrorExportar(null)
    try {
      const fecha = new Date().toISOString().slice(0, 10)
      saveBlob(await auditoriaApi.exportar(formato, filtro), `auditoria_${fecha}.${formato}`)
    } catch (e) {
      setErrorExportar(e)
    } finally {
      setExportando('')
    }
  }

  const total = datos.data?.total ?? 0
  const sel = (k: keyof FiltroAuditoria) => (e: React.ChangeEvent<HTMLSelectElement | HTMLInputElement>) =>
    cambiar({ [k]: e.target.value === '' ? undefined : k === 'id_usuario' ? Number(e.target.value) : e.target.value })

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="card flex flex-col gap-3.5 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <div className="rounded-xl bg-primary/10 p-2.5 text-primary"><Lock size={18} /></div>
            <div>
              <h2 className="m-0 text-base font-bold">Registro de cambios</h2>
              <p className="m-0 mt-0.5 max-w-2xl text-xs text-muted-foreground">
                Quién cambió qué y cuándo en inventario, catálogos, proveedores, usuarios, tasas, ventas, compras e importaciones.
                Es de solo lectura: nadie puede modificar ni borrar estos registros.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="btn-muted" disabled={exportando !== '' || total === 0} onClick={() => exportar('xlsx')}>
              <FileSpreadsheet size={14} /> {exportando === 'xlsx' ? 'Exportando…' : 'Exportar Excel'}
            </button>
            <button className="btn-muted" disabled={exportando !== '' || total === 0} onClick={() => exportar('csv')}>
              <Download size={14} /> {exportando === 'csv' ? 'Exportando…' : 'CSV'}
            </button>
          </div>
        </div>

        <div className="grid gap-2.5 sm:grid-cols-2 lg:grid-cols-[repeat(5,minmax(0,1fr))_minmax(0,1.6fr)]">
          <label><span className="label-caps">Desde</span>
            <input type="date" className="input" value={filtro.desde ?? ''} max={filtro.hasta} onChange={sel('desde')} /></label>
          <label><span className="label-caps">Hasta</span>
            <input type="date" className="input" value={filtro.hasta ?? ''} min={filtro.desde} onChange={sel('hasta')} /></label>
          <label><span className="label-caps">Módulo</span>
            <select className="input" value={filtro.modulo ?? ''} onChange={sel('modulo')}>
              <option value="">Todos</option>
              {opciones.data?.modulos.map(o => <option key={o.clave} value={o.clave}>{o.etiqueta}</option>)}
            </select></label>
          <label><span className="label-caps">Acción</span>
            <select className="input" value={filtro.accion ?? ''} onChange={sel('accion')}>
              <option value="">Todas</option>
              {opciones.data?.acciones.map(o => <option key={o.clave} value={o.clave}>{o.etiqueta}</option>)}
            </select></label>
          <label><span className="label-caps">Usuario</span>
            <select className="input" value={filtro.id_usuario ?? ''} onChange={sel('id_usuario')}>
              <option value="">Todos</option>
              {opciones.data?.usuarios.map(u => <option key={u.id_usuario ?? 0} value={u.id_usuario ?? 0}>{u.nombre}</option>)}
            </select></label>
          <label><span className="label-caps">Buscar</span>
            <div className="relative">
              <Search size={14} className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground" />
              <input className="input !pl-8" placeholder="SKU, producto, factura, usuario…" value={texto} onChange={e => setTexto(e.target.value)} />
            </div></label>
        </div>
        {(hayFiltros || filtro.id_operacion) && (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {filtro.id_operacion && (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 font-semibold text-primary">
                Mostrando una sola operación
                <button aria-label="Quitar filtro de operación" className="cursor-pointer border-none bg-transparent p-0 text-primary" onClick={() => cambiar({ id_operacion: undefined })}><X size={13} /></button>
              </span>
            )}
            <button className="btn-muted !px-3 !py-1 text-xs" onClick={limpiar}>Limpiar filtros</button>
          </div>
        )}
        {errorExportar ? <ErrorBanner error={errorExportar} /> : null}
      </div>

      <div className="card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="flex-1 overflow-auto">
          {datos.isLoading ? <Spinner label="Cargando auditoría..." /> : datos.error ? (
            <div className="p-4"><ErrorBanner error={datos.error} onRetry={() => datos.refetch()} /></div>
          ) : (
            <table className={cx('w-full border-collapse text-[13px]', datos.isFetching && 'opacity-60')}>
              <thead className="sticky top-0 z-10">
                <tr className="border-b-2 border-border bg-muted">
                  {['Fecha y hora', 'Usuario', 'Módulo', 'Acción', 'Descripción', ''].map(h => <th key={h} className="th">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {datos.data?.items.map(r => (
                  <React.Fragment key={r.id_auditoria}>
                    <tr className={cx('cursor-pointer border-b border-border hover:bg-[#f0f0ff]', abierto === r.id_auditoria && 'bg-[#f0f0ff]')}
                      onClick={() => setAbierto(a => a === r.id_auditoria ? null : r.id_auditoria)}>
                      <td className="td font-mono text-xs whitespace-nowrap text-muted-foreground">{fmtFechaHora(r.fecha)}</td>
                      <td className="td whitespace-nowrap">
                        <div className="font-semibold">{r.nombre_usuario}</div>
                        {r.rol && <div className="text-[11px] text-muted-foreground">{r.rol}</div>}
                      </td>
                      <td className="td whitespace-nowrap text-muted-foreground">{r.modulo_etiqueta}</td>
                      <td className="td"><Badge tone={TONO[r.accion]}>{r.accion_etiqueta}</Badge></td>
                      <td className="td">
                        <div>{r.descripcion}</div>
                        {r.origen && <div className="mt-0.5 text-[11px] text-muted-foreground">{r.origen}</div>}
                      </td>
                      <td className="td w-10">
                        <button aria-label={abierto === r.id_auditoria ? 'Ocultar detalle' : 'Ver detalle'} aria-expanded={abierto === r.id_auditoria}
                          className="btn-icon border-none bg-transparent">
                          <ChevronDown size={16} className={cx('transition-transform', abierto === r.id_auditoria && 'rotate-180')} />
                        </button>
                      </td>
                    </tr>
                    {abierto === r.id_auditoria && (
                      <tr className="border-b border-border">
                        <td colSpan={6} className="p-0">
                          <Detalle r={r} verOperacion={id => cambiar({ id_operacion: id })} />
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                ))}
                {datos.data?.items.length === 0 && (
                  <tr><td colSpan={6}><EmptyState title="No hay registros con estos filtros." hint={hayFiltros ? 'Pruebe con otro rango de fechas o limpie los filtros.' : 'Los cambios que se hagan desde ahora aparecerán aquí.'} /></td></tr>
                )}
              </tbody>
            </table>
          )}
        </div>
        <div className="flex shrink-0 items-center justify-between gap-3 border-t border-border px-5 py-3.5">
          <span className="text-xs text-muted-foreground">{total.toLocaleString('es-VE')} registro{total === 1 ? '' : 's'} · más recientes primero</span>
          <Pagination page={pagina} total={Math.max(1, Math.ceil(total / POR_PAGINA))} onChange={p => { setPagina(p); setAbierto(null) }} />
        </div>
      </div>
    </div>
  )
}
