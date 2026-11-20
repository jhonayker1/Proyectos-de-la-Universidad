from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import require_roles
from app.database.session import get_db
from app.models.finanzas import Moneda, TasaCambio
from app.models.usuarios import Usuario
from app.schemas.finanzas import MonedaRead, TasaCambioCreate, TasaCambioRead
from app.services.finanzas_service import get_moneda, require_tasa_vigente

monedas_router = APIRouter(prefix="/monedas", tags=["monedas"])
tasas_router = APIRouter(prefix="/tasas", tags=["tasas"])


def to_read(tasa: TasaCambio) -> TasaCambioRead:
    return TasaCambioRead(
        id_tasa=tasa.id_tasa,
        id_moneda=tasa.id_moneda,
        codigo_moneda=tasa.moneda.codigo.strip(),
        tasa_compra=tasa.tasa_compra,
        tasa_venta=tasa.tasa_venta,
        fecha_actualizacion=tasa.fecha_actualizacion,
        estado=tasa.estado,
    )


@monedas_router.get("/", response_model=list[MonedaRead])
def list_currencies(
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> list[Moneda]:
    return db.query(Moneda).filter(Moneda.estado == 1).order_by(Moneda.id_moneda).all()


@tasas_router.get("/vigente", response_model=TasaCambioRead)
def current_rate(
    codigo_moneda: str = Query(default=settings.LOCAL_CURRENCY, min_length=3, max_length=3),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin", "cashier"])),
) -> TasaCambioRead:
    return to_read(require_tasa_vigente(db, get_moneda(db, codigo_moneda)))


@tasas_router.get("/", response_model=list[TasaCambioRead])
def rate_history(
    codigo_moneda: str | None = Query(default=None, min_length=3, max_length=3),
    limite: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> list[TasaCambioRead]:
    query = db.query(TasaCambio)
    if codigo_moneda:
        query = query.filter(TasaCambio.id_moneda == get_moneda(db, codigo_moneda).id_moneda)
    return [to_read(t) for t in query.order_by(TasaCambio.id_tasa.desc()).limit(limite).all()]


@tasas_router.post("/", response_model=TasaCambioRead, status_code=status.HTTP_201_CREATED)
def set_rate(
    tasa_in: TasaCambioCreate,
    db: Session = Depends(get_db),
    _: Usuario = Depends(require_roles(["admin"])),
) -> TasaCambioRead:
    """Registra una tasa nueva; las anteriores de esa moneda quedan con estado = 0."""
    moneda = get_moneda(db, tasa_in.codigo_moneda)
    if moneda.es_base == 1:
        raise HTTPException(
            status_code=400, detail="La moneda base no necesita tasa de cambio."
        )
    db.query(TasaCambio).filter(
        TasaCambio.id_moneda == moneda.id_moneda, TasaCambio.estado == 1
    ).update({TasaCambio.estado: 0}, synchronize_session=False)
    tasa = TasaCambio(
        id_moneda=moneda.id_moneda,
        tasa_venta=tasa_in.tasa_venta,
        tasa_compra=tasa_in.tasa_compra or tasa_in.tasa_venta,
        estado=1,
    )
    db.add(tasa)
    db.commit()
    db.refresh(tasa)
    return to_read(tasa)
