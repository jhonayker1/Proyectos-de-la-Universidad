-- Migración 005: bajas lógicas de productos, usuarios y facturas escaneadas.
-- Protege además las tablas de negocio frente a DELETE/TRUNCATE físicos.
-- Aplicar después de 002_frontend.sql, 003_sku_por_categoria.py y 004_auditoria.sql.
-- Uso: psql -h localhost -U postgres -d cauchos_rey_def -f migrations/005_baja_logica.sql

BEGIN;

ALTER TABLE public.productos
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS fecha_eliminacion timestamp without time zone,
    ADD COLUMN IF NOT EXISTS id_usuario_eliminacion integer;

ALTER TABLE public.usuarios
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS fecha_eliminacion timestamp without time zone,
    ADD COLUMN IF NOT EXISTS id_usuario_eliminacion integer;

ALTER TABLE public.facturas_imagenes
    ADD COLUMN IF NOT EXISTS is_deleted boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS fecha_eliminacion timestamp without time zone,
    ADD COLUMN IF NOT EXISTS id_usuario_eliminacion integer;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.productos'::regclass
          AND conname = 'ck_productos_soft_delete'
    ) THEN
        ALTER TABLE public.productos
            ADD CONSTRAINT ck_productos_soft_delete
            CHECK (
                (is_deleted AND fecha_eliminacion IS NOT NULL)
                OR (NOT is_deleted AND fecha_eliminacion IS NULL)
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.usuarios'::regclass
          AND conname = 'ck_usuarios_soft_delete'
    ) THEN
        ALTER TABLE public.usuarios
            ADD CONSTRAINT ck_usuarios_soft_delete
            CHECK (
                (is_deleted AND fecha_eliminacion IS NOT NULL)
                OR (NOT is_deleted AND fecha_eliminacion IS NULL)
            );
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'public.facturas_imagenes'::regclass
          AND conname = 'ck_facturas_imagenes_soft_delete'
    ) THEN
        ALTER TABLE public.facturas_imagenes
            ADD CONSTRAINT ck_facturas_imagenes_soft_delete
            CHECK (
                (is_deleted AND fecha_eliminacion IS NOT NULL)
                OR (NOT is_deleted AND fecha_eliminacion IS NULL)
            );
    END IF;
END;
$$;

-- Las bajas históricas de productos se reconocen por el sufijo que añadía la versión
-- anterior. Cuando existe auditoría se recuperan su fecha y usuario originales.
UPDATE public.productos p
SET is_deleted = true,
    fecha_eliminacion = COALESCE(
        (
            SELECT a.fecha
            FROM public.auditoria a
            WHERE a.modulo = 'inventario'
              AND a.accion = 'eliminar'
              AND a.entidad = 'producto'
              AND a.id_registro = p.id_producto::text
            ORDER BY a.fecha DESC, a.id_auditoria DESC
            LIMIT 1
        ),
        CURRENT_TIMESTAMP
    ),
    id_usuario_eliminacion = (
        SELECT a.id_usuario
        FROM public.auditoria a
        WHERE a.modulo = 'inventario'
          AND a.accion = 'eliminar'
          AND a.entidad = 'producto'
          AND a.id_registro = p.id_producto::text
        ORDER BY a.fecha DESC, a.id_auditoria DESC
        LIMIT 1
    )
WHERE p.estado = 'Inactivo'
  AND p.sku ~ ('~' || p.id_producto::text || '$');

-- Conserva el SKU en la fila archivada, pero permite reutilizarlo en un producto activo.
ALTER TABLE public.productos
    DROP CONSTRAINT IF EXISTS productos_sku_key;

-- La versión anterior añadía "~id" al SKU de productos archivados con historial.
-- Recupera el SKU antes del índice parcial y recompone el estado de stock, sin
-- modificar el historial de ventas/compras ni los niveles de stock.
UPDATE public.productos p
SET sku = COALESCE(
        (
            SELECT cambios_detalle.cambio->>'antes'
            FROM public.auditoria a
            CROSS JOIN LATERAL jsonb_array_elements(
                COALESCE(a.cambios::jsonb, '[]'::jsonb)
            ) AS cambios_detalle(cambio)
            WHERE a.modulo = 'inventario'
              AND a.accion = 'eliminar'
              AND a.entidad = 'producto'
              AND a.id_registro = p.id_producto::text
              AND cambios_detalle.cambio->>'campo' = 'sku'
            ORDER BY a.fecha DESC, a.id_auditoria DESC
            LIMIT 1
        ),
        regexp_replace(p.sku, '~[0-9]+$', '')
    ),
    estado = CASE
        WHEN p.stock_actual <= 0 THEN 'Agotado'
        WHEN p.stock_actual < p.stock_minimo THEN 'Bajo Stock'
        ELSE 'Disponible'
    END
WHERE p.is_deleted
  AND p.sku ~ ('~' || p.id_producto::text || '$');

CREATE UNIQUE INDEX IF NOT EXISTS ux_productos_sku_activo
    ON public.productos (sku)
    WHERE is_deleted = false;

CREATE INDEX IF NOT EXISTS ix_facturas_activas_fecha
    ON public.facturas_imagenes (fecha_subida DESC)
    WHERE is_deleted = false;

CREATE OR REPLACE FUNCTION public.rechazar_borrado_fisico()
RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Borrado físico bloqueado en %. Use la baja lógica.', TG_TABLE_NAME
        USING ERRCODE = '55000';
END;
$$;

DO $$
DECLARE
    tabla text;
BEGIN
    FOREACH tabla IN ARRAY ARRAY[
        'roles', 'usuarios', 'monedas', 'tasas_cambio',
        'categorias', 'marcas', 'proveedores', 'productos',
        'ventas', 'detalles_venta', 'compras', 'detalles_compra',
        'facturas_imagenes'
    ] LOOP
        EXECUTE format('DROP TRIGGER IF EXISTS tr_rechazar_delete ON public.%I', tabla);
        EXECUTE format(
            'CREATE TRIGGER tr_rechazar_delete BEFORE DELETE ON public.%I
             FOR EACH ROW EXECUTE FUNCTION public.rechazar_borrado_fisico()',
            tabla
        );
        EXECUTE format('DROP TRIGGER IF EXISTS tr_rechazar_truncate ON public.%I', tabla);
        EXECUTE format(
            'CREATE TRIGGER tr_rechazar_truncate BEFORE TRUNCATE ON public.%I
             FOR EACH STATEMENT EXECUTE FUNCTION public.rechazar_borrado_fisico()',
            tabla
        );
    END LOOP;
END;
$$;

COMMIT;
