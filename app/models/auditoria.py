from sqlalchemy import BigInteger, Column, DateTime, Index, Integer, String, Text

from app.database.session import Base


class Auditoria(Base):
    """Bitácora de cambios (migración 004). Solo se inserta: en PostgreSQL un trigger
    rechaza UPDATE, DELETE y TRUNCATE. La escribe app.services.auditoria_service."""

    __tablename__ = "auditoria"

    id_auditoria = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    fecha = Column(DateTime, nullable=False)
    # Sin llave foránea: el registro sobrevive aunque el usuario se elimine.
    id_usuario = Column(Integer, nullable=True)
    nombre_usuario = Column(String(100), nullable=False)
    rol = Column(String(20), nullable=True)
    modulo = Column(String(30), nullable=False)
    accion = Column(String(30), nullable=False)
    entidad = Column(String(40), nullable=False)
    id_registro = Column(String(40), nullable=True)
    referencia = Column(String(200), nullable=True)
    descripcion = Column(Text, nullable=False)
    cambios = Column(Text, nullable=True)  # JSON [{campo, etiqueta, antes, despues}]
    origen = Column(String(200), nullable=True)
    ruta = Column(String(200), nullable=True)
    ip = Column(String(45), nullable=True)
    id_operacion = Column(String(32), nullable=True)

    __table_args__ = (
        Index("ix_auditoria_fecha", fecha.desc()),
        Index("ix_auditoria_modulo_fecha", modulo, fecha.desc()),
        Index("ix_auditoria_usuario", id_usuario),
        Index("ix_auditoria_operacion", id_operacion),
    )
