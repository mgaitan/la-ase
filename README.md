# A.S.E.

Sitio web de la **Asociacion Secreta de Escritores**, un club de lectura y escritura formado por Ema, Gael y Oliver.

Está hecho con **FastAPI**, **SQLite**, plantillas del lado del servidor y un panel simple para publicar contenido.

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
uv run fastapi dev
```

Nota: si ya se creó la base `data/ase.db`, cambiar estas variables no modifica el usuario existente. En ese caso tenés que borrar la base o actualizar el registro manualmente.

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
