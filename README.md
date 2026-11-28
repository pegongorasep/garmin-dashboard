# Garmin · Ahí la Llevas

Este repo es el **motor** de Ahí la Llevas (https://ahilallevas.com): el dashboard de entrenamiento con datos de Garmin Connect
(semáforo de recuperación, semana, plan y tendencias), el generador de planes (`plan/motor_v6.py`), la web con cuentas por
invitación (`web/`, FastAPI) y el workflow reutilizable `.github/workflows/motor.yml`, el tubo de datos que baja Garmin y lo sube
a la web. Cada persona tiene su propio repo-tubo, creado desde [`plantilla_v5/`](plantilla_v5/). Mi configuración personal vive en
`config.yaml` y `plan/`.

## Correrlo en local

1. Entorno: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt`
2. Copia `.env.example` a `.env` y pon tu `PERSONAL_API_KEY` (solo lectura de Garmin).
3. Motor y dashboard: `./run_local.sh` baja los datos, construye `site/data.json` y sirve en http://localhost:8000.
4. Web: `pip install -r web/requirements.txt`, luego `.venv/bin/alembic -c web/alembic.ini upgrade head` y
   `.venv/bin/python -m uvicorn web.app:app --port 8000` (SQLite en `web/dev.db`).

## Pruebas

`.venv/bin/python -m pytest -q`

## Documentos

- [`CLAUDE.md`](CLAUDE.md): comandos, flujo de trabajo y reglas del proyecto.
- [`docs/README.md`](docs/README.md): índice de documentos vigentes; `docs/historial/` guarda los planes ya ejecutados.
