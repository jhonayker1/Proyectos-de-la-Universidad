"""Reportes operativos (administrador y gestor). Ninguno incluye utilidad ni márgenes:
eso es información financiera, exclusiva del administrador."""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel


class AlertaStock(BaseModel):
    id_producto: int
    sku: str
    nombre: str
    stock_actual: int
    stock_minimo: int
    estado: str


class ResumenGestor(BaseModel):
    dia: date
    ventas_hoy: int
    articulos_hoy: int
    monto_hoy_usd: Decimal
    compras_hoy: int
    unidades_entrada_hoy: int
    ajustes_hoy: int
    productos_bajo_stock: int
    productos_agotados: int
    stock_critico: list[AlertaStock]
    cuentas_por_pagar_cantidad: int
    cuentas_por_pagar_usd: Decimal


class Movimiento(BaseModel):
    fecha: datetime
    tipo: Literal["entrada", "salida", "devolucion", "ajuste"]
    id_producto: int
    sku: str
    producto: str
    cantidad: int  # positivo entra al inventario, negativo sale
    referencia: str
    usuario: str | None
    detalle: str | None = None


class Kardex(BaseModel):
    desde: date
    hasta: date
    entradas: int
    salidas: int
    devoluciones: int
    ajustes: int  # neto (con signo)
    movimientos: list[Movimiento]
    truncado: bool


class CompraPendiente(BaseModel):
    id_compra: int
    numero_factura: str | None
    fecha: date
    monto_usd: Decimal
    dias: int


class CuentaPorPagar(BaseModel):
    id_proveedor: int
    proveedor: str
    rif: str | None
    telefono: str | None
    compras: int
    monto_usd: Decimal
    mas_antigua: date
    detalle: list[CompraPendiente]


class CuentasPorPagar(BaseModel):
    total_usd: Decimal
    compras: int
    proveedores: list[CuentaPorPagar]
