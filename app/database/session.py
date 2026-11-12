import importlib
import logging
import time

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

Base = declarative_base()


def _engine_options(database_url: str) -> dict:
    # pool_pre_ping descarta conexiones caídas y abre una nueva antes de usarlas.
    options: dict = {"pool_pre_ping": True}
    if make_url(database_url).get_backend_name() == "postgresql":
        options.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            pool_timeout=settings.DB_POOL_TIMEOUT,
            pool_recycle=settings.DB_POOL_RECYCLE,
            connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT},
        )
    return options


engine = create_engine(settings.DATABASE_URL, **_engine_options(settings.DATABASE_URL))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """SQLite (desarrollo): crea las tablas. PostgreSQL: el esquema ya existe y solo se
    comprueba que estén todas las tablas que usa la aplicación."""
    # Importa los modelos para que queden registrados en Base.metadata.
    importlib.import_module("app.models")

    if engine.url.get_backend_name() == "sqlite":
        Base.metadata.create_all(bind=engine)
        seed_reference_data()
        return
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing = sorted(set(Base.metadata.tables) - existing)
    missing += sorted(
        f"{name}.{column.name}"
        for name, table in Base.metadata.tables.items()
        if name in existing
        for column in table.columns
        if column.name not in {c["name"] for c in inspector.get_columns(name)}
    )
    if missing:
        raise RuntimeError(
            "Faltan tablas o columnas en la base de datos: " + ", ".join(missing)
            + ". Aplique las migraciones pendientes de la carpeta migrations/ "
            "(002_frontend.sql, 003_sku_por_categoria.py y 004_auditoria.sql) antes de iniciar."
        )


def seed_reference_data() -> None:
    """Solo SQLite de desarrollo: roles y monedas mínimos que cauchos_rey_def ya trae."""
    from app.models import Moneda, Rol

    with SessionLocal() as db:
        if db.query(Rol).count() == 0:
            db.add_all([Rol(nombre="Administrador"), Rol(nombre="Cajero")])
        if db.query(Moneda).count() == 0:
            db.add_all(
                [
                    Moneda(codigo="USD", nombre="Dólar estadounidense", simbolo="$", es_base=1),
                    Moneda(codigo=settings.LOCAL_CURRENCY, nombre="Moneda local", es_base=0),
                ]
            )
        db.commit()


def check_database_connection() -> None:
    """Ejecuta SELECT NOW() con reintentos; falla si la base no responde."""
    safe_url = engine.url.render_as_string(hide_password=True)
    attempts = max(settings.DB_CONNECT_RETRIES, 1)
    for attempt in range(1, attempts + 1):
        try:
            with engine.connect() as connection:
                now = connection.execute(select(func.now())).scalar_one()
            logger.info("Conexión a la base de datos exitosa (%s): %s", safe_url, now)
            return
        except OperationalError as exc:
            if attempt == attempts:
                raise RuntimeError(
                    f"No se pudo conectar a la base de datos {safe_url} "
                    f"tras {attempts} intentos."
                ) from exc
            delay = settings.DB_RETRY_DELAY * 2 ** (attempt - 1)
            logger.warning(
                "Intento %d/%d de conexión fallido (%s). Reintentando en %.1f s.",
                attempt,
                attempts,
                exc.orig,
                delay,
            )
            time.sleep(delay)


def dispose_engine() -> None:
    engine.dispose()
