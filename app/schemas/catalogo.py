import re
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.services.sku_service import normalizar_prefijo


def _prefijo_opcional(v: str | None) -> str | None:
    return None if v is None else normalizar_prefijo(v)


class CategoriaCreate(BaseModel):
    nombre: str = Field(min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)
    margen_ganancia: Decimal = Field(default=Decimal("0"), ge=0, le=999.99, max_digits=5, decimal_places=2)
    # Código para el SKU automático (2 a 5 letras). Si se omite, se deriva del nombre.
    prefijo_sku: str | None = None

    validar_prefijo = field_validator("prefijo_sku")(_prefijo_opcional)


class CategoriaUpdate(BaseModel):
    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    descripcion: str | None = Field(default=None, max_length=255)
    estado: int | None = Field(default=None, ge=0, le=1)
    margen_ganancia: Decimal | None = Field(
        default=None, ge=0, le=999.99, max_digits=5, decimal_places=2
    )
    # Cambiarlo solo afecta a los productos nuevos; los SKU existentes no se modifican.
    prefijo_sku: str | None = None

    validar_prefijo = field_validator("prefijo_sku")(_prefijo_opcional)


class CategoriaRead(BaseModel):
    id_categoria: int
    nombre: str
    descripcion: str | None
    estado: int
    margen_ganancia: Decimal
    prefijo_sku: str | None = None

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


# Letras de RIF en Venezuela: V (venezolano), E (extranjero), J (jurídico),
# P (pasaporte), G (gobierno), C (comunal).
RIF_PATTERN = re.compile(r"^([VEJPGC])[-\s]?(\d{5,9})(?:[-\s]?(\d))?$")


def normalize_rif(value: str) -> str:
    """Valida que el RIF empiece con su letra y lo deja como J-12345678-9."""
    rif = value.strip().upper()
    if not rif:
        raise ValueError("El RIF es obligatorio.")
    if not rif[0].isalpha():
        raise ValueError("El RIF debe comenzar con una letra (V, E, J, P, G o C), p. ej. J-12345678-9.")
    match = RIF_PATTERN.match(rif)
    if match is None:
        raise ValueError("RIF inválido: use una letra V, E, J, P, G o C seguida de los números, p. ej. J-12345678-9.")
    letra, numero, verificador = match.groups()
    if verificador is None and len(numero) == 9:
        numero, verificador = numero[:8], numero[8]
    return f"{letra}-{numero}" + (f"-{verificador}" if verificador else "")


def check_telefono(value: str) -> str:
    telefono = " ".join(value.split())
    if not telefono:
        raise ValueError("El teléfono es obligatorio.")
    if not re.fullmatch(r"[\d\s+()\-.]+", telefono):
        raise ValueError("El teléfono solo puede tener números, espacios, +, -, ( y ).")
    if not 7 <= sum(c.isdigit() for c in telefono) <= 15:
        raise ValueError("El teléfono debe tener entre 7 y 15 dígitos.")
    return telefono


class ProveedorBase(BaseModel):
    contacto: str | None = Field(default=None, max_length=100)
    ciudad: str | None = Field(default=None, max_length=60)
    condiciones: str | None = Field(default=None, max_length=120)


class ProveedorCreate(ProveedorBase):
    nombre: str = Field(min_length=1, max_length=100)
    rif: str = Field(max_length=20)
    telefono: str = Field(max_length=20)
    correo: EmailStr = Field(max_length=100)

    validar_rif = field_validator("rif")(normalize_rif)
    validar_telefono = field_validator("telefono")(check_telefono)


class ProveedorUpdate(ProveedorBase):
    """Los campos obligatorios no pueden enviarse vacíos ni como null (ver catalogo.py)."""

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    rif: str | None = Field(default=None, max_length=20)
    telefono: str | None = Field(default=None, max_length=20)
    correo: EmailStr | None = Field(default=None, max_length=100)
    estado: int | None = Field(default=None, ge=0, le=1)

    @field_validator("rif")
    @classmethod
    def validar_rif(cls, v: str | None) -> str | None:
        return None if v is None else normalize_rif(v)

    @field_validator("telefono")
    @classmethod
    def validar_telefono(cls, v: str | None) -> str | None:
        return None if v is None else check_telefono(v)


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
