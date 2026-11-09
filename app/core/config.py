import os
import secrets
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

BASE_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BASE_DIR / ".env")


def build_database_url() -> str:
    """DATABASE_URL tiene prioridad; si no existe, se arma con las variables DB_*."""
    explicit_url = os.getenv("DATABASE_URL")
    if explicit_url:
        return explicit_url
    user = os.getenv("DB_USER")
    name = os.getenv("DB_NAME")
    if user and name:
        return URL.create(
            "postgresql+psycopg",
            username=user,
            password=os.getenv("DB_PASSWORD") or None,
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            database=name,
        ).render_as_string(hide_password=False)
    return "sqlite:///./inventario.db"


class Settings:
    PROJECT_NAME: str = "Representaciones July Rey - Inventario de Repuestos"
    PORT: int = int(os.getenv("PORT", "8000"))
    # Moneda local en la que se convierten los precios en USD (p. ej. VES).
    LOCAL_CURRENCY: str = os.getenv("LOCAL_CURRENCY", "VES")
    # Zona horaria del negocio, usada para delimitar los días en los reportes.
    TIMEZONE: str = os.getenv("TIMEZONE", "America/Caracas")
    # Carpeta donde se guardan las facturas escaneadas que sube el administrador.
    UPLOAD_DIR: Path = Path(os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads")))
    MAX_UPLOAD_MB: int = int(os.getenv("MAX_UPLOAD_MB", "10"))
    DATABASE_URL: str = build_database_url()
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", "30"))
    DB_POOL_RECYCLE: int = int(os.getenv("DB_POOL_RECYCLE", "1800"))
    DB_CONNECT_TIMEOUT: int = int(os.getenv("DB_CONNECT_TIMEOUT", "10"))
    DB_CONNECT_RETRIES: int = int(os.getenv("DB_CONNECT_RETRIES", "5"))
    DB_RETRY_DELAY: float = float(os.getenv("DB_RETRY_DELAY", "2"))
    SECRET_KEY: str = os.getenv("SECRET_KEY") or secrets.token_urlsafe(32)
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60")
    )
    CORS_ORIGINS: list[str] = [
        origin.strip()
        for origin in os.getenv(
            "CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173",
        ).split(",")
        if origin.strip()
    ]
    INITIAL_ADMIN_NAME: str | None = os.getenv("INITIAL_ADMIN_NAME")
    INITIAL_ADMIN_EMAIL: str | None = os.getenv("INITIAL_ADMIN_EMAIL")
    INITIAL_ADMIN_PASSWORD: str | None = os.getenv("INITIAL_ADMIN_PASSWORD")


settings = Settings()
