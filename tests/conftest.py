import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  registra las tablas
from app.core.security import hash_password
from app.database.session import Base, get_db
from app.main import app
from app.models import Categoria, Moneda, Producto, Rol, Usuario

PASSWORD = "secure-pass-123"


@pytest.fixture()
def db_session():
    # Base SQLite en memoria nueva por test, con los catálogos mínimos de cauchos_rey_def.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(autocommit=False, autoflush=False, bind=engine)()
    db.add_all(
        [
            Rol(id_rol=1, nombre="Administrador", estado=1),
            Rol(id_rol=2, nombre="Cajero", estado=1),
            Moneda(id_moneda=1, codigo="USD", nombre="Dólar", simbolo="$", es_base=1, estado=1),
            Moneda(id_moneda=2, codigo="VES", nombre="Bolívar", simbolo="Bs", es_base=0, estado=1),
            Categoria(id_categoria=1, nombre="Cauchos", estado=1),
        ]
    )
    db.commit()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.initialize_database = False
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    app.state.initialize_database = True


def add_user(db_session, correo: str, id_rol: int, estado: int = 1) -> Usuario:
    user = Usuario(
        id_rol=id_rol,
        nombre_completo=correo.split("@")[0],
        correo=correo,
        password_hash=hash_password(PASSWORD),
        estado=estado,
    )
    db_session.add(user)
    db_session.commit()
    return user


def add_admin(db_session, correo: str = "admin@test.com") -> Usuario:
    return add_user(db_session, correo, id_rol=1)


def add_cashier(db_session, correo: str = "cajero@test.com") -> Usuario:
    return add_user(db_session, correo, id_rol=2)


def auth_header(client, correo: str) -> dict[str, str]:
    response = client.post("/auth/login", json={"correo": correo, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def add_product(db_session, sku: str, stock: int, precio_usd: str = "25.00") -> Producto:
    producto = Producto(
        sku=sku,
        nombre=f"Producto {sku}",
        id_categoria=1,
        precio_distribuidor=10,
        precio_usd=precio_usd,
        stock_actual=stock,
        stock_minimo=0,
        estado="Disponible",
    )
    db_session.add(producto)
    db_session.commit()
    return producto


def set_rate(client, headers, tasa: str, codigo: str = "VES") -> None:
    response = client.post(
        "/tasas/", headers=headers, json={"codigo_moneda": codigo, "tasa_venta": tasa}
    )
    assert response.status_code == 201, response.text
