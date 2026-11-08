from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.money import to_local
from app.database.session import get_db
from app.models.inventario import (
    PRODUCTO_DISPONIBLE,
    PRODUCTO_INACTIVO,
    Categoria,
    Marca,
    Producto,
    Proveedor,
)
from app.models.usuarios import Usuario
from app.schemas.productos import (
    ProductoAdminRead,
    ProductoCreate,
    ProductoRead,
    ProductoUpdate,
)
from app.services.finanzas_service import local_rate_value
from app.services.precios_service import apply_margin_price, effective_margin

router = APIRouter(prefix="/productos", tags=["productos"])


def to_read(schema: type[ProductoRead], producto: Producto, rate: Decimal | None) -> ProductoRead:
    read = schema.model_validate(producto)
    read.nombre_categoria = producto.categoria.nombre if producto.categoria else None
    read.nombre_marca = producto.marca.nombre if producto.marca else None
    if isinstance(read, ProductoAdminRead):
        read.nombre_proveedor = producto.proveedor.nombre if producto.proveedor else None
        read.margen_efectivo = effective_margin(producto, producto.categoria)
    if rate is not None:
        read.precio_local = to_local(producto.precio_usd, rate)
    return read


def get_or_404(db: Session, id_producto: int) -> Producto:
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).first()
    if producto is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return producto


def validate_references(db: Session, values: dict) -> None:
    references = (
        ("id_categoria", Categoria, Categoria.id_categoria, "Categoría"),
        ("id_marca", Marca, Marca.id_marca, "Marca"),
        ("id_proveedor", Proveedor, Proveedor.id_proveedor, "Proveedor"),
    )
    for field, model, pk, label in references:
        value = values.get(field)
        if value is not None and db.query(model).filter(pk == value).first() is None:
            raise HTTPException(status_code=404, detail=f"{label} {value} no encontrada(o).")


def commit_or_conflict(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El SKU ya está registrado.") from exc


@router.get("/", response_model=list[ProductoRead])
def list_products(
    buscar: str | None = Query(default=None, max_length=150),
    id_categoria: int | None = None,
    id_marca: int | None = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> list[ProductoRead]:
    query = db.query(Producto).filter(Producto.estado != PRODUCTO_INACTIVO)
    if buscar:
        pattern = f"%{buscar.strip()}%"
        query = query.filter(or_(Producto.nombre.ilike(pattern), Producto.sku.ilike(pattern)))
    if id_categoria is not None:
        query = query.filter(Producto.id_categoria == id_categoria)
    if id_marca is not None:
        query = query.filter(Producto.id_marca == id_marca)
    rate = local_rate_value(db)
    return [to_read(ProductoRead, p, rate) for p in query.order_by(Producto.nombre).all()]


@router.get("/admin", response_model=list[ProductoAdminRead])
def list_products_admin(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> list[ProductoRead]:
    rate = local_rate_value(db)
    productos = db.query(Producto).order_by(Producto.nombre).all()
    return [to_read(ProductoAdminRead, p, rate) for p in productos]


@router.get("/stock-bajo", response_model=list[ProductoAdminRead])
def list_low_stock(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> list[ProductoRead]:
    rate = local_rate_value(db)
    productos = (
        db.query(Producto)
        .filter(
            Producto.estado != PRODUCTO_INACTIVO,
            Producto.stock_actual < Producto.stock_minimo,
        )
        .order_by(Producto.stock_actual, Producto.nombre)
        .all()
    )
    return [to_read(ProductoAdminRead, p, rate) for p in productos]


@router.get("/{id_producto}", response_model=ProductoRead)
def get_product(
    id_producto: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> ProductoRead:
    producto = get_or_404(db, id_producto)
    if not producto.is_active:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return to_read(ProductoRead, producto, local_rate_value(db))


@router.post("/", response_model=ProductoAdminRead, status_code=status.HTTP_201_CREATED)
def create_product(
    producto_in: ProductoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> ProductoRead:
    values = producto_in.model_dump()
    validate_references(db, values)
    values["sku"] = producto_in.sku.strip().upper()
    producto = Producto(**values, estado=PRODUCTO_DISPONIBLE)
    if producto.precio_usd is None:
        apply_margin_price(db, producto)
    producto.sync_stock_status()
    db.add(producto)
    commit_or_conflict(db)
    db.refresh(producto)
    return to_read(ProductoAdminRead, producto, local_rate_value(db))


@router.put("/{id_producto}", response_model=ProductoAdminRead)
def update_product(
    id_producto: int,
    producto_in: ProductoUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> ProductoRead:
    producto = get_or_404(db, id_producto)
    values = producto_in.model_dump(exclude_unset=True)
    validate_references(db, values)
    for field, value in values.items():
        setattr(producto, field, value.strip().upper() if field == "sku" else value)
    if "precio_usd" not in values and values.keys() & {
        "precio_distribuidor", "margen_pct", "id_categoria"
    }:
        apply_margin_price(db, producto)
    if values.get("estado") != PRODUCTO_INACTIVO:
        # Reactivar o cambiar stock recalcula el estado; solo "Inactivo" se fija a mano.
        if producto.estado == PRODUCTO_INACTIVO and "estado" in values:
            producto.estado = PRODUCTO_DISPONIBLE
        producto.sync_stock_status()
    commit_or_conflict(db)
    db.refresh(producto)
    return to_read(ProductoAdminRead, producto, local_rate_value(db))


@router.delete("/{id_producto}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(
    id_producto: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> None:
    get_or_404(db, id_producto).estado = PRODUCTO_INACTIVO
    db.commit()
