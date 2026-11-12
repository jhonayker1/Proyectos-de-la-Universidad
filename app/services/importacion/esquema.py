"""Campos que se pueden importar.

Los tipos y límites (longitud de varchar, dígitos y decimales de numeric, si admite
NULL) no se escriben a mano: se leen de las columnas del modelo ``Producto`` y de las
tablas de catálogo, que ``init_db`` comprueba contra la base al arrancar. Si cambia el
esquema (p. ej. ``ubicacion`` pasa a varchar(120)), la validación lo sigue sola.

Aquí solo se declara lo que el esquema no sabe: el nombre visible, los alias con que
suelen aparecer en un Excel y el significado de negocio de cada campo.
"""

from dataclasses import dataclass
from decimal import Decimal
from functools import cache

from sqlalchemy import Column, Integer, Numeric, String

from app.models.inventario import Categoria, Marca, Producto, Proveedor

TEXTO = "texto"
DECIMAL = "decimal"
ENTERO = "entero"
BOOLEANO = "booleano"
REFERENCIA = "referencia"  # nombre (o código / ID) de otra tabla


@dataclass(frozen=True)
class Campo:
    clave: str
    etiqueta: str
    tipo: str
    descripcion: str
    alias: tuple[str, ...]
    # Alias que solo se usan si ninguna otra columna ocupa el campo ("Descripción" es el
    # nombre del producto cuando no hay una columna "Nombre").
    alias_secundarios: tuple[str, ...] = ()
    columna: str | None = None  # columna de productos que alimenta
    obligatorio_al_crear: bool = False
    max_length: int | None = None
    max_digits: int | None = None
    decimales: int | None = None
    minimo: Decimal | None = None
    maximo: Decimal | None = None
    ejemplo: str = ""

    def como_dict(self) -> dict:
        return {
            "clave": self.clave,
            "etiqueta": self.etiqueta,
            "tipo": self.tipo,
            "descripcion": self.descripcion,
            "obligatorio_al_crear": self.obligatorio_al_crear,
            "columna_bd": self.columna,
            "max_length": self.max_length,
            "decimales": self.decimales,
            "minimo": str(self.minimo) if self.minimo is not None else None,
            "maximo": str(self.maximo) if self.maximo is not None else None,
            "alias": list(self.alias + self.alias_secundarios),
            "ejemplo": self.ejemplo,
        }


def _limites(columna: Column) -> dict:
    """Límites de una columna según su tipo SQL."""
    tipo = columna.type
    if isinstance(tipo, String):
        return {"max_length": tipo.length}
    if isinstance(tipo, Numeric):
        digitos, escala = tipo.precision or 12, tipo.scale or 0
        tope = Decimal(10) ** (digitos - escala) - Decimal(1).scaleb(-escala)
        return {"max_digits": digitos, "decimales": escala, "maximo": tope}
    if isinstance(tipo, Integer):
        return {"maximo": Decimal(2**31 - 1)}  # integer de PostgreSQL
    return {}


def _de_columna(clave: str, tipo: str, columna: Column, **extra) -> Campo:
    datos = {"columna": columna.name, **_limites(columna)}
    datos.update(extra)
    if tipo in (DECIMAL, ENTERO):
        datos.setdefault("minimo", Decimal(0))
    return Campo(clave=clave, tipo=tipo, **datos)


@cache
def campos() -> tuple[Campo, ...]:
    p = Producto.__table__.c
    return (
        _de_columna(
            "sku", TEXTO, p.sku,
            etiqueta="SKU",
            descripcion="Código del producto. Si existe se actualiza ese producto; si se deja "
                        "vacío se genera el siguiente de la categoría (p. ej. CR-0063).",
            alias=("sku", "codigo", "cod", "codigo producto", "cod producto", "codigo articulo",
                   "codigo interno", "codigo repuesto", "referencia", "ref", "part number",
                   "numero parte", "nro parte", "num parte", "no parte", "item code",
                   "product code", "code"),
            ejemplo="(vacío = automático)",
        ),
        _de_columna(
            "nombre", TEXTO, p.nombre,
            etiqueta="Nombre",
            descripcion="Nombre del producto. Obligatorio para productos nuevos.",
            alias=("nombre", "producto", "nombre producto", "articulo", "nombre articulo",
                   "repuesto", "item", "product", "product name", "name", "denominacion"),
            alias_secundarios=("descripcion", "description", "detalle", "descripcion producto"),
            obligatorio_al_crear=True,
            ejemplo="Caucho 205/55 R16",
        ),
        Campo(
            clave="categoria", tipo=REFERENCIA, columna="id_categoria",
            etiqueta="Categoría",
            descripcion="Nombre o código de la categoría (Cauchos o CR). Obligatoria para "
                        "productos nuevos; define el código del SKU automático.",
            alias=("categoria", "category", "rubro", "familia", "linea", "grupo", "tipo",
                   "tipo producto", "clasificacion", "departamento", "seccion", "id categoria",
                   "cod categoria"),
            obligatorio_al_crear=True,
            max_length=Categoria.__table__.c.nombre.type.length,
            ejemplo="Cauchos",
        ),
        Campo(
            clave="marca", tipo=REFERENCIA, columna="id_marca",
            etiqueta="Marca",
            descripcion="Nombre de la marca. Opcional.",
            alias=("marca", "brand", "fabricante", "manufacturer", "make", "id marca"),
            max_length=Marca.__table__.c.nombre.type.length,
            ejemplo="Michelin",
        ),
        Campo(
            clave="proveedor", tipo=REFERENCIA, columna="id_proveedor",
            etiqueta="Proveedor",
            descripcion="Nombre o RIF de un proveedor ya registrado. Opcional.",
            alias=("proveedor", "supplier", "vendor", "distribuidor", "proveedor principal",
                   "id proveedor", "rif proveedor", "rif", "casa comercial"),
            max_length=Proveedor.__table__.c.nombre.type.length,
        ),
        _de_columna(
            "precio_distribuidor", DECIMAL, p.precio_distribuidor,
            etiqueta="Costo USD",
            descripcion="Precio de compra al distribuidor, en USD.",
            alias=("precio distribuidor", "costo", "cost", "precio costo", "costo unitario",
                   "p costo", "pc", "precio compra", "costo compra", "valor compra",
                   "precio proveedor", "unit cost"),
            ejemplo="45.00",
        ),
        _de_columna(
            "precio_usd", DECIMAL, p.precio_usd,
            etiqueta="Precio venta USD",
            descripcion="Precio de venta en USD. Si se deja vacío se calcula con el margen: "
                        "costo × (1 + margen / 100).",
            alias=("precio venta", "p venta", "pv", "pvp", "precio", "price", "sale price",
                   "precio publico", "precio venta publico", "precio detal", "valor venta",
                   "precio final"),
            ejemplo="62.50",
        ),
        _de_columna(
            "margen_pct", DECIMAL, p.margen_pct,
            etiqueta="Margen %",
            descripcion="Margen de ganancia propio del producto (%). Vacío = el de la categoría.",
            alias=("margen", "margen ganancia", "ganancia", "utilidad", "margen pct",
                   "ganancia pct", "utilidad pct", "pct ganancia", "markup",
                   "porcentaje ganancia", "porcentaje", "pct"),
        ),
        _de_columna(
            "stock_actual", ENTERO, p.stock_actual,
            etiqueta="Stock",
            descripcion="Unidades en existencia (número entero).",
            alias=("stock", "stock actual", "existencia", "existencias", "cantidad", "cant",
                   "qty", "quantity", "unidades", "inventario", "disponible",
                   "stock disponible", "cantidad disponible", "en stock", "saldo"),
            ejemplo="12",
        ),
        _de_columna(
            "stock_minimo", ENTERO, p.stock_minimo,
            etiqueta="Stock mínimo",
            descripcion="Debajo de este número el producto queda en Bajo Stock. Por defecto 5.",
            alias=("stock minimo", "minimo", "min", "stock min", "cantidad minima",
                   "punto reorden", "reorden", "min stock", "minimum stock",
                   "existencia minima", "alerta stock"),
            ejemplo="4",
        ),
        _de_columna(
            "ubicacion", TEXTO, p.ubicacion,
            etiqueta="Ubicación",
            descripcion="Dónde está en la tienda o el depósito.",
            alias=("ubicacion", "location", "estante", "anaquel", "pasillo", "almacen",
                   "deposito", "bodega", "ubicacion fisica", "rack", "gaveta"),
            ejemplo="Estante A",
        ),
        Campo(
            clave="activo", tipo=BOOLEANO, columna="estado",
            etiqueta="Activo",
            descripcion="Sí/No. 'No' oculta el producto (estado Inactivo); 'Sí' lo reactiva. "
                        "Vacío = no cambia.",
            alias=("activo", "active", "habilitado", "vigente", "disponible venta", "visible"),
            ejemplo="Sí",
        ),
    )


@cache
def por_clave() -> dict[str, Campo]:
    return {c.clave: c for c in campos()}


# Columnas frecuentes que no tienen dónde guardarse. Se reconocen para explicar por qué
# se ignoran en vez de confundirlas con otro campo ("Código de barras" no es el SKU).
IGNORADAS: dict[str, tuple[str, ...]] = {
    "La base de datos no tiene un campo de código de barras; la columna no se importa.": (
        "codigo barras", "cod barras", "barcode", "ean", "upc", "codigo ean",
    ),
    "Los precios se guardan en USD; el precio en otras monedas se calcula con la tasa del día.": (
        "precio bs", "precio bolivares", "precio ves", "precio cop", "precio pesos",
        "precio local", "bs", "bolivares", "costo bs", "precio eur",
    ),
    "El estado (Disponible, Bajo Stock, Agotado) se calcula solo según el stock. "
    "Para ocultar productos use la columna Activo (Sí/No).": (
        "estado", "status", "disponibilidad", "situacion",
    ),
    "La fecha de ingreso se registra automáticamente.": (
        "fecha", "fecha ingreso", "fecha registro", "fecha alta", "date",
    ),
    "Es un valor calculado (precio × cantidad); no se importa.": (
        "total", "precio total", "valor inventario", "valor total", "subtotal", "monto",
        "costo total",
    ),
    "El ID lo asigna la base de datos; para actualizar un producto use su SKU.": (
        "id", "id producto", "num", "nro", "numero", "n",
    ),
    "La base de datos no guarda imágenes de productos.": ("imagen", "foto", "image", "url imagen"),
}
