import pytest

from app.core.config import settings
from app.models import Categoria, Producto, Proveedor, Usuario
from tests.conftest import PASSWORD, add_admin, add_cashier, add_product, auth_header

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00"
    b"\x00\x00\x00IEND\xaeB`\x82"
)


def producto(db_session, id_producto: int) -> Producto:
    db_session.expire_all()
    return db_session.get(Producto, id_producto)


def test_price_follows_category_margin_and_own_margin(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")

    assert client.put("/categorias/1", headers=admin, json={"margen_ganancia": "30"}).status_code == 200
    creado = client.post(
        "/productos/",
        headers=admin,
        json={"sku": "m-1", "nombre": "Caucho", "id_categoria": 1, "precio_distribuidor": "100.00"},
    ).json()
    assert creado["precio_usd"] == "130.00"
    assert creado["margen_efectivo"] == "30.00"

    propio = client.put(
        f"/productos/{creado['id_producto']}", headers=admin, json={"margen_pct": "50"}
    ).json()
    assert propio["precio_usd"] == "150.00"

    # Cambiar el margen de la categoría solo afecta a productos sin margen propio.
    otro = add_product(db_session, "M-2", stock=1, precio_usd="0")
    otro.precio_distribuidor = 10
    db_session.commit()
    client.put("/categorias/1", headers=admin, json={"margen_ganancia": "40"})
    assert producto(db_session, creado["id_producto"]).precio_usd == 150
    assert producto(db_session, otro.id_producto).precio_usd == 14

    assert client.put("/categorias/1", headers=admin, json={"margen_ganancia": None}).status_code == 422


def test_zero_margin_keeps_manual_price(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    p = add_product(db_session, "MAN-1", stock=3, precio_usd="25.00")

    # Margen 0 (valor tras la migración): cambiar el costo no baja el precio al costo.
    actualizado = client.put(
        f"/productos/{p.id_producto}", headers=admin, json={"precio_distribuidor": "20.00"}
    ).json()
    assert actualizado["precio_usd"] == "25.00"


def test_purchase_adds_stock_updates_cost_and_debt(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    db_session.add(Proveedor(nombre="Dist. Goodyear", estado=1))
    db_session.get(Categoria, 1).margen_ganancia = 25
    db_session.commit()
    p = add_product(db_session, "CMP-1", stock=0)
    assert producto(db_session, p.id_producto).estado == "Disponible"

    compra = client.post(
        "/compras/",
        headers=admin,
        json={
            "id_proveedor": 1,
            "numero_factura": "F-004512",
            "detalles": [{"id_producto": p.id_producto, "cantidad": 40, "costo_unitario_usd": "80.00"}],
        },
    )
    assert compra.status_code == 201, compra.text
    data = compra.json()
    assert data["monto_usd"] == "3200.00"
    assert data["pagado"] is False
    stored = producto(db_session, p.id_producto)
    assert stored.stock_actual == 40
    assert stored.precio_distribuidor == 80
    assert stored.precio_usd == 100

    entradas = client.get("/compras/entradas-recientes", headers=admin).json()
    assert entradas[0]["cantidad"] == 40
    assert entradas[0]["nombre_proveedor"] == "Dist. Goodyear"
    assert len(client.get("/compras/?pagado=false", headers=admin).json()) == 1
    pagada = client.patch(f"/compras/{data['id_compra']}/pagado", headers=admin, json={"pagado": True})
    assert pagada.json()["pagado"] is True
    assert client.get("/compras/?pagado=false", headers=admin).json() == []

    assert client.post(
        "/compras/", headers=admin, json={"id_proveedor": 1}
    ).status_code == 422


def test_delete_product_without_history_removes_it(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    p = add_product(db_session, "BORRAR-1", stock=3)

    assert client.delete(f"/productos/{p.id_producto}", headers=admin).status_code == 204

    db_session.expire_all()
    assert db_session.get(Producto, p.id_producto) is None
    assert client.get("/productos/admin", headers=admin).json() == []


def test_delete_product_with_sales_hides_it_and_keeps_history(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    p = add_product(db_session, "HIST-1", stock=5, precio_usd="10.00")
    venta = client.post("/ventas/", headers=admin, json={
        "codigo_moneda_pago": "USD", "detalles": [{"id_producto": p.id_producto, "cantidad": 2}]}).json()

    assert client.delete(f"/productos/{p.id_producto}", headers=admin).status_code == 204

    # Desaparece de todas las listas…
    assert client.get("/productos/admin", headers=admin).json() == []
    assert client.get("/productos/", headers=admin).json() == []
    assert client.get(f"/productos/{p.id_producto}", headers=admin).status_code == 404
    # …pero la venta conserva su detalle.
    detalle = client.get(f"/ventas/{venta['id_venta']}", headers=admin).json()["detalles"][0]
    assert detalle["nombre_producto_snapshot"] == "Producto HIST-1"
    # El SKU queda libre para un producto nuevo.
    nuevo = client.post("/productos/", headers=admin, json={
        "sku": "HIST-1", "nombre": "Reemplazo", "id_categoria": 1, "precio_usd": "12.00"})
    assert nuevo.status_code == 201, nuevo.text
    ocultos = client.get("/productos/admin?incluir_eliminados=true", headers=admin).json()
    assert {x["sku"] for x in ocultos} == {"HIST-1", f"HIST-1~{p.id_producto}"}


def test_category_with_stock_cannot_be_deactivated(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    con_stock = add_product(db_session, "STK-1", stock=4)
    add_product(db_session, "STK-2", stock=0)  # sin stock: no impide

    por_delete = client.delete("/categorias/1", headers=admin)
    assert por_delete.status_code == 409
    assert "1 producto(s) con stock (4 unidades)" in por_delete.json()["detail"]
    assert "Producto STK-1" in por_delete.json()["detail"]
    # Desactivar editando el estado tampoco se permite.
    assert client.put("/categorias/1", headers=admin, json={"estado": 0}).status_code == 409
    assert db_session.get(Categoria, 1).estado == 1

    # Un producto dado de baja (Inactivo) no cuenta aunque tenga stock.
    client.delete(f"/productos/{con_stock.id_producto}", headers=admin)
    assert client.delete("/categorias/1", headers=admin).status_code == 204
    db_session.expire_all()
    assert db_session.get(Categoria, 1).estado == 0
    # Reactivar sigue permitido.
    assert client.put("/categorias/1", headers=admin, json={"estado": 1}).status_code == 200


def test_category_deactivation_allowed_when_stock_is_zero(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    add_product(db_session, "CERO-1", stock=0)

    assert client.put("/categorias/1", headers=admin, json={"estado": 0}).status_code == 200


def test_supplier_with_pending_purchases_cannot_be_deleted(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    db_session.add(Proveedor(nombre="Dist. Goodyear", estado=1))
    db_session.commit()
    compra = client.post("/compras/", headers=admin, json={"id_proveedor": 1, "monto_usd": "1250.50"}).json()

    bloqueado = client.delete("/proveedores/1", headers=admin)
    assert bloqueado.status_code == 409
    assert "1 compra(s) pendiente(s)" in bloqueado.json()["detail"]
    assert "$1,250.50" in bloqueado.json()["detail"]
    assert [p["nombre"] for p in client.get("/proveedores/", headers=admin).json()] == ["Dist. Goodyear"]

    client.patch(f"/compras/{compra['id_compra']}/pagado", headers=admin, json={"pagado": True})
    assert client.delete("/proveedores/1", headers=admin).status_code == 204
    # Sale de la lista activa, pero su historial de compras se conserva.
    assert client.get("/proveedores/", headers=admin).json() == []
    assert len(client.get("/compras/?id_proveedor=1", headers=admin).json()) == 1
    # A un proveedor eliminado ya no se le registran compras.
    assert client.post("/compras/", headers=admin, json={"id_proveedor": 1, "monto_usd": "10"}).status_code == 404


def test_supplier_extended_fields(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")

    creado = client.post(
        "/proveedores/",
        headers=admin,
        json={"nombre": "Bosch Occidente", "rif": "J-31002244-5", "contacto": "Luis",
              "telefono": "+58 261 555 0123", "correo": "comercial@bosch.example",
              "ciudad": "Maracaibo", "condiciones": "Crédito a 15 días"},
    )
    assert creado.status_code == 201, creado.text
    assert creado.json()["ciudad"] == "Maracaibo"
    assert client.post(
        "/proveedores/", headers=admin,
        json={"nombre": "X", "rif": "J-1234567", "telefono": "04141234567", "correo": "no-es-correo"},
    ).status_code == 422


VALIDO = {"nombre": "Prov", "rif": "J-30123456-7", "telefono": "0414-555-0141", "correo": "v@prov.example"}


@pytest.mark.parametrize("rif, esperado", [
    ("J-30123456-7", "J-30123456-7"),
    ("j301234567", "J-30123456-7"),      # minúscula y sin guiones: se normaliza
    (" v 12345678 ", "V-12345678"),
    ("G-20000001-0", "G-20000001-0"),
])
def test_supplier_rif_is_normalized(client, db_session, rif, esperado):
    add_admin(db_session)
    r = client.post("/proveedores/", headers=auth_header(client, "admin@test.com"), json={**VALIDO, "rif": rif})
    assert r.status_code == 201, r.text
    assert r.json()["rif"] == esperado


@pytest.mark.parametrize("cambio, mensaje", [
    ({"rif": "30123456-7"}, "debe comenzar con una letra"),
    ({"rif": "X-30123456-7"}, "RIF inválido"),
    ({"rif": "J-ABC"}, "RIF inválido"),
    ({"rif": "  "}, "El RIF es obligatorio"),
    ({"telefono": ""}, "El teléfono es obligatorio"),
    ({"telefono": "abc-1234"}, "solo puede tener números"),
    ({"telefono": "123"}, "entre 7 y 15 dígitos"),
    ({"correo": ""}, "correo"),
])
def test_supplier_create_rejects_invalid_data(client, db_session, cambio, mensaje):
    add_admin(db_session)
    r = client.post("/proveedores/", headers=auth_header(client, "admin@test.com"), json={**VALIDO, **cambio})
    assert r.status_code == 422
    assert mensaje in str(r.json()["detail"])


@pytest.mark.parametrize("faltante", ["rif", "telefono", "correo"])
def test_supplier_create_requires_rif_phone_and_email(client, db_session, faltante):
    add_admin(db_session)
    datos = {k: v for k, v in VALIDO.items() if k != faltante}
    r = client.post("/proveedores/", headers=auth_header(client, "admin@test.com"), json=datos)
    assert r.status_code == 422


def test_supplier_edit_cannot_clear_or_break_required_fields(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    p = client.post("/proveedores/", headers=admin, json=VALIDO).json()
    url = f"/proveedores/{p['id_proveedor']}"

    for campo in ("rif", "telefono", "correo"):
        assert client.put(url, headers=admin, json={campo: None}).status_code == 422
    assert client.put(url, headers=admin, json={"telefono": ""}).status_code == 422
    assert client.put(url, headers=admin, json={"rif": "12345678"}).status_code == 422
    ok = client.put(url, headers=admin, json={"rif": "e-8123456", "ciudad": "Valencia"})
    assert ok.status_code == 200
    assert ok.json()["rif"] == "E-8123456"


def test_user_edit_password_reset_and_delete(client, db_session):
    add_admin(db_session)
    cajero = add_cashier(db_session)
    admin = auth_header(client, "admin@test.com")

    editado = client.put(
        f"/usuarios/{cajero.id_usuario}",
        headers=admin,
        json={"nombre_completo": "Carlos Pérez", "permisos": "Ventas, apertura de caja"},
    )
    assert editado.status_code == 200, editado.text
    assert editado.json()["permisos"] == "Ventas, apertura de caja"
    assert client.put(
        f"/usuarios/{cajero.id_usuario}", headers=admin, json={"correo": "admin@test.com"}
    ).status_code == 409

    assert client.patch(
        f"/usuarios/{cajero.id_usuario}/password", headers=admin, json={"password": "nueva-clave-1"}
    ).status_code == 204
    assert client.post(
        "/auth/login", json={"correo": "cajero@test.com", "password": PASSWORD}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"correo": "cajero@test.com", "password": "nueva-clave-1"}
    ).status_code == 200

    assert client.delete(f"/usuarios/{cajero.id_usuario}", headers=admin).status_code == 204
    assert db_session.query(Usuario).filter(Usuario.correo == "cajero@test.com").first() is None


def test_user_with_sales_cannot_be_deleted(client, db_session):
    add_admin(db_session)
    cajero = add_cashier(db_session)
    p = add_product(db_session, "DEL-1", stock=2)
    client.post(
        "/ventas/",
        headers=auth_header(client, "cajero@test.com"),
        json={"codigo_moneda_pago": "USD", "detalles": [{"id_producto": p.id_producto}]},
    )

    response = client.delete(
        f"/usuarios/{cajero.id_usuario}", headers=auth_header(client, "admin@test.com")
    )

    assert response.status_code == 409


def test_invoice_upload_download_and_validation(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    add_admin(db_session)
    add_cashier(db_session)
    admin = auth_header(client, "admin@test.com")

    subida = client.post(
        "/facturas/", headers=admin, files={"archivo": ("factura.png", PNG_1PX, "image/png")}
    )
    assert subida.status_code == 201, subida.text
    factura = subida.json()
    assert factura["nombre_original"] == "factura.png"
    assert len(list((tmp_path / "facturas").iterdir())) == 1

    archivo = client.get(f"/facturas/{factura['id_factura_img']}/archivo", headers=admin)
    assert archivo.content == PNG_1PX
    assert len(client.get("/facturas/", headers=admin).json()) == 1

    falsa = client.post(
        "/facturas/", headers=admin, files={"archivo": ("x.png", b"no soy png", "image/png")}
    )
    assert falsa.status_code == 415
    texto = client.post(
        "/facturas/", headers=admin, files={"archivo": ("x.txt", b"hola", "text/plain")}
    )
    assert texto.status_code == 415
    assert client.post(
        "/facturas/",
        headers=auth_header(client, "cajero@test.com"),
        files={"archivo": ("factura.png", PNG_1PX, "image/png")},
    ).status_code == 403

    assert client.delete(f"/facturas/{factura['id_factura_img']}", headers=admin).status_code == 204
    assert list((tmp_path / "facturas").iterdir()) == []


def test_dashboard_series_top_and_stock_reports(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)
    admin = auth_header(client, "admin@test.com")
    cajero = auth_header(client, "cajero@test.com")
    a = add_product(db_session, "TOP-A", stock=10, precio_usd="10.00")
    b = add_product(db_session, "TOP-B", stock=10, precio_usd="5.00")
    client.post("/ventas/", headers=cajero, json={"codigo_moneda_pago": "USD", "detalles": [
        {"id_producto": a.id_producto, "cantidad": 3}, {"id_producto": b.id_producto, "cantidad": 1}]})
    client.post("/ventas/", headers=cajero, json={"codigo_moneda_pago": "USD", "detalles": [
        {"id_producto": b.id_producto, "cantidad": 1}]})

    dash = client.get("/reportes/dashboard", headers=admin).json()
    assert dash["ventas_hoy_usd"] == "40.00"
    assert dash["ventas_hoy_cantidad"] == 2
    assert dash["articulos_hoy"] == 5
    assert dash["ventas_mes_usd"] == "40.00"
    assert dash["unidades_en_stock"] == 15

    horas = client.get("/reportes/serie-ventas?agrupar=hora", headers=admin).json()
    assert len(horas) == 24
    assert sum(p["cantidad_ventas"] for p in horas) == 2
    dias = client.get("/reportes/serie-ventas?agrupar=dia", headers=admin).json()
    assert len(dias) == 1 and dias[0]["monto_total_usd"] == "40.00"

    top = client.get("/reportes/top-productos", headers=admin).json()
    assert [(t["nombre_producto"], t["unidades"]) for t in top] == [
        ("Producto TOP-A", 3), ("Producto TOP-B", 2)
    ]
    stock = client.get("/reportes/stock-por-categoria", headers=admin).json()
    assert stock[0]["nombre_categoria"] == "Cauchos" and stock[0]["unidades"] == 15

    resumen = client.get("/ventas/mi-resumen", headers=cajero).json()
    assert resumen["articulos_vendidos"] == 5
    rango = client.get("/ventas/?desde=2000-01-01", headers=cajero).json()
    assert len(rango) == 2 and rango[0]["nombre_usuario"] == "cajero"
    assert client.get("/ventas/?desde=2026-02-01&hasta=2026-01-01", headers=cajero).status_code == 422

    db_session.add(Proveedor(nombre="Prov", estado=1))
    db_session.commit()
    client.post("/compras/", headers=admin, json={"id_proveedor": 1, "detalles": [
        {"id_producto": a.id_producto, "cantidad": 12, "costo_unitario_usd": "4.00"}]})
    mov = client.get("/reportes/movimientos-stock", headers=admin).json()
    assert (mov["entradas"], mov["salidas"], mov["neto"]) == (12, 5, 7)
    assert mov["ingresos_por_producto"][0]["nombre_producto"] == "Producto TOP-A"
    cats = client.get("/reportes/ventas-por-categoria", headers=admin).json()
    assert cats == [{"id_categoria": 1, "nombre_categoria": "Cauchos", "unidades": 5,
                     "monto_total_usd": "40.00"}]

    for path in ("/reportes/dashboard", "/reportes/serie-ventas", "/reportes/movimientos-stock",
                 "/compras/", "/facturas/"):
        assert client.get(path, headers=cajero).status_code == 403
