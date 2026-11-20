/** Hooks de lectura con caché (TanStack Query) y claves para invalidar tras cada cambio. */
import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query'
import { ApiError } from './client'
import { categoriasApi, finanzasApi, marcasApi, productosApi, proveedoresApi } from './endpoints'

export const keys = {
  usuarios: ['usuarios'] as const,
  categorias: ['categorias'] as const,
  marcas: ['marcas'] as const,
  proveedores: ['proveedores'] as const,
  productos: ['productos'] as const,
  monedas: ['monedas'] as const,
  tasas: ['tasas'] as const,
  ventas: ['ventas'] as const,
  compras: ['compras'] as const,
  facturas: ['facturas'] as const,
  reportes: ['reportes'] as const,
}

export function useCategorias() {
  return useQuery({ queryKey: keys.categorias, queryFn: categoriasApi.list })
}

export function useMarcas() {
  return useQuery({ queryKey: keys.marcas, queryFn: marcasApi.list, staleTime: 5 * 60_000 })
}

export function useProveedores() {
  return useQuery({ queryKey: keys.proveedores, queryFn: proveedoresApi.list })
}

export function useMonedas() {
  return useQuery({ queryKey: keys.monedas, queryFn: finanzasApi.monedas, staleTime: 10 * 60_000 })
}

/** Tasa vigente de una moneda; null si aún no hay ninguna registrada (409 del backend). */
export function useTasa(codigo: string) {
  return useQuery({
    queryKey: [...keys.tasas, 'vigente', codigo],
    queryFn: async () => {
      try {
        return await finanzasApi.tasaVigente(codigo)
      } catch (e) {
        if (e instanceof ApiError && (e.status === 409 || e.status === 404)) return null
        throw e
      }
    },
  })
}

export function useProductosAdmin() {
  return useQuery({ queryKey: [...keys.productos, 'admin'], queryFn: productosApi.listAdmin })
}

export function useProductos() {
  return useQuery({ queryKey: [...keys.productos, 'publico'], queryFn: () => productosApi.list() })
}

/** Mutación que, al terminar bien, invalida las claves indicadas (refresca pantallas). */
export function useApiMutation<TArgs, TResult>(
  fn: (args: TArgs) => Promise<TResult>,
  invalidate: QueryKey[],
  onSuccess?: (result: TResult) => void,
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: result => {
      invalidate.forEach(queryKey => qc.invalidateQueries({ queryKey }))
      onSuccess?.(result)
    },
  })
}
