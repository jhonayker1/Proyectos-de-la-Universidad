# Guía práctica de consultas e INSERT en PostgreSQL

Guía para leer y consultar la base de datos de Cauchos Rey con PostgreSQL. Incluye
ejemplos de lectura, altas de catálogo y pautas para operar con transacciones sin
confundir el acceso directo a la base con las reglas de la aplicación.

> **Importante:** en producción, los cambios de ventas, compras, pagos, usuarios,
> contraseñas y ajustes de stock deben hacerse desde la aplicación/API. La aplicación
> valida roles, precios, inventario y reglas adicionales y genera registros de auditoría.
> Una sentencia SQL directa no pasa por esas validaciones ni crea automáticamente su
> auditoría. Utiliza los `INSERT` de este documento para aprender, para datos de catálogo
> controlados o en una base de pruebas; antes de modificar datos reales, confirma el
> impacto y cuenta con un respaldo.

El esquema original está en [database.sql](../database.sql); las columnas y tablas
posteriores vienen de [migrations/](../migrations/). Para conocer las relaciones,
consulta también el [esquema explicado](./ESQUEMA_BASE_DATOS.md).

## 1. Conectarse con `psql`

En Windows, abre PowerShell o una terminal y ejecuta:

```powershell
psql -h localhost -p 5432 -U postgres -d cauchos_rey_def
```

`-h` es el servidor, `-p` el puerto, `-U` el usuario y `-d` el nombre de la base. `psql`
pedirá la contraseña. Evita poner contraseñas en el comando o guardarlas en archivos
compartidos.

Comandos útiles dentro de `psql`:

| Comando | Resultado |
|---|---|
| `\conninfo` | Muestra a qué servidor y base estás conectado. |
| `\dt public.*` | Lista las tablas del esquema `public`. |
| `\d public.productos` | Muestra columnas, índices y restricciones de una tabla. |
| `\d+ public.ventas` | Muestra más detalles de una tabla. |
| `\di public.*` | Lista índices. |
| `\dn` | Lista esquemas. |
| `\timing on` | Muestra cuánto tarda cada consulta. |
| `\x auto` | Presenta filas anchas en formato vertical cuando conviene. |
| `\q` | Sale de `psql`. |

Las líneas que empiezan con `\` son comandos de `psql`, no SQL estándar; no se ejecutan
desde una ventana SQL que no sea `psql`.

## 2. Ideas básicas de SQL

### Leer datos: `SELECT`

Una consulta indica qué columnas mostrar, de qué tabla y qué filas seleccionar:

```sql
SELECT id_producto, sku, nombre
FROM public.productos
WHERE is_deleted = false
ORDER BY nombre
LIMIT 20;
```

- `SELECT` decide las columnas de salida.
- `FROM` indica la tabla.
- `WHERE` filtra filas.
- `ORDER BY` ordena.
- `LIMIT` limita el número de resultados.

### Insertar datos: `INSERT`

Especifica siempre las columnas. Así no dependes del orden físico de las columnas y
dejas claro qué valores se están guardando:

```sql
INSERT INTO public.marcas (nombre, pais_origen, estado)
VALUES ('Ejemplo Motors', 'Japón', 1)
RETURNING id_marca, nombre;
```

`RETURNING` muestra los valores insertados, incluyendo el identificador generado. En
PostgreSQL, los identificadores `SERIAL` se generan automáticamente: normalmente no
debes proporcionar `id_*`.

### Modificar y borrar

`UPDATE` cambia filas y `DELETE` las elimina físicamente. **No ejecutes un `UPDATE` o
`DELETE` sin revisar primero el mismo filtro con un `SELECT`.** En esta aplicación hay
triggers que bloquean `DELETE` y `TRUNCATE` físicos en varias tablas. Las bajas de
productos, usuarios y facturas son lógicas (archivar), no borrados de filas.

## 3. Tipos y condiciones que aparecen en esta base

- **Dinero:** usa `numeric`, por ejemplo `12.50`. Evita `real` o `double precision` para
  cálculos monetarios porque son aproximados.
- **Fecha:** `date` es solo día; `timestamp without time zone` no almacena zona horaria.
  La aplicación aplica `TIMEZONE` al interpretar sus fechas.
- **`NULL`:** significa “sin valor conocido”, no cero ni texto vacío. Usa `IS NULL` y
  `IS NOT NULL`; `columna = NULL` no sirve.
- **Estado numérico:** en `roles`, `usuarios`, `monedas`, `tasas_cambio`, categorías,
  marcas y proveedores, normalmente `1` significa activo y `0` inactivo.
- **Baja lógica:** `is_deleted = false` significa que el producto/usuario/factura no
  está archivado. No todas las tablas tienen esta columna.
- **Estado de producto:** valores utilizados por la aplicación: `Disponible`,
  `Bajo Stock`, `Agotado` e `Inactivo`.
- **Venta:** normalmente `Completada` o `Anulada`.
- **Compra:** `pagado = 1` indica pagada y `pagado = 0` pendiente.
- **Tasa:** `tasa_venta` expresa cuántas unidades de esa moneda equivalen a 1 USD.

Usa siempre comillas simples para los valores de texto (`'VES'`) y no para los nombres
de columnas. Los identificadores sin comillas no distinguen mayúsculas de minúsculas.

## 4. Consultas de lectura frecuentes

### 4.1 Ver las tablas disponibles

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

Para ver las columnas de una tabla:

```sql
SELECT
    ordinal_position,
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'productos'
ORDER BY ordinal_position;
```

### 4.2 Consultar categorías, marcas y proveedores activos

```sql
SELECT id_categoria, nombre, margen_ganancia, prefijo_sku
FROM public.categorias
WHERE estado = 1
ORDER BY nombre;
```

```sql
SELECT id_marca, nombre, pais_origen
FROM public.marcas
WHERE estado = 1
ORDER BY nombre;
```

```sql
SELECT id_proveedor, nombre, rif, telefono, correo, ciudad
FROM public.proveedores
WHERE estado = 1
ORDER BY nombre;
```

Una categoría puede tener `prefijo_sku` nulo si aún no se le asignó uno. Esta columna se
añade con la migración `003_sku_por_categoria.py`.

### 4.3 Catálogo de productos con nombres de categoría, marca y proveedor

```sql
SELECT
    p.id_producto,
    p.sku,
    p.nombre AS producto,
    c.nombre AS categoria,
    m.nombre AS marca,
    pr.nombre AS proveedor,
    p.precio_distribuidor AS costo_usd,
    p.precio_usd AS precio_venta_usd,
    p.stock_actual,
    p.stock_minimo,
    p.estado
FROM public.productos AS p
JOIN public.categorias AS c ON c.id_categoria = p.id_categoria
LEFT JOIN public.marcas AS m ON m.id_marca = p.id_marca
LEFT JOIN public.proveedores AS pr ON pr.id_proveedor = p.id_proveedor
WHERE p.is_deleted = false
  AND p.estado <> 'Inactivo'
ORDER BY c.nombre, p.nombre;
```

`JOIN` requiere que exista una fila relacionada. `LEFT JOIN` conserva el producto aunque
no tenga marca o proveedor asociado.

### 4.4 Buscar por SKU o por parte del nombre

```sql
SELECT id_producto, sku, nombre, precio_usd, stock_actual, estado
FROM public.productos
WHERE is_deleted = false
  AND (
      sku ILIKE '%LUB%'
      OR nombre ILIKE '%aceite%'
  )
ORDER BY nombre;
```

`ILIKE` busca texto sin distinguir mayúsculas de minúsculas. El carácter `%` representa
cualquier secuencia de caracteres.

### 4.5 Productos agotados o por debajo del mínimo

```sql
SELECT id_producto, sku, nombre, stock_actual, stock_minimo, estado
FROM public.productos
WHERE is_deleted = false
  AND estado <> 'Inactivo'
  AND stock_actual < stock_minimo
ORDER BY stock_actual, nombre;
```

El filtro también incluye productos con cero unidades. Si quieres exclusivamente los
agotados, añade `AND stock_actual <= 0`. La aplicación calcula el estado al registrar
ventas, compras y ajustes; un `SELECT` como este compara las cantidades actuales y no
depende de que el texto de `estado` esté actualizado.

### 4.6 Valor de inventario al costo y al precio de venta

```sql
SELECT
    COUNT(*) AS productos,
    SUM(stock_actual) AS unidades,
    SUM(stock_actual * precio_distribuidor) AS valor_al_costo_usd,
    SUM(stock_actual * precio_usd) AS valor_a_precio_venta_usd
FROM public.productos
WHERE is_deleted = false
  AND estado <> 'Inactivo';
```

El valor a precio de venta no equivale a utilidad: no incluye gastos, descuentos,
devoluciones u otros costos.

### 4.7 Productos por categoría

```sql
SELECT
    c.id_categoria,
    c.nombre AS categoria,
    COUNT(p.id_producto) AS cantidad_productos,
    COALESCE(SUM(p.stock_actual), 0) AS unidades
FROM public.categorias AS c
LEFT JOIN public.productos AS p
       ON p.id_categoria = c.id_categoria
      AND p.is_deleted = false
      AND p.estado <> 'Inactivo'
WHERE c.estado = 1
GROUP BY c.id_categoria, c.nombre
ORDER BY c.nombre;
```

`COALESCE(valor, 0)` reemplaza un `NULL` por cero. Las condiciones sobre productos están
en el `ON` para no convertir el `LEFT JOIN` en un `JOIN` normal.

### 4.8 Última tasa vigente por moneda

```sql
SELECT DISTINCT ON (m.codigo)
    m.codigo,
    m.nombre,
    t.tasa_compra,
    t.tasa_venta,
    t.fecha_actualizacion
FROM public.tasas_cambio AS t
JOIN public.monedas AS m ON m.id_moneda = t.id_moneda
WHERE t.estado = 1
  AND m.estado = 1
ORDER BY m.codigo, t.fecha_actualizacion DESC, t.id_tasa DESC;
```

`DISTINCT ON` es una extensión de PostgreSQL. El `ORDER BY` elige la tasa más reciente
para cada código. Para consultar una sola moneda, por ejemplo VES:

```sql
SELECT t.id_tasa, m.codigo, t.tasa_venta, t.fecha_actualizacion
FROM public.tasas_cambio AS t
JOIN public.monedas AS m ON m.id_moneda = t.id_moneda
WHERE m.codigo = 'VES'
  AND t.estado = 1
ORDER BY t.fecha_actualizacion DESC, t.id_tasa DESC
LIMIT 1;
```

### 4.9 Ventas de un día

Como `fecha_venta` es `timestamp without time zone`, filtra con intervalo semiabierto:
incluye el inicio del día y excluye la medianoche del día siguiente.

```sql
-- Cambia la fecha por el día que quieras consultar.
SELECT
    v.id_venta,
    v.numero_factura,
    v.fecha_venta,
    u.nombre_completo AS cajero,
    m.codigo AS moneda_pago,
    v.monto_total_usd,
    v.monto_total_moneda,
    v.tasa_aplicada,
    v.estado
FROM public.ventas AS v
JOIN public.usuarios AS u ON u.id_usuario = v.id_usuario
JOIN public.monedas AS m ON m.id_moneda = v.id_moneda_pago
WHERE v.fecha_venta >= TIMESTAMP '2026-11-24 00:00:00'
  AND v.fecha_venta <  TIMESTAMP '2026-11-25 00:00:00'
ORDER BY v.fecha_venta DESC;
```

Para incluir un rango de fechas, define `desde` y `hasta` como fechas y compara con
`>= desde` y `< hasta + 1 día` (si `hasta` es inclusiva). Las fechas almacenadas deben
interpretarse con la zona horaria configurada para la aplicación.

### 4.10 Detalle de una venta

```sql
SELECT
    v.numero_factura,
    v.fecha_venta,
    dv.nombre_producto_snapshot AS producto_en_la_venta,
    p.sku,
    dv.cantidad,
    dv.precio_unitario_usd,
    dv.subtotal_usd
FROM public.ventas AS v
JOIN public.detalles_venta AS dv ON dv.id_venta = v.id_venta
JOIN public.productos AS p ON p.id_producto = dv.id_producto
WHERE v.id_venta = 123
ORDER BY dv.id_detalle;
```

La descripción histórica es `nombre_producto_snapshot`; el nombre actual de `productos`
puede haber cambiado.

### 4.11 Totales de ventas por día

```sql
SELECT
    date_trunc('day', fecha_venta) AS dia,
    COUNT(*) FILTER (WHERE estado = 'Completada') AS ventas_completadas,
    COUNT(*) FILTER (WHERE estado = 'Anulada') AS ventas_anuladas,
    COALESCE(
        SUM(monto_total_usd) FILTER (WHERE estado = 'Completada'),
        0
    ) AS total_completado_usd
FROM public.ventas
GROUP BY date_trunc('day', fecha_venta)
ORDER BY dia DESC
LIMIT 30;
```

Una venta anulada sigue en la base como historial. Por eso se excluye explícitamente de
la suma de ventas completadas.

### 4.12 Compras y cuentas pendientes

```sql
SELECT
    co.id_compra,
    co.fecha,
    pr.nombre AS proveedor,
    co.numero_factura,
    co.monto_usd,
    co.pagado,
    u.nombre_completo AS registrado_por
FROM public.compras AS co
JOIN public.proveedores AS pr ON pr.id_proveedor = co.id_proveedor
JOIN public.usuarios AS u ON u.id_usuario = co.id_usuario
WHERE co.pagado = 0
ORDER BY co.fecha, co.id_compra;
```

Resumen de deuda por proveedor:

```sql
SELECT
    pr.id_proveedor,
    pr.nombre AS proveedor,
    COUNT(*) AS compras_pendientes,
    SUM(co.monto_usd) AS saldo_pendiente_usd
FROM public.compras AS co
JOIN public.proveedores AS pr ON pr.id_proveedor = co.id_proveedor
WHERE co.pagado = 0
GROUP BY pr.id_proveedor, pr.nombre
ORDER BY saldo_pendiente_usd DESC;
```

### 4.13 Cambios de stock documentados

```sql
SELECT
    a.fecha,
    p.sku,
    p.nombre AS producto,
    a.motivo,
    a.cantidad,
    a.stock_anterior,
    a.stock_nuevo,
    a.observacion,
    u.nombre_completo AS usuario
FROM public.ajustes_stock AS a
JOIN public.productos AS p ON p.id_producto = a.id_producto
JOIN public.usuarios AS u ON u.id_usuario = a.id_usuario
ORDER BY a.fecha DESC
LIMIT 100;
```

`ajustes_stock` existe desde `006_gestor.sql`.

### 4.14 Buscar en la auditoría

```sql
SELECT
    fecha,
    nombre_usuario,
    rol,
    modulo,
    accion,
    entidad,
    id_registro,
    descripcion,
    cambios,
    id_operacion
FROM public.auditoria
WHERE fecha >= TIMESTAMP '2026-11-01 00:00:00'
  AND fecha <  TIMESTAMP '2026-12-01 00:00:00'
ORDER BY fecha DESC
LIMIT 200;
```

Para filtrar por un producto o factura, usa `entidad`, `id_registro` o `referencia`
según el tipo de evento. La auditoría es de solo lectura y no debe modificarse ni
borrarse.

### 4.15 Conteo de filas

```sql
SELECT 'productos' AS tabla, COUNT(*) AS filas FROM public.productos
UNION ALL
SELECT 'ventas', COUNT(*) FROM public.ventas
UNION ALL
SELECT 'compras', COUNT(*) FROM public.compras
UNION ALL
SELECT 'usuarios activos', COUNT(*) FROM public.usuarios
WHERE estado = 1 AND is_deleted = false;
```

## 5. INSERT de datos de catálogo

En cada ejemplo sustituye los valores de muestra por los reales. El `RETURNING` permite
copiar el ID asignado sin consultar la secuencia manualmente.

### 5.1 Insertar una categoría

`prefijo_sku` se añade con la migración 003. Debe ser único y tener hasta cinco
caracteres. Si la migración aún no se ejecutó, omite esa columna.

```sql
INSERT INTO public.categorias
    (nombre, descripcion, estado, margen_ganancia, prefijo_sku)
VALUES
    ('Lubricantes', 'Aceites y lubricantes para vehículos', 1, 25.00, 'LUB')
RETURNING id_categoria, nombre, margen_ganancia, prefijo_sku;
```

El ejemplo fija un margen de 25 %. El precio sugerido por esa regla es
`precio_distribuidor * (1 + margen / 100)`. En este proyecto, margen cero corresponde
a precio manual; no pongas cero si lo que quieres es un margen positivo.

### 5.2 Insertar una marca

```sql
INSERT INTO public.marcas (nombre, pais_origen, estado)
VALUES ('Marca Ejemplo', 'Japón', 1)
RETURNING id_marca, nombre;
```

### 5.3 Insertar un proveedor

La aplicación espera que el proveedor tenga RIF, teléfono y correo válidos, aunque la
base permite algunos de esos campos como `NULL`. Para mantener los datos coherentes,
rellénalos:

```sql
INSERT INTO public.proveedores
    (nombre, telefono, estado, rif, contacto, correo, ciudad, condiciones, direccion)
VALUES
    (
        'Distribuidora Ejemplo',
        '+58-212-5550101',
        1,
        'J-12345678-9',
        'Ana Pérez',
        'compras@ejemplo.com',
        'Caracas',
        'Crédito a 30 días',
        'Av. Principal, local 10'
    )
RETURNING id_proveedor, nombre, rif, correo;
```

`direccion` requiere la migración 006. Sin ella, omite esa columna y su valor. El formato
del RIF mostrado es un ejemplo: registra el identificador legal real del proveedor.

### 5.4 Insertar un producto activo

Este ejemplo obtiene el ID de la categoría, marca y proveedor por sus nombres y no
especifica el ID del producto. Si la categoría no existe, el `SELECT` no insertará
ninguna fila. SKU debe ser único entre los productos activos.

```sql
INSERT INTO public.productos (
    sku,
    nombre,
    id_marca,
    id_categoria,
    id_proveedor,
    precio_distribuidor,
    precio_usd,
    stock_actual,
    stock_minimo,
    estado,
    fecha_ingreso,
    margen_pct,
    ubicacion,
    is_deleted,
    fecha_eliminacion
)
SELECT
    'LUB-0001',
    'Aceite sintético 5W-30',
    m.id_marca,
    c.id_categoria,
    pr.id_proveedor,
    8.00,
    10.00,
    12,
    3,
    CASE
        WHEN 12 <= 0 THEN 'Agotado'
        WHEN 12 < 3 THEN 'Bajo Stock'
        ELSE 'Disponible'
    END,
    CURRENT_TIMESTAMP,
    NULL,
    'Estante A-01',
    false,
    NULL
FROM public.categorias AS c
LEFT JOIN public.marcas AS m ON m.nombre = 'Marca Ejemplo'
LEFT JOIN public.proveedores AS pr ON pr.nombre = 'Distribuidora Ejemplo'
WHERE c.nombre = 'Lubricantes'
RETURNING id_producto, sku, nombre, precio_usd, stock_actual, estado;
```

Notas:

- Cambia SKU y datos de muestra. En el uso normal, la aplicación puede generar el SKU
  siguiente de la categoría; SQL directo no ejecuta esa lógica automáticamente.
- `margen_pct = NULL` significa que el producto hereda el margen de la categoría según
  la lógica de la aplicación. Si vas a registrar un precio manual, verifica la regla de
  margen aplicada antes de insertar.
- El valor de `estado` debe concordar con el stock y el mínimo.
- Si existen dos marcas o proveedores con el mismo nombre (la marca es única, el nombre
  del proveedor no necesariamente), la consulta podría insertar más de un producto.
  Para evitarlo, busca primero sus IDs y usa los IDs correctos.
- Si el SKU activo ya existe, el índice parcial impedirá el INSERT. Un SKU archivado se
  puede reutilizar si no lo usa otro producto activo.

### 5.5 Alta de una moneda en un entorno de prueba

Las monedas se configuran normalmente durante la instalación. Comprueba primero que el
código no exista:

```sql
SELECT id_moneda, codigo, nombre, es_base, estado
FROM public.monedas
WHERE codigo = 'VES';
```

Si de verdad falta en una base de prueba y no es una base operativa:

```sql
INSERT INTO public.monedas (codigo, nombre, simbolo, es_base, estado)
VALUES ('VES', 'Bolívar', 'Bs.', 0, 1)
RETURNING id_moneda, codigo, nombre;
```

No insertes una segunda moneda base. En el sistema, USD es la moneda base de los precios.

## 6. INSERT de tasa de cambio (operación controlada)

La aplicación conserva historial de tasas y considera vigente la última activa. Al
registrar una tasa nueva, las anteriores activas de esa moneda deben quedar inactivas.
En producción utiliza el panel/API; este ejemplo solo muestra la idea para una base
controlada.

El bloque comprueba que la moneda exista, toma un bloqueo sobre ella y hace ambas
operaciones en la misma transacción:

```sql
BEGIN;

DO $$
DECLARE
    v_id_moneda integer;
BEGIN
    SELECT id_moneda
    INTO v_id_moneda
    FROM public.monedas
    WHERE codigo = 'VES'
      AND estado = 1
    FOR UPDATE;

    IF v_id_moneda IS NULL THEN
        RAISE EXCEPTION 'No existe una moneda VES activa';
    END IF;

    UPDATE public.tasas_cambio
    SET estado = 0
    WHERE id_moneda = v_id_moneda
      AND estado = 1;

    INSERT INTO public.tasas_cambio
        (id_moneda, tasa_compra, tasa_venta, fecha_actualizacion, estado)
    VALUES
        (v_id_moneda, 350.0000, 355.0000, CURRENT_TIMESTAMP, 1);
END
$$;

COMMIT;
```

Sustituye los números de muestra por la tasa autorizada. Si una sentencia falla, la
transacción queda abortada; ejecuta `ROLLBACK;` antes de continuar en `psql`.

## 7. Transacciones y verificación

Una transacción agrupa varias sentencias: se confirman todas con `COMMIT` o se deshacen
con `ROLLBACK`.

```sql
BEGIN;

-- Ejecuta aquí solo cambios revisados.
-- Comprueba el resultado antes de confirmar:
SELECT id_categoria, nombre, estado
FROM public.categorias
WHERE nombre = 'Lubricantes';

-- Si todo está correcto:
COMMIT;

-- Si algo no cuadra, en lugar de COMMIT usa:
-- ROLLBACK;
```

En `psql` también puedes activar `ON_ERROR_STOP` en scripts no interactivos para que
una sentencia con error detenga el archivo:

```powershell
psql -v ON_ERROR_STOP=1 -h localhost -U postgres -d cauchos_rey_def -f consulta.sql
```

Para ejecutar un archivo con `INSERT`, revisa su contenido antes de correrlo. No ejecutes
archivos SQL recibidos de terceros sin entender qué tablas modifican.

## 8. Consultas previas a un cambio

Antes de insertar producto, encuentra los IDs y confirma que los registros estén
activos:

```sql
SELECT id_categoria, nombre, estado, prefijo_sku
FROM public.categorias
WHERE lower(nombre) = lower('Lubricantes');

SELECT id_marca, nombre, estado
FROM public.marcas
WHERE lower(nombre) = lower('Marca Ejemplo');

SELECT id_proveedor, nombre, rif, estado
FROM public.proveedores
WHERE rif = 'J-12345678-9';
```

Comprueba también si el SKU está ocupado por un producto activo:

```sql
SELECT id_producto, sku, nombre, is_deleted, estado
FROM public.productos
WHERE sku = 'LUB-0001'
  AND is_deleted = false;
```

## 9. Por qué no se incluyen INSERT directos de ventas y compras

Una venta no es solo una fila en `ventas`: requiere validar usuario y moneda, calcular
totales/tasa, guardar renglones, comprobar y descontar stock de forma concurrente,
asignar el número de factura y generar auditoría. Una compra también debe crear sus
detalles, sumar stock y actualizar el estado del producto. Un INSERT incompleto puede
dejar importes, stock e historial inconsistentes, aunque PostgreSQL acepte la fila.

Por la misma razón, evita cambiar directamente `productos.stock_actual`, marcar una
compra como pagada, anular una venta, insertar un usuario o cambiar una contraseña. Usa
la pantalla correspondiente o los endpoints de la API. Para usuarios, además, el campo
`password_hash` requiere un hash compatible con el verificador de la aplicación; una
contraseña en texto plano no sirve y expone la cuenta.

## 10. UPDATE y borrados lógicos: leer antes de escribir

La siguiente consulta **solo muestra** qué fila se afectaría:

```sql
SELECT id_categoria, nombre, estado
FROM public.categorias
WHERE id_categoria = 10;
```

Las categorías, marcas y proveedores se desactivan en la aplicación; no se deben borrar
físicamente porque las referencias e historial pueden depender de ellos. Los productos,
usuarios y facturas se archivan usando columnas de baja lógica y controles adicionales.
La aplicación también registra estos cambios en `auditoria`; un `UPDATE` manual no
produce esa entrada.

No uses estas sentencias en esta base:

```sql
-- No ejecutar:
-- DELETE FROM public.productos;
-- TRUNCATE public.ventas;
```

Los triggers de PostgreSQL bloquean los borrados físicos en varias tablas, pero no son
un sustituto de una copia de seguridad ni una garantía de que cualquier `UPDATE` directo
sea seguro.

## 11. Errores SQL frecuentes

### `duplicate key value violates unique constraint`

Ya hay otra fila con ese valor único (por ejemplo, correo, código de moneda, nombre de
categoría o SKU activo). Búscalo antes de reintentar; no cambies el ID manualmente.

### `violates foreign key constraint`

El ID de categoría, usuario, producto, proveedor o moneda no existe. Consulta el registro
relacionado primero; no inventes IDs.

### `null value in column ... violates not-null constraint`

Falta un valor obligatorio. Revisa las columnas con `\d public.nombre_tabla` o
`information_schema.columns`.

### `current transaction is aborted`

Una sentencia anterior dentro de la transacción falló. Ejecuta `ROLLBACK;`, corrige la
causa y vuelve a intentar desde el inicio.

### `column ... does not exist`

Puede faltar una migración o el nombre puede ser incorrecto. Compara el esquema con
`database.sql` y `migrations/`; no agregues una columna manualmente para ocultar una
migración pendiente.

## 12. Recomendaciones finales

1. Confirma la base y el servidor con `\conninfo`.
2. Usa `SELECT` para revisar los datos antes y después de un cambio.
3. Especifica las columnas en cada `INSERT`; utiliza `RETURNING`.
4. No establezcas IDs `SERIAL` manualmente.
5. Agrupa cambios relacionados con `BEGIN`/`COMMIT`; deshaz con `ROLLBACK` si hay dudas.
6. No cambies directamente ventas, compras, stock, pagos, usuarios ni auditoría en una
   base de producción.
7. Mantén sincronizados `database.sql`, los modelos y las migraciones cuando el esquema
   evolucione.
8. Consulta el [README](../README.md) para el orden de migraciones y las reglas de
   negocio.
