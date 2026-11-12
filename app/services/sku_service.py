"""SKU automático por categoría: cada categoría tiene un código (prefijo_sku, p. ej. LUB) y
los productos nuevos continúan su numeración: LUB-27 -> LUB-28. Las categorías sin
productos con ese código empiezan en {PREFIJO}-0001."""

import re
import unicodedata
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.inventario import Categoria, Producto

PREFIJO_RE = re.compile(r"^[A-Z]{2,5}$")
ANCHO_POR_DEFECTO = 4
# Código al inicio del SKU de los productos existentes: "LUB-01", "CR-0012" (y "CR-0050~4" eliminados).
_SKU_RE = re.compile(r"^([A-Z]{2,5})-(\d+)(?:~\d+)?$")


def normalizar_prefijo(valor: str) -> str:
    prefijo = valor.strip().upper()
    if not PREFIJO_RE.match(prefijo):
        raise ValueError("El código de la categoría debe tener de 2 a 5 letras, sin números ni acentos (p. ej. LUB).")
    return prefijo


def prefijo_desde_nombre(nombre: str, ocupados: set[str]) -> str:
    """Primeras letras del nombre sin acentos (Baterías -> BAT); si ya existe, prueba variantes."""
    plano = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().upper()
    palabras = re.findall(r"[A-Z]+", plano) or ["CAT"]
    candidatos = [palabras[0][:3], "".join(p[0] for p in palabras)[:5], palabras[0][:4], palabras[0][:5]]
    for c in candidatos:
        if len(c) >= 2 and c not in ocupados:
            return c
    base = (palabras[0] + "XX")[:3]
    letra = 0
    while f"{base}{chr(65 + letra)}" in ocupados:  # BATA, BATB, ...
        letra += 1
    return f"{base}{chr(65 + letra)}"


def ocupados(db: Session, excepto_id: int | None = None) -> set[str]:
    return {
        p for (i, p) in db.query(Categoria.id_categoria, Categoria.prefijo_sku).all()
        if p and i != excepto_id
    }


def asegurar_prefijo_libre(db: Session, prefijo: str, excepto_id: int | None = None) -> None:
    otra = (
        db.query(Categoria)
        .filter(Categoria.prefijo_sku == prefijo, Categoria.id_categoria != (excepto_id or 0))
        .first()
    )
    if otra is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El código {prefijo} ya lo usa la categoría {otra.nombre}.",
        )


def asignar_prefijos_faltantes(db: Session) -> dict[str, str]:
    """Da código a las categorías que no tienen. Usa el código que ya llevan sus productos
    (el más frecuente); si dos categorías comparten código, lo conserva la que más lo usa y
    a la otra se le deriva uno del nombre. Devuelve {categoría: código} de lo asignado."""
    categorias = db.query(Categoria).order_by(Categoria.id_categoria).all()
    tomados = {c.prefijo_sku for c in categorias if c.prefijo_sku}
    pendientes = [c for c in categorias if not c.prefijo_sku]
    candidatos: list[tuple[int, Categoria, str]] = []
    for c in pendientes:
        conteo = Counter(
            m.group(1)
            for (sku,) in db.query(Producto.sku).filter(Producto.id_categoria == c.id_categoria)
            if (m := _SKU_RE.match(sku))
        )
        if conteo:
            prefijo, n = conteo.most_common(1)[0]
            candidatos.append((n, c, prefijo))
    asignados: dict[str, str] = {}
    for _, c, prefijo in sorted(candidatos, key=lambda t: (-t[0], t[1].id_categoria)):
        if prefijo not in tomados:
            c.prefijo_sku = prefijo
            tomados.add(prefijo)
            asignados[c.nombre] = prefijo
    for c in pendientes:
        if not c.prefijo_sku:
            c.prefijo_sku = prefijo_desde_nombre(c.nombre, tomados)
            tomados.add(c.prefijo_sku)
            asignados[c.nombre] = c.prefijo_sku
    db.flush()
    return asignados


def numeracion(db: Session, prefijo: str) -> tuple[int, int]:
    """(último número usado, ancho del número) entre los SKU {prefijo}-NNNN existentes."""
    numeros: list[tuple[int, int]] = []  # (valor, cantidad de dígitos)
    for (sku,) in db.query(Producto.sku).filter(Producto.sku.like(f"{prefijo}-%")):
        m = _SKU_RE.match(sku)
        if m and m.group(1) == prefijo:
            numeros.append((int(m.group(2)), len(m.group(2))))
    ultimo = max((n for n, _ in numeros), default=0)
    ancho = max((w for _, w in numeros), default=ANCHO_POR_DEFECTO)
    return ultimo, ancho


def siguiente_sku(db: Session, categoria: Categoria) -> str:
    """Próximo SKU libre de la categoría, con el mismo ancho de número que ya usa."""
    if not categoria.prefijo_sku:
        categoria.prefijo_sku = prefijo_desde_nombre(categoria.nombre, ocupados(db, categoria.id_categoria))
        db.flush()
    prefijo = categoria.prefijo_sku
    ultimo, ancho = numeracion(db, prefijo)
    siguiente = ultimo + 1
    while True:
        sku = f"{prefijo}-{siguiente:0{ancho}d}"
        if db.query(Producto.id_producto).filter(Producto.sku == sku).first() is None:
            return sku
        siguiente += 1
