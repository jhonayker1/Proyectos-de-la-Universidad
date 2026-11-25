from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.orm import relationship

from app.core.dates import local_now
from app.database.session import Base

# Nombres de la tabla roles que se reconocen como cada rol de la aplicación.
ROLE_ALIASES = {
    "admin": "admin",
    "administrador": "admin",
    "cashier": "cashier",
    "cajero": "cashier",
    "gestor": "gestor",
    "asistente administrativo": "gestor",
    "secretario": "gestor",
}


def role_key(role_name: str | None) -> str | None:
    """Traduce los nombres de roles de la base a sus claves internas."""
    if not role_name:
        return None
    return ROLE_ALIASES.get(role_name.strip().lower())


class Rol(Base):
    __tablename__ = "roles"

    id_rol = Column(Integer, primary_key=True)
    nombre = Column(String(50), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")


class Usuario(Base):
    __tablename__ = "usuarios"

    id_usuario = Column(Integer, primary_key=True)
    id_rol = Column(Integer, ForeignKey("roles.id_rol"), nullable=False)
    nombre_completo = Column(String(100), nullable=False)
    correo = Column(String(100), nullable=False, unique=True)
    password_hash = Column(String(255), nullable=False)
    telefono = Column(String(20), nullable=True)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")
    fecha_creacion = Column(DateTime, nullable=True, default=local_now)
    permisos = Column(String(255), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    fecha_eliminacion = Column(DateTime, nullable=True)
    id_usuario_eliminacion = Column(Integer, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "(is_deleted AND fecha_eliminacion IS NOT NULL) OR "
            "(NOT is_deleted AND fecha_eliminacion IS NULL)",
            name="ck_usuarios_soft_delete",
        ),
    )

    rol_rel = relationship("Rol", lazy="joined")

    @property
    def rol(self) -> str | None:
        return role_key(self.rol_rel.nombre) if self.rol_rel else None

    @property
    def is_active(self) -> bool:
        return self.estado == 1 and not self.is_deleted
