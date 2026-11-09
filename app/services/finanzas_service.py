from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.finanzas import Moneda, TasaCambio


def get_moneda(db: Session, codigo: str) -> Moneda:
    moneda = (
        db.query(Moneda)
        .filter(func.upper(Moneda.codigo) == codigo.strip().upper(), Moneda.estado == 1)
        .first()
    )
    if moneda is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Moneda '{codigo}' no encontrada o inactiva.",
        )
    return moneda


def get_tasa_vigente(db: Session, id_moneda: int) -> TasaCambio | None:
    return (
        db.query(TasaCambio)
        .filter(TasaCambio.id_moneda == id_moneda, TasaCambio.estado == 1)
        .order_by(TasaCambio.id_tasa.desc())
        .first()
    )


def require_tasa_vigente(db: Session, moneda: Moneda) -> TasaCambio:
    tasa = get_tasa_vigente(db, moneda.id_moneda)
    if tasa is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"No hay tasa de cambio vigente para {moneda.codigo.strip()}. "
            "Un administrador debe registrarla.",
        )
    return tasa


def local_rate_value(db: Session):
    """tasa_venta vigente de la moneda local (LOCAL_CURRENCY), o None si no hay."""
    moneda = (
        db.query(Moneda)
        .filter(func.upper(Moneda.codigo) == settings.LOCAL_CURRENCY.upper(), Moneda.estado == 1)
        .first()
    )
    if moneda is None or moneda.es_base == 1:
        return None
    tasa = get_tasa_vigente(db, moneda.id_moneda)
    return tasa.tasa_venta if tasa is not None else None
