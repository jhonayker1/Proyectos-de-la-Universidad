"""Orquestación de la importación: validación en dos pasadas y escritura transaccional.

Pasada 1 (siempre, sin escribir nada):
  cada fila se convierte (tipos), se resuelven sus referencias (categoría, marca,
  proveedor) y se valida contra el archivo (SKU o producto repetido) y contra la base
  (SKU existente, producto con el mismo nombre). De cada fila válida solo se guarda el
  plan (crear / actualizar / omitir y su SKU), no sus datos: el archivo se vuelve a leer
  en la pasada 2. Al final se asignan los SKU automáticos, ya conociendo todos los SKU
  escritos en el archivo, para que nunca choquen.

Decisión según el modo:
  - ``validar``: devuelve el reporte; nada se guarda (vista previa).
  - ``estricto``: si hay al menos una fila con error, no se guarda nada.
  - ``parcial``: se guardan las filas válidas y se informan las demás.

Pasada 2 (escritura): una sola transacción; se escribe por lotes (flush cada
``TAMANO_LOTE`` filas, liberando memoria) y se confirma al final. Ante cualquier
fallo de la base se hace ROLLBACK completo: o entra todo lo planificado o nada.
"""

import logging
from contextlib import closing
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, BinaryIO, Literal

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.inventario import PRODUCTO_DISPONIBLE, PRODUCTO_INACTIVO, Producto
from app.services.importacion import catalogos as cat
from app.services.importacion.conversores import convertir, es_vacio
from app.services.importacion.errores import (
    ADVERTENCIA,
    ErrorDeArchivo,
    Incidencia,
    ValorInvalido,
    mostrar_valor,
)
from app.services.importacion.esquema import REFERENCIA, por_clave
from app.services.importacion.lector import Lector, Tabla, fila_vacia
from app.services.importacion.mapeo import Mapeo, mapear
from app.services.auditoria_service import establecer_origen, registrar
from app.services.precios_service import apply_margin_price
from app.services.sku_service import numeracion

logger = logging.getLogger(__name__)

TAMANO_LOTE = 500
MAX_INCIDENCIAS = 5000  # incidencias guardadas para el reporte Excel
MAX_FILAS_CON_ERROR = 5000  # filas originales que se devuelven para corregir
MAX_EN_JSON = 500  # errores (y advertencias) incluidos en la respuesta JSON
MAX_VISTA_PREVIA = 100

CREAR, ACTUALIZAR, OMITIR = "crear", "actualizar", "omitir"
_CAMPOS_DIRECTOS = (
    "nombre", "precio_distribuidor", "precio_usd", "margen_pct", "ubicacion",
    "stock_actual", "stock_minimo",
)


@dataclass
class Opciones:
    modo: Literal["validar", "estricto", "parcial"] = "validar"
    si_existe: Literal["actualizar", "omitir", "error"] = "actualizar"
    crear_faltantes: bool = False
    id_categoria_defecto: int | None = None
    hoja: str | None = None
    mapeo: dict[str, str] = field(default_factory=dict)
    max_filas: int = field(default_factory=lambda: settings.MAX_IMPORT_FILAS)


@dataclass(slots=True)
class Plan:
    accion: str
    sku: str | None  # None = se genera al terminar la pasada 1
    categoria: cat.Referencia | None
    nombre: str
    sku_automatico: bool = False


@dataclass(slots=True)
class _Existente:
    id: int
    nombre: str
    estado: str


@dataclass
class Resultado:
    nombre_archivo: str
    opciones: Opciones
    tabla: Tabla
    mapeo: Mapeo
    estado: str = "validado"
    aplicado: bool = False
    mensaje: str = ""
    filas_leidas: int = 0
    filas_vacias: int = 0
    filas_con_error: int = 0
    total_errores: int = 0
    total_advertencias: int = 0
    conteo: dict[str, int] = field(default_factory=lambda: {CREAR: 0, ACTUALIZAR: 0, OMITIR: 0})
    creados: int = 0
    actualizados: int = 0
    incidencias: list[Incidencia] = field(default_factory=list)
    filas_erroneas: list[tuple[int, list[Any], list[str]]] = field(default_factory=list)
    vista_previa: list[dict] = field(default_factory=list)
    categorias_nuevas: list[dict] = field(default_factory=list)
    marcas_nuevas: list[dict] = field(default_factory=list)

    @property
    def filas_validas(self) -> int:
        return self.filas_leidas - self.filas_con_error

    def errores(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.nivel != ADVERTENCIA]

    def advertencias(self) -> list[Incidencia]:
        return [i for i in self.incidencias if i.nivel == ADVERTENCIA]

    def resumen(self) -> dict:
        return {
            "filas_leidas": self.filas_leidas,
            "filas_vacias_omitidas": self.filas_vacias,
            "filas_validas": self.filas_validas,
            "filas_con_error": self.filas_con_error,
            "total_errores": self.total_errores,
            "total_advertencias": self.total_advertencias,
            "a_crear": self.conteo[CREAR],
            "a_actualizar": self.conteo[ACTUALIZAR],
            "a_omitir": self.conteo[OMITIR],
            "creados": self.creados,
            "actualizados": self.actualizados,
            "categorias_nuevas": self.categorias_nuevas,
            "marcas_nuevas": self.marcas_nuevas,
        }

    def como_dict(self) -> dict:
        errores, advertencias = self.errores(), self.advertencias()
        return {
            "estado": self.estado,
            "aplicado": self.aplicado,
            "mensaje": self.mensaje,
            "modo": self.opciones.modo,
            "archivo": {
                "nombre": self.nombre_archivo,
                "formato": self.tabla.formato,
                "hoja": self.tabla.hoja,
                "hojas": self.tabla.hojas,
                "fila_encabezados": self.tabla.fila_encabezados,
                **self.tabla.detalles_formato,
            },
            "mapeo": [c.como_dict() for c in self.mapeo.columnas],
            "columnas_ignoradas": [c.como_dict() for c in self.mapeo.ignoradas],
            "resumen": self.resumen(),
            "errores": [i.como_dict() for i in errores[:MAX_EN_JSON]],
            "advertencias": [i.como_dict() for i in advertencias[:MAX_EN_JSON]],
            "errores_truncados": self.total_errores > min(len(errores), MAX_EN_JSON),
            "advertencias_truncadas": self.total_advertencias > min(len(advertencias), MAX_EN_JSON),
            "vista_previa": self.vista_previa,
        }


class Importador:
    def __init__(self, db: Session, tabla: Tabla, mapeo: Mapeo, opciones: Opciones, nombre: str):
        self.db = db
        self.tabla = tabla
        self.mapeo = mapeo
        self.op = opciones
        self.r = Resultado(nombre, opciones, tabla, mapeo)
        self.catalogos = cat.cargar(db)
        self.categoria_defecto = self._categoria_defecto()
        self._revisar_columnas()
        self._cargar_existentes()
        self.planes: dict[int, Plan] = {}
        self.skus_archivo: dict[str, int] = {}  # SKU -> primera fila donde aparece
        self.claves_archivo: dict[tuple, tuple[int, bool]] = {}  # producto -> (fila, tenía SKU)

    # ------------------------------------------------------------ preparación
    def _categoria_defecto(self) -> cat.Referencia | None:
        if self.op.id_categoria_defecto is None:
            return None
        ref = self.catalogos["categoria"].buscar(str(self.op.id_categoria_defecto))
        if ref is None or ref.id != self.op.id_categoria_defecto:
            raise ErrorDeArchivo(f"La categoría por defecto ({self.op.id_categoria_defecto}) no existe.")
        if not ref.activo:
            raise ErrorDeArchivo(f"La categoría por defecto '{ref.nombre}' está desactivada.")
        return ref

    def _revisar_columnas(self) -> None:
        m = self.mapeo
        ayuda = [
            f"Columnas reconocidas: {', '.join(f'{c.encabezado} → {por_clave()[c.campo].etiqueta}' for c in m.columnas) or 'ninguna'}."
        ]
        if not m.tiene("sku") and not m.tiene("nombre"):
            raise ErrorDeArchivo(
                "Falta la columna del nombre del producto (o la del SKU, para actualizar "
                "productos existentes).",
                detalles=ayuda,
            )
        if m.tiene("nombre") and not m.tiene("sku") and not m.tiene("categoria") and self.categoria_defecto is None:
            raise ErrorDeArchivo(
                "Falta la columna Categoría. Agréguela o elija una categoría por defecto para "
                "todas las filas.",
                detalles=ayuda,
            )
        if not [c for c in m.columnas if c.campo != "sku"]:
            raise ErrorDeArchivo("El archivo solo trae la columna SKU; no hay datos para importar.", detalles=ayuda)

    def _cargar_existentes(self) -> None:
        """Una consulta para todo el inventario: SKU -> producto y nombre -> SKU."""
        self.existentes: dict[str, _Existente] = {}
        self.claves_bd: dict[tuple, tuple[str, str]] = {}
        filas = self.db.query(
            Producto.id_producto, Producto.sku, Producto.nombre, Producto.id_categoria,
            Producto.id_marca, Producto.estado,
        )
        for id_producto, sku, nombre, id_categoria, id_marca, estado in filas:
            self.existentes[sku.upper()] = _Existente(id_producto, nombre, estado)
            if estado != PRODUCTO_INACTIVO:
                clave = (cat.normalizar_nombre(nombre), ("id", id_categoria), ("id", id_marca) if id_marca else None)
                self.claves_bd.setdefault(clave, (sku, nombre))

    # ------------------------------------------------------------ incidencias
    def _anotar(self, incidencia: Incidencia) -> None:
        if incidencia.nivel == ADVERTENCIA:
            self.r.total_advertencias += 1
        else:
            self.r.total_errores += 1
        if len(self.r.incidencias) < MAX_INCIDENCIAS:
            self.r.incidencias.append(incidencia)

    def _incidencia(self, fila: int, campo: str | None, motivo: str, valor: Any = None, nivel: str = "error") -> Incidencia:
        col = self.mapeo.columna(campo) if campo else None
        return Incidencia(
            fila=fila, motivo=motivo, columna=col.encabezado if col else None,
            letra=col.letra if col else None, campo=campo, valor=mostrar_valor(valor), nivel=nivel,
        )

    # ------------------------------------------------------------ conversión
    def _convertir_fila(self, numero: int, valores: list[Any]) -> tuple[dict[str, Any], list[Incidencia]]:
        datos: dict[str, Any] = {}
        errores: list[Incidencia] = []
        for col in self.mapeo.columnas:
            crudo = valores[col.indice] if col.indice < len(valores) else None
            if es_vacio(crudo):
                continue  # celda vacía = no se informa (al actualizar, no cambia)
            campo = por_clave()[col.campo]
            try:
                valor = convertir(crudo, campo)
                if campo.tipo == REFERENCIA:
                    valor = self.catalogos[campo.clave].resolver(valor, numero, crear=self.op.crear_faltantes)
                elif campo.clave == "sku":
                    valor = valor.upper()
                    if "~" in valor:
                        raise ValorInvalido("El SKU no puede contener '~' (se reserva para productos eliminados).")
                datos[campo.clave] = valor
            except ValorInvalido as exc:
                errores.append(Incidencia(
                    numero, exc.motivo, col.encabezado, col.letra, campo.clave, mostrar_valor(crudo)
                ))
        return datos, errores

    # ------------------------------------------------------------ pasada 1
    def _planificar(self, numero: int, datos: dict[str, Any]) -> tuple[Plan | None, list[Incidencia]]:
        avisos: list[Incidencia] = []
        sku = datos.get("sku")
        existente = self.existentes.get(sku) if sku else None

        if existente is not None:
            if self.op.si_existe == "error":
                return None, [self._incidencia(
                    numero, "sku", f"El SKU {sku} ya existe en el inventario ({existente.nombre}).", sku
                )]
            if self.op.si_existe == "omitir":
                avisos.append(self._incidencia(
                    numero, "sku", f"El SKU {sku} ya existe ({existente.nombre}); la fila se omite.",
                    sku, ADVERTENCIA,
                ))
                return Plan(OMITIR, sku, None, existente.nombre), avisos
            if len(datos) == 1:
                avisos.append(self._incidencia(
                    numero, None, "La fila solo trae el SKU; no hay datos que actualizar.", nivel=ADVERTENCIA
                ))
                return Plan(OMITIR, sku, None, existente.nombre), avisos
            if existente.estado == PRODUCTO_INACTIVO and "activo" not in datos:
                avisos.append(self._incidencia(
                    numero, "sku", f"El producto {sku} está inactivo (oculto); se actualiza pero "
                    "sigue oculto. Agregue la columna Activo = Sí para reactivarlo.", sku, ADVERTENCIA,
                ))
            plan = Plan(ACTUALIZAR, sku, datos.get("categoria"), datos.get("nombre", existente.nombre))
        else:
            errores: list[Incidencia] = []
            nombre = datos.get("nombre")
            categoria = datos.get("categoria") or self.categoria_defecto
            if not nombre:
                motivo = "El nombre es obligatorio para crear un producto nuevo."
                if sku:
                    motivo = f"El SKU {sku} no existe, así que la fila crearía un producto nuevo y le falta el nombre."
                errores.append(self._incidencia(numero, "nombre", motivo))
            if categoria is None:
                errores.append(self._incidencia(numero, "categoria", "La categoría es obligatoria para crear un producto nuevo."))
            if errores:
                return None, errores
            marca = datos.get("marca")
            clave = (cat.normalizar_nombre(nombre), categoria.clave, marca.clave if marca else None)
            en_bd = self.claves_bd.get(clave)
            if en_bd is not None:
                motivo = (f"Ya existe '{en_bd[1]}' (SKU {en_bd[0]}) con el mismo nombre, categoría y marca.")
                if not sku:
                    return None, [self._incidencia(
                        numero, "nombre", motivo + " Escriba su SKU en la fila para actualizarlo, o cambie el nombre.", nombre
                    )]
                avisos.append(self._incidencia(numero, "nombre", motivo + " Se creará otro producto con el SKU indicado.", nombre, ADVERTENCIA))
            previo = self.claves_archivo.get(clave)
            if previo is not None:
                if not sku and not previo[1]:
                    return None, [self._incidencia(
                        numero, "nombre", f"Producto repetido en el archivo: la fila {previo[0]} tiene el "
                        "mismo nombre, categoría y marca.", nombre,
                    )]
                avisos.append(self._incidencia(
                    numero, "nombre", f"La fila {previo[0]} tiene el mismo nombre, categoría y marca (con otro SKU).",
                    nombre, ADVERTENCIA,
                ))
            else:
                self.claves_archivo[clave] = (numero, bool(sku))
            plan = Plan(CREAR, sku, categoria, nombre)
            if "precio_usd" not in datos:
                margen = datos.get("margen_pct", categoria.margen)
                if not margen:
                    avisos.append(self._incidencia(
                        numero, "precio_usd", "Sin precio de venta y sin margen de ganancia: el precio de "
                        "venta quedará igual al costo.", nivel=ADVERTENCIA,
                    ))

        costo, venta = datos.get("precio_distribuidor"), datos.get("precio_usd")
        if costo is not None and venta is not None and venta < costo:
            avisos.append(self._incidencia(
                numero, "precio_usd", f"El precio de venta ({venta}) es menor que el costo ({costo}).",
                venta, ADVERTENCIA,
            ))
        margen = datos.get("margen_pct")
        if margen is not None and margen >= 100:
            avisos.append(self._incidencia(
                numero, "margen_pct", f"Un margen de {margen} % representa una cantidad "
                "desproporcionada; verifique.", margen, ADVERTENCIA,
            ))
        return plan, avisos

    def validar(self) -> None:
        r = self.r
        with closing(self.tabla.filas()) as filas:
            for numero, valores in filas:
                if fila_vacia(valores):
                    r.filas_vacias += 1
                    continue
                r.filas_leidas += 1
                if r.filas_leidas > self.op.max_filas:
                    raise ErrorDeArchivo(
                        f"El archivo tiene más de {self.op.max_filas} filas de datos. Divídalo en "
                        "varios archivos.",
                        status_code=413,
                    )
                datos, errores = self._convertir_fila(numero, valores)
                sku = datos.get("sku")
                if sku:
                    primera = self.skus_archivo.setdefault(sku, numero)
                    if primera != numero:
                        errores.append(self._incidencia(
                            numero, "sku", f"El SKU {sku} está repetido en el archivo (ya aparece en "
                            f"la fila {primera}).", sku,
                        ))
                plan = None
                if not errores:
                    plan, incidencias = self._planificar(numero, datos)
                    errores = [i for i in incidencias if i.nivel != ADVERTENCIA]
                    for aviso in (i for i in incidencias if i.nivel == ADVERTENCIA):
                        self._anotar(aviso)
                if errores or plan is None:
                    r.filas_con_error += 1
                    for e in errores:
                        self._anotar(e)
                    if len(r.filas_erroneas) < MAX_FILAS_CON_ERROR:
                        r.filas_erroneas.append((numero, valores, [e.motivo for e in errores]))
                    continue
                self.planes[numero] = plan
                r.conteo[plan.accion] += 1
                if plan.accion != OMITIR:
                    for ref in (plan.categoria, datos.get("marca")):
                        if ref is not None:
                            ref.filas += 1
        if r.filas_leidas == 0:
            raise ErrorDeArchivo(
                f"El archivo no tiene filas de datos debajo de los encabezados (fila {self.tabla.fila_encabezados})."
            )
        self._asignar_skus()

    def _asignar_skus(self) -> None:
        """SKU automático para las filas nuevas sin SKU, siguiendo la numeración de su
        categoría y saltando todo SKU existente o escrito en el archivo."""
        cat.planificar_prefijos(self.db, self.catalogos["categoria"])
        tomados = set(self.existentes) | set(self.skus_archivo)
        secuencias: dict[tuple, list[int]] = {}
        for plan in self.planes.values():
            if plan.accion != CREAR or plan.sku is not None:
                continue
            ref = plan.categoria
            prefijo = ref.prefijo_sku
            if ref.clave not in secuencias:
                secuencias[ref.clave] = list(numeracion(self.db, prefijo))
            secuencia = secuencias[ref.clave]
            ancho = secuencia[1]
            siguiente = secuencia[0] + 1
            while f"{prefijo}-{siguiente:0{ancho}d}" in tomados:
                siguiente += 1
            secuencia[0] = siguiente
            plan.sku = f"{prefijo}-{siguiente:0{ancho}d}"
            plan.sku_automatico = True
            tomados.add(plan.sku)
        self.r.vista_previa = [
            {
                "fila": fila, "accion": p.accion, "sku": p.sku, "sku_automatico": p.sku_automatico,
                "nombre": p.nombre, "categoria": p.categoria.nombre if p.categoria else None,
            }
            for fila, p in list(self.planes.items())[:MAX_VISTA_PREVIA]
        ]
        c = self.catalogos
        self.r.categorias_nuevas = [
            {"nombre": ref.nombre, "prefijo_sku": ref.prefijo_sku, "filas": ref.filas, "primera_fila": ref.primera_fila}
            for ref in c["categoria"].nuevas()
        ]
        self.r.marcas_nuevas = [
            {"nombre": ref.nombre, "filas": ref.filas, "primera_fila": ref.primera_fila}
            for ref in c["marca"].nuevas()
        ]

    # ------------------------------------------------------------ pasada 2
    def escribir(self) -> None:
        cat.crear_pendientes(self.db, self.catalogos)
        cat.guardar_prefijos(self.db, self.catalogos["categoria"])
        lote: list[tuple[Plan, dict[str, Any]]] = []
        with closing(self.tabla.filas()) as filas:
            for numero, valores in filas:
                plan = self.planes.get(numero)
                if plan is None or plan.accion == OMITIR:
                    continue
                datos, errores = self._convertir_fila(numero, valores)
                if errores:  # el archivo es el mismo: solo pasaría si cambió entre pasadas
                    raise ErrorDeArchivo(f"La fila {numero} cambió durante la importación; no se guardó nada.", 409)
                lote.append((plan, datos))
                if len(lote) >= TAMANO_LOTE:
                    self._escribir_lote(lote)
                    lote = []
        if lote:
            self._escribir_lote(lote)

    def _escribir_lote(self, lote: list[tuple[Plan, dict[str, Any]]]) -> None:
        skus = [p.sku for p, _ in lote if p.accion == ACTUALIZAR]
        actuales = (
            {p.sku.upper(): p for p in self.db.query(Producto).filter(Producto.sku.in_(skus))}
            if skus else {}
        )
        for plan, datos in lote:
            if plan.accion == CREAR:
                producto = Producto(
                    sku=plan.sku,
                    id_categoria=plan.categoria.id,
                    precio_distribuidor=datos.get("precio_distribuidor", Decimal("0")),
                    stock_actual=datos.get("stock_actual", 0),
                    stock_minimo=datos.get("stock_minimo", 5),
                    estado=PRODUCTO_INACTIVO if datos.get("activo") is False else PRODUCTO_DISPONIBLE,
                )
                for clave in _CAMPOS_DIRECTOS:
                    if clave in datos:
                        setattr(producto, clave, datos[clave])
                self._referencias(producto, datos)
                self.db.add(producto)
                if producto.precio_usd is None:
                    apply_margin_price(self.db, producto)
                self.r.creados += 1
            else:
                producto = actuales.get(plan.sku)
                if producto is None:
                    raise ErrorDeArchivo(
                        f"El producto {plan.sku} fue eliminado mientras se importaba; no se guardó nada.", 409
                    )
                for clave in _CAMPOS_DIRECTOS:
                    if clave in datos:
                        setattr(producto, clave, datos[clave])
                self._referencias(producto, datos)
                if "precio_usd" not in datos and datos.keys() & {"precio_distribuidor", "margen_pct", "categoria"}:
                    apply_margin_price(self.db, producto)
                if "activo" in datos:
                    if not datos["activo"]:
                        producto.estado = PRODUCTO_INACTIVO
                    elif producto.estado == PRODUCTO_INACTIVO:
                        producto.estado = PRODUCTO_DISPONIBLE
                self.r.actualizados += 1
            producto.sync_stock_status()
        self.db.flush()
        # Lo ya enviado a la base no hace falta en memoria; la transacción sigue abierta.
        self.db.expunge_all()

    @staticmethod
    def _referencias(producto: Producto, datos: dict[str, Any]) -> None:
        for clave, columna in (("categoria", "id_categoria"), ("marca", "id_marca"), ("proveedor", "id_proveedor")):
            if clave in datos:
                setattr(producto, columna, datos[clave].id)


def _n(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def _mensaje(r: Resultado) -> str:
    listas = f"{_n(r.conteo[CREAR], 'nueva', 'nuevas')}, {r.conteo[ACTUALIZAR]} a actualizar"
    if r.conteo[OMITIR]:
        listas += f", {_n(r.conteo[OMITIR], 'omitida', 'omitidas')}"
    if r.estado == "validado":
        return (f"Validación terminada: {_n(r.filas_leidas, 'fila', 'filas')}, {r.filas_validas} "
                f"correcta{'' if r.filas_validas == 1 else 's'} ({listas}) y {r.filas_con_error} con "
                "errores. Todavía no se guardó nada.")
    if r.estado == "rechazado":
        if r.opciones.modo == "estricto":
            return (f"Importación rechazada: {_n(r.filas_con_error, 'fila', 'filas')} con errores. En modo "
                    "estricto no se guarda nada si alguna fila falla; corríjalas o use el modo parcial.")
        return "No se importó nada: ninguna fila es válida."
    if r.estado == "sin_cambios":
        return "No hay cambios que guardar: todas las filas se omitieron."
    total = r.creados + r.actualizados
    texto = (f"Se {'importó' if total == 1 else 'importaron'} {_n(total, 'producto', 'productos')} "
             f"({_n(r.creados, 'nuevo', 'nuevos')}, {_n(r.actualizados, 'actualizado', 'actualizados')}).")
    if r.filas_con_error:
        texto += f" Se {'omitió' if r.filas_con_error == 1 else 'omitieron'} {_n(r.filas_con_error, 'fila', 'filas')} con errores."
    return texto


def importar(
    db: Session,
    archivo: BinaryIO,
    nombre_archivo: str | None,
    opciones: Opciones,
    id_usuario: int | None = None,
) -> Resultado:
    """Punto de entrada. Lanza ErrorDeArchivo si el archivo no se puede procesar; los
    problemas de cada fila van en el Resultado."""
    nombre = nombre_archivo or "archivo"
    with Lector(archivo, nombre, opciones.hoja) as lector:
        tabla = lector.abrir()
        mapeo = mapear(tabla.encabezados, opciones.mapeo)
        imp = Importador(db, tabla, mapeo, opciones, nombre)
        r = imp.r
        try:
            imp.validar()
            pendientes = r.conteo[CREAR] + r.conteo[ACTUALIZAR]
            if opciones.modo == "validar":
                r.estado = "validado"
            elif r.filas_con_error and (opciones.modo == "estricto" or pendientes == 0):
                r.estado = "rechazado"
            elif pendientes == 0:
                r.estado = "sin_cambios"
            else:
                establecer_origen(db, f"Importación masiva: {nombre} (modo {opciones.modo})")
                imp.escribir()
                registrar(
                    db, "importacion", "importar", "archivo",
                    f"Importación de {nombre}: {r.creados} producto(s) nuevo(s) y {r.actualizados} "
                    f"actualizado(s); {r.filas_con_error} fila(s) con errores no se importaron.",
                    referencia=nombre[:200],
                    cambios=[
                        {"campo": clave, "etiqueta": etiqueta, "antes": None, "despues": str(valor)}
                        for clave, etiqueta, valor in (
                            ("modo", "Modo", opciones.modo),
                            ("filas_leidas", "Filas leídas", r.filas_leidas),
                            ("creados", "Productos nuevos", r.creados),
                            ("actualizados", "Productos actualizados", r.actualizados),
                            ("filas_con_error", "Filas con errores", r.filas_con_error),
                        )
                    ],
                )
                db.commit()
                r.aplicado = True
                r.estado = "importado_parcial" if r.filas_con_error else "importado"
        except ErrorDeArchivo:
            db.rollback()
            raise
        except IntegrityError as exc:
            db.rollback()
            logger.warning("Importación rechazada por la base: %s", exc.orig)
            raise ErrorDeArchivo(
                "La base de datos rechazó la importación por un dato repetido (otro usuario pudo "
                "crear el mismo SKU mientras se importaba). No se guardó ningún cambio; vuelva a intentarlo.",
                status_code=409,
            ) from exc
        except SQLAlchemyError as exc:
            db.rollback()
            logger.exception("Error de base de datos durante la importación")
            raise ErrorDeArchivo(
                "No se pudo completar la importación por un error de la base de datos. No se "
                "guardó ningún cambio.",
                status_code=503,
            ) from exc
        finally:
            if not r.aplicado:
                db.rollback()  # la validación no deja nada pendiente en la sesión
    r.mensaje = _mensaje(r)
    logger.info(
        "Importación de inventario (usuario %s, archivo %s, modo %s): %s",
        id_usuario, nombre, opciones.modo, r.estado,
    )
    return r
