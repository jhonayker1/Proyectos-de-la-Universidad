from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.usuarios import Rol, Usuario, role_key
from app.schemas.usuarios import UsuarioCreate


def find_role(db: Session, key: str) -> Rol:
    """Busca en la tabla roles el registro que corresponde a 'admin' o 'cashier'."""
    for rol in db.query(Rol).filter(Rol.estado == 1).order_by(Rol.id_rol).all():
        if role_key(rol.nombre) == key:
            return rol
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"No existe un rol activo para '{key}' en la tabla roles.",
    )


def find_user_by_email(db: Session, correo: str) -> Usuario | None:
    return (
        db.query(Usuario)
        .filter(func.lower(Usuario.correo) == correo.strip().lower())
        .first()
    )


def register_user(db: Session, user_in: UsuarioCreate) -> Usuario:
    correo = str(user_in.correo).lower()
    if find_user_by_email(db, correo):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya existe.")

    user = Usuario(
        id_rol=find_role(db, user_in.rol).id_rol,
        nombre_completo=user_in.nombre_completo.strip(),
        correo=correo,
        password_hash=hash_password(user_in.password),
        telefono=user_in.telefono,
        permisos=user_in.permisos,
        estado=1,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="El correo ya existe.") from exc
    db.refresh(user)
    return user


def authenticate_user(db: Session, correo: str, password: str) -> Usuario | None:
    user = find_user_by_email(db, correo)
    if user is None or not verify_password(password, user.password_hash):
        return None
    if not user.is_active or user.rol is None:
        return None
    return user
