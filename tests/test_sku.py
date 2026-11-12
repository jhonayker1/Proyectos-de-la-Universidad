import pytest

from app.models import Categoria, Producto
from app.services.sku_service import asignar_prefijos_faltantes, prefijo_desde_nombre
from tests.conftest import add_admin, auth_header


def crear(client, headers, id_categoria=1, **extra):
    r = client.post("/productos/", headers=headers, json={
        "nombre": "Producto", "id_categoria": id_categoria, "precio_usd": "10.00", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def nuevo_producto(db_session, sku, id_categoria=1, estado="Disponible"):
    db_session.add(Producto(sku=sku, nombre=sku, id_categoria=id_categoria, precio_usd=1,
                            precio_distribuidor=1, stock_actual=1, stock_minimo=0, estado=estado))
    db_session.commit()


def test_new_category_starts_at_0001_and_increments(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    db_session.get(Categoria, 1).prefijo_sku = "CR"
    db_session.commit()

    assert crear(client, admin)["sku"] == "CR-0001"
    assert crear(client, admin)["sku"] == "CR-0002"
    assert client.get("/productos/siguiente-sku?id_categoria=1", headers=admin).json() == {
        "sku": "CR-0003", "prefijo": "CR"}


def test_continues_existing_numbering_and_width(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    db_session.get(Categoria, 1).prefijo_sku = "LUB"
    db_session.commit()
    for sku in ("LUB-01", "LUB-02", "LUB-27"):
        nuevo_producto(db_session, sku)

    assert crear(client, admin)["sku"] == "LUB-28"


def test_skips_codes_used_by_other_categories_and_deleted_products(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    db_session.add(Categoria(id_categoria=2, nombre="Baterías", estado=1, prefijo_sku="BAT"))
    db_session.get(Categoria, 1).prefijo_sku = "CR"
    db_session.commit()
    nuevo_producto(db_session, "CR-0062", id_categoria=2)  # mismo código en otra categoría
    nuevo_producto(db_session, "CR-0070~9", estado="Inactivo")  # eliminado con historial

    assert crear(client, admin)["sku"] == "CR-0071"
    assert crear(client, admin, id_categoria=2)["sku"] == "BAT-0001"


def test_category_without_code_gets_one_from_its_name(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")  # conftest crea "Cauchos" sin código

    assert crear(client, admin)["sku"] == "CAU-0001"
    db_session.expire_all()
    assert db_session.get(Categoria, 1).prefijo_sku == "CAU"


def test_explicit_sku_is_still_accepted(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")
    assert crear(client, admin, sku="manual-1")["sku"] == "MANUAL-1"


def test_category_code_create_validation_and_uniqueness(client, db_session):
    add_admin(db_session)
    admin = auth_header(client, "admin@test.com")

    auto = client.post("/categorias/", headers=admin, json={"nombre": "Baterías"})
    assert auto.status_code == 201 and auto.json()["prefijo_sku"] == "BAT"
    manual = client.post("/categorias/", headers=admin, json={"nombre": "Aceites", "prefijo_sku": "lub"})
    assert manual.json()["prefijo_sku"] == "LUB"
    repetido = client.post("/categorias/", headers=admin, json={"nombre": "Lubricantes", "prefijo_sku": "LUB"})
    assert repetido.status_code == 409
    assert "ya lo usa la categoría Aceites" in repetido.json()["detail"]
    for invalido in ("L", "LUB1", "LUBRIC", "ÑAÑ"):
        assert client.post("/categorias/", headers=admin, json={"nombre": f"X{invalido}", "prefijo_sku": invalido}).status_code == 422

    id_aceites = manual.json()["id_categoria"]
    assert client.put(f"/categorias/{id_aceites}", headers=admin, json={"prefijo_sku": "BAT"}).status_code == 409
    assert client.put(f"/categorias/{id_aceites}", headers=admin, json={"prefijo_sku": None}).status_code == 422
    assert client.put(f"/categorias/{id_aceites}", headers=admin, json={"prefijo_sku": "ace"}).json()["prefijo_sku"] == "ACE"


def test_backfill_uses_existing_codes_and_resolves_conflicts(db_session):
    """Reproduce la situación real: CR compartido por Cauchos (3) y Baterías (1)."""
    db_session.get(Categoria, 1).nombre = "Lubricantes y Aceites"
    db_session.add_all([
        Categoria(id_categoria=2, nombre="Cauchos", estado=1),
        Categoria(id_categoria=3, nombre="Baterías", estado=1),
    ])
    db_session.commit()
    for sku in ("LUB-01", "LUB-02", "CR-0062"):
        nuevo_producto(db_session, sku, id_categoria=1)
    for sku in ("CR-0012", "CR-0020", "CR-0025"):
        nuevo_producto(db_session, sku, id_categoria=2)
    nuevo_producto(db_session, "CR-0038", id_categoria=3)

    asignados = asignar_prefijos_faltantes(db_session)

    assert asignados == {"Cauchos": "CR", "Lubricantes y Aceites": "LUB", "Baterías": "BAT"}


@pytest.mark.parametrize("nombre, ocupados, esperado", [
    ("Baterías", set(), "BAT"),
    ("Refrigerantes y Líquidos", set(), "REF"),
    ("Refrigerantes y Líquidos", {"REF"}, "RYL"),
    ("Ñandú", set(), "NAN"),
])
def test_prefix_from_name(nombre, ocupados, esperado):
    assert prefijo_desde_nombre(nombre, ocupados) == esperado
