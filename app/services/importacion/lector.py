"""Lectura del archivo, fila por fila y sin cargarlo entero en memoria.

- .xlsx / .xlsm: openpyxl en modo solo lectura (va descomprimiendo la hoja a medida que
  se recorre) y con los valores ya calculados de las fórmulas.
- .csv / .txt: se detecta la codificación (UTF-8, UTF-16 de "Texto Unicode" de Excel o
  Windows-1252, típico de Excel en español) y el separador (; , tabulador o |).

La fila de encabezados se busca entre las primeras filas, así que los títulos o logos
encima de la tabla no molestan. Cada recorrido vuelve a leer el archivo desde el disco:
la validación y la escritura son dos pasadas sin guardar las filas en memoria.
"""

import codecs
import csv
import io
import zipfile
from collections.abc import Iterator
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, BinaryIO

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from app.services.importacion.errores import ErrorDeArchivo
from app.services.importacion.mapeo import reconocidos

FILAS_BUSQUEDA_ENCABEZADO = 15
MAX_COLUMNAS = 200
_MUESTRA_CSV = 64 * 1024
_SEPARADORES = ";,\t|"


def _recortar(fila: tuple | list) -> list[Any]:
    valores = list(fila[:MAX_COLUMNAS])
    while valores and (valores[-1] is None or (isinstance(valores[-1], str) and not valores[-1].strip())):
        valores.pop()
    return valores


def fila_vacia(valores: list[Any]) -> bool:
    return all(v is None or (isinstance(v, str) and not v.strip()) for v in valores)


@dataclass
class Tabla:
    """Una hoja (o el CSV) con su fila de encabezados ya ubicada."""

    formato: str  # xlsx | csv
    hoja: str | None
    fila_encabezados: int  # número de fila como lo ve el usuario (1 = primera)
    encabezados: list[Any]
    hojas: list[str] = field(default_factory=list)
    detalles_formato: dict[str, str] = field(default_factory=dict)
    _origen: Any = None

    def filas(self) -> Iterator[tuple[int, list[Any]]]:
        """(número de fila, valores) de cada fila debajo de los encabezados."""
        for numero, valores in self._origen():
            if numero > self.fila_encabezados:
                yield numero, valores


class Lector:
    """Abre el archivo y entrega la Tabla. Úsese como contexto: cierra el libro al salir."""

    def __init__(self, archivo: BinaryIO, nombre: str | None, hoja: str | None = None):
        self.archivo = archivo
        self.nombre = nombre or "archivo"
        self.hoja = hoja
        self._libro = None

    def __enter__(self) -> "Lector":
        return self

    def __exit__(self, *_: object) -> None:
        if self._libro is not None:
            self._libro.close()

    def abrir(self) -> Tabla:
        self.archivo.seek(0)
        inicio = self.archivo.read(8)
        self.archivo.seek(0)
        if not inicio:
            raise ErrorDeArchivo("El archivo está vacío.")
        if inicio.startswith(b"PK\x03\x04"):
            return self._abrir_xlsx()
        if inicio.startswith(b"\xd0\xcf\x11\xe0"):
            raise ErrorDeArchivo(
                "El archivo es un Excel antiguo (.xls). Ábralo en Excel y guárdelo como "
                "'Libro de Excel (.xlsx)' o como CSV.",
                status_code=415,
            )
        if inicio.startswith(b"%PDF") or self.nombre.lower().endswith((".pdf", ".doc", ".docx")):
            raise ErrorDeArchivo("Solo se aceptan archivos Excel (.xlsx) o CSV.", status_code=415)
        return self._abrir_csv()

    # ---------------------------------------------------------------- Excel
    def _abrir_xlsx(self) -> Tabla:
        try:
            self._libro = load_workbook(self.archivo, read_only=True, data_only=True)
        except (InvalidFileException, zipfile.BadZipFile, KeyError, OSError, ValueError) as exc:
            raise ErrorDeArchivo(
                "El archivo no es un Excel válido o está dañado. Ábralo en Excel y vuelva a "
                "guardarlo como .xlsx.",
                status_code=415,
            ) from exc
        hojas = list(self._libro.sheetnames)
        if self.hoja is not None:
            if self.hoja not in hojas:
                raise ErrorDeArchivo(
                    f"El libro no tiene una hoja llamada '{self.hoja}'.",
                    detalles=[f"Hojas disponibles: {', '.join(hojas)}"],
                )
            candidatas = [self.hoja]
        else:
            # Primero la hoja activa (la que se ve al abrir el libro) y luego las demás.
            activa = self._libro.active.title if self._libro.active is not None else None
            candidatas = ([activa] if activa in hojas else []) + [h for h in hojas if h != activa]
        for nombre_hoja in candidatas:
            hoja = self._libro[nombre_hoja]
            if not hasattr(hoja, "iter_rows"):
                continue  # hoja de gráfico
            # Algunos programas guardan mal el tamaño de la hoja (p. ej. "A1"); así se
            # recorre lo que realmente tiene.
            hoja.reset_dimensions()

            def origen(h=hoja) -> Iterator[tuple[int, list[Any]]]:
                for numero, fila in enumerate(h.iter_rows(values_only=True, max_col=MAX_COLUMNAS), start=1):
                    yield numero, _recortar(fila)

            tabla = self._ubicar_encabezados(origen, "xlsx", nombre_hoja)
            if tabla is not None:
                tabla.hojas = hojas
                return tabla
        raise self._sin_encabezados(hojas)

    # ---------------------------------------------------------------- CSV
    def _codificacion(self, muestra: bytes) -> str:
        if muestra.startswith(codecs.BOM_UTF8):
            return "utf-8-sig"
        if muestra.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            return "utf-16"
        try:
            # final=False: la muestra puede cortar un carácter de varios bytes al final.
            codecs.getincrementaldecoder("utf-8")().decode(muestra, final=False)
            return "utf-8"
        except UnicodeDecodeError:
            return "cp1252"

    def _separador(self, texto: str) -> str:
        try:
            return csv.Sniffer().sniff(texto, delimiters=_SEPARADORES).delimiter
        except csv.Error:
            primera = next((linea for linea in texto.splitlines() if linea.strip()), "")
            return max(_SEPARADORES, key=primera.count)

    def _abrir_csv(self) -> Tabla:
        muestra = self.archivo.read(_MUESTRA_CSV)
        self.archivo.seek(0)
        if b"\x00" in muestra and not muestra.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            raise ErrorDeArchivo(
                "El archivo no parece ser un Excel ni un CSV de texto.", status_code=415
            )
        codificacion = self._codificacion(muestra)
        texto = muestra.decode(codificacion, errors="ignore")
        separador = self._separador(texto)

        def origen() -> Iterator[tuple[int, list[Any]]]:
            self.archivo.seek(0)
            envoltura = io.TextIOWrapper(self.archivo, encoding=codificacion, newline="")
            try:
                for numero, fila in enumerate(csv.reader(envoltura, delimiter=separador), start=1):
                    yield numero, _recortar(fila)
            except UnicodeDecodeError as exc:
                raise ErrorDeArchivo(
                    "El CSV tiene caracteres que no se pueden leer. Guárdelo desde Excel como "
                    "'CSV UTF-8 (delimitado por comas)'.",
                ) from exc
            except csv.Error as exc:
                raise ErrorDeArchivo(f"El CSV está mal formado: {exc}.") from exc
            finally:
                envoltura.detach()  # no cerrar el archivo subido: se vuelve a leer

        tabla = self._ubicar_encabezados(origen, "csv", None)
        if tabla is None:
            raise self._sin_encabezados([])
        nombres = {";": "punto y coma", ",": "coma", "\t": "tabulador", "|": "barra vertical"}
        tabla.detalles_formato = {
            "codificacion": codificacion,
            "separador": nombres.get(separador, separador),
        }
        return tabla

    # ---------------------------------------------------------------- común
    def _ubicar_encabezados(self, origen, formato: str, hoja: str | None) -> Tabla | None:
        """La fila de encabezados es la primera, entre las 15 de arriba, con al menos dos
        nombres de campo reconocidos."""
        with closing(origen()) as filas:
            for numero, valores in filas:
                if numero > FILAS_BUSQUEDA_ENCABEZADO:
                    break
                if not fila_vacia(valores) and reconocidos(valores) >= 2:
                    return Tabla(formato, hoja, numero, valores, _origen=origen)
        return None

    def _sin_encabezados(self, hojas: list[str]) -> ErrorDeArchivo:
        from app.services.importacion.esquema import campos

        detalles = [
            "Se buscó, en las primeras 15 filas, una fila con al menos dos encabezados "
            "reconocibles (por ejemplo 'SKU', 'Nombre', 'Categoría', 'Precio', 'Stock').",
            "Encabezados aceptados: " + ", ".join(c.etiqueta for c in campos()) + ".",
        ]
        if hojas:
            detalles.append(f"Hojas revisadas: {', '.join(hojas)}.")
        return ErrorDeArchivo("No se encontró la fila de encabezados de la tabla.", detalles=detalles)
