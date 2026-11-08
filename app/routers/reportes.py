from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dates import local_today
from app.core.dependencies import require_roles
from app.core.money import round_money
from app.database.session import get_db
from app.models.inventario import (
    PRODUCTO_AGOTADO,
    PRODUCTO_BAJO_STOCK,
    PRODUCTO_INACTIVO,
    Categoria,
    Producto,
)
from app.models.usuarios import Usuario
from app.models.ventas import VENTA_ANULADA, VENTA_COMPLETADA, DetalleVenta, Venta
from app.routers.ventas import build_summary, filter_by_day, filter_by_range
from app.models.compras import Compra, DetalleCompra
from app.schemas.ventas import (
    Dashboard,
    IngresoProducto,
    MovimientosStock,
    PuntoSerie,
    ReporteVentas,
    StockCategoria,
    TopProducto,
    VentasCategoria,
    VentasPorUsuario,
)

router = APIRouter(
    prefix="/reportes",
    tags=["reportes"],
    dependencies=[Depends(require_roles(["admin"]))],
)


@router.get("/ventas", response_model=ReporteVentas)
def sales_report(
    dia: date = Query(default_factory=local_today),
    db: Session = Depends(get_db),
) -> ReporteVentas:
    summary = build_summary(db, dia)
    anuladas = (
        filter_by_day(db.query(func.count(Venta.id_venta)), dia)
        .filter(Venta.estado == VENTA_ANULADA)
        .scalar()
    )
    rows = (
        filter_by_day(
            db.query(
                Usuario.id_usuario,
                Usuario.nombre_completo,
                func.count(Venta.id_venta),
                func.coalesce(func.sum(Venta.monto_total_usd), 0),
            ).join(Venta, Venta.id_usuario == Usuario.id_usuario),
            dia,
        )
        .filter(Venta.estado == VENTA_COMPLETADA)
        .group_by(Usuario.id_usuario, Usuario.nombre_completo)
        .order_by(Usuario.nombre_completo)
        .all()
    )
    return ReporteVentas(
        **summary.model_dump(),
        ventas_anuladas=anuladas,
        por_usuario=[
            VentasPorUsuario(
                id_usuario=id_usuario,
                nombre_completo=nombre,
                cantidad_ventas=count,
                monto_total_usd=round_money(total),
            )
            for id_usuario, nombre, count, total in rows
        ],
    )


def completed_total(db: Session, desde: date, hasta: date) -> Decimal:
    total = filter_by_range(
        db.query(func.coalesce(func.sum(Venta.monto_total_usd), 0)), desde, hasta
    ).filter(Venta.estado == VENTA_COMPLETADA).scalar()
    return round_money(total)


@router.get("/dashboard", response_model=Dashboard)
def dashboard(db: Session = Depends(get_db)) -> Dashboard:
    hoy = local_today()
    inicio_mes = hoy.replace(day=1)
    fin_mes_anterior = inicio_mes - timedelta(days=1)
    resumen_hoy = build_summary(db, hoy)
    productos = db.query(Producto).filter(Producto.estado != PRODUCTO_INACTIVO).all()
    return Dashboard(
        dia=hoy,
        ventas_hoy_usd=resumen_hoy.monto_total_usd,
        ventas_hoy_cantidad=resumen_hoy.cantidad_ventas,
        articulos_hoy=resumen_hoy.articulos_vendidos,
        ventas_mes_usd=completed_total(db, inicio_mes, hoy),
        ventas_mes_anterior_usd=completed_total(db, fin_mes_anterior.replace(day=1), fin_mes_anterior),
        productos_activos=len(productos),
        unidades_en_stock=sum(p.stock_actual for p in productos),
        valor_inventario_usd=round_money(
            sum((p.precio_distribuidor * p.stock_actual for p in productos), Decimal("0"))
        ),
        productos_bajo_stock=sum(1 for p in productos if p.estado == PRODUCTO_BAJO_STOCK),
        productos_agotados=sum(1 for p in productos if p.estado == PRODUCTO_AGOTADO),
    )


@router.get("/serie-ventas", response_model=list[PuntoSerie])
def sales_series(
    desde: date = Query(default_factory=local_today),
    hasta: date = Query(default_factory=local_today),
    agrupar: Literal["hora", "dia"] = "dia",
    db: Session = Depends(get_db),
) -> list[PuntoSerie]:
    """Ventas completadas agrupadas por hora (00-23) o por día; incluye los días sin ventas."""
    ventas = filter_by_range(db.query(Venta), desde, hasta).filter(
        Venta.estado == VENTA_COMPLETADA
    ).all()
    buckets: dict[str, list] = defaultdict(lambda: [0, 0, Decimal("0")])
    for venta in ventas:
        key = (
            f"{venta.fecha_venta.hour:02d}" if agrupar == "hora"
            else venta.fecha_venta.date().isoformat()
        )
        bucket = buckets[key]
        bucket[0] += 1
        bucket[1] += sum(d.cantidad for d in venta.detalles)
        bucket[2] += venta.monto_total_usd
    if agrupar == "hora":
        keys = [f"{h:02d}" for h in range(24)]
    else:
        keys = [(desde + timedelta(days=i)).isoformat() for i in range((hasta - desde).days + 1)]
    return [
        PuntoSerie(
            etiqueta=key,
            cantidad_ventas=buckets[key][0],
            articulos_vendidos=buckets[key][1],
            monto_total_usd=round_money(buckets[key][2]),
        )
        for key in keys
    ]


@router.get("/top-productos", response_model=list[TopProducto])
def top_products(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    limite: int = Query(default=5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[TopProducto]:
    unidades = func.sum(DetalleVenta.cantidad)
    rows = (
        filter_by_range(
            db.query(
                Producto.id_producto,
                DetalleVenta.nombre_producto_snapshot,
                Categoria.nombre,
                unidades,
                func.coalesce(func.sum(DetalleVenta.subtotal_usd), 0),
            )
            .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
            .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
            .outerjoin(Categoria, Categoria.id_categoria == Producto.id_categoria),
            desde,
            hasta,
        )
        .filter(Venta.estado == VENTA_COMPLETADA)
        .group_by(Producto.id_producto, DetalleVenta.nombre_producto_snapshot, Categoria.nombre)
        .order_by(unidades.desc())
        .limit(limite)
        .all()
    )
    return [
        TopProducto(
            id_producto=id_producto,
            nombre_producto=nombre,
            nombre_categoria=categoria,
            unidades=int(cantidad),
            monto_total_usd=round_money(total),
        )
        for id_producto, nombre, categoria, cantidad, total in rows
    ]


@router.get("/movimientos-stock", response_model=MovimientosStock)
def stock_movements(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    limite_productos: int = Query(default=6, ge=1, le=50),
    db: Session = Depends(get_db),
) -> MovimientosStock:
    unidades = func.sum(DetalleCompra.cantidad)
    ingresos = (
        db.query(Producto.id_producto, Producto.nombre, unidades)
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .join(Producto, Producto.id_producto == DetalleCompra.id_producto)
        .filter(Compra.fecha >= desde, Compra.fecha <= hasta)
        .group_by(Producto.id_producto, Producto.nombre)
        .order_by(unidades.desc())
        .all()
    )
    entradas = sum(int(n) for _, _, n in ingresos)
    salidas = filter_by_range(
        db.query(func.coalesce(func.sum(DetalleVenta.cantidad), 0)).join(
            Venta, Venta.id_venta == DetalleVenta.id_venta
        ),
        desde,
        hasta,
    ).filter(Venta.estado == VENTA_COMPLETADA).scalar()
    salidas = int(salidas or 0)
    return MovimientosStock(
        desde=desde,
        hasta=hasta,
        entradas=entradas,
        salidas=salidas,
        neto=entradas - salidas,
        ingresos_por_producto=[
            IngresoProducto(id_producto=i, nombre_producto=nombre, unidades=int(n))
            for i, nombre, n in ingresos[:limite_productos]
        ],
    )


@router.get("/ventas-por-categoria", response_model=list[VentasCategoria])
def sales_by_category(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    db: Session = Depends(get_db),
) -> list[VentasCategoria]:
    unidades = func.sum(DetalleVenta.cantidad)
    rows = (
        filter_by_range(
            db.query(
                Categoria.id_categoria,
                Categoria.nombre,
                unidades,
                func.coalesce(func.sum(DetalleVenta.subtotal_usd), 0),
            )
            .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
            .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
            .outerjoin(Categoria, Categoria.id_categoria == Producto.id_categoria),
            desde,
            hasta,
        )
        .filter(Venta.estado == VENTA_COMPLETADA)
        .group_by(Categoria.id_categoria, Categoria.nombre)
        .order_by(unidades.desc())
        .all()
    )
    return [
        VentasCategoria(
            id_categoria=id_categoria,
            nombre_categoria=nombre or "Sin categoría",
            unidades=int(n),
            monto_total_usd=round_money(total),
        )
        for id_categoria, nombre, n, total in rows
    ]


@router.get("/stock-por-categoria", response_model=list[StockCategoria])
def stock_by_category(db: Session = Depends(get_db)) -> list[StockCategoria]:
    categorias = {c.id_categoria: c for c in db.query(Categoria).all()}
    stats: dict[int, list] = defaultdict(lambda: [0, 0, Decimal("0"), 0, 0])
    for p in db.query(Producto).filter(Producto.estado != PRODUCTO_INACTIVO).all():
        row = stats[p.id_categoria]
        row[0] += 1
        row[1] += p.stock_actual
        row[2] += p.precio_distribuidor * p.stock_actual
        row[3] += p.estado == PRODUCTO_BAJO_STOCK
        row[4] += p.estado == PRODUCTO_AGOTADO
    return sorted(
        (
            StockCategoria(
                id_categoria=id_categoria,
                nombre_categoria=categorias[id_categoria].nombre,
                productos=row[0],
                unidades=row[1],
                valor_costo_usd=round_money(row[2]),
                bajo_stock=row[3],
                agotados=row[4],
            )
            for id_categoria, row in stats.items()
        ),
        key=lambda s: s.unidades,
        reverse=True,
    )
