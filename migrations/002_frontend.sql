-- Migración 002: datos que usan las pantallas del frontend (márgenes, detalle de
-- proveedores, compras/entradas de stock y facturas escaneadas).
-- Solo agrega columnas y tablas; no modifica ni borra datos existentes.
-- Se puede ejecutar varias veces (IF NOT EXISTS).
-- Uso: psql -h localhost -U postgres -d cauchos_rey_def -f migrations/002_frontend.sql

BEGIN;

-- Margen de ganancia (%) por categoría y, opcionalmente, por producto.
-- precio_usd = precio_distribuidor * (1 + margen / 100)
ALTER TABLE public.categorias
    ADD COLUMN IF NOT EXISTS margen_ganancia numeric(5,2) DEFAULT 0 NOT NULL;

ALTER TABLE public.productos
    ADD COLUMN IF NOT EXISTS margen_pct numeric(5,2),
    ADD COLUMN IF NOT EXISTS ubicacion character varying(80);

ALTER TABLE public.proveedores
    ADD COLUMN IF NOT EXISTS rif character varying(20),
    ADD COLUMN IF NOT EXISTS contacto character varying(100),
    ADD COLUMN IF NOT EXISTS correo character varying(100),
    ADD COLUMN IF NOT EXISTS ciudad character varying(60),
    ADD COLUMN IF NOT EXISTS condiciones character varying(120);

ALTER TABLE public.usuarios
    ADD COLUMN IF NOT EXISTS permisos character varying(255);

-- Compras a proveedores. Registrar una compra con detalles suma stock (entradas).
CREATE TABLE IF NOT EXISTS public.compras (
    id_compra SERIAL PRIMARY KEY,
    id_proveedor integer NOT NULL,
    numero_factura character varying(30),
    fecha date NOT NULL,
    descripcion character varying(255),
    monto_usd numeric(12,2) NOT NULL,
    pagado smallint DEFAULT 0 NOT NULL,
    id_usuario integer NOT NULL,
    fecha_registro timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_compras_proveedor FOREIGN KEY (id_proveedor)
        REFERENCES public.proveedores(id_proveedor) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_compras_usuario FOREIGN KEY (id_usuario)
        REFERENCES public.usuarios(id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS public.detalles_compra (
    id_detalle_compra SERIAL PRIMARY KEY,
    id_compra integer NOT NULL,
    id_producto integer NOT NULL,
    cantidad integer NOT NULL,
    costo_unitario_usd numeric(10,2) NOT NULL,
    CONSTRAINT fk_detcompra_compra FOREIGN KEY (id_compra)
        REFERENCES public.compras(id_compra) ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_detcompra_producto FOREIGN KEY (id_producto)
        REFERENCES public.productos(id_producto) ON UPDATE CASCADE ON DELETE RESTRICT
);

-- Facturas escaneadas (imagen o PDF) guardadas en disco por el backend.
CREATE TABLE IF NOT EXISTS public.facturas_imagenes (
    id_factura_img SERIAL PRIMARY KEY,
    nombre_original character varying(255) NOT NULL,
    ruta_archivo character varying(255) NOT NULL,
    tipo_mime character varying(100) NOT NULL,
    tamano_bytes integer NOT NULL,
    id_compra integer,
    id_usuario integer NOT NULL,
    fecha_subida timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_facturas_compra FOREIGN KEY (id_compra)
        REFERENCES public.compras(id_compra) ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_facturas_usuario FOREIGN KEY (id_usuario)
        REFERENCES public.usuarios(id_usuario) ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS ix_compras_proveedor ON public.compras (id_proveedor);
CREATE INDEX IF NOT EXISTS ix_compras_fecha ON public.compras (fecha);
CREATE INDEX IF NOT EXISTS ix_detalles_compra_compra ON public.detalles_compra (id_compra);
CREATE INDEX IF NOT EXISTS ix_facturas_fecha ON public.facturas_imagenes (fecha_subida);

COMMIT;
