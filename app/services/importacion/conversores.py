"""Conversión de celdas a los tipos de la base, con motivos de error legibles.

Cada función recibe el valor tal como lo entrega openpyxl o el CSV (str, int, float,
datetime, bool o None) y devuelve el valor limpio, o lanza ``ValorInvalido`` con el
motivo exacto ("El valor 'N/A' no es un número válido.").
"""

import math
import re
from datetime import date, datetime, time
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.services.importacion.errores import ValorInvalido, mostrar_valor
from app.services.importacion.esquema import BOOLEANO, DECIMAL, ENTERO, Campo

ERRORES_EXCEL = {
    "#N/A", "#VALUE!", "#REF!", "#DIV/0!", "#NUM!", "#NAME?", "#NULL!", "#SPILL!", "#CALC!",
    "#GETTING_DATA", "#¡VALOR!", "#¡REF!", "#¡DIV/0!", "#¿NOMBRE?", "#¡NUM!", "#¡NULO!",
}
VERDADEROS = {"si", "sí", "s", "yes", "y", "true", "verdadero", "v", "1", "x", "activo", "ok"}
FALSOS = {"no", "n", "false", "falso", "f", "0", "inactivo"}
_MONEDA = re.compile(r"(?i)us\$|usd|\$|bs\.?\s*s?\.?|ves|cop|eur|€")
_NUMERO = re.compile(r"^[+-]?\d+(\.\d+)?$")


def es_vacio(valor: Any) -> bool:
    return valor is None or (isinstance(valor, str) and valor.strip() == "")


def _revisar_error_excel(valor: Any) -> None:
    if isinstance(valor, str) and valor.strip().upper() in ERRORES_EXCEL:
        raise ValorInvalido(
            f"La celda tiene un error de fórmula de Excel ({valor.strip()}); corrija la fórmula "
            "o escriba el valor."
        )


def a_texto(valor: Any, max_length: int | None) -> str:
    _revisar_error_excel(valor)
    if isinstance(valor, bool):
        valor = "Sí" if valor else "No"
    elif isinstance(valor, float) and valor.is_integer():
        valor = int(valor)  # SKU 1001 escrito como número: Excel lo entrega como 1001.0
    elif isinstance(valor, datetime) and valor.time() == time(0):
        valor = valor.date()
    if isinstance(valor, (date, datetime)):
        valor = valor.isoformat()
    texto = " ".join(str(valor).split())
    if max_length is not None and len(texto) > max_length:
        raise ValorInvalido(
            f"El texto tiene {len(texto)} caracteres y el máximo permitido es {max_length}."
        )
    return texto


def _normalizar_separadores(texto: str) -> str:
    """'1.234,56' y '1,234.56' -> '1234.56'; '12,5' -> '12.5' (coma decimal de Venezuela)."""
    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            return texto.replace(".", "").replace(",", ".")
        return texto.replace(",", "")
    if "," in texto:
        return texto.replace(",", ".") if texto.count(",") == 1 else texto.replace(",", "")
    if texto.count(".") > 1:
        return texto.replace(".", "")  # 1.234.567
    return texto


def _a_numero(valor: Any, permitir_pct: bool) -> Decimal:
    _revisar_error_excel(valor)
    original = valor
    if isinstance(valor, bool) or isinstance(valor, (date, datetime, time)):
        raise ValorInvalido(f"El valor '{mostrar_valor(original)}' no es un número válido.")
    if isinstance(valor, float):
        if math.isnan(valor) or math.isinf(valor):
            raise ValorInvalido("El valor no es un número válido.")
        return Decimal(str(valor))  # str evita arrastrar el error binario (0.1 -> 0.1000000000000000055)
    if isinstance(valor, (int, Decimal)):
        return Decimal(valor)
    texto = str(valor).strip().replace(" ", "").replace(" ", "").replace("'", "")
    texto = _MONEDA.sub("", texto)
    if permitir_pct:
        texto = texto.rstrip("%")
    if texto.startswith("(") and texto.endswith(")"):
        texto = "-" + texto[1:-1]  # (12.50) = negativo, formato contable
    texto = _normalizar_separadores(texto)
    if not _NUMERO.match(texto):
        raise ValorInvalido(f"El valor '{mostrar_valor(original)}' no es un número válido.")
    try:
        return Decimal(texto)
    except InvalidOperation as exc:  # pragma: no cover - la regex ya lo descarta
        raise ValorInvalido(f"El valor '{mostrar_valor(original)}' no es un número válido.") from exc


def _limites(numero: Decimal, campo: Campo) -> None:
    if campo.minimo is not None and numero < campo.minimo:
        raise ValorInvalido(
            "El valor no puede ser negativo." if campo.minimo == 0
            else f"El valor debe ser como mínimo {campo.minimo}."
        )
    if campo.maximo is not None and numero > campo.maximo:
        raise ValorInvalido(f"El valor {numero} supera el máximo permitido ({campo.maximo}).")


def a_decimal(valor: Any, campo: Campo) -> Decimal:
    numero = _a_numero(valor, permitir_pct=campo.clave == "margen_pct")
    if campo.decimales is not None:
        # Las fórmulas de Excel dejan 12.3456789; se redondea a centavos como en la caja.
        numero = numero.quantize(Decimal(1).scaleb(-campo.decimales), rounding=ROUND_HALF_UP)
    _limites(numero, campo)
    return numero


def a_entero(valor: Any, campo: Campo) -> int:
    numero = _a_numero(valor, permitir_pct=False)
    if numero != numero.to_integral_value():
        raise ValorInvalido(
            f"El valor '{mostrar_valor(valor)}' debe ser un número entero (sin decimales)."
        )
    _limites(numero, campo)
    return int(numero)


def a_booleano(valor: Any) -> bool:
    _revisar_error_excel(valor)
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, (int, float)) and valor in (0, 1):
        return bool(valor)
    texto = str(valor).strip().lower().rstrip(".")
    if texto in VERDADEROS:
        return True
    if texto in FALSOS:
        return False
    raise ValorInvalido(f"El valor '{mostrar_valor(valor)}' no es válido; use Sí o No.")


def convertir(valor: Any, campo: Campo) -> Any:
    """Valor limpio para el campo (las referencias se devuelven como texto)."""
    if campo.tipo == DECIMAL:
        return a_decimal(valor, campo)
    if campo.tipo == ENTERO:
        return a_entero(valor, campo)
    if campo.tipo == BOOLEANO:
        return a_booleano(valor)
    return a_texto(valor, campo.max_length)
