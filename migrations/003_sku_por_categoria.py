"""Migración 003: código de categoría para el SKU automático (categorias.prefijo_sku).

Agrega la columna (única) y asigna un código a cada categoría que no lo tenga, tomando el
que ya usan sus productos (LUB-01 -> LUB). Si dos categorías usan el mismo código, lo
conserva la que más productos tiene con él y la otra recibe uno derivado de su nombre.
No modifica ningún SKU existente. Se puede ejecutar varias veces.

Uso (desde la carpeta del proyecto):  .\\.venv\\Scripts\\python.exe migrations\\003_sku_por_categoria.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.database.session import engine  # noqa: E402
from app.models.inventario import Categoria  # noqa: E402
from app.services.sku_service import asignar_prefijos_faltantes, siguiente_sku  # noqa: E402


def main() -> None:
    with engine.begin() as conn:  # una sola transacción: todo o nada
        conn.execute(text("ALTER TABLE categorias ADD COLUMN IF NOT EXISTS prefijo_sku varchar(5)"))
        conn.execute(text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_categorias_prefijo_sku ON categorias (prefijo_sku)"
        ))
        db = Session(bind=conn)
        asignados = asignar_prefijos_faltantes(db)
        db.flush()
        print("Código y próximo SKU por categoría:")
        for c in db.query(Categoria).order_by(Categoria.id_categoria):
            nuevo = " (asignado ahora)" if c.nombre in asignados else ""
            print(f"  {c.nombre:<34} {c.prefijo_sku:<5} -> {siguiente_sku(db, c)}{nuevo}")
        db.flush()
    print("Migración 003 aplicada.")


if __name__ == "__main__":
    main()
