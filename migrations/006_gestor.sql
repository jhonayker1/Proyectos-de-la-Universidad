-- Migración 006: rol Gestor, dirección de proveedores y ajustes justificados de stock.
-- Aplicar después de 005_baja_logica.sql.

BEGIN;

INSERT INTO public.roles (nombre, descripcion, estado)
SELECT 'Gestor', 'Asistente administrativo / secretario: supervisión operativa', 1
WHERE NOT EXISTS (
    SELECT 1 FROM public.roles WHERE lower(nombre) = 'gestor'
);

ALTER TABLE public.proveedores
    ADD COLUMN IF NOT EXISTS direccion character varying(200);

CREATE TABLE IF NOT EXISTS public.ajustes_stock (
    id_ajuste SERIAL PRIMARY KEY,
    id_producto integer NOT NULL REFERENCES public.productos(id_producto)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    cantidad integer NOT NULL,
    stock_anterior integer NOT NULL,
    stock_nuevo integer NOT NULL,
    motivo character varying(30) NOT NULL,
    observacion character varying(255) NOT NULL,
    id_usuario integer NOT NULL REFERENCES public.usuarios(id_usuario)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    fecha timestamp without time zone NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ajustes_stock_fecha
    ON public.ajustes_stock (fecha DESC);

COMMIT;
