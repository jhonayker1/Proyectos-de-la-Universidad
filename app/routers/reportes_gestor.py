"""Consultas operativas permitidas al administrador y al gestor."""

from collections import defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from io import BytesIO
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.dates import day_bounds, local_today
from app.core.dependencies import require_roles
from app.core.money import round_money
from app.database.session import get_db
from app.models.auditoria import Auditoria
from app.models.compras import Compra, DetalleCompra
from app.models.inventario import (
    PRODUCTO_AGOTADO,
    PRODUCTO_BAJO_STOCK,
    PRODUCTO_INACTIVO,
    AjusteStock,
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
from app.schemas.ventas import ReporteVentas, VentasPorUsuario

router = APIRouter(
    prefix="/reportes/gestor",
    tags=["reportes operativos"],
    dependencies=[Depends(require_roles(["admin", "gestor"]))],
)

_COLOR_PRINCIPAL = "4F46E5"
_COLOR_TEXTO = "1F2937"
_COLOR_SECUNDARIO = "64748B"
_COLOR_FILA_PAR = "F1F5F9"
_FORMATO_CANTIDAD = '+#,##0;-#,##0;0'
_ETIQUETAS_TIPO = {
    "entrada": "Entrada",
    "salida": "Salida",
    "devolucion": "Devolución",
    "ajuste": "Ajuste",
}


@router.get("/resumen", response_model=ResumenGestor)
def resumen_gestor(db: Session = Depends(get_db)) -> ResumenGestor:
    hoy = local_today()
    resumen = build_summary(db, hoy)
    compras_hoy, unidades_hoy = (
        db.query(func.count(func.distinct(Compra.id_compra)), func.coalesce(func.sum(DetalleCompra.cantidad), 0))
        .outerjoin(DetalleCompra, DetalleCompra.id_compra == Compra.id_compra)
        .filter(Compra.fecha == hoy)
        .one()
    )
    ajustes_hoy = (
        db.query(func.count(AjusteStock.id_ajuste))
        .filter(AjusteStock.fecha >= day_bounds(hoy)[0], AjusteStock.fecha < day_bounds(hoy)[1])
        .scalar()
    )
    pendientes, monto_pendiente = (
        db.query(func.count(Compra.id_compra), func.coalesce(func.sum(Compra.monto_usd), 0))
        .filter(Compra.pagado == 0)
        .one()
    )
    productos = (
        db.query(Producto)
        .filter(Producto.is_deleted.is_(False), Producto.estado != PRODUCTO_INACTIVO)
        .all()
    )
    criticos = sorted(
        (p for p in productos if p.estado in (PRODUCTO_AGOTADO, PRODUCTO_BAJO_STOCK)),
        key=lambda p: (p.stock_actual, p.nombre),
    )
    return ResumenGestor(
        dia=hoy,
        ventas_hoy=resumen.cantidad_ventas,
        articulos_hoy=resumen.articulos_vendidos,
        monto_hoy_usd=resumen.monto_total_usd,
        compras_hoy=int(compras_hoy or 0),
        unidades_entrada_hoy=int(unidades_hoy or 0),
        ajustes_hoy=int(ajustes_hoy or 0),
        productos_bajo_stock=sum(p.estado == PRODUCTO_BAJO_STOCK for p in productos),
        productos_agotados=sum(p.estado == PRODUCTO_AGOTADO for p in productos),
        stock_critico=[
            AlertaStock(
                id_producto=p.id_producto,
                sku=p.sku,
                nombre=p.nombre,
                stock_actual=p.stock_actual,
                stock_minimo=p.stock_minimo,
                estado=p.estado,
            )
            for p in criticos[:20]
        ],
        cuentas_por_pagar_cantidad=int(pendientes or 0),
        cuentas_por_pagar_usd=round_money(monto_pendiente),
    )


@router.get("/ventas-dia", response_model=ReporteVentas)
def ventas_dia(
    dia: date = Query(default_factory=local_today),
    db: Session = Depends(get_db),
) -> ReporteVentas:
    resumen = build_summary(db, dia)
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
        **resumen.model_dump(),
        ventas_anuladas=int(anuladas or 0),
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


@router.get("/cuentas-por-pagar", response_model=CuentasPorPagar)
def cuentas_por_pagar(db: Session = Depends(get_db)) -> CuentasPorPagar:
    rows = (
        db.query(Compra, Proveedor)
        .join(Proveedor, Proveedor.id_proveedor == Compra.id_proveedor)
        .filter(Compra.pagado == 0)
        .order_by(Proveedor.nombre, Compra.fecha, Compra.id_compra)
        .all()
    )
    agrupadas: dict[int, list[Compra]] = defaultdict(list)
    proveedores: dict[int, Proveedor] = {}
    for compra, proveedor in rows:
        agrupadas[proveedor.id_proveedor].append(compra)
        proveedores[proveedor.id_proveedor] = proveedor

    resultado = []
    for id_proveedor, compras in agrupadas.items():
        proveedor = proveedores[id_proveedor]
        resultado.append(
            CuentaPorPagar(
                id_proveedor=id_proveedor,
                proveedor=proveedor.nombre,
                rif=proveedor.rif,
                telefono=proveedor.telefono,
                compras=len(compras),
                monto_usd=round_money(sum((c.monto_usd for c in compras), Decimal("0"))),
                mas_antigua=min(c.fecha for c in compras),
                detalle=[
                    CompraPendiente(
                        id_compra=c.id_compra,
                        numero_factura=c.numero_factura,
                        fecha=c.fecha,
                        monto_usd=c.monto_usd,
                        dias=max((local_today() - c.fecha).days, 0),
                    )
                    for c in compras
                ],
            )
        )
    resultado.sort(key=lambda c: (-c.monto_usd, c.proveedor.lower()))
    return CuentasPorPagar(
        total_usd=round_money(sum((p.monto_usd for p in resultado), Decimal("0"))),
        compras=sum(p.compras for p in resultado),
        proveedores=resultado,
    )


@router.get("/kardex/exportar")
def exportar_kardex_excel(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    id_producto: int | None = Query(default=None, gt=0),
    tipo: Literal["entrada", "salida", "devolucion", "ajuste", "todos"] = "todos",
    limite: int = Query(default=5000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> Response:
    reporte = kardex(desde=desde, hasta=hasta, id_producto=id_producto, limite=limite, db=db)
    movimientos = [
        movimiento
        for movimiento in reporte.movimientos
        if tipo == "todos" or movimiento.tipo == tipo
    ]

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Movimientos"
    hoja.sheet_view.showGridLines = False
    hoja.freeze_panes = "A7"
    hoja.auto_filter.ref = f"A6:H{6 + len(movimientos)}"
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.print_title_rows = "1:6"

    for columna, ancho in enumerate((21, 17, 18, 38, 15, 25, 30, 58), start=1):
        hoja.column_dimensions[chr(64 + columna)].width = ancho

    hoja.merge_cells("A1:H1")
    titulo = hoja["A1"]
    titulo.value = "Movimientos de inventario"
    titulo.font = Font(name="Aptos Display", size=18, bold=True, color="FFFFFF")
    titulo.fill = PatternFill("solid", fgColor=_COLOR_PRINCIPAL)
    titulo.alignment = Alignment(vertical="center")
    hoja.row_dimensions[1].height = 34
    for celdas in hoja.iter_rows(min_row=1, max_row=1, min_col=1, max_col=8):
        for celda in celdas:
            celda.fill = PatternFill("solid", fgColor=_COLOR_PRINCIPAL)

    producto = next(
        (f"{m.sku} · {m.producto}" for m in reporte.movimientos if m.id_producto == id_producto),
        f"ID {id_producto}" if id_producto else "Todos los productos",
    )
    hoja.merge_cells("A2:H2")
    hoja["A2"] = (
        f"Período: {desde:%d/%m/%Y} – {hasta:%d/%m/%Y}   ·   "
        f"Producto: {producto}   ·   Tipo: "
        f"{_ETIQUETAS_TIPO.get(tipo, 'Todos')}"
    )
    hoja["A2"].font = Font(name="Aptos", size=10, color=_COLOR_SECUNDARIO)
    hoja["A2"].alignment = Alignment(wrap_text=True, vertical="center")
    hoja.row_dimensions[2].height = 30

    if reporte.truncado:
        hoja.merge_cells("A3:H3")
        hoja["A3"] = f"Se muestran los {limite} movimientos más recientes del período."
        hoja["A3"].font = Font(name="Aptos", size=9, italic=True, color=_COLOR_SECUNDARIO)

    resumen = (
        ("Entradas", reporte.entradas),
        ("Salidas", reporte.salidas),
        ("Devoluciones", reporte.devoluciones),
        ("Ajustes (neto)", reporte.ajustes),
    )
    for indice, (etiqueta, valor) in enumerate(resumen):
        columna_etiqueta = indice * 2 + 1
        celda_etiqueta = hoja.cell(row=4, column=columna_etiqueta, value=etiqueta)
        celda_valor = hoja.cell(row=4, column=columna_etiqueta + 1, value=valor)
        for celda in (celda_etiqueta, celda_valor):
            celda.fill = PatternFill("solid", fgColor="EEF2FF")
            celda.alignment = Alignment(vertical="center")
        celda_etiqueta.font = Font(name="Aptos", size=9, bold=True, color=_COLOR_SECUNDARIO)
        celda_valor.font = Font(name="Aptos", size=11, bold=True, color=_COLOR_PRINCIPAL)
        celda_valor.number_format = _FORMATO_CANTIDAD
    hoja.row_dimensions[4].height = 25

    encabezados = ["Fecha", "Tipo", "SKU", "Producto", "Cantidad", "Referencia", "Usuario", "Detalle"]
    for columna, texto in enumerate(encabezados, start=1):
        celda = hoja.cell(row=6, column=columna, value=texto)
        celda.font = Font(name="Aptos", size=10, bold=True, color="FFFFFF")
        celda.fill = PatternFill("solid", fgColor=_COLOR_PRINCIPAL)
        celda.alignment = Alignment(horizontal="center", vertical="center")
    hoja.row_dimensions[6].height = 24

    borde_fila = Border(bottom=Side(style="hair", color="CBD5E1"))
    for fila, movimiento in enumerate(movimientos, start=7):
        valores = (
            movimiento.fecha.replace(tzinfo=None),
            _ETIQUETAS_TIPO[movimiento.tipo],
            movimiento.sku,
            movimiento.producto,
            movimiento.cantidad,
            movimiento.referencia,
            movimiento.usuario or "—",
            movimiento.detalle or "",
        )
        for columna, valor in enumerate(valores, start=1):
            celda = hoja.cell(row=fila, column=columna, value=valor)
            if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")):
                celda.data_type = "s"
            celda.font = Font(name="Aptos", size=10, color=_COLOR_TEXTO)
            celda.alignment = Alignment(vertical="top", wrap_text=columna in (4, 6, 7, 8))
            celda.border = borde_fila
            if fila % 2 == 0:
                celda.fill = PatternFill("solid", fgColor=_COLOR_FILA_PAR)
            if columna == 1:
                celda.number_format = "dd/mm/yyyy hh:mm"
            elif columna == 5:
                celda.number_format = _FORMATO_CANTIDAD
                celda.font = Font(
                    name="Aptos",
                    size=10,
                    bold=True,
                    color="15803D" if valor > 0 else "B91C1C" if valor < 0 else _COLOR_TEXTO,
                )
        hoja.row_dimensions[fila].height = 30

    salida = BytesIO()
    libro.save(salida)
    nombre = f"movimientos_{desde.isoformat()}_{hasta.isoformat()}.xlsx"
    return Response(
        content=salida.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nombre}"'},
    )


@router.get("/kardex", response_model=Kardex)
def kardex(
    desde: date = Query(default_factory=lambda: local_today().replace(day=1)),
    hasta: date = Query(default_factory=local_today),
    id_producto: int | None = Query(default=None, gt=0),
    limite: int = Query(default=5000, ge=1, le=5000),
    db: Session = Depends(get_db),
) -> Kardex:
    if desde > hasta:
        raise HTTPException(status_code=422, detail="'desde' no puede ser posterior a 'hasta'.")
    registros: list[Movimiento] = []
    compras_query = (
        db.query(DetalleCompra, Compra, Producto, Usuario)
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .join(Producto, Producto.id_producto == DetalleCompra.id_producto)
        .join(Usuario, Usuario.id_usuario == Compra.id_usuario)
        .filter(Compra.fecha >= desde, Compra.fecha <= hasta)
    )
    ventas_query = (
        db.query(DetalleVenta, Venta, Producto, Usuario)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .join(Usuario, Usuario.id_usuario == Venta.id_usuario)
    )
    ventas_query = filter_by_range(ventas_query, desde, hasta)
    ajustes_query = db.query(AjusteStock).filter(
        AjusteStock.fecha >= day_bounds(desde)[0],
        AjusteStock.fecha < day_bounds(hasta)[1],
    )
    if id_producto is not None:
        compras_query = compras_query.filter(Producto.id_producto == id_producto)
        ventas_query = ventas_query.filter(Producto.id_producto == id_producto)
        ajustes_query = ajustes_query.filter(AjusteStock.id_producto == id_producto)

    cancelaciones = (
        db.query(Auditoria.id_registro, Auditoria.fecha)
        .filter(
            Auditoria.modulo == "ventas",
            Auditoria.accion == "anular",
            Auditoria.fecha >= day_bounds(desde)[0],
            Auditoria.fecha < day_bounds(hasta)[1],
        )
        .all()
    )
    fecha_anulacion = {
        int(id_registro): fecha
        for id_registro, fecha in cancelaciones
        if id_registro and id_registro.isdigit()
    }

    entradas = (
        db.query(func.coalesce(func.sum(DetalleCompra.cantidad), 0))
        .join(Compra, Compra.id_compra == DetalleCompra.id_compra)
        .filter(Compra.fecha >= desde, Compra.fecha <= hasta)
    )
    ventas_base = (
        db.query(func.coalesce(func.sum(DetalleVenta.cantidad), 0))
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
    )
    if id_producto is not None:
        entradas = entradas.filter(DetalleCompra.id_producto == id_producto)
        ventas_base = ventas_base.filter(DetalleVenta.id_producto == id_producto)
    entradas = int(entradas.scalar() or 0)
    salidas = int(filter_by_range(ventas_base, desde, hasta).scalar() or 0)
    devoluciones_query = db.query(func.coalesce(func.sum(DetalleVenta.cantidad), 0))
    if fecha_anulacion:
        devoluciones_query = devoluciones_query.filter(
            DetalleVenta.id_venta.in_(fecha_anulacion)
        )
        if id_producto is not None:
            devoluciones_query = devoluciones_query.filter(
                DetalleVenta.id_producto == id_producto
            )
        devoluciones = int(devoluciones_query.scalar() or 0)
    else:
        devoluciones = 0
    ajustes = int(
        db.query(func.coalesce(func.sum(AjusteStock.cantidad), 0))
        .filter(
            AjusteStock.fecha >= day_bounds(desde)[0],
            AjusteStock.fecha < day_bounds(hasta)[1],
            *([AjusteStock.id_producto == id_producto] if id_producto is not None else []),
        )
        .scalar()
        or 0
    )

    compras_query = compras_query.order_by(Compra.fecha.desc(), Compra.id_compra.desc()).limit(limite + 1)
    ventas_query = ventas_query.order_by(Venta.fecha_venta.desc(), Venta.id_venta.desc()).limit(limite + 1)
    ajustes_query = ajustes_query.order_by(AjusteStock.fecha.desc(), AjusteStock.id_ajuste.desc()).limit(limite + 1)
    devoluciones_query = (
        db.query(DetalleVenta, Venta, Producto, Usuario)
        .join(Venta, Venta.id_venta == DetalleVenta.id_venta)
        .join(Producto, Producto.id_producto == DetalleVenta.id_producto)
        .join(Usuario, Usuario.id_usuario == Venta.id_usuario)
        .filter(Venta.id_venta.in_(fecha_anulacion))
        .order_by(Venta.id_venta.desc(), DetalleVenta.id_detalle)
        .limit(limite + 1)
    ) if fecha_anulacion else None
    if devoluciones_query is not None and id_producto is not None:
        devoluciones_query = devoluciones_query.filter(Producto.id_producto == id_producto)

    for detalle, compra, producto, usuario in compras_query.all():
        registros.append(Movimiento(
            fecha=datetime.combine(compra.fecha, time.min),
            tipo="entrada",
            id_producto=producto.id_producto,
            sku=producto.sku,
            producto=producto.nombre,
            cantidad=detalle.cantidad,
            referencia=compra.numero_factura or f"Compra #{compra.id_compra}",
            usuario=usuario.nombre_completo,
            detalle=compra.descripcion,
        ))
    for detalle, venta, producto, usuario in ventas_query.all():
        registros.append(Movimiento(
            fecha=venta.fecha_venta or datetime.combine(desde, time.min),
            tipo="salida",
            id_producto=producto.id_producto,
            sku=producto.sku,
            producto=producto.nombre,
            cantidad=-detalle.cantidad,
            referencia=venta.numero_factura,
            usuario=usuario.nombre_completo,
        ))
    if devoluciones_query is not None:
        for detalle, venta, producto, usuario in devoluciones_query.all():
            registros.append(Movimiento(
                fecha=fecha_anulacion[venta.id_venta],
                tipo="devolucion",
                id_producto=producto.id_producto,
                sku=producto.sku,
                producto=producto.nombre,
                cantidad=detalle.cantidad,
                referencia=venta.numero_factura,
                usuario=usuario.nombre_completo,
                detalle="Venta anulada",
            ))
    for ajuste in ajustes_query.all():
        producto = ajuste.producto
        registros.append(Movimiento(
            fecha=ajuste.fecha,
            tipo="ajuste",
            id_producto=producto.id_producto,
            sku=producto.sku,
            producto=producto.nombre,
            cantidad=ajuste.cantidad,
            referencia=f"Ajuste #{ajuste.id_ajuste}",
            usuario=ajuste.usuario.nombre_completo if ajuste.usuario else None,
            detalle=f"{ajuste.motivo}: {ajuste.observacion}",
        ))

    registros.sort(key=lambda m: m.fecha, reverse=True)
    truncado = len(registros) > limite
    return Kardex(
        desde=desde,
        hasta=hasta,
        entradas=entradas,
        salidas=salidas,
        devoluciones=devoluciones,
        ajustes=ajustes,
        movimientos=registros[:limite],
        truncado=truncado,
    )
