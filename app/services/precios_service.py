from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.money import price_with_margin
from app.models.inventario import Categoria, Producto


def effective_margin(producto: Producto, categoria: Categoria | None) -> Decimal:
    """Margen propio del producto o, si no tiene, el de su categoría."""
    if producto.margen_pct is not None:
        return producto.margen_pct
    return categoria.margen_ganancia if categoria is not None else Decimal("0")


def apply_margin_price(db: Session, producto: Producto) -> None:
    """precio_usd = precio_distribuidor × (1 + margen efectivo / 100).

    Un margen efectivo de 0 significa "precio manual": si el producto ya tiene precio,
    no se toca (así los productos existentes no quedan a precio de costo)."""
    categoria = db.get(Categoria, producto.id_categoria)
    margen = effective_margin(producto, categoria)
    if margen == 0 and producto.precio_usd is not None:
        return
    producto.precio_usd = price_with_margin(producto.precio_distribuidor, margen)


def reprice_category(db: Session, categoria: Categoria) -> None:
    """Recalcula los productos de la categoría que no tienen margen propio."""
    if categoria.margen_ganancia == 0:
        return
    productos = (
        db.query(Producto)
        .filter(Producto.id_categoria == categoria.id_categoria, Producto.margen_pct.is_(None))
        .all()
    )
    for producto in productos:
        producto.precio_usd = price_with_margin(
            producto.precio_distribuidor, categoria.margen_ganancia
        )
