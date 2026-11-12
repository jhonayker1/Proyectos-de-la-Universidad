from typing import Literal

from pydantic import BaseModel


class CampoImportable(BaseModel):
    clave: str
    etiqueta: str
    tipo: str
    descripcion: str
    obligatorio_al_crear: bool
    columna_bd: str | None
    max_length: int | None
    decimales: int | None
    minimo: str | None
    maximo: str | None
    alias: list[str]
    ejemplo: str


class ArchivoLeido(BaseModel):
    nombre: str
    formato: Literal["xlsx", "csv"]
    hoja: str | None
    hojas: list[str]
    fila_encabezados: int
    codificacion: str | None = None
    separador: str | None = None


class ColumnaMapeada(BaseModel):
    letra: str
    columna: str
    campo: str
    etiqueta: str
    metodo: Literal["alias", "aproximado", "manual"]
    confianza: float


class ColumnaIgnorada(BaseModel):
    letra: str
    columna: str
    motivo: str


class IncidenciaRead(BaseModel):
    """Un problema de una fila: "Fila 14, Columna 'Precio Venta': El valor 'N/A' no es un número válido."."""

    fila: int | None
    columna: str | None
    letra: str | None
    campo: str | None
    valor: str | None
    motivo: str
    nivel: Literal["error", "advertencia"]
    mensaje: str


class CatalogoNuevo(BaseModel):
    nombre: str
    filas: int
    primera_fila: int | None
    prefijo_sku: str | None = None


class ResumenImportacion(BaseModel):
    filas_leidas: int
    filas_vacias_omitidas: int
    filas_validas: int
    filas_con_error: int
    total_errores: int
    total_advertencias: int
    a_crear: int
    a_actualizar: int
    a_omitir: int
    creados: int
    actualizados: int
    categorias_nuevas: list[CatalogoNuevo]
    marcas_nuevas: list[CatalogoNuevo]


class FilaPrevia(BaseModel):
    fila: int
    accion: Literal["crear", "actualizar", "omitir"]
    sku: str | None
    sku_automatico: bool
    nombre: str
    categoria: str | None


class ResultadoImportacion(BaseModel):
    estado: Literal["validado", "rechazado", "sin_cambios", "importado", "importado_parcial"]
    aplicado: bool
    mensaje: str
    modo: Literal["validar", "estricto", "parcial"]
    archivo: ArchivoLeido
    mapeo: list[ColumnaMapeada]
    columnas_ignoradas: list[ColumnaIgnorada]
    resumen: ResumenImportacion
    errores: list[IncidenciaRead]
    advertencias: list[IncidenciaRead]
    errores_truncados: bool
    advertencias_truncadas: bool
    vista_previa: list[FilaPrevia]
    # Si hubo errores o advertencias: GET /productos/importar/reportes/{reporte_id} (24 h).
    reporte_id: str | None = None


class ErrorImportacion(BaseModel):
    """El archivo no se pudo procesar (formato, encabezados, tamaño); no se guardó nada."""

    detail: str
    detalles: list[str] = []
