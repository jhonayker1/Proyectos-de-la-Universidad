/** Facturas escaneadas: se suben al backend y se descargan las de la semana en un PDF. */
import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, X } from 'lucide-react'
import { facturasApi } from '@/api/endpoints'
import { keys, useApiMutation } from '@/api/queries'
import type { Factura } from '@/api/types'
import { ErrorBanner, Spinner, errorText, useToast } from '@/shared/components/ui'
import { fmtFecha, iso, parseLocal, startOfWeek } from '@/shared/lib/dates'
import { pdfFacturas } from '@/shared/lib/pdf'

const MAX_MB = 10
const TIPOS = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf']

/** Miniatura cargada con el token (los archivos no son públicos). */
function useArchivoUrl(f: Factura) {
  const q = useQuery({ queryKey: [...keys.facturas, 'archivo', f.id_factura_img], queryFn: () => facturasApi.archivo(f.id_factura_img), staleTime: Infinity })
  const [url, setUrl] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!q.data) return
    const u = URL.createObjectURL(q.data)
    setUrl(u)
    return () => URL.revokeObjectURL(u)
  }, [q.data])
  return url
}

function Miniatura({ f, className }: { f: Factura; className: string }) {
  const url = useArchivoUrl(f)
  if (f.tipo_mime === 'application/pdf') return <div className={`${className} flex items-center justify-center bg-muted`}><FileText size={18} className="text-muted-foreground" /></div>
  return url ? <img src={url} alt={f.nombre_original} className={`${className} object-cover`} /> : <div className={`${className} animate-pulse bg-muted`} />
}

export default function Facturas() {
  const toast = useToast()
  const inputRef = React.useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = React.useState(false)
  const [subiendo, setSubiendo] = React.useState(0)
  const [generando, setGenerando] = React.useState(false)
  const lunes = startOfWeek(new Date())
  const domingo = new Date(lunes)
  domingo.setDate(lunes.getDate() + 6)

  const facturas = useQuery({ queryKey: keys.facturas, queryFn: () => facturasApi.list() })
  const semana = (facturas.data ?? []).filter(f => {
    const d = f.fecha_subida ? iso(parseLocal(f.fecha_subida)) : ''
    return d >= iso(lunes) && d <= iso(domingo)
  })
  const subir = useApiMutation((file: File) => facturasApi.upload(file), [keys.facturas])
  const borrar = useApiMutation((f: Factura) => facturasApi.remove(f.id_factura_img), [keys.facturas], () => toast('Factura eliminada.'))

  const addFiles = async (files: FileList | null) => {
    if (!files) return
    for (const file of Array.from(files)) {
      if (!TIPOS.includes(file.type)) { toast(`${file.name}: solo JPG, PNG, WEBP o PDF.`, 'error'); continue }
      if (file.size > MAX_MB * 1024 * 1024) { toast(`${file.name}: supera ${MAX_MB} MB.`, 'error'); continue }
      setSubiendo(n => n + 1)
      try {
        await subir.mutateAsync(file)
      } catch (e) {
        toast(`${file.name}: ${errorText(e)}`, 'error')
      } finally {
        setSubiendo(n => n - 1)
      }
    }
  }

  const descargar = async () => {
    const imagenes = semana.filter(f => f.tipo_mime.startsWith('image/'))
    if (imagenes.length === 0) return toast('No hay imágenes de facturas esta semana (los PDF se descargan aparte).', 'error')
    setGenerando(true)
    const urls: string[] = []
    try {
      const items = await Promise.all(imagenes.map(async f => {
        const url = URL.createObjectURL(await facturasApi.archivo(f.id_factura_img))
        urls.push(url)
        return { url, nombre: f.nombre_original }
      }))
      await pdfFacturas(items, `Semana del ${fmtFecha(lunes)} al ${fmtFecha(domingo)}`)
    } catch (e) {
      toast(errorText(e), 'error')
    } finally {
      urls.forEach(URL.revokeObjectURL)
      setGenerando(false)
    }
  }

  const abrir = async (f: Factura) => {
    try {
      const url = URL.createObjectURL(await facturasApi.archivo(f.id_factura_img))
      window.open(url, '_blank', 'noopener')
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) { toast(errorText(e), 'error') }
  }

  return (
    <div>
      <h2 className="m-0 mb-3.5 text-lg font-bold">Facturas</h2>
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="card flex flex-col gap-4 !rounded-[14px] p-5">
          <div className="font-display text-[15px] font-bold">Subir facturas</div>
          <div role="button" tabIndex={0} onClick={() => inputRef.current?.click()} onKeyDown={e => { if (e.key === 'Enter') inputRef.current?.click() }}
            onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
            onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}
            className={`cursor-pointer rounded-xl border-2 border-dashed px-5 py-7 text-center transition-all ${dragging ? 'border-primary bg-primary/5' : 'border-border bg-muted'}`}>
            <div className="mb-2 text-3xl">🖼️</div>
            <div className="mb-1 text-[13px] font-semibold">{subiendo > 0 ? `Subiendo ${subiendo} archivo(s)...` : 'Arrastra imágenes o PDF aquí'}</div>
            <div className="text-xs text-muted-foreground">o haz clic para seleccionar · máx. {MAX_MB} MB</div>
            <input ref={inputRef} type="file" accept={TIPOS.join(',')} multiple hidden onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
          </div>
          {facturas.isLoading ? <Spinner /> : facturas.error ? <ErrorBanner error={facturas.error} onRetry={() => facturas.refetch()} /> : (
            facturas.data!.length === 0 ? <div className="text-center text-xs text-muted-foreground">No hay facturas subidas aún</div> : (
              <div className="flex max-h-60 flex-col gap-2 overflow-y-auto">
                {facturas.data!.map(f => (
                  <div key={f.id_factura_img} className="flex items-center gap-2.5 rounded-lg border border-border bg-muted px-2.5 py-2">
                    <button className="cursor-pointer border-none bg-transparent p-0" onClick={() => abrir(f)} title="Abrir"><Miniatura f={f} className="h-10 w-10 shrink-0 rounded-md" /></button>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-xs font-semibold">{f.nombre_original}</div>
                      <div className="text-[11px] text-muted-foreground">{f.fecha_subida ? parseLocal(f.fecha_subida).toLocaleDateString('es-VE') : ''} · {(f.tamano_bytes / 1024).toFixed(0)} KB</div>
                    </div>
                    <button aria-label={`Eliminar ${f.nombre_original}`} className="btn-icon border-none bg-transparent text-danger"
                      onClick={() => { if (window.confirm(`¿Eliminar ${f.nombre_original}?`)) borrar.mutate(f, { onError: e => toast(errorText(e), 'error') }) }}>
                      <X size={15} />
                    </button>
                  </div>
                ))}
              </div>
            )
          )}
        </div>

        <div className="card flex flex-col gap-4 !rounded-[14px] p-5">
          <div className="font-display text-[15px] font-bold">Descargar facturas de la semana</div>
          <div className="rounded-xl border border-border bg-muted px-4 py-3 text-[13px] text-muted-foreground">
            Período: <span className="font-bold text-foreground">{fmtFecha(lunes)} – {fmtFecha(domingo)}</span>
          </div>
          {semana.length > 0 ? (
            <div className="grid max-h-52 flex-1 grid-cols-3 gap-2 overflow-y-auto">
              {semana.map(f => <Miniatura key={f.id_factura_img} f={f} className="aspect-[3/4] w-full rounded-lg border border-border" />)}
            </div>
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 py-6 text-[13px] text-muted-foreground">
              <span className="text-3xl">📄</span><span>No hay facturas esta semana</span>
            </div>
          )}
          <div className="text-xs text-muted-foreground">{semana.length} {semana.length === 1 ? 'factura' : 'facturas'} en el período</div>
          <button className="btn-primary !py-2.5" onClick={descargar} disabled={semana.length === 0 || generando}>
            {generando ? 'Generando PDF...' : '⬇ Descargar PDF'}
          </button>
        </div>
      </div>
    </div>
  )
}
