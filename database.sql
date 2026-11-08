-- Esquema de cauchos_rey_def (extraído del respaldo pg_dump del proyecto).
-- El backend trabaja sobre estas tablas tal cual; no las crea ni las modifica.
-- Úselo solo para montar una base nueva vacía con la misma estructura y, después,
-- aplique migrations/002_frontend.sql (márgenes, proveedores, compras y facturas).

CREATE TABLE public.roles (
    id_rol SERIAL PRIMARY KEY,
    nombre character varying(50) NOT NULL UNIQUE,
    descripcion character varying(255),
    estado smallint DEFAULT 1 NOT NULL
);

CREATE TABLE public.usuarios (
    id_usuario SERIAL PRIMARY KEY,
    id_rol integer NOT NULL,
    nombre_completo character varying(100) NOT NULL,
    correo character varying(100) NOT NULL UNIQUE,
    password_hash character varying(255) NOT NULL,
    telefono character varying(20),
    estado smallint DEFAULT 1 NOT NULL,
    fecha_creacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_usuarios_rol FOREIGN KEY (id_rol) REFERENCES public.roles(id_rol)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE public.monedas (
    id_moneda SERIAL PRIMARY KEY,
    codigo character(3) NOT NULL UNIQUE,
    nombre character varying(50) NOT NULL,
    simbolo character varying(5),
    es_base smallint DEFAULT 0 NOT NULL,
    estado smallint DEFAULT 1 NOT NULL
);

CREATE TABLE public.tasas_cambio (
    id_tasa SERIAL PRIMARY KEY,
    id_moneda integer NOT NULL,
    tasa_compra numeric(15,4) NOT NULL,
    tasa_venta numeric(15,4) NOT NULL,
    fecha_actualizacion timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    estado smallint DEFAULT 1 NOT NULL,
    CONSTRAINT fk_tasas_moneda FOREIGN KEY (id_moneda) REFERENCES public.monedas(id_moneda)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE public.categorias (
    id_categoria SERIAL PRIMARY KEY,
    nombre character varying(100) NOT NULL UNIQUE,
    descripcion character varying(255),
    estado smallint DEFAULT 1 NOT NULL
);

CREATE TABLE public.marcas (
    id_marca SERIAL PRIMARY KEY,
    nombre character varying(100) NOT NULL UNIQUE,
    pais_origen character varying(50),
    estado smallint DEFAULT 1 NOT NULL
);

CREATE TABLE public.proveedores (
    id_proveedor SERIAL PRIMARY KEY,
    nombre character varying(100) NOT NULL,
    telefono character varying(20),
    estado smallint DEFAULT 1 NOT NULL
);

CREATE TABLE public.productos (
    id_producto SERIAL PRIMARY KEY,
    sku character varying(50) NOT NULL UNIQUE,
    nombre character varying(150) NOT NULL,
    id_marca integer,
    id_categoria integer NOT NULL,
    id_proveedor integer,
    precio_distribuidor numeric(10,2) DEFAULT 0.00 NOT NULL,
    precio_usd numeric(10,2) DEFAULT 0.00 NOT NULL,
    stock_actual integer DEFAULT 0 NOT NULL,
    stock_minimo integer DEFAULT 5 NOT NULL,
    estado character varying(50) DEFAULT 'Disponible'::character varying NOT NULL,
    fecha_ingreso timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_productos_marca FOREIGN KEY (id_marca) REFERENCES public.marcas(id_marca)
        ON UPDATE CASCADE ON DELETE SET NULL,
    CONSTRAINT fk_productos_categoria FOREIGN KEY (id_categoria)
        REFERENCES public.categorias(id_categoria) ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_productos_proveedor FOREIGN KEY (id_proveedor)
        REFERENCES public.proveedores(id_proveedor) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE public.ventas (
    id_venta SERIAL PRIMARY KEY,
    numero_factura character varying(30) NOT NULL UNIQUE,
    id_usuario integer NOT NULL,
    id_moneda_pago integer NOT NULL,
    monto_total_usd numeric(12,2) NOT NULL,
    monto_total_moneda numeric(15,2) NOT NULL,
    tasa_aplicada numeric(15,4) NOT NULL,
    referencia_pago character varying(50),
    estado character varying(50) DEFAULT 'Completada'::character varying NOT NULL,
    fecha_venta timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_ventas_usuario FOREIGN KEY (id_usuario) REFERENCES public.usuarios(id_usuario)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_ventas_moneda FOREIGN KEY (id_moneda_pago) REFERENCES public.monedas(id_moneda)
        ON UPDATE CASCADE ON DELETE RESTRICT
);

CREATE TABLE public.detalles_venta (
    id_detalle SERIAL PRIMARY KEY,
    id_venta integer NOT NULL,
    id_producto integer NOT NULL,
    nombre_producto_snapshot character varying(150) NOT NULL,
    cantidad integer NOT NULL,
    precio_unitario_usd numeric(10,2) NOT NULL,
    subtotal_usd numeric(12,2) NOT NULL,
    CONSTRAINT fk_detventa_venta FOREIGN KEY (id_venta) REFERENCES public.ventas(id_venta)
        ON UPDATE CASCADE ON DELETE CASCADE,
    CONSTRAINT fk_detventa_producto FOREIGN KEY (id_producto)
        REFERENCES public.productos(id_producto) ON UPDATE CASCADE ON DELETE RESTRICT
);
