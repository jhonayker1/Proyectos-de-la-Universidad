from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

RolKey = Literal["admin", "cashier"]


def check_bcrypt_length(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes.")
    return password


class UsuarioCreate(BaseModel):
    nombre_completo: str = Field(min_length=3, max_length=100)
    correo: EmailStr = Field(max_length=100)
    password: str = Field(min_length=8)
    telefono: str | None = Field(default=None, max_length=20)
    permisos: str | None = Field(default=None, max_length=255)
    rol: RolKey = "cashier"

    _check_password = field_validator("password")(check_bcrypt_length)


class UsuarioUpdate(BaseModel):
    """Edición sin contraseña (se cambia con /usuarios/{id}/password)."""

    nombre_completo: str | None = Field(default=None, min_length=3, max_length=100)
    correo: EmailStr | None = Field(default=None, max_length=100)
    telefono: str | None = Field(default=None, max_length=20)
    permisos: str | None = Field(default=None, max_length=255)


class PasswordReset(BaseModel):
    password: str = Field(min_length=8)

    _check_password = field_validator("password")(check_bcrypt_length)


class RecuperacionSolicitud(BaseModel):
    correo: str = Field(min_length=3, max_length=100)


class RecuperacionConfirmacion(BaseModel):
    correo: str = Field(min_length=3, max_length=100)
    codigo: str = Field(pattern=r"^\s*\d{6}\s*$")
    password: str = Field(min_length=8)

    _check_password = field_validator("password")(check_bcrypt_length)


class UsuarioEstadoUpdate(BaseModel):
    activo: bool


class LoginRequest(BaseModel):
    correo: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=1)


class UsuarioRead(BaseModel):
    id_usuario: int
    id_rol: int
    rol: RolKey | None
    nombre_completo: str
    correo: str
    telefono: str | None
    permisos: str | None = None
    estado: int
    fecha_creacion: datetime | None

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: RolKey
    id_usuario: int
    nombre_completo: str
