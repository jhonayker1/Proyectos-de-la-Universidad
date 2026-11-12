import csv
import io
import json
import logging
import re

import pytest
from openpyxl import Workbook, load_workbook

from app.core.config import settings
from app.models import Auditoria, Proveedor
from app.services import recuperacion_service
from tests.conftest import add_admin, add_cashier, add_product, auth_header, set_rate

URL = "/auditoria/"


@pytest.fixture()
def admin(client, db_session):
    add_admin(db_session)
    return auth_header(client, "admin@test.com")


def registros(db_session, **filtros) -> list[Auditoria]:
    db_session.expire_all()
    query = db_session.query(Auditoria).filter_by(**filtros)
    return query.order_by(Auditoria.id_auditoria).all()


def cambios(registro: Auditoria) -> dict[str, tuple]:
    return {c["campo"]: (c["antes"], c["despues"]) for c in json.loads(registro.cambios or "[]")}


def test_producto_crear_modificar_y_eliminar_quedan_registrados(client, db_session, admin):
    r = client.post("/productos/", headers=admin, json={
        "nombre": "Aceite 20W50", "id_categoria": 1, "precio_distribuidor": "10", "precio_usd": "25",
        "stock_actual": 4,
    })
    assert r.status_code == 201, r.text
    producto = r.json()
    client.put(f"/productos/{producto['id_producto']}", headers=admin, json={"precio_usd": "30", "ubicacion": "Estante B"})
    client.delete(f"/productos/{producto['id_producto']}", headers=admin)

    crear, modificar, eliminar = registros(db_session, modulo="inventario")
    assert (crear.accion, crear.nombre_usuario, crear.rol, crear.ruta) == ("crear", "admin", "Administrador", "POST /productos/")
    assert crear.descripcion == f"Producto {producto['sku']} · Aceite 20W50 creado."
    assert cambios(crear)["id_categoria"] == (None, "Cauchos")  # el nombre, no el ID
    assert modificar.accion == "modificar"
    assert modificar.descripcion == f"Producto {producto['sku']} · Aceite 20W50: precio venta USD 25.00 → 30.00; ubicación — → Estante B."
    assert cambios(modificar) == {"precio_usd": ("25.00", "30.00"), "ubicacion": (None, "Estante B")}
    assert eliminar.accion == "eliminar" and cambios(eliminar)["stock_actual"] == ("4", None)
    assert len({crear.id_operacion, modificar.id_operacion, eliminar.id_operacion}) == 3


def test_venta_es_un_registro_con_sus_movimientos_de_stock(client, db_session, admin):
    producto = add_product(db_session, "CR-0001", stock=5)
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")
    r = client.post("/ventas/", headers=cajero, json={
        "codigo_moneda_pago": "USD", "detalles": [{"id_producto": producto.id_producto, "cantidad": 2}]
    })
    assert r.status_code == 201, r.text

    (venta,) = registros(db_session, modulo="ventas")
    # Un solo registro "creada", sin el paso intermedio del número temporal de factura.
    assert venta.accion == "crear" and venta.rol == "Cajero"
    assert venta.descripcion == "Venta F-00000001 registrada por cajero: 50.00 USD, pagada en USD. 2× Producto CR-0001."
    (stock,) = registros(db_session, modulo="inventario", accion="stock")
    assert cambios(stock) == {"stock_actual": ("5", "3")}
    assert stock.origen == "Venta en punto de venta" and stock.id_operacion == venta.id_operacion

    client.post(f"/ventas/{r.json()['id_venta']}/anular", headers=admin)
    anulada = registros(db_session, modulo="ventas", accion="anular")[0]
    assert anulada.descripcion == "Venta F-00000001 anulada." and anulada.nombre_usuario == "admin"
    devuelto = registros(db_session, modulo="inventario", accion="stock")[-1]
    assert cambios(devuelto)["stock_actual"] == ("3", "5")
    assert devuelto.origen == "Anulación de la venta F-00000001"


def test_operacion_fallida_no_deja_registro(client, db_session, admin):
    producto = add_product(db_session, "CR-0002", stock=1)
    antes = len(registros(db_session))
    r = client.post("/ventas/", headers=admin, json={
        "codigo_moneda_pago": "USD", "detalles": [{"id_producto": producto.id_producto, "cantidad": 9}]
    })
    assert r.status_code == 409
    libro = Workbook()
    libro.active.append(["Nombre", "Categoría", "Precio"])
    libro.active.append(["Malo", "Cauchos", "N/A"])
    buffer = io.BytesIO()
    libro.save(buffer)
    for modo in ("validar", "estricto"):  # ninguno guarda cambios, así que no hay nada que auditar
        client.post("/productos/importar", headers=admin, files={"archivo": ("x.xlsx", buffer.getvalue())},
                    data={"modo": modo})
    assert len(registros(db_session)) == antes


def test_importacion_audita_cada_producto_y_un_resumen(client, db_session, admin, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)
    libro = Workbook()
    for fila in (["SKU", "Nombre", "Categoría", "Precio", "Stock"], ["CR-0003", None, None, None, 9],
                 [None, "Caucho nuevo", "Cauchos", 40, 2]):
        libro.active.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    add_product(db_session, "CR-0003", stock=1)
    r = client.post("/productos/importar", headers=admin, files={"archivo": ("julio.xlsx", buffer.getvalue())},
                    data={"modo": "estricto"})
    assert r.json()["estado"] == "importado", r.text

    (resumen,) = registros(db_session, modulo="importacion")
    assert resumen.accion == "importar" and resumen.referencia == "julio.xlsx"
    assert "1 producto(s) nuevo(s) y 1 actualizado(s)" in resumen.descripcion
    productos = registros(db_session, modulo="inventario", id_operacion=resumen.id_operacion)
    assert sorted(p.accion for p in productos) == ["crear", "stock"]
    assert all(p.origen == "Importación masiva: julio.xlsx (modo estricto)" for p in productos)


def test_contrasenas_nunca_se_guardan(client, db_session, admin, caplog):
    r = client.post("/usuarios/", headers=admin, json={
        "nombre_completo": "Caja Dos", "correo": "caja2@test.com", "password": "clave-segura-1", "rol": "cashier"
    })
    assert r.status_code == 201, r.text
    id_usuario = r.json()["id_usuario"]
    client.patch(f"/usuarios/{id_usuario}/password", headers=admin, json={"password": "otra-clave-22"})
    client.patch(f"/usuarios/{id_usuario}/estado", headers=admin, json={"activo": False})
    client.patch(f"/usuarios/{id_usuario}/estado", headers=admin, json={"activo": True})
    recuperacion_service.clear()
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        client.post("/auth/recuperar/solicitar", json={"correo": "caja2@test.com"})
    codigo = re.findall(r"Código:\s+(\d{6})", caplog.text)[-1]
    client.post("/auth/recuperar/confirmar", json={"correo": "caja2@test.com", "codigo": codigo, "password": "tercera-clave3"})

    crear, cambio, desactivar, reactivar, recuperar = registros(db_session, modulo="usuarios", id_registro=str(id_usuario))
    assert cambios(crear)["password_hash"] == (None, "(definida)")
    assert (cambio.accion, cambio.descripcion) == ("contrasena", "Usuario Caja Dos (caja2@test.com): contraseña cambiada.")
    assert cambios(cambio) == {"password_hash": ("(oculta)", "(cambiada)")}
    assert [desactivar.accion, reactivar.accion] == ["desactivar", "reactivar"]
    # La recuperación queda a nombre del propio usuario, que no tenía sesión.
    assert (recuperar.nombre_usuario, recuperar.origen) == ("Caja Dos", "Recuperación de contraseña con código del servidor")
    todo = " ".join(f"{a.descripcion} {a.cambios}" for a in registros(db_session))
    assert "$2b$" not in todo and "pbkdf2" not in todo and "clave" not in todo.lower().replace("contraseña", "")


def test_catalogos_tasas_y_compras(client, db_session, admin):
    client.put("/categorias/1", headers=admin, json={"estado": 0})
    set_rate(client, admin, "40")
    proveedor = Proveedor(nombre="Distribuidora Rey", rif="J-12345678-9", telefono="04141234567",
                          correo="v@rey.com", estado=1)
    db_session.add(proveedor)
    db_session.commit()
    client.put("/categorias/1", headers=admin, json={"estado": 1})
    producto = add_product(db_session, "CR-0009", stock=0)
    r = client.post("/compras/", headers=admin, json={
        "id_proveedor": proveedor.id_proveedor, "numero_factura": "A-77",
        "detalles": [{"id_producto": producto.id_producto, "cantidad": 6, "costo_unitario_usd": "10"}],
    })
    assert r.status_code == 201, r.text
    client.patch(f"/compras/{r.json()['id_compra']}/pagado", headers=admin, json={"pagado": True})

    assert [a.descripcion for a in registros(db_session, modulo="categorias", nombre_usuario="admin")] == [
        "Categoría Cauchos desactivada.", "Categoría Cauchos reactivada."
    ]
    (tasa,) = registros(db_session, modulo="tasas")
    assert tasa.descripcion == "Nueva tasa de cambio VES: 40.0000 por USD."
    compra, pago = registros(db_session, modulo="compras")
    assert compra.descripcion == f"Compra #{r.json()['id_compra']} a Distribuidora Rey registrada: 60.00 USD. 6× Producto CR-0009."
    assert pago.descripcion == f"Compra #{r.json()['id_compra']} · Distribuidora Rey · factura A-77 marcada como pagada."
    entrada = registros(db_session, modulo="inventario", id_operacion=compra.id_operacion)
    assert [(e.accion, e.origen) for e in entrada] == [("stock", "Compra a proveedor (entrada de stock)")]


def test_api_filtra_pagina_y_es_solo_lectura(client, db_session, admin):
    for i in range(3):
        client.post("/productos/", headers=admin, json={"nombre": f"Filtro {i}", "id_categoria": 1, "precio_usd": "5"})
    client.put("/categorias/1", headers=admin, json={"margen_ganancia": "20"})

    pagina = client.get(URL, headers=admin, params={"modulo": "inventario", "por_pagina": 2}).json()
    assert pagina["total"] == 3 + 3  # 3 creados + 3 recalculados por el margen de la categoría
    assert len(pagina["items"]) == 2 and pagina["items"][0]["modulo_etiqueta"] == "Inventario"
    busqueda = client.get(URL, headers=admin, params={"buscar": "filtro 1", "accion": "crear"}).json()
    assert [i["referencia"] for i in busqueda["items"]] == ["CAU-0002 · Filtro 1"]
    margen = client.get(URL, headers=admin, params={"modulo": "categorias"}).json()["items"][0]
    misma = client.get(URL, headers=admin, params={"id_operacion": margen["id_operacion"]}).json()
    assert misma["total"] == 4  # la categoría y los 3 productos que recalculó

    filtros = client.get(f"{URL}filtros", headers=admin).json()
    assert {"clave": "stock", "etiqueta": "Movimiento de stock"} in filtros["acciones"]
    assert {"id_usuario": None, "nombre": "Sistema"} in filtros["usuarios"]
    sistema = client.get(URL, headers=admin, params={"id_usuario": 0}).json()
    assert sistema["total"] >= 1 and all(i["nombre_usuario"] == "Sistema" for i in sistema["items"])

    id_registro = pagina["items"][0]["id_auditoria"]
    assert client.put(f"{URL}{id_registro}", headers=admin, json={}).status_code in (404, 405)
    assert client.delete(f"{URL}{id_registro}", headers=admin).status_code in (404, 405)
    assert client.get(URL, headers=admin, params={"desde": "2026-02-01", "hasta": "2026-01-01"}).status_code == 422


def test_exportar_excel_y_csv_queda_registrado(client, db_session, admin):
    client.post("/productos/", headers=admin, json={"nombre": "=HYPERLINK(\"x\")", "id_categoria": 1, "precio_usd": "5"})
    r = client.get(f"{URL}exportar", headers=admin, params={"formato": "xlsx", "modulo": "inventario"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("application/vnd.openxml")
    hoja = load_workbook(io.BytesIO(r.content))["Auditoría"]
    filas = list(hoja.iter_rows(values_only=True))
    assert filas[0][:5] == ("Fecha", "Usuario", "Rol", "Módulo", "Acción")
    assert filas[1][3:5] == ("Inventario", "Crear") and "Nombre: — → =HYPERLINK" in filas[1][9]
    assert hoja["H2"].data_type == "s"  # la referencia empieza con el SKU, pero ningún texto es fórmula

    r = client.get(f"{URL}exportar", headers=admin, params={"formato": "csv", "modulo": "inventario"})
    texto = r.content.decode("utf-8")
    assert texto.startswith("﻿")
    filas = list(csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";"))
    assert filas[0][0] == "Fecha" and len(filas) == 2
    exportes = registros(db_session, modulo="auditoria", accion="exportar")
    assert [e.referencia.rsplit(".", 1)[1] for e in exportes] == ["xlsx", "csv"]
    assert "1 registro(s) (modulo=inventario)" in exportes[0].descripcion


def test_solo_el_administrador_ve_la_auditoria(client, db_session):
    add_cashier(db_session)
    cajero = auth_header(client, "cajero@test.com")
    assert client.get(URL, headers=cajero).status_code == 403
    assert client.get(f"{URL}exportar", headers=cajero).status_code == 403
