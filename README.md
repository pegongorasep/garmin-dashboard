# Garmin · base aeróbica

Dashboard personal que une mi CrossFit con 3 corridas por semana para construir base aeróbica, con un plan de 12 semanas. Lee los datos de la API personal de Garmin Connect (solo lectura) y publica un sitio estático con el semáforo de recuperación, la semana, el plan y las tendencias.

## Motor y plantilla (para otras personas)

Este repo es el **motor**: el código del dashboard, el generador de plan por nivel (novato, intermedio, corredor) y el workflow reutilizable `.github/workflows/motor.yml`. Mi configuración vive en `config.yaml` y `plan/`.

Cada persona tiene su propio repo chiquito (creado desde [`template/`](template/)) con su `config.yaml`, su plan y su propio GitHub Pages. Su workflow llama a `motor.yml` con la etiqueta `stable`, así que recibe las mejoras sin tocar nada.

**Para invitar a alguien:** pásale el repo de la plantilla (o el contenido de `template/`) y su [`README`](template/README.md): crea su repo con "Use this template", lo abre con Claude Code y escribe `/setup`. Yo muevo `stable` cuando probé el cambio en mi página (ver [`CLAUDE.md`](CLAUDE.md)).

## Ahí la Llevas (v5)

Web con cuentas por invitación (`web/`, FastAPI): cada persona conecta su repo de GitHub (creado desde [`plantilla_v5/`](plantilla_v5/)), que sube sus datos a la web; la web calcula su dashboard, su plan y su coach. Ver [`CLAUDE.md`](CLAUDE.md) y `docs/PLAN_V5.md`.

Sitio: https://pegongorasep.github.io/garmin-dashboard/

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
