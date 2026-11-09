/** Filtros, moneda y tasas que usan el inventario del admin y el del cajero. */
import React from 'react'
import { Search } from 'lucide-react'
import { useCategorias, useMarcas, useTasa } from '@/api/queries'
import type { Producto } from '@/api/types'
import { fmtMoneda, num } from '@/shared/lib/money'

export type MonedaVista = 'USD' | 'VES' | 'COP'
export const MONEDAS_VISTA: { codigo: MonedaVista; label: string }[] = [
  { codigo: 'USD', label: 'Dólares (USD)' },
  { codigo: 'VES', label: 'Bolívares (Bs.)' },
  { codigo: 'COP', label: 'Pesos COP' },
]

/** Tasas vigentes (unidades por 1 USD) de VES y COP; null si no hay. */
export function useTasas() {
  const ves = useTasa('VES')
  const cop = useTasa('COP')
  const tasas = {
    VES: ves.data ? num(ves.data.tasa_venta) : null,
    COP: cop.data ? num(cop.data.tasa_venta) : null,
  }
  const convertir = (usd: string | number, moneda: MonedaVista) => {
    if (moneda === 'USD') return fmtMoneda(usd, 'USD')
    const t = tasas[moneda]
    return t === null ? 'Sin tasa' : fmtMoneda(num(usd) * t, moneda)
  }
  return { ves, cop, tasas, convertir, isLoading: ves.isLoading || cop.isLoading }
}

export function CurrencySelect({ value, onChange }: { value: MonedaVista; onChange: (m: MonedaVista) => void }) {
  return (
    <select aria-label="Moneda de los precios" value={value} onChange={e => onChange(e.target.value as MonedaVista)}
      className="cursor-pointer rounded-md border border-border bg-primary px-2 py-0.5 font-display text-[11px] font-bold text-white">
      {MONEDAS_VISTA.map(m => <option key={m.codigo} value={m.codigo}>{m.label}</option>)}
    </select>
  )
}

export const ESTADOS_PRODUCTO = ['Disponible', 'Bajo Stock', 'Agotado'] as const

export type Filtros = { busqueda: string; categoria: string; marca: string; estado: string }
const VACIO: Filtros = { busqueda: '', categoria: '', marca: '', estado: '' }

/** Estado de filtros + lista filtrada; `pagina` vuelve a 1 al cambiar un filtro. */
export function useFiltrosProductos<T extends Producto>(productos: T[] | undefined, pageSize = 8) {
  const [filtros, setFiltrosRaw] = React.useState<Filtros>(VACIO)
  const [pagina, setPagina] = React.useState(1)
  const setFiltros = (f: Partial<Filtros>) => { setFiltrosRaw(prev => ({ ...prev, ...f })); setPagina(1) }
  const filtrados = React.useMemo(() => {
    const q = filtros.busqueda.trim().toLowerCase()
    return (productos ?? []).filter(p =>
      (!q || p.nombre.toLowerCase().includes(q) || p.sku.toLowerCase().includes(q)) &&
      (!filtros.categoria || String(p.id_categoria) === filtros.categoria) &&
      (!filtros.marca || String(p.id_marca) === filtros.marca) &&
      (!filtros.estado || p.estado === filtros.estado),
    )
  }, [productos, filtros])
  const totalPaginas = Math.max(1, Math.ceil(filtrados.length / pageSize))
  const actual = Math.min(pagina, totalPaginas)
  return {
    filtros, setFiltros, limpiar: () => { setFiltrosRaw(VACIO); setPagina(1) },
    filtrados, pagina: actual, setPagina, totalPaginas,
    paginados: filtrados.slice((actual - 1) * pageSize, actual * pageSize),
  }
}

export function FiltrosBar({ filtros, setFiltros, limpiar, children }: {
  filtros: Filtros
  setFiltros: (f: Partial<Filtros>) => void
  limpiar: () => void
  children?: React.ReactNode
}) {
  const categorias = useCategorias()
  const marcas = useMarcas()
  return (
    <div className="card flex flex-wrap items-end gap-3 !rounded-[14px] px-4 py-3.5">
      <label className="flex min-w-[180px] flex-[1_1_200px] flex-col">
        <span className="label-caps">Buscar por nombre</span>
        <div className="relative">
          <Search size={14} className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-muted-foreground" />
          <input className="input !bg-card !pl-8" placeholder="Nombre o SKU..." value={filtros.busqueda} onChange={e => setFiltros({ busqueda: e.target.value })} />
        </div>
      </label>
      <label className="flex w-40 flex-col">
        <span className="label-caps">Categoría</span>
        <select className="input !bg-card" value={filtros.categoria} onChange={e => setFiltros({ categoria: e.target.value })}>
          <option value="">Todas</option>
          {categorias.data?.map(c => <option key={c.id_categoria} value={c.id_categoria}>{c.nombre}</option>)}
        </select>
      </label>
      <label className="flex w-40 flex-col">
        <span className="label-caps">Marca</span>
        <select className="input !bg-card" value={filtros.marca} onChange={e => setFiltros({ marca: e.target.value })}>
          <option value="">Todas</option>
          {marcas.data?.map(m => <option key={m.id_marca} value={m.id_marca}>{m.nombre}</option>)}
        </select>
      </label>
      <label className="flex w-36 flex-col">
        <span className="label-caps">Estado</span>
        <select className="input !bg-card" value={filtros.estado} onChange={e => setFiltros({ estado: e.target.value })}>
          <option value="">Todos</option>
          {ESTADOS_PRODUCTO.map(e => <option key={e} value={e}>{e}</option>)}
        </select>
      </label>
      <div className="flex gap-2">
        <button className="btn-muted" onClick={limpiar}>Limpiar filtros</button>
        {children}
      </div>
    </div>
  )
}

/** Celda de stock: ⚠️ en ámbar si está por debajo del mínimo o agotado. */
export function StockCell({ p }: { p: Producto }) {
  const bajo = p.stock_actual < p.stock_minimo || p.stock_actual <= 0
  return (
    <div className="flex items-center gap-1.5" title={`Mínimo: ${p.stock_minimo}`}>
      <span className="text-sm">{bajo ? '⚠️' : '📦'}</span>
      <span className={bajo ? 'font-bold text-warning' : 'font-bold'}>{p.stock_actual}</span>
    </div>
  )
}

const EMOJI: [RegExp, string][] = [[/cauch|neum|llant/i, '🛞'], [/bater/i, '🔋'], [/aceit|lubric|filtr/i, '🛢️']]
/** Icono por categoría (reemplaza el campo `emoji` que el diseño tenía escrito a mano). */
export const emojiCategoria = (nombre: string | null) => EMOJI.find(([re]) => re.test(nombre ?? ''))?.[1] ?? '📦'
