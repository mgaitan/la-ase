# A.S.E.

Sitio web de la **Asociacion Secreta de Escritores**, un club de lectura y escritura formado por Ema, Gael y Oliver.

Está hecho con **FastAPI**, **SQLite/PostgreSQL**, plantillas del lado del servidor y un panel simple para publicar contenido.

## Qué incluye

- Inicio editorial con identidad visual personalizada
- Blog con comentarios moderables
- Sección de publicaciones con categorías como `Cuentos`, `Poemas` y `Otros`
- Etiquetas filtrables
- Páginas fijas
- Menú configurable desde el panel
- Usuario administrador inicial

## Levantar en local

```bash
cp .env.example .env
uv sync
uv run fastapi dev
```

Abrir en `http://127.0.0.1:8000`.

## Acceso al panel

- URL: `/admin/login`
- Usuario inicial: el valor de `ASE_ADMIN_USERNAME`
- Contraseña inicial: el valor de `ASE_ADMIN_PASSWORD`

La app lee el archivo `.env` al arrancar. Un ejemplo mínimo:

```bash
SESSION_SECRET='una-clave-larga-y-privada'
ASE_ADMIN_USERNAME='admin'
ASE_ADMIN_PASSWORD='cambiar-esto'
ASE_EMA_PASSWORD='cambiar-esto'
ASE_GAEL_PASSWORD='cambiar-esto'
ASE_OLIVER_PASSWORD='cambiar-esto'
uv run fastapi dev
```

Nota: si ya se creó la base `data/ase.db`, cambiar estas variables no modifica el usuario existente. En ese caso tenés que borrar la base o actualizar el registro manualmente.

## Base de datos

En desarrollo local, si no definís `DATABASE_URL`, la app sigue usando SQLite en `data/ase.db`.

En producción, si definís `DATABASE_URL`, la app usa esa conexión. Esto sirve para Neon con una URL como:

```bash
DATABASE_URL='postgresql://usuario:password@ep-xxxxxx.us-east-1.aws.neon.tech/dbname?sslmode=require'
```

Si se pierde el `.env`, no se puede recuperar el valor de un secreto: hay que obtener una nueva URL de conexión desde Neon, crear nuevas credenciales R2 en Cloudflare y cargarlas de nuevo en FastAPI Cloud. Con la cuenta propietaria de la app:

```bash
uv run fastapi login
uv run fastapi cloud link
uv run fastapi cloud env set --secret DATABASE_URL 'postgresql://...'
uv run fastapi cloud env set --secret SESSION_SECRET "$(openssl rand -hex 32)"
uv run fastapi cloud env set --secret ASE_ADMIN_PASSWORD '...'
uv run fastapi cloud env set --secret ASE_EMA_PASSWORD '...'
uv run fastapi cloud env set --secret ASE_GAEL_PASSWORD '...'
uv run fastapi cloud env set --secret ASE_OLIVER_PASSWORD '...'
uv run fastapi cloud env set --secret R2_ACCOUNT_ID '...'
uv run fastapi cloud env set --secret R2_BUCKET_NAME 'la-ase-media'
uv run fastapi cloud env set --secret R2_ACCESS_KEY_ID '...'
uv run fastapi cloud env set --secret R2_SECRET_ACCESS_KEY '...'
```

Los cambios de variables se aplican en el próximo deploy. `SESSION_SECRET` nuevo invalida las sesiones activas; las contraseñas de usuarios ya existentes se cambian desde el panel.

Si la URL viene con esquema `postgres://`, la app también la adapta automáticamente.

## Estructura principal

- [`main.py`](/home/tin/lab/la_ase/ase/main.py): punto de entrada
- [`app/main.py`](/home/tin/lab/la_ase/ase/app/main.py): rutas públicas y panel
- [`app/models.py`](/home/tin/lab/la_ase/ase/app/models.py): modelos SQLAlchemy
- [`app/seed.py`](/home/tin/lab/la_ase/ase/app/seed.py): contenido inicial y usuario admin
- [`app/templates`](/home/tin/lab/la_ase/ase/app/templates): vistas HTML
- [`app/static/css/styles.css`](/home/tin/lab/la_ase/ase/app/static/css/styles.css): estilos

## Despliegue en FastAPI Cloud

El CLI disponible en este proyecto expone:

```bash
uv run fastapi deploy .
```

También admite desplegar contra una app existente:

```bash
uv run fastapi deploy . --app-id TU_APP_ID
```

Antes del deploy conviene definir al menos:

```bash
SESSION_SECRET='una-clave-larga-y-privada'
ASE_ADMIN_PASSWORD='una-clave-segura'
```

## Imagenes con Cloudflare R2

La app ya soporta subida real de imágenes desde el editor del panel usando Cloudflare R2.

Variables necesarias:

```bash
R2_ACCOUNT_ID='tu-account-id'
R2_BUCKET_NAME='la-ase-media'
R2_ACCESS_KEY_ID='tu-access-key-id'
R2_SECRET_ACCESS_KEY='tu-secret-access-key'
```

Las imágenes se suben al bucket y luego se sirven desde la propia app en `/media/...`, así que no hace falta exponer el bucket públicamente.

Al subirlas, la app ahora las redimensiona automáticamente para que ningún lado supere `1280px`, manteniendo proporción.

## Backups de producción

El workflow `.github/workflows/backup.yml` hace un backup diario de PostgreSQL en `backups/postgres/` dentro de R2 y elimina archivos de más de 30 días. También se puede ejecutar manualmente desde GitHub Actions.

Para activarlo, agregá estos secretos del repositorio: `DATABASE_URL`, `R2_ACCOUNT_ID`, `R2_BUCKET_NAME`, `R2_ACCESS_KEY_ID` y `R2_SECRET_ACCESS_KEY`. La URL de base y las credenciales R2 deben ser las mismas que usa la aplicación en producción.
