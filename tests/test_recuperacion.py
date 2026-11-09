import logging
import re

import pytest

from app.services import recuperacion_service
from tests.conftest import PASSWORD, add_admin, add_user

URL_SOLICITAR = "/auth/recuperar/solicitar"
URL_CONFIRMAR = "/auth/recuperar/confirmar"


@pytest.fixture(autouse=True)
def limpiar_codigos():
    recuperacion_service.clear()
    yield
    recuperacion_service.clear()


def codigo_en_consola(caplog) -> str:
    codigos = re.findall(r"Código:\s+(\d{6})", caplog.text)
    assert codigos, "no se escribió ningún código en la consola"
    return codigos[-1]


def login(client, password):
    return client.post("/auth/login", json={"correo": "admin@test.com", "password": password}).status_code


def test_recovery_flow_changes_password(client, db_session, caplog):
    add_admin(db_session)
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        r = client.post(URL_SOLICITAR, json={"correo": "ADMIN@test.com"})
    assert r.status_code == 202
    codigo = codigo_en_consola(caplog)

    ok = client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": codigo, "password": "nueva-clave-9"})

    assert ok.status_code == 204
    assert login(client, PASSWORD) == 401
    assert login(client, "nueva-clave-9") == 200
    # El código es de un solo uso.
    reuse = client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": codigo, "password": "otra-clave-99"})
    assert reuse.status_code == 400


def test_unknown_or_inactive_email_gives_same_answer_and_no_code(client, db_session, caplog):
    add_user(db_session, "inactivo@test.com", id_rol=1, estado=0)
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        a = client.post(URL_SOLICITAR, json={"correo": "nadie@test.com"})
        b = client.post(URL_SOLICITAR, json={"correo": "inactivo@test.com"})
    assert a.status_code == b.status_code == 202
    assert a.json() == b.json()
    assert "Código:" not in caplog.text


def test_wrong_code_is_rejected_and_blocks_after_max_attempts(client, db_session, caplog):
    add_admin(db_session)
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        client.post(URL_SOLICITAR, json={"correo": "admin@test.com"})
    codigo = codigo_en_consola(caplog)
    malo = "000000" if codigo != "000000" else "111111"
    for _ in range(recuperacion_service.MAX_ATTEMPTS):
        r = client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": malo, "password": "nueva-clave-9"})
        assert r.status_code == 400
    # Tras los intentos máximos, ni el código correcto sirve.
    r = client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": codigo, "password": "nueva-clave-9"})
    assert r.status_code == 400
    assert login(client, PASSWORD) == 200


def test_expired_code_is_rejected(client, db_session, caplog, monkeypatch):
    add_admin(db_session)
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        client.post(URL_SOLICITAR, json={"correo": "admin@test.com"})
    codigo = codigo_en_consola(caplog)
    reloj = recuperacion_service.time.monotonic() + recuperacion_service.CODE_TTL_SECONDS + 1
    monkeypatch.setattr(recuperacion_service.time, "monotonic", lambda: reloj)

    r = client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": codigo, "password": "nueva-clave-9"})

    assert r.status_code == 400


def test_repeated_request_within_a_minute_keeps_same_code(client, db_session, caplog):
    add_admin(db_session)
    with caplog.at_level(logging.WARNING, logger="recuperacion"):
        client.post(URL_SOLICITAR, json={"correo": "admin@test.com"})
        client.post(URL_SOLICITAR, json={"correo": "admin@test.com"})
    assert len(re.findall(r"Código:\s+\d{6}", caplog.text)) == 1


def test_short_password_and_bad_code_format_are_validated(client, db_session):
    add_admin(db_session)
    assert client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": "123456", "password": "corta"}).status_code == 422
    assert client.post(URL_CONFIRMAR, json={"correo": "admin@test.com", "codigo": "12ab", "password": "nueva-clave-9"}).status_code == 422
