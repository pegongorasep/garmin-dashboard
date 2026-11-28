@AGENTS.md

# Garmin dashboard: el motor (repo de Pedro)

Este repo es la **fuente de verdad del código** y además guarda los archivos personales de Pedro (`config.yaml`,
`plan/plan.json`, `plan/inbody.json`). Las demás personas usan la web (Ahí la Llevas); su repo (creado desde `plantilla_v5/`)
es solo el tubo de datos y corre `motor.yml` con la etiqueta `stable`. Mapa, recetas e invariantes: AGENTS.md.

## Flujo de trabajo

1. **Plan primero**: se aclaran y acuerdan los requisitos antes de construir (ver `docs/PLAN_*.md`).
2. Sonnet ejecuta el plan por fases: un commit local por fase, con el nombre de la fase en el mensaje.
3. Opus revisa, hace push, verifica la página y mueve `stable`.

## Lo personal de Pedro

- `plan/plan.json` es del motor anterior y se queda como está (el sitio lo sigue pintando).
- Reloj (solo Pedro): `.venv/bin/python reloj.py semana` simula; `--si` manda la semana del plan al reloj. Login una vez en la Terminal (`reloj.py login`); en Claude, `/reloj`.
- Pedro corre con `main` (su commit), no con `stable`.
- `deploy.yml` es el tubo de datos de Pedro (corre `motor.yml`: baja Garmin y sube a la web); no publica ningún sitio.

## La etiqueta `stable`

`stable` = el código del motor que usan los repos-tubo de las personas (`motor.yml`, `scripts/subir.py`,
`garmin_connect.py`, `dashboard/paquete.py`). Se mueve **solo después de un despliegue exitoso de la web**, y solo si
cambió alguno de esos archivos:

```sh
git tag -f stable <sha> && git push -f origin stable
```

## Despliegue y producción

- Deploy de la web: push a `main` y `gh workflow run web.yml` (pruebas e imagen a la vez → Cloud Run, Workload Identity Federation); seguirlo con `gh run watch`.
- Admin en producción: Cloud Run Job (`gcloud run jobs execute ahi-cli --args=...`), nunca con la cadena de la base en la compu.
  Única excepción (decidida el 2026-11-27, mientras solo exista producción): `./run_web.sh`, que la tiene solo en memoria y
  nunca la imprime ni la guarda. Claude, al probar ahí, solo mira; para guardar algo usa únicamente la cuenta de Pedro y
  pregunta antes.
- Respaldo: `respaldo.yml` (diario 09:00 UTC) deja `gs://<bucket>/respaldos/AAAA-MM-DD.sql.gz`. **Restaurar:**
  `gcloud storage cp gs://<bucket>/respaldos/<fecha>.sql.gz .`, `gunzip`, y con una base vacía de Neon
  `psql "$DATABASE_URL" < respaldo.sql` (la cadena se pega en la terminal desde Secret Manager, nunca en el chat);
  luego `alembic -c web/alembic.ini stamp head` si la tabla `alembic_version` no vino en el respaldo.
- Rutas especiales de la web: `/admin` (invitaciones), `/mcp` (conector del coach para Claude), `/diseno` (catálogo).
- Planes y decisiones de la web: `docs/REQUISITOS_V5.md`, `docs/PLAN_V5.md`, `docs/DUDAS.md` (sección v5).
