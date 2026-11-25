# Plan v5: Ahí la Llevas — web con usuarios (solo amigos, por invitación)

Requisitos aprobados por Pedro (2026-11-25): [`REQUISITOS_V5.md`](REQUISITOS_V5.md). Base: v4.5.1 (`stable` = f0ffe37).

Quién: 🤖 Sonnet ejecuta por tandas; 🔍 Opus revisa, despliega y verifica al cerrar cada tanda. **No hagas push.**

| Tanda | Fases | Al cerrar |
|---|---|---|
| A | F0 motor listo · F1 servidor y cuentas · F2 tubo de datos | Opus despliega en Cloud Run; el repo de Pedro empieza a subir (su Pages sigue igual) |
| B | F3 ajustes e historial · F4 plan vivo | Opus revisa con Pedro en la web |
| C | F5 coach · F6 conector MCP · F7 privacidad, admin y PWA | Opus prueba el conector con Claude y ChatGPT |
| D | F8 migración | Opus + Pedro (pasos en GitHub de cada amigo) |

## Reglas

Las de siempre:
- **No leas, imprimas ni copies `.env`.** Correr `garmin_connect.py` (que lo usa por dentro) sí se vale.
- La key de Garmin **nunca** llega a la web: ni en código, ni en formularios, ni en logs. La web no tiene un solo
  campo que la pida.
- Pasos chicos y verifica cada uno. `.venv/bin/python -m pytest -q` verde siempre.
- La lógica va en Python; el JS solo pinta. Textos en español. Sin librerías de JS.
- Privacidad por lista blanca (lo que sube el repo y el `data.json`): sin IDs de Garmin, nombres de actividades,
  GPS, nombre ni fecha de nacimiento. `serie` (FC por segundo) puede subir a la web pero **nunca** sale en un
  `data.json`.
- Toda clave nueva de `config` o `data.json` lleva valor por defecto y entra en la lista blanca de `validar.py`.
- Un commit local por fase (`v5 F<n>: …`).
- Antes de tocar gráficas, colores o CSS, carga el skill `dataviz`.
- Si algo choca con el código, decide lo más simple que cumpla el requisito y anótalo en `docs/DUDAS.md`
  (sección "v5"); no te detengas.

**Regla de oro:** el dashboard de Pedro servido por la web debe ser **igual** al de GitHub Pages. Prueba
automática (F2): `build()` con los archivos de `data/` == `build()` con lo que la web guardó del paquete de esos
mismos archivos (JSON normalizado). Las únicas diferencias permitidas son las que este plan nombra (textos de
`/ajustar` → botones, ligas del menú); anótalas en DUDAS.

**Seguridad web (todas las fases):** cookies `HttpOnly; Secure; SameSite=Lax`; token CSRF en todo POST de
formulario; tokens (invitación, liga de login, OAuth) se guardan **solo como hash** (SHA-256) y son de un uso;
toda consulta filtra por usuario con una sola función `puede_ver(actor, atleta)` / `puede_editar(actor, atleta)`
(prueba: un usuario nunca ve datos de otro sin acceso de coach); sin secretos en el repo (variables de entorno).

## Estructura objetivo

```
web/                      ← NUEVO: la app (FastAPI)
  app.py                  rutas y arranque
  db.py  modelos.py       SQLAlchemy; migraciones en web/alembic/
  auth.py                 invitaciones, liga por correo, sesiones, CSRF
  tubo.py                 OIDC de GitHub Actions, instrucciones y subida
  calculo.py              arma `data` desde la base y llama dashboard/build.build()
  ajustes_web.py plan_vivo.py coach.py mcp_server.py oauth.py privacidad.py admin.py
  plantillas/             Jinja2 (login, onboarding, ajustes, plan, coach, privacidad, admin)
  estaticos/              styles propios de las páginas Jinja2 (reusa variables de site/styles.css)
  requirements.txt        dependencias solo de la web (no se instalan en Actions de amigos)
Dockerfile  .dockerignore ← NUEVO: imagen de la web (motor + web + site; sin data/, plan/ personal ni .env)
.github/workflows/web.yml ← NUEVO: pruebas → imagen → despliegue a Cloud Run (manual, como deploy.yml)
.github/workflows/respaldo.yml ← NUEVO: respaldo nocturno de la base a Cloud Storage
dashboard/paquete.py      ← NUEVO: arma y valida el paquete que sube cada repo (lo usan repo y web)
scripts/subir.py          ← NUEVO: pide instrucciones a la web y sube el paquete con OIDC
site/                     igual; la web lo sirve por usuario
```

**Hosting, todo en planes gratis (~$0/mes):**

| Pieza | Servicio | Notas para el código |
|---|---|---|
| Web | **Google Cloud Run** (`us-central1`, mín. 0 / máx. 1 instancia, 512 MiB) | Se duerme sin uso y despierta en segundos: nada en memoria es fuente de verdad (solo cachés). Sistema de archivos efímero: nada se escribe a disco. Escucha en `$PORT`. |
| Base | **Neon** Postgres (plan Free, ~0.5–1 GB) | Usar la cadena *pooled* con `sslmode=require`, `pool_pre_ping=True` y pool chico (5); la primera consulta tras dormir tarda ~1 s. |
| Correo | **Resend** (Free: 3,000/mes, 100/día) | Desde `entrar@ahilallevas.com`. |
| Secretos | **Secret Manager** de Google (`SECRET_KEY`, `DATABASE_URL`, `RESEND_API_KEY`) | Cloud Run los monta como variables de entorno. Nunca en el repo ni en el chat. |
| Despliegue | GitHub Actions → Cloud Run con **Workload Identity Federation** (OIDC de GitHub, sin llaves JSON de Google) | Solo desde `pegongorasep/garmin-dashboard`, rama `main`. |
| Respaldos | `pg_dump` cada noche → bucket privado de **Cloud Storage** (borra después de 30 días) | **Nunca** como artefacto de Actions: el repo es público y los artefactos se pueden descargar. |
| Dominio | `ahilallevas.com` en Cloudflare → mapeo de dominio de Cloud Run (DNS sin proxy) | Opus confirma el método vigente al desplegar. |

Si algún día Google da lata, el mismo Dockerfile corre en Render Starter (~7 USD/mes) sin cambiar código.

Base de datos (nombres en español; JSON como `sa.JSON` para que pruebas usen SQLite y producción Postgres):

| Tabla | Campos clave |
|---|---|
| `usuarios` | id, correo (único), apodo, es_admin, creado, github_owner, github_owner_id, repo, repo_id, sensor (`banda`/`muñeca`), borrado |
| `invitaciones` | token_hash, creada_por, nota, expira, usada_por, usada_en |
| `ligas_login` | token_hash, usuario_id, expira, usada_en |
| `sesiones` | id (aleatorio, en la cookie), usuario_id, creada, expira, ultima_vez |
| `consentimientos` | usuario_id, version_aviso, fecha |
| `datos_garmin` | usuario_id, tipo (`actividad`/`detalle`/`dia`/`sueno`/`hrv`/`zonas`/`historial`/`meta`), clave, contenido JSON, actualizado; único (usuario_id, tipo, clave) |
| `subidas` | usuario_id, fecha, motor (sha), bytes, ok, error |
| `ajustes` | usuario_id, config JSON (mismo formato que `config.yaml`), version |
| `planes` | usuario_id, plan JSON (formato de `plan.json`), version |
| `inbody` | usuario_id, fecha, valores JSON (formato de una entrada de `plan/inbody.json`) |
| `cambios` | id, atleta_id, autor_id, via (`web`/`ia`/`coach`/`sistema`), descripcion, antes JSON, despues JSON, fecha, visto, deshecho_por |
| `coaches` | atleta_id, coach_id, creado |
| `cache_data` | usuario_id, contenido JSON, calculado, huella (hash de entradas + fecha local) |
| (F6) `oauth_clientes`, `oauth_codigos`, `oauth_tokens` | según F6 |

---

## F0 — Motor listo para la web 🤖 (sin cambios visibles)

Objetivo: que la web pueda llamar al motor con datos en memoria, y que el repo suba un paquete limpio.

1. `dashboard/ajustes.py`: separa `cargar_config(user_dir)` en `leer_config_yaml(ruta) -> dict` (crudo) y
   `normalizar_config(crudo: dict) -> dict` (todo lo que hoy valida). `cargar_config` queda como las dos juntas.
   La web guarda el **crudo** (mismo formato que `config.yaml`) y llama `normalizar_config`.
2. `plan/gen_plan.py`: `generar(cfg)` ya existe; asegúrate de que recibe la config normalizada sin leer disco y
   que `verificar` se puede llamar igual. Prueba: `generar(normalizar_config(leer_config_yaml(config.yaml)))`
   == `plan/plan.json` de Pedro.
3. `dashboard/build.py`: `load_data(user_dir=None)` y `load_plan(user_dir=None)` aceptan carpeta. `build()` no
   lee disco ni `USER_DIR` (revisa `ayuda.py`, `tipos.py`, `metrics.py`).
4. **Modo web en textos**: `config["modo"]` (`"pages"` por defecto, `"web"` en la web; no se escribe en
   `config.yaml`, lo pone quien llama). Con `"web"`: "Corre /ajustar…" → "Ve a Ajustes" (build.py:801,
   metrics.py:569–576, ayuda.py:123, app.js:248 usa `t.siguiente`). `ui.acciones_url` sigue igual.
5. `garmin_connect.py` funciona **sin `config.yaml`** (repos nuevos solo tubo): lo que necesite de la config sale
   de defaults. Acepta `--historial-desde AAAA-MM-DD` y `--dias-actividades N` (además de los posicionales de hoy).
6. `dashboard/paquete.py`:
   - `armar(data_dir, salt) -> dict`: `{"esquema": 1, "motor": <sha o "local">, "archivos": {daily, activities,
     activity_details, hr_zones, historial_corridas, meta}}`. **Sin `profile`.**
   - Lista blanca **por campo** de cada archivo: solo los campos que lee el motor (búscalos con grep en
     `dashboard/` y `plan/`; anótalos en la docstring). Nada de `ownerX`, `locationName`, lat/long, `uuid`.
   - `activityId` se reemplaza por `id` opaco = primeros 16 hex de `sha256(f"{salt}:{activityId}")`; las llaves de
     `activity_details` igual. El motor deja de leer `activityId`: usa `a.get("id") or a.get("activityId")` en
     una sola función `id_de(a)` (metrics.py:140,311,466,691,887; build.py:281,330,433,435).
   - `activityName` no sube: se calcula ahí `es_carrera` con la regla de `metrics._NOMBRE_CARRERA`, y el motor usa
     `a.get("es_carrera")` si existe (metrics.py:855).
   - Revisa `splits`/`serie`/`ritmos_km` de `activity_details` por si traen GPS; si sí, fuera.
   - `validar(paquete) -> list[str]` (problemas): esquema, archivos conocidos, ninguna clave de
     `validar.PROHIBIDAS` salvo `serie` dentro de `activity_details`, tamaño < 10 MB.
7. Pruebas: build con `data/` crudo == build con un paquete armado de `data/` (dict→archivos en tmp) para la
   config de Pedro; paquete sin claves prohibidas; `garmin_connect` sin config (con cliente falso).

## F1 — Servidor, cuentas e invitaciones, dashboard por usuario 🤖 (local)

1. `web/requirements.txt` (versiones fijas, instaladas en `.venv`): fastapi, uvicorn, sqlalchemy, alembic,
   psycopg[binary], jinja2, python-multipart, itsdangerous, httpx, pyjwt[crypto]. Sin SDK de Resend: un POST con
   httpx.
2. Config por variables de entorno (`web/config.py`): `DATABASE_URL` (por defecto SQLite en
   `<scratch o web/dev.db>`, gitignored), `SECRET_KEY`, `BASE_URL`, `RESEND_API_KEY` (vacía = la liga se imprime
   en consola), `CORREO_DE`, `OIDC_AUDIENCE` (= `BASE_URL`), `ADMIN_CORREO`.
3. Alembic con la migración inicial de todas las tablas de arriba excepto las de F6.
4. **Invitaciones**: `python -m web.cli invitar [--nota "Adrián"]` imprime una liga de un solo uso (14 días).
   `python -m web.cli crear-admin <correo>` crea a Pedro. (La pantalla de admin llega en F7.)
5. **Login sin contraseña**: `/entrar` pide correo → si existe, manda liga (15 min, un uso) por Resend; siempre
   responde lo mismo ("Si tu correo está registrado, te llegó una liga") para no revelar quién existe. Límite: 5
   ligas por correo por hora. `/invitacion/<token>` pide correo y crea la cuenta, luego manda la liga.
   Sesión: 60 días, renovada al usarse; `/salir` la borra.
6. **Dashboard por usuario**: `/` sin sesión → página de bienvenida con "Entrar"; con sesión → el sitio actual
   (`site/index.html` y sus archivos servidos tal cual) y `/data.json` = el `data.json` del usuario. El `fetch`
   relativo de `vistas.js` no cambia.
   - `web/calculo.py`: `datos_de(usuario)` arma el mismo dict que `build.load_data`, desde `datos_garmin` +
     `inbody`; config = `normalizar_config(ajustes)` con `modo="web"`; plan = `planes`. Llama `build()` con la
     hora local del usuario. Guarda en `cache_data`; se recalcula si cambió la huella (subida, ajuste, plan,
     inbody o cambió el día local) o tiene más de 30 min.
   - `validar.problemas()` corre sobre cada `data.json` calculado; si falla, se responde error y se registra (no se
     sirve un JSON con claves prohibidas).
   - `ui.menu`: lista `[{texto, url}]` (Ajustes, Coach, Privacidad, Salir; según la fase) que el JS pinta junto al
     `?`. Default `[]` en Pages (lista blanca en `validar.py`; las URLs del menú son relativas, sin `http`).
7. `python -m web.cli importar <correo> <carpeta>`: carga `config.yaml`, `plan/plan.json`, `plan/inbody.json` y
   el paquete armado de `data/` de esa carpeta (pasa por `paquete.armar` + la misma función de guardado de F2).
   Sirve para probar con los datos de Pedro en local.
8. Pruebas (TestClient + SQLite en memoria): invitación de un uso, liga vencida/usada, sesión, CSRF, que un
   usuario no pueda pedir el `data.json` de otro, `data.json` de Pedro importado == el de `build.py` (salvo lo
   permitido).

## F2 — Tubo de datos: OIDC, subida, onboarding y aviso 🤖

1. **Endpoints del tubo** (`web/tubo.py`), autenticados con el token OIDC de GitHub Actions en
   `Authorization: Bearer`:
   - Verifica con PyJWT + JWKS de `https://token.actions.githubusercontent.com/.well-known/jwks` (caché 1 h):
     firma RS256, `iss`, `aud == OIDC_AUDIENCE`, `exp`, y que `job_workflow_ref` empiece con
     `pegongorasep/garmin-dashboard/.github/workflows/motor.yml@` y termine en `refs/tags/stable` o
     `refs/heads/main`.
   - Usuario = el que tenga `repo_id == claim repository_id`. Si ninguno, **coincidir el owner NO basta** (un invitado
     podría escribir el usuario de GitHub de otra persona): token con `repository_visibility` distinto de `private` →
     nunca se vincula solo (solo `python -m web.cli vincular <correo> <owner/repo> <repo_id>`, que registra un `cambio`
     de sistema; así se vincula Pedro, cuyo repo es público). Repo privado y un único usuario con consentimiento y
     `github_owner` igual (sin mayúsculas) → se genera un **código de 6 dígitos** (se guarda su hash con el repo candidato,
     vence en 1 h; mientras viva se reutiliza el mismo pendiente) y la respuesta 403 de `instrucciones` y `subida` trae
     `{"codigo": "123456"}`; esa subida **no se guarda**. `subir.py` escribe el código en `$GITHUB_STEP_SUMMARY` (solo lo ven
     quienes tienen acceso al repo privado). Se vincula cuando la persona escribe el código en el paso 6 del onboarding.
     Sin consentimiento o sin usuario único: 403 sin código (el workflow sigue con Pages como hoy).
   - `POST /api/tubo/instrucciones` → `{"vinculado": bool, "historial_desde": fecha|null, "dias_actividades":
     int}`. `historial_desde` se manda en la primera corrida (365 días atrás) o cuando la web lo pidió; se limpia
     al recibir esa subida.
   - `POST /api/tubo/subida` (JSON gzip, ≤ 10 MB) → `paquete.validar`; guarda con **upsert** por (tipo, clave):
     actividades y detalles por `id`, días/sueño/hrv por fecha, zonas e historial completos, meta. Nunca borra.
     Registra en `subidas` (motor, bytes, ok/error). Invalida `cache_data`. Responde `{"ok": true,
     "publicar_pages": bool}` (`false` cuando el usuario ya terminó la migración de F8; antes `true`).
2. **`scripts/subir.py`** (lo corre `motor.yml`; solo `requests` y la librería estándar):
   `instrucciones` imprime los argumentos para `garmin_connect.py`; `subir` arma el paquete (`salt` =
   `GITHUB_REPOSITORY_ID`) y lo sube; escribe `publicar_pages=true|false` en `$GITHUB_OUTPUT`. URL de la web =
   `AHILALLEVAS_URL` (por defecto la de producción, fija en `motor.yml`). Si la web no responde (timeout 60 s
   por si Cloud Run está despertando, 2 reintentos): avisa y sigue (salida `publicar_pages=true`). Nunca falla el workflow por la web. El token OIDC se pide con
   `ACTIONS_ID_TOKEN_REQUEST_URL`/`_TOKEN` y `audience`.
3. **`motor.yml`**: antes de bajar datos, `subir.py instrucciones` (con fallback a los argumentos de hoy); después,
   `subir.py subir`. Si el repo **no tiene `config.yaml`** (repo nuevo solo tubo): no construye, no valida, no
   publica Pages ni copia CLAUDE.md. Si `publicar_pages` es `false`: no publica Pages (salida del job `build`
   que condiciona `deploy`). Todo lo demás igual: con la web caída o sin vincular, los repos de hoy publican como
   siempre. `permissions` no cambia (ya trae `id-token: write`).
4. **Onboarding** (`/bienvenida`, pasos con progreso; se puede salir y volver al paso donde iba):
   1. Aviso de privacidad simplificado + liga al integral + casilla de **consentimiento expreso** para datos
      sensibles (se guarda versión y fecha). Sin esto no se vincula nada.
   2. "¿Cuál es tu usuario de GitHub?" (si no tiene: liga para crear cuenta gratis, con la explicación de para qué).
   3. Botón **"Crear mi copia en GitHub"** → `https://github.com/new?template_owner=pegongorasep&template_name=<plantilla>&name=ahilallevas-datos&visibility=private`
      (la plantilla nueva se crea en F8; mientras, Opus usa `garmin-prueba`).
   4. "Pon tu key de Garmin en tu repo": liga a `connect.garmin.com/app/settings/personalApiToken` y liga directa
      a `https://github.com/<owner>/<repo>/settings/secrets/actions/new`, con el nombre `PERSONAL_API_KEY` en un
      botón de copiar (JS de una línea; el JS no ve la key). Texto claro: "tu key se queda en tu GitHub; aquí no
      la pedimos nunca".
   5. "Actívalo": liga a `https://github.com/<owner>/<repo>/actions` (activar) y a "Run workflow".
   6. Vincular: "Abre la última corrida de tu repo (liga) y escribe el código" (`POST /bienvenida/codigo` con CSRF;
      máximo 5 intentos por pendiente, luego se invalida y la siguiente corrida genera otro; `hmac.compare_digest`). Al
      coincidir guarda repo, repo_id y owner_id y registra el `cambio`; la página ofrece "Run workflow" (la corrida del
      código no guardó datos). Después espera: la página consulta `/api/estado` cada 10 s y muestra "Ya llegaron tus datos ✔" al vincularse y
      recibir la primera subida.
   7. Preguntas del plan (las mismas que `/setup`: nivel, intensidad, calidad, caminatas, actividades y días de
      pierna, fecha de inicio = próximo lunes por defecto, sensor banda/muñeca, zona horaria por defecto
      `America/Merida`) → guarda `ajustes`, genera `planes` con `gen_plan.generar` → al dashboard.
   El nombre del repo lo deduce la web de lo que escribió + la primera subida (no se le pide teclearlo dos veces).
5. **Aviso de privacidad** (`/privacidad`, plantilla con versión `2026-12`): responsable (Pedro), datos que se
   tratan y cuáles son sensibles, finalidades (mostrar tu dashboard y plan; compartir con tu coach si tú lo
   activas), encargados (Google Cloud, Neon, Resend, GitHub, Cloudflare; Garmin como
   fuente), sin transferencias ni venta,
   derechos ARCO (correo de Pedro + botones de F7), "no es consejo médico", "Datos de Garmin" como atribución.
   Pie de página en todas las páginas con esas dos frases y la liga al aviso.
6. **Estado del repo**: si un usuario vinculado no sube en 24 h, banner en su dashboard ("tu repo no ha mandado
   datos: revisa que Actions esté activo o renueva tu key") con las ligas; y "Actualizar ahora" en `ui.acciones_url`
   apunta a su repo.
7. **Despliegue en Cloud Run:**
   - `Dockerfile` (python:3.12-slim, `pip install -r requirements.txt -r web/requirements.txt`, copia solo
     `dashboard/ plan/gen_plan.py plan/plan.example.json site/ web/ scripts/`; al arrancar `alembic upgrade head`
     y luego `uvicorn web.app:app --host 0.0.0.0 --port $PORT`). `.dockerignore` excluye `.env`, `data/`,
     `config.yaml`, `plan/plan.json`, `plan/inbody.json`, `.venv`, `tests/`. Prueba: la imagen no contiene esos
     archivos (`docker run … ls`, o prueba que lea `.dockerignore`).
   - `.github/workflows/web.yml` (`workflow_dispatch`): pytest → login a Google con
     `google-github-actions/auth` por Workload Identity Federation (variables del repo `GCP_PROYECTO`,
     `GCP_PROVEEDOR_WIF`, `GCP_CUENTA_SERVICIO`; ningún secreto JSON) → build y push a Artifact Registry →
     `gcloud run deploy` con `--min-instances 0 --max-instances 1 --memory 512Mi --region us-central1`, secretos
     de Secret Manager como variables y `--allow-unauthenticated` (la app hace su propio login).
   - **Comandos de admin en producción** (`web.cli invitar`, `crear-admin`, `importar`): como **Cloud Run Job**
     con la misma imagen (`gcloud run jobs execute … --args`), así nadie copia la cadena de la base a su compu.
     `importar` en producción recibe el paquete por stdin/archivo subido al job; anótalo en DUDAS si es más simple
     otra vía.
   - `.github/workflows/respaldo.yml` (diario, 09:00 UTC, y manual): mismo login WIF, `pg_dump` con la cadena de
     Secret Manager (nunca impresa), gzip y sube a `gs://<bucket>/respaldos/AAAA-MM-DD.sql.gz`. El bucket es
     privado con regla de borrado a 30 días. Si falla, el workflow falla (Pedro recibe el correo de GitHub).
     Documenta en `CLAUDE.md` cómo restaurar.
   - `/salud` responde 200 sin tocar la base (Cloud Run lo usa como sonda de arranque).
8. Pruebas: tokens OIDC firmados con una llave RSA de prueba y JWKS falso (válido, otro `aud`, vencido, otro
   workflow, otra rama); vinculación solo con consentimiento y owner correcto; upsert sin duplicar; paquete con
   clave prohibida → 422; `subir.py` con la web caída → `publicar_pages=true`; **regla de oro** de arriba.

### 🔍 Cierre de la tanda A (Opus)

Revisa, push, `stable` **no se mueve** hasta ver que los repos de amigos siguen publicando igual.

Montaje (una vez, Opus guía a Pedro paso a paso; Opus usa `gcloud` en la Terminal de Pedro cuando se pueda):
1. Proyecto de Google Cloud con facturación + **alerta de presupuesto de 1 USD** (correo a Pedro). Activar Cloud
   Run, Artifact Registry, Secret Manager, Cloud Storage, IAM Credentials.
2. Workload Identity Federation para `pegongorasep/garmin-dashboard` (solo ese repo) + cuenta de servicio con los
   permisos mínimos (desplegar Cloud Run, subir imágenes, leer los 3 secretos, escribir en el bucket).
3. Neon: proyecto en la región más cercana a `us-central1` (AWS us-east). **Pedro** pega la cadena *pooled* en
   Secret Manager desde la consola (no en el chat), igual `RESEND_API_KEY`; `SECRET_KEY` se genera ahí mismo.
4. Resend: dominio `ahilallevas.com` verificado (registros DNS en Cloudflare).
5. Mapeo de `ahilallevas.com` a Cloud Run (registros en Cloudflare sin proxy). Mientras propaga, la URL
   `*.run.app`.

Luego: `web.yml`, Job `crear-admin` para Pedro, invitación de prueba con `garmin-prueba`, y verificar que el repo
de Pedro sube 3 veces al día, su dashboard en la web == su Pages, Pages sigue igual, el respaldo nocturno llega al
bucket, y el gasto de Google sigue en $0.

---

## F3 — Ajustes, historial y deshacer, InBody 🤖

1. `/ajustes`: formulario por secciones con lo que hoy cambia `/ajustar` (perfil: zona horaria, FC máx o edad,
   sensor; corrida: nivel, intensidad, calidad, caminatas, variada, semanas, fecha de inicio, semanas repetidas,
   carreras; actividades: categorías y días de pierna; InBody sí/no). Validación = `normalizar_config` (el error se
   muestra junto al campo). Cambios que afectan el plan regeneran `planes` y lo dicen antes de guardar
   ("esto rehace tu plan desde la semana N; las semanas ya pasadas no cambian").
2. **Historial** (`web/cambios.py`): **toda** escritura a `ajustes`, `planes` o `inbody` pasa por
   `aplicar_cambio(atleta, autor, via, descripcion, nuevo)` que guarda antes/después. `/historial` lista
   (quién, cuándo, qué) con **Deshacer** (aplica el `antes` como un cambio nuevo y marca `deshecho_por`).
3. **Avisos**: si el autor no es el atleta, el atleta ve un banner en su dashboard ("Pedro cambió tu semana 7 ·
   Ver · Deshacer") hasta que lo marque visto. Va en `data.json` como `avisos` (lista blanca, default `[]`).
4. **InBody**: `/cuerpo/nuevo` con los campos de `plan/inbody.json` (fecha, peso, grasa, músculo, visceral, …;
   los obligatorios mínimos: fecha y peso); editar/borrar entradas. Pasa por `aplicar_cambio`.
5. Pruebas: cada cambio deja historial; deshacer restaura exacto; regenerar no toca semanas pasadas.

## F4 — Plan vivo 🤖

Modelo dentro de `ajustes` (crudo) con defaults vacíos; el generador sigue siendo `gen_plan.generar` + una capa
`web/plan_vivo.py` que aplica metas y eventos al plan generado. Todo cambio pasa por `aplicar_cambio`.

1. **Metas**: `metas: [{tipo: "carrera", fecha, distancia_km, nombre}]` y la meta base (sin fecha = base aeróbica,
   lo de hoy). Carrera dentro del plan: su semana = **semana de carrera** (2 corridas Z2 cortas al 60 % + la
   carrera ese día), la semana anterior = **descarga**; la fecha entra en `carreras` para que el dashboard la
   reconozca. Carrera después del plan: se guarda y se ve en "Próximo"; el siguiente bloque la toma.
2. **Bloques encadenados**: al terminar, la tarjeta `plan_terminado` muestra el botón **"Armar siguiente
   bloque"** (misma config, inicia el lunes siguiente, base = lo que logró en la prueba si hubo); el plan anterior
   queda en el historial.
3. **Eventos** (botones en `/plan`): **"Voy de viaje"** (fechas, ¿podrás correr?: sí → semana ligera: 2 Z2 cortas;
   no → sin corridas), **"Estoy enfermo/lastimado"** (desde hoy; las sesiones de esos días quedan *pausadas*; al
   volver ofrece "repetir la semana"), **"Repetir semana"** (lo de `semanas_repetidas`), **"Agregar carrera"**.
   Cada evento se ve en el calendario del Plan (lista blanca: `plan.eventos`, default `[]`).
4. **Sesiones flexibles**: un paso puede ser `{"repetir": n, "pasos": [...]}`. Editor en `/plan/sesion/<id>`
   (formulario Jinja2: filas de paso tipo trote/caminata, minutos, zona; agrupar en "repetir"). Revisa que
   `build.py` (`convert_steps`, `rampas_de`, `rachas_de`), las siluetas de `site/` y `dashboard/reloj_plan.py`
   entiendan las repeticiones (expandiéndolas donde haga falta). Prueba con la Larga 8'/1' × 6 + 10' continuo.
5. **Escalera trote/caminata por persona**: `corrida.escalera` = `["3/1","5/1","8/1","12/1","continuo"]` y
   `corrida.escalon` actual (default: el que dé `caminatas` hoy, para no cambiar planes existentes). Las sesiones
   con caminatas usan el escalón; botón "subir escalón" (y el semáforo sugiere subirlo tras 2 semanas completas
   sin rojos; solo sugiere).
6. **Sensor**: con `sensor: muñeca` el dashboard no muestra métricas que dependen de banda (deriva y lo que
   `metrics` marque como sensible a la banda; anota la lista en DUDAS). Default `banda` (lo de hoy).
7. Pruebas: el plan de Pedro sin metas/eventos queda **idéntico**; viaje/enfermedad/carrera cambian solo sus
   semanas; repetir y deshacer.

### 🔍 Cierre de la tanda B (Opus)

Revisa, push, despliega. Pedro prueba en su celular: ajustes, un viaje de prueba, deshacer. (Aquí entran, cuando
Pedro diga, los cambios del 10K del 10 de enero usando las mismas herramientas.)

---

## F5 — Acceso de coach 🤖

1. `/coach`: el atleta escribe el correo de alguien con cuenta → le da acceso (ver y editar plan, ajustes e
   InBody); lista de quiénes tienen acceso con **Quitar**. Nadie puede darse acceso a sí mismo por otro.
2. El coach ve "Mis atletas" con estado (último dato, semana del plan, semáforo de hoy) y entra a
   `/a/<id>/` = el mismo sitio con `/a/<id>/data.json` (fetch relativo, sin cambiar el JS) y a sus
   ajustes/plan. Todo lo que cambia queda con `via="coach"` y genera aviso al atleta (F3).
3. `puede_ver`/`puede_editar` = dueño o coach vigente. Quitar el acceso corta de inmediato (sesiones del coach
   ya abiertas también).
4. Pruebas: sin acceso → 404 (no 403, para no confirmar que existe); al quitar acceso, el coach pierde todo.

## F6 — Conector MCP con OAuth 🤖

Antes de empezar, 🔍 Opus confirma con la documentación vigente cómo agregan conectores remotos **Claude**
(conectores personalizados) y **ChatGPT** (modo desarrollador / apps) — transporte, descubrimiento OAuth y
registro de clientes — y ajusta esta fase en DUDAS. Base esperada:

1. **OAuth 2.1** (Authlib) en la misma app: metadatos (`/.well-known/oauth-authorization-server`,
   `/.well-known/oauth-protected-resource`), registro dinámico de clientes, código de autorización con PKCE
   (S256), pantalla de consentimiento en español ("Claude quiere ver y cambiar tu plan en Ahí la Llevas"),
   tokens de acceso de 1 h + refresh, guardados como hash, revocables desde `/conexiones`.
2. **Servidor MCP** (SDK oficial `mcp` de Python, transporte HTTP streamable) montado en `/mcp`, que exige el
   token. Herramientas (todas con `atleta` opcional; por defecto tú; coach solo sobre sus atletas):
   `resumen_hoy`, `semana`, `plan`, `corridas_recientes`, `progreso`, `ver_ajustes`, `cambiar_ajustes`,
   `agregar_carrera`, `agregar_evento`, `editar_sesion`, `repetir_semana`, `subir_escalon`, `registrar_inbody`
   (descripción: "lee la foto de la hoja InBody del usuario y manda los valores"), `historial`, `deshacer`,
   `mis_atletas`.
   Las lecturas devuelven lo mismo que el `data.json` (ya filtrado; jamás `serie`). Las escrituras pasan por las
   mismas funciones que los botones (`aplicar_cambio`, `via="ia"`) y regresan qué cambió y cómo deshacerlo.
3. Descripciones de herramientas en español con las reglas fijas: cambios conservadores, dolor = parar, no es
   consejo médico.
4. `/conexiones`: ver y revocar las IAs conectadas. Guía corta en `/ayuda/conector` con pasos para Claude y
   ChatGPT (URL del conector = `BASE_URL/mcp`).
5. Pruebas: flujo OAuth completo con cliente de prueba; token de A no puede leer a B; coach sí sobre su atleta;
   cada herramienta de escritura deja historial `via="ia"`.

## F7 — Privacidad completa, admin y PWA 🤖

1. `/privacidad/mis-datos`: **Descargar** (ZIP con JSON de ajustes, plan, InBody, datos Garmin guardados,
   historial de cambios y consentimientos) y **Borrar mi cuenta** (confirmación escribiendo "BORRAR"; borra todo
   lo del usuario, accesos de coach en ambos sentidos y tokens; deja solo un registro anónimo de la fecha de baja).
   Mensaje: "tu repo de GitHub es tuyo; bórralo o quita la key si ya no lo usarás".
2. **Admin** (solo Pedro, `/admin`): crear invitaciones (liga para copiar), ver usuarios (correo, apodo, repo,
   última subida y versión del motor, si se atrasó), revocar invitaciones. **El admin no ve dashboards ajenos** si
   no es su coach.
3. **PWA**: `manifest.webmanifest` (nombre "Ahí la Llevas", íconos generados, tema oscuro), service worker mínimo
   (caché del sitio estático; `data.json` siempre de red con respaldo al último). Instalable en iPhone y Android.
4. Pruebas: descargar trae todo lo del usuario y nada de otros; borrar no deja filas del usuario.

### 🔍 Cierre de la tanda C (Opus)

Revisa, push, despliega. Conecta Claude y ChatGPT con su cuenta de prueba y corre: leer semana, agregar viaje,
registrar InBody desde una foto, deshacer. Revisa el aviso de privacidad completo con Pedro.

---

## F8 — Migración 🔍 (Opus + Pedro)

1. **Plantilla nueva** (preguntar a Pedro antes de crear el repo): repo plantilla mínimo con solo
   `.github/workflows/deploy.yml` (llama `motor.yml@stable`, mismo horario y los **mismos permisos que hoy**: un
   workflow llamado no puede pedir más que quien lo llama, y `motor.yml` pide `contents`/`pages: write`), `keepalive.yml` y un README que dice "créalo desde Ahí la Llevas". Sin `config.yaml`, sin
   CLAUDE.md ni skills. Actualizar la liga del onboarding.
2. **Pedro**: `importar` sus archivos personales a la web (config, plan, InBody), verificar igualdad con Pages,
   marcarlo migrado (`publicar_pages=false`), apagar su GitHub Pages. `reloj.py` lee el plan desde un archivo que
   Pedro descarga en `/plan` ("Descargar plan para el reloj") o con `--plan <ruta>`.
3. **Cada amigo** (hoy solo `garmin-prueba`): invitación → onboarding con su repo existente (se vincula por owner,
   su `config.yaml`/`plan` se importan automáticamente en la primera subida si la web aún no tiene ajustes; añadir
   esto a `subir.py` como archivo opcional del paquete) → migrado → apagar su Pages (pasos con liga).
4. Quitar de `motor.yml` la copia de CLAUDE.md/skills para usuarios migrados; `template/` y las skills
   `/setup` `/ajustar` `/revision` quedan para quien no migre hasta que Pedro decida retirarlas.
5. Actualizar `CLAUDE.md` (secciones web, Cloud Run/Neon, comandos `web.cli`, respaldos) y `README.md`.

---

## Lo que Pedro tiene que hacer (y cuándo)

| Cuándo | Qué |
|---|---|
| ~~Antes~~ | ~~Comprar `ahilallevas.com` en Cloudflare~~ ✔ (2026-11-25) |
| Antes de cerrar la tanda A | Cuentas gratis: Google Cloud (con tarjeta, solo para la alerta de $1), Neon y Resend |
| Cierre A | Pegar la cadena de Neon y la key de Resend en Secret Manager (Opus dice dónde); aprobar en DNS de Cloudflare lo que Opus indique |
| Cierre B | Probar ajustes/eventos en su celular |
| Cierre C | Leer el aviso de privacidad; conectar su Claude |
| F8 | Apagar sus Pages; invitar amigos |
