from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CategoriaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)
    margen_ganancia: Decimal = Field(default=Decimal("0"), ge=0, le=999.99, max_digits=5, decimal_places=2)


class CategoriaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)
    estado: int | None = Field(default=None, ge=0, le=1)
    margen_ganancia: Decimal | None = Field(
        default=None, ge=0, le=999.99, max_digits=5, decimal_places=2
    )


class CategoriaRead(BaseModel):
    id_categoria: int
    nombre: str
    descripcion: str | None
    estado: int
    margen_ganancia: Decimal

    model_config = ConfigDict(from_attributes=True)


class MarcaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    pais_origen: str | None = Field(default=None, max_length=50)


class MarcaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    pais_origen: str | None = Field(default=None, max_length=50)
    estado: int | None = Field(default=None, ge=0, le=1)


class MarcaRead(BaseModel):
    id_marca: int
    nombre: str
    pais_origen: str | None
    estado: int

    model_config = ConfigDict(from_attributes=True)


class ProveedorBase(BaseModel):
    telefono: str | None = Field(default=None, max_length=20)
    rif: str | None = Field(default=None, max_length=20)
    contacto: str | None = Field(default=None, max_length=100)
    correo: EmailStr | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=60)
    condiciones: str | None = Field(default=None, max_length=120)


class ProveedorCreate(ProveedorBase):
    nombre: str = Field(min_length=1, max_length=100)


class ProveedorUpdate(ProveedorBase):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    estado: int | None = Field(default=None, ge=0, le=1)


class ProveedorRead(BaseModel):
    id_proveedor: int
    nombre: str
    telefono: str | None
    rif: str | None
    contacto: str | None
    correo: str | None
    ciudad: str | None
    condiciones: str | None
    estado: int

    model_config = ConfigDict(from_attributes=True)
