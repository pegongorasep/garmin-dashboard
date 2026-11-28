# Plan de calidad (2026-11-28)

**Estado:** C1–C6 hechas y desplegadas el 2026-11-28. Solo `/mcp` conserva montaje explícito (`montar_mcp`: sub-app ASGI).

Sigue a `PLAN_LIMPIEZA.md` (cerrado). Sin cambios de comportamiento visibles; un commit `Calidad C<n>: …` por fase,
`ruff check .` y `.venv/bin/python -m pytest -q -n auto` en verde. Fuera de alcance: el `TODO(F4+)` de `web/plan_nuevo.py`.

**C1. Dependencias y HSTS**
- `.github/dependabot.yml`: pip (`/` y `/web`, semanal, agrupado) y github-actions (mensual).
- `web.yml`: paso `pip-audit -r requirements.txt -r web/requirements.txt` (pip-audit fijo en `requirements-dev.txt`).
- `web/app.py`: `Strict-Transport-Security: max-age=31536000; includeSubDomains` junto a la CSP (solo fuera de local/http).

**C2. Utilerías de fechas y formularios sin duplicar**
- `dashboard/fechas.py`: `lunes(d)` (y lo que sea idéntico de `_lunes`/`monday`); `semanal.py` tiene `_lunes` dos veces.
- `web/formularios.py`: lectura de enteros y fechas de formularios con su error i18n, si las firmas se pueden unir sin
  cambiar mensajes. Lo que no sea idéntico se queda (no forzar).

**C3. Ayudas de pruebas**
- `tests/ayudas.py` con lo que las pruebas importan unas de otras (`test_web_cuentas`, `test_web_ajustes`,
  `test_conexion`, `test_web_tubo`…). Quitar de `ruff.toml` los ignores F401/F811/F841 de `tests/` si ya no hacen falta.

**C4. CSP sin `'unsafe-inline'` en scripts**
- Los `<script>` en línea de `web/plantillas/` y `site/*.html` pasan a archivos `.js`; `onclick=` y similares a
  `addEventListener`. Datos que el script necesita: atributos `data-*` o `<script type="application/json">`.
- `script-src 'self'`. Revisar en Chrome cada página (consola sin violaciones de CSP).

**C5. Rutas con `APIRouter`**
- C5a: `web/deps.py` con las dependencias (`get_db`, `actual`, `render`, `formulario`, `settings`) leídas de
  `request.app.state`; piloto con `web/coach.py` (rutas como funciones de primer nivel en un `router`).
- C5b/C5c: el resto de los módulos en dos tandas; `crear_app` solo registra routers y middlewares. AGENTS.md al día
  (convención y receta de ruta nueva). El orden de registro se conserva (`/plan/nuevo` antes de `/plan/{...}`,
  `/{archivo}` al final).

**C6. Fachadas más delgadas**
- El código de `dashboard/`, `web/` y `plan/` importa de `dashboard.metricas.*` / `dashboard.construir.*` en lugar de
  `metrics`/`build` cuando sea directo; las fachadas se quedan para pruebas y compatibilidad.
