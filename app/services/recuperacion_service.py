"""Recuperación de contraseña con un código que solo se muestra en la consola del servidor.

Quien tiene acceso a la computadora donde corre el backend puede leer el código; así nadie
puede cambiar una contraseña solo con abrir la página de login. Los códigos viven en memoria
(un solo proceso): se pierden al reiniciar el servidor, lo cual es aceptable porque duran minutos.
"""

import hashlib
import hmac
import logging
import secrets
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger("recuperacion")

CODE_TTL_SECONDS = 10 * 60
MAX_ATTEMPTS = 5
RESEND_INTERVAL_SECONDS = 60


@dataclass
class _Pending:
    code_hash: bytes
    expires_at: float
    created_at: float
    attempts: int = 0


_pending: dict[str, _Pending] = {}
_lock = threading.Lock()


def _hash(code: str) -> bytes:
    return hashlib.sha256(code.encode("utf-8")).digest()


def _key(correo: str) -> str:
    return correo.strip().lower()


def issue_code(correo: str, nombre: str) -> None:
    """Genera un código y lo escribe en la consola. Si ya se pidió uno hace menos de un
    minuto, no genera otro (el anterior sigue valiendo)."""
    now = time.monotonic()
    key = _key(correo)
    with _lock:
        current = _pending.get(key)
        if current and now - current.created_at < RESEND_INTERVAL_SECONDS and now < current.expires_at:
            return
        code = f"{secrets.randbelow(1_000_000):06d}"
        _pending[key] = _Pending(_hash(code), now + CODE_TTL_SECONDS, now)
    logger.warning(
        "\n" + "=" * 60
        + f"\n  CÓDIGO DE RECUPERACIÓN DE CONTRASEÑA\n  Usuario: {nombre} <{key}>"
        + f"\n  Código:  {code}   (vence en {CODE_TTL_SECONDS // 60} minutos, un solo uso)\n"
        + "=" * 60
    )


def consume_code(correo: str, code: str) -> bool:
    """True si el código es correcto y vigente (y lo invalida). Cuenta los intentos fallidos."""
    key = _key(correo)
    with _lock:
        pending = _pending.get(key)
        if pending is None:
            return False
        if time.monotonic() >= pending.expires_at:
            del _pending[key]
            return False
        if hmac.compare_digest(pending.code_hash, _hash(code.strip())):
            del _pending[key]
            return True
        pending.attempts += 1
        if pending.attempts >= MAX_ATTEMPTS:
            del _pending[key]
        return False


def clear() -> None:
    """Solo para pruebas."""
    with _lock:
        _pending.clear()
