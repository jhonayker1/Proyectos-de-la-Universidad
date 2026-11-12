"""Categorías, marcas y proveedores: misma lógica de consulta y mantenimiento."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.core.money import round_money
from app.database.session import get_db
from app.models.compras import Compra
from app.models.inventario import PRODUCTO_INACTIVO, Categoria, Marca, Producto, Proveedor
from app.models.usuarios import Usuario
from app.schemas.catalogo import (
    CategoriaCreate,
    CategoriaRead,
    CategoriaUpdate,
    MarcaCreate,
    MarcaRead,
    MarcaUpdate,
    ProveedorCreate,
    ProveedorRead,
    ProveedorUpdate,
)
from app.services.precios_service import reprice_category
from app.services.sku_service import asegurar_prefijo_libre, ocupados, prefijo_desde_nombre


def build_catalog_router(
    prefix: str,
    model,
    pk_name: str,
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    read_schema: type[BaseModel],
    label: str,
    required_on_update: frozenset[str] = frozenset({"nombre", "estado"}),
    after_update: Callable[[Session, object, dict], None] | None = None,
    before_delete: Callable[[Session, object], None] | None = None,
    before_create: Callable[[Session, dict], None] | None = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["catalogo"])
    pk = getattr(model, pk_name)

    def get_or_404(db: Session, item_id: int):
        item = db.query(model).filter(pk == item_id).first()
        if item is None:
            raise HTTPException(status_code=404, detail=f"{label} no encontrado(a).")
        return item

    def commit_or_conflict(db: Session) -> None:
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=409, detail=f"{label} ya registrado(a).") from exc

    @router.get("/", response_model=list[read_schema])
    def list_items(
        incluir_inactivos: bool = Query(default=False),
        db: Session = Depends(get_db),
        _: Usuario = Depends(require_roles(["admin", "cashier"])),
    ):
        query = db.query(model)
        if not incluir_inactivos:
            query = query.filter(model.estado == 1)
        return query.order_by(model.nombre).all()

    @router.post("/", response_model=read_schema, status_code=status.HTTP_201_CREATED)
    def create_item(
        item_in: create_schema,
        db: Session = Depends(get_db),
        _: Usuario = Depends(require_roles(["admin"])),
    ):
        values = item_in.model_dump()
        values["nombre"] = values["nombre"].strip()
        if before_create is not None:
            before_create(db, values)
        item = model(**values, estado=1)
        db.add(item)
        commit_or_conflict(db)
        db.refresh(item)
        return item

    @router.put("/{item_id}", response_model=read_schema)
    def update_item(
        item_id: int,
        item_in: update_schema,
        db: Session = Depends(get_db),
        _: Usuario = Depends(require_roles(["admin"])),
    ):
        item = get_or_404(db, item_id)
        values = item_in.model_dump(exclude_unset=True)
        for field, value in values.items():
            if value is None and field in required_on_update:
                raise HTTPException(status_code=422, detail=f"{field} no puede ser null.")
            setattr(item, field, value.strip() if field == "nombre" else value)
        if after_update is not None:
            try:
                after_update(db, item, values)
            except HTTPException:
                # Una validación rechazó el cambio: se descarta lo asignado arriba.
                db.rollback()
                raise
        commit_or_conflict(db)
        db.refresh(item)
        return item

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    def deactivate_item(
        item_id: int,
        db: Session = Depends(get_db),
        _: Usuario = Depends(require_roles(["admin"])),
    ) -> None:
        item = get_or_404(db, item_id)
        if before_delete is not None:
            before_delete(db, item)
        item.estado = 0
        db.commit()

    return router


def ensure_category_without_stock(db: Session, categoria: Categoria) -> None:
    """No se desactiva una categoría mientras tenga productos activos con stock."""
    con_stock = (
        db.query(Producto)
        .filter(
            Producto.id_categoria == categoria.id_categoria,
            Producto.estado != PRODUCTO_INACTIVO,
            Producto.stock_actual > 0,
        )
        .order_by(Producto.stock_actual.desc())
        .all()
    )
    if con_stock:
        unidades = sum(p.stock_actual for p in con_stock)
        ejemplos = ", ".join(p.nombre for p in con_stock[:3])
        resto = f" y {len(con_stock) - 3} más" if len(con_stock) > 3 else ""
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede desactivar {categoria.nombre}: tiene {len(con_stock)} producto(s) "
                f"con stock ({unidades} unidades): {ejemplos}{resto}. Venda ese stock o cambie "
                "esos productos de categoría antes de desactivarla."
            ),
        )


def on_category_update(db: Session, categoria: Categoria, values: dict) -> None:
    """Desactivar por PUT (estado = 0) exige lo mismo que por DELETE; el margen recalcula
    precios; el código del SKU no puede repetirse con otra categoría."""
    if values.get("estado") == 0:
        ensure_category_without_stock(db, categoria)
    if "margen_ganancia" in values:
        reprice_category(db, categoria)
    if "prefijo_sku" in values:
        asegurar_prefijo_libre(db, categoria.prefijo_sku, excepto_id=categoria.id_categoria)


def on_category_create(db: Session, values: dict) -> None:
    """Código del SKU: el indicado (si está libre) o uno derivado del nombre."""
    if values.get("prefijo_sku"):
        asegurar_prefijo_libre(db, values["prefijo_sku"])
    else:
        values["prefijo_sku"] = prefijo_desde_nombre(values["nombre"], ocupados(db))


categorias_router = build_catalog_router(
    "/categorias", Categoria, "id_categoria",
    CategoriaCreate, CategoriaUpdate, CategoriaRead, "Categoría",
    required_on_update=frozenset({"nombre", "estado", "margen_ganancia", "prefijo_sku"}),
    after_update=on_category_update,
    before_delete=ensure_category_without_stock,
    before_create=on_category_create,
)
marcas_router = build_catalog_router(
    "/marcas", Marca, "id_marca", MarcaCreate, MarcaUpdate, MarcaRead, "Marca"
)


def ensure_no_pending_purchases(db: Session, proveedor: Proveedor) -> None:
    """No se elimina un proveedor al que se le deben compras."""
    count, total = (
        db.query(func.count(Compra.id_compra), func.coalesce(func.sum(Compra.monto_usd), 0))
        .filter(Compra.id_proveedor == proveedor.id_proveedor, Compra.pagado == 0)
        .one()
    )
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"No se puede eliminar {proveedor.nombre}: tiene {count} compra(s) pendiente(s) "
                f"de pago por ${round_money(total):,.2f}. Márquelas como pagadas antes de eliminarlo."
            ),
        )


proveedores_router = build_catalog_router(
    "/proveedores", Proveedor, "id_proveedor",
    ProveedorCreate, ProveedorUpdate, ProveedorRead, "Proveedor",
    # RIF, teléfono y correo son obligatorios: al editar no se pueden borrar (null).
    required_on_update=frozenset({"nombre", "estado", "rif", "telefono", "correo"}),
    before_delete=ensure_no_pending_purchases,
)
