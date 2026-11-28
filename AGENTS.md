# AGENTS.md: guía para cualquier agente que llegue sin contexto

## 1. Qué es

- **Ahí la Llevas** (https://ahilallevas.com): web de entrenamiento con datos de Garmin Connect. Cuentas solo por invitación.
- Este repo es el **motor** (Python en `dashboard/` y `plan/`, JS que solo pinta en `site/`) y la **web** (`web/`, FastAPI + SQLAlchemy/Alembic).
- Cada persona tiene un repo-tubo de GitHub (creado desde `plantilla_v5/`) que baja sus datos de Garmin y los sube a la web.
- La web guarda los datos en la base (SQLite en local, Postgres/Neon en producción) y calcula el `data.json` de cada quien al pedirlo.
- Idioma: español en código, comentarios y textos; hay catálogo es/en (`i18n/`).

```
Garmin Connect
  -> repo-tubo de la persona: motor.yml (código en la etiqueta `stable`)
       -> garmin_connect.py  (baja a data/)
       -> scripts/subir.py   (arma el paquete con dashboard/paquete.py, lista blanca por campo)
  -> web: POST /api/tubo/* (token OIDC de GitHub Actions)  [web/tubo.py -> web/datos.py -> tabla datos_garmin]
  -> web/calculo.py (config + plan + datos de la base) -> dashboard/build.py -> data.json (lista blanca)
  -> GET /data.json -> site/*.js lo pinta (app.js, vista_*.js, vistas.js, componentes.js, charts.js)
```

Local de Pedro: `garmin_connect.py` -> `dashboard/build.py` -> `site/data.json` -> `run_local.sh` lo sirve.

## 2. Mapa de módulos

Convención: módulos nuevos = `router = APIRouter()` con rutas de primer nivel y dependencias de `web/deps.py` (`get_db`, `actual`, `render`, `formulario`, `settings`; leen `request.app.state`), registrado con `app.include_router(x.router)` en `crear_app()` (ya así: `coach.py`). Los viejos con `montar(app, ...)` (rutas como closures) se están migrando. Sin ninguno de los dos = lógica pura o utilería.

Imports: siempre de paquete (`from dashboard import metrics as m`, `from plan import pasos`, `from scripts import subir`); nada de `sys.path` ni imports planos. Solo los puntos de entrada que se corren como archivo (`garmin_connect.py`, `reloj.py`, `dashboard/build.py`, `scripts/subir.py`, `scripts/web_local.py`) insertan la raíz del repo en `sys.path` una vez; `pytest` usa `pythonpath = ["."]` (`pyproject.toml`).

### Raíz
- `garmin_connect.py`: descarga historial de la Garmin Connect Personal API a `data/` (lo corre el tubo).
- `reloj.py`: manda entrenamientos al reloj; solo la Mac de Pedro (usa `dashboard/reloj_plan.py`).
- `run_local.sh`: baja datos, construye y sirve en :8000. `Dockerfile`: imagen de la web (sin `data/`, config ni plan personal).
- `config.yaml`, `plan/plan.json`, `plan/inbody.json`, `data/`: archivos personales de Pedro.

### `dashboard/` (motor; funciones puras salvo donde se indica)
- `build.py`: `build`/`_build`/`main`: convierte data/ + plan + config en `data.json` (lista blanca); también escribe `site/i18n/*.json`. Re-exporta `construir/`; el código nuevo importa de `dashboard.construir.*`.
  - `construir/cargar.py`: leer `data/`, el plan y los JSON personales.
  - `construir/comun.py`: `r1`/`r2`, `monday`, `light_on`, `week_assignment`, `rw_json`, fin del plan.
  - `construir/sesiones.py`: pasos, rampas, rachas, estructura de calidad y etiquetas de sesión.
  - `construir/semanas.py`: marcas, semanas del plan y de la vista, resumen de la semana pasada, retomar.
  - `construir/actividades.py`: corridas, detalle y curva de FC, actividades del día, historial, carreras.
  - `construir/progreso.py`: pruebas, mejora, números, días y detalles.
  - `construir/ui.py`: textos y categorías de la interfaz, eventos del plan, huellas/avisos, titular de hoy.
- `metrics.py`: fachada que re-exporta `metricas/`; sin I/O ni reloj. El código nuevo importa de `dashboard.metricas.*`.
  - `metricas/comun.py`: clasificar actividades, `day_of`, `id_de`, `ZONAS`.
  - `metricas/zonas.py`: zonas de FC, perfil Garmin, minutos por zona, FC máxima.
  - `metricas/carga.py`: esfuerzo, RPE, carga de sesión/semana, distribución.
  - `metricas/recuperacion.py`: FC en reposo, HRV, sueño, semáforo, motivos, ayer duro.
  - `metricas/semana.py`: secuencia de semanas, asignar sesiones, tarjeta de hoy, plan vs real.
  - `metricas/corridas.py`: detalle, run/walk, ritmos, deriva, progreso, encadenadas.
  - `metricas/carreras.py`: pruebas, carreras, mejores marcas.
  - `metricas/inbody.py`: composición y hoja InBody.
- `semanal.py`: cifras de la semana y del plan (cumplimiento, ritmo, volumen, rachas) para Hoy, Plan y Progreso.
- `fechas.py`: `lunes(d)`, única definición del lunes de la semana (`monday` de `construir/comun.py` es alias).
- `ajustes.py`: lee `config.yaml` + `defaults.yaml` y devuelve el dict plano (`cargar_config`, `normalizar_config`).
- `defaults.yaml`: valores por defecto del motor (umbrales, categorías, `sin_plan`).
- `paquete.py`: el paquete que sube cada repo; archivos de `data/` reducidos a lista blanca (ids opacos).
- `validar.py`: revisa `data.json` (claves permitidas/prohibidas, URLs, íconos); también CLI.
- `i18n.py`: catálogo de textos es/en compartido por motor y web (`t`, `tt`, `usar`, `catalogo_sitio`, `escribir_json`).
- `plan_i18n.py`: textos del plan (nombres de sesión, notas de paso) en el idioma en curso.
- `ayuda.py`: página de ayuda armada con config y plan de cada persona.
- `tipos.py`: catálogo de tipos de entreno y silueta de cada sesión.
- `reloj_plan.py`: arma los entrenamientos del plan en el formato de Garmin (sin red).

### `plan/` (motor de planes v6; solo se genera al crear el plan)
- `motor_v6.py`: genera el plan con las reglas de `docs/INVESTIGACION_PLANES.md`; `secuencia_de` aplica `corrida.saltos`.
- `pasos.py`: piezas básicas (paso = zona + minutos, sesión, versión suave, redondeos); las usan el motor y el editor de sesiones.
- `nivel.py`: nivel de la persona calculado desde sus actividades de Garmin.
- `simulador.py` + `personas.yaml`: personas sintéticas y reglas de seguridad sobre un plan (`python -m plan.simulador`).
- `convertir_viejo.py`: convierte un plan del motor anterior (`plan.json`) al formato v6.
- `plan.example.json`: ejemplo que copia la imagen; `plan.json` e `inbody.json` son de Pedro.

### `web/`
Cuentas y entrada
- `app.py`: `crear_app()`; login, CSRF, idioma, páginas base, `/data.json`, `/a/<id>/` (sitio del coach), estáticos, `/i18n/*.json`. Rutas.
- `auth.py`: invitaciones, ligas de entrada, sesiones y CSRF (tokens solo como hash). Lógica.
- `google.py`: login con Google (OIDC + PKCE; sigue exigiendo invitación). Rutas.
- `correo.py`: envío con Resend. `config.py`: `Settings` desde variables de entorno. `db.py`: motor y sesiones SQLAlchemy.
- `deps.py`: dependencias de las rutas con `APIRouter` (`get_db`, `actual`, `render`, `formulario`, `settings`) desde `app.state`. `modelos.py`: tablas. `permisos.py`: `puede_ver`/`puede_editar` y permisos sociales. `errores.py`: errores de formulario con clave i18n.
- `onboarding.py`: guía de Garmin `/bienvenida`. Rutas. `primer_inicio.py`: lo que Hoy ofrece a quien llega sin nada. Lógica.
- `perfil.py`: nombre, apellido y foto. Rutas. `privacidad.py`: versión del aviso y rutas públicas. Constantes.
- `cuenta.py`: descargar mis datos (ZIP) y borrar cuenta. Rutas. `admin.py`: `/admin` (invitaciones; solo admin). Rutas.
- `cli.py`: `python -m web.cli crear-admin|invitar|importar`. `importar.py`: carga los archivos personales de una carpeta a la base.

Conexión con Garmin y GitHub
- `tubo.py`: `/api/tubo/*`: recibe el paquete con token OIDC y da instrucciones al workflow. Rutas.
- `datos.py`: guarda y lee los datos de Garmin (`datos_garmin`; subir es upsert, nunca borra). Lógica.
- `github_app.py`: cliente mínimo de la GitHub App. `conexion.py`: instalar la App en el repo de la persona y disparar corridas. Rutas.
- `sincronizar.py`: estado de cada sincronización (lógica). `sync_web.py`: `/api/sync` (botón Sincronizar y franja). Rutas.
- `garmin_key.py`: `/garmin/key`, guía cuando Garmin rechaza la key. Rutas.

Plan, ajustes y datos propios
- `calculo.py`: arma el `data.json` de una persona con el motor a partir de la base (`calcular`, `calcular_propuesta`). Lógica.
- `plan_vivo.py`: metas, eventos, repetir/retomar, escalera y edición de sesiones (`plan_efectivo`). Lógica pura.
- `plan_web.py`: `/plan` y `/plan/sesion/<n>/<id>`. Rutas. `plan_nuevo.py`: `/plan/nuevo` (Motor v6, guiado). Rutas.
- `ajustes_web.py`: `/ajustes`, `/historial` (deshacer) y `/cuerpo` (InBody); `resolver` decide con `puede_editar`. Rutas.
- `cambios.py`: TODA escritura a `ajustes`, `planes` o `inbody` pasa por `aplicar_cambio` (quién, vía, antes/después, deshacer). Lógica.
- `actividad_web.py`: `/actividad/nueva|{id}|borrar`. Rutas. `manual.py`: validación y forma Garmin de las actividades a mano. Lógica.
- `semana_plan.py`: semana contra el plan, compartida por perfil y tarjetas de grupo. Lógica.

Social
- `grupos.py`: crear, unirse con liga, salir, pausar lo compartido. Rutas. `grupos_resumen.py`: tarjetas de avance (solo campos de lista blanca). Lógica.
- `feed.py`: feed de «Juntos», reacciones y comentarios. Rutas. `persona.py`: `/api/juntos/persona/<id>`. Rutas.

Coach y MCP
- `coach.py`: `/coach`, dar y quitar acceso a un coach. Rutas.
- `oauth.py`: OAuth 2.1 del conector MCP (metadatos, registro dinámico, PKCE) y `/conexiones`. Rutas.
- `mcp_servidor.py`: servidor MCP en `/mcp` con las herramientas del coach. Rutas.

Páginas varias
- `aprende.py`: «Aprende», artículos de `aprende/es/<slug>.yaml`. Rutas.
- `plantillas/`: Jinja2 (una por página; las `_x.html` son parciales; `base.html`, `componentes.html`, `_nav.html` compartidas).
- `estaticos/`: `dialogos.js`, `instalar.js`, `paginas.css` de las páginas con Jinja (se sirven en `/estaticos`).
- `alembic/`, `alembic.ini`: migraciones. `requirements.txt`: dependencias de la web.

### `site/` (el JS solo pinta; sin librerías)
- `index.html`: página del dashboard. `catalogo.html`: catálogo del sistema de diseño (en la web, `/diseno`, solo admin).
- `base.js`: utilidades compartidas, `T("sitio.clave")` de i18n. `app.js`: Hoy, ayuda, grupo y la navegación.
- `vista_comun.js` (tarjeta con vistas, unidad min/km), `vista_plan.js`, `vista_progreso.js` (Corridas, Cuerpo), `vista_grupo.js` (Juntos) y `vistas.js` (ayuda, tema, rutas, menú y arranque; va al final). Scripts clásicos con globales: el orden de carga es el de `index.html`, `plan_nuevo.html` y `sw.js`. `charts.js`: gráficas SVG a mano.
- `componentes.js` (objeto `DS`) y `componentes.css`: componentes del sistema de diseño. `styles.css`: layout propio de la app.
- `franja.js`: franja de sincronización (`window.Franja`). `actualizar.js`: registra el service worker y ofrece la versión nueva.
- `sw.js`: service worker (`VERSION`, lista `ESTATICOS`). `manifest.webmanifest` e íconos PNG: la PWA.
- `tokens.css` e `iconos.js`: GENERADOS por `scripts/tokens.py`; no se editan a mano. `fuentes/`, `dibujo-github.svg`: recursos.
- `data.json` (generado por build; no se versiona) e `i18n/{es,en}.json` (generados por build; sí se versionan).

### Otras carpetas
- `i18n/`: `es.yaml` (referencia) y `en.yaml`. `aprende/es/`: artículos. `diseno/`: `tokens.json`, `iconos/*.svg`, `LEEME.md`.
- `scripts/`: `subir.py` (lo corre `motor.yml` en el tubo), `tokens.py` (genera `tokens.css` e `iconos.js`), `iconos_pwa.py` (íconos PNG).
- `plantilla_v5/`: solo el README de la plantilla de repos-tubo nuevos (repo destino `PLANTILLA_V5_URL` en `web/config.py`).
- `.github/workflows/`: `web.yml` (pruebas, imagen, Cloud Run), `deploy.yml` (tubo de Pedro), `motor.yml` (tubo de todos, vía `stable`), `respaldo.yml`, `keepalive.yml`.
- `tests/`: pytest (`conftest.py` trae `web_ctx`); `docs/`: planes y requisitos (`docs/README.md` dice qué está vigente).

## 3. Recetas

**Clave nueva de `config.yaml`**
1. Pon su valor por defecto en `dashboard/defaults.yaml` (o con `cfg.get("x", default)` en `ajustes.normalizar_config`). Sin default no se acepta: configs viejas deben seguir funcionando.
2. Léela en `normalizar_config` (`dashboard/ajustes.py`), valida y truena con `ConfigError` (mensaje en español); un valor viejo o raro cae al default.
3. Si la web debe poder editarla: `web/ajustes_web.py` (formulario) y pasa por `cambios.aplicar_cambio`. La web arma el config con `calculo.config_de`.
4. Prueba en `tests/test_ajustes.py`; agrega el caso de config sin la clave.

**Campo nuevo de `data.json`**
1. Calcúlalo en Python (`dashboard/build.py`, `metrics.py` o `semanal.py`); el JS solo lo pinta.
2. Si es una clave de primer nivel, agrégala a `CLAVES` en `dashboard/validar.py` (lista blanca; sin eso `validar` y `tests/test_build.py` fallan). Las obligatorias van en `OBLIGATORIAS`.
3. Nunca ids de Garmin, nombres de actividades, GPS ni nada de `PROHIBIDAS` (`validar.py`); URLs solo las permitidas (`ui.acciones_url`, `ui.repo_estado`).
4. Si viene de un campo nuevo de Garmin, súbelo también en la lista blanca de `dashboard/paquete.py` (y documéntalo en su docstring).
5. El sitio debe tolerar la clave ausente (datos viejos). Pruebas: `tests/test_build.py`; revisa `test_privacidad_*` y `dashboard/validar.py`.

**Texto nuevo**
1. Agrega la clave plana con puntos en `i18n/es.yaml` Y en `i18n/en.yaml` (mismas claves y mismas variables `{x}`; `tests/test_i18n.py` lo exige).
2. Python: `i18n.t(clave, idioma, **vars)`; en el cálculo del motor, `i18n.tt(clave)`; en plantillas, `t("clave")`.
3. Para el JS, la clave debe empezar con `sitio.`; se usa con `T("sitio.x", {var})`.
4. `site/i18n/es.json` y `en.json` se generan: corre `.venv/bin/python dashboard/build.py` y versiona los dos (la prueba falla si están desactualizados). La web los sirve en `/i18n/<idioma>.json` desde el catálogo.
5. Cambió algo del sitio: sube `VERSION` en `site/sw.js` (ver la receta de archivo nuevo).

**Ruta nueva de la web**
1. Crea `web/<tema>.py` con `router = APIRouter()` y funciones de primer nivel que importan de `web/deps.py` (copia `web/coach.py`); regístralo con `app.include_router(<tema>.router)` en `crear_app()` de `web/app.py`. El orden importa: `/plan/nuevo` va antes de `/plan/{...}`; `@app.get("/{archivo}")` va siempre al final.
2. Todo POST empieza con `form = await formulario(request)` (verifica el CSRF, 403 si falla); en plantillas el campo es `csrf` (viene de `render`). Sin sesión: `RedirectResponse("/entrar", 303)`.
3. Toda consulta de datos de una persona pasa por `permisos.puede_ver` / `puede_editar` (si no puede: 404). Páginas de edición: `ajustes_web.resolver(db, usuario, atleta_id)`; la ruta se repite bajo `/a/{atleta_id}/...` para el coach.
4. Toda escritura a `ajustes`, `planes` o `inbody` va por `cambios.aplicar_cambio`.
5. Textos por i18n, plantilla en `web/plantillas/`. Rutas públicas o de API que no deba cachear el service worker: `sw.js` ya ignora `/api`, `/oauth`, `/mcp`, `/admin`.
6. Prueba en `tests/test_web_<tema>.py` con la fixture `web_ctx`.

**Migración Alembic**
1. Edita la tabla en `web/modelos.py` (fechas en UTC naive; JSON con `sa.JSON`).
2. Crea `web/alembic/versions/00NN_nombre.py` con la siguiente numeración (hoy la última es `0023`); `revision = "00NN"`, `down_revision = "00NN-1"`, con `upgrade()` y `downgrade()`.
3. Aplícala en local: `.venv/bin/alembic -c web/alembic.ini upgrade head`. En producción corre sola al arrancar (el `CMD` del Dockerfile; máximo 1 instancia).
4. Columnas nuevas con `nullable=True` o valor por defecto. Si la tabla guarda algo de una persona, revisa `web/cuenta.py` (descarga y borrado de cuenta).

**Archivo nuevo de `site/`**
1. Agrégalo a `ESTATICOS_SITE` en `web/app.py` (si no, `/archivo` da 404) y, si carga en las páginas, a `ESTATICOS` en `site/sw.js`.
2. Cárgalo en `site/index.html` (y en `catalogo.html` si aplica); orden: `base.js` primero.
3. Sube `VERSION` en `site/sw.js` (`"v82"` -> `"v83"`) y actualiza la aserción en `tests/test_autorizar.py` (busca `VERSION = "v`). Es lo que hace que la app abierta ofrezca actualizar.
4. Colores y espacios solo con variables de `tokens.css`; los valores crudos permitidos están en `tests/test_componentes.py`. `tokens.css` e `iconos.js` se generan: edita `diseno/tokens.json` o `diseno/iconos/*.svg` y corre `.venv/bin/python scripts/tokens.py`.
5. Si el archivo entra a la imagen: `COPY site/` ya lo cubre. Si es un directorio nuevo de la raíz, agrégalo al `Dockerfile`.

## 4. Invariantes y «no hagas»

Seguridad y privacidad
- **Nunca leas, imprimas ni copies `.env`.** Correr `garmin_connect.py` (que lo lee por dentro) sí se vale.
- La key de Garmin nunca en el chat ni en archivos; solo como secreto `PERSONAL_API_KEY` de GitHub. La web no tiene ni pide la key. Las copias se vinculan únicamente al autorizar la GitHub App (no hay código de seis dígitos).
- El `data.json` público sale de una **lista blanca**: sin IDs de Garmin, nombres de actividades, GPS, nombre ni fecha de nacimiento. `dashboard/validar.py` y `tests/test_build.py` lo vigilan. Nunca un token de GitHub en el sitio.
- La FC por segundo (`serie`) y los `splits` pueden subir a la web dentro de `activity_details`, pero nunca salen en un `data.json`.
- Cookies HttpOnly/Secure/SameSite=Lax, CSRF en todo POST, tokens solo como hash, `permisos.puede_ver/puede_editar` en toda consulta de datos de una persona.
- Secretos y variables (`DATABASE_URL`, `SECRET_KEY`, `RESEND_API_KEY`, `OIDC_AUDIENCE`...) viven en Google Secret Manager; nunca en el repo ni en el chat. El admin en producción corre como Cloud Run Job, nunca con la cadena de la base en la compu (única excepción: `./run_web.sh`, ver CLAUDE.md).

Compatibilidad
- El motor debe seguir funcionando con configs viejas: **toda clave nueva de `config.yaml` o de `data.json` lleva un valor por defecto** (`dashboard/defaults.yaml` o `ajustes.cargar_config`) y el sitio tolera claves ausentes.
- Los repos-tubo reciben cada cambio de `stable` sin tocar nada: no rompas los archivos de `stable` (`.github/workflows/motor.yml`, `scripts/subir.py`, `garmin_connect.py`, `dashboard/paquete.py`; lo que estos importan, como `dashboard/ajustes.py` y `validar.py`, debe seguir compatible).
- Dependencias del motor: `requirements.txt` (lo instalan los repos-tubo; fijas con `==`). De la web: `web/requirements.txt`. De pruebas: `requirements-dev.txt`. Dependencia nueva: instálala en `.venv` y fíjala en el requirements que corresponda.

Código y diseño
- Lógica en Python; el JS solo pinta (lo que se muestra lo decide Python). Textos en español, por i18n. **Sin librerías de JS.**
- **Altura fija**: elegir no cambia la altura de nada; solo expandir/colapsar. Ranuras reservadas en `em`/`lh`; nunca cambios de `font-weight` al elegir; gráficas de altura fija.
- Solo la web: Pages ya no existe (retirado 2026-11-26); diseña solo para ahilallevas.com, sin respaldos para Pages. El build local de Pedro (`dashboard/build.py`, `run_local.sh`) pinta lo de la web; en el servidor estático algunas ligas (`/plan/...`, Ajustes) no funcionan.
- No edites a mano lo generado (`site/tokens.css`, `site/iconos.js`, `site/i18n/*.json`).
- Las plantillas de repos nuevos viven en `plantilla_v5/`; `template/` ya no existe.
- No toques `.claude/worktrees/` (tiene trabajo sin integrar).
- Antes de un push: `git pull --rebase`.

Planes
- Solo el motor v6 (`plan/motor_v6.py`). El motor genera el plan al crearlo; no hay ajuste semanal.
- «Repetir esta semana» y «Retomar desde la semana X» guardan `corrida.saltos` (`motor_v6.secuencia_de`), con vista previa en `/plan/propuesta.json`; se deshacen solo en la misma semana.
- «Agregar carrera» = carrera de paso (`de_paso`, reemplaza la larga en `plan_efectivo`) o plan nuevo para esa carrera.
- El coach (MCP) hace cambios conservadores: poco a poco, nunca saltos grandes; con dolor, parar y descansar.

## 5. Cómo probar

- Todo: `.venv/bin/python -m pytest -q -n auto` (en paralelo; el Python del sistema no tiene pytest). Un archivo: `.venv/bin/python -m pytest -q tests/test_build.py`.
- Planes: `.venv/bin/python -m plan.simulador` (personas sintéticas y reglas de seguridad).
- Privacidad del `data.json`: `.venv/bin/python dashboard/validar.py [ruta/data.json]`.
- Construir el sitio: `.venv/bin/python dashboard/build.py` (`--day AAAA-MM-DD`, `--out ruta`). Con `GARMIN_USER_DIR=<carpeta>` usa config.yaml, plan/ y data/ de otra persona.
- Web en local: `./run_web.sh` usa la **base de producción** (lee la cadena de Secret Manager con la sesión de `gcloud`; no migra: si la revisión de la base no es la del código, no arranca; lo que se guarda ahí es real). `./run_web.sh --temporal` usa SQLite (`web/dev.db`) con las migraciones al día; para probar cambios de estructura, siempre este. En ambos modos solo escucha en esta compu, no manda correos ni habla con GitHub o Google, no usa la caché de `data.json`, y la liga o código de entrada sale en la consola.
- Admin local: `python -m web.cli crear-admin <correo>`, `invitar [--nota X]`, `importar <correo> <carpeta> [--repo-id N]`.
- Sitio estático solo con datos de Pedro: `./run_local.sh` (baja datos, construye y sirve en http://localhost:8000).
- CI (`web.yml`): `pip install -r requirements.txt -r web/requirements.txt -r requirements-dev.txt`, `ruff check .` y `python -m pytest -q -n auto --dist worksteal`, en dos máquinas (`tests/test_web_*.py` y el resto); la imagen se construye a la vez y el deploy espera a ambas.
