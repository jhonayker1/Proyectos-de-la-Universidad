-- Migración 004: bitácora de auditoría (quién cambió qué, cuándo y desde dónde).
-- Solo agrega una tabla; no modifica datos existentes. Se puede ejecutar varias veces.
-- Uso: psql -h localhost -U postgres -d cauchos_rey_def -f migrations/004_auditoria.sql

BEGIN;

CREATE TABLE IF NOT EXISTS public.auditoria (
    id_auditoria BIGSERIAL PRIMARY KEY,
    fecha timestamp without time zone NOT NULL,
    -- Sin llave foránea: el registro debe sobrevivir aunque el usuario se elimine;
    -- por eso también se guarda su nombre y rol de ese momento.
    id_usuario integer,
    nombre_usuario character varying(100) NOT NULL,
    rol character varying(20),
    modulo character varying(30) NOT NULL,
    accion character varying(30) NOT NULL,
    entidad character varying(40) NOT NULL,
    id_registro character varying(40),
    referencia character varying(200),
    descripcion text NOT NULL,
    cambios text,                       -- JSON: [{campo, etiqueta, antes, despues}]
    origen character varying(200),      -- p. ej. "Venta en punto de venta", "Importación masiva"
    ruta character varying(200),        -- método y ruta de la API que hizo el cambio
    ip character varying(45),
    id_operacion character varying(32)  -- agrupa los cambios hechos en una misma petición
);

CREATE INDEX IF NOT EXISTS ix_auditoria_fecha ON public.auditoria (fecha DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_modulo_fecha ON public.auditoria (modulo, fecha DESC);
CREATE INDEX IF NOT EXISTS ix_auditoria_usuario ON public.auditoria (id_usuario);
CREATE INDEX IF NOT EXISTS ix_auditoria_operacion ON public.auditoria (id_operacion);

-- La bitácora es de solo lectura: la base rechaza modificar o borrar registros.
CREATE OR REPLACE FUNCTION public.auditoria_solo_lectura() RETURNS trigger
    LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'La auditoría es de solo lectura: no se pueden modificar ni borrar registros.';
END;
$$;

DROP TRIGGER IF EXISTS tr_auditoria_solo_lectura ON public.auditoria;
CREATE TRIGGER tr_auditoria_solo_lectura
    BEFORE UPDATE OR DELETE ON public.auditoria
    FOR EACH ROW EXECUTE FUNCTION public.auditoria_solo_lectura();

DROP TRIGGER IF EXISTS tr_auditoria_sin_truncate ON public.auditoria;
CREATE TRIGGER tr_auditoria_sin_truncate
    BEFORE TRUNCATE ON public.auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION public.auditoria_solo_lectura();

COMMIT;
