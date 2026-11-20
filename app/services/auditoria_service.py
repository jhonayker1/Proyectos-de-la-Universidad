"""Auditoría automática: quién cambió qué, cuándo y desde dónde.

Funciona con eventos del ORM, así que ningún endpoint puede "olvidarse" de auditar:

- ``after_flush``: por cada objeto vigilado (productos, catálogos, proveedores,
  usuarios, tasas, ventas, compras, facturas) que se crea, modifica o elimina, se
  calcula la diferencia campo por campo y se guarda como pendiente en la sesión.
  Varios flush de una misma transacción se combinan: la venta que se crea con un
  número temporal y luego recibe F-00000012 queda como un solo registro "creada".
- ``before_commit``: se escriben los pendientes en la tabla ``auditoria`` dentro de la
  MISMA transacción: si el cambio se confirma, su registro también; si se deshace
  (ROLLBACK), no queda registro de algo que no ocurrió.

Quién y desde dónde lo pone ``establecer_contexto`` (lo llama la autenticación en cada
petición). Las contraseñas nunca se guardan, ni siquiera su hash.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import Numeric, event, inspect, insert, select
from sqlalchemy.orm import Session

from app.core.dates import local_now
from app.models.auditoria import Auditoria
from app.models.compras import Compra, FacturaImagen
from app.models.finanzas import Moneda, TasaCambio
from app.models.inventario import PRODUCTO_INACTIVO, Categoria, Marca, Producto, Proveedor
from app.models.usuarios import Rol, Usuario
from app.models.ventas import VENTA_ANULADA, Venta

MODULOS = {
    "inventario": "Inventario",
    "categorias": "Categorías",
    "marcas": "Marcas",
    "proveedores": "Proveedores",
    "usuarios": "Usuarios",
    "tasas": "Tasas de cambio",
    "ventas": "Ventas",
    "compras": "Compras",
    "facturas": "Facturas",
    "importacion": "Importación",
    "auditoria": "Auditoría",
}
ACCIONES = {
    "crear": "Crear",
    "modificar": "Modificar",
    "eliminar": "Eliminar",
    "desactivar": "Desactivar",
    "reactivar": "Reactivar",
    "stock": "Movimiento de stock",
    "contrasena": "Cambio de contraseña",
    "anular": "Anular",
    "pago": "Cambio de pago",
    "importar": "Importar",
    "exportar": "Exportar",
}
ROLES = {"admin": "Administrador", "cashier": "Cajero"}
SISTEMA = "Sistema"
OCULTO = "(oculta)"

_PENDIENTES = "auditoria_pendientes"
_MANUALES = "auditoria_manuales"
_CONTEXTO = "auditoria_contexto"
_MAX_RESUMEN = 4  # cambios que se nombran en la descripción; el detalle los trae todos


# --------------------------------------------------------------------- qué se vigila


@dataclass(frozen=True)
class Seguimiento:
    modulo: str
    entidad: str
    femenino: bool
    etiquetas: dict[str, str]  # solo estos campos se auditan
    referencia: Callable[[dict[str, Any], str], str]
    # Campo -> (pk, columna con el nombre) para mostrar "Filtros" en vez de "3".
    nombres: dict[str, tuple[Any, Any]] = field(default_factory=dict)
    banderas: dict[str, tuple[str, str]] = field(default_factory=dict)  # 1 / 0
    secretos: frozenset[str] = frozenset()
    texto_crear: Callable[[dict[str, Any], str], str] | None = None

    @property
    def articulo(self) -> str:
        return "La" if self.femenino else "El"

    def participio(self, raiz: str) -> str:
        return raiz + ("a" if self.femenino else "o")


def _sku_visible(sku: Any) -> str:
    # Los productos eliminados con historial guardan su SKU como "LUB-28~12".
    return str(sku or "").split("~")[0]


ACTIVO = ("Activo", "Inactivo")
SEGUIMIENTOS: dict[type, Seguimiento] = {
    Producto: Seguimiento(
        "inventario", "producto", False,
        {
            "sku": "SKU", "nombre": "Nombre", "id_categoria": "Categoría", "id_marca": "Marca",
            "id_proveedor": "Proveedor", "precio_distribuidor": "Costo USD",
            "precio_usd": "Precio venta USD", "margen_pct": "Margen %", "stock_actual": "Stock",
            "stock_minimo": "Stock mínimo", "ubicacion": "Ubicación", "estado": "Estado",
        },
        lambda v, _: f"{_sku_visible(v.get('sku'))} · {v.get('nombre')}",
        nombres={
            "id_categoria": (Categoria.id_categoria, Categoria.nombre),
            "id_marca": (Marca.id_marca, Marca.nombre),
            "id_proveedor": (Proveedor.id_proveedor, Proveedor.nombre),
        },
    ),
    Categoria: Seguimiento(
        "categorias", "categoría", True,
        {"nombre": "Nombre", "descripcion": "Descripción", "margen_ganancia": "Margen de ganancia %",
         "prefijo_sku": "Código SKU", "estado": "Estado"},
        lambda v, _: str(v.get("nombre")),
        banderas={"estado": ("Activa", "Inactiva")},
    ),
    Marca: Seguimiento(
        "marcas", "marca", True,
        {"nombre": "Nombre", "pais_origen": "País de origen", "estado": "Estado"},
        lambda v, _: str(v.get("nombre")),
        banderas={"estado": ("Activa", "Inactiva")},
    ),
    Proveedor: Seguimiento(
        "proveedores", "proveedor", False,
        {"nombre": "Nombre", "rif": "RIF", "telefono": "Teléfono", "correo": "Correo",
         "contacto": "Contacto", "ciudad": "Ciudad", "condiciones": "Condiciones", "estado": "Estado"},
        lambda v, _: str(v.get("nombre")),
        banderas={"estado": ACTIVO},
    ),
    Usuario: Seguimiento(
        "usuarios", "usuario", False,
        {"nombre_completo": "Nombre", "correo": "Correo", "telefono": "Teléfono", "id_rol": "Rol",
         "permisos": "Permisos", "estado": "Estado", "password_hash": "Contraseña"},
        lambda v, _: f"{v.get('nombre_completo')} ({v.get('correo')})",
        nombres={"id_rol": (Rol.id_rol, Rol.nombre)},
        banderas={"estado": ACTIVO},
        secretos=frozenset({"password_hash"}),
    ),
    TasaCambio: Seguimiento(
        "tasas", "tasa de cambio", True,
        {"id_moneda": "Moneda", "tasa_venta": "Tasa de venta", "tasa_compra": "Tasa de compra",
         "estado": "Vigente"},
        lambda v, _: str(v.get("id_moneda")),
        nombres={"id_moneda": (Moneda.id_moneda, Moneda.codigo)},
        banderas={"estado": ("Sí", "No")},
        texto_crear=lambda v, _: f"Nueva tasa de cambio {v.get('id_moneda')}: {v.get('tasa_venta')} por USD.",
    ),
    Venta: Seguimiento(
        "ventas", "venta", True,
        {"numero_factura": "Factura", "id_usuario": "Vendedor", "id_moneda_pago": "Moneda de pago",
         "monto_total_usd": "Total USD", "monto_total_moneda": "Total en moneda de pago",
         "tasa_aplicada": "Tasa aplicada", "referencia_pago": "Referencia de pago", "estado": "Estado"},
        lambda v, _: str(v.get("numero_factura")),
        nombres={"id_usuario": (Usuario.id_usuario, Usuario.nombre_completo),
                 "id_moneda_pago": (Moneda.id_moneda, Moneda.codigo)},
        texto_crear=lambda v, _: (
            f"Venta {v.get('numero_factura')} registrada por {v.get('id_usuario')}: "
            f"{v.get('monto_total_usd')} USD, pagada en {v.get('id_moneda_pago')}."
        ),
    ),
    Compra: Seguimiento(
        "compras", "compra", True,
        {"id_proveedor": "Proveedor", "numero_factura": "Factura", "fecha": "Fecha",
         "descripcion": "Descripción", "monto_usd": "Monto USD", "pagado": "Pagada"},
        lambda v, i: f"#{i} · {v.get('id_proveedor')}" + (f" · factura {v['numero_factura']}" if v.get("numero_factura") else ""),
        nombres={"id_proveedor": (Proveedor.id_proveedor, Proveedor.nombre)},
        banderas={"pagado": ("Sí", "No")},
        texto_crear=lambda v, i: f"Compra #{i} a {v.get('id_proveedor')} registrada: {v.get('monto_usd')} USD.",
    ),
    FacturaImagen: Seguimiento(
        "facturas", "factura escaneada", True,
        {"nombre_original": "Archivo", "tipo_mime": "Tipo", "tamano_bytes": "Tamaño (bytes)",
         "id_compra": "Compra"},
        lambda v, _: str(v.get("nombre_original")),
    ),
}


# --------------------------------------------------------------------- contexto


def establecer_contexto(db: Session, usuario: Usuario | None = None, request: Any = None,
                        origen: str | None = None) -> None:
    """Quién hace los cambios de esta sesión y desde dónde. Una petición = una operación."""
    db.info[_CONTEXTO] = {
        "usuario": (usuario.id_usuario, usuario.nombre_completo, ROLES.get(usuario.rol or "", usuario.rol))
        if usuario is not None else None,
        "ip": request.client.host if request is not None and request.client else None,
        "ruta": f"{request.method} {request.url.path}"[:200] if request is not None else None,
        "origen": origen,
        "operacion": uuid4().hex,
    }


def establecer_origen(db: Session, origen: str) -> None:
    """Motivo de negocio de los cambios (p. ej. "Venta en punto de venta")."""
    db.info.setdefault(_CONTEXTO, {"operacion": uuid4().hex})["origen"] = origen[:200]


def registrar(db: Session, modulo: str, accion: str, entidad: str, descripcion: str,
              referencia: str | None = None, id_registro: Any = None,
              cambios: list[dict] | None = None) -> None:
    """Evento que no es un cambio de una fila (una importación, una exportación). Se
    escribe con el próximo commit de la sesión, junto con el resto."""
    db.info.setdefault(_MANUALES, []).append({
        "modulo": modulo, "accion": accion, "entidad": entidad, "descripcion": descripcion,
        "referencia": referencia, "id_registro": None if id_registro is None else str(id_registro),
        "cambios": cambios,
    })


# --------------------------------------------------------------------- captura


@dataclass
class _Pendiente:
    seg: Seguimiento
    id_registro: str
    tipo: str  # crear | modificar | eliminar
    actuales: dict[str, Any]
    cambios: dict[str, list[Any]] = field(default_factory=dict)  # campo -> [antes, después]
    articulos: list[tuple[Any, int]] = field(default_factory=list)  # ventas/compras


def _como_en_la_base(columna: Any, valor: Any) -> Any:
    """El valor como lo guarda la columna: 30 en un numeric(10,2) es 30.00."""
    tipo = getattr(columna, "type", None)
    if valor is not None and isinstance(tipo, Numeric) and tipo.scale is not None:
        try:
            return Decimal(str(valor)).quantize(Decimal(1).scaleb(-tipo.scale))
        except (ArithmeticError, ValueError):
            return valor
    return valor


def _iguales(a: Any, b: Any) -> bool:
    try:
        return a == b or (a is not None and b is not None and Decimal(str(a)) == Decimal(str(b)))
    except Exception:  # noqa: BLE001 - valores no numéricos distintos
        return False


def _articulos(obj: Any) -> list[tuple[Any, int]]:
    detalles = inspect(obj).attrs.detalles.loaded_value if hasattr(obj, "detalles") else None
    if not isinstance(detalles, list):
        return []
    if isinstance(obj, Venta):
        return [(d.nombre_producto_snapshot, d.cantidad) for d in detalles]
    return [(("producto", d.id_producto), d.cantidad) for d in detalles]


def _capturar(session: Session, obj: Any, tipo: str) -> None:
    seg = SEGUIMIENTOS.get(type(obj))
    if seg is None:
        return
    estado = inspect(obj)
    columnas = estado.mapper.columns
    actuales = {c: _como_en_la_base(columnas.get(c), estado.dict.get(c)) for c in seg.etiquetas}
    pk = estado.mapper.primary_key_from_instance(obj)
    if any(v is None for v in pk):
        return
    clave = (estado.mapper.local_table.name, tuple(pk))
    pendientes: dict = session.info.setdefault(_PENDIENTES, {})
    previo: _Pendiente | None = pendientes.get(clave)
    id_registro = "-".join(str(v) for v in pk)

    if tipo == "crear":
        pendientes[clave] = _Pendiente(seg, id_registro, "crear", actuales, articulos=_articulos(obj))
        return
    if tipo == "eliminar":
        if previo is not None and previo.tipo == "crear":
            del pendientes[clave]  # creado y borrado en la misma transacción: no ocurrió
            return
        pendientes[clave] = _Pendiente(seg, id_registro, "eliminar", previo.actuales if previo else actuales)
        return

    cambios = {}
    for campo in seg.etiquetas:
        historia = estado.attrs[campo].history
        if not historia.has_changes():
            continue
        antes = _como_en_la_base(columnas.get(campo), historia.deleted[0] if historia.deleted else None)
        despues = _como_en_la_base(columnas.get(campo), historia.added[0] if historia.added else None)
        if not _iguales(antes, despues):
            cambios[campo] = [antes, despues]
    if not cambios:
        return
    if previo is None:
        pendientes[clave] = _Pendiente(seg, id_registro, "modificar", actuales, cambios)
    elif previo.tipo == "crear":
        previo.actuales = actuales  # p. ej. el número definitivo de la venta recién creada
        previo.articulos = previo.articulos or _articulos(obj)
    else:
        for campo, (antes, despues) in cambios.items():
            if campo in previo.cambios:
                previo.cambios[campo][1] = despues
            else:
                previo.cambios[campo] = [antes, despues]
        previo.cambios = {c: v for c, v in previo.cambios.items() if not _iguales(*v)}
        previo.actuales = actuales
        if not previo.cambios:
            del pendientes[clave]


def _despues_del_flush(session: Session, _contexto) -> None:
    for obj in list(session.new):
        _capturar(session, obj, "crear")
    for obj in list(session.dirty):
        _capturar(session, obj, "modificar")
    for obj in list(session.deleted):
        _capturar(session, obj, "eliminar")


# --------------------------------------------------------------------- escritura


def _texto(valor: Any) -> str | None:
    if valor is None or valor == "":
        return None
    if isinstance(valor, bool):
        return "Sí" if valor else "No"
    if isinstance(valor, (datetime, date)):
        return valor.isoformat(sep=" ", timespec="minutes") if isinstance(valor, datetime) else valor.isoformat()
    return str(valor)


class _Nombres:
    """Resuelve en lote los IDs de llaves foráneas a nombres (una consulta por tabla)."""

    def __init__(self, session: Session, pendientes: list[_Pendiente]):
        pedidos: dict[tuple, set] = {}
        for p in pendientes:
            for campo, (pk, columna) in p.seg.nombres.items():
                valores = [p.actuales.get(campo), *p.cambios.get(campo, [])]
                pedidos.setdefault((pk, columna), set()).update(v for v in valores if v is not None)
            for producto, _ in p.articulos:
                if isinstance(producto, tuple):
                    pedidos.setdefault((Producto.id_producto, Producto.nombre), set()).add(producto[1])
        conexion = session.connection()
        self.mapa: dict[tuple, dict] = {}
        for (pk, columna), ids in pedidos.items():
            filas = {}
            lista = list(ids)
            for i in range(0, len(lista), 1000):
                filas.update(conexion.execute(select(pk, columna).where(pk.in_(lista[i:i + 1000]))).all())
            self.mapa[(pk, columna)] = filas

    def mostrar(self, seg: Seguimiento, campo: str, valor: Any) -> str | None:
        if valor is None:
            return None
        if campo in seg.secretos:
            return OCULTO
        if campo in seg.nombres:
            return str(self.mapa.get(seg.nombres[campo], {}).get(valor, f"#{valor}"))
        if campo in seg.banderas:
            return seg.banderas[campo][0 if valor in (1, True) else 1]
        if campo == "sku":
            return _sku_visible(valor)
        return _texto(valor)

    def producto(self, id_producto: int) -> str:
        return str(self.mapa.get((Producto.id_producto, Producto.nombre), {}).get(id_producto, f"#{id_producto}"))


def _accion(p: _Pendiente) -> str:
    if p.tipo != "modificar":
        return p.tipo
    campos = set(p.cambios)
    if campos <= p.seg.secretos:
        return "contrasena"
    estado = p.cambios.get("estado")
    if p.seg.modulo == "inventario":
        if estado and estado[1] == PRODUCTO_INACTIVO:
            return "eliminar" if "~" in str(p.actuales.get("sku")) else "desactivar"
        if estado and estado[0] == PRODUCTO_INACTIVO:
            return "reactivar"
        if campos <= {"stock_actual", "estado"}:
            return "stock"
    if p.seg.modulo == "ventas" and estado and estado[1] == VENTA_ANULADA:
        return "anular"
    if p.seg.modulo == "compras" and campos == {"pagado"}:
        return "pago"
    if estado is not None and "estado" in p.seg.banderas and campos <= {"estado"}:
        return "desactivar" if estado[1] == 0 else "reactivar"
    return "modificar"


def _fila(p: _Pendiente, nombres: _Nombres) -> dict[str, Any]:
    seg = p.seg
    visibles = {c: nombres.mostrar(seg, c, v) for c, v in p.actuales.items()}
    referencia = seg.referencia(visibles, p.id_registro)
    accion = _accion(p)
    cambios: list[dict] = []
    if p.tipo == "modificar":
        for campo, (antes, despues) in p.cambios.items():
            cambios.append({
                "campo": campo, "etiqueta": seg.etiquetas[campo],
                "antes": nombres.mostrar(seg, campo, antes),
                "despues": "(cambiada)" if campo in seg.secretos else nombres.mostrar(seg, campo, despues),
            })
    else:
        for campo, texto in visibles.items():
            if texto is not None:
                if campo in seg.secretos:
                    texto = "(definida)" if p.tipo == "crear" else OCULTO
                par = {"antes": None, "despues": texto} if p.tipo == "crear" else {"antes": texto, "despues": None}
                cambios.append({"campo": campo, "etiqueta": seg.etiquetas[campo], **par})
    if p.articulos:
        detalle = "; ".join(
            f"{cantidad}× {nombres.producto(prod[1]) if isinstance(prod, tuple) else prod}"
            for prod, cantidad in p.articulos
        )
        cambios.append({"campo": "articulos", "etiqueta": "Artículos", "antes": None, "despues": detalle})

    entidad = seg.entidad[0].upper() + seg.entidad[1:]
    if accion == "crear" and seg.texto_crear is not None:
        descripcion = seg.texto_crear(visibles, p.id_registro)
    elif accion in ("crear", "eliminar", "desactivar", "reactivar", "anular"):
        raiz = {"crear": "cread", "eliminar": "eliminad", "desactivar": "desactivad",
                "reactivar": "reactivad", "anular": "anulad"}[accion]
        descripcion = f"{entidad} {referencia} {seg.participio(raiz)}."
        if accion == "eliminar" and p.tipo == "modificar":
            descripcion = f"{entidad} {referencia} {seg.participio('eliminad')} (se conserva oculto por su historial)."
    elif accion == "contrasena":
        descripcion = f"{entidad} {referencia}: contraseña cambiada."
    elif accion == "pago":
        descripcion = f"Compra {referencia} marcada como {'pagada' if p.cambios['pagado'][1] else 'pendiente de pago'}."
    else:
        partes = [  # "precio venta USD 12.00 → 14.50": solo la primera letra en minúscula
            f"{c['etiqueta'][0].lower()}{c['etiqueta'][1:]} {c['antes'] or '—'} → {c['despues'] or '—'}"
            for c in cambios[:_MAX_RESUMEN]
        ]
        resto = len(cambios) - _MAX_RESUMEN
        descripcion = f"{entidad} {referencia}: " + "; ".join(partes) + (f" y {resto} cambio(s) más." if resto > 0 else ".")
    if p.articulos and accion == "crear":
        descripcion += f" {cambios[-1]['despues']}."
    return {
        "modulo": seg.modulo, "accion": accion, "entidad": seg.entidad, "id_registro": p.id_registro,
        "referencia": referencia[:200], "descripcion": descripcion, "cambios": cambios,
    }


def _antes_del_commit(session: Session) -> None:
    session.flush()  # captura lo que aún no se envió a la base
    pendientes: dict = session.info.pop(_PENDIENTES, {})
    manuales: list = session.info.pop(_MANUALES, [])
    if not pendientes and not manuales:
        return
    lista = list(pendientes.values())
    nombres = _Nombres(session, lista)
    contexto = session.info.get(_CONTEXTO) or {}
    id_usuario, nombre, rol = contexto.get("usuario") or (None, SISTEMA, None)
    comunes = {
        "fecha": local_now(), "id_usuario": id_usuario, "nombre_usuario": nombre[:100], "rol": rol,
        "origen": contexto.get("origen"), "ruta": contexto.get("ruta"), "ip": contexto.get("ip"),
        "id_operacion": contexto.get("operacion") or uuid4().hex,
    }
    filas = [_fila(p, nombres) for p in lista] + manuales
    for fila in filas:
        fila.update(comunes)
        fila["cambios"] = json.dumps(fila["cambios"], ensure_ascii=False) if fila.get("cambios") else None
    session.connection().execute(insert(Auditoria.__table__), filas)
    # Cada petición es una operación; si la sesión sigue, la próxima transacción es otra.
    if _CONTEXTO in session.info:
        session.info[_CONTEXTO]["operacion"] = uuid4().hex


def _fin_de_transaccion(session: Session, transaccion) -> None:
    if transaccion.parent is None:  # ROLLBACK o cierre sin commit: nada que registrar
        session.info.pop(_PENDIENTES, None)
        session.info.pop(_MANUALES, None)


event.listen(Session, "after_flush", _despues_del_flush)
event.listen(Session, "before_commit", _antes_del_commit)
event.listen(Session, "after_transaction_end", _fin_de_transaccion)
