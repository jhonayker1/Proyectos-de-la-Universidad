import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import EmailStr, TypeAdapter
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import (
    SessionLocal,
    check_database_connection,
    dispose_engine,
    init_db,
)
from app.routers import (
    auditoria,
    auth,
    catalogo,
    compras,
    facturas,
    finanzas,
    importacion,
    productos,
    reportes,
    usuarios,
    ventas,
)
from app.schemas.usuarios import UsuarioCreate
from app.services.auth_service import find_user_by_email, register_user

logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s - %(message)s")
logger = logging.getLogger(__name__)


def seed_initial_admin(db: Session) -> None:
    """Crea un administrador si se definen INITIAL_ADMIN_* y el correo no existe."""
    credentials = (
        settings.INITIAL_ADMIN_NAME,
        settings.INITIAL_ADMIN_EMAIL,
        settings.INITIAL_ADMIN_PASSWORD,
    )
    if not any(credentials):
        return
    if not all(credentials):
        raise RuntimeError(
            "Define INITIAL_ADMIN_NAME, INITIAL_ADMIN_EMAIL e "
            "INITIAL_ADMIN_PASSWORD juntos para crear el administrador inicial."
        )
    name, email, password = credentials
    normalized_email = TypeAdapter(EmailStr).validate_python(email).lower()
    existing = find_user_by_email(db, normalized_email)
    if existing is not None:
        if existing.rol != "admin" or not existing.is_active:
            raise RuntimeError(
                "INITIAL_ADMIN_EMAIL pertenece a una cuenta que no es un administrador activo."
            )
        return
    try:
        register_user(
            db,
            UsuarioCreate(
                nombre_completo=name, correo=normalized_email, password=password, rol="admin"
            ),
        )
    except HTTPException as exc:
        raise RuntimeError(f"No se pudo crear el administrador inicial: {exc.detail}") from exc
    logger.info("Administrador inicial creado: %s", normalized_email)


@asynccontextmanager
async def lifespan(application: FastAPI):
    if application.state.initialize_database:
        check_database_connection()
        init_db()
        with SessionLocal() as db:
            seed_initial_admin(db)
    yield
    dispose_engine()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version="3.0.0",
    description=(
        "API de inventario y ventas de repuestos con precios en USD, conversión a "
        "moneda local según una tasa manual y roles de administrador y cajero."
    ),
    lifespan=lifespan,
)
app.state.initialize_database = True
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(usuarios.router)
app.include_router(catalogo.categorias_router)
app.include_router(catalogo.marcas_router)
app.include_router(catalogo.proveedores_router)
app.include_router(importacion.router)  # antes de productos: /productos/importar/...
app.include_router(productos.router)
app.include_router(finanzas.monedas_router)
app.include_router(finanzas.tasas_router)
app.include_router(ventas.router)
app.include_router(compras.router)
app.include_router(facturas.router)
app.include_router(reportes.router)
app.include_router(auditoria.router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"mensaje": "API de Inventario de Repuestos Activa"}
