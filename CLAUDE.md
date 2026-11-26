# Garmin dashboard: el motor (repo de Pedro)

Este repo es la **fuente de verdad del código** (`dashboard/`, `plan/gen_plan.py`, `garmin_connect.py`, `site/`,
workflows) y además guarda los archivos personales de Pedro (`config.yaml`, `plan/plan.json`, `plan/inbody.json`).
Otras personas usan `template/` (su propio repo chiquito) y reciben este código con la etiqueta `stable`.

## Flujo de trabajo

1. **Plan primero**: se aclaran y acuerdan los requisitos antes de construir (ver `docs/PLAN_V*.md`).
2. Sonnet ejecuta el plan por fases (un commit local por fase, `v4 F<n>: …`).
3. Opus revisa, hace push, verifica la página y mueve `stable`.

## Comandos

- Pruebas (el Python del sistema no tiene pytest): `.venv/bin/python -m pytest -q`
- Construir el sitio: `.venv/bin/python dashboard/build.py` (opciones: `--day AAAA-MM-DD`, `--out ruta`).
  Con `GARMIN_USER_DIR=<carpeta>` usa los archivos personales de otra persona (config.yaml, plan/, data/).
- Plan: `.venv/bin/python plan/gen_plan.py [--config …] [--out …]`. Validar privacidad: `.venv/bin/python dashboard/validar.py`.
- Reloj (solo Pedro): `.venv/bin/python reloj.py semana` simula; `--si` manda la semana del plan al reloj. Login una vez en la Terminal (`reloj.py login`); en Claude, `/reloj`.
- En local: `./run_local.sh` (baja datos, construye y sirve en http://localhost:8000).
- Deploy: push a `main` y `gh workflow run deploy.yml`; seguirlo con `gh run watch`.
- Antes de un push: `git pull --rebase`.
- Dependencias nuevas: instalarlas en `.venv` y fijarlas en `requirements.txt`.

## Reglas de seguridad

- **No leas, imprimas ni copies `.env`.** Correr `garmin_connect.py` (que lo lee por dentro) sí se vale.
- La key de Garmin nunca en el chat ni en archivos; solo como secreto `PERSONAL_API_KEY` de GitHub.
- El `data.json` público sale de una **lista blanca**: sin IDs de Garmin, nombres de actividades, GPS, nombre ni
  fecha de nacimiento. `dashboard/validar.py` y `tests/test_build.py` lo vigilan. Nunca un token de GitHub en el sitio.
- Lógica en Python; el JS solo pinta. Textos en español. Sin librerías de JS.

## La etiqueta `stable`

Los repos de amigos publican con el código de `stable`; Pedro publica con `main` (su commit). Se mueve **solo después
de ver bien la página de Pedro publicada** con ese commit:

```sh
git tag -f stable <sha> && git push -f origin stable
```

## Compatibilidad

El motor debe seguir funcionando con configs viejas: **toda clave nueva de `config.yaml` o de `data.json` lleva un
valor por defecto** (en `dashboard/defaults.yaml` o en `ajustes.cargar_config`) y el sitio tolera claves ausentes.
Los amigos reciben cada cambio sin tocar nada.

## Template

`template/` es lo que recibe cada amigo (`CLAUDE.md`, skills `/setup` `/ajustar` `/revision`, `config.example.yaml`,
workflows). Su `CLAUDE.md` y `.claude/skills/` los copia `motor.yml` desde `stable` en cada publicación: cambiar
instrucciones aquí las actualiza en todos los repos.

Los amigos nuevos crean su repo desde `pegongorasep/garmin-dashboard-template` (Actions apagado ahí). Si cambió
`template/`, después de mover `stable` corre `scripts/sync_template.sh` para dejar la plantilla igual.

## Web "Ahí la Llevas" (v5, carpeta `web/`)

FastAPI + SQLAlchemy/Alembic; reutiliza `dashboard/` y `plan/`. Cada persona tiene cuenta (solo por invitación); su repo
de GitHub es el tubo de datos (`motor.yml` → `scripts/subir.py` → `/api/tubo/*` con token OIDC) y la web calcula su
`data.json`. Planes: `docs/REQUISITOS_V5.md`, `docs/PLAN_V5.md`; decisiones: `docs/DUDAS.md` (sección v5).

- Dependencias de la web: `web/requirements.txt` (no van en `requirements.txt`, que instalan los repos de amigos).
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

