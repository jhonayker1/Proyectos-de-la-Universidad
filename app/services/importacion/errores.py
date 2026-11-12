"""Estructuras de error de la importación.

Hay dos niveles:

- ``Incidencia``: problema de una fila (o advertencia). Nunca detiene la lectura; se
  acumula y se devuelve como "Fila X, Columna 'Y': motivo".
- ``ErrorDeArchivo``: el archivo completo no se puede procesar (formato, encabezados,
  tamaño). Se responde con un JSON limpio y el código HTTP indicado, nunca con un 500.
"""

from dataclasses import dataclass
from typing import Any

ERROR = "error"
ADVERTENCIA = "advertencia"


def mostrar_valor(valor: Any, limite: int = 60) -> str | None:
    if valor is None:
        return None
    texto = str(valor)
    return texto if len(texto) <= limite else texto[: limite - 1] + "…"


@dataclass(slots=True)
class Incidencia:
    fila: int | None
    motivo: str
    columna: str | None = None  # encabezado tal como está en el archivo
    letra: str | None = None  # letra de la columna en Excel (A, B, …)
    campo: str | None = None  # campo del inventario al que corresponde
    valor: str | None = None
    nivel: str = ERROR

    @property
    def mensaje(self) -> str:
        partes = []
        if self.fila is not None:
            partes.append(f"Fila {self.fila}")
        if self.columna:
            partes.append(f"Columna '{self.columna}'")
        prefijo = ", ".join(partes)
        return f"{prefijo}: {self.motivo}" if prefijo else self.motivo

    def como_dict(self) -> dict[str, Any]:
        return {
            "fila": self.fila,
            "columna": self.columna,
            "letra": self.letra,
            "campo": self.campo,
            "valor": self.valor,
            "motivo": self.motivo,
            "nivel": self.nivel,
            "mensaje": self.mensaje,
        }


class ValorInvalido(Exception):
    """Una celda no se puede convertir; el texto es el motivo que verá el usuario."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


class ErrorDeArchivo(Exception):
    """El archivo no se puede procesar en absoluto (no hay nada que importar fila a fila)."""

    def __init__(self, mensaje: str, status_code: int = 422, detalles: list[str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code
        self.detalles = detalles or []

    def como_dict(self) -> dict[str, Any]:
        return {"detail": self.mensaje, "detalles": self.detalles}
