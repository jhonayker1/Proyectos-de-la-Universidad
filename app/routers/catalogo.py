"""Categorías, marcas y proveedores: misma lógica de consulta y mantenimiento."""

from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.inventario import Categoria, Marca, Proveedor
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
            after_update(db, item, values)
        commit_or_conflict(db)
        db.refresh(item)
        return item

    @router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
    def deactivate_item(
        item_id: int,
        db: Session = Depends(get_db),
        _: Usuario = Depends(require_roles(["admin"])),
    ) -> None:
        get_or_404(db, item_id).estado = 0
        db.commit()

    return router


def reprice_category_products(db: Session, categoria: Categoria, values: dict) -> None:
    """Al cambiar el margen de la categoría, recalcula los productos sin margen propio."""
    if "margen_ganancia" in values:
        reprice_category(db, categoria)


categorias_router = build_catalog_router(
    "/categorias", Categoria, "id_categoria",
    CategoriaCreate, CategoriaUpdate, CategoriaRead, "Categoría",
    required_on_update=frozenset({"nombre", "estado", "margen_ganancia"}),
    after_update=reprice_category_products,
)
marcas_router = build_catalog_router(
    "/marcas", Marca, "id_marca", MarcaCreate, MarcaUpdate, MarcaRead, "Marca"
)
proveedores_router = build_catalog_router(
    "/proveedores", Proveedor, "id_proveedor",
    ProveedorCreate, ProveedorUpdate, ProveedorRead, "Proveedor",
)
