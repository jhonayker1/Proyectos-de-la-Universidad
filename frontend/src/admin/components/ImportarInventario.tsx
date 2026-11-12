/** Carga masiva de inventario desde Excel o CSV: validar (vista previa) -> revisar -> importar. */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, RefreshCw, Upload } from 'lucide-react'
import { ApiError, saveBlob } from '@/api/client'
import { importacionApi } from '@/api/endpoints'
import { keys, useApiMutation, useCategorias } from '@/api/queries'
import type { IncidenciaImportacion, ModoImportacion, OpcionesImportacion, ResultadoImportacion, SiExiste } from '@/api/types'
import { Badge, Field, Modal, Pagination, StatBox, Tabs, cx, errorText, useToast } from '@/shared/components/ui'

const POR_PAGINA = 8
const IGNORAR = ''
const PESTANAS = ['Errores', 'Advertencias', 'Vista previa'] as const
type Pestana = (typeof PESTANAS)[number]

function ErrorImportacion({ error }: { error: unknown }) {
  if (!error) return null
  const detalles = error instanceof ApiError ? error.details : []
  return (
    <div role="alert" className="rounded-xl border border-danger/30 bg-danger/10 px-4 py-3 text-[13px] text-danger">
      <div className="flex items-center gap-2 font-semibold"><AlertTriangle size={16} className="shrink-0" />{errorText(error)}</div>
      {detalles.length > 0 && <ul className="mt-1.5 mb-0 list-disc pl-9 text-xs">{detalles.map(d => <li key={d}>{d}</li>)}</ul>}
    </div>
  )
}

function TablaIncidencias({ items, vacio }: { items: IncidenciaImportacion[]; vacio: string }) {
  const [pagina, setPagina] = React.useState(1)
  const total = Math.max(1, Math.ceil(items.length / POR_PAGINA))
  const visibles = items.slice((pagina - 1) * POR_PAGINA, pagina * POR_PAGINA)
  if (items.length === 0) return <div className="py-6 text-center text-[13px] text-muted-foreground">{vacio}</div>
  return (
    <>
      <div className="overflow-x-auto rounded-xl border border-border">
        <table className="w-full border-collapse text-[12.5px]">
          <thead><tr className="bg-muted">{['Fila', 'Columna', 'Valor', 'Motivo'].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
          <tbody>
            {visibles.map((e, i) => (
              <tr key={`${e.fila}-${e.campo}-${i}`} className="border-t border-border">
                <td className="td !py-2 font-mono font-semibold">{e.fila ?? '—'}</td>
                <td className="td !py-2 whitespace-nowrap">{e.columna ? <><span className="text-muted-foreground">{e.letra}:</span> {e.columna}</> : '—'}</td>
                <td className="td !py-2 max-w-[160px] truncate font-mono text-muted-foreground" title={e.valor ?? undefined}>{e.valor ?? '—'}</td>
                <td className="td !py-2">{e.motivo}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-2 flex justify-end"><Pagination page={pagina} total={total} onChange={setPagina} /></div>
    </>
  )
}

const ESTADOS: Record<ResultadoImportacion['estado'], { tono: string; icono: React.ReactNode }> = {
  validado: { tono: 'border-primary/30 bg-primary/5 text-primary', icono: <FileSpreadsheet size={16} /> },
  rechazado: { tono: 'border-danger/30 bg-danger/10 text-danger', icono: <AlertTriangle size={16} /> },
  sin_cambios: { tono: 'border-border bg-muted text-muted-foreground', icono: <FileSpreadsheet size={16} /> },
  importado: { tono: 'border-success/30 bg-success/10 text-success', icono: <CheckCircle2 size={16} /> },
  importado_parcial: { tono: 'border-warning/40 bg-warning/10 text-warning', icono: <CheckCircle2 size={16} /> },
}

export default function ImportarInventario({ onClose }: { onClose: () => void }) {
  const toast = useToast()
  const categorias = useCategorias()
  const campos = useQuery({ queryKey: ['importacion', 'campos'], queryFn: importacionApi.campos, staleTime: Infinity })
  const [archivo, setArchivo] = React.useState<File | null>(null)
  const [siExiste, setSiExiste] = React.useState<SiExiste>('actualizar')
  const [crearFaltantes, setCrearFaltantes] = React.useState(false)
  const [categoriaDefecto, setCategoriaDefecto] = React.useState('')
  const [mapeo, setMapeo] = React.useState<Record<string, string>>({})
  const [resultado, setResultado] = React.useState<ResultadoImportacion | null>(null)
  const [desactualizado, setDesactualizado] = React.useState(false)
  const [pestana, setPestana] = React.useState<Pestana>('Errores')
  const [descargando, setDescargando] = React.useState<'' | 'plantilla' | 'reporte'>('')
  const [errorDescarga, setErrorDescarga] = React.useState<unknown>(null)

  const opciones = (modo: ModoImportacion): OpcionesImportacion => ({
    modo, si_existe: siExiste, crear_faltantes: crearFaltantes,
    id_categoria_defecto: categoriaDefecto ? Number(categoriaDefecto) : null,
    hoja: resultado?.archivo.hoja ?? null, mapeo,
  })
  // Cualquier cambio de archivo u opciones obliga a validar de nuevo antes de importar.
  const cambiar = <T,>(set: (v: T) => void) => (v: T) => { set(v); if (resultado) setDesactualizado(true) }

  const validar = useApiMutation((modo: ModoImportacion) => importacionApi.importar(archivo!, opciones(modo)),
    [], r => {
      setResultado(r); setDesactualizado(false)
      setPestana(r.errores.length ? 'Errores' : r.advertencias.length ? 'Advertencias' : 'Vista previa')
    })
  const importar = useApiMutation((modo: ModoImportacion) => importacionApi.importar(archivo!, opciones(modo)),
    [keys.productos, keys.categorias, keys.marcas, keys.reportes], r => {
      setResultado(r)
      toast(r.mensaje, r.aplicado ? 'ok' : 'error')
    })
  const ocupado = validar.isPending || importar.isPending
  const r = resultado
  const importado = r?.aplicado ?? false

  const elegirArchivo = (f: File | null) => {
    setArchivo(f); setResultado(null); setMapeo({}); setDesactualizado(false); validar.reset(); importar.reset()
  }

  const descargar = async (que: 'plantilla' | 'reporte') => {
    setDescargando(que); setErrorDescarga(null)
    try {
      if (que === 'plantilla') saveBlob(await importacionApi.plantilla(), 'plantilla_inventario.xlsx')
      else if (resultado?.reporte_id) {
        const base = (archivo?.name ?? 'inventario').replace(/\.[^.]+$/, '')
        saveBlob(await importacionApi.reporte(resultado.reporte_id), `errores_${base}.xlsx`)
      }
    } catch (e) {
      setErrorDescarga(e)
    } finally {
      setDescargando('')
    }
  }

  // Campo asignado a cada columna (letra), según el último análisis y los cambios manuales.
  const columnas = r ? [
    ...r.mapeo.map(c => ({ letra: c.letra, columna: c.columna, campo: c.campo, metodo: c.metodo, confianza: c.confianza, motivo: '' })),
    ...r.columnas_ignoradas.map(c => ({ letra: c.letra, columna: c.columna, campo: IGNORAR, metodo: 'ignorada', confianza: 0, motivo: c.motivo })),
  ].sort((a, b) => a.letra.length - b.letra.length || a.letra.localeCompare(b.letra)) : []
  const campoDe = (letra: string, original: string) => mapeo[letra] ?? original
  const usados = new Set(columnas.map(c => campoDe(c.letra, c.campo)).filter(Boolean))

  const validas = r ? r.resumen.a_crear + r.resumen.a_actualizar : 0
  const conErrores = r?.resumen.filas_con_error ?? 0

  const footer = importado ? (
    <button className="btn-primary" onClick={onClose}>Cerrar</button>
  ) : (
    <>
      <button className="btn-muted" onClick={onClose}>Cancelar</button>
      {r && !desactualizado && validas > 0 && (
        <button className={conErrores ? 'btn-success' : 'btn-primary'} disabled={ocupado}
          onClick={() => importar.mutate(conErrores ? 'parcial' : 'estricto')}>
          <Upload size={14} />
          {importar.isPending ? 'Importando…' : conErrores
            ? `Importar las ${validas} filas válidas`
            : `Importar ${validas} producto${validas === 1 ? '' : 's'}`}
        </button>
      )}
      {(!r || desactualizado) && (
        <button className="btn-primary" disabled={!archivo || ocupado} onClick={() => validar.mutate('validar')}>
          {r ? <RefreshCw size={14} /> : <FileSpreadsheet size={14} />}
          {validar.isPending ? 'Validando…' : r ? 'Volver a validar' : 'Validar archivo'}
        </button>
      )}
    </>
  )

  return (
    <Modal title="Importar inventario desde Excel" width="max-w-5xl" onClose={onClose} footer={footer}
      subtitle="Archivos .xlsx o .csv. Las columnas pueden estar en cualquier orden y con otros nombres (P. Venta, Existencia, Rubro…).">
      <div className="flex flex-col gap-4">
        {/* 1. Archivo y opciones */}
        <div className="grid gap-3.5 md:grid-cols-[1.4fr_1fr]">
          <label className={cx('flex cursor-pointer items-center gap-3 rounded-xl border-2 border-dashed px-4 py-3.5',
            archivo ? 'border-primary/40 bg-primary/5' : 'border-border bg-muted hover:border-primary/40')}>
            <FileSpreadsheet size={26} className="shrink-0 text-primary" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold">{archivo ? archivo.name : 'Elegir archivo Excel o CSV…'}</div>
              <div className="text-[11px] text-muted-foreground">
                {archivo ? `${(archivo.size / 1024).toFixed(0)} KB · haga clic para cambiarlo` : 'La tabla puede tener un título encima; se detecta la fila de encabezados.'}
              </div>
            </div>
            <input type="file" className="sr-only" accept=".xlsx,.xlsm,.csv,.txt" disabled={ocupado || importado}
              onChange={e => elegirArchivo(e.target.files?.[0] ?? null)} />
          </label>
          <div className="flex flex-col justify-center gap-2 rounded-xl border border-border px-4 py-3 text-xs text-muted-foreground">
            ¿No tiene un archivo? Use la plantilla con las categorías, marcas y proveedores actuales.
            <button className="btn-muted !py-1.5 self-start text-xs" disabled={descargando !== ''} onClick={() => descargar('plantilla')}>
              <Download size={13} /> {descargando === 'plantilla' ? 'Descargando…' : 'Descargar plantilla'}
            </button>
          </div>
        </div>

        <div className="grid gap-3.5 md:grid-cols-3">
          <Field label="Si el SKU ya existe">
            <select className="input" value={siExiste} disabled={importado} onChange={e => cambiar(setSiExiste)(e.target.value as SiExiste)}>
              <option value="actualizar">Actualizar el producto</option>
              <option value="omitir">Omitir la fila</option>
              <option value="error">Marcarlo como error</option>
            </select>
          </Field>
          <Field label="Categoría para filas sin categoría">
            <select className="input" value={categoriaDefecto} disabled={importado} onChange={e => cambiar(setCategoriaDefecto)(e.target.value)}>
              <option value="">Ninguna (la fila la debe traer)</option>
              {categorias.data?.map(c => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre}</option>)}
            </select>
          </Field>
          <label className="flex items-center gap-2.5 self-end rounded-lg border border-border px-3 py-2 text-[13px]">
            <input type="checkbox" checked={crearFaltantes} disabled={importado} onChange={e => cambiar(setCrearFaltantes)(e.target.checked)} />
            Crear categorías y marcas que no existan
          </label>
        </div>

        <ErrorImportacion error={validar.error ?? importar.error ?? errorDescarga} />

        {/* 2. Resultado del análisis */}
        {r && (
          <>
            <div className={cx('flex items-start gap-2.5 rounded-xl border px-4 py-3 text-[13px] font-semibold', ESTADOS[r.estado].tono)}>
              <span className="mt-0.5 shrink-0">{ESTADOS[r.estado].icono}</span>
              <div className="flex-1">
                {r.mensaje}
                <div className="mt-0.5 text-[11px] font-normal opacity-80">
                  {r.archivo.hoja ? `Hoja "${r.archivo.hoja}"` : `CSV (${r.archivo.codificacion}, separado por ${r.archivo.separador})`} ·
                  encabezados en la fila {r.archivo.fila_encabezados}
                </div>
              </div>
            </div>
            {desactualizado && (
              <div className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-2.5 text-xs font-semibold text-warning">
                Cambió el archivo, el mapeo o las opciones: vuelva a validar antes de importar.
              </div>
            )}

            <div className="grid grid-cols-3 gap-2.5 md:grid-cols-6">
              <StatBox label="Filas leídas" value={r.resumen.filas_leidas} />
              <StatBox label={importado ? 'Creados' : 'Nuevos'} value={importado ? r.resumen.creados : r.resumen.a_crear} color="var(--primary)" />
              <StatBox label={importado ? 'Actualizados' : 'A actualizar'} value={importado ? r.resumen.actualizados : r.resumen.a_actualizar} color="var(--accent)" />
              <StatBox label="Omitidas" value={r.resumen.a_omitir} />
              <StatBox label="Con errores" value={conErrores} color={conErrores ? 'var(--danger)' : undefined} />
              <StatBox label="Advertencias" value={r.resumen.total_advertencias} color={r.resumen.total_advertencias ? 'var(--warning)' : undefined} />
            </div>

            {(r.resumen.categorias_nuevas.length > 0 || r.resumen.marcas_nuevas.length > 0) && (
              <div className="rounded-xl border border-border bg-muted px-4 py-2.5 text-xs">
                {importado ? 'Se crearon' : 'Se crearán'}:{' '}
                {r.resumen.categorias_nuevas.map(c => <span key={c.nombre} className="mr-2 font-semibold">categoría {c.nombre} ({c.prefijo_sku})</span>)}
                {r.resumen.marcas_nuevas.map(m => <span key={m.nombre} className="mr-2 font-semibold">marca {m.nombre}</span>)}
              </div>
            )}

            {!importado && (
              <div>
                <div className="label-caps">Columnas del archivo</div>
                <div className="overflow-x-auto rounded-xl border border-border">
                  <table className="w-full border-collapse text-[12.5px]">
                    <thead><tr className="bg-muted">{['Col.', 'Encabezado en el archivo', 'Se guarda como', 'Detección'].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
                    <tbody>
                      {columnas.map(c => {
                        const actual = campoDe(c.letra, c.campo)
                        const cambiado = c.letra in mapeo && mapeo[c.letra] !== c.campo
                        return (
                          <tr key={c.letra} className="border-t border-border">
                            <td className="td !py-1.5 font-mono font-semibold text-muted-foreground">{c.letra}</td>
                            <td className="td !py-1.5 font-semibold">{c.columna}</td>
                            <td className="td !py-1.5">
                              <select aria-label={`Campo de la columna ${c.letra}`} className="input !w-52 !py-1 text-xs" value={actual}
                                onChange={e => { setMapeo(m => ({ ...m, [c.letra]: e.target.value })); setDesactualizado(true) }}>
                                <option value={IGNORAR}>— No importar —</option>
                                {campos.data?.map(f => (
                                  <option key={f.clave} value={f.clave} disabled={f.clave !== actual && usados.has(f.clave)}>{f.etiqueta}</option>
                                ))}
                              </select>
                            </td>
                            <td className="td !py-1.5 text-xs text-muted-foreground">
                              {cambiado ? <Badge tone="Pendiente">cambio manual</Badge>
                                : c.metodo === 'ignorada' ? c.motivo
                                  : c.metodo === 'aproximado' ? <Badge tone="Bajo Stock">aproximada {Math.round(c.confianza * 100)}%</Badge>
                                    : c.metodo === 'manual' ? <Badge>manual</Badge>
                                      : <Badge tone="Disponible">reconocida</Badge>}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            <div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <Tabs value={pestana} onChange={setPestana} options={PESTANAS} />
                {r.reporte_id && !desactualizado && (
                  <button className="btn-muted !py-1.5 text-xs" disabled={descargando !== ''} onClick={() => descargar('reporte')}
                    title="Excel con cada error y las filas rechazadas tal como venían, para corregirlas y volver a subirlas">
                    <Download size={13} /> {descargando === 'reporte' ? 'Generando…' : 'Descargar reporte de errores (.xlsx)'}
                  </button>
                )}
              </div>
              {pestana === 'Errores' && (
                <>
                  <TablaIncidencias items={r.errores} vacio="Sin errores: todas las filas se pueden importar." />
                  {r.errores_truncados && <div className="text-[11px] text-muted-foreground">Se muestran los primeros {r.errores.length} de {r.resumen.total_errores}; el reporte en Excel los trae todos.</div>}
                </>
              )}
              {pestana === 'Advertencias' && (
                <TablaIncidencias items={r.advertencias} vacio="Sin advertencias." />
              )}
              {pestana === 'Vista previa' && (
                r.vista_previa.length === 0 ? <div className="py-6 text-center text-[13px] text-muted-foreground">No hay filas válidas.</div> : (
                  <div className="max-h-72 overflow-auto rounded-xl border border-border">
                    <table className="w-full border-collapse text-[12.5px]">
                      <thead className="sticky top-0"><tr className="bg-muted">{['Fila', 'Acción', 'SKU', 'Producto', 'Categoría'].map(h => <th key={h} className="th !py-2">{h}</th>)}</tr></thead>
                      <tbody>
                        {r.vista_previa.map(p => (
                          <tr key={p.fila} className="border-t border-border">
                            <td className="td !py-1.5 font-mono">{p.fila}</td>
                            <td className="td !py-1.5"><Badge tone={p.accion === 'crear' ? 'Disponible' : p.accion === 'omitir' ? 'Inactivo' : undefined}>{p.accion}</Badge></td>
                            <td className="td !py-1.5 font-mono font-semibold text-primary">{p.sku}{p.sku_automatico && <span className="ml-1 text-[10px] font-normal text-muted-foreground">auto</span>}</td>
                            <td className="td !py-1.5">{p.nombre}</td>
                            <td className="td !py-1.5 text-muted-foreground">{p.categoria ?? '—'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )
              )}
            </div>
            {!importado && conErrores > 0 && validas > 0 && !desactualizado && (
              <div className="text-xs text-muted-foreground">
                Puede importar ahora solo las filas válidas (las que tienen errores no se guardan) o corregir el archivo y volver a subirlo.
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  )
}
