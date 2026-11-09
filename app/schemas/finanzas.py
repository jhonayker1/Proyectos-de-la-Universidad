from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class MonedaRead(BaseModel):
    id_moneda: int
    codigo: str
    nombre: str
    simbolo: str | None
    es_base: int
    estado: int

    model_config = ConfigDict(from_attributes=True)


class TasaCambioCreate(BaseModel):
    codigo_moneda: str = Field(min_length=3, max_length=3)
    tasa_venta: Decimal = Field(gt=0, max_digits=15, decimal_places=4)
    # Si no se indica, se usa la misma tasa de venta.
    tasa_compra: Decimal | None = Field(default=None, gt=0, max_digits=15, decimal_places=4)


class TasaCambioRead(BaseModel):
    id_tasa: int
    id_moneda: int
    codigo_moneda: str
    tasa_compra: Decimal
    tasa_venta: Decimal
    fecha_actualizacion: datetime | None
    estado: int
