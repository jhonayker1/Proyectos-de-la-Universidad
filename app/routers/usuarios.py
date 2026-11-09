from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.security import hash_password
from app.database.session import get_db
from app.models.compras import Compra, FacturaImagen
from app.models.usuarios import Usuario
from app.models.ventas import Venta
from app.schemas.usuarios import (
    PasswordReset,
    UsuarioCreate,
    UsuarioEstadoUpdate,
    UsuarioRead,
    UsuarioUpdate,
)
from app.services.auth_service import find_user_by_email, register_user

router = APIRouter(prefix="/usuarios", tags=["usuarios"])
admin_only = require_roles(["admin"])


def get_or_404(db: Session, id_usuario: int) -> Usuario:
    user = db.query(Usuario).filter(Usuario.id_usuario == id_usuario).first()
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")
    return user


def ensure_not_last_admin(db: Session, user: Usuario) -> None:
    if user.rol != "admin" or not user.is_active:
        return
    active_admins = [
        u for u in db.query(Usuario).filter(Usuario.estado == 1).all() if u.rol == "admin"
    ]
    if len(active_admins) <= 1:
        raise HTTPException(
            status_code=409,
            detail="No se puede quitar el último administrador activo.",
        )


@router.post("/", response_model=UsuarioRead, status_code=status.HTTP_201_CREATED)
def create_user(
    user_in: UsuarioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(admin_only),
) -> Usuario:
    return register_user(db, user_in)


@router.get("/", response_model=list[UsuarioRead])
def list_users(db: Session = Depends(get_db), _: Usuario = Depends(admin_only)) -> list[Usuario]:
    return db.query(Usuario).order_by(Usuario.id_usuario).all()


@router.put("/{id_usuario}", response_model=UsuarioRead)
def update_user(
    id_usuario: int,
    update: UsuarioUpdate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(admin_only),
) -> Usuario:
    user = get_or_404(db, id_usuario)
    values = update.model_dump(exclude_unset=True)
    for field in ("nombre_completo", "correo"):
        if field in values and values[field] is None:
            raise HTTPException(status_code=422, detail=f"{field} no puede ser null.")
    if "correo" in values:
        values["correo"] = str(values["correo"]).lower()
        other = find_user_by_email(db, values["correo"])
        if other is not None and other.id_usuario != user.id_usuario:
            raise HTTPException(status_code=409, detail="El correo ya existe.")
    if "nombre_completo" in values:
        values["nombre_completo"] = values["nombre_completo"].strip()
    for field, value in values.items():
        setattr(user, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="El correo ya existe.") from exc
    db.refresh(user)
    return user


@router.patch("/{id_usuario}/password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(
    id_usuario: int,
    reset: PasswordReset,
    db: Session = Depends(get_db),
    _: Usuario = Depends(admin_only),
) -> None:
    get_or_404(db, id_usuario).password_hash = hash_password(reset.password)
    db.commit()


@router.patch("/{id_usuario}/estado", response_model=UsuarioRead)
def set_user_status(
    id_usuario: int,
    update: UsuarioEstadoUpdate,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(admin_only),
) -> Usuario:
    user = get_or_404(db, id_usuario)
    if user.id_usuario == current_user.id_usuario and not update.activo:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")
    if not update.activo:
        ensure_not_last_admin(db, user)

    user.estado = 1 if update.activo else 0
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{id_usuario}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    id_usuario: int,
    db: Session = Depends(get_db),
    current_user: Usuario = Depends(admin_only),
) -> None:
    """Solo borra usuarios sin historial; los demás deben desactivarse."""
    user = get_or_404(db, id_usuario)
    if user.id_usuario == current_user.id_usuario:
        raise HTTPException(status_code=400, detail="No puedes eliminar tu propia cuenta.")
    ensure_not_last_admin(db, user)
    has_history = any(
        db.query(model).filter(model.id_usuario == user.id_usuario).first() is not None
        for model in (Venta, Compra, FacturaImagen)
    )
    if has_history:
        raise HTTPException(
            status_code=409,
            detail="El usuario tiene ventas o compras registradas; desactívelo en su lugar.",
        )
    db.delete(user)
    db.commit()
