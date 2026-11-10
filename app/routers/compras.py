from collections import defaultdict
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.dates import local_today
from app.core.dependencies import require_roles
from app.core.money import round_money
from app.database.session import get_db
from app.models.compras import Compra, DetalleCompra
from app.models.inventario import Proveedor
from app.models.usuarios import Usuario
from app.routers.ventas import lock_products
from app.schemas.compras import (
    CompraCreate,
    CompraPagadoUpdate,
    CompraRead,
    DetalleCompraRead,
    EntradaStockRead,
)
from app.services.precios_service import apply_margin_price

router = APIRouter(
    prefix="/compras",
    tags=["compras"],
    dependencies=[Depends(require_roles(["admin"]))],
)


def to_read(compra: Compra) -> CompraRead:
    return CompraRead(
        id_compra=compra.id_compra,
        id_proveedor=compra.id_proveedor,
        nombre_proveedor=compra.proveedor.nombre,
        numero_factura=compra.numero_factura,
        fecha=compra.fecha,
        descripcion=compra.descripcion,
        monto_usd=compra.monto_usd,
        pagado=compra.pagado == 1,
        id_usuario=compra.id_usuario,
        fecha_registro=compra.fecha_registro,
        detalles=[
            DetalleCompraRead(
                id_detalle_compra=d.id_detalle_compra,
                id_producto=d.id_producto,
                sku=d.producto.sku,
                nombre_producto=d.producto.nombre,
                cantidad=d.cantidad,
                costo_unitario_usd=d.costo_unitario_usd,
            )
            for d in compra.detalles
        ],
    )


def get_or_404(db: Session, id_compra: int) -> Compra:
    compra = db.query(Compra).filter(Compra.id_compra == id_compra).first()
    if compra is None:
        raise HTTPException(status_code=404, detail="Compra no encontrada.")
    return compra


@router.get("/", response_model=list[CompraRead])
def list_purchases(
    id_proveedor: int | None = None,
    desde: date | None = None,
    hasta: date | None = None,
    pagado: bool | None = None,
    limite: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> list[CompraRead]:
    query = db.query(Compra)
    if id_proveedor is not None:
        query = query.filter(Compra.id_proveedor == id_proveedor)
    if desde is not None:
        query = query.filter(Compra.fecha >= desde)
    if hasta is not None:
        query = query.filter(Compra.fecha <= hasta)
    if pagado is not None:
        query = query.filter(Compra.pagado == (1 if pagado else 0))
    compras = query.order_by(Compra.fecha.desc(), Compra.id_compra.desc()).limit(limite).all()
    return [to_read(c) for c in compras]


@router.get("/entradas-recientes", response_model=list[EntradaStockRead])
def recent_stock_entries(
    limite: int = Query(default=10, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[EntradaStockRead]:
    rows = (
        db.query(DetalleCompra, Compra)
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .order_by(Compra.fecha.desc(), DetalleCompra.id_detalle_compra.desc())
        .limit(limite)
        .all()
    )
    return [
        EntradaStockRead(
            id_compra=compra.id_compra,
            fecha=compra.fecha,
            id_producto=detalle.id_producto,
            nombre_producto=detalle.producto.nombre,
            cantidad=detalle.cantidad,
            nombre_proveedor=compra.proveedor.nombre,
        )
        for detalle, compra in rows
    ]


@router.get("/{id_compra}", response_model=CompraRead)
def get_purchase(id_compra: int, db: Session = Depends(get_db)) -> CompraRead:
    return to_read(get_or_404(db, id_compra))


@router.post("/", response_model=CompraRead, status_code=status.HTTP_201_CREATED)
def create_purchase(
    compra_in: CompraCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(require_roles(["admin"])),
) -> CompraRead:
    """Registra la compra y, en la misma transacción, suma el stock de cada producto."""
    proveedor = db.get(Proveedor, compra_in.id_proveedor)
    if proveedor is None or proveedor.estado != 1:
        raise HTTPException(status_code=404, detail="Proveedor no encontrado o eliminado.")

    requested: dict[int, int] = defaultdict(int)
    for item in compra_in.detalles:
        requested[item.id_producto] += item.cantidad
    productos = lock_products(db, sorted(requested))
    missing = sorted(set(requested) - set(productos))
    if missing:
        raise HTTPException(status_code=404, detail=f"Producto {missing[0]} no encontrado.")

    compra = Compra(
        id_proveedor=compra_in.id_proveedor,
        numero_factura=compra_in.numero_factura.strip() if compra_in.numero_factura else None,
        fecha=compra_in.fecha or local_today(),
        descripcion=compra_in.descripcion,
        monto_usd=Decimal("0.00"),
        pagado=1 if compra_in.pagado else 0,
        id_usuario=admin.id_usuario,
    )
    total = Decimal("0.00")
    for item in compra_in.detalles:
        producto = productos[item.id_producto]
        producto.stock_actual += item.cantidad
        if compra_in.actualizar_costos:
            producto.precio_distribuidor = item.costo_unitario_usd
            apply_margin_price(db, producto)
        producto.sync_stock_status()
        total += round_money(item.costo_unitario_usd * item.cantidad)
        compra.detalles.append(
            DetalleCompra(
                id_producto=item.id_producto,
                cantidad=item.cantidad,
                costo_unitario_usd=item.costo_unitario_usd,
            )
        )
    compra.monto_usd = compra_in.monto_usd if compra_in.monto_usd is not None else total
    db.add(compra)
    db.commit()
    db.refresh(compra)
    return to_read(compra)


@router.patch("/{id_compra}/pagado", response_model=CompraRead)
def set_paid(
    id_compra: int,
    update: CompraPagadoUpdate,
    db: Session = Depends(get_db),
) -> CompraRead:
    compra = get_or_404(db, id_compra)
    compra.pagado = 1 if update.pagado else 0
    db.commit()
    db.refresh(compra)
    return to_read(compra)
