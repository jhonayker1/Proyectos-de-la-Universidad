from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DetalleCompraCreate(BaseModel):
    id_producto: int = Field(gt=0)
    cantidad: int = Field(gt=0)
    costo_unitario_usd: Decimal = Field(ge=0, max_digits=10, decimal_places=2)


class CompraCreate(BaseModel):
    """Con detalles, la compra suma stock. Sin detalles, solo registra la factura."""

    id_proveedor: int = Field(gt=0)
    numero_factura: str | None = Field(default=None, max_length=30)
    fecha: date | None = None
    descripcion: str | None = Field(default=None, max_length=255)
    # Si se omite, es la suma de los detalles.
    monto_usd: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    pagado: bool = False
    # Actualiza el costo (precio_distribuidor) de cada producto y su precio por margen.
    actualizar_costos: bool = True
    detalles: list[DetalleCompraCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_amount_or_items(self) -> "CompraCreate":
        if self.monto_usd is None and not self.detalles:
            raise ValueError("Indique monto_usd o al menos un detalle.")
        return self


class CompraPagadoUpdate(BaseModel):
    pagado: bool


class DetalleCompraRead(BaseModel):
    id_detalle_compra: int
    id_producto: int
    sku: str
    nombre_producto: str
    cantidad: int
    costo_unitario_usd: Decimal


class CompraRead(BaseModel):
    id_compra: int
    id_proveedor: int
    nombre_proveedor: str
    numero_factura: str | None
    fecha: date
    descripcion: str | None
    monto_usd: Decimal
    pagado: bool
    id_usuario: int
    fecha_registro: datetime | None
    detalles: list[DetalleCompraRead]


class EntradaStockRead(BaseModel):
    id_compra: int
    fecha: date
    id_producto: int
    nombre_producto: str
    cantidad: int
    nombre_proveedor: str


class FacturaRead(BaseModel):
    id_factura_img: int
    nombre_original: str
    tipo_mime: str
    tamano_bytes: int
    id_compra: int | None
    id_usuario: int
    fecha_subida: datetime | None

    model_config = ConfigDict(from_attributes=True)
