# Plan de limpieza (2026-11-27)

**Estado (2026-11-28):** L1–L8 hechas y desplegadas (`stable` en 9e21e6d). De L8 quedó sin hacer, a propósito, agrupar
`web/` en subcarpetas: el mapa de AGENTS.md basta por ahora. Las 104 claves iguales en `en.yaml` son marcas, unidades y
palabras iguales en inglés (no faltan traducciones).

Objetivo: que el código no se vuelva un revoltijo. Sin cambios de comportamiento visibles; cada fase es un commit
`Limpieza L<n>: …` con las pruebas en verde (`.venv/bin/python -m pytest -q`).

## Ahora (bajo riesgo)

**L1. Higiene**
- `.gitignore`: agregar `.claude/worktrees/` (no borrar los worktrees: tienen trabajo sin integrar).
- `requirements.txt` (lo instalan los repos-tubo): quitar `pandas` (nadie lo usa) y `pytest`; fijar versiones (`==`) con las de `.venv`.
- `requirements-dev.txt` nuevo con `pytest` (y luego `ruff`); `web.yml` lo instala para las pruebas.
- `web/alembic.ini`: `path_separator = os` (quita la advertencia).
- Toca `requirements.txt` → mover `stable` tras el despliegue.

**L2. Docs vigentes**
- Mover a `docs/historial/` los planes ya ejecutados; dejar en `docs/` solo lo vigente.
- `docs/README.md`: índice de qué está vigente y qué es historia.
- README.md al día (sin «12 semanas», sitio estático ni «Actions → Deploy»).

**L3. AGENTS.md**
- `AGENTS.md` en la raíz: mapa de módulos (qué vive en cada archivo de `dashboard/`, `plan/`, `web/`, `site/`),
  recetas (clave nueva de config, texto i18n, ruta, migración, campo de `data.json`), invariantes y «no hagas».
- `CLAUDE.md`: quitar lo desactualizado («v4 F<n>») y lo que repita AGENTS.md; empezar con `@AGENTS.md`.

**L4. Linter**
- `ruff` en `requirements-dev.txt`, `ruff.toml` conservador (`F`, `E9`, `I`; línea larga no).
- Arreglar lo que salga (imports y variables sin usar) sin cambiar comportamiento; paso `ruff check .` en `web.yml`.
- Una pasada de `vulture` (sin instalarla fija) para quitar funciones muertas comprobadas con grep.

**L5. Adiós al modo «pages»**
- Pages se retiró: la web es el único modo. Quitar las ramas `modo != "web"` de `dashboard/` y `web/`,
  el texto «Corre /ajustar», y pasar a i18n los textos fijos de `build.py` («Plan terminado», «Ve a Ajustes…»).
- `publicar_pages` en `tubo.py`: se deja la respuesta si los tubos en `stable` la leen; si no, se quita.
- `run_local.sh` y `dashboard/build.py` siguen funcionando para Pedro.
- Hecho: la columna sin uso `usuarios.migrado` se quitó en la migración 0023.

## Después (cuando se integren las ramas de los worktrees)

**L6. Imports de paquete**: `from dashboard import metrics` en lugar de `sys.path.insert` (10 archivos);
`pyproject.toml` con `pythonpath` para pytest. Toca archivos de `stable`: probar con un tubo antes de mover la etiqueta.

**L7. Partir `metrics.py` y `build.py`** en subpaquetes por tema (zonas, recuperación, semana, corridas, carreras,
InBody / semana, actividad, progreso, ui), con re-exportación para no romper a nadie. `test_golden_semana` protege.

**L8. Menores**: `site/vistas.js` en plan/progreso, `pytest-xdist`, revisar claves de `en.yaml` sin traducir,
agrupar `web/` en subcarpetas si el mapa de AGENTS.md no basta.
