/**
 * Ticket en curso del cajero. Solo guarda id y cantidad: nombre, precio y stock se leen
 * siempre de la lista de productos, así el total coincide con lo que cobra el backend.
 */
import React from 'react'
import { useProductos } from '@/api/queries'
import type { Producto } from '@/api/types'
import { num, round2 } from '@/shared/lib/money'

type Items = Record<number, number>
export type LineaTicket = { producto: Producto; cantidad: number; subtotal: number }

type Cart = {
  lineas: LineaTicket[]
  totalUsd: number
  unidades: number
  cantidadDe: (id: number) => number
  agregar: (p: Producto) => boolean
  cambiar: (id: number, cantidad: number) => void
  quitar: (id: number) => void
  vaciar: () => void
}

const CartContext = React.createContext<Cart | null>(null)

export function CartProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<Items>({})
  const productos = useProductos()

  const lineas = React.useMemo(() => {
    const porId = new Map((productos.data ?? []).map(p => [p.id_producto, p]))
    return Object.entries(items).flatMap(([id, cantidad]) => {
      const producto = porId.get(Number(id))
      return producto ? [{ producto, cantidad, subtotal: round2(num(producto.precio_usd) * cantidad) }] : []
    })
  }, [items, productos.data])

  const value = React.useMemo<Cart>(() => ({
    lineas,
    totalUsd: round2(lineas.reduce((t, l) => t + l.subtotal, 0)),
    unidades: lineas.reduce((t, l) => t + l.cantidad, 0),
    cantidadDe: id => items[id] ?? 0,
    agregar: p => {
      const actual = items[p.id_producto] ?? 0
      if (actual >= p.stock_actual) return false
      setItems(it => ({ ...it, [p.id_producto]: actual + 1 }))
      return true
    },
    cambiar: (id, cantidad) => setItems(it => {
      const stock = lineas.find(l => l.producto.id_producto === id)?.producto.stock_actual ?? cantidad
      const n = Math.max(1, Math.min(cantidad, stock))
      return { ...it, [id]: n }
    }),
    quitar: id => setItems(it => {
      const { [id]: _, ...rest } = it
      return rest
    }),
    vaciar: () => setItems({}),
  }), [items, lineas])

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>
}

export function useCart() {
  const ctx = React.useContext(CartContext)
  if (!ctx) throw new Error('useCart debe usarse dentro de CartProvider')
  return ctx
}
