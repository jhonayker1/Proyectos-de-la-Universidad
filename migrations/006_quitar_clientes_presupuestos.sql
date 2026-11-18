-- Migración 006: retira los módulos de Clientes y Presupuestos.
-- Solo hace falta en bases donde se aplicó la versión anterior de 005_gestor.sql, que
-- creaba esas tablas. Si alguna tiene datos, se detiene sin borrar nada (respáldelos
-- primero). Se puede ejecutar varias veces.
-- Uso: psql -h localhost -U postgres -d cauchos_rey_def -f migrations/006_quitar_clientes_presupuestos.sql

BEGIN;

-- Consulta dinámica: si la tabla ya no existe (segunda ejecución) no se evalúa.
DO $$
DECLARE
    tabla text;
    con_datos boolean;
BEGIN
    FOREACH tabla IN ARRAY ARRAY['presupuestos', 'clientes'] LOOP
        IF to_regclass('public.' || tabla) IS NOT NULL THEN
            EXECUTE format('SELECT EXISTS (SELECT 1 FROM public.%I)', tabla) INTO con_datos;
            IF con_datos THEN
                RAISE EXCEPTION 'La tabla % tiene datos: respáldelos antes de quitar el módulo.', tabla;
            END IF;
        END IF;
    END LOOP;
END $$;

DROP TABLE IF EXISTS public.detalles_presupuesto;
DROP TABLE IF EXISTS public.presupuestos;
DROP TABLE IF EXISTS public.clientes;

COMMIT;
