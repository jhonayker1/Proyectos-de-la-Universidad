import importlib

from app.models.auditoria import Auditoria
from app.models.compras import Compra, DetalleCompra, FacturaImagen
from app.models.finanzas import Moneda, TasaCambio
from app.models.inventario import Categoria, Marca, Producto, Proveedor
from app.models.usuarios import Rol, Usuario
from app.models.ventas import DetalleVenta, Venta

# Registra la auditoría automática en toda sesión (API, scripts de consola y pruebas).
importlib.import_module("app.services.auditoria_service")

__all__ = [
    "Auditoria",
    "Rol",
    "Usuario",
    "Categoria",
    "Marca",
    "Proveedor",
    "Producto",
    "Moneda",
    "TasaCambio",
    "Venta",
    "DetalleVenta",
    "Compra",
    "DetalleCompra",
    "FacturaImagen",
]
