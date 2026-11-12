from datetime import datetime

from pydantic import BaseModel


class CambioAuditado(BaseModel):
    campo: str
    etiqueta: str
    antes: str | None
    despues: str | None


class RegistroAuditoria(BaseModel):
    id_auditoria: int
    fecha: datetime
    id_usuario: int | None
    nombre_usuario: str
    rol: str | None
    modulo: str
    modulo_etiqueta: str
    accion: str
    accion_etiqueta: str
    entidad: str
    id_registro: str | None
    referencia: str | None
    descripcion: str
    cambios: list[CambioAuditado]
    origen: str | None
    ruta: str | None
    ip: str | None
    id_operacion: str | None


class PaginaAuditoria(BaseModel):
    total: int
    pagina: int
    por_pagina: int
    items: list[RegistroAuditoria]


class Opcion(BaseModel):
    clave: str
    etiqueta: str


class UsuarioAuditado(BaseModel):
    id_usuario: int | None
    nombre: str


class FiltrosAuditoria(BaseModel):
    modulos: list[Opcion]
    acciones: list[Opcion]
    usuarios: list[UsuarioAuditado]
