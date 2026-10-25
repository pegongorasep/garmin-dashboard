# Garmin · base aeróbica

Dashboard personal que une mi CrossFit con 2 corridas por semana para construir base aeróbica, con un plan de 12 semanas. Lee los datos de la API personal de Garmin Connect (solo lectura) y publica un sitio estático con el semáforo de recuperación, la semana, el plan y las tendencias.

Sitio: https://pegongorasep.github.io/garmin-dashboard/

## Correrlo en local

1. Crea el entorno: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. Copia `.env.example` a `.env` y pon tu `PERSONAL_API_KEY`.
3. Corre `./run_local.sh`: baja los datos, construye `site/data.json` y sirve el sitio en http://localhost:8000.
4. Pruebas: `.venv/bin/pytest`

## Actualizar el sitio

Se actualiza solo 3 veces al día (7:00, 13:00 y 19:00 hora de Mérida). Para forzarlo: en GitHub, **Actions → Deploy → Run workflow**.

## Documentos

- [`docs/REQUISITOS.md`](docs/REQUISITOS.md): qué hace y por qué.
- [`docs/PLAN_ENTRENAMIENTO.md`](docs/PLAN_ENTRENAMIENTO.md): las 12 semanas.
- [`docs/PLAN_CONSTRUCCION.md`](docs/PLAN_CONSTRUCCION.md): cómo se construyó.
