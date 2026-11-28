#!/bin/sh
# Prueba la web (Ahí la Llevas) en http://localhost:8000.
#   ./run_web.sh              contra la base de PRODUCCIÓN (necesita gcloud y gh con sesión; no migra nada)
#   ./run_web.sh --temporal   contra una base SQLite local (web/dev.db), con las migraciones al día
# Opciones por entorno: PORT, GCP_PROYECTO, PYTHON (por defecto .venv/bin/python).
set -e
cd "$(dirname "$0")"
exec "${PYTHON:-.venv/bin/python}" scripts/web_local.py "$@"
