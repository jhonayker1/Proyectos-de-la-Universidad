from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import ExpiredSignatureError, InvalidTokenError
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database.session import get_db
from app.models.usuarios import Usuario

bearer_scheme = HTTPBearer(auto_error=False)


def unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    if credentials is None:
        raise unauthorized("No autenticado.")

    try:
        payload = decode_access_token(credentials.credentials)
    except ExpiredSignatureError as exc:
        raise unauthorized("Token expirado.") from exc
    except InvalidTokenError as exc:
        raise unauthorized("Token inválido.") from exc

    subject = payload.get("sub")
    if subject is None or not str(subject).isdigit():
        raise unauthorized("Token inválido.")

    user = db.query(Usuario).filter(Usuario.id_usuario == int(subject)).first()
    if user is None:
        raise unauthorized("Usuario no encontrado.")
    if not user.is_active:
        raise unauthorized("Usuario inactivo.")
    return user


def require_roles(allowed_roles: list[str]):
    """allowed_roles usa las claves internas 'admin' y 'cashier' (ver models.usuarios)."""

    def role_checker(current_user: Usuario = Depends(get_current_user)) -> Usuario:
        if current_user.rol not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permisos para realizar esta acción.",
            )
        return current_user

    return role_checker
