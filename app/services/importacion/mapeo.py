"""Reconocimiento de encabezados: "P. Venta", "Precio de Venta ($)" o "price" -> precio_usd.

1. Se normaliza el texto: sin acentos, minúsculas, sin signos ni palabras vacías
   ("de", "la", "usd", …). "Precio de Venta ($)" -> "precio venta".
2. Se compara con los alias de cada campo (y con las columnas conocidas que se
   ignoran) y se le da un puntaje:
   - 1.00 igual a un alias; 0.97 igual sin espacios ("pventa");
   - 0.75–0.95 si contiene todas las palabras de un alias ("precio venta mayor");
   - la similitud de difflib si es >= 0.80 (errores de tipeo: "Exsitencia").
   Los alias secundarios valen un 7 % menos.
3. Asignación global: el mejor puntaje se queda con el campo; una columna nunca ocupa
   un campo ya tomado. Lo no reconocido se informa como ignorado, con su motivo.

El usuario puede corregir cualquier columna con ``mapeo`` ({"C": "precio_usd"}).
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache

from openpyxl.utils import get_column_letter

from app.services.importacion.errores import ErrorDeArchivo
from app.services.importacion.esquema import IGNORADAS, campos, por_clave

UMBRAL = 0.80
UMBRAL_ENCABEZADO = 0.97  # para decidir qué fila es la de encabezados
PENALIZACION_SECUNDARIO = 0.93
IGNORAR = "ignorar"

_VACIAS = {
    "de", "del", "la", "el", "los", "las", "en", "por", "al", "a", "y", "para", "con",
    "usd", "us", "dolar", "dolares", "unitario", "unit",
}


def normalizar(texto: object) -> str:
    plano = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode().lower()
    plano = plano.replace("%", " pct ").replace("$", " usd ")
    palabras = re.findall(r"[a-z0-9]+", plano)
    utiles = [p for p in palabras if p not in _VACIAS]
    # "USD" solo: no dejar el encabezado vacío.
    return " ".join(utiles or palabras)


@dataclass(frozen=True)
class _Alias:
    texto: str
    destino: str  # clave del campo, o el motivo si es una columna que se ignora
    ignorada: bool
    peso: float


@cache
def _alias() -> tuple[_Alias, ...]:
    lista = []
    for campo in campos():
        for a in campo.alias:
            lista.append(_Alias(normalizar(a), campo.clave, False, 1.0))
        for a in campo.alias_secundarios:
            lista.append(_Alias(normalizar(a), campo.clave, False, PENALIZACION_SECUNDARIO))
    for motivo, alias in IGNORADAS.items():
        for a in alias:
            lista.append(_Alias(normalizar(a), motivo, True, 1.0))
    return tuple(lista)


def _puntaje(encabezado: str, alias: str) -> float:
    if encabezado == alias:
        return 1.0
    if encabezado.replace(" ", "") == alias.replace(" ", ""):
        return 0.97
    palabras_e, palabras_a = encabezado.split(), alias.split()
    contiene = 0.0
    if palabras_a and set(palabras_a) <= set(palabras_e):
        contiene = 0.75 + 0.2 * len(palabras_a) / len(palabras_e)
    similitud = SequenceMatcher(None, encabezado, alias).ratio()
    return max(contiene, similitud if similitud >= UMBRAL else 0.0)


def candidatos(encabezado: object) -> list[tuple[float, _Alias]]:
    """Destinos posibles de un encabezado, el mejor primero (uno por destino)."""
    texto = normalizar(encabezado)
    if not texto:
        return []
    mejores: dict[tuple[str, bool], tuple[float, _Alias]] = {}
    for a in _alias():
        puntaje = _puntaje(texto, a.texto) * a.peso
        if puntaje >= UMBRAL:
            clave = (a.destino, a.ignorada)
            if clave not in mejores or puntaje > mejores[clave][0]:
                mejores[clave] = (puntaje, a)
    return sorted(mejores.values(), key=lambda t: -t[0])


def reconocidos(fila: list[object]) -> int:
    """Cuántas celdas de una fila son, con seguridad, encabezados de campos."""
    total = 0
    for celda in fila:
        if celda is None or str(celda).strip() == "":
            continue
        mejor = candidatos(celda)
        if mejor and not mejor[0][1].ignorada and mejor[0][0] >= UMBRAL_ENCABEZADO:
            total += 1
    return total


@dataclass
class ColumnaMapeada:
    indice: int  # 0 = columna A
    encabezado: str
    campo: str
    metodo: str  # alias | aproximado | manual
    confianza: float

    @property
    def letra(self) -> str:
        return get_column_letter(self.indice + 1)

    def como_dict(self) -> dict:
        return {
            "letra": self.letra,
            "columna": self.encabezado,
            "campo": self.campo,
            "etiqueta": por_clave()[self.campo].etiqueta,
            "metodo": self.metodo,
            "confianza": round(self.confianza, 2),
        }


@dataclass
class ColumnaIgnorada:
    indice: int
    encabezado: str
    motivo: str

    @property
    def letra(self) -> str:
        return get_column_letter(self.indice + 1)

    def como_dict(self) -> dict:
        return {"letra": self.letra, "columna": self.encabezado, "motivo": self.motivo}


@dataclass
class Mapeo:
    columnas: list[ColumnaMapeada]
    ignoradas: list[ColumnaIgnorada]

    def __post_init__(self) -> None:
        self._por_campo = {c.campo: c for c in self.columnas}

    def columna(self, campo: str) -> ColumnaMapeada | None:
        return self._por_campo.get(campo)

    def tiene(self, campo: str) -> bool:
        return campo in self._por_campo


def _texto_encabezado(valor: object, indice: int) -> str:
    texto = " ".join(str(valor).split()) if valor is not None else ""
    return texto or f"(sin título, columna {get_column_letter(indice + 1)})"


def _leer_mapeo_manual(manual: dict[str, str], encabezados: list[str]) -> dict[int, str]:
    """{"C": "precio_usd", "Existencia": "stock_actual", "D": ""} -> {índice: campo}."""
    validos = por_clave()
    letras = {get_column_letter(i + 1): i for i in range(len(encabezados))}
    por_texto = {normalizar(e): i for i, e in enumerate(encabezados) if e}
    resultado: dict[int, str] = {}
    errores = []
    for origen, destino in manual.items():
        clave = str(origen).strip()
        indice = letras.get(clave.upper())
        if indice is None:
            indice = por_texto.get(normalizar(clave))
        if indice is None:
            errores.append(f"El mapeo indica la columna '{clave}', que no está en el archivo.")
            continue
        destino = (destino or "").strip() or IGNORAR
        if destino != IGNORAR and destino not in validos:
            errores.append(
                f"El mapeo asigna la columna '{clave}' al campo '{destino}', que no existe. "
                f"Campos válidos: {', '.join(validos)}."
            )
            continue
        resultado[indice] = destino
    duplicados = [d for d in set(resultado.values()) if d != IGNORAR and list(resultado.values()).count(d) > 1]
    for d in duplicados:
        errores.append(f"El mapeo asigna más de una columna al campo '{d}'.")
    if errores:
        raise ErrorDeArchivo("El mapeo de columnas indicado no es válido.", detalles=errores)
    return resultado


def mapear(encabezados_crudos: list[object], manual: dict[str, str] | None = None) -> Mapeo:
    encabezados = [_texto_encabezado(v, i) for i, v in enumerate(encabezados_crudos)]
    vacias = {i for i, v in enumerate(encabezados_crudos) if v is None or str(v).strip() == ""}
    fijadas = _leer_mapeo_manual(manual or {}, encabezados)

    columnas: list[ColumnaMapeada] = []
    ignoradas: list[ColumnaIgnorada] = []
    tomados: set[str] = set()
    asignadas: set[int] = set()
    for indice, destino in fijadas.items():
        asignadas.add(indice)
        if destino == IGNORAR:
            ignoradas.append(ColumnaIgnorada(indice, encabezados[indice], "Ignorada en el mapeo indicado."))
        else:
            columnas.append(ColumnaMapeada(indice, encabezados[indice], destino, "manual", 1.0))
            tomados.add(destino)

    # Todas las parejas (columna, destino) posibles, la de mayor puntaje primero.
    parejas = []
    motivo_ignorada: dict[int, str] = {}
    mejor_campo: dict[int, str] = {}
    for indice, texto in enumerate(encabezados):
        if indice in asignadas or indice in vacias:
            continue
        for puntaje, alias in candidatos(texto):
            (motivo_ignorada if alias.ignorada else mejor_campo).setdefault(indice, alias.destino)
            parejas.append((puntaje, indice, alias))
    parejas.sort(key=lambda t: (-t[0], t[1]))
    mejor_puntaje: dict[int, float] = {}
    for puntaje, indice, _ in parejas:
        mejor_puntaje.setdefault(indice, puntaje)
    for puntaje, indice, alias in parejas:
        if indice in asignadas:
            continue
        # Si su mejor opción ya está tomada, una columna solo pasa a otra opción si esa
        # coincide exactamente; "Precio Venta" no debe terminar como "Activo" por "venta".
        if puntaje < mejor_puntaje[indice] and puntaje < UMBRAL_ENCABEZADO:
            continue
        if alias.ignorada:
            asignadas.add(indice)
            ignoradas.append(ColumnaIgnorada(indice, encabezados[indice], alias.destino))
        elif alias.destino not in tomados:
            asignadas.add(indice)
            tomados.add(alias.destino)
            exacto = _puntaje(normalizar(encabezados[indice]), alias.texto) >= UMBRAL_ENCABEZADO
            metodo = "alias" if exacto else "aproximado"
            columnas.append(ColumnaMapeada(indice, encabezados[indice], alias.destino, metodo, puntaje))

    for indice, texto in enumerate(encabezados):
        if indice in asignadas or indice in vacias:
            continue
        if indice in mejor_campo:
            ocupado = next(c for c in columnas if c.campo == mejor_campo[indice])
            motivo = (
                f"Parece ser {por_clave()[ocupado.campo].etiqueta}, pero ese campo ya lo toma "
                f"la columna {ocupado.letra} ('{ocupado.encabezado}')."
            )
        else:
            motivo = motivo_ignorada.get(indice, "No corresponde a ningún campo del inventario.")
        ignoradas.append(ColumnaIgnorada(indice, texto, motivo))

    columnas.sort(key=lambda c: c.indice)
    ignoradas.sort(key=lambda c: c.indice)
    return Mapeo(columnas, ignoradas)
