"""Bitácora de auditoría: solo consulta y exportación (no hay rutas para editar ni borrar;
en PostgreSQL un trigger además rechaza UPDATE/DELETE sobre la tabla)."""

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_now
from app.core.dependencies import require_roles
from app.core.permisos import GESTION, SOLO_ADMIN
from app.database.session import get_db
from app.models.auditoria import Auditoria
from app.models.usuarios import Usuario
from app.schemas.auditoria import ExportacionAuditoria, FiltrosAuditoria, PaginaAuditoria
from app.services.auditoria_service import ACCIONES, MODULOS, MODULOS_OPERATIVOS, ROLES, registrar

router = APIRouter(
    prefix="/auditoria",
    tags=["auditoría"],
    dependencies=[Depends(require_roles(GESTION))],
)

# El reporte se entrega en PDF (no editable); más filas que esto ya no es legible impreso.
MAX_EXPORTAR = 5000


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
        usuario: Usuario = Depends(require_roles(GESTION)),
    ):
        if desde and hasta and desde > hasta:
            raise HTTPException(status_code=422, detail="La fecha 'desde' es posterior a 'hasta'.")
        self.desde, self.hasta, self.modulo, self.accion = desde, hasta, modulo, accion
        self.id_usuario, self.entidad, self.id_registro = id_usuario, entidad, id_registro
        self.id_operacion, self.buscar = id_operacion, (buscar or "").strip() or None
        # El gestor solo ve los módulos operativos (no usuarios, tasas, categorías ni la
        # propia auditoría); el administrador ve todo.
        self._permitidos = modulos_visibles(usuario)
        if self.modulo and self._permitidos is not None and self.modulo not in self._permitidos:
            raise HTTPException(status_code=403, detail="No tienes permisos para ver la auditoría de ese módulo.")

    def aplicar(self, query: SAQuery) -> SAQuery:
        if self._permitidos is not None:
            query = query.filter(Auditoria.modulo.in_(sorted(self._permitidos)))
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
        partes = [f"{k}={v}" for k, v in vars(self).items() if not k.startswith("_") and v not in (None, "")]
        return ", ".join(partes) or "sin filtros"


def modulos_visibles(usuario: Usuario) -> frozenset[str] | None:
    """None = todos los módulos (administrador)."""
    return None if usuario.rol in SOLO_ADMIN else MODULOS_OPERATIVOS


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
) -> dict:
    query = filtros.aplicar(db.query(Auditoria))
    total = query.count()
    filas = (query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc())
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all())
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": [_leer(a) for a in filas]}


@router.get("/filtros", response_model=FiltrosAuditoria)
def audit_filters(db: Session = Depends(get_db), usuario: Usuario = Depends(require_roles(GESTION))) -> dict:
    """Opciones para los filtros; los usuarios salen de la bitácora (incluye eliminados)."""
    permitidos = modulos_visibles(usuario)
    consulta = db.query(Auditoria.id_usuario, Auditoria.nombre_usuario)
    if permitidos is not None:
        consulta = consulta.filter(Auditoria.modulo.in_(sorted(permitidos)))
    usuarios = {}
    for id_usuario, nombre in consulta.distinct():
        usuarios.setdefault(id_usuario, nombre)  # si cambió de nombre, basta uno
    return {
        "modulos": [{"clave": k, "etiqueta": v} for k, v in MODULOS.items() if permitidos is None or k in permitidos],
        "acciones": [{"clave": k, "etiqueta": v} for k, v in ACCIONES.items()],
        "usuarios": sorted(
            ({"id_usuario": i, "nombre": n} for i, n in usuarios.items()),
            key=lambda u: (u["id_usuario"] is None, u["nombre"].lower()),
        ),
    }


@router.get("/exportar", response_model=ExportacionAuditoria)
def export_audit(
    filtros: Filtros = Depends(),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(require_roles(GESTION)),
) -> dict:
    """Registros que cumplen los filtros (máximo 5000) para el reporte en PDF, que arma el
    navegador como documento no editable. La exportación queda registrada en la auditoría."""
    query = filtros.aplicar(db.query(Auditoria))
    total = query.count()
    if total > MAX_EXPORTAR:
        raise HTTPException(
            status_code=413,
            detail=f"Hay {total} registros; el reporte en PDF admite hasta {MAX_EXPORTAR}. Acote las fechas o los filtros.",
        )
    ahora = local_now()
    nombre = f"auditoria_{ahora:%Y%m%d_%H%M}.pdf"
    registros = [_leer(a) for a in query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc())]
    registrar(db, "auditoria", "exportar", "bitácora",
              f"Exportación de la auditoría a PDF: {total} registro(s) ({filtros.resumen()}).",
              referencia=nombre)
    db.commit()
    return {
        "generado": ahora, "generado_por": usuario.nombre_completo,
        "rol": ROLES.get(usuario.rol or "", usuario.rol), "archivo": nombre, "total": total,
        "registros": registros,
    }
