"""Resolución de categoría, marca y proveedor escritos como texto ("Michelin", "Frenos").

Cada catálogo se carga una sola vez (una consulta) en un índice en memoria; después cada
fila se resuelve sin tocar la base. Se acepta:

- el nombre sin importar mayúsculas, acentos ni espacios, y en singular o plural
  ("BATERIA" = "Baterías");
- el código de la categoría ("LUB") y el RIF del proveedor ("J-12345678-9");
- el ID numérico.

Si no existe: con ``crear_faltantes`` se crea (solo categorías y marcas; un proveedor
exige RIF, teléfono y correo, así que nunca se inventa); si no, se reporta el error con
la sugerencia más parecida ("¿Quiso decir 'Frenos'?").
"""

import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from difflib import get_close_matches

from sqlalchemy.orm import Session

from app.models.inventario import Categoria, Marca, Proveedor
from app.schemas.catalogo import normalize_rif
from app.services.importacion.errores import ValorInvalido
from app.services.sku_service import prefijo_desde_nombre


def normalizar_nombre(texto: str) -> str:
    plano = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", plano))


def _variantes(norm: str) -> list[str]:
    """Formas en singular: 'baterias' -> 'bateria'; 'motores' -> 'motor'."""
    sin_s = " ".join(p[:-1] if p.endswith("s") and len(p) > 3 else p for p in norm.split())
    sin_es = " ".join(p[:-2] if p.endswith("es") and len(p) > 4 else p for p in norm.split())
    return [v for v in dict.fromkeys((sin_s, sin_es)) if v != norm]


@dataclass(eq=False)
class Referencia:
    """Un registro de catálogo, existente o por crear en esta importación."""

    id: int | None
    nombre: str
    activo: bool = True
    nueva: bool = False
    prefijo_sku: str | None = None  # solo categorías
    margen: Decimal = Decimal(0)  # solo categorías: margen de ganancia por defecto
    primera_fila: int | None = None  # fila que la originó, si es nueva
    filas: int = 0  # cuántas filas válidas la usan

    @property
    def clave(self) -> tuple:
        return ("id", self.id) if self.id is not None else ("nueva", normalizar_nombre(self.nombre))


@dataclass
class Catalogo:
    entidad: str  # "categoría", "marca", "proveedor"
    femenino: bool
    permite_crear: bool
    referencias: list[Referencia] = field(default_factory=list)
    _exacto: dict[str, Referencia] = field(default_factory=dict)
    # Forma singular -> registro; None si dos registros la comparten (ambigua).
    _singular: dict[str, Referencia | None] = field(default_factory=dict)
    _por_codigo: dict[str, Referencia] = field(default_factory=dict)
    _por_id: dict[int, Referencia] = field(default_factory=dict)

    @property
    def articulo(self) -> str:
        return "La" if self.femenino else "El"

    def agregar(self, ref: Referencia, codigos: tuple[str, ...] = ()) -> None:
        self.referencias.append(ref)
        if ref.id is not None:
            self._por_id[ref.id] = ref
        norm = normalizar_nombre(ref.nombre)
        self._exacto.setdefault(norm, ref)
        for forma in (norm, *_variantes(norm)):
            if forma not in self._singular:
                self._singular[forma] = ref
            elif self._singular[forma] is not ref:
                self._singular[forma] = None
        for codigo in codigos:
            if codigo:
                self._por_codigo[codigo.upper()] = ref

    def buscar(self, texto: str) -> Referencia | None:
        norm = normalizar_nombre(texto)
        if norm in self._exacto:
            return self._exacto[norm]
        for forma in (norm, *_variantes(norm)):
            ref = self._singular.get(forma)
            if ref is not None:
                return ref
        codigo = texto.strip().upper()
        if codigo in self._por_codigo:
            return self._por_codigo[codigo]
        if self.entidad == "proveedor":
            try:
                ref = self._por_codigo.get(normalize_rif(texto))
            except ValueError:
                ref = None
            if ref is not None:
                return ref
        if re.fullmatch(r"\d+", texto.strip()):
            return self._por_id.get(int(texto.strip()))
        return None

    def sugerencia(self, texto: str) -> str | None:
        nombres = {normalizar_nombre(r.nombre): r.nombre for r in self.referencias if r.activo}
        parecidos = get_close_matches(normalizar_nombre(texto), list(nombres), n=1, cutoff=0.7)
        return nombres[parecidos[0]] if parecidos else None

    def resolver(self, texto: str, fila: int, crear: bool) -> Referencia:
        ref = self.buscar(texto)
        if ref is not None:
            if not ref.activo:
                o_a = "a" if self.femenino else "o"
                donde = "Proveedores" if self.entidad == "proveedor" else "Catálogo"
                raise ValorInvalido(
                    f"{self.articulo} {self.entidad} '{ref.nombre}' está desactivad{o_a}; "
                    f"reactíve{'la' if self.femenino else 'lo'} en {donde} antes de importar."
                )
            return ref
        if crear and self.permite_crear:
            ref = Referencia(id=None, nombre=texto.strip(), nueva=True, primera_fila=fila)
            self.agregar(ref)
            return ref
        motivo = f"{self.articulo} {self.entidad} '{texto.strip()}' no existe."
        parecido = self.sugerencia(texto)
        if parecido:
            motivo += f" ¿Quiso decir '{parecido}'?"
        if self.entidad == "proveedor":
            motivo += (" Regístrelo en Proveedores (requiere RIF, teléfono y correo) o deje la "
                       "celda vacía.")
        elif self.permite_crear:
            motivo += " Créela en Catálogo o active la opción de crear categorías y marcas que falten."
        raise ValorInvalido(motivo)

    def nuevas(self) -> list[Referencia]:
        return [r for r in self.referencias if r.nueva and r.filas > 0]


def cargar(db: Session) -> dict[str, Catalogo]:
    categorias = Catalogo("categoría", femenino=True, permite_crear=True)
    for c in db.query(Categoria).order_by(Categoria.id_categoria):
        categorias.agregar(
            Referencia(
                c.id_categoria, c.nombre, activo=c.estado == 1, prefijo_sku=c.prefijo_sku,
                margen=Decimal(str(c.margen_ganancia or 0)),
            ),
            codigos=(c.prefijo_sku or "",),
        )
    marcas = Catalogo("marca", femenino=True, permite_crear=True)
    for m in db.query(Marca).order_by(Marca.id_marca):
        marcas.agregar(Referencia(m.id_marca, m.nombre, activo=m.estado == 1))
    proveedores = Catalogo("proveedor", femenino=False, permite_crear=False)
    for p in db.query(Proveedor).order_by(Proveedor.id_proveedor):
        codigos = ()
        if p.rif:
            try:
                codigos = (normalize_rif(p.rif),)
            except ValueError:
                codigos = (p.rif.strip().upper(),)
        proveedores.agregar(Referencia(p.id_proveedor, p.nombre, activo=p.estado == 1), codigos)
    return {"categoria": categorias, "marca": marcas, "proveedor": proveedores}


def crear_pendientes(db: Session, catalogos: dict[str, Catalogo]) -> None:
    """Inserta las categorías y marcas nuevas que usan las filas válidas."""
    for ref in catalogos["categoria"].nuevas():
        categoria = Categoria(nombre=ref.nombre, estado=1, margen_ganancia=0, prefijo_sku=ref.prefijo_sku)
        db.add(categoria)
        db.flush()
        ref.id = categoria.id_categoria
    for ref in catalogos["marca"].nuevas():
        marca = Marca(nombre=ref.nombre, estado=1)
        db.add(marca)
        db.flush()
        ref.id = marca.id_marca


def planificar_prefijos(db: Session, categorias: Catalogo) -> None:
    """Código de SKU para las categorías nuevas o que aún no tienen (sin escribir nada)."""
    tomados = {r.prefijo_sku for r in categorias.referencias if r.prefijo_sku}
    for ref in categorias.referencias:
        if not ref.prefijo_sku and ref.filas > 0:
            ref.prefijo_sku = prefijo_desde_nombre(ref.nombre, tomados)
            tomados.add(ref.prefijo_sku)


def guardar_prefijos(db: Session, categorias: Catalogo) -> None:
    """Persiste el código planificado de las categorías existentes que no tenían."""
    for ref in categorias.referencias:
        if ref.id is not None and not ref.nueva and ref.prefijo_sku and ref.filas > 0:
            categoria = db.get(Categoria, ref.id)
            if categoria is not None and not categoria.prefijo_sku:
                categoria.prefijo_sku = ref.prefijo_sku
    db.flush()
