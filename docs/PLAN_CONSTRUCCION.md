# Plan de construcción: dashboard Garmin + plan de 12 semanas

Fuente de verdad: [`REQUISITOS.md`](REQUISITOS.md) (aprobado v2). Si algo de este plan lo contradice, manda REQUISITOS.

**Quién hace qué**
- 🤖 **Sonnet**: ejecuta los pasos en orden.
- 🔍 **Opus**: revisa en cada *checkpoint*. Sonnet **se detiene** en cada checkpoint y no sigue hasta recibir el visto bueno.
- 👤 **Pedro**: pasos que solo él puede hacer, como iniciar sesión en GitHub.

---

## Reglas para quien ejecuta (léelas antes de empezar)

1. **Nunca leas, imprimas, muestres en logs ni copies `.env`** o la API key. Los scripts la cargan solos con `python-dotenv`. Si un comando pudiera mostrarla, no lo corras.
2. Un paso = un cambio pequeño. Al terminar un paso, corre su **✅ verificación**. Si falla, arréglalo antes de seguir.
3. **No inventes requisitos.** Si algo no está claro, anótalo en `docs/DUDAS.md` y sigue con lo demás. Si bloquea, para.
4. Python 3 del `.venv` (`.venv/bin/python`). Dependencias nuevas van a `requirements.txt`.
5. Código, nombres y comentarios en el estilo del `garmin_connect.py` actual: corto y con funciones simples. Los comentarios y el texto visible van en español.
6. Hay una zona horaria fija: **America/Merida** (UTC−6, sin horario de verano). "Hoy" y "anoche" se calculan en esa zona.
7. Al terminar cada fase, haz commit con un mensaje claro (git se inicia en F0).
8. Al llegar a un checkpoint 🔍, entrega un resumen corto: qué hiciste, qué verificaste y cualquier duda.

---

## Arquitectura

```
garmin/
├─ garmin_connect.py         # baja datos crudos → data/          (ya existe; se amplía)
├─ dashboard/
│  ├─ config.json            # FC máx, umbrales, fechas (editable a mano)
│  ├─ metrics.py             # funciones puras: zonas, carga, semáforo, etc.
│  └─ build.py               # data/ + plan + config → site/data.json (solo lo necesario)
├─ plan/plan.json            # las 12 semanas (lo escribe Opus, ver F4)
├─ site/                     # sitio estático que se publica
│  ├─ index.html  styles.css  app.js
│  └─ data.json              # GENERADO, no se versiona
├─ tests/                    # pytest
├─ docs/                     # REQUISITOS.md, PLAN_CONSTRUCCION.md, PLAN_ENTRENAMIENTO.md
└─ .github/workflows/deploy.yml
```

- **Flujo:** `garmin_connect.py` → `data/*.json` (crudo, privado) → `dashboard/build.py` → `site/data.json` (público, limpio) → GitHub Pages.
- **Lógica en Python, en `build.py`.** Ahí se calculan el semáforo, las zonas, la carga y los estados del plan. El JS solo pinta lo que recibe, así todo se puede probar con pytest.
- **Frontend:** HTML, CSS y JS sin frameworks ni build. Las gráficas son SVG hechas a mano, sin librerías externas.
- **Los datos no se guardan en git.** La Action baja, construye y publica directo en Pages.

---

## F0 — Preparación 🤖

- **0.1** `git init`. Agrega a `.gitignore`: `site/data.json`, `.pytest_cache/`, `.DS_Store`. **✅** `git status` no lista `.env` ni `data/`.
- **0.2** Crea las carpetas `dashboard/`, `plan/`, `site/` y `tests/`. Agrega `pytest` a `requirements.txt` e instálalo. **✅** `.venv/bin/pytest` corre (aunque no haya tests).
- **0.3** Crea `dashboard/config.json`:
  ```json
  {
    "timezone": "America/Merida",
    "max_hr": 190,
    "max_hr_floor": 183,
    "max_hr_review_above": 200,
    "zone_pcts": [50, 60, 70, 80, 90],
    "plan_start": "2026-10-26",
    "strap_in_crossfit_since": "2026-10-26",
    "rhr_tolerance_bpm": 4,
    "sleep_min_hours": 6.5,
    "rpe_heavy": 8,
    "run_types": ["running", "treadmill_running", "trail_running", "track_running"],
    "crossfit_types": ["hiit", "strength_training"]
  }
  ```
  **✅** Carga con `json.load` sin error.
- **0.4** Primer commit: "Estructura inicial".

## F1 — Datos 🤖

- **1.1** En `garmin_connect.py`, cambia los defaults: salud **16 semanas** y actividades **120 días**. Son 12 semanas de tendencias más el margen para los promedios. **✅** `python garmin_connect.py` sin argumentos termina en OK.
- **1.2** Busca el RPE. El endpoint de lista **no** trae RPE. Pide el detalle de **una sola** actividad reciente: `GET /activity-service/activity/{activityId}`. Guárdalo en `data/sample_activity_detail.json` y busca campos como `directWorkoutRpe`, `directWorkoutFeel` o `perceivedWorkoutEffort` (pueden venir dentro de `summaryDTO`). Anota en `docs/DUDAS.md` qué campos y escala encontraste. Garmin suele guardar el RPE ×10 (70 = 7). Si la actividad no tiene RPE porque la autoevaluación estaba apagada, anótalo así. **✅** Archivo guardado y nota escrita.
- **1.3** Agrega `pull_activity_details(c, activities)`: pide el detalle de cada actividad de **CrossFit o corrida** de la ventana y guarda en `data/activity_details.json` un dict `{activityId: {"rpe": ..., "feel": ...}}` (solo esos campos, `null` si no hay). Usa un caché en ese mismo archivo para no volver a pedir las que ya tienen RPE. **✅** El archivo existe y tiene una entrada por cada actividad de esos tipos.
- **1.4** Agrega a `meta.json` el campo `pulled_at_utc` (ISO con hora). **✅** Correr y revisar.

### 🔍 Checkpoint R1 — revisión de datos
Opus revisa: que la key no salga en ningún output, el formato del RPE, el caché y el tiempo total del script.

## F2 — Métricas (`dashboard/metrics.py`) 🤖

Cada paso es **una función pura con su test** en `tests/test_metrics.py`. Los tests usan datos pequeños inventados, nunca `data/`.

- **2.1** `zones(max_hr, rhr, pcts)` → lista de 5 `(zona, piso, techo)` con Karvonen: `piso = rhr + pct × (max − rhr)`, redondeado. **✅** Con max 190, rhr 60: Z2 = 138–151.
- **2.2** `rhr_7d(daily_summaries, day)` → promedio de `heartRate.restingValue` de los 7 días **anteriores** a `day`, ignorando vacíos. **✅** Test con huecos.
- **2.3** `classify(activity, config)` → `"run"`, `"crossfit"` u `"other"` según `activityType.typeKey`. **✅** Test.
- **2.4** `zone_minutes(activity)` → `{Z1..Z5}` en minutos desde `hrTimeInZone_1..5`. Z0 = duración − suma, y **no** se devuelve para sumar. **✅** Test.
- **2.5** `week_distribution(activities, week_start)` → minutos por zona de **todas** las actividades de esa semana (lunes a domingo), más los porcentajes agrupados `bajo` (Z1–Z2), `limbo` (Z3) y `alto` (Z4–Z5) sobre el total Z1–Z5. **✅** Test: 80/10/10.
- **2.6** `session_load(activity, details)` → RPE × minutos. Si no hay RPE, devuelve `None` (no se inventa). `week_load(...)` → `{crossfit, run, total, sin_rpe: n}`. **✅** Test con y sin RPE.
- **2.7** `signals(day, data, config)` → las 4 señales de "anoche y ayer". Cada una es `{"estado": "ok" | "fuera" | "sin_dato", "valor", "referencia", "texto"}`:
  - **HRV**: `lastNightAvg` contra `baseline.balancedLow–balancedUpper`. Está *fuera* si es menor a `balancedLow`. Se marca `hrv_baja = true` si `status == "LOW"` o si es menor a `baseline.lowUpper`.
  - **FC reposo**: la de hoy contra `rhr_7d`. Está *fuera* si supera el promedio + `rhr_tolerance_bpm`.
  - **Sueño**: `sleepTimeSeconds` de la noche que termina hoy. Está *fuera* si es menor a `sleep_min_hours`.
  - **RPE de CrossFit de ayer**: el máximo de ayer. Está *fuera* si es ≥ `rpe_heavy`. Si no hubo CrossFit, es `ok` con el texto "sin CrossFit ayer".

  **✅** Un test por señal, incluido `sin_dato`.
- **2.8** `traffic_light(signals, prev_light)`. `sin_dato` no cuenta como fuera.
  - 🔴 si `hrv_baja` o si hay ≥ 2 señales fuera;
  - 🟡 si hay 1 fuera;
  - 🟢 si no hay ninguna.

  Además, `repetir_semana = true` si hoy y ayer fueron 🔴. **✅** Tabla de casos en el test.
- **2.9** `week_index(day, plan_start)` → número de semana del plan, de 1 a 12. Es `None` antes del inicio o después del final. **✅** Test de bordes: 26 oct = semana 1, 18 ene = `None`.
- **2.10** `plan_status(week, runs_this_week)`:
  - Asigna las corridas hechas a las sesiones **en orden** (la 1ª corrida a la sesión 1 y la 2ª a la sesión 2).
  - Devuelve el estado de cada sesión: `hecha` o `pendiente`.
  - Marca `ajustada` si se hizo en un día con 🟡 o 🔴.

  **✅** Test.
- **2.11** `today_card(day, light, plan_status, activities, config)` decide qué mostrar hoy:
  - Si hoy ya hay CrossFit registrado, o es lun/mar/jue y no hay corrida hoy → "Hoy es CrossFit".
  - Si no, y hay sesión pendiente → la siguiente sesión pendiente, en versión **normal** si es 🟢, **suave** si es 🟡 y **descanso/caminata** si es 🔴.
  - Si ya están las 2 → "Semana completa, descansa".
  - Si fue 🔴 dos días seguidos → agrega el aviso "repetir la semana".

  **✅** Test de cada rama.
- **2.12** `run_rows(activities, config)` → por corrida: fecha, minutos, FC promedio, % en Z1–Z2 y `eficiencia`. La eficiencia es (velocidad m/min) ÷ FC promedio y solo se calcula para `running` (al aire libre). En caminadora es `None`. **✅** Test.
- **2.13** `max_hr_progress(activities, config)` → las sesiones de CrossFit desde `strap_in_crossfit_since` con su `maxHR`, el pico, la estimación `max(pico + 3, max_hr_floor)`, `revisar = estimación > max_hr_review_above` y `listo = semanas medidas ≥ 2`. **✅** Test.
- **2.14** `watch_zone_mismatch(hr_zones, config)` → aviso si `maxHeartRateUsed` del reloj ≠ `max_hr` del config. Las zonas por actividad vienen del reloj, así que si no coinciden la barra 80/20 queda mal. **✅** Test.

### 🔍 Checkpoint R2 — revisión de métricas
Opus revisa la lógica contra REQUISITOS §2, §4.2 y §5, y corre todos los tests.

## F3 — Build del sitio (`dashboard/build.py`) 🤖

- **3.1** `build.py` lee `data/`, `plan/plan.json` y `config.json`, y escribe `site/data.json` con esta forma:
  ```
  { generado, zonas[], aviso_zonas, hoy{semaforo, señales[], tarjeta},
    semana{dias[7], corridas_hechas, carga, carga_anterior, distribucion},
    plan{semana_actual, semanas[] (con zonas ya convertidas a lpm), estado_sesiones},
    tendencias{dias[] (fecha, hrv, hrv_base_baja, hrv_base_alta, rhr, sueño_h), semanas[] (inicio, carga_crossfit, carga_corrida, sin_rpe)},
    corridas[], fc_max{...} }
  ```
  Si `plan/plan.json` todavía no existe, usa `plan/plan.example.json` (2 semanas de ejemplo que crea Sonnet con el esquema de F4). **✅** Se genera y es JSON válido.
- **3.2** **Privacidad.** Usa una lista blanca: solo se copian campos explícitos. Agrega un test que recorra `site/data.json` y falle si encuentra alguna de estas claves o valores: `activityId`, `activityName`, `ownerDisplayName`, `ownerFullName`, `userProfilePk`, `uuid`, `displayName`, URLs de fotos, `locationName`, ni el nombre o correo del perfil. **✅** El test pasa.
- **3.3** Tamaño menor a 300 KB. Fechas en formato ISO local. **✅** Revisar.
- **3.4** `make`-style: un script `run_local.sh` que corre `garmin_connect.py`, luego `build.py` y luego `python -m http.server -d site 8000`. **✅** Corre.

### 🔍 Checkpoint R3 — revisión del JSON publicado
Opus revisa `site/data.json` real: privacidad, valores razonables y que el semáforo de hoy tenga sentido.

## F4 — Contenido del plan de 12 semanas 🔍 (lo hace Opus, en paralelo a F1–F3)

- **4.1** `docs/PLAN_ENTRENAMIENTO.md`: las 12 semanas en lenguaje humano, con la lógica de progresión (una variable a la vez, descarga en las semanas 4, 8 y 12) y la versión suave de cada sesión.
- **4.2** `plan/plan.json` con el esquema siguiente. Las zonas van por nombre y `build.py` las convierte a lpm, así cambian solas si cambia la FC máx.
  ```json
  { "start": "2026-10-26",
    "weeks": [ { "n": 1, "block": 1, "kind": "carga|descarga", "focus": "texto corto",
      "sessions": [ { "id": "A", "name": "Espiga", "minutes": 30,
        "steps": [ {"kind": "warmup|run|walk|cooldown", "minutes": 5, "zone": "Z1|Z2|Z3|Z1-Z2", "note": ""},
                   {"kind": "repeat", "times": 3, "steps": [ ... ]} ],
        "easy": { "name": "...", "minutes": 20, "steps": [ ... ] } } ] } ] }
  ```
  Sonnet crea `plan/plan.example.json` con este mismo esquema (2 semanas inventadas) para poder trabajar sin esperar.

## F5 — Frontend (`site/`) 🤖

Antes de escribir CSS o gráficas, **carga el skill `dataviz`** y sigue su paleta, sus especificaciones de marcas y sus anti-patrones. Tiene que funcionar a 400 px (celular) y en la Mac, con tema claro y oscuro según el sistema.

- **5.1** Esqueleto: `index.html` con una barra de pestañas fija abajo (**Hoy · Semana · Plan · Tendencias · Más**), cambio de vista por `#hash` y `fetch('data.json')`. Muestra "actualizado hace X". **✅** Las pestañas cambian y el hash funciona al recargar.
- **5.2** Tokens CSS: claro y oscuro, colores de las 5 zonas (fijos y validados con el script del skill) y colores de estado 🟢🟡🔴 siempre con ícono y texto. **✅** El validador pasa.
- **5.3** **Hoy**: semáforo grande con texto, la tarjeta de la sesión de hoy (normal, suave o descanso, con sus pasos) y las 4 señales con ✓/⚠/— y su valor contra la referencia. Aviso de "repetir semana" y `aviso_zonas` si aplican. **✅** Se ve bien a 400 px.
- **5.4** **Semana**: tira de 7 días con íconos y texto (CrossFit / corrida / pendiente / descanso), "corridas 1 de 2", carga contra la semana anterior y la barra de 5 zonas con 5 colores, agrupada en **bajo Z1–Z2 (meta 80 %) · limbo Z3 · alto Z4–Z5 (20 %)**, con la etiqueta "referencia". **✅** Bien a 400 px.

### 🔍 Checkpoint R4 — revisión visual Hoy + Semana
Opus revisa las capturas a 400 px y en escritorio, en claro y oscuro.

- **5.5** **Plan**: tarjetas de las sesiones de la semana actual con sus pasos (y su lpm) listos para copiar a Garmin Connect, más el estado (hecha / pendiente / ajustada). Debajo va la línea de 12 semanas con los 3 bloques, las descargas y la semana actual marcada; al tocar una semana se ven sus sesiones. **✅**
- **5.6** **Tendencias**: selector de 4 / 8 / 12 semanas y 4 gráficas separadas, cada una con un solo eje:
  - HRV con la banda de rango base;
  - FC en reposo;
  - sueño, con una línea en 6.5 h;
  - carga semanal apilada (CrossFit y corrida).

  Las de línea llevan tooltip con cruz y las de barra, tooltip por barra. **✅**
- **5.7** **Más**: tres secciones:
  - Corridas: lista y gráfica de eficiencia aeróbica en el tiempo.
  - FC máx: progreso de la medición y tabla de zonas actual.
  - Cómo funciona: reglas del semáforo, umbrales leídos del JSON y link a los docs en GitHub.

  **✅**
- **5.8** Estados vacíos: si no hay datos de una señal o gráfica, muestra un texto claro en lugar de que se rompa la vista. **✅** Probar con un `data.json` recortado.

### 🔍 Checkpoint R5 — revisión visual completa
Opus revisa todas las pestañas y cruza los números contra `site/data.json`.

## F6 — Publicación 🤖 + 👤

- **6.1** 🤖 `.github/workflows/deploy.yml`:
  - **Disparadores**: `workflow_dispatch` y `schedule` con `cron: "0 13 * * *"`, `"0 19 * * *"` y `"0 1 * * *"` (UTC = 7:00, 13:00 y 19:00 en Mérida).
  - **Pasos**: checkout → Python 3.12 → `pip install -r requirements.txt` → `python garmin_connect.py` con `PERSONAL_API_KEY: ${{ secrets.PERSONAL_API_KEY }}` → `python dashboard/build.py` → `pytest` → `actions/upload-pages-artifact` (carpeta `site/`) → `actions/deploy-pages`.
  - **Permisos**: `pages: write` e `id-token: write`.
  - El caché de `activity_details.json` entre corridas va con `actions/cache`.

  **✅** `actionlint` si está disponible; si no, revisión de Opus.
- **6.2** 🤖 Agrega un `README.md` corto con qué es, cómo correrlo local y cómo forzar una actualización con "Run workflow".
- **6.3** 👤 Pedro corre `! gh auth login`.
- **6.4** 🤖 `gh repo create garmin-dashboard --public --source . --push`.
- **6.5** 👤/🤖 **Secreto.** Se recomienda **regenerar la API key** en developer.garmin.com antes de subirla y pegar la nueva en `.env`. Luego se sube sin mostrarla:
  `grep '^PERSONAL_API_KEY=' .env | cut -d= -f2- | gh secret set PERSONAL_API_KEY`
- **6.6** 🤖 Activa Pages con fuente "GitHub Actions": `gh api -X POST repos/{owner}/garmin-dashboard/pages -f build_type=workflow`. Después corre `gh workflow run deploy.yml` y `gh run watch`. **✅** La Action queda en verde.
- **6.7** **Ojo:** GitHub apaga los `schedule` de los repos públicos tras **60 días sin commits**, y el plan dura 84. Agrega al workflow un paso que, el día 1 de cada mes, haga un commit vacío `chore: keepalive` (con `contents: write`). **✅** Revisión de Opus.

### 🔍 Checkpoint R6 — revisión final
Opus abre `https://<usuario>.github.io/garmin-dashboard/` en el navegador, lo revisa a 400 px y en escritorio, y confirma que en el sitio no aparece ningún dato privado.

---

## Seguimiento

| Fase | Estado |
|---|---|
| F0 Preparación | ✅ |
| F1 Datos · R1 | ✅ |
| F2 Métricas · R2 | ✅ |
| F3 Build · R3 | ✅ |
| F4 Plan 12 semanas (Opus) | ⬜ |
| F5 Frontend · R4 · R5 | 🔄 R5 (5.1–5.8 hechos, en revisión) |
| F6 Publicación · R6 | ⬜ |
