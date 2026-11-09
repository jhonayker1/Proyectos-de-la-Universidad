from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class DetalleVentaCreate(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(default=1, gt=0)


class VentaCreate(BaseModel):
    # Moneda en la que paga el cliente (código de la tabla monedas, p. ej. USD o VES).
    codigo_moneda_pago: str = Field(min_length=3, max_length=3)
    referencia_pago: str | None = Field(default=None, max_length=50)
    detalles: list[DetalleVentaCreate] = Field(min_length=1)


class DetalleVentaRead(BaseModel):
    id_detalle: int
    id_producto: int
    nombre_producto_snapshot: str
    cantidad: int
    precio_unitario_usd: Decimal
    subtotal_usd: Decimal

    model_config = ConfigDict(from_attributes=True)


class VentaRead(BaseModel):
    id_venta: int
    numero_factura: str
    id_usuario: int
    nombre_usuario: str | None = None
    id_moneda_pago: int
    codigo_moneda_pago: str
    monto_total_usd: Decimal
    monto_total_moneda: Decimal
    tasa_aplicada: Decimal
    referencia_pago: str | None
    estado: str
    fecha_venta: datetime | None
    detalles: list[DetalleVentaRead]


class TotalPorMoneda(BaseModel):
    codigo_moneda: str
    cantidad_ventas: int
    monto_total_moneda: Decimal


class ResumenVentas(BaseModel):
    dia: date
    cantidad_ventas: int
    articulos_vendidos: int = 0
    monto_total_usd: Decimal
    por_moneda: list[TotalPorMoneda]


class VentasPorUsuario(BaseModel):
    id_usuario: int
    nombre_completo: str
    cantidad_ventas: int
    monto_total_usd: Decimal


class ReporteVentas(ResumenVentas):
    ventas_anuladas: int
    por_usuario: list[VentasPorUsuario]


class PuntoSerie(BaseModel):
    """Un punto de la serie de ventas: 'etiqueta' es la hora (08) o el día (2026-11-03)."""

    etiqueta: str
    cantidad_ventas: int
    articulos_vendidos: int
    monto_total_usd: Decimal


class TopProducto(BaseModel):
    id_producto: int
    nombre_producto: str
    nombre_categoria: str | None
    unidades: int
    monto_total_usd: Decimal


class StockCategoria(BaseModel):
    id_categoria: int
    nombre_categoria: str
    productos: int
    unidades: int
    valor_costo_usd: Decimal
    bajo_stock: int
    agotados: int


class IngresoProducto(BaseModel):
    id_producto: int
    nombre_producto: str
    unidades: int


class MovimientosStock(BaseModel):
    """Entradas (compras) y salidas (ventas completadas) de unidades en el rango."""

    desde: date
    hasta: date
    entradas: int
    salidas: int
    neto: int
    ingresos_por_producto: list[IngresoProducto]


class VentasCategoria(BaseModel):
    id_categoria: int | None
    nombre_categoria: str
    unidades: int
    monto_total_usd: Decimal


class Dashboard(BaseModel):
    dia: date
    ventas_hoy_usd: Decimal
    ventas_hoy_cantidad: int
    articulos_hoy: int
    ventas_mes_usd: Decimal
    ventas_mes_anterior_usd: Decimal
    productos_activos: int
    unidades_en_stock: int
    valor_inventario_usd: Decimal
    productos_bajo_stock: int
    productos_agotados: int
