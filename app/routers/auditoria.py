"""Bitácora de auditoría: solo consulta y exportación (no hay rutas para editar ni borrar;
en PostgreSQL un trigger además rechaza UPDATE/DELETE sobre la tabla)."""

import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_now
from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.auditoria import Auditoria
from app.models.usuarios import Usuario
from app.schemas.auditoria import ExportacionAuditoria, FiltrosAuditoria, PaginaAuditoria
from app.services.auditoria_service import ACCIONES, MODULOS, registrar

router = APIRouter(
    prefix="/auditoria",
    tags=["auditoría"],
    dependencies=[Depends(require_roles(["admin", "gestor"]))],
)

MAX_EXPORTAR = 100_000
MODULOS_GESTOR = {"inventario", "categorias", "marcas", "proveedores", "compras"}


class Filtros:
    """Los mismos filtros para la consulta y la exportación."""

    def __init__(
        self,
        desde: date | None = Query(default=None, description="Desde el día (incluido)."),
        hasta: date | None = Query(default=None, description="Hasta el día (incluido)."),
        modulo: str | None = Query(default=None, max_length=30),
        accion: str | None = Query(default=None, max_length=30),
        id_usuario: int | None = Query(default=None, description="0 = acciones del sistema."),
        entidad: str | None = Query(default=None, max_length=40),
        id_registro: str | None = Query(default=None, max_length=40),
        id_operacion: str | None = Query(default=None, max_length=32),
        buscar: str | None = Query(default=None, max_length=100, description="En descripción, referencia o usuario."),
    ):
        if desde and hasta and desde > hasta:
            raise HTTPException(status_code=422, detail="La fecha 'desde' es posterior a 'hasta'.")
        self.desde, self.hasta, self.modulo, self.accion = desde, hasta, modulo, accion
        self.id_usuario, self.entidad, self.id_registro = id_usuario, entidad, id_registro
        self.id_operacion, self.buscar = id_operacion, (buscar or "").strip() or None

    def aplicar(self, query: SAQuery) -> SAQuery:
        if self.desde:
            query = query.filter(Auditoria.fecha >= day_bounds(self.desde)[0])
        if self.hasta:
            query = query.filter(Auditoria.fecha < day_bounds(self.hasta)[1])
        for columna, valor in ((Auditoria.modulo, self.modulo), (Auditoria.accion, self.accion),
                               (Auditoria.entidad, self.entidad), (Auditoria.id_registro, self.id_registro),
                               (Auditoria.id_operacion, self.id_operacion)):
            if valor:
                query = query.filter(columna == valor)
        if self.id_usuario is not None:
            query = query.filter(
                Auditoria.id_usuario.is_(None) if self.id_usuario == 0 else Auditoria.id_usuario == self.id_usuario
            )
        if self.buscar:
            patron = f"%{self.buscar}%"
            query = query.filter(or_(Auditoria.descripcion.ilike(patron), Auditoria.referencia.ilike(patron),
                                     Auditoria.nombre_usuario.ilike(patron)))
        return query

    def resumen(self) -> str:
        partes = [f"{k}={v}" for k, v in vars(self).items() if v not in (None, "")]
        return ", ".join(partes) or "sin filtros"


def _cambios(texto: str | None) -> list[dict]:
    try:
        return json.loads(texto) if texto else []
    except ValueError:
        return []


def _leer(a: Auditoria) -> dict:
    return {
        "id_auditoria": a.id_auditoria, "fecha": a.fecha, "id_usuario": a.id_usuario,
        "nombre_usuario": a.nombre_usuario, "rol": a.rol, "modulo": a.modulo,
        "modulo_etiqueta": MODULOS.get(a.modulo, a.modulo), "accion": a.accion,
        "accion_etiqueta": ACCIONES.get(a.accion, a.accion), "entidad": a.entidad,
        "id_registro": a.id_registro, "referencia": a.referencia, "descripcion": a.descripcion,
        "cambios": _cambios(a.cambios), "origen": a.origen, "ruta": a.ruta, "ip": a.ip,
        "id_operacion": a.id_operacion,
    }


@router.get("/", response_model=PaginaAuditoria)
def list_audit(
    filtros: Filtros = Depends(),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["admin", "gestor"])),
) -> dict:
    query = filtros.aplicar(db.query(Auditoria))
    if current_user.rol == "gestor":
        if filtros.modulo and filtros.modulo not in MODULOS_GESTOR:
            raise HTTPException(status_code=403, detail="No tienes permisos para consultar ese módulo.")
        query = query.filter(Auditoria.modulo.in_(MODULOS_GESTOR))
    total = query.count()
    filas = (query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc())
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all())
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": [_leer(a) for a in filas]}


@router.get("/filtros", response_model=FiltrosAuditoria)
def audit_filters(
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["admin", "gestor"])),
) -> dict:
    """Opciones para los filtros; los usuarios salen de la bitácora (incluye eliminados)."""
    usuarios = {}
    query = db.query(Auditoria.id_usuario, Auditoria.nombre_usuario)
    if current_user.rol == "gestor":
        query = query.filter(Auditoria.modulo.in_(MODULOS_GESTOR))
    for id_usuario, nombre in query.distinct():
        usuarios.setdefault(id_usuario, nombre)  # si cambió de nombre, basta uno
    return {
        "modulos": [
            {"clave": k, "etiqueta": v}
            for k, v in MODULOS.items()
            if current_user.rol == "admin" or k in MODULOS_GESTOR
        ],
        "acciones": [{"clave": k, "etiqueta": v} for k, v in ACCIONES.items()],
        "usuarios": sorted(
            ({"id_usuario": i, "nombre": n} for i, n in usuarios.items()),
            key=lambda u: (u["id_usuario"] is None, u["nombre"].lower()),
        ),
    }


@router.get("/exportar", response_model=ExportacionAuditoria)
def export_audit(
    formato: Literal["pdf"] = Query(default="pdf"),
    filtros: Filtros = Depends(),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles(["admin"])),
):
    """Prepara los registros para el PDF (máximo 100 000) y registra la exportación."""
    query = filtros.aplicar(db.query(Auditoria))
    total = query.count()
    if total > MAX_EXPORTAR:
        raise HTTPException(
            status_code=413,
            detail=f"Hay {total} registros; el máximo por exportación es {MAX_EXPORTAR}. Acote las fechas o los filtros.",
        )
    filas = query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc()).all()
    nombre = f"auditoria_{local_now():%Y%m%d_%H%M}.pdf"

    registrar(db, "auditoria", "exportar", "bitácora",
              f"Exportación de la auditoría a PDF: {total} registro(s) ({filtros.resumen()}).",
              referencia=nombre)
    db.commit()
    return {"total": total, "items": [_leer(a) for a in filas]}
