from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt
from passlib.context import CryptContext

from app.core.config import settings

# Contraseñas nuevas: bcrypt (formato $2b$, compatible con Node/PHP).
# También se aceptan hashes PBKDF2 creados por versiones anteriores del backend.
legacy_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password:
        return False
    if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        password = plain_password.encode("utf-8")
        if len(password) > 72:
            return False
        # $2y$ (PHP) es el mismo algoritmo que $2b$.
        stored = hashed_password.replace("$2y$", "$2b$", 1).encode("utf-8")
        try:
            return bcrypt.checkpw(password, stored)
        except ValueError:
            return False
    if legacy_context.identify(hashed_password):
        return legacy_context.verify(plain_password, hashed_password)
    return False


def create_access_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
