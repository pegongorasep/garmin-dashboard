#!/bin/sh
# Baja datos de Garmin, construye site/data.json y sirve el sitio en http://localhost:8000
# El catálogo del sistema de diseño sale en http://localhost:8000/catalogo.html (en la web es /diseno, solo admin).
set -e
cd "$(dirname "$0")"
.venv/bin/python garmin_connect.py
.venv/bin/python dashboard/build.py
.venv/bin/python -m http.server -d site 8000
