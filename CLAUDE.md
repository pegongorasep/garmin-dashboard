# Garmin dashboard: el motor (repo de Pedro)

Este repo es la **fuente de verdad del código** (`dashboard/`, `plan/motor_v6.py`, `garmin_connect.py`, `site/`,
workflows) y además guarda los archivos personales de Pedro (`config.yaml`, `plan/plan.json`, `plan/inbody.json`).
Las demás personas usan la web (Ahí la Llevas); su repo (creado desde `plantilla_v5/`) es solo el tubo de datos y corre
`motor.yml` con la etiqueta `stable`. Ya no existe GitHub Pages (retirado 2026-11-26).

## Flujo de trabajo

1. **Plan primero**: se aclaran y acuerdan los requisitos antes de construir (ver `docs/PLAN_V*.md`).
2. Sonnet ejecuta el plan por fases (un commit local por fase, `v4 F<n>: …`).
3. Opus revisa, hace push, verifica la página y mueve `stable`.

## Comandos

- Pruebas (el Python del sistema no tiene pytest): `.venv/bin/python -m pytest -q`
- Construir el sitio: `.venv/bin/python dashboard/build.py` (opciones: `--day AAAA-MM-DD`, `--out ruta`).
  Con `GARMIN_USER_DIR=<carpeta>` usa los archivos personales de otra persona (config.yaml, plan/, data/).
- Planes: solo el motor v6 (`plan/motor_v6.py`, piezas en `plan/pasos.py`; `.venv/bin/python -m plan.simulador` lo prueba con personas sintéticas). El `plan/plan.json` de Pedro es del motor anterior y se queda como está (el sitio lo sigue pintando). Validar privacidad: `.venv/bin/python dashboard/validar.py`.
  El motor solo genera el plan al crearlo (no hay ajuste semanal). «Repetir esta semana» y «Retomar desde la semana X» guardan
  `corrida.saltos` (`m.secuencia_de`), con vista previa en `/plan/propuesta.json`, y se deshacen solo en la misma semana.
  «Agregar carrera» = carrera de paso (`de_paso`, reemplaza la larga en `plan_efectivo`) o plan nuevo para esa carrera.
- Reloj (solo Pedro): `.venv/bin/python reloj.py semana` simula; `--si` manda la semana del plan al reloj. Login una vez en la Terminal (`reloj.py login`); en Claude, `/reloj`.
- En local: `./run_local.sh` (baja datos, construye y sirve en http://localhost:8000).
- Deploy de la web: push a `main` y `gh workflow run web.yml`; seguirlo con `gh run watch`. `deploy.yml` es el tubo de datos
  de Pedro (corre `motor.yml`: baja Garmin y sube a la web); no publica ningún sitio.
- Antes de un push: `git pull --rebase`.
- Dependencias nuevas: instalarlas en `.venv` y fijarlas en `requirements.txt`.

## Reglas de seguridad

- **No leas, imprimas ni copies `.env`.** Correr `garmin_connect.py` (que lo lee por dentro) sí se vale.
- La key de Garmin nunca en el chat ni en archivos; solo como secreto `PERSONAL_API_KEY` de GitHub. Las copias se vinculan únicamente al autorizar la GitHub App; ya no hay código de seis dígitos.
- El `data.json` público sale de una **lista blanca**: sin IDs de Garmin, nombres de actividades, GPS, nombre ni
  fecha de nacimiento. `dashboard/validar.py` y `tests/test_build.py` lo vigilan. Nunca un token de GitHub en el sitio.
- Lógica en Python; el JS solo pinta. Textos en español. Sin librerías de JS.

## La etiqueta `stable`

`stable` = el código del motor que usan los repos-tubo de las personas (`motor.yml`, `scripts/subir.py`,
`garmin_connect.py`, `dashboard/paquete.py`). Pedro corre con `main` (su commit). Se mueve **solo después de un despliegue
exitoso de la web**, y solo si cambió alguno de esos archivos:

```sh
git tag -f stable <sha> && git push -f origin stable
```

## Compatibilidad

El motor debe seguir funcionando con configs viejas: **toda clave nueva de `config.yaml` o de `data.json` lleva un
valor por defecto** (en `dashboard/defaults.yaml` o en `ajustes.cargar_config`) y el sitio tolera claves ausentes.
Los repos-tubo reciben cada cambio de `stable` sin tocar nada.

## Plantilla de repos nuevos

Vive en `plantilla_v5/` (solo el tubo de datos; ver más abajo). `template/` y Pages ya no existen.

## Web "Ahí la Llevas" (v5, carpeta `web/`)

FastAPI + SQLAlchemy/Alembic; reutiliza `dashboard/` y `plan/`. Cada persona tiene cuenta (solo por invitación); su repo
de GitHub es el tubo de datos (`motor.yml` → `scripts/subir.py` → `/api/tubo/*` con token OIDC) y la web calcula su
`data.json`. Planes: `docs/REQUISITOS_V5.md`, `docs/PLAN_V5.md`; decisiones: `docs/DUDAS.md` (sección v5).

- Dependencias de la web: `web/requirements.txt` (no van en `requirements.txt`, que instalan los repos-tubo).
- En local: `.venv/bin/alembic -c web/alembic.ini upgrade head`, luego `.venv/bin/python -m uvicorn web.app:app --port 8000`
  (SQLite en `web/dev.db`; sin `RESEND_API_KEY` las ligas de entrada salen en la consola).
- Admin: `python -m web.cli crear-admin <correo>`, `invitar [--nota X]`, `importar <correo> <carpeta> [--repo-id N]`.
  En producción corren como Cloud Run Job (`gcloud run jobs execute ahi-cli --args=...`), nunca con la cadena de la base en la compu.
- Variables: `DATABASE_URL`, `SECRET_KEY`, `BASE_URL`, `RESEND_API_KEY`, `CORREO_DE`, `OIDC_AUDIENCE`, `ADMIN_CORREO`
  (en Google Secret Manager; nunca en el repo ni en el chat).
- Seguridad: cookies HttpOnly/Secure/SameSite=Lax, CSRF en todo POST, tokens solo como hash, `permisos.puede_ver/puede_editar`
  en toda consulta de datos de una persona. La web no tiene ni pide la key de Garmin.
- Diseño: elegir no cambia la altura; solo expandir/colapsar (ranuras reservadas en `em`/`lh`, nunca cambios de `font-weight` al elegir).
- Rutas: `/admin` (invitaciones), `/mcp` (conector del coach para Claude), `/diseno` (catálogo). La plantilla de repos nuevos está en `plantilla_v5/` (`scripts/sync_template.sh` no la toca; repo destino `PLANTILLA_V5_URL` en `web/config.py`).
- Despliegue: `gh workflow run web.yml` (pruebas → imagen → Cloud Run, Workload Identity Federation).
- Respaldo: `respaldo.yml` (diario 09:00 UTC) deja `gs://<bucket>/respaldos/AAAA-MM-DD.sql.gz`. **Restaurar:**
  `gcloud storage cp gs://<bucket>/respaldos/<fecha>.sql.gz .`, `gunzip`, y con una base vacía de Neon
  `psql "$DATABASE_URL" < respaldo.sql` (la cadena se pega en la terminal desde Secret Manager, nunca en el chat);
  luego `alembic -c web/alembic.ini stamp head` si la tabla `alembic_version` no vino en el respaldo.

