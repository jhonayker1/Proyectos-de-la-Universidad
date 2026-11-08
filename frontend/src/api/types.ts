/** Tipos espejo de app/schemas/*. Los Decimal de Python llegan como string ("12.50"). */

export type Money = string
export type Rol = 'admin' | 'cashier'

export interface Token {
  access_token: string
  token_type: string
  rol: Rol
  id_usuario: number
  nombre_completo: string
}

export interface Usuario {
  id_usuario: number
  id_rol: number
  rol: Rol | null
  nombre_completo: string
  correo: string
  telefono: string | null
  permisos: string | null
  estado: number
  fecha_creacion: string | null
}

export interface UsuarioCreate {
  nombre_completo: string
  correo: string
  password: string
  telefono?: string | null
  permisos?: string | null
  rol?: Rol
}

export type UsuarioUpdate = Partial<Pick<Usuario, 'nombre_completo' | 'correo' | 'telefono' | 'permisos'>>

export interface Categoria {
  id_categoria: number
  nombre: string
  descripcion: string | null
  estado: number
  margen_ganancia: Money
}

export interface Marca {
  id_marca: number
  nombre: string
  pais_origen: string | null
  estado: number
}

export interface Proveedor {
  id_proveedor: number
  nombre: string
  telefono: string | null
  rif: string | null
  contacto: string | null
  correo: string | null
  ciudad: string | null
  condiciones: string | null
  estado: number
}

export type EstadoProducto = 'Disponible' | 'Bajo Stock' | 'Agotado' | 'Inactivo'

export interface Producto {
  id_producto: number
  sku: string
  nombre: string
  id_categoria: number
  nombre_categoria: string | null
  id_marca: number | null
  nombre_marca: string | null
  precio_usd: Money
  precio_local: Money | null
  stock_actual: number
  stock_minimo: number
  estado: EstadoProducto | string
  ubicacion: string | null
}

export interface ProductoAdmin extends Producto {
  id_proveedor: number | null
  nombre_proveedor: string | null
  precio_distribuidor: Money
  margen_pct: Money | null
  margen_efectivo: Money | null
  fecha_ingreso: string | null
}

export interface ProductoInput {
  sku: string
  nombre: string
  id_categoria: number
  id_marca: number | null
  id_proveedor: number | null
  precio_distribuidor: string
  precio_usd?: string | null
  margen_pct: string | null
  ubicacion: string | null
  stock_actual: number
  stock_minimo: number
  /** Solo al editar: 'Inactivo' da de baja; otro valor reactiva (el backend recalcula según stock). */
  estado?: string
}

export interface Moneda {
  id_moneda: number
  codigo: string
  nombre: string
  simbolo: string | null
  es_base: number
  estado: number
}

export interface Tasa {
  id_tasa: number
  id_moneda: number
  codigo_moneda: string
  tasa_compra: Money
  tasa_venta: Money
  fecha_actualizacion: string | null
  estado: number
}

export interface DetalleVenta {
  id_detalle: number
  id_producto: number
  nombre_producto_snapshot: string
  cantidad: number
  precio_unitario_usd: Money
  subtotal_usd: Money
}

export interface Venta {
  id_venta: number
  numero_factura: string
  id_usuario: number
  nombre_usuario: string | null
  id_moneda_pago: number
  codigo_moneda_pago: string
  monto_total_usd: Money
  monto_total_moneda: Money
  tasa_aplicada: Money
  referencia_pago: string | null
  estado: 'Completada' | 'Anulada' | string
  fecha_venta: string | null
  detalles: DetalleVenta[]
}

export interface VentaCreate {
  codigo_moneda_pago: string
  referencia_pago?: string | null
  detalles: { id_producto: number; cantidad: number }[]
}

export interface ResumenVentas {
  dia: string
  cantidad_ventas: number
  articulos_vendidos: number
  monto_total_usd: Money
  por_moneda: { codigo_moneda: string; cantidad_ventas: number; monto_total_moneda: Money }[]
}

export interface Dashboard {
  dia: string
  ventas_hoy_usd: Money
  ventas_hoy_cantidad: number
  articulos_hoy: number
  ventas_mes_usd: Money
  ventas_mes_anterior_usd: Money
  productos_activos: number
  unidades_en_stock: number
  valor_inventario_usd: Money
  productos_bajo_stock: number
  productos_agotados: number
}

export interface PuntoSerie {
  etiqueta: string
  cantidad_ventas: number
  articulos_vendidos: number
  monto_total_usd: Money
}

export interface TopProducto {
  id_producto: number
  nombre_producto: string
  nombre_categoria: string | null
  unidades: number
  monto_total_usd: Money
}

export interface StockCategoria {
  id_categoria: number
  nombre_categoria: string
  productos: number
  unidades: number
  valor_costo_usd: Money
  bajo_stock: number
  agotados: number
}

export interface MovimientosStock {
  desde: string
  hasta: string
  entradas: number
  salidas: number
  neto: number
  ingresos_por_producto: { id_producto: number; nombre_producto: string; unidades: number }[]
}

export interface VentasCategoria {
  id_categoria: number | null
  nombre_categoria: string
  unidades: number
  monto_total_usd: Money
}

export interface DetalleCompra {
  id_detalle_compra: number
  id_producto: number
  sku: string
  nombre_producto: string
  cantidad: number
  costo_unitario_usd: Money
}

export interface Compra {
  id_compra: number
  id_proveedor: number
  nombre_proveedor: string
  numero_factura: string | null
  fecha: string
  descripcion: string | null
  monto_usd: Money
  pagado: boolean
  id_usuario: number
  fecha_registro: string | null
  detalles: DetalleCompra[]
}

export interface CompraCreate {
  id_proveedor: number
  numero_factura?: string | null
  fecha?: string | null
  descripcion?: string | null
  monto_usd?: string | null
  pagado?: boolean
  actualizar_costos?: boolean
  detalles: { id_producto: number; cantidad: number; costo_unitario_usd: string }[]
}

export interface EntradaStock {
  id_compra: number
  fecha: string
  id_producto: number
  nombre_producto: string
  cantidad: number
  nombre_proveedor: string
}

export interface Factura {
  id_factura_img: number
  nombre_original: string
  tipo_mime: string
  tamano_bytes: number
  id_compra: number | null
  id_usuario: number
  fecha_subida: string | null
}
