/** Una función por endpoint del backend (ver README del backend para permisos). */
import { api } from './client'
import type {
  Categoria,
  Compra,
  CompraCreate,
  Dashboard,
  EntradaStock,
  Factura,
  Marca,
  Moneda,
  MovimientosStock,
  Producto,
  ProductoAdmin,
  ProductoInput,
  Proveedor,
  PuntoSerie,
  ResumenVentas,
  StockCategoria,
  Tasa,
  Token,
  TopProducto,
  Usuario,
  UsuarioCreate,
  UsuarioUpdate,
  Venta,
  VentaCreate,
  VentasCategoria,
} from './types'

type Rango = { desde?: string; hasta?: string }

export const authApi = {
  login: (correo: string, password: string) => api.post<Token>('/auth/login', { correo, password }),
  me: () => api.get<Usuario>('/auth/me'),
  solicitarCodigo: (correo: string) => api.post<{ mensaje: string }>('/auth/recuperar/solicitar', { correo }),
  confirmarCodigo: (correo: string, codigo: string, password: string) =>
    api.post<void>('/auth/recuperar/confirmar', { correo, codigo, password }),
}

export const usuariosApi = {
  list: () => api.get<Usuario[]>('/usuarios/'),
  create: (data: UsuarioCreate) => api.post<Usuario>('/usuarios/', data),
  update: (id: number, data: UsuarioUpdate) => api.put<Usuario>(`/usuarios/${id}`, data),
  setActivo: (id: number, activo: boolean) => api.patch<Usuario>(`/usuarios/${id}/estado`, { activo }),
  resetPassword: (id: number, password: string) => api.patch<void>(`/usuarios/${id}/password`, { password }),
  remove: (id: number) => api.delete(`/usuarios/${id}`),
}

export const categoriasApi = {
  list: () => api.get<Categoria[]>('/categorias/'),
  listTodas: () => api.get<Categoria[]>('/categorias/', { incluir_inactivos: true }),
  create: (data: Partial<Categoria>) => api.post<Categoria>('/categorias/', data),
  update: (id: number, data: Partial<Categoria>) => api.put<Categoria>(`/categorias/${id}`, data),
  remove: (id: number) => api.delete(`/categorias/${id}`),
}

export const marcasApi = {
  list: () => api.get<Marca[]>('/marcas/'),
  listTodas: () => api.get<Marca[]>('/marcas/', { incluir_inactivos: true }),
  create: (data: Partial<Marca>) => api.post<Marca>('/marcas/', data),
  update: (id: number, data: Partial<Marca>) => api.put<Marca>(`/marcas/${id}`, data),
  remove: (id: number) => api.delete(`/marcas/${id}`),
}

export const proveedoresApi = {
  list: () => api.get<Proveedor[]>('/proveedores/'),
  create: (data: Partial<Proveedor>) => api.post<Proveedor>('/proveedores/', data),
  update: (id: number, data: Partial<Proveedor>) => api.put<Proveedor>(`/proveedores/${id}`, data),
}

export const productosApi = {
  list: (q: { buscar?: string; id_categoria?: number; id_marca?: number } = {}) =>
    api.get<Producto[]>('/productos/', q),
  listAdmin: () => api.get<ProductoAdmin[]>('/productos/admin'),
  stockBajo: () => api.get<ProductoAdmin[]>('/productos/stock-bajo'),
  create: (data: ProductoInput) => api.post<ProductoAdmin>('/productos/', data),
  update: (id: number, data: Partial<ProductoInput>) => api.put<ProductoAdmin>(`/productos/${id}`, data),
  remove: (id: number) => api.delete(`/productos/${id}`),
}

export const finanzasApi = {
  monedas: () => api.get<Moneda[]>('/monedas/'),
  tasaVigente: (codigo_moneda: string) => api.get<Tasa>('/tasas/vigente', { codigo_moneda }),
  historial: (codigo_moneda?: string) => api.get<Tasa[]>('/tasas/', { codigo_moneda }),
  setTasa: (codigo_moneda: string, tasa_venta: string) =>
    api.post<Tasa>('/tasas/', { codigo_moneda, tasa_venta }),
}

export const ventasApi = {
  list: (q: { dia?: string; limite?: number } & Rango = {}) => api.get<Venta[]>('/ventas/', q),
  get: (id: number) => api.get<Venta>(`/ventas/${id}`),
  create: (data: VentaCreate) => api.post<Venta>('/ventas/', data),
  anular: (id: number) => api.post<Venta>(`/ventas/${id}/anular`),
  miResumen: (dia?: string) => api.get<ResumenVentas>('/ventas/mi-resumen', { dia }),
}

export const comprasApi = {
  list: (q: { id_proveedor?: number; pagado?: boolean; limite?: number } & Rango = {}) =>
    api.get<Compra[]>('/compras/', q),
  create: (data: CompraCreate) => api.post<Compra>('/compras/', data),
  setPagado: (id: number, pagado: boolean) => api.patch<Compra>(`/compras/${id}/pagado`, { pagado }),
  entradasRecientes: (limite = 10) => api.get<EntradaStock[]>('/compras/entradas-recientes', { limite }),
}

export const facturasApi = {
  list: (q: Rango = {}) => api.get<Factura[]>('/facturas/', q),
  upload: (archivo: File, id_compra?: number) => {
    const form = new FormData()
    form.append('archivo', archivo)
    if (id_compra) form.append('id_compra', String(id_compra))
    return api.post<Factura>('/facturas/', form)
  },
  archivo: (id: number) => api.blob(`/facturas/${id}/archivo`),
  remove: (id: number) => api.delete(`/facturas/${id}`),
}

export const reportesApi = {
  dashboard: () => api.get<Dashboard>('/reportes/dashboard'),
  serieVentas: (q: Rango & { agrupar: 'hora' | 'dia' }) => api.get<PuntoSerie[]>('/reportes/serie-ventas', q),
  topProductos: (q: Rango & { limite?: number } = {}) => api.get<TopProducto[]>('/reportes/top-productos', q),
  stockPorCategoria: () => api.get<StockCategoria[]>('/reportes/stock-por-categoria'),
  movimientosStock: (q: Rango = {}) => api.get<MovimientosStock>('/reportes/movimientos-stock', q),
  ventasPorCategoria: (q: Rango = {}) => api.get<VentasCategoria[]>('/reportes/ventas-por-categoria', q),
}
