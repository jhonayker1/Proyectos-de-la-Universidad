"""Facturas escaneadas (imagen o PDF). Los archivos se guardan en UPLOAD_DIR/facturas."""

from datetime import date
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dates import day_bounds
from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.compras import Compra, FacturaImagen
from app.models.usuarios import Usuario
from app.schemas.compras import FacturaRead

router = APIRouter(
    prefix="/facturas",
    tags=["facturas"],
    dependencies=[Depends(require_roles(["admin"]))],
)

# Tipo permitido -> (extensión, firma de los primeros bytes)
ALLOWED_TYPES = {
    "image/jpeg": (".jpg", (b"\xff\xd8\xff",)),
    "image/png": (".png", (b"\x89PNG\r\n\x1a\n",)),
    "image/webp": (".webp", (b"RIFF",)),
    "application/pdf": (".pdf", (b"%PDF",)),
}


def facturas_dir() -> Path:
    path = settings.UPLOAD_DIR / "facturas"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_or_404(db: Session, id_factura_img: int) -> FacturaImagen:
    factura = db.get(FacturaImagen, id_factura_img)
    if factura is None:
        raise HTTPException(status_code=404, detail="Factura no encontrada.")
    return factura


@router.post("/", response_model=FacturaRead, status_code=status.HTTP_201_CREATED)
async def upload_invoice(
    archivo: UploadFile = File(...),
    id_compra: int | None = Form(default=None),
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles(["admin"])),
) -> FacturaImagen:
    allowed = ALLOWED_TYPES.get(archivo.content_type or "")
    if allowed is None:
        raise HTTPException(status_code=415, detail="Solo se aceptan imágenes JPG, PNG, WEBP o PDF.")
    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    content = await archivo.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413, detail=f"El archivo supera {settings.MAX_UPLOAD_MB} MB."
        )
    extension, signatures = allowed
    if not content.startswith(signatures):
        raise HTTPException(status_code=415, detail="El contenido no coincide con el tipo de archivo.")
    if id_compra is not None and db.get(Compra, id_compra) is None:
        raise HTTPException(status_code=404, detail="Compra no encontrada.")

    # Nombre aleatorio: nunca se usa el nombre que envía el navegador como ruta.
    stored_name = f"{uuid4().hex}{extension}"
    (facturas_dir() / stored_name).write_bytes(content)
    factura = FacturaImagen(
        nombre_original=(archivo.filename or stored_name)[:255],
        ruta_archivo=stored_name,
        tipo_mime=archivo.content_type,
        tamano_bytes=len(content),
        id_compra=id_compra,
        id_usuario=admin.id_usuario,
    )
    db.add(factura)
    try:
        db.commit()
    except Exception:
        (facturas_dir() / stored_name).unlink(missing_ok=True)
        raise
    db.refresh(factura)
    return factura


@router.get("/", response_model=list[FacturaRead])
def list_invoices(
    desde: date | None = None,
    hasta: date | None = None,
    db: Session = Depends(get_db),
) -> list[FacturaImagen]:
    query = db.query(FacturaImagen)
    if desde is not None:
        query = query.filter(FacturaImagen.fecha_subida >= day_bounds(desde)[0])
    if hasta is not None:
        query = query.filter(FacturaImagen.fecha_subida < day_bounds(hasta)[1])
    return query.order_by(FacturaImagen.id_factura_img.desc()).all()


@router.get("/{id_factura_img}/archivo")
def download_invoice(id_factura_img: int, db: Session = Depends(get_db)) -> FileResponse:
    factura = get_or_404(db, id_factura_img)
    path = facturas_dir() / Path(factura.ruta_archivo).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="El archivo de la factura no existe en disco.")
    return FileResponse(path, media_type=factura.tipo_mime, filename=factura.nombre_original)


@router.delete("/{id_factura_img}", status_code=status.HTTP_204_NO_CONTENT)
def delete_invoice(id_factura_img: int, db: Session = Depends(get_db)) -> None:
    factura = get_or_404(db, id_factura_img)
    path = facturas_dir() / Path(factura.ruta_archivo).name
    db.delete(factura)
    db.commit()
    path.unlink(missing_ok=True)
