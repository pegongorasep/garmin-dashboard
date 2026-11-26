# Garmin · base aeróbica

Dashboard personal que une mi CrossFit con 3 corridas por semana para construir base aeróbica, con un plan de 12 semanas. Lee los datos de la API personal de Garmin Connect (solo lectura) y publica un sitio estático con el semáforo de recuperación, la semana, el plan y las tendencias.

## Motor

Este repo es el **motor**: el código del dashboard, el generador de plan por nivel (novato, intermedio, corredor), la web y el workflow reutilizable `.github/workflows/motor.yml` (el tubo de datos: baja Garmin y sube a la web). Mi configuración vive en `config.yaml` y `plan/`. GitHub Pages ya no se usa (retirado 2026-11-26).

## Ahí la Llevas (v5)

Web con cuentas por invitación (`web/`, FastAPI): cada persona conecta su repo de GitHub (creado desde [`plantilla_v5/`](plantilla_v5/)), que sube sus datos a la web; la web calcula su dashboard, su plan y su coach. Ver [`CLAUDE.md`](CLAUDE.md) y `docs/PLAN_V5.md`.

Sitio: https://ahilallevas.com

## Correrlo en local

1. Crea el entorno: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Copia `.env.example` a `.env` y pon tu `PERSONAL_API_KEY`. La configuración personal está en `config.yaml`.
3. Corre `./run_local.sh`: baja los datos, construye `site/data.json` y sirve el sitio en http://localhost:8000.
4. Pruebas: `.venv/bin/python -m pytest -q`

## Actualizar el sitio

Se actualiza solo 3 veces al día (7:00, 13:00 y 19:00 hora de Mérida). Para forzarlo: en GitHub, **Actions → Deploy → Run workflow**.

## Documentos

- [`docs/REQUISITOS.md`](docs/REQUISITOS.md): qué hace y por qué.
- [`docs/PLAN_ENTRENAMIENTO.md`](docs/PLAN_ENTRENAMIENTO.md): las 12 semanas.
- [`docs/PLAN_CONSTRUCCION.md`](docs/PLAN_CONSTRUCCION.md): cómo se construyó.
