from app.models import Producto, TasaCambio
from tests.conftest import add_admin, add_cashier, add_product, auth_header, set_rate


def stock(db_session, id_producto: int) -> int:
    db_session.expire_all()
    return db_session.query(Producto).filter(Producto.id_producto == id_producto).one().stock_actual


def test_catalog_products_and_sale_in_bolivares(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)
    add_cashier(db_session, "otro@test.com")
    admin = auth_header(client, "admin@test.com")
    cajero = auth_header(client, "cajero@test.com")
    otro = auth_header(client, "otro@test.com")

    marca = client.post("/marcas/", headers=admin, json={"nombre": "Pirelli", "pais_origen": "Italia"})
    assert marca.status_code == 201, marca.text
    producto = client.post(
        "/productos/",
        headers=admin,
        json={
            "sku": "cau-175",
            "nombre": "Caucho 175/70 R13",
            "id_categoria": 1,
            "id_marca": marca.json()["id_marca"],
            "precio_distribuidor": "30.00",
            "precio_usd": "45.50",
            "stock_actual": 4,
            "stock_minimo": 2,
        },
    )
    assert producto.status_code == 201, producto.text
    assert producto.json()["sku"] == "CAU-175"
    assert producto.json()["estado"] == "Disponible"
    id_producto = producto.json()["id_producto"]

    set_rate(client, admin, "36.5000")
    assert client.get("/tasas/vigente", headers=cajero).json()["tasa_venta"] == "36.5000"

    listado = client.get("/productos/", headers=cajero).json()
    assert "precio_distribuidor" not in listado[0]
    assert listado[0]["nombre_marca"] == "Pirelli"
    assert listado[0]["nombre_categoria"] == "Cauchos"
    assert listado[0]["precio_local"] == "1660.75"

    venta = client.post(
        "/ventas/",
        headers=cajero,
        json={
            "codigo_moneda_pago": "VES",
            "referencia_pago": "PM-123",
            "detalles": [{"id_producto": id_producto, "cantidad": 3}],
        },
    )
    assert venta.status_code == 201, venta.text
    data = venta.json()
    assert data["numero_factura"] == f"F-{data['id_venta']:08d}"
    assert data["monto_total_usd"] == "136.50"
    assert data["tasa_aplicada"] == "36.5000"
    assert data["monto_total_moneda"] == "4982.25"
    assert data["detalles"][0]["nombre_producto_snapshot"] == "Caucho 175/70 R13"
    assert stock(db_session, id_producto) == 1
    assert db_session.get(Producto, id_producto).estado == "Bajo Stock"

    # Una tasa nueva no cambia la venta registrada y desactiva la anterior.
    set_rate(client, admin, "40")
    assert client.get(f"/ventas/{data['id_venta']}", headers=cajero).json()[
        "monto_total_moneda"
    ] == "4982.25"
    assert db_session.query(TasaCambio).filter(TasaCambio.estado == 1).count() == 1

    assert len(client.get("/ventas/", headers=cajero).json()) == 1
    assert client.get("/ventas/", headers=otro).json() == []
    assert client.get(f"/ventas/{data['id_venta']}", headers=otro).status_code == 404

    resumen = client.get("/ventas/mi-resumen", headers=cajero).json()
    assert resumen["cantidad_ventas"] == 1
    assert resumen["por_moneda"] == [
        {"codigo_moneda": "VES", "cantidad_ventas": 1, "monto_total_moneda": "4982.25"}
    ]
    bajos = client.get("/productos/stock-bajo", headers=admin).json()
    assert [p["sku"] for p in bajos] == ["CAU-175"]


def test_sale_in_usd_needs_no_rate(client, db_session):
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")
    producto = add_product(db_session, "USD-1", stock=2, precio_usd="10.00")

    venta = client.post(
        "/ventas/",
        headers=cajero,
        json={"codigo_moneda_pago": "USD", "detalles": [{"id_producto": producto.id_producto}]},
    )

    assert venta.status_code == 201, venta.text
    assert venta.json()["tasa_aplicada"] == "1.0000"
    assert venta.json()["monto_total_moneda"] == "10.00"


def test_stock_status_follows_sales_and_cancellations(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    producto = add_product(db_session, "EST-1", stock=2)

    venta = client.post(
        "/ventas/",
        headers=admin,
        json={"codigo_moneda_pago": "USD",
              "detalles": [{"id_producto": producto.id_producto, "cantidad": 2}]},
    ).json()
    db_session.expire_all()
    assert db_session.get(Producto, producto.id_producto).estado == "Agotado"

    client.post(f"/ventas/{venta['id_venta']}/anular", headers=admin)
    db_session.expire_all()
    assert db_session.get(Producto, producto.id_producto).estado == "Disponible"

    client.delete(f"/productos/{producto.id_producto}", headers=admin)
    assert client.get(f"/productos/{producto.id_producto}", headers=admin).status_code == 404
    reactivado = client.put(
        f"/productos/{producto.id_producto}", headers=admin, json={"estado": "Disponible"}
    )
    assert reactivado.json()["estado"] == "Disponible"


def test_sale_in_bolivares_requires_rate(client, db_session):
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")
    producto = add_product(db_session, "NOR-1", stock=5)

    response = client.post(
        "/ventas/",
        headers=cajero,
        json={"codigo_moneda_pago": "VES", "detalles": [{"id_producto": producto.id_producto}]},
    )

    assert response.status_code == 409
    assert stock(db_session, producto.id_producto) == 5


def test_insufficient_stock_rejects_sale(client, db_session):
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")
    producto = add_product(db_session, "FRE-1", stock=1)

    response = client.post(
        "/ventas/",
        headers=cajero,
        json={
            "codigo_moneda_pago": "USD",
            "detalles": [
                {"id_producto": producto.id_producto, "cantidad": 1},
                {"id_producto": producto.id_producto, "cantidad": 1},
            ],
        },
    )

    assert response.status_code == 409
    assert stock(db_session, producto.id_producto) == 1


def test_admin_cancels_sale_and_report(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)
    admin = auth_header(client, "admin@test.com")
    cajero = auth_header(client, "cajero@test.com")
    producto = add_product(db_session, "BUJ-1", stock=10, precio_usd="2.00")

    ventas = [
        client.post(
            "/ventas/",
            headers=headers,
            json={"codigo_moneda_pago": "USD",
                  "detalles": [{"id_producto": producto.id_producto, "cantidad": 2}]},
        ).json()
        for headers in (admin, cajero, cajero)
    ]
    anular = f"/ventas/{ventas[0]['id_venta']}/anular"
    assert client.post(anular, headers=cajero).status_code == 403
    anulada = client.post(anular, headers=admin)
    assert anulada.status_code == 200, anulada.text
    assert anulada.json()["estado"] == "Anulada"
    assert client.post(anular, headers=admin).status_code == 409
    assert stock(db_session, producto.id_producto) == 6

    reporte = client.get("/reportes/ventas", headers=admin).json()
    assert reporte["cantidad_ventas"] == 2
    assert reporte["ventas_anuladas"] == 1
    assert reporte["monto_total_usd"] == "8.00"
    assert [(u["nombre_completo"], u["cantidad_ventas"]) for u in reporte["por_usuario"]] == [
        ("cajero", 2)
    ]


def test_cashier_cannot_manage_catalog_rates_or_reports(client, db_session):
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")

    assert client.post(
        "/productos/",
        headers=cajero,
        json={"sku": "X-1", "nombre": "X", "id_categoria": 1, "precio_usd": "1.00"},
    ).status_code == 403
    assert client.post("/categorias/", headers=cajero, json={"nombre": "Nueva"}).status_code == 403
    assert client.get("/productos/admin", headers=cajero).status_code == 403
    assert client.post(
        "/tasas/", headers=cajero, json={"codigo_moneda": "VES", "tasa_venta": "50"}
    ).status_code == 403
    assert client.get("/reportes/ventas", headers=cajero).status_code == 403
    assert client.get("/categorias/", headers=cajero).status_code == 200
