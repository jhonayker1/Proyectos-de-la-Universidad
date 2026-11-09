# Inventario y ventas de repuestos (Cauchos Rey)

- **Backend** (`app/`): FastAPI sobre la base PostgreSQL existente `cauchos_rey_def`.
- **Frontend** (`frontend/`): una sola app React (Vite + Tailwind) con login único;
  según el rol abre el panel de **administrador** (`/admin`) o de **cajero** (`/cajero`).
  Es la adaptación de los diseños de Figma que estaban en `Admin/` y `Cajero/`.

## Puesta en marcha

1. **Base de datos.** El backend usa las tablas de `cauchos_rey_def` (`usuarios`,
   `roles`, `productos`, `categorias`, `marcas`, `proveedores`, `monedas`,
   `tasas_cambio`, `ventas`, `detalles_venta`) y las que agrega
   `migrations/002_frontend.sql` (márgenes, datos de proveedor, `compras`,
   `detalles_compra`, `facturas_imagenes`). La migración solo agrega columnas y
   tablas y se puede ejecutar más de una vez:
   ```
   psql -h localhost -U postgres -d cauchos_rey_def -f migrations/002_frontend.sql
   ```
   Para una base nueva vacía: `database.sql` y luego la migración.
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
| Admin | Inventario | `GET /productos/admin`, `POST/PUT/DELETE /productos`, `/categorias`, `/marcas`, `/proveedores` |
| Admin | Catálogo | `GET /categorias?incluir_inactivos=true`, `POST/PUT/DELETE /categorias` (con margen de ganancia), lo mismo para `/marcas`; desactivar es baja lógica (`estado = 0`) y se puede reactivar |
| Admin | Reportes | `/reportes/serie-ventas`, `/reportes/top-productos`, `/reportes/movimientos-stock`, `/reportes/ventas-por-categoria`, `/compras/entradas-recientes`, `/productos/stock-bajo`, `GET /ventas?dia=` y `?desde&hasta`, `POST /ventas/{id}/anular`, `/facturas` |
| Admin | Proveedores | `GET/POST/PUT /proveedores`, `GET/POST /compras`, `PATCH /compras/{id}/pagado` |
| Cajero | Punto de venta | `GET /ventas/mi-resumen`, `GET /tasas/vigente`, `GET /monedas`, `POST /ventas`, `GET /ventas?dia=` |
| Cajero | Inventario | `GET /productos` (solo lectura; agregar al ticket) |
| Cajero | Mis ventas | `GET /ventas?dia=` y `?desde&hasta` (el backend solo devuelve las propias) |

Todas las rutas exigen `Authorization: Bearer <token>` (de `POST /auth/login` con
`correo` y `password`; vence a los `ACCESS_TOKEN_EXPIRE_MINUTES`). El frontend
guarda el token en `sessionStorage` y vuelve al login si el backend responde 401.

## Pruebas

`.\.venv\Scripts\python.exe -m pytest` (backend, SQLite en memoria) y
`cd frontend; npm run build` (verificación de tipos + compilación).
