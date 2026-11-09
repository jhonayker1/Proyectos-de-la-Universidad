from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.config import settings

# Las columnas de fecha de la base son "timestamp without time zone": se guarda la
# hora local del negocio (TIMEZONE) sin zona, igual que CURRENT_TIMESTAMP del servidor.


def business_timezone() -> ZoneInfo:
    return ZoneInfo(settings.TIMEZONE)


def local_now() -> datetime:
    return datetime.now(business_timezone()).replace(tzinfo=None)


def local_today() -> date:
    return local_now().date()


def day_bounds(day: date) -> tuple[datetime, datetime]:
    """Inicio y fin (exclusivo) del día, en hora local sin zona."""
    start = datetime.combine(day, time.min)
    return start, start + timedelta(days=1)
