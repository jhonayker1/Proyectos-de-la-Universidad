from sqlalchemy import CHAR, Column, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import relationship

from app.core.dates import local_now
from app.database.session import Base


class Moneda(Base):
    """es_base = 1 marca la moneda en la que están los precios (USD)."""

    __tablename__ = "monedas"

    id_moneda = Column(Integer, primary_key=True)
    codigo = Column(CHAR(3), nullable=False, unique=True)
    nombre = Column(String(50), nullable=False)
    simbolo = Column(String(5), nullable=True)
    es_base = Column(SmallInteger, nullable=False, default=0, server_default="0")
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")


class TasaCambio(Base):
    """Unidades de la moneda por 1 USD. La vigente es la última con estado = 1."""

    __tablename__ = "tasas_cambio"

    id_tasa = Column(Integer, primary_key=True)
    id_moneda = Column(Integer, ForeignKey("monedas.id_moneda"), nullable=False)
    tasa_compra = Column(Numeric(15, 4), nullable=False)
    tasa_venta = Column(Numeric(15, 4), nullable=False)
    fecha_actualizacion = Column(DateTime, nullable=True, default=local_now)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")

    moneda = relationship("Moneda", lazy="joined")
