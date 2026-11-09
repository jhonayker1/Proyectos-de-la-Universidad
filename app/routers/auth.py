from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.security import create_access_token, hash_password
from app.database.session import get_db
from app.models.usuarios import Usuario
from app.schemas.usuarios import (
    LoginRequest,
    RecuperacionConfirmacion,
    RecuperacionSolicitud,
    Token,
    UsuarioRead,
)
from app.services import recuperacion_service
from app.services.auth_service import authenticate_user, find_user_by_email

router = APIRouter(prefix="/auth", tags=["auth"])

RESPUESTA_SOLICITUD = {
    "mensaje": "Si el correo pertenece a un usuario activo, se generó un código de "
    "recuperación. Búsquelo en la ventana donde corre el servidor."
}


@router.post("/login", response_model=Token)
def login(login_in: LoginRequest, db: Session = Depends(get_db)) -> Token:
    user = authenticate_user(db, login_in.correo, login_in.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales inválidas.",
        )
    token = create_access_token({"sub": str(user.id_usuario), "rol": user.rol})
    return Token(
        access_token=token,
        rol=user.rol,
        id_usuario=user.id_usuario,
        nombre_completo=user.nombre_completo,
    )


@router.get("/me", response_model=UsuarioRead)
def read_current_user(current_user: Usuario = Depends(get_current_user)) -> Usuario:
    return current_user


@router.post("/recuperar/solicitar", status_code=status.HTTP_202_ACCEPTED)
def request_recovery_code(datos: RecuperacionSolicitud, db: Session = Depends(get_db)) -> dict:
    """Genera un código de recuperación que se muestra en la consola del servidor.
    La respuesta es la misma exista o no el correo, para no revelar qué cuentas existen."""
    user = find_user_by_email(db, datos.correo)
    if user is not None and user.is_active and user.rol is not None:
        recuperacion_service.issue_code(user.correo, user.nombre_completo)
    return RESPUESTA_SOLICITUD


@router.post("/recuperar/confirmar", status_code=status.HTTP_204_NO_CONTENT)
def confirm_recovery(datos: RecuperacionConfirmacion, db: Session = Depends(get_db)) -> None:
    user = find_user_by_email(db, datos.correo)
    if user is None or not recuperacion_service.consume_code(user.correo, datos.codigo):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Código inválido o vencido. Solicite uno nuevo.",
        )
    user.password_hash = hash_password(datos.password)
    db.commit()
