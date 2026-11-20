"""Carga masiva de inventario desde Excel o CSV (solo administrador).

Flujo recomendado: subir con ``modo=validar`` (vista previa, no guarda nada), revisar el
mapeo de columnas y los errores, y volver a subir con ``modo=estricto`` o ``parcial``.
"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.usuarios import Usuario
from app.schemas.importacion import CampoImportable, ErrorImportacion, ResultadoImportacion
from app.services.importacion import ErrorDeArchivo, Opciones, importar
from app.services.importacion.esquema import campos
from app.services.importacion.reporte import plantilla, reporte_errores

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/productos/importar",
    tags=["importación de inventario"],
    dependencies=[Depends(require_roles(["admin"]))],
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
# .xls se deja pasar para que el lector explique cómo convertirlo.
EXTENSIONES = {".xlsx", ".xlsm", ".xls", ".csv", ".txt", ".tsv"}
_ERRORES = {
    413: {"model": ErrorImportacion, "description": "Archivo demasiado grande o con demasiadas filas."},
    415: {"model": ErrorImportacion, "description": "Formato no admitido o archivo dañado."},
    422: {"model": ErrorImportacion, "description": "Sin encabezados reconocibles, faltan columnas o parámetros inválidos."},
    409: {"model": ErrorImportacion, "description": "Conflicto con cambios simultáneos; no se guardó nada."},
}


VIGENCIA_REPORTE_HORAS = 24
_REPORTE_ID = re.compile(r"^[0-9a-f]{32}$")


def _reportes_dir() -> Path:
    path = settings.UPLOAD_DIR / "importaciones"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _guardar_reporte(contenido: bytes, id_usuario: int) -> str:
    """Guarda el reporte de esta importación para descargarlo después (el archivo subido
    no se guarda). Borra los reportes de más de 24 horas."""
    carpeta = _reportes_dir()
    limite = time.time() - VIGENCIA_REPORTE_HORAS * 3600
    for viejo in carpeta.glob("*.xlsx"):
        try:
            if viejo.stat().st_mtime < limite:
                viejo.unlink()
        except OSError:
            pass  # otro proceso lo borró o lo tiene abierto; se reintenta en la próxima
    reporte_id = uuid4().hex
    (carpeta / f"{id_usuario}-{reporte_id}.xlsx").write_bytes(contenido)
    return reporte_id


def _error(exc: ErrorDeArchivo) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.como_dict())


def _descarga(contenido: bytes, nombre: str) -> Response:
    return Response(
        content=contenido,
        media_type=XLSX,
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/campos", response_model=list[CampoImportable])
def list_import_fields() -> list[dict]:
    """Campos que se pueden importar, con sus tipos y límites (leídos del esquema) y los
    nombres de columna que se reconocen para cada uno."""
    return [c.como_dict() for c in campos()]


@router.get("/plantilla", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def download_template(db: Session = Depends(get_db)) -> Response:
    """Plantilla .xlsx con los encabezados, instrucciones y las listas de categorías,
    marcas y proveedores actuales."""
    return _descarga(plantilla(db), "plantilla_inventario.xlsx")


@router.post("", response_model=ResultadoImportacion, responses={**_ERRORES, 200: {"content": {XLSX: {}}}})
def import_inventory(
    archivo: UploadFile = File(..., description="Excel (.xlsx) o CSV"),
    modo: Literal["validar", "estricto", "parcial"] = Form(
        "validar",
        description="validar: solo revisa (no guarda). estricto: guarda solo si no hay ningún "
                    "error. parcial: guarda las filas válidas y reporta las demás.",
    ),
    si_existe: Literal["actualizar", "omitir", "error"] = Form(
        "actualizar", description="Qué hacer con los SKU que ya existen en el inventario."
    ),
    crear_faltantes: bool = Form(False, description="Crear las categorías y marcas que no existan."),
    id_categoria_defecto: int | None = Form(None, gt=0, description="Categoría para las filas sin categoría."),
    hoja: str | None = Form(None, description="Hoja del Excel; por defecto se detecta."),
    mapeo: str | None = Form(
        None, description='JSON para corregir columnas: {"C": "precio_usd", "Notas": ""} ("" = ignorar).'
    ),
    formato: Literal["json", "xlsx"] = Form("json", description="xlsx devuelve el reporte de errores en Excel."),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles(["admin"])),
):
    nombre = archivo.filename or "archivo"
    extension = Path(nombre).suffix.lower()
    if extension and extension not in EXTENSIONES:
        return _error(ErrorDeArchivo(
            f"El tipo de archivo '{extension}' no se admite. Use Excel (.xlsx) o CSV.", status_code=415
        ))
    archivo.file.seek(0, 2)
    tamano = archivo.file.tell()
    archivo.file.seek(0)
    if tamano > settings.MAX_IMPORT_MB * 1024 * 1024:
        return _error(ErrorDeArchivo(f"El archivo supera {settings.MAX_IMPORT_MB} MB.", status_code=413))

    manual: dict[str, str] = {}
    if mapeo:
        try:
            manual = json.loads(mapeo)
            if not isinstance(manual, dict) or not all(isinstance(v, (str, type(None))) for v in manual.values()):
                raise ValueError
        except ValueError:
            return _error(ErrorDeArchivo(
                'El parámetro mapeo debe ser un objeto JSON, p. ej. {"C": "precio_usd"}.'
            ))

    opciones = Opciones(
        modo=modo,
        si_existe=si_existe,
        crear_faltantes=crear_faltantes,
        id_categoria_defecto=id_categoria_defecto,
        hoja=hoja or None,
        mapeo={str(k): v or "" for k, v in manual.items()},
    )
    try:
        resultado = importar(db, archivo.file, nombre, opciones, id_usuario=admin.id_usuario)
    except ErrorDeArchivo as exc:
        return _error(exc)
    except Exception:  # nunca un 500 sin explicación: se registra y se informa que no se guardó nada
        db.rollback()
        logger.exception("Error inesperado al importar %s", nombre)
        return _error(ErrorDeArchivo(
            "Ocurrió un error inesperado al procesar el archivo. No se guardó ningún cambio; "
            "revise el registro del servidor.",
            status_code=500,
        ))
    if formato == "xlsx":
        return _descarga(reporte_errores(resultado), f"importacion_{resultado.estado}.xlsx")
    respuesta = resultado.como_dict()
    if resultado.total_errores or resultado.total_advertencias:
        # El reporte describe esta misma ejecución: si se descargara volviendo a validar
        # después de importar, las filas recién creadas aparecerían como duplicadas.
        respuesta["reporte_id"] = _guardar_reporte(reporte_errores(resultado), admin.id_usuario)
    return respuesta


@router.get("/reportes/{reporte_id}", response_class=Response, responses={200: {"content": {XLSX: {}}}})
def download_report(
    reporte_id: str,
    admin: Usuario = Depends(require_roles(["admin"])),
) -> Response:
    """Reporte de errores (.xlsx) de una importación hecha por el mismo usuario en las
    últimas 24 horas."""
    if not _REPORTE_ID.match(reporte_id):
        return _error(ErrorDeArchivo("Reporte no encontrado.", status_code=404))
    ruta = _reportes_dir() / f"{admin.id_usuario}-{reporte_id}.xlsx"
    if not ruta.is_file():
        return _error(ErrorDeArchivo(
            "El reporte ya no está disponible (se guardan 24 horas). Vuelva a validar el archivo.",
            status_code=404,
        ))
    return FileResponse(ruta, media_type=XLSX, filename="reporte_importacion.xlsx")
