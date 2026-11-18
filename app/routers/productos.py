from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dates import day_bounds
from app.core.dependencies import require_roles
from app.core.money import to_local
from app.core.permisos import GESTION, SOLO_ADMIN, TODOS
from app.database.session import get_db
from app.models.compras import DetalleCompra
from app.models.inventario import (
    MOTIVOS_AJUSTE,
    PRODUCTO_DISPONIBLE,
    PRODUCTO_INACTIVO,
    AjusteStock,
    Categoria,
    Marca,
    Producto,
    Proveedor,
)
from app.models.usuarios import Usuario
from app.models.ventas import DetalleVenta
from app.schemas.productos import (
    AjusteStockCreate,
    AjusteStockRead,
    ProductoAdminRead,
    ProductoCreate,
    ProductoRead,
    ProductoUpdate,
)
from app.services.auditoria_service import establecer_origen
from app.services.finanzas_service import local_rate_value
from app.services.precios_service import apply_margin_price, effective_margin
from app.services.sku_service import siguiente_sku

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
    _: Usuario = Depends(require_roles(TODOS)),
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
    incluir_eliminados: bool = Query(default=False),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(GESTION)),
) -> list[ProductoRead]:
    rate = local_rate_value(db)
    query = db.query(Producto)
    if not incluir_eliminados:
        query = query.filter(Producto.estado != PRODUCTO_INACTIVO)
    return [to_read(ProductoAdminRead, p, rate) for p in query.order_by(Producto.nombre).all()]


@router.get("/stock-bajo", response_model=list[ProductoAdminRead])
def list_low_stock(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(GESTION)),
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


@router.get("/siguiente-sku")
def next_sku(
    id_categoria: int = Query(gt=0),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(GESTION)),
) -> dict[str, str]:
    """Vista previa del SKU que recibirá un producto nuevo de la categoría."""
    categoria = db.get(Categoria, id_categoria)
    if categoria is None:
        raise HTTPException(status_code=404, detail="Categoría no encontrada.")
    sku = siguiente_sku(db, categoria)
    db.commit()  # guarda el código de la categoría si se acaba de derivar
    return {"sku": sku, "prefijo": categoria.prefijo_sku}


def ajuste_to_read(a: AjusteStock) -> AjusteStockRead:
    return AjusteStockRead(
        id_ajuste=a.id_ajuste, id_producto=a.id_producto, sku=a.producto.sku, nombre_producto=a.producto.nombre,
        cantidad=a.cantidad, stock_anterior=a.stock_anterior, stock_nuevo=a.stock_nuevo, motivo=a.motivo,
        motivo_etiqueta=MOTIVOS_AJUSTE.get(a.motivo, a.motivo), observacion=a.observacion,
        id_usuario=a.id_usuario, nombre_usuario=a.usuario.nombre_completo, fecha=a.fecha,
    )


@router.get("/ajustes", response_model=list[AjusteStockRead])
def list_stock_adjustments(
    desde: date | None = None,
    hasta: date | None = None,
    id_producto: int | None = None,
    limite: int = Query(default=200, ge=1, le=5000),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(GESTION)),
) -> list[AjusteStockRead]:
    """Historial de ajustes de stock con su motivo y quién los hizo."""
    query = db.query(AjusteStock)
    if desde:
        query = query.filter(AjusteStock.fecha >= day_bounds(desde)[0])
    if hasta:
        query = query.filter(AjusteStock.fecha < day_bounds(hasta)[1])
    if id_producto:
        query = query.filter(AjusteStock.id_producto == id_producto)
    return [ajuste_to_read(a) for a in query.order_by(AjusteStock.id_ajuste.desc()).limit(limite).all()]


@router.post("/{id_producto}/ajustes", response_model=AjusteStockRead, status_code=status.HTTP_201_CREATED)
def adjust_stock(
    id_producto: int,
    ajuste_in: AjusteStockCreate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles(GESTION)),
) -> AjusteStockRead:
    """Corrige el stock con una justificación: sumar, restar o fijar el conteo físico.
    Nunca deja el stock negativo y queda en la auditoría con su motivo."""
    producto = db.query(Producto).filter(Producto.id_producto == id_producto).with_for_update(of=Producto).first()
    if producto is None or not producto.is_active:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    anterior = producto.stock_actual
    if ajuste_in.tipo == "conteo":
        nuevo = ajuste_in.cantidad
    elif ajuste_in.tipo == "sumar":
        nuevo = anterior + ajuste_in.cantidad
    else:
        nuevo = anterior - ajuste_in.cantidad
    if nuevo < 0:
        raise HTTPException(
            status_code=409,
            detail=f"No se pueden restar {ajuste_in.cantidad} unidades: {producto.nombre} tiene {anterior} en stock.",
        )
    if nuevo == anterior:
        raise HTTPException(status_code=422, detail=f"El stock de {producto.nombre} ya es {anterior}; no hay nada que ajustar.")
    etiqueta = MOTIVOS_AJUSTE[ajuste_in.motivo]
    establecer_origen(db, f"Ajuste de stock: {etiqueta} — {ajuste_in.observacion}")
    producto.stock_actual = nuevo
    producto.sync_stock_status()
    ajuste = AjusteStock(
        id_producto=producto.id_producto, cantidad=nuevo - anterior, stock_anterior=anterior, stock_nuevo=nuevo,
        motivo=ajuste_in.motivo, observacion=ajuste_in.observacion, id_usuario=user.id_usuario,
    )
    db.add(ajuste)
    db.commit()
    db.refresh(ajuste)
    return ajuste_to_read(ajuste)


@router.get("/{id_producto}", response_model=ProductoRead)
def get_product(
    id_producto: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(TODOS)),
) -> ProductoRead:
    producto = get_or_404(db, id_producto)
    if not producto.is_active:
        raise HTTPException(status_code=404, detail="Producto no encontrado.")
    return to_read(ProductoRead, producto, local_rate_value(db))


@router.post("/", response_model=ProductoAdminRead, status_code=status.HTTP_201_CREATED)
def create_product(
    producto_in: ProductoCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(GESTION)),
) -> ProductoRead:
    values = producto_in.model_dump()
    validate_references(db, values)
    automatico = not (producto_in.sku and producto_in.sku.strip())
    for intento in range(3):
        # Sin SKU se genera el siguiente de la categoría; si otro usuario lo tomó en el
        # mismo instante, el índice único lo rechaza y se prueba con el próximo.
        values["sku"] = (
            siguiente_sku(db, db.get(Categoria, values["id_categoria"]))
            if automatico else producto_in.sku.strip().upper()
        )
        producto = Producto(**values, estado=PRODUCTO_DISPONIBLE)
        if producto.precio_usd is None:
            apply_margin_price(db, producto)
        producto.sync_stock_status()
        db.add(producto)
        try:
            db.commit()
            break
        except IntegrityError as exc:
            db.rollback()
            if not automatico or intento == 2:
                raise HTTPException(status_code=409, detail="El SKU ya está registrado.") from exc
    db.refresh(producto)
    return to_read(ProductoAdminRead, producto, local_rate_value(db))


@router.put("/{id_producto}", response_model=ProductoAdminRead)
def update_product(
    id_producto: int,
    producto_in: ProductoUpdate,
    db: Session = Depends(get_db),
    user: Usuario = Depends(require_roles(GESTION)),
) -> ProductoRead:
    producto = get_or_404(db, id_producto)
    values = producto_in.model_dump(exclude_unset=True)
    if user.rol not in SOLO_ADMIN and "estado" in values and (
        values["estado"] == PRODUCTO_INACTIVO or producto.estado == PRODUCTO_INACTIVO
    ):
        raise HTTPException(status_code=403, detail="Solo el administrador puede dar de baja o reactivar productos.")
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
def delete_product(
    id_producto: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(SOLO_ADMIN)),
) -> None:
    """Elimina el producto. Sin ventas ni compras se borra de la base; con historial se
    oculta de todas las pantallas (estado Inactivo) para no romper facturas y reportes, y
    se libera su SKU para poder reutilizarlo."""
    producto = get_or_404(db, id_producto)
    tiene_historial = any(
        db.query(modelo).filter(modelo.id_producto == id_producto).first() is not None
        for modelo in (DetalleVenta, DetalleCompra)
    )
    if tiene_historial:
        sufijo = f"~{producto.id_producto}"
        if producto.estado != PRODUCTO_INACTIVO:
            producto.sku = producto.sku[: 50 - len(sufijo)] + sufijo
        producto.estado = PRODUCTO_INACTIVO
    else:
        db.delete(producto)
    db.commit()
