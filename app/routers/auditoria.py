"""Bitácora de auditoría: solo consulta y exportación (no hay rutas para editar ni borrar;
en PostgreSQL un trigger además rechaza UPDATE/DELETE sobre la tabla)."""

import csv
import io
import json
from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font, PatternFill
from sqlalchemy import or_
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_now
from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.auditoria import Auditoria
from app.models.usuarios import Usuario
from app.schemas.auditoria import FiltrosAuditoria, PaginaAuditoria
from app.services.auditoria_service import ACCIONES, MODULOS, registrar

router = APIRouter(
    prefix="/auditoria",
    tags=["auditoría"],
    dependencies=[Depends(require_roles(["admin"]))],
)

MAX_EXPORTAR = 100_000
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
COLUMNAS = ("Fecha", "Usuario", "Rol", "Módulo", "Acción", "Entidad", "ID registro", "Referencia",
            "Descripción", "Cambios", "Origen", "Ruta", "IP", "Operación")


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
) -> dict:
    query = filtros.aplicar(db.query(Auditoria))
    total = query.count()
    filas = (query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc())
             .offset((pagina - 1) * por_pagina).limit(por_pagina).all())
    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": [_leer(a) for a in filas]}


@router.get("/filtros", response_model=FiltrosAuditoria)
def audit_filters(db: Session = Depends(get_db)) -> dict:
    """Opciones para los filtros; los usuarios salen de la bitácora (incluye eliminados)."""
    usuarios = {}
    for id_usuario, nombre in db.query(Auditoria.id_usuario, Auditoria.nombre_usuario).distinct():
        usuarios.setdefault(id_usuario, nombre)  # si cambió de nombre, basta uno
    return {
        "modulos": [{"clave": k, "etiqueta": v} for k, v in MODULOS.items()],
        "acciones": [{"clave": k, "etiqueta": v} for k, v in ACCIONES.items()],
        "usuarios": sorted(
            ({"id_usuario": i, "nombre": n} for i, n in usuarios.items()),
            key=lambda u: (u["id_usuario"] is None, u["nombre"].lower()),
        ),
    }


def _texto_cambios(a: Auditoria) -> str:
    return "\n".join(
        f"{c.get('etiqueta')}: {c.get('antes') or '—'} → {c.get('despues') or '—'}"
        for c in _cambios(a.cambios)
    )


def _valores(a: Auditoria) -> list:
    return [
        a.fecha.strftime("%Y-%m-%d %H:%M:%S") if a.fecha else None, a.nombre_usuario, a.rol,
        MODULOS.get(a.modulo, a.modulo), ACCIONES.get(a.accion, a.accion), a.entidad, a.id_registro,
        a.referencia, a.descripcion, _texto_cambios(a), a.origen, a.ruta, a.ip, a.id_operacion,
    ]


def _seguro_csv(valor) -> str:
    """Evita que Excel interprete un texto como fórmula al abrir el CSV."""
    texto = "" if valor is None else str(valor)
    return "'" + texto if texto[:1] in ("=", "+", "-", "@") else texto


@router.get("/exportar")
def export_audit(
    formato: Literal["xlsx", "csv"] = Query(default="xlsx"),
    filtros: Filtros = Depends(),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles(["admin"])),
):
    """Exporta los registros que cumplen los filtros (máximo 100 000). La exportación
    misma queda registrada en la auditoría."""
    query = filtros.aplicar(db.query(Auditoria))
    total = query.count()
    if total > MAX_EXPORTAR:
        raise HTTPException(
            status_code=413,
            detail=f"Hay {total} registros; el máximo por exportación es {MAX_EXPORTAR}. Acote las fechas o los filtros.",
        )
    filas = query.order_by(Auditoria.fecha.desc(), Auditoria.id_auditoria.desc()).yield_per(1000)
    nombre = f"auditoria_{local_now():%Y%m%d_%H%M}.{formato}"

    if formato == "csv":
        salida = io.StringIO()
        escritor = csv.writer(salida, delimiter=";")
        escritor.writerow(COLUMNAS)
        for a in filas:
            escritor.writerow([_seguro_csv(v) for v in _valores(a)])
        contenido = "﻿" + salida.getvalue()  # BOM: Excel en español abre bien los acentos
    else:
        libro = Workbook(write_only=True)
        hoja = libro.create_sheet("Auditoría")
        for i, ancho in enumerate((18, 22, 14, 14, 18, 16, 10, 34, 70, 60, 34, 28, 14, 34), start=1):
            hoja.column_dimensions[chr(64 + i)].width = ancho
        hoja.freeze_panes = "A2"
        titulo, fondo = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="4F46E5")
        encabezados = []
        for c in COLUMNAS:
            celda = WriteOnlyCell(hoja, value=c)
            celda.font, celda.fill = titulo, fondo
            encabezados.append(celda)
        hoja.append(encabezados)
        for a in filas:
            fila = []
            for v in _valores(a):
                celda = WriteOnlyCell(hoja, value=v)
                if isinstance(v, str) and v.startswith(("=", "+", "-", "@")):
                    celda.data_type = "s"  # texto, nunca una fórmula
                fila.append(celda)
            hoja.append(fila)
        buffer = io.BytesIO()
        libro.save(buffer)
        contenido = buffer.getvalue()

    registrar(db, "auditoria", "exportar", "bitácora",
              f"Exportación de la auditoría a {formato.upper()}: {total} registro(s) ({filtros.resumen()}).",
              referencia=nombre)
    db.commit()
    return Response(
        content=contenido.encode("utf-8") if isinstance(contenido, str) else contenido,
        media_type=XLSX if formato == "xlsx" else "text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )
