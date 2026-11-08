from collections import defaultdict
from datetime import date
from decimal import Decimal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_today
from app.core.dependencies import require_roles
from app.core.money import round_money, to_local
from app.database.session import get_db
from app.models.finanzas import Moneda
from app.models.inventario import Producto
from app.models.usuarios import Usuario
from app.models.ventas import VENTA_ANULADA, VENTA_COMPLETADA, DetalleVenta, Venta
from app.schemas.ventas import (
    DetalleVentaRead,
    ResumenVentas,
    TotalPorMoneda,
    VentaCreate,
    VentaRead,
)
from app.services.finanzas_service import get_moneda, require_tasa_vigente

router = APIRouter(prefix="/ventas", tags=["ventas"])


def to_read(venta: Venta) -> VentaRead:
    return VentaRead(
        id_venta=venta.id_venta,
        numero_factura=venta.numero_factura,
        id_usuario=venta.id_usuario,
        nombre_usuario=venta.usuario.nombre_completo if venta.usuario else None,
        id_moneda_pago=venta.id_moneda_pago,
        codigo_moneda_pago=venta.moneda_pago.codigo.strip(),
        monto_total_usd=venta.monto_total_usd,
        monto_total_moneda=venta.monto_total_moneda,
        tasa_aplicada=venta.tasa_aplicada,
        referencia_pago=venta.referencia_pago,
        estado=venta.estado,
        fecha_venta=venta.fecha_venta,
        detalles=[DetalleVentaRead.model_validate(d) for d in venta.detalles],
    )


def filter_by_day(query: SAQuery, day: date) -> SAQuery:
    return filter_by_range(query, day, day)


def filter_by_range(query: SAQuery, desde: date, hasta: date) -> SAQuery:
    """Ventas entre el inicio de `desde` y el final de `hasta` (ambos incluidos)."""
    if hasta < desde:
        raise HTTPException(status_code=422, detail="'hasta' no puede ser anterior a 'desde'.")
    start, end = day_bounds(desde)[0], day_bounds(hasta)[1]
    return query.filter(Venta.fecha_venta >= start, Venta.fecha_venta < end)


def lock_products(db: Session, ids: list[int]) -> dict[int, Producto]:
    # Bloqueo en orden de id para evitar interbloqueos entre ventas simultáneas.
    productos = (
        db.query(Producto)
        .filter(Producto.id_producto.in_(ids))
        .order_by(Producto.id_producto)
        .with_for_update(of=Producto)
        .all()
    )
    return {p.id_producto: p for p in productos}


def build_summary(db: Session, day: date, id_usuario: int | None = None) -> ResumenVentas:
    def scoped(query: SAQuery) -> SAQuery:
        query = filter_by_day(query, day).filter(Venta.estado == VENTA_COMPLETADA)
        if id_usuario is not None:
            query = query.filter(Venta.id_usuario == id_usuario)
        return query

    count, total_usd = scoped(
        db.query(func.count(Venta.id_venta), func.coalesce(func.sum(Venta.monto_total_usd), 0))
    ).one()
    articulos = scoped(
        db.query(func.coalesce(func.sum(DetalleVenta.cantidad), 0)).join(
            Venta, Venta.id_venta == DetalleVenta.id_venta
        )
    ).scalar()
    rows = (
        scoped(
            db.query(
                Moneda.codigo,
                func.count(Venta.id_venta),
                func.coalesce(func.sum(Venta.monto_total_moneda), 0),
            ).join(Moneda, Moneda.id_moneda == Venta.id_moneda_pago)
        )
        .group_by(Moneda.codigo)
        .order_by(Moneda.codigo)
        .all()
    )
    return ResumenVentas(
        dia=day,
        cantidad_ventas=count,
        articulos_vendidos=int(articulos or 0),
        monto_total_usd=round_money(total_usd),
        por_moneda=[
            TotalPorMoneda(
                codigo_moneda=codigo.strip(),
                cantidad_ventas=n,
                monto_total_moneda=round_money(total),
            )
            for codigo, n, total in rows
        ],
    )


@router.post("/", response_model=VentaRead, status_code=status.HTTP_201_CREATED)
def create_sale(
    venta_in: VentaCreate,
    db: Session = Depends(get_db),
    vendedor: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> VentaRead:
    moneda = get_moneda(db, venta_in.codigo_moneda_pago)
    tasa = Decimal("1") if moneda.es_base == 1 else require_tasa_vigente(db, moneda).tasa_venta

    requested: dict[int, int] = defaultdict(int)
    for item in venta_in.detalles:
        requested[item.id_producto] += item.cantidad

    productos = lock_products(db, sorted(requested))
    for id_producto, cantidad in requested.items():
        producto = productos.get(id_producto)
        if producto is None or not producto.is_active:
            raise HTTPException(status_code=404, detail=f"Producto {id_producto} no encontrado.")
        if producto.stock_actual < cantidad:
            raise HTTPException(
                status_code=409,
                detail=f"Stock insuficiente para {producto.nombre}. "
                f"Disponible: {producto.stock_actual}.",
            )

    venta = Venta(
        # Valor temporal único; se reemplaza por el número definitivo tras obtener el id.
        numero_factura=f"TMP-{uuid4().hex[:24]}",
        id_usuario=vendedor.id_usuario,
        id_moneda_pago=moneda.id_moneda,
        monto_total_usd=Decimal("0.00"),
        monto_total_moneda=Decimal("0.00"),
        tasa_aplicada=tasa,
        referencia_pago=venta_in.referencia_pago,
        estado=VENTA_COMPLETADA,
    )
    total_usd = Decimal("0.00")
    for item in venta_in.detalles:
        producto = productos[item.id_producto]
        producto.stock_actual -= item.cantidad
        producto.sync_stock_status()
        precio = round_money(producto.precio_usd)
        subtotal = round_money(precio * item.cantidad)
        total_usd += subtotal
        venta.detalles.append(
            DetalleVenta(
                id_producto=producto.id_producto,
                nombre_producto_snapshot=producto.nombre,
                cantidad=item.cantidad,
                precio_unitario_usd=precio,
                subtotal_usd=subtotal,
            )
        )

    venta.monto_total_usd = total_usd
    venta.monto_total_moneda = to_local(total_usd, tasa)
    db.add(venta)
    db.flush()
    venta.numero_factura = f"F-{venta.id_venta:08d}"
    db.commit()
    db.refresh(venta)
    return to_read(venta)


@router.get("/", response_model=list[VentaRead])
def list_sales(
    dia: date | None = Query(default=None, description="Día (AAAA-MM-DD)."),
    desde: date | None = Query(default=None, description="Inicio del rango (incluido)."),
    hasta: date | None = Query(default=None, description="Fin del rango (incluido)."),
    limite: int = Query(default=100, ge=1, le=5000),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> list[VentaRead]:
    query = db.query(Venta)
    if current_user.rol == "cashier":
        query = query.filter(Venta.id_usuario == current_user.id_usuario)
    if dia is not None:
        query = filter_by_day(query, dia)
    if desde is not None or hasta is not None:
        query = filter_by_range(query, desde or date.min, hasta or local_today())
    return [to_read(v) for v in query.order_by(Venta.id_venta.desc()).limit(limite).all()]


@router.get("/mi-resumen", response_model=ResumenVentas)
def my_daily_summary(
    dia: date = Query(default_factory=local_today),
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> ResumenVentas:
    """Corte diario de las ventas registradas por el usuario autenticado."""
    return build_summary(db, dia, current_user.id_usuario)


@router.get("/{id_venta}", response_model=VentaRead)
def get_sale(
    id_venta: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> VentaRead:
    venta = db.query(Venta).filter(Venta.id_venta == id_venta).first()
    if venta is None or (
        current_user.rol == "cashier" and venta.id_usuario != current_user.id_usuario
    ):
        raise HTTPException(status_code=404, detail="Venta no encontrada.")
    return to_read(venta)


@router.post("/{id_venta}/anular", response_model=VentaRead)
def cancel_sale(
    id_venta: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> VentaRead:
    """Anula la venta y devuelve las cantidades vendidas al inventario."""
    venta = (
        db.query(Venta).filter(Venta.id_venta == id_venta).with_for_update(of=Venta).first()
    )
    if venta is None:
        raise HTTPException(status_code=404, detail="Venta no encontrada.")
    if venta.estado == VENTA_ANULADA:
        raise HTTPException(status_code=409, detail="La venta ya está anulada.")

    productos = lock_products(db, sorted({d.id_producto for d in venta.detalles}))
    for detalle in venta.detalles:
        producto = productos[detalle.id_producto]
        producto.stock_actual += detalle.cantidad
        producto.sync_stock_status()

    venta.estado = VENTA_ANULADA
    db.commit()
    db.refresh(venta)
    return to_read(venta)
