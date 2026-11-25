from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
)
from sqlalchemy.orm import relationship

from app.core.dates import local_now
from app.database.session import Base

PRODUCTO_DISPONIBLE = "Disponible"
PRODUCTO_BAJO_STOCK = "Bajo Stock"
PRODUCTO_AGOTADO = "Agotado"
PRODUCTO_INACTIVO = "Inactivo"
MOTIVOS_AJUSTE = {
    "conteo": "Conteo físico",
    "merma": "Daño o merma",
    "devolucion": "Devolución",
    "otro": "Otro",
}


class Categoria(Base):
    __tablename__ = "categorias"

    id_categoria = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    descripcion = Column(String(255), nullable=True)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")
    # Margen de ganancia (%) por defecto de los productos de la categoría (migración 002).
    margen_ganancia = Column(Numeric(5, 2), nullable=False, default=0, server_default="0")
    # Código de la categoría para el SKU automático: LUB -> LUB-0001 (migración 003).
    prefijo_sku = Column(String(5), nullable=True, unique=True)


class Marca(Base):
    __tablename__ = "marcas"

    id_marca = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False, unique=True)
    pais_origen = Column(String(50), nullable=True)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")


class Proveedor(Base):
    __tablename__ = "proveedores"

    id_proveedor = Column(Integer, primary_key=True)
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(20), nullable=True)
    estado = Column(SmallInteger, nullable=False, default=1, server_default="1")
    rif = Column(String(20), nullable=True)
    contacto = Column(String(100), nullable=True)
    correo = Column(String(100), nullable=True)
    ciudad = Column(String(60), nullable=True)
    direccion = Column(String(200), nullable=True)
    condiciones = Column(String(120), nullable=True)


class Producto(Base):
    """Repuesto. precio_usd es el precio de venta; precio_distribuidor, el costo."""

    __tablename__ = "productos"

    id_producto = Column(Integer, primary_key=True)
    sku = Column(String(50), nullable=False)
    nombre = Column(String(150), nullable=False)
    id_marca = Column(Integer, ForeignKey("marcas.id_marca"), nullable=True)
    id_categoria = Column(Integer, ForeignKey("categorias.id_categoria"), nullable=False)
    id_proveedor = Column(Integer, ForeignKey("proveedores.id_proveedor"), nullable=True)
    precio_distribuidor = Column(Numeric(10, 2), nullable=False, default=0)
    precio_usd = Column(Numeric(10, 2), nullable=False, default=0)
    stock_actual = Column(Integer, nullable=False, default=0)
    stock_minimo = Column(Integer, nullable=False, default=5)
    estado = Column(String(50), nullable=False, default=PRODUCTO_DISPONIBLE)
    fecha_ingreso = Column(DateTime, nullable=True, default=local_now)
    # Margen propio (%); si es NULL se usa el de la categoría (migración 002).
    margen_pct = Column(Numeric(5, 2), nullable=True)
    ubicacion = Column(String(80), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False, server_default="false")
    fecha_eliminacion = Column(DateTime, nullable=True)
    id_usuario_eliminacion = Column(Integer, nullable=True)

    marca = relationship("Marca", lazy="joined")
    categoria = relationship("Categoria", lazy="joined")
    proveedor = relationship("Proveedor", lazy="joined")

    __table_args__ = (
        Index(
            "ux_productos_sku_activo",
            "sku",
            unique=True,
            postgresql_where=is_deleted.is_(False),
            sqlite_where=is_deleted.is_(False),
        ),
        CheckConstraint(
            "(is_deleted AND fecha_eliminacion IS NOT NULL) OR "
            "(NOT is_deleted AND fecha_eliminacion IS NULL)",
            name="ck_productos_soft_delete",
        ),
    )

    @property
    def is_active(self) -> bool:
        return not self.is_deleted and self.estado != PRODUCTO_INACTIVO

    def sync_stock_status(self) -> None:
        """Ajusta estado según el stock, con la misma regla de los datos de la base:
        Agotado si no hay stock, Bajo Stock si está por debajo del mínimo y Disponible
        en otro caso. No toca productos dados de baja (Inactivo)."""
        if self.is_deleted or self.estado == PRODUCTO_INACTIVO:
            return
        if self.stock_actual <= 0:
            self.estado = PRODUCTO_AGOTADO
        elif self.stock_actual < self.stock_minimo:
            self.estado = PRODUCTO_BAJO_STOCK
        else:
            self.estado = PRODUCTO_DISPONIBLE


class AjusteStock(Base):
    """Corrección manual de stock con su justificación."""

    __tablename__ = "ajustes_stock"

    id_ajuste = Column(Integer, primary_key=True)
    id_producto = Column(Integer, ForeignKey("productos.id_producto"), nullable=False)
    cantidad = Column(Integer, nullable=False)
    stock_anterior = Column(Integer, nullable=False)
    stock_nuevo = Column(Integer, nullable=False)
    motivo = Column(String(30), nullable=False)
    observacion = Column(String(255), nullable=False)
    id_usuario = Column(Integer, ForeignKey("usuarios.id_usuario"), nullable=False)
    fecha = Column(DateTime, nullable=False, default=local_now)

    producto = relationship("Producto", lazy="joined")
    usuario = relationship("Usuario", lazy="joined")
