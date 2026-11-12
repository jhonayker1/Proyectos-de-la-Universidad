import io
import json
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from app.core.config import settings
from app.models import Categoria, Marca, Producto, Proveedor
from app.services.importacion.conversores import a_booleano, a_decimal, a_entero
from app.services.importacion.errores import ValorInvalido
from app.services.importacion.esquema import por_clave
from app.services.importacion.mapeo import mapear
from tests.conftest import add_admin, add_cashier, auth_header

URL = "/productos/importar"
ENCABEZADOS = ["Código", "Descripción", "Rubro", "Marca", "Costo ($)", "P. Venta", "Existencia"]


def xlsx(filas: list[list], titulo: str | None = None) -> bytes:
    libro = Workbook()
    hoja = libro.active
    if titulo:  # un título y una fila vacía encima de la tabla, como en muchos inventarios
        hoja.append([titulo])
        hoja.append([])
    for fila in filas:
        hoja.append(fila)
    for celdas in hoja.iter_rows():
        for celda in celdas:
            if isinstance(celda.value, str) and celda.value.startswith("="):
                celda.data_type = "s"  # texto literal, no una fórmula
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def subir(client, headers, contenido: bytes, nombre: str = "inventario.xlsx", **form):
    datos = {k: (json.dumps(v) if isinstance(v, dict) else str(v).lower() if isinstance(v, bool) else str(v))
             for k, v in form.items()}
    return client.post(URL, headers=headers, files={"archivo": (nombre, contenido)}, data=datos)


@pytest.fixture(autouse=True)
def carpeta_temporal(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", tmp_path)  # los reportes no van a uploads/


@pytest.fixture()
def admin(client, db_session):
    add_admin(db_session)
    db_session.add_all([
        Categoria(id_categoria=2, nombre="Lubricantes", estado=1, prefijo_sku="LUB", margen_ganancia=30),
        Categoria(id_categoria=3, nombre="Herramientas", estado=0, prefijo_sku="HER"),
        Marca(id_marca=1, nombre="Michelin", estado=1),
        Proveedor(id_proveedor=1, nombre="Distribuidora Rey", rif="J-12345678-9", telefono="04141234567",
                  correo="ventas@rey.com", estado=1),
        Producto(sku="LUB-27", nombre="Aceite 20W50", id_categoria=2, precio_distribuidor=8,
                 precio_usd=12, stock_actual=10, stock_minimo=2, estado="Disponible"),
    ])
    db_session.commit()
    return auth_header(client, "admin@test.com")


def productos(db_session) -> dict[str, Producto]:
    db_session.expire_all()
    return {p.sku: p for p in db_session.query(Producto)}


# ---------------------------------------------------------------- capas


def test_mapeo_reconoce_alias_aproximados_e_ignoradas():
    m = mapear(["Código", "Descripción", "P. Venta", "Costo ($)", "Exsitencias", "Stock Mín.",
                "Rubro", "% Ganancia", "Código de barras", "Precio Bs", "Notas"])
    campos = {c.encabezado: c.campo for c in m.columnas}
    assert campos == {
        "Código": "sku", "Descripción": "nombre", "P. Venta": "precio_usd",
        "Costo ($)": "precio_distribuidor", "Exsitencias": "stock_actual",
        "Stock Mín.": "stock_minimo", "Rubro": "categoria", "% Ganancia": "margen_pct",
    }
    assert next(c for c in m.columnas if c.campo == "stock_actual").metodo == "aproximado"
    ignoradas = {c.encabezado: c.motivo for c in m.ignoradas}
    assert "código de barras" in ignoradas["Código de barras"]
    assert "USD" in ignoradas["Precio Bs"]
    assert ignoradas["Notas"] == "No corresponde a ningún campo del inventario."


def test_mapeo_no_asigna_dos_columnas_al_mismo_campo():
    m = mapear(["Nombre", "Descripción", "Precio", "Precio Venta"])
    assert [c.encabezado for c in m.columnas] == ["Nombre", "Precio"]
    motivos = {c.encabezado: c.motivo for c in m.ignoradas}
    assert "ya lo toma la columna A ('Nombre')" in motivos["Descripción"]
    assert "ya lo toma la columna C ('Precio')" in motivos["Precio Venta"]


def test_conversores():
    precio = por_clave()["precio_usd"]
    assert a_decimal("1.234,56", precio) == Decimal("1234.56")
    assert a_decimal("1,234.56", precio) == Decimal("1234.56")
    assert a_decimal("$ 12,5", precio) == Decimal("12.50")
    assert a_decimal(12.3456, precio) == Decimal("12.35")
    assert a_decimal("35%", por_clave()["margen_pct"]) == Decimal("35.00")
    for malo, motivo in (("N/A", "El valor 'N/A' no es un número válido."),
                         ("-3", "El valor no puede ser negativo."),
                         ("#N/A", "error de fórmula de Excel (#N/A)")):
        with pytest.raises(ValorInvalido, match=motivo.replace("(", r"\(").replace(")", r"\)")):
            a_decimal(malo, precio)
    with pytest.raises(ValorInvalido, match="supera el máximo"):
        a_decimal("1000", por_clave()["margen_pct"])
    stock = por_clave()["stock_actual"]
    assert a_entero(5.0, stock) == 5
    assert a_entero("12", stock) == 12
    with pytest.raises(ValorInvalido, match="debe ser un número entero"):
        a_entero("5,5", stock)
    assert a_booleano("Sí") is True and a_booleano("no") is False and a_booleano(1) is True
    with pytest.raises(ValorInvalido, match="use Sí o No"):
        a_booleano("tal vez")


# ---------------------------------------------------------------- endpoint


def test_validar_muestra_errores_con_fila_y_columna_y_no_guarda(client, db_session, admin):
    contenido = xlsx([
        ["SKU", "Producto", "Categoría", "Precio Venta", "Stock"],
        [None, "Aceite 15W40", "Lubricantes", 15, 6],
        [None, "Aceite 5W30", "Lubricantes", "N/A", 4],
        [None, "Refrigerante", "lubricante", "9,50", "tres"],
    ], titulo="Inventario Cauchos Rey")
    r = subir(client, admin, contenido)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["estado"] == "validado" and body["aplicado"] is False
    assert body["archivo"]["fila_encabezados"] == 3
    assert body["resumen"]["filas_leidas"] == 3
    assert body["resumen"]["filas_validas"] == 1
    mensajes = [e["mensaje"] for e in body["errores"]]
    assert mensajes == [
        "Fila 5, Columna 'Precio Venta': El valor 'N/A' no es un número válido.",
        "Fila 6, Columna 'Stock': El valor 'tres' no es un número válido.",
    ]
    assert body["errores"][0]["letra"] == "D" and body["errores"][0]["campo"] == "precio_usd"
    # Continúa la numeración de la categoría (LUB-27 -> LUB-28) con el mismo ancho.
    assert body["vista_previa"] == [{
        "fila": 4, "accion": "crear", "sku": "LUB-28", "sku_automatico": True,
        "nombre": "Aceite 15W40", "categoria": "Lubricantes",
    }]
    assert set(productos(db_session)) == {"LUB-27"}


def test_estricto_no_guarda_nada_si_una_fila_falla(client, db_session, admin):
    contenido = xlsx([
        ["Nombre", "Categoría", "Precio", "Stock"],
        ["Aceite 15W40", "Lubricantes", 15, 6],
        ["Aceite 5W30", "Lubricantes", -2, 4],
    ])
    r = subir(client, admin, contenido, modo="estricto")
    body = r.json()
    assert r.status_code == 200
    assert body["estado"] == "rechazado" and body["aplicado"] is False
    assert "modo estricto" in body["mensaje"]
    assert body["errores"][0]["mensaje"] == "Fila 3, Columna 'Precio': El valor no puede ser negativo."
    assert set(productos(db_session)) == {"LUB-27"}


def test_parcial_guarda_las_validas_y_el_sku_automatico_no_choca(client, db_session, admin):
    contenido = xlsx([
        ["SKU", "Nombre", "Categoría", "Costo", "Precio", "Stock", "Stock mínimo"],
        [None, "Aceite 15W40", "LUB", 10, None, 6, 2],  # código de la categoría
        ["lub-28", "Aceite 10W30", "Lubricantes", 9, 14, 1, 3],  # SKU escrito más abajo
        [None, "Aceite roto", "Lubricantes", "abc", 1, 1, 1],
    ])
    r = subir(client, admin, contenido, modo="parcial")
    body = r.json()
    assert r.status_code == 200, r.text
    assert body["estado"] == "importado_parcial" and body["aplicado"] is True
    assert body["resumen"]["creados"] == 2 and body["resumen"]["filas_con_error"] == 1
    actuales = productos(db_session)
    assert set(actuales) == {"LUB-27", "LUB-28", "LUB-29"}
    automatico = actuales["LUB-29"]  # LUB-28 lo pidió el archivo, así que salta al siguiente
    assert automatico.nombre == "Aceite 15W40"
    assert automatico.precio_usd == Decimal("13.00")  # costo 10 + margen 30 % de la categoría
    assert automatico.estado == "Disponible"
    assert actuales["LUB-28"].estado == "Bajo Stock"  # stock 1 < mínimo 3


def test_actualiza_por_sku_y_las_celdas_vacias_no_cambian(client, db_session, admin):
    contenido = xlsx([["SKU", "Nombre", "Precio", "Stock", "Ubicación"], ["LUB-27", None, None, 0, "Estante B"]])
    r = subir(client, admin, contenido, modo="estricto")
    assert r.json()["estado"] == "importado", r.text
    aceite = productos(db_session)["LUB-27"]
    assert (aceite.nombre, aceite.precio_usd, aceite.stock_actual, aceite.ubicacion, aceite.estado) == (
        "Aceite 20W50", Decimal("12.00"), 0, "Estante B", "Agotado"
    )


def test_politicas_para_sku_existente(client, db_session, admin):
    contenido = xlsx([["SKU", "Nombre", "Stock"], ["LUB-27", "Otro nombre", 99]])
    error = subir(client, admin, contenido, si_existe="error").json()
    assert error["errores"][0]["mensaje"] == (
        "Fila 2, Columna 'SKU': El SKU LUB-27 ya existe en el inventario (Aceite 20W50)."
    )
    omitir = subir(client, admin, contenido, si_existe="omitir", modo="estricto").json()
    assert omitir["estado"] == "sin_cambios" and omitir["resumen"]["a_omitir"] == 1
    assert productos(db_session)["LUB-27"].stock_actual == 10


def test_duplicados_en_el_archivo_y_contra_la_base(client, db_session, admin):
    contenido = xlsx([
        ["SKU", "Nombre", "Categoría", "Stock"],
        ["NUEVO-1", "Filtro A", "Lubricantes", 1],
        ["nuevo-1", "Filtro B", "Lubricantes", 1],
        [None, "Bujía", "Lubricantes", 1],
        [None, "bujia", "Lubricantes", 2],
        [None, "Aceite 20W50", "Lubricantes", 3],
    ])
    body = subir(client, admin, contenido).json()
    mensajes = [e["mensaje"] for e in body["errores"]]
    assert mensajes == [
        "Fila 3, Columna 'SKU': El SKU NUEVO-1 está repetido en el archivo (ya aparece en la fila 2).",
        "Fila 5, Columna 'Nombre': Producto repetido en el archivo: la fila 4 tiene el mismo nombre, categoría y marca.",
        "Fila 6, Columna 'Nombre': Ya existe 'Aceite 20W50' (SKU LUB-27) con el mismo nombre, categoría y "
        "marca. Escriba su SKU en la fila para actualizarlo, o cambie el nombre.",
    ]


def test_referencias_por_texto_codigo_rif_y_sugerencias(client, db_session, admin):
    contenido = xlsx([
        ["Nombre", "Categoría", "Marca", "Proveedor"],
        ["Caucho 205/55 R16", "CAUCHO", "michelin", "j123456789"],
        ["Caucho 185/65 R15", "Cauchos", "Michelinn", None],
        ["Llave 10 mm", "Herramientas", None, None],
        ["Pastillas", "Frenos", None, "Otro Proveedor"],
    ])
    body = subir(client, admin, contenido).json()
    mensajes = {e["fila"]: e["motivo"] for e in body["errores"]}
    assert mensajes[3] == "La marca 'Michelinn' no existe. ¿Quiso decir 'Michelin'? Créela en Catálogo o active la opción de crear categorías y marcas que falten."
    assert mensajes[4] == "La categoría 'Herramientas' está desactivada; reactívela en Catálogo antes de importar."
    assert body["resumen"]["filas_validas"] == 1
    errores_fila5 = [e["campo"] for e in body["errores"] if e["fila"] == 5]
    assert errores_fila5 == ["categoria", "proveedor"]


def test_crear_faltantes_crea_categoria_y_marca_con_su_codigo(client, db_session, admin):
    contenido = xlsx([
        ["Nombre", "Categoría", "Marca", "Precio", "Stock"],
        ["Pastillas delanteras", "Frenos", "Bosch", 30, 4],
        ["Pastillas traseras", "frenos", "BOSCH", 25, 4],
    ])
    body = subir(client, admin, contenido, modo="estricto", crear_faltantes=True).json()
    assert body["estado"] == "importado", body
    assert body["resumen"]["categorias_nuevas"] == [
        {"nombre": "Frenos", "prefijo_sku": "FRE", "filas": 2, "primera_fila": 2}
    ]
    assert [m["nombre"] for m in body["resumen"]["marcas_nuevas"]] == ["Bosch"]
    frenos = db_session.query(Categoria).filter_by(nombre="Frenos").one()
    assert frenos.prefijo_sku == "FRE"
    nuevos = {p.sku: p for p in db_session.query(Producto).filter_by(id_categoria=frenos.id_categoria)}
    assert set(nuevos) == {"FRE-0001", "FRE-0002"}
    assert all(p.marca.nombre == "Bosch" for p in nuevos.values())


def test_csv_de_excel_en_espanol(client, db_session, admin):
    texto = "Descripción;Categoría;Precio;Existencia;Activo\nAceite sintético;Lubricantes;12,50;3;No\n"
    r = subir(client, admin, texto.encode("cp1252"), nombre="inventario.csv", modo="estricto")
    body = r.json()
    assert body["estado"] == "importado", body
    assert body["archivo"]["codificacion"] == "cp1252" and body["archivo"]["separador"] == "punto y coma"
    nuevo = productos(db_session)["LUB-28"]
    assert (nuevo.nombre, nuevo.precio_usd, nuevo.estado) == ("Aceite sintético", Decimal("12.50"), "Inactivo")


def test_mapeo_manual_y_categoria_por_defecto(client, db_session, admin):
    contenido = xlsx([["Nombre", "Precio", "Cant. en tienda"], ["Aceite 0W20", 20, 7]])
    body = subir(client, admin, contenido, modo="estricto", id_categoria_defecto=2,
                 mapeo={"C": "stock_actual"}).json()
    assert body["estado"] == "importado", body
    assert {c["letra"]: (c["campo"], c["metodo"]) for c in body["mapeo"]}["C"] == ("stock_actual", "manual")
    assert productos(db_session)["LUB-28"].stock_actual == 7


def test_advertencias_no_bloquean(client, db_session, admin):
    contenido = xlsx([["Nombre", "Categoría", "Costo", "Precio", "Margen"], ["Aceite caro", "Lubricantes", 20, 15, 150]])
    body = subir(client, admin, contenido, modo="estricto").json()
    assert body["estado"] == "importado"
    motivos = [a["motivo"] for a in body["advertencias"]]
    assert "El precio de venta (15.00) es menor que el costo (20.00)." in motivos
    assert any("150.00 % representa una cantidad desproporcionada" in m for m in motivos)


def test_texto_mas_largo_que_la_columna(client, admin):
    contenido = xlsx([["Nombre", "Categoría"], ["x" * 151, "Lubricantes"]])
    body = subir(client, admin, contenido).json()
    assert body["errores"][0]["motivo"] == "El texto tiene 151 caracteres y el máximo permitido es 150."


def test_reporte_excel_con_filas_a_corregir_sin_formulas(client, admin):
    contenido = xlsx([["Nombre", "Categoría", "Precio"], ["=1+1", "Lubricantes", "N/A"], ["Bien", "Lubricantes", 3]])
    r = subir(client, admin, contenido, formato="xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    libro = load_workbook(io.BytesIO(r.content))
    assert libro.sheetnames == ["Resumen", "Errores", "Filas a corregir"]
    errores = list(libro["Errores"].iter_rows(values_only=True))
    assert errores[1][1:3] == (2, "C: Precio") and "no es un número válido" in errores[1][5]
    corregir = libro["Filas a corregir"]
    assert [c.value for c in corregir[1]] == ["Fila original", "Errores", "Nombre", "Categoría", "Precio"]
    celda = corregir["C2"]
    assert celda.value == "=1+1" and celda.data_type == "s"


def test_reporte_guardado_describe_la_importacion_hecha(client, db_session, admin):
    contenido = xlsx([["Nombre", "Categoría", "Precio"], ["Malo", "Lubricantes", "N/A"], ["Bueno", "Lubricantes", 3]])
    body = subir(client, admin, contenido, modo="parcial").json()
    assert body["estado"] == "importado_parcial"
    assert body["mensaje"] == "Se importó 1 producto (1 nuevo, 0 actualizados). Se omitió 1 fila con errores."
    r = client.get(f"{URL}/reportes/{body['reporte_id']}", headers=admin)
    assert r.status_code == 200
    resumen = dict(load_workbook(io.BytesIO(r.content))["Resumen"].iter_rows(min_row=2, max_row=13, values_only=True))
    # Lo que pasó en esta importación, no una nueva validación (donde "Bueno" ya sería un duplicado).
    assert resumen["Resultado"] == "Importado parcialmente"
    assert resumen["Productos nuevos"] == 1 and resumen["Filas con errores"] == 1

    sin_errores = subir(client, admin, xlsx([["Nombre", "Categoría", "Precio"], ["Otro", "Lubricantes", 4]])).json()
    assert sin_errores["reporte_id"] is None
    assert client.get(f"{URL}/reportes/{'0' * 32}", headers=admin).status_code == 404
    assert client.get(f"{URL}/reportes/..%2F..%2Fsecreto", headers=admin).status_code == 404
    otro = add_admin(db_session, "otro@test.com")
    assert otro.id_usuario
    ajeno = client.get(f"{URL}/reportes/{body['reporte_id']}", headers=auth_header(client, "otro@test.com"))
    assert ajeno.status_code == 404  # cada administrador ve solo sus reportes


def test_plantilla_descargada_se_puede_llenar_e_importar(client, db_session, admin):
    r = client.get(f"{URL}/plantilla", headers=admin)
    assert r.status_code == 200
    libro = load_workbook(io.BytesIO(r.content))
    assert {"Productos", "Instrucciones", "Categorías", "Marcas", "Proveedores"} <= set(libro.sheetnames)
    hoja = libro["Productos"]
    encabezados = [c.value for c in hoja[1]]
    assert hoja.max_row == 1  # sin filas de ejemplo que se importen por error
    fila = {"Nombre": "Caucho 175/70 R13", "Categoría": "Cauchos", "Marca": "Michelin",
            "Costo USD": 40, "Precio venta USD": 55, "Stock": 8}
    hoja.append([fila.get(e) for e in encabezados])
    salida = io.BytesIO()
    libro.save(salida)
    body = subir(client, admin, salida.getvalue(), modo="estricto").json()
    assert body["estado"] == "importado", body
    assert productos(db_session)["CAU-0001"].precio_usd == Decimal("55.00")

    campos = client.get(f"{URL}/campos", headers=admin).json()
    nombre = next(c for c in campos if c["clave"] == "nombre")
    assert nombre["max_length"] == 150 and nombre["obligatorio_al_crear"] is True


@pytest.mark.parametrize(
    ("contenido", "nombre", "status", "texto"),
    [
        (b"\xd0\xcf\x11\xe0" + b"0" * 100, "viejo.xls", 415, "Excel antiguo"),
        (b"%PDF-1.4", "factura.pdf", 415, "no se admite"),
        (b"", "vacio.csv", 422, "vacío"),
        (b"PK\x03\x04roto", "roto.xlsx", 415, "dañado"),
        ("hola;mundo\n1;2\n".encode(), "x.csv", 422, "No se encontró la fila de encabezados"),
        ("Precio;Stock\n1;2\n".encode(), "x.csv", 422, "Falta la columna del nombre"),
        ("Nombre;Precio\nA;2\n".encode(), "x.csv", 422, "Falta la columna Categoría"),
        ("Nombre;Categoría\n".encode(), "x.csv", 422, "no tiene filas de datos"),
    ],
)
def test_errores_de_archivo_responden_json_limpio(client, admin, contenido, nombre, status, texto):
    r = subir(client, admin, contenido, nombre=nombre)
    assert r.status_code == status, r.text
    assert texto in r.json()["detail"]


def test_solo_el_administrador_importa(client, db_session):
    add_cashier(db_session)
    headers = auth_header(client, "cajero@test.com")
    assert subir(client, headers, xlsx([["Nombre"]])).status_code == 403
    assert client.get(f"{URL}/plantilla", headers=headers).status_code == 403
