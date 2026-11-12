"""Archivos Excel que genera la importación.

- ``plantilla``: hoja lista para llenar, con instrucciones y los catálogos actuales.
- ``reporte_errores``: resumen, cada error/advertencia con fila y columna, y una hoja
  "Filas a corregir" con las filas rechazadas tal como venían, para arreglarlas y
  volver a subir solo esas.

Todo texto que viene del archivo del usuario se escribe como texto: un valor como
"=HYPERLINK(...)" no se convierte en fórmula al abrir el reporte.
"""

import io
from typing import Any

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation
from sqlalchemy.orm import Session

from app.models.inventario import Categoria, Marca, Proveedor
from app.services.importacion.esquema import campos
from app.services.importacion.procesador import Resultado

_TITULO = Font(bold=True, color="FFFFFF")
_FONDO = PatternFill("solid", fgColor="4F46E5")
_FONDO_ERROR = PatternFill("solid", fgColor="FDE2E7")
_FONDO_AVISO = PatternFill("solid", fgColor="FEF3C7")
_ESTADOS = {
    "validado": "Validado (sin guardar)",
    "rechazado": "Rechazado: no se guardó nada",
    "sin_cambios": "Sin cambios",
    "importado": "Importado",
    "importado_parcial": "Importado parcialmente",
}


def _celda(hoja, valor: Any, fuente: Font | None = None, fondo: PatternFill | None = None) -> WriteOnlyCell:
    celda = WriteOnlyCell(hoja, value=valor)
    if isinstance(valor, str) and valor.startswith(("=", "+", "-", "@")):
        celda.data_type = "s"  # nunca una fórmula
    if fuente is not None:
        celda.font = fuente
    if fondo is not None:
        celda.fill = fondo
    return celda


def _encabezados(hoja, titulos: list[str], anchos: list[int]) -> None:
    for i, ancho in enumerate(anchos, start=1):
        hoja.column_dimensions[get_column_letter(i)].width = ancho
    hoja.freeze_panes = "A2"
    hoja.append([_celda(hoja, t, _TITULO, _FONDO) for t in titulos])


def _a_bytes(libro: Workbook) -> bytes:
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def reporte_errores(r: Resultado) -> bytes:
    libro = Workbook(write_only=True)

    resumen = libro.create_sheet("Resumen")
    resumen.column_dimensions["A"].width = 32
    resumen.column_dimensions["B"].width = 90
    datos = r.resumen()
    filas = [
        ("Archivo", r.nombre_archivo),
        ("Hoja", r.tabla.hoja or "(CSV)"),
        ("Fila de encabezados", r.tabla.fila_encabezados),
        ("Modo", r.opciones.modo),
        ("Resultado", _ESTADOS.get(r.estado, r.estado)),
        ("Mensaje", r.mensaje),
        ("Filas leídas", datos["filas_leidas"]),
        ("Filas válidas", datos["filas_validas"]),
        ("Filas con errores", datos["filas_con_error"]),
        ("Productos nuevos", datos["creados"] if r.aplicado else datos["a_crear"]),
        ("Productos actualizados", datos["actualizados"] if r.aplicado else datos["a_actualizar"]),
        ("Filas omitidas", datos["a_omitir"]),
        ("Advertencias", datos["total_advertencias"]),
    ]
    resumen.append([_celda(resumen, "Concepto", _TITULO, _FONDO), _celda(resumen, "Valor", _TITULO, _FONDO)])
    for concepto, valor in filas:
        resumen.append([_celda(resumen, concepto, Font(bold=True)), _celda(resumen, valor)])
    resumen.append([])
    resumen.append([_celda(resumen, "Columnas del archivo", _TITULO, _FONDO), _celda(resumen, "Uso", _TITULO, _FONDO)])
    for c in r.mapeo.columnas:
        resumen.append([_celda(resumen, f"{c.letra}: {c.encabezado}"), _celda(resumen, f"→ {c.como_dict()['etiqueta']} ({c.metodo})")])
    for c in r.mapeo.ignoradas:
        resumen.append([_celda(resumen, f"{c.letra}: {c.encabezado}"), _celda(resumen, f"Ignorada: {c.motivo}")])

    errores = libro.create_sheet("Errores")
    _encabezados(errores, ["Tipo", "Fila", "Columna", "Campo", "Valor", "Motivo", "Mensaje"],
                 [13, 7, 22, 20, 28, 70, 90])
    for i in r.errores() + r.advertencias():
        fondo = _FONDO_AVISO if i.nivel == "advertencia" else _FONDO_ERROR
        errores.append([
            _celda(errores, "Advertencia" if i.nivel == "advertencia" else "Error", fondo=fondo),
            _celda(errores, i.fila),
            _celda(errores, f"{i.letra}: {i.columna}" if i.letra else i.columna),
            _celda(errores, i.campo),
            _celda(errores, i.valor),
            _celda(errores, i.motivo),
            _celda(errores, i.mensaje),
        ])
    if r.total_errores + r.total_advertencias > len(r.incidencias):
        errores.append([_celda(errores, f"… y {r.total_errores + r.total_advertencias - len(r.incidencias)} más (se muestran las primeras {len(r.incidencias)}).")])

    corregir = libro.create_sheet("Filas a corregir")
    titulos = ["Fila original", "Errores"] + [str(e) if e is not None else "" for e in r.tabla.encabezados]
    _encabezados(corregir, titulos, [12, 60] + [18] * len(r.tabla.encabezados))
    for numero, valores, motivos in r.filas_erroneas:
        corregir.append(
            [_celda(corregir, numero), _celda(corregir, " | ".join(motivos), fondo=_FONDO_ERROR)]
            + [_celda(corregir, v) for v in valores]
        )
    return _a_bytes(libro)


def plantilla(db: Session) -> bytes:
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Productos"
    lista = campos()
    for i, campo in enumerate(lista, start=1):
        celda = hoja.cell(row=1, column=i, value=campo.etiqueta)
        celda.font, celda.fill = _TITULO, _FONDO
        hoja.column_dimensions[get_column_letter(i)].width = max(14, len(campo.etiqueta) + 4)
    hoja.freeze_panes = "A2"

    categorias = db.query(Categoria).filter(Categoria.estado == 1).order_by(Categoria.nombre).all()
    marcas = db.query(Marca).filter(Marca.estado == 1).order_by(Marca.nombre).all()
    proveedores = db.query(Proveedor).filter(Proveedor.estado == 1).order_by(Proveedor.nombre).all()

    ayuda = libro.create_sheet("Instrucciones")
    for col, ancho in zip("ABCDEF", (20, 13, 12, 70, 20, 60)):
        ayuda.column_dimensions[col].width = ancho
    ayuda.append(["Columna", "Obligatoria", "Tipo", "Descripción", "Ejemplo", "También se reconoce como"])
    for celda in ayuda[1]:
        celda.font, celda.fill = _TITULO, _FONDO
    for campo in lista:
        ejemplo = campo.ejemplo
        if campo.clave == "categoria" and categorias:
            ejemplo = categorias[0].nombre
        ayuda.append([
            campo.etiqueta,
            "Al crear" if campo.obligatorio_al_crear else "No",
            campo.tipo,
            campo.descripcion + (f" Máximo {campo.max_length} caracteres." if campo.max_length and campo.tipo == "texto" else ""),
            ejemplo,
            ", ".join((campo.alias + campo.alias_secundarios)[:8]),
        ])
    ayuda.append([])
    notas = (
        "El orden de las columnas no importa y los encabezados no tienen que ser exactos.",
        "La tabla puede empezar más abajo (por ejemplo, con un título encima).",
        "Si el SKU ya existe, se actualiza ese producto; las celdas vacías no cambian nada.",
        "Sin SKU se crea un producto nuevo con el siguiente código de su categoría.",
        "Los números aceptan coma o punto decimal (12,50 o 12.50) y símbolos como $.",
        "Use 'Validar' antes de importar: muestra cada error con su fila y columna sin guardar nada.",
    )
    for nota in notas:
        ayuda.append([nota])

    for titulo, filas, encabezados in (
        ("Categorías", [(c.nombre, c.prefijo_sku) for c in categorias], ("Categoría", "Código SKU")),
        ("Marcas", [(m.nombre,) for m in marcas], ("Marca",)),
        ("Proveedores", [(p.nombre, p.rif) for p in proveedores], ("Proveedor", "RIF")),
    ):
        h = libro.create_sheet(titulo)
        h.append(list(encabezados))
        for celda in h[1]:
            celda.font, celda.fill = _TITULO, _FONDO
        h.column_dimensions["A"].width = 34
        h.column_dimensions["B"].width = 16
        for fila in filas:
            h.append(list(fila))

    # Listas desplegables con los catálogos (se pueden escribir otros valores).
    for clave, hoja_lista, n in (("categoria", "Categorías", len(categorias)), ("marca", "Marcas", len(marcas))):
        if n:
            letra = get_column_letter([c.clave for c in lista].index(clave) + 1)
            validacion = DataValidation(type="list", formula1=f"='{hoja_lista}'!$A$2:$A${n + 1}",
                                        allow_blank=True, showErrorMessage=False)
            hoja.add_data_validation(validacion)
            validacion.add(f"{letra}2:{letra}5000")
    for celda in hoja[1]:
        celda.alignment = Alignment(vertical="center")
    return _a_bytes(libro)
