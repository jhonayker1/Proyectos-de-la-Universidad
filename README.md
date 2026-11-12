# Inventario y ventas de repuestos (Cauchos Rey)

- **Backend** (`app/`): FastAPI sobre la base PostgreSQL existente `cauchos_rey_def`.
- **Frontend** (`frontend/`): una sola app React (Vite + Tailwind) con login único;
  según el rol abre el panel de **administrador** (`/admin`) o de **cajero** (`/cajero`).
  Es la adaptación de los diseños de Figma que estaban en `Admin/` y `Cajero/`.

## Puesta en marcha

1. **Base de datos.** El backend usa las tablas de `cauchos_rey_def` (`usuarios`,
   `roles`, `productos`, `categorias`, `marcas`, `proveedores`, `monedas`,
   `tasas_cambio`, `ventas`, `detalles_venta`) y las que agrega
   las migraciones: `002_frontend.sql` (márgenes, datos de proveedor, `compras`,
   `detalles_compra`, `facturas_imagenes`), `003_sku_por_categoria.py` (código de
   cada categoría para el SKU automático; se asigna a partir de los SKU que ya
   usan sus productos) y `004_auditoria.sql` (tabla `auditoria`, de solo lectura).
   Solo agregan columnas y tablas, no modifican SKU ni datos existentes, y se pueden
   ejecutar más de una vez, en orden:
   ```
   psql -h localhost -U postgres -d cauchos_rey_def -f migrations/002_frontend.sql
   .\.venv\Scripts\python.exe migrations\003_sku_por_categoria.py
   psql -h localhost -U postgres -d cauchos_rey_def -f migrations/004_auditoria.sql
   ```
   Para una base nueva vacía: `database.sql` y luego las migraciones.
2. **Backend.** Configure `.env` (ver `.env.example`; `DB_PASSWORD` es la clave
   de `postgres`), instale `pip install -r requirements.txt` e inicie con
   `python run.py` (puerto 8000; documentación en `http://127.0.0.1:8000/docs`).
3. **Frontend.** Requiere Node.js 22 o superior:
   ```
   cd frontend
   npm install
   npm run dev        # http://localhost:5173
   ```
   En desarrollo, Vite envía `/api` al backend (`BACKEND_URL`, por defecto
   `http://127.0.0.1:8000`), así que no hace falta configurar CORS. Para
   producción: `npm run build` genera `frontend/dist`; si el backend está en otro
   dominio, defina `VITE_API_URL` antes del build y agregue ese dominio a
   `CORS_ORIGINS`.

Al iniciar, el backend ejecuta `SELECT NOW()` con reintentos y comprueba que
existan todas las tablas y columnas; si falta algo, indica qué migración aplicar.

**Contraseña olvidada:** en el login, "¿Olvidaste tu contraseña?" pide el correo y
el backend escribe un código de 6 dígitos en la consola donde corre `run.py`
(vence en 10 minutos, un solo uso, 5 intentos). Así solo quien tiene acceso a la
computadora del servidor puede restablecer una clave. La respuesta es la misma
exista o no el correo. Alternativas: `python reset_password.py` en el servidor, o
el administrador desde Usuarios → "Restablecer contraseña". Si ningún usuario
puede entrar, también puede definir `INITIAL_ADMIN_*` para crear un administrador.

## Reglas de negocio

- **Roles:** los registros de `roles` llamados `Administrador`/`Admin` o `Cajero`
  se reconocen como administrador y cajero; otros roles no tienen acceso. El panel
  solo crea cajeros.
- **Bimoneda:** los precios (`precio_usd`) están en USD (`monedas.es_base = 1`).
  El administrador registra la tasa de VES y COP; la vigente es la última con
  `estado = 1` y las anteriores quedan como historial. Cada venta guarda la moneda
  de pago, la tasa aplicada y el total en USD y en esa moneda.
- **Precio por margen:** `precio_usd = precio_distribuidor × (1 + margen/100)`,
  con el margen propio del producto o, si no tiene, el de su categoría. Cambiar el
  margen de una categoría recalcula sus productos sin margen propio. **Margen 0 =
  precio manual** (se escribe a mano y no se recalcula); así quedan todas las
  categorías tras la migración, hasta que el administrador fije su porcentaje.
- **Stock:** se valida y descuenta en la transacción de la venta (con bloqueo de
  filas). Registrar una compra a proveedor suma stock y, opcionalmente, actualiza
  el costo. El estado se recalcula solo: `Agotado` (sin stock), `Bajo Stock`
  (debajo del mínimo) o `Disponible`. Anular una venta devuelve el stock.
- **Facturas escaneadas:** JPG, PNG, WEBP o PDF de hasta `MAX_UPLOAD_MB` (10 MB),
  guardadas en `UPLOAD_DIR` (por defecto `uploads/`, fuera de git).
- El número de factura de venta es `F-00000001`, a partir de `id_venta`.
- `TIMEZONE` (`America/Caracas`) es la hora con la que se guardan las fechas y se
  delimitan los días de los reportes.

## Pantallas y API

| Panel | Pantalla | Endpoints |
|---|---|---|
| Admin | Inicio | `GET /reportes/dashboard`, `/reportes/top-productos`, `/reportes/stock-por-categoria` |
| Admin | Usuarios | `GET/POST /usuarios`, `PUT /usuarios/{id}`, `PATCH /usuarios/{id}/estado`, `PATCH /usuarios/{id}/password`, `DELETE /usuarios/{id}` (solo sin historial); tasas `GET /tasas/vigente`, `POST /tasas`; márgenes `GET/PUT /categorias` |
| Admin | Inventario | `GET /productos/admin` (sin los eliminados; `?incluir_eliminados=true` para verlos), `POST/PUT /productos` (al crear sin `sku`, se genera el siguiente de la categoría: `LUB-27` → `LUB-28`, con el mismo ancho de número; las categorías sin productos empiezan en `XXX-0001`; nunca repite un SKU), `GET /productos/siguiente-sku?id_categoria=` (vista previa), `DELETE /productos/{id}`: elimina el producto de la lista; si no tiene ventas ni compras se borra de la base, y si tiene historial se oculta (estado `Inactivo`) para conservar facturas y reportes y su SKU queda libre (`SKU~id`). También usa `/categorias`, `/marcas`, `/proveedores` |
| Admin | Inventario → Importar Excel | `POST /productos/importar` (multipart: `archivo`, `modo`, `si_existe`, `crear_faltantes`, `id_categoria_defecto`, `hoja`, `mapeo`, `formato`), `GET /productos/importar/reportes/{id}`, `GET /productos/importar/plantilla`, `GET /productos/importar/campos`. Ver "Carga masiva de inventario" |
| Admin | Catálogo | `GET /categorias?incluir_inactivos=true`, `POST/PUT/DELETE /categorias` (con margen de ganancia), lo mismo para `/marcas`; desactivar es baja lógica (`estado = 0`) y se puede reactivar. Una categoría con productos activos con stock no se puede desactivar (409, por `DELETE` o `PUT` con `estado = 0`) |
| Admin | Reportes | `/reportes/serie-ventas`, `/reportes/top-productos`, `/reportes/movimientos-stock`, `/reportes/ventas-por-categoria`, `/compras/entradas-recientes`, `/productos/stock-bajo`, `GET /ventas?dia=` y `?desde&hasta`, `POST /ventas/{id}/anular`, `/facturas` |
| Admin | Proveedores | `GET/POST/PUT /proveedores` (RIF, teléfono y correo obligatorios; el RIF debe empezar con V, E, J, P, G o C y se guarda como `J-12345678-9`), `DELETE /proveedores/{id}` (baja lógica; 409 si tiene compras pendientes de pago), `GET/POST /compras`, `PATCH /compras/{id}/pagado` |
| Admin | Auditoría | `GET /auditoria/` (filtros `desde`, `hasta`, `modulo`, `accion`, `id_usuario` (0 = sistema), `entidad`, `id_registro`, `id_operacion`, `buscar`; paginado), `GET /auditoria/filtros`, `GET /auditoria/exportar?formato=xlsx\|csv` (mismos filtros, máx. 100 000). Solo lectura. Ver "Auditoría" |
| Cajero | Punto de venta | `GET /ventas/mi-resumen`, `GET /tasas/vigente`, `GET /monedas`, `POST /ventas`, `GET /ventas?dia=` |
| Cajero | Inventario | `GET /productos` (solo lectura; agregar al ticket) |
| Cajero | Mis ventas | `GET /ventas?dia=` y `?desde&hasta` (el backend solo devuelve las propias) |

## Auditoría

`app/services/auditoria_service.py` registra **automáticamente**, con eventos del ORM,
cada alta, cambio o baja de productos, categorías, marcas, proveedores, usuarios,
tasas, ventas, compras y facturas escaneadas, sin depender de que cada endpoint lo
haga. Cada registro guarda la fecha, el usuario (nombre y rol de ese momento), el
módulo, la acción, una descripción legible ("Producto LUB-28 · Aceite: precio venta
USD 12.00 → 14.50"), el detalle campo por campo con el antes y el después (las llaves
foráneas con su nombre, no el ID), el origen ("Venta en punto de venta", "Importación
masiva: julio.xlsx"), la ruta de la API, la IP y un `id_operacion` que agrupa lo que
cambió en una misma petición (una venta y los movimientos de stock que causó).

- Se escribe en la **misma transacción** que el cambio: si se deshace, no queda
  registro; los pasos internos se combinan (la venta con número temporal queda como un
  solo "Venta F-00000012 registrada").
- Las **contraseñas nunca se guardan** (ni su hash): solo "contraseña cambiada".
- Acciones: crear, modificar, eliminar, desactivar, reactivar, movimiento de stock,
  cambio de contraseña, anular, cambio de pago, importar y exportar (las exportaciones
  de la auditoría también quedan registradas). También se registran los cambios hechos
  por `reset_password.py` y la recuperación de contraseña con código.
- **Solo lectura:** la API no tiene rutas para editar ni borrar, y en PostgreSQL un
  trigger rechaza `UPDATE`, `DELETE` y `TRUNCATE` sobre la tabla. No usa llave foránea
  hacia `usuarios`, para que el historial sobreviva aunque se elimine un usuario.

## Carga masiva de inventario (Excel / CSV)

Código en `app/services/importacion/` (una capa por archivo) y `app/routers/importacion.py`.

- **Archivos:** `.xlsx`/`.xlsm` (openpyxl en modo solo lectura, fila por fila) y
  `.csv` (detecta UTF-8, UTF-16 o Windows-1252 y el separador `;` `,` tabulador `|`).
  Hasta `MAX_IMPORT_MB` (15 MB) y `MAX_IMPORT_FILAS` (50 000). Un `.xls` antiguo se
  rechaza explicando cómo convertirlo. La fila de encabezados se busca entre las 15
  primeras, así que los títulos encima de la tabla no molestan.
- **Columnas:** no importan el orden ni el nombre exacto. Se reconocen por alias y por
  coincidencia aproximada ("P. Venta", "Precio de Venta ($)", "price" → precio de venta;
  "Exsitencia" → stock). Los tipos y límites (largo de varchar, decimales) se leen del
  modelo `Producto`. Las columnas sin destino (código de barras, precio en Bs, estado,
  totales) se informan como ignoradas, con su motivo. `mapeo` (`{"C": "precio_usd"}`)
  corrige cualquier columna a mano.
- **Validación por fila:** números con coma o punto decimal y símbolos (`$ 1.234,50`),
  enteros, Sí/No, largo máximo, errores de fórmula de Excel (`#N/A`). Categoría por
  nombre, código (`LUB`) o ID; marca por nombre; proveedor por nombre o RIF; sin
  importar mayúsculas, acentos ni singular/plural, y con sugerencia si no existe
  ("¿Quiso decir 'Frenos'?"). Con `crear_faltantes` se crean las categorías y marcas
  que falten (los proveedores no: exigen RIF, teléfono y correo).
- **Duplicados:** un SKU repetido en el archivo, o un producto sin SKU con el mismo
  nombre, categoría y marca que otro del archivo o de la base, es un error. Un SKU que
  ya existe se actualiza (solo las celdas con valor), se omite o se marca como error
  (`si_existe`). Sin SKU se genera el siguiente de la categoría, sin chocar con los SKU
  escritos más abajo en el mismo archivo.
- **Modos:** `validar` (vista previa; no guarda nada), `estricto` (si una fila falla no
  se guarda ninguna) y `parcial` (guarda las válidas). Se valida todo en una primera
  pasada y se escribe en una segunda, en una sola transacción con lotes de 500 filas;
  ante un error de la base se deshace todo (`ROLLBACK`).
- **Errores:** nunca un 500 sin explicación. Un archivo ilegible responde 413/415/422 con
  `{"detail", "detalles"}`. Los problemas de cada fila van en `errores` y
  `advertencias`, como "Fila 14, Columna 'Precio Venta': El valor 'N/A' no es un número
  válido.". Si los hay, `reporte_id` permite descargar un Excel con el resumen, cada
  error y la hoja "Filas a corregir" (las filas rechazadas tal como venían, para
  arreglarlas y volver a subirlas). Se guarda 24 horas en `UPLOAD_DIR/importaciones`.

Todas las rutas exigen `Authorization: Bearer <token>` (de `POST /auth/login` con
`correo` y `password`; vence a los `ACCESS_TOKEN_EXPIRE_MINUTES`). El frontend
guarda el token en `sessionStorage` y vuelve al login si el backend responde 401.

## Pruebas

`.\.venv\Scripts\python.exe -m pytest` (backend, SQLite en memoria) y
`cd frontend; npm run build` (verificación de tipos + compilación).
