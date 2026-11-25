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
