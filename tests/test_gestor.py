"""Rol Gestor (asistente administrativo): permisos y módulos operativos."""

import json
import pytest

from app.core.security import create_access_token
from app.models import Auditoria, Marca, Producto, Proveedor
from tests.conftest import add_admin, add_cashier, add_gestor, add_product

ROLES = ("admin", "gestor", "cashier")


@pytest.fixture()
def h(client, db_session):
    """Encabezados por rol y datos base: producto 1 (stock 10, $25), marca 1, proveedor 1,
    compra 1 (sin pagar) y venta 1."""
    usuarios = {"admin": add_admin(db_session), "gestor": add_gestor(db_session), "cashier": add_cashier(db_session)}
    db_session.add_all([
        Marca(id_marca=1, nombre="Michelin", estado=1),
        Proveedor(id_proveedor=1, nombre="Distribuidora Rey", rif="J-12345678-9", telefono="04141234567",
                  correo="v@rey.com", estado=1),
    ])
    db_session.commit()
    add_product(db_session, "CR-0001", stock=10)
    # Token directo (sin bcrypt en cada caso de la matriz); el login real lo prueba test_sesion_del_gestor.
    headers = {
        rol: {"Authorization": f"Bearer {create_access_token({'sub': str(u.id_usuario), 'rol': rol})}"}
        for rol, u in usuarios.items()
    }
    r = client.post("/compras/", headers=headers["admin"], json={
        "id_proveedor": 1, "numero_factura": "A-1",
        "detalles": [{"id_producto": 1, "cantidad": 5, "costo_unitario_usd": "10"}],
    })
    assert r.status_code == 201, r.text
    r = client.post("/ventas/", headers=headers["cashier"], json={
        "codigo_moneda_pago": "USD", "detalles": [{"id_producto": 1, "cantidad": 1}]})
    assert r.status_code == 201, r.text
    return headers


# ------------------------------------------------------------------ matriz de permisos

PERMISOS = [
    # (método, ruta, cuerpo, roles con acceso)
    ("GET", "/productos/", None, ROLES),
    ("GET", "/productos/admin", None, ("admin", "gestor")),
    ("POST", "/productos/", {"nombre": "Nuevo", "id_categoria": 1, "precio_usd": "5"}, ("admin", "gestor")),
    ("PUT", "/productos/1", {"precio_usd": "26"}, ("admin", "gestor")),
    ("PUT", "/productos/1", {"estado": "Inactivo"}, ("admin",)),
    ("DELETE", "/productos/1", None, ("admin",)),
    ("POST", "/productos/1/ajustes", {"tipo": "sumar", "cantidad": 1, "motivo": "otro", "observacion": "prueba"},
     ("admin", "gestor")),
    ("GET", "/productos/ajustes", None, ("admin", "gestor")),
    ("GET", "/productos/importar/plantilla", None, ("admin", "gestor")),
    ("GET", "/categorias/", None, ROLES),
    ("POST", "/categorias/", {"nombre": "Frenos"}, ("admin",)),
    ("PUT", "/categorias/1", {"margen_ganancia": "30"}, ("admin",)),
    ("POST", "/marcas/", {"nombre": "Bosch"}, ("admin", "gestor")),
    ("PUT", "/marcas/1", {"pais_origen": "Francia"}, ("admin", "gestor")),
    ("DELETE", "/marcas/1", None, ("admin",)),
    ("POST", "/proveedores/", {"nombre": "Otro", "rif": "J-87654321-0", "telefono": "02121234567",
                               "correo": "o@o.com"}, ("admin", "gestor")),
    ("PUT", "/proveedores/1", {"direccion": "Av. Bolívar"}, ("admin", "gestor")),
    ("PUT", "/proveedores/1", {"estado": 0}, ("admin",)),
    ("DELETE", "/proveedores/1", None, ("admin",)),
    ("GET", "/compras/", None, ("admin", "gestor")),
    ("POST", "/compras/", {"id_proveedor": 1, "detalles": [{"id_producto": 1, "cantidad": 1, "costo_unitario_usd": "9"}]},
     ("admin", "gestor")),
    ("PATCH", "/compras/1/pagado", {"pagado": True}, ("admin",)),
    ("DELETE", "/facturas/1", None, ("admin",)),
    ("GET", "/facturas/", None, ("admin", "gestor")),
    ("GET", "/tasas/vigente?codigo_moneda=VES", None, ROLES),
    ("POST", "/tasas/", {"codigo_moneda": "VES", "tasa_venta": "40"}, ("admin",)),
    ("GET", "/ventas/", None, ROLES),
    ("POST", "/ventas/", {"codigo_moneda_pago": "USD", "detalles": [{"id_producto": 1, "cantidad": 1}]},
     ("admin", "cashier")),
    ("POST", "/ventas/1/anular", None, ("admin",)),
    ("GET", "/reportes/dashboard", None, ("admin",)),
    ("GET", "/reportes/ventas", None, ("admin", "gestor")),
    ("GET", "/reportes/gestor/resumen", None, ("admin", "gestor")),
    ("GET", "/reportes/movimientos", None, ("admin", "gestor")),
    ("GET", "/reportes/cuentas-por-pagar", None, ("admin", "gestor")),
    ("GET", "/usuarios/", None, ("admin",)),
    ("POST", "/usuarios/", {"nombre_completo": "Otro Cajero", "correo": "c2@test.com", "password": "clave-segura-1"},
     ("admin",)),
    ("GET", "/auditoria/", None, ("admin", "gestor")),
    ("GET", "/auditoria/?modulo=usuarios", None, ("admin",)),
    ("GET", "/auditoria/?modulo=tasas", None, ("admin",)),
]


@pytest.mark.parametrize("rol", ROLES)
@pytest.mark.parametrize(("metodo", "ruta", "cuerpo", "permitidos"), PERMISOS,
                         ids=[f"{m} {r} {json.dumps(c)[:30] if c else ''}" for m, r, c, _ in PERMISOS])
def test_matriz_de_permisos(client, h, rol, metodo, ruta, cuerpo, permitidos):
    r = client.request(metodo, ruta, headers=h[rol], json=cuerpo)
    if rol in permitidos:
        assert r.status_code not in (401, 403), f"{rol} debería poder: {r.status_code} {r.text}"
        assert r.status_code < 500
    else:
        assert r.status_code == 403, f"{rol} no debería poder: {r.status_code} {r.text}"


def test_sesion_del_gestor(client, h):
    me = client.get("/auth/me", headers=h["gestor"]).json()
    assert me["rol"] == "gestor"
    login = client.post("/auth/login", json={"correo": "gestor@test.com", "password": "secure-pass-123"}).json()
    assert login["rol"] == "gestor"


def test_admin_crea_gestores(client, h):
    r = client.post("/usuarios/", headers=h["admin"], json={
        "nombre_completo": "Ana Gestora", "correo": "ana@test.com", "password": "clave-segura-1", "rol": "gestor"})
    assert r.status_code == 201 and r.json()["rol"] == "gestor"


# ------------------------------------------------------------------ ajustes y reportes


def test_ajustes_de_stock_justificados(client, db_session, h):
    # Stock: 10 + 5 (compra) - 1 (venta) = 14
    r = client.post("/productos/1/ajustes", headers=h["gestor"], json={
        "tipo": "restar", "cantidad": 99, "motivo": "merma", "observacion": "cauchos dañados"})
    assert r.status_code == 409 and "tiene 14 en stock" in r.json()["detail"]
    r = client.post("/productos/1/ajustes", headers=h["gestor"], json={
        "tipo": "restar", "cantidad": 2, "motivo": "merma", "observacion": "  "})
    assert r.status_code == 422
    r = client.post("/productos/1/ajustes", headers=h["gestor"], json={
        "tipo": "restar", "cantidad": 2, "motivo": "merma", "observacion": "Dos cauchos con defecto de fábrica"})
    assert r.status_code == 201, r.text
    assert (r.json()["stock_anterior"], r.json()["stock_nuevo"], r.json()["cantidad"]) == (14, 12, -2)
    r = client.post("/productos/1/ajustes", headers=h["gestor"], json={
        "tipo": "conteo", "cantidad": 0, "motivo": "conteo", "observacion": "Inventario físico"})
    assert r.json()["stock_nuevo"] == 0
    db_session.expire_all()
    assert db_session.get(Producto, 1).estado == "Agotado"

    historial = client.get("/productos/ajustes", headers=h["gestor"]).json()
    assert [a["motivo_etiqueta"] for a in historial] == ["Conteo físico", "Daño o merma"]
    ajuste = db_session.query(Auditoria).filter_by(accion="ajuste").order_by(Auditoria.id_auditoria).first()
    assert ajuste.rol == "Gestor"
    assert ajuste.descripcion == "Ajuste de stock de Producto CR-0001: 14 → 12 (Daño o merma). Dos cauchos con defecto de fábrica"
    stock = db_session.query(Auditoria).filter_by(accion="stock", id_operacion=ajuste.id_operacion).one()
    assert stock.origen == "Ajuste de stock: Daño o merma — Dos cauchos con defecto de fábrica"


def test_resumen_del_gestor_sin_informacion_financiera(client, h):
    resumen = client.get("/reportes/gestor/resumen", headers=h["gestor"]).json()
    claves = " ".join(resumen).lower()
    assert not any(palabra in claves for palabra in ("utilidad", "ganancia", "margen", "mes", "valor_inventario"))
    assert (resumen["ventas_hoy"], resumen["compras_hoy"], resumen["unidades_entrada_hoy"]) == (1, 1, 5)
    assert (resumen["productos_agotados"], resumen["productos_bajo_stock"]) == (0, 0)
    assert not any("presupuesto" in clave for clave in resumen)
    assert (resumen["cuentas_por_pagar_cantidad"], resumen["cuentas_por_pagar_usd"]) == (1, "50.00")


def test_kardex_y_cuentas_por_pagar(client, h):
    client.post("/productos/1/ajustes", headers=h["gestor"], json={
        "tipo": "sumar", "cantidad": 3, "motivo": "devolucion", "observacion": "Cliente devolvió sin uso"})
    client.post("/ventas/1/anular", headers=h["admin"])
    kardex = client.get("/reportes/movimientos", headers=h["gestor"]).json()
    tipos = sorted((m["tipo"], m["cantidad"]) for m in kardex["movimientos"])
    assert tipos == [("ajuste", 3), ("devolucion", 1), ("entrada", 5), ("salida", -1)]
    assert (kardex["entradas"], kardex["salidas"], kardex["devoluciones"], kardex["ajustes"]) == (5, 1, 1, 3)
    devolucion = next(m for m in kardex["movimientos"] if m["tipo"] == "devolucion")
    assert devolucion["referencia"] == "Anulación de F-00000001" and devolucion["usuario"] == "admin"

    cuentas = client.get("/reportes/cuentas-por-pagar", headers=h["gestor"]).json()
    assert cuentas["total_usd"] == "50.00" and cuentas["proveedores"][0]["proveedor"] == "Distribuidora Rey"


def test_auditoria_del_gestor_solo_modulos_operativos(client, h):
    client.post("/tasas/", headers=h["admin"], json={"codigo_moneda": "VES", "tasa_venta": "40"})
    items = client.get("/auditoria/", headers=h["gestor"], params={"por_pagina": 200}).json()["items"]
    modulos = {i["modulo"] for i in items}
    assert {"compras", "ventas", "inventario"} <= modulos
    assert not modulos & {"usuarios", "tasas", "categorias", "auditoria"}
    filtros = client.get("/auditoria/filtros", headers=h["gestor"]).json()
    assert "usuarios" not in {m["clave"] for m in filtros["modulos"]}
    todos = {i["modulo"] for i in client.get("/auditoria/", headers=h["admin"], params={"por_pagina": 200}).json()["items"]}
    assert {"usuarios", "tasas"} <= todos
    export = client.get("/auditoria/exportar", headers=h["gestor"])
    assert export.status_code == 200
    assert not {r["modulo"] for r in export.json()["registros"]} & {"usuarios", "tasas", "categorias", "auditoria"}


@pytest.mark.parametrize("ruta", ["/clientes/", "/presupuestos/", "/presupuestos/numero/1"])
def test_modulos_clientes_y_presupuestos_retirados(client, h, ruta):
    for rol in ROLES:
        assert client.get(ruta, headers=h[rol]).status_code == 404
    auditoria = client.get("/auditoria/filtros", headers=h["admin"]).json()
    assert not {"clientes", "presupuestos"} & {m["clave"] for m in auditoria["modulos"]}
