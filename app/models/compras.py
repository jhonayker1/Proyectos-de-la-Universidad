from sqlalchemy import Column, Date, DateTime, ForeignKey, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import relationship

from app.core.dates import local_now
from app.database.session import Base


class Compra(Base):
    """Compra a proveedor (migración 002). Sus detalles representan entradas de stock."""

    __tablename__ = "compras"

    id_compra = Column(Integer, primary_key=True)
    id_proveedor = Column(Integer, ForeignKey("proveedores.id_proveedor"), nullable=False)
    numero_factura = Column(String(30), nullable=True)
    fecha = Column(Date, nullable=False)
    descripcion = Column(String(255), nullable=True)
    monto_usd = Column(Numeric(12, 2), nullable=False)
    pagado = Column(SmallInteger, nullable=False, default=0, server_default="0")
    id_usuario = Column(Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    fecha_registro = Column(DateTime, nullable=True, default=local_now)

    proveedor = relationship("Proveedor", lazy="joined")
    detalles = relationship(
        "DetalleCompra",
        back_populates="compra",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="DetalleCompra.id_detalle_compra",
    )


class DetalleCompra(Base):
    __tablename__ = "detalles_compra"

    id_detalle_compra = Column(Integer, primary_key=True)
    id_compra = Column(
        Integer, ForeignKey("compras.id_compra", ondelete="CASCADE"), nullable=False
    )
    id_producto = Column(Integer, ForeignKey("productos.id_producto"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    costo_unitario_usd = Column(Numeric(10, 2), nullable=False)

    compra = relationship("Compra", back_populates="detalles")
    producto = relationship("Producto", lazy="joined")


class FacturaImagen(Base):
    """Factura escaneada guardada en disco (uploads/facturas)."""

    __tablename__ = "facturas_imagenes"

    id_factura_img = Column(Integer, primary_key=True)
    nombre_original = Column(String(255), nullable=False)
    ruta_archivo = Column(String(255), nullable=False)
    tipo_mime = Column(String(100), nullable=False)
    tamano_bytes = Column(Integer, nullable=False)
    id_compra = Column(
        Integer, ForeignKey("compras.id_compra", ondelete="SET NULL"), nullable=True
    )
    id_usuario = Column(Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    fecha_subida = Column(DateTime, nullable=True, default=local_now)
