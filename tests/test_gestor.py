from io import BytesIO
from datetime import date, datetime, time, timedelta

from openpyxl import load_workbook

from app.core.dates import local_today
from tests.conftest import add_admin, add_cashier, add_gestor, add_product, auth_header
from app.models import Compra, Proveedor, Venta


def test_gestor_can_open_operational_dashboard(client, db_session):
    add_gestor(db_session)

    response = client.get("/reportes/gestor/resumen", headers=auth_header(client, "gestor@test.com"))

    assert response.status_code == 200, response.text
    assert response.json()["ventas_hoy"] == 0
    assert response.json()["stock_critico"] == []


def test_gestor_stock_changes_require_a_justified_adjustment(client, db_session):
    add_gestor(db_session)
    producto = add_product(db_session, "TEST-1", stock=4)
    headers = auth_header(client, "gestor@test.com")

    direct = client.put(
        f"/productos/{producto.id_producto}",
        headers=headers,
        json={"stock_actual": 9},
    )
    adjusted = client.post(
        f"/productos/{producto.id_producto}/ajustes-stock",
        headers=headers,
        json={
            "tipo": "restar",
            "cantidad": 1,
            "motivo": "merma",
            "observacion": "Producto dañado en almacén",
        },
    )

    assert direct.status_code == 403
    assert adjusted.status_code == 201, adjusted.text
    assert adjusted.json()["cantidad"] == -1
    assert adjusted.json()["stock_anterior"] == 4
    assert adjusted.json()["stock_nuevo"] == 3
    assert db_session.refresh(producto) is None
    assert producto.stock_actual == 3
    auditoria = client.get("/auditoria/", headers=headers)
    assert auditoria.status_code == 200, auditoria.text
    assert any(item["accion"] == "ajuste" for item in auditoria.json()["items"])
    assert client.get("/auditoria/exportar", headers=headers).status_code == 403


def test_gestor_cannot_register_a_paid_purchase_or_mark_it_paid(client, db_session):
    add_gestor(db_session)
    producto = add_product(db_session, "TEST-2", stock=0)
    proveedor = Proveedor(nombre="Proveedor de prueba", estado=1)
    db_session.add(proveedor)
    db_session.commit()
    headers = auth_header(client, "gestor@test.com")
    purchase = {
        "id_proveedor": proveedor.id_proveedor,
        "pagado": True,
        "detalles": [{"id_producto": producto.id_producto, "cantidad": 1, "costo_unitario_usd": "10.00"}],
    }

    response = client.post("/compras/", headers=headers, json=purchase)

    assert response.status_code == 403
    assert db_session.query(Compra).count() == 0


def test_gestor_can_register_unpaid_purchase_and_consult_operations(client, db_session):
    add_gestor(db_session)
    producto = add_product(db_session, "TEST-3", stock=0)
    proveedor = Proveedor(nombre="Proveedor operativo", estado=1, rif="J-12345678-9", telefono="04145550141")
    db_session.add(proveedor)
    db_session.commit()
    headers = auth_header(client, "gestor@test.com")
    purchase = {
        "id_proveedor": proveedor.id_proveedor,
        "fecha": date.today().isoformat(),
        "numero_factura": "FAC-3",
        "pagado": False,
        "detalles": [{"id_producto": producto.id_producto, "cantidad": 2, "costo_unitario_usd": "10.00"}],
    }

    created = client.post("/compras/", headers=headers, json=purchase)

    assert created.status_code == 201, created.text
    compra_id = created.json()["id_compra"]
    assert created.json()["pagado"] is False
    assert client.patch(
        f"/compras/{compra_id}/pagado",
        headers=headers,
        json={"pagado": True},
    ).status_code == 403

    payables = client.get("/reportes/gestor/cuentas-por-pagar", headers=headers)
    kardex = client.get(
        f"/reportes/gestor/kardex?desde={date.today()}&hasta={date.today()}",
        headers=headers,
    )
    assert payables.status_code == 200, payables.text
    assert payables.json()["compras"] == 1
    assert kardex.status_code == 200, kardex.text
    assert kardex.json()["entradas"] == 2
    assert kardex.json()["movimientos"][0]["referencia"] == "FAC-3"


def test_gestor_can_export_formatted_excel_with_spanish_text(client, db_session):
    add_gestor(db_session)
    producto = add_product(db_session, "TEST-EXCEL", stock=0)
    producto.nombre = "Neumático ágil"
    proveedor = Proveedor(nombre="Distribución José", estado=1)
    db_session.add(proveedor)
    db_session.commit()
    headers = auth_header(client, "gestor@test.com")
    compra = client.post(
        "/compras/",
        headers=headers,
        json={
            "id_proveedor": proveedor.id_proveedor,
            "fecha": date.today().isoformat(),
            "numero_factura": "FACT-Á-1",
            "pagado": False,
            "detalles": [{"id_producto": producto.id_producto, "cantidad": 2, "costo_unitario_usd": "10.00"}],
        },
    )
    assert compra.status_code == 201, compra.text

    response = client.get(
        "/reportes/gestor/kardex/exportar",
        params={"desde": date.today(), "hasta": date.today()},
        headers=headers,
    )

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.headers["content-disposition"].endswith(".xlsx\"")
    hoja = load_workbook(BytesIO(response.content), data_only=True).active
    assert hoja["A1"].value == "Movimientos de inventario"
    assert "Período:" in hoja["A2"].value
    assert hoja.freeze_panes == "A7"
    assert hoja.auto_filter.ref == "A6:H7"
    assert hoja["D7"].value == "Neumático ágil"
    assert hoja["F7"].value == "FACT-Á-1"
    assert hoja["E7"].value == 2
    assert hoja["E7"].number_format == "+#,##0;-#,##0;0"
    assert hoja["A6"].font.bold is True
    assert hoja["A6"].font.color.rgb.endswith("FFFFFF")


def test_kardex_places_cancelled_sale_return_on_cancellation_day(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)
    add_gestor(db_session)
    producto = add_product(db_session, "TEST-4", stock=5)
    cashier_headers = auth_header(client, "cajero@test.com")
    admin_headers = auth_header(client, "admin@test.com")
    gestor_headers = auth_header(client, "gestor@test.com")

    sale = client.post(
        "/ventas/",
        headers=cashier_headers,
        json={"codigo_moneda_pago": "USD", "detalles": [{"id_producto": producto.id_producto, "cantidad": 1}]},
    )
    assert sale.status_code == 201, sale.text
    fecha_venta = local_today() - timedelta(days=2)
    venta = db_session.query(Venta).filter(Venta.id_venta == sale.json()["id_venta"]).one()
    venta.fecha_venta = datetime.combine(fecha_venta, time.min)
    db_session.commit()
    cancelada = client.post(f"/ventas/{venta.id_venta}/anular", headers=admin_headers)
    assert cancelada.status_code == 200, cancelada.text

    devolucion = client.get(
        f"/reportes/gestor/kardex?desde={local_today()}&hasta={local_today()}",
        headers=gestor_headers,
    )
    salida = client.get(
        f"/reportes/gestor/kardex?desde={fecha_venta}&hasta={fecha_venta}",
        headers=gestor_headers,
    )

    assert devolucion.status_code == 200, devolucion.text
    assert devolucion.json()["devoluciones"] == 1
    assert devolucion.json()["movimientos"][0]["tipo"] == "devolucion"
    assert salida.status_code == 200, salida.text
    assert salida.json()["salidas"] == 1
    assert salida.json()["movimientos"][0]["tipo"] == "salida"
