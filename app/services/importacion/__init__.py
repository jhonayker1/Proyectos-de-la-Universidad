"""Carga masiva de inventario desde Excel (.xlsx) o CSV.

Capas, en el orden en que trabajan:

- ``lector``: abre el archivo y lo recorre fila por fila sin cargarlo entero en memoria
  (openpyxl en modo solo lectura; csv con detección de codificación y separador).
- ``mapeo``: reconoce los encabezados por alias y coincidencia aproximada, sin
  depender del orden ni del nombre exacto de las columnas.
- ``esquema``: los campos de destino, con tipos y límites leídos del modelo ``Producto``.
- ``conversores``: convierte cada celda (números con coma o punto, enteros, Sí/No, texto).
- ``catalogos``: resuelve categoría, marca y proveedor escritos como texto a sus IDs.
- ``procesador``: validación en dos pasadas y escritura por lotes en una transacción.
- ``reporte``: plantilla de carga y reporte de errores en Excel.
"""

from app.services.importacion.errores import ErrorDeArchivo, Incidencia
from app.services.importacion.procesador import Opciones, importar

__all__ = ["ErrorDeArchivo", "Incidencia", "Opciones", "importar"]
