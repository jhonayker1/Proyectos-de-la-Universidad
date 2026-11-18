from collections import defaultdict
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_today
from app.core.dependencies import require_roles
from app.core.money import round_money
from app.core.permisos import GESTION, SOLO_ADMIN
from app.database.session import get_db
from app.models.auditoria import Auditoria
from app.models.compras import Compra, DetalleCompra
from app.models.inventario import (
    MOTIVOS_AJUSTE,
    PRODUCTO_AGOTADO,
    PRODUCTO_BAJO_STOCK,
    PRODUCTO_INACTIVO,
    AjusteStock,
    Categoria,
    Producto,
    Proveedor,
)
from app.models.usuarios import Usuario
from app.models.ventas import VENTA_ANULADA, VENTA_COMPLETADA, DetalleVenta, Venta
from app.routers.ventas import build_summary, filter_by_day, filter_by_range
from app.schemas.operativos import (
    AlertaStock,
    CompraPendiente,
    CuentaPorPagar,
    CuentasPorPagar,
    Kardex,
    Movimiento,
    ResumenGestor,
)
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
    dependencies=[Depends(require_roles(GESTION))],
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


@router.get(
    "/dashboard", response_model=Dashboard,
    # Financiero (mes contra mes anterior, valor del inventario): solo el administrador.
    dependencies=[Depends(require_roles(SOLO_ADMIN))],
)
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


# ------------------------------------------------------------- reportes operativos
# Para el administrador y el gestor. Ninguno calcula utilidad ni márgenes.


@router.get("/gestor/resumen", response_model=ResumenGestor)
def operational_summary(db: Session = Depends(get_db)) -> ResumenGestor:
    """Panel de inicio del gestor: actividad del día y alertas operativas."""
    hoy = local_today()
    inicio, fin = day_bounds(hoy)
    resumen = build_summary(db, hoy)
    compras_hoy, unidades = (
        db.query(func.count(func.distinct(Compra.id_compra)), func.coalesce(func.sum(DetalleCompra.cantidad), 0))
        .outerjoin(DetalleCompra, DetalleCompra.id_compra == Compra.id_compra)
        .filter(Compra.fecha_registro >= inicio, Compra.fecha_registro < fin)
        .one()
    )
    productos = db.query(Producto).filter(
        Producto.estado.in_([PRODUCTO_AGOTADO, PRODUCTO_BAJO_STOCK])
    ).order_by(Producto.stock_actual, Producto.nombre).all()
    deuda_n, deuda_usd = (
        db.query(func.count(Compra.id_compra), func.coalesce(func.sum(Compra.monto_usd), 0))
        .filter(Compra.pagado == 0).one()
    )
    return ResumenGestor(
        dia=hoy,
        ventas_hoy=resumen.cantidad_ventas,
        articulos_hoy=resumen.articulos_vendidos,
        monto_hoy_usd=resumen.monto_total_usd,
        compras_hoy=compras_hoy,
        unidades_entrada_hoy=int(unidades or 0),
        ajustes_hoy=db.query(func.count(AjusteStock.id_ajuste)).filter(
            AjusteStock.fecha >= inicio, AjusteStock.fecha < fin).scalar(),
        productos_bajo_stock=sum(p.estado == PRODUCTO_BAJO_STOCK for p in productos),
        productos_agotados=sum(p.estado == PRODUCTO_AGOTADO for p in productos),
        stock_critico=[
            AlertaStock(id_producto=p.id_producto, sku=p.sku, nombre=p.nombre, stock_actual=p.stock_actual,
                        stock_minimo=p.stock_minimo, estado=p.estado)
            for p in productos[:12]
        ],
        cuentas_por_pagar_cantidad=deuda_n,
        cuentas_por_pagar_usd=round_money(deuda_usd),
    )


@router.get("/movimientos", response_model=Kardex)
def inventory_movements(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    id_producto: int | None = None,
    limite: int = Query(default=1000, ge=1, le=10000),
    db: Session = Depends(get_db),
) -> Kardex:
    """Kárdex: entradas (compras), salidas (ventas), devoluciones (ventas anuladas) y
    ajustes, del más reciente al más antiguo."""
    if hasta < desde:
        raise HTTPException(status_code=422, detail="'hasta' no puede ser anterior a 'desde'.")
    inicio, fin = day_bounds(desde)[0], day_bounds(hasta)[1]
    movimientos: list[Movimiento] = []

    compras = (
        db.query(DetalleCompra, Compra, Producto, Proveedor.nombre, Usuario.nombre_completo)
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .join(Producto, Producto.id_producto == DetalleCompra.id_producto)
        .join(Proveedor, Proveedor.id_proveedor == Compra.id_proveedor)
        .outerjoin(Usuario, Usuario.id_usuario == Compra.id_usuario)
        .filter(Compra.fecha >= desde, Compra.fecha <= hasta)
    )
    if id_producto:
        compras = compras.filter(DetalleCompra.id_producto == id_producto)
    for d, c, p, proveedor, usuario in compras:
        referencia = f"Compra #{c.id_compra} · {proveedor}" + (f" · factura {c.numero_factura}" if c.numero_factura else "")
        movimientos.append(Movimiento(
            fecha=c.fecha_registro or datetime.combine(c.fecha, time()), tipo="entrada", id_producto=p.id_producto,
            sku=p.sku, producto=p.nombre, cantidad=d.cantidad, referencia=referencia, usuario=usuario,
        ))

    ventas = (
        db.query(DetalleVenta, Venta, Producto.sku, Usuario.nombre_completo)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .outerjoin(Usuario, Usuario.id_usuario == Venta.id_usuario)
        .filter(Venta.fecha_venta >= inicio, Venta.fecha_venta < fin)
    )
    if id_producto:
        ventas = ventas.filter(DetalleVenta.id_producto == id_producto)
    filas_ventas = ventas.all()
    # Fecha de la anulación según la auditoría (las anteriores a ella usan la de la venta).
    anuladas = {v.id_venta for _, v, _, _ in filas_ventas if v.estado == VENTA_ANULADA}
    fecha_anulacion: dict[int, tuple] = {}
    if anuladas:
        for id_registro, fecha, nombre in db.query(
            Auditoria.id_registro, Auditoria.fecha, Auditoria.nombre_usuario
        ).filter(
            Auditoria.modulo == "ventas", Auditoria.accion == "anular",
            Auditoria.id_registro.in_([str(i) for i in anuladas]),
        ):
            fecha_anulacion[int(id_registro)] = (fecha, nombre)
    for d, v, sku, usuario in filas_ventas:
        movimientos.append(Movimiento(
            fecha=v.fecha_venta, tipo="salida", id_producto=d.id_producto, sku=sku,
            producto=d.nombre_producto_snapshot, cantidad=-d.cantidad,
            referencia=f"Venta {v.numero_factura}" + (" (anulada)" if v.estado == VENTA_ANULADA else ""),
            usuario=usuario,
        ))
        if v.estado == VENTA_ANULADA:
            fecha, quien = fecha_anulacion.get(v.id_venta, (v.fecha_venta, None))
            movimientos.append(Movimiento(
                fecha=fecha, tipo="devolucion", id_producto=d.id_producto, sku=sku,
                producto=d.nombre_producto_snapshot, cantidad=d.cantidad,
                referencia=f"Anulación de {v.numero_factura}", usuario=quien,
            ))

    ajustes = db.query(AjusteStock).filter(AjusteStock.fecha >= inicio, AjusteStock.fecha < fin)
    if id_producto:
        ajustes = ajustes.filter(AjusteStock.id_producto == id_producto)
    for a in ajustes:
        movimientos.append(Movimiento(
            fecha=a.fecha, tipo="ajuste", id_producto=a.id_producto, sku=a.producto.sku,
            producto=a.producto.nombre, cantidad=a.cantidad,
            referencia=f"Ajuste: {MOTIVOS_AJUSTE.get(a.motivo, a.motivo)} ({a.stock_anterior} → {a.stock_nuevo})",
            usuario=a.usuario.nombre_completo, detalle=a.observacion,
        ))

    movimientos.sort(key=lambda m: m.fecha, reverse=True)
    return Kardex(
        desde=desde, hasta=hasta,
        entradas=sum(m.cantidad for m in movimientos if m.tipo == "entrada"),
        salidas=-sum(m.cantidad for m in movimientos if m.tipo == "salida"),
        devoluciones=sum(m.cantidad for m in movimientos if m.tipo == "devolucion"),
        ajustes=sum(m.cantidad for m in movimientos if m.tipo == "ajuste"),
        movimientos=movimientos[:limite],
        truncado=len(movimientos) > limite,
    )


@router.get("/cuentas-por-pagar", response_model=CuentasPorPagar)
def accounts_payable(db: Session = Depends(get_db)) -> CuentasPorPagar:
    """Compras a proveedores sin pagar, agrupadas por proveedor (la de más deuda primero)."""
    hoy = local_today()
    grupos: dict[int, CuentaPorPagar] = {}
    compras = db.query(Compra).filter(Compra.pagado == 0).order_by(Compra.fecha, Compra.id_compra).all()
    for c in compras:
        p = c.proveedor
        grupo = grupos.get(p.id_proveedor)
        if grupo is None:
            grupo = grupos[p.id_proveedor] = CuentaPorPagar(
                id_proveedor=p.id_proveedor, proveedor=p.nombre, rif=p.rif, telefono=p.telefono,
                compras=0, monto_usd=Decimal("0"), mas_antigua=c.fecha, detalle=[],
            )
        grupo.compras += 1
        grupo.monto_usd = round_money(grupo.monto_usd + c.monto_usd)
        grupo.detalle.append(CompraPendiente(
            id_compra=c.id_compra, numero_factura=c.numero_factura, fecha=c.fecha, monto_usd=c.monto_usd,
            dias=(hoy - c.fecha).days,
        ))
    proveedores = sorted(grupos.values(), key=lambda g: g.monto_usd, reverse=True)
    return CuentasPorPagar(
        total_usd=round_money(sum((g.monto_usd for g in proveedores), Decimal("0"))),
        compras=len(compras),
        proveedores=proveedores,
    )
