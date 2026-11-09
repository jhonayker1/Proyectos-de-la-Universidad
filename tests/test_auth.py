from passlib.context import CryptContext

from app.models import Usuario
from tests.conftest import PASSWORD, add_admin, add_cashier, add_user, auth_header


def test_login_by_email_returns_role(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)

    admin = client.post("/auth/login", json={"correo": "ADMIN@test.com", "password": PASSWORD})
    cashier = client.post("/auth/login", json={"correo": "cajero@test.com", "password": PASSWORD})

    assert admin.status_code == 200
    assert admin.json()["rol"] == "admin"
    assert cashier.json()["rol"] == "cashier"
    me = client.get("/auth/me", headers=auth_header(client, "cajero@test.com")).json()
    assert me["correo"] == "cajero@test.com"
    assert "password_hash" not in me


def test_admin_creates_cashier_and_cashier_cannot(client, db_session):
    add_admin(db_session)
    add_cashier(db_session)
    payload = {
        "nombre_completo": "Nuevo Cajero",
        "correo": "nuevo@test.com",
        "password": "secure-pass-456",
    }

    denied = client.post("/usuarios/", headers=auth_header(client, "cajero@test.com"), json=payload)
    created = client.post("/usuarios/", headers=auth_header(client, "admin@test.com"), json=payload)

    assert denied.status_code == 403
    assert created.status_code == 201, created.text
    assert created.json()["rol"] == "cashier"
    assert created.json()["id_rol"] == 2
    stored = db_session.query(Usuario).filter(Usuario.correo == "nuevo@test.com").one()
    assert stored.password_hash.startswith("$2b$")


def test_inactive_wrong_password_and_missing_token_are_rejected(client, db_session):
    add_user(db_session, "inactivo@test.com", id_rol=2, estado=0)
    add_cashier(db_session)

    assert client.post(
        "/auth/login", json={"correo": "inactivo@test.com", "password": PASSWORD}
    ).status_code == 401
    assert client.post(
        "/auth/login", json={"correo": "cajero@test.com", "password": "otra-clave"}
    ).status_code == 401
    assert client.get("/productos/").status_code == 401


def test_legacy_pbkdf2_hash_still_logs_in(client, db_session):
    legacy_hash = CryptContext(schemes=["pbkdf2_sha256"]).hash(PASSWORD)
    db_session.add(
        Usuario(id_rol=2, nombre_completo="Viejo", correo="viejo@test.com",
                password_hash=legacy_hash, estado=1)
    )
    db_session.commit()

    response = client.post("/auth/login", json={"correo": "viejo@test.com", "password": PASSWORD})

    assert response.status_code == 200


def test_admin_cannot_deactivate_last_admin(client, db_session):
    admin = add_admin(db_session)
    cashier = add_cashier(db_session)
    headers = auth_header(client, "admin@test.com")

    own = client.patch(f"/usuarios/{admin.id_usuario}/estado", headers=headers, json={"activo": False})
    other = client.patch(
        f"/usuarios/{cashier.id_usuario}/estado", headers=headers, json={"activo": False}
    )

    assert own.status_code == 400
    assert other.status_code == 200
    assert other.json()["estado"] == 0
