"""Grupos de roles con nombre para ``require_roles``.

Jerarquía: Administrador > Gestor (asistente administrativo) > Cajero.

- ``SOLO_ADMIN``: configuración (usuarios, tasas, márgenes y categorías), reportes
  financieros y todo lo irreversible (anular ventas, eliminar productos, proveedores,
  facturas, marcar compras pagadas).
- ``GESTION``: operación diaria supervisada (inventario, entradas y ajustes,
  proveedores y reportes operativos).
- ``TODOS``: lo que también usa el cajero (catálogo y productos en solo lectura, ventas).
"""

from app.core.dependencies import require_roles

ADMIN = "admin"
GESTOR = "gestor"
CAJERO = "cashier"

SOLO_ADMIN = [ADMIN]
GESTION = [ADMIN, GESTOR]
TODOS = [ADMIN, GESTOR, CAJERO]
CAJA = [ADMIN, CAJERO]  # quienes cobran en el punto de venta

solo_admin = require_roles(SOLO_ADMIN)
gestion = require_roles(GESTION)
todos = require_roles(TODOS)
caja = require_roles(CAJA)
