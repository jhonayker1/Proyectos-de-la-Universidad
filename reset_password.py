"""Restablece la contraseña de un usuario existente desde la terminal.

Uso:  .\\.venv\\Scripts\\python.exe reset_password.py
Pide el correo y la nueva contraseña (oculta, dos veces) y guarda su hash bcrypt.
"""

import sys
from getpass import getpass

from app.core.security import hash_password
from app.database.session import SessionLocal, check_database_connection
from app.services.auditoria_service import establecer_origen  # además registra la auditoría
from app.services.auth_service import find_user_by_email


def reset_password(correo: str, password: str) -> str:
    """Cambia la contraseña y devuelve un resumen del usuario; lanza ValueError si no aplica."""
    if len(password) < 8:
        raise ValueError("La contraseña debe tener al menos 8 caracteres.")
    if len(password.encode("utf-8")) > 72:
        raise ValueError("La contraseña no puede superar 72 bytes.")
    with SessionLocal() as db:
        user = find_user_by_email(db, correo)
        if user is None:
            raise ValueError(f"No existe un usuario con el correo {correo}.")
        establecer_origen(db, "Consola del servidor (reset_password.py)")
        user.password_hash = hash_password(password)
        db.commit()
        estado = "activo" if user.is_active else "INACTIVO (no podrá entrar hasta activarlo)"
        rol = {"admin": "Administrador", "cashier": "Cajero"}.get(user.rol or "", "sin rol válido")
        return f"{user.nombre_completo} <{user.correo}> · {rol} · {estado}"


def main() -> int:
    check_database_connection()
    correo = input("Correo del usuario: ").strip()
    password = getpass("Nueva contraseña (no se muestra): ")
    if getpass("Repita la contraseña: ") != password:
        print("Las contraseñas no coinciden. No se cambió nada.")
        return 1
    try:
        resumen = reset_password(correo, password)
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    print(f"Contraseña actualizada: {resumen}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
