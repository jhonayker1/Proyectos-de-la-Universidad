from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProductoCreate(BaseModel):
    # Si se omite, se genera según la categoría: LUB-27 -> LUB-28 (ver sku_service).
    sku: str | None = Field(default=None, min_length=1, max_length=50)
    nombre: str = Field(min_length=1, max_length=150)
    id_categoria: int = Field(gt=0)
    id_marca: int | None = Field(default=None, gt=0)
    id_proveedor: int | None = Field(default=None, gt=0)
    precio_distribuidor: Decimal = Field(default=Decimal("0"), ge=0, max_digits=10, decimal_places=2)
    # Si se omite, se calcula: precio_distribuidor × (1 + margen / 100).
    precio_usd: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    # Margen propio (%); si se omite, se usa el de la categoría.
    margen_pct: Decimal | None = Field(default=None, ge=0, le=999.99, max_digits=5, decimal_places=2)
    ubicacion: str | None = Field(default=None, max_length=80)
    stock_actual: int = Field(default=0, ge=0)
    stock_minimo: int = Field(default=5, ge=0)


class ProductoUpdate(BaseModel):
    """Si cambia el costo o el margen y no se envía precio_usd, el precio se recalcula."""

    sku: str | None = Field(default=None, min_length=1, max_length=50)
    nombre: str | None = Field(default=None, min_length=1, max_length=150)
    id_categoria: int | None = Field(default=None, gt=0)
    id_marca: int | None = Field(default=None, gt=0)
    id_proveedor: int | None = Field(default=None, gt=0)
    precio_distribuidor: Decimal | None = Field(
        default=None, ge=0, max_digits=10, decimal_places=2
    )
    precio_usd: Decimal | None = Field(default=None, ge=0, max_digits=10, decimal_places=2)
    # null explícito = volver a usar el margen de la categoría.
    margen_pct: Decimal | None = Field(default=None, ge=0, le=999.99, max_digits=5, decimal_places=2)
    ubicacion: str | None = Field(default=None, max_length=80)
    stock_actual: int | None = Field(default=None, ge=0)
    stock_minimo: int | None = Field(default=None, ge=0)
    estado: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def reject_null_required_fields(self) -> "ProductoUpdate":
        required = {
            "sku",
            "nombre",
            "id_categoria",
            "precio_distribuidor",
            "precio_usd",
            "stock_actual",
            "stock_minimo",
            "estado",
        }
        for field in required & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} no puede ser null.")
        return self


class ProductoRead(BaseModel):
    """precio_usd y, si hay tasa vigente de la moneda local, precio_local."""

    id_producto: int
    sku: str
    nombre: str
    id_categoria: int
    nombre_categoria: str | None = None
    id_marca: int | None
    nombre_marca: str | None = None
    precio_usd: Decimal
    precio_local: Decimal | None = None
    stock_actual: int
    stock_minimo: int
    estado: str
    ubicacion: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductoAdminRead(ProductoRead):
    id_proveedor: int | None
    nombre_proveedor: str | None = None
    precio_distribuidor: Decimal
    margen_pct: Decimal | None = None
    # Margen que se aplica de verdad (el propio o el de la categoría).
    margen_efectivo: Decimal | None = None
    fecha_ingreso: datetime | None
