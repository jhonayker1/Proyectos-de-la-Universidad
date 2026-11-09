from sqlalchemy import Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship

from app.core.dates import local_now
from app.database.session import Base

VENTA_COMPLETADA = "Completada"
VENTA_ANULADA = "Anulada"


class Venta(Base):
    __tablename__ = "ventas"

    id_venta = Column(Integer, primary_key=True)
    numero_factura = Column(String(30), nullable=False, unique=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    id_moneda_pago = Column(Integer, ForeignKey("monedas.id_moneda"), nullable=False)
    monto_total_usd = Column(Numeric(12, 2), nullable=False)
    monto_total_moneda = Column(Numeric(15, 2), nullable=False)
    tasa_aplicada = Column(Numeric(15, 4), nullable=False)
    referencia_pago = Column(String(50), nullable=True)
    estado = Column(String(50), nullable=False, default=VENTA_COMPLETADA)
    fecha_venta = Column(DateTime, nullable=True, default=local_now)

    usuario = relationship("Usuario")
    moneda_pago = relationship("Moneda", lazy="joined")
    detalles = relationship(
        "DetalleVenta",
        back_populates="venta",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DetalleVenta.id_detalle",
    )


class DetalleVenta(Base):
    __tablename__ = "detalles_venta"

    id_detalle = Column(Integer, primary_key=True)
    id_venta = Column(
        Integer, ForeignKey("ventas.id_venta", ondelete="CASCADE"), nullable=False
    )
    id_producto = Column(Integer, ForeignKey("productos.id_producto"), nullable=False)
    nombre_producto_snapshot = Column(String(150), nullable=False)
    cantidad = Column(Integer, nullable=False)
    precio_unitario_usd = Column(Numeric(10, 2), nullable=False)
    subtotal_usd = Column(Numeric(12, 2), nullable=False)

    venta = relationship("Venta", back_populates="detalles")
