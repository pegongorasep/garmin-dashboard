# Plan de construcción v3: 3 corridas, 2 pestañas, trote/caminata

Fuente de verdad: [`REQUISITOS.md`](REQUISITOS.md) **§7 (APROBADO v3)** y [`PLAN_ENTRENAMIENTO.md`](PLAN_ENTRENAMIENTO.md)
(APROBADO v2). Si este plan los contradice, mandan ellos. El plan v1 de construcción
([`PLAN_CONSTRUCCION.md`](PLAN_CONSTRUCCION.md)) ya está terminado; este documento solo cubre los cambios.

**Meta de fecha:** publicado antes del **miércoles 18 nov 2026** (primera Z2 del plan nuevo).

**Quién hace qué**
- 🤖 **Sonnet** ejecuta los pasos en orden.
- 🔍 **Opus** revisa en cada checkpoint. Sonnet **se detiene** en cada 🔍 y no sigue sin visto bueno.

---

## Reglas para quien ejecuta (léelas antes de empezar)

1. **Nunca leas, imprimas ni copies `.env`** ni la API key. `garmin_connect.py` la carga solo.
2. Un paso = un cambio pequeño + su **✅ verificación**. Si falla, arréglalo antes de seguir.
3. **No inventes requisitos.** Lo que no esté claro va a `docs/DUDAS.md` (sección "v3"); si bloquea, para.
4. Python del `.venv`: `.venv/bin/python`. Tests: `.venv/bin/python -m pytest -q`. **Todos los tests pasan al
   final de cada paso** (si un paso rompe un test viejo a propósito, ese mismo paso lo actualiza).
5. Estilo del código actual: funciones cortas, puras en `metrics.py`, nombres y textos en español, sin
   librerías nuevas (ni Python ni JS). Mira cómo están hechas las funciones vecinas y copia su forma.
6. `metrics.py` no tiene I/O ni reloj. `build.py` es el único con reloj. El JS **solo pinta** `data.json`:
   cualquier cálculo (estados, umbrales, textos de resumen) va en Python con su test.
7. Zona horaria fija **America/Merida**. Las fechas de Garmin ya vienen en hora local.
8. **Privacidad:** a `site/data.json` solo llegan campos de la lista blanca de `build.py`. Nunca nombres de
   actividad, IDs, GPS ni `splitSummaries` crudos.
9. Commit al terminar cada fase (mensaje en español, claro). **No hagas `git push`** hasta la F5.
10. En cada 🔍 entrega: qué hiciste, salida de pytest, y dudas.

---

## Decisiones ya tomadas (no las cambies)

| Tema | Decisión |
|---|---|
| Sesiones por semana | 3: `z2a` "Z2 #1", `z2b` "Z2 #2", `larga` "Larga" |
| Días de CrossFit | lun, mar, jue → `config.crossfit_days = [0, 1, 3]` (0 = lunes) |
| Tiempo de sesión | tiempo de reloj (`duration` de la actividad), caminatas incluidas |
| Asignación | corrida en **sáb/dom** con `minutos + 0.5 ≥ 0.7 × larga.minutes` → Larga (si hay varias, la más larga). Las demás, en orden cronológico, llenan `z2a` y luego `z2b`. Sobrantes = "extra" (no se asignan) |
| Estado | `hecha` si `minutos + 0.5 ≥ 0.7 × ref`; si no, `incompleta`; sin corrida, `pendiente`. `ref` = minutos de la versión suave si ese día fue 🟡/🔴, si no, los normales. `ajustada` = hecha en día 🟡/🔴 |
| Semáforo sin datos | HRV, FC reposo **y** sueño los tres `sin_dato` → color `"sin_datos"`. Sesión normal + aviso "Sin datos de anoche: decide por cómo te sientes" |
| "¿Lo hice bien?" | minutos sobre el techo de Z2 = `hrTimeInZone_3 + _4 + _5` (s → min). ✓ si `≤ 2'`; si la sesión tiene pasos Z3 opcionales, `≤ 4'` |
| Trote/caminata | tramos `RWD_RUN` y `RWD_WALK` de Garmin. `RWD_STAND` se ignora. % trote = trote ÷ (trote + caminata) |
| Ritmo trotando | segundos de `RWD_RUN` ÷ km de `RWD_RUN`. En **caminadora** se muestra pero no entra en gráficas ni resumen |
| Promedio 7 días | media de los valores no nulos de los 7 días que terminan en ese día (incluido); `None` si hay menos de 3 |
| Eficiencia aeróbica (v1) | **se elimina** (la reemplaza el ritmo trotando) |

---

## Forma nueva de `site/data.json`

```
{ generado, datos_al, zonas[], rhr_promedio_7d, aviso_zonas,
  hoy: { semaforo{color: verde|amarillo|rojo|sin_datos, fuera, repetir_semana},
         señales[], tarjeta{tipo, texto, version, sesion_id, aviso, sesion?} },
  ultima_corrida: null | { fecha, minutos, km, fc_prom, caminadora,
         sesion: null | {id, name, minutes_plan, version: normal|suave},
         min_sobre_techo, tolerancia_min, techo_ok, trote: null | RW },
  semana: { dias[7]{fecha, dia_semana, tipo, luz}, sesiones_total, hechas, incompletas,
            minutos, km, min_trote },
  plan: { inicio, semana_actual, semanas_repetidas, semanas[] (pasos en lpm),
          estado_sesiones[]{id, name, tipo, estado, ajustada, fecha, minutos} },
  progreso: { resumen{"4","8","12"}: texto,
              corridas[]{fecha, sesion, minutos, km, fc_prom, pct_z1z2, caminadora, ...RW aplanado},
              semanas[12]{inicio, minutos, km, min_trote, min_camina, plan_min},
              dias[84]{fecha, hrv, hrv_7d, hrv_base_baja, hrv_base_alta, rhr, rhr_7d, sueño_h, sueño_7d} },
  detalles: { distribucion, carga, carga_anterior, carga_semanas[12], fc_max{...}, umbrales } }

RW = { trote_min, camina_min, pct_trote, caminatas, patron_trote_min, patron_camina_min,
       km_trote, ritmo_trote_s, fc_trote }        (fc_trote puede ser null)
```

---

## F1 — Plan y config 🤖

- **1.1** `dashboard/config.json`: `"plan_start": "2026-11-16"`, agrega `"crossfit_days": [0, 1, 3]`,
  `"done_ratio": 0.7`, `"ceiling_tolerance_min": 2`. `semanas_repetidas` sigue en `[]`.
  **Ojo:** `tests/test_build.py` usa este config con `AHORA` = 4 nov → cámbialo para que use una copia con
  `"plan_start": "2026-10-26"` (el fixture es de esa semana). **✅** pytest verde.
- **1.2** Crea `plan/gen_plan.py` (se versiona) que escribe `plan/plan.json` a partir de esta tabla, sacada
  de `PLAN_ENTRENAMIENTO.md`:

  | n | block | kind | z2a | z2b | larga | picos Z3 en z2a |
  |---|---|---|---|---|---|---|
  | 1 | 1 | carga | 20 | 20 | 40 | no |
  | 2 | 1 | carga | 20 | 20 | 45 | no |
  | 3 | 1 | carga | 20 | 25 | 50 | no |
  | 4 | 1 | descarga | 20 | 20 | 30 | no |
  | 5 | 2 | carga | 25 | 25 | 50 | sí |
  | 6 | 2 | carga | 25 | 25 | 55 | sí |
  | 7 | 2 | carga | 25 | 30 | 60 | sí |
  | 8 | 2 | descarga | 20 | 20 | 40 | no |
  | 9 | 3 | carga | 30 | 30 | 60 | sí |
  | 10 | 3 | carga | 30 | 30 | 65 | sí |
  | 11 | 3 | carga | 30 | 30 | 70 | sí |
  | 12 | 3 | descarga | 25 | 25 | 45 | no |

  Esquema (igual al v1 más `tipo` en la sesión y `optional` en el paso):
  ```json
  {"start": "2026-11-16", "weeks": [{"n": 1, "block": 1, "kind": "carga", "focus": "Larga 40'",
    "sessions": [
      {"id": "z2a", "tipo": "z2", "name": "Z2 #1", "minutes": 20,
       "steps": [{"kind": "run", "minutes": 20, "zone": "Z1-Z2", "note": "arranca suave; camina si pasas el techo"}],
       "easy": {"name": "Suave", "minutes": 15, "steps": [{"kind": "run", "minutes": 15, "zone": "Z1-Z2", "note": ""}]}},
      {"id": "z2b", "tipo": "z2", "name": "Z2 #2", ...},
      {"id": "larga", "tipo": "larga", "name": "Larga", ...}]}]}
  ```
  - **Con picos** (z2a de 25'): `10' Z1-Z2 · 1' Z3 (optional) · 3' Z2 · 1' Z3 (optional) · 10' Z1-Z2`.
    De 30': `12 · 1 · 3 · 1 · 13`. Los pasos Z3 llevan `"optional": true` y `"note": "opcional"`.
  - **Versión suave** = un paso Z1-Z2, sin Z3, con: 20→15, 25→20, 30→20, 40→30, 45→30, 50→35, 55→40,
    60→40, 65→45, 70→50.
  - `focus`: "Larga 40'" en carga y "Descarga" en descarga (más " · picos Z3 opcionales" si aplica).
  - `assert`s en el script: cada sesión suma sus minutos; totales por semana =
    `[80, 85, 95, 70, 100, 105, 115, 80, 120, 125, 130, 95]`; ninguna larga ni versión suave tiene Z3.

  **✅** `.venv/bin/python plan/gen_plan.py` escribe 12 semanas y los asserts pasan.
- **1.3** Reescribe `plan/plan.example.json` con el esquema nuevo (2 semanas: copia las semanas 1 y 5 del
  generado, `start` = "2026-10-26"). **✅** pytest verde (arregla `test_plan_convertido_a_lpm` para el esquema
  nuevo: Z1-Z2 con reposo 60 y máx 190 = `[125, 151]`).
- **1.4** `build.convert_steps` copia `optional` (default `false`); `convert_session` copia `tipo`.
  **✅** Test: un paso Z3 opcional sale con `optional: true` y su lpm.
- Commit: "v3 F1: plan de 3 corridas y config".

## F2 — Datos de trote/caminata 🤖

- **2.1** En `garmin_connect.py`, `pull_activity_details`: para **corridas** guarda también
  `"splits"`: lista de `{"tipo": "RWD_RUN"|"RWD_WALK"|"RWD_STAND", "seg": duration, "m": distance,
  "fc": averageHR (o null), "n": noOfSplits}` tomada de `splitSummaries` del **detalle**
  (`/activity-service/activity/{id}`; el detalle sí trae `averageHR` por tipo de tramo).
  Regla de caché nueva: reusar la entrada si `rpe` no es null **y** (no es corrida **o** ya tiene `"splits"`).
  Para CrossFit no se guardan splits. **✅** Corre `garmin_connect.py`; en `data/activity_details.json` la
  corrida del 2026-11-12 tiene RWD_RUN ≈ 1645 s / 3467 m / n 9 y RWD_WALK ≈ 658 s / 893 m / n 9, con `fc`.
- **2.2** Respaldo: si una corrida no tiene `splits` en details, `build` usa `activity["splitSummaries"]` de la
  lista (mismos campos, sin FC → `fc_trote = null`). Lo resuelve la función de 3.1 (recibe ambos).
- Commit: "v3 F2: tramos de trote/caminata".

## F3 — Métricas (`dashboard/metrics.py`) 🤖

Cada paso: función pura + tests en `tests/test_metrics.py` con datos inventados (nunca `data/`).

- **3.1** `run_walk(activity, details) -> dict | None` → RW (ver forma arriba). Fuente: `details[id]["splits"]`
  o, si no hay, `activity["splitSummaries"]` (claves `duration`, `distance`, `noOfSplits`, `splitType`).
  `None` si no hay tramos RUN ni WALK. Sin tramos WALK → `caminatas 0`, `pct_trote 100`,
  `patron_camina_min None`. `patron_*_min` = minutos ÷ `n` del tipo. **✅** Caso 12 nov:
  trote 27.4', caminata 11.0', 71.4 %, 9 caminatas, patrón ≈ 3.05 / 1.22, ritmo ≈ 475 s/km; caso sin
  caminata; caso sin tramos → None; caso respaldo sin FC.
- **3.2** `traffic_light`: si `hrv`, `rhr` y `sueno` son los tres `sin_dato` → `{"color": "sin_datos",
  "fuera": 0, "repetir_semana": False}` (aunque haya RPE). Lo demás igual. **✅** Tests nuevos + los viejos.
- **3.3** `assign_sessions(week, runs, config) -> list` reemplaza a `plan_status`.
  `runs` = `[{"fecha", "minutos", "luz"}]` en orden cronológico. Sigue la tabla de decisiones (Larga en
  fin de semana con 0.7, el resto en orden a z2a/z2b, estado hecha/incompleta/pendiente con `ref` según luz,
  `ajustada`). Devuelve por sesión `{"id", "name", "tipo", "estado", "ajustada", "fecha", "minutos"}`
  (`fecha`/`minutos` null si pendiente). `luz == "sin_datos"` cuenta como verde.
  **✅** Casos: (a) mié 21' + vie 20' + dom 41' → las 3 hechas; (b) sáb 25' con larga de 40 → no es larga
  (25 < 28) → va a z2a; (c) dom 27.6' con larga 40 → larga hecha (27.6 + 0.5 ≥ 28); (d) z2 de 12' → incompleta;
  (e) día amarillo, z2 de 20' con suave 15 → hecha y ajustada; (f) 4 corridas → la sobrante no se asigna;
  (g) sin corridas → 3 pendientes. Borra `plan_status` y sus tests.
- **3.4** `today_card`: usa `config["crossfit_days"]` en vez de `(0, 1, 3)`. Elección de sesión pendiente:
  en **sáb/dom** la Larga si está pendiente, si no la primera Z2 pendiente; **entre semana** la primera Z2
  pendiente, y si solo falta la Larga → tipo `sesion` con esa sesión y `aviso` "La larga va el sábado o
  domingo". `incompleta` **no** es pendiente. Color `sin_datos` → versión `normal` y `aviso` "Sin datos de
  anoche: decide por cómo te sientes" (si ya había aviso, se unen con " · "). Texto de `completa`:
  "Semana completa". **✅** Test por rama nueva.
- **3.5** `run_check(activity, session) -> dict`: `min_sobre_techo` (Z3+Z4+Z5 en min, 1 decimal),
  `tolerancia_min` = 2 (+2 si algún paso de `session` tiene `optional`), `techo_ok`. `session` puede ser
  None (tolerancia 2). **✅** Tests.
- **3.6** `rolling_mean(valores, ventana=7, minimo=3) -> list` sobre una lista con nulos. **✅** Tests con huecos.
- **3.7** `run_rows(activities, details, config)`: quita `eficiencia`; agrega `km`, `caminadora`
  (`typeKey == "treadmill_running"`) y los campos RW aplanados (o null). **✅** Tests actualizados.
- **3.8** `progress_summary(rows, hoy, semanas) -> str`: compara las corridas **al aire libre** de las últimas
  `semanas` contra las `semanas` anteriores: % trote promedio y ritmo trotando promedio. Formato:
  `"Trotas 68 % del tiempo (antes 58 %) · ritmo trotando 7:40 → 7:25 /km"`. Si un lado no tiene corridas:
  `"Aún no hay corridas suficientes para comparar"`. Ritmo `mm:ss`. **✅** Tests (incluye sin datos).
- **3.9** Borra `watch_zone_mismatch` si quedó algo de él y cualquier función que ya nadie use. **✅** `grep`.

### 🔍 Checkpoint R1 — métricas
Opus revisa la lógica contra la tabla de decisiones y corre pytest.

## F4 — Build (`dashboard/build.py`) 🤖

- **4.1** `week_runs(week_start, hasta, data, config)` (generaliza la actual) → corridas de esa semana hasta
  `hasta`, con `minutos` y `luz`. Una función `week_assignment(day, ...)` devuelve, para la semana del plan que
  contiene `day`, `(semana_plan, asignación)` o `(None, [])`. **✅** Test.
- **4.2** Arma `hoy`, `plan.estado_sesiones` (con `assign_sessions`) y `semana` con la forma nueva
  (`sesiones_total`, `hechas`, `incompletas`, `minutos`, `km`, `min_trote`). **✅** Test de forma.
- **4.3** `ultima_corrida`: la corrida más reciente (cualquier fecha). Su `sesion` sale de la asignación de
  **su** semana (null si cae fuera del plan o es extra), con `version` según la luz de ese día y
  `minutes_plan` de esa versión. Incluye `run_check` y `trote` (RW). **✅** Test con el fixture.
- **4.4** `progreso`: `resumen` para 4/8/12, `corridas` (con `sesion` = nombre si fue asignada), `semanas`
  (12 semanas: minutos, km, min_trote, min_camina de corridas; `plan_min` = suma de la semana del plan o
  null), `dias` (84 días con `*_7d` vía `rolling_mean`; calcula el promedio con 6 días extra antes de la
  ventana para que el primer punto no salga vacío). **✅** Tests.
- **4.5** `detalles`: mueve ahí `distribucion`, `carga`, `carga_anterior`, `carga_semanas` (lo que era
  `tendencias.semanas`), `fc_max` y `umbrales`. Quita `tendencias` y `corridas` de la raíz. **✅**
  `test_forma_y_json_valido` actualizado con las claves nuevas.
- **4.6** Privacidad: agrega `"splitSummaries"`, `"splits"`, `"endLatitude"`, `"endLongitude"` a
  `PROHIBIDAS`; el fixture de `test_build.py` gana `splitSummaries` en sus corridas y `splits` en details.
  **✅** Tests de privacidad verdes (fixture y datos reales).
- **4.7** Flag nuevo `--plan-start YYYY-MM-DD` en `build.py` (solo para pruebas visuales; sobreescribe el
  config en memoria). **✅** `build.py --day 2026-11-14 --plan-start 2026-11-09` → la corrida del 12 nov
  sale como Z2 #1 hecha y `ultima_corrida.sesion.name == "Z2 #1"`.
- **4.8** Tamaño `< 300 KB` con datos reales. Commit: "v3 F4: build con forma nueva".

### 🔍 Checkpoint R2 — JSON
Opus revisa `site/data.json` real (con y sin `--plan-start`): privacidad, números contra Garmin, semáforo.

## F5 — Frontend 🤖

Antes de tocar gráficas o CSS, **carga el skill `dataviz`** y sigue sus reglas (un eje, marcas finas,
tooltip, leyenda si hay ≥ 2 series, tabla "Ver como tabla"). Colores nuevos: valida con su script en claro y
oscuro. Debe verse bien a **400 px** y en escritorio, claro y oscuro. Mantén las utilidades `h()`, `fmt`,
`badge`, `tablaDatos`, `pasoLi`.

- **5.1** Navegación: 2 pestañas abajo, **Hoy** (`#hoy`) y **Progreso** (`#progreso`). Vista **Detalles**
  (`#detalles`) sin pestaña: se abre con un enlace "Detalles: zonas, reglas, intensidad y carga →" al final
  de Hoy y de Progreso, y tiene un "← Volver" arriba. Hash desconocido → Hoy. **✅** Recargar con cada hash.
- **5.2** Hoy, en este orden:
  1. **Semáforo** (como hoy) con las 4 señales dentro de la misma tarjeta. Color `sin_datos`: gris, ícono
     "—", título "Sin datos", texto "No hay datos de anoche: decide por cómo te sientes".
  2. **Sesión de hoy** (tarjeta actual, adaptada: "Sesión Z2 #1 · 20 min", pasos con "(opcional)" en los
     Z3 opcionales, `aviso` si viene).
  3. **Última corrida — ¿lo hice bien?**: fecha, sesión ("Z2 #1 · plan 20'" o "sin sesión del plan"),
     `minutos · km`, línea de techo ("✓ 1.5' sobre el techo (tolerancia 2')" o "⚠ 6' sobre el techo"),
     **barra trote/caminata** (2 segmentos, separación de 2 px, etiqueta directa "Trote 27' · Caminata 11'"),
     "9 caminatas · patrón ≈ 3:03 / 1:13", "Ritmo trotando 7:55 /km a 145 lpm" (sin FC si es null;
     "caminadora" si aplica). Sin corrida → texto vacío claro.
  4. **Semana**: la tira de 7 días (badge gris para `sin_datos`) + "2 de 3 corridas · 9.1 km · 52' trotando"
     (+ "· 1 incompleta" si hay).
  5. **Plan de la semana** ("Semana n de 12 · bloque b · carga/descarga"): las 3 sesiones como filas
     compactas (nombre, minutos, estado: Hecha / Hecha · ajustada / Incompleta / Pendiente). Cada fila con un
     `<details>` que tiene pasos, versión suave y "Cómo crearla en Garmin Connect". Sin semana activa:
     "El plan arranca el lunes 16 nov".

  **✅** Capturas a 400 px y escritorio, claro y oscuro (ver "Cómo hacer capturas").
- **5.3** `charts.js`: (a) `lineChart` acepta `cfg.puntos` (dibuja la serie como puntos pequeños r=2.5 sin
  línea) y `cfg.promedio` (array de y del mismo largo, dibujado como línea de 2 px); el tooltip muestra ambos
  vía `cfg.texto`. (b) `cfg.invertir` voltea el eje y (para ritmo: arriba = más rápido). (c) `barChart` acepta
  `meta` por semana (raya horizontal fina en el valor del plan, color de texto secundario, no de serie).
  **✅** Las gráficas existentes siguen igual sin las opciones nuevas.
- **5.4** Progreso, en este orden (selector 4 / 8 / 12 semanas arriba, como el de Tendencias):
  1. Frase `resumen[periodo]` en grande.
  2. **% del tiempo trotando** por corrida (puntos + línea, solo aire libre).
  3. **Ritmo trotando** por corrida (invertido, eje en `mm:ss`, tooltip con FC trotando).
  4. **Volumen semanal**: barras apiladas trote/caminata (minutos) con raya del plan; tooltip
     "Semana del 23 nov · 95' (plan 100') · 9.1 km · trote 62'"; leyenda Trote / Caminata / — Plan.
  5. **Recuperación**: HRV (puntos diarios + línea 7 días + banda base), FC reposo (puntos + línea 7 días),
     sueño (puntos + línea 7 días + raya en 6.5 h). Subtítulo con el último promedio de 7 días.
  6. **12 semanas**: la línea de bloques actual (de la vista Plan); al tocar una semana se ven sus 3 sesiones
     debajo (filas compactas como en Hoy, sin estado salvo en la semana actual).
  7. **Corridas**: tabla Fecha · Sesión · Min · Km · % trote · Ritmo trote · FC prom (más recientes primero).

  Cada gráfica con "Ver como tabla". **✅** Capturas.
- **5.5** Detalles: FC máxima y zonas (tarjeta actual), Cómo funciona (actualiza el texto: 3 corridas,
  asignación automática, "sin datos", tolerancia del techo), Intensidad de la semana (barra 80/20 actual) y
  Carga (tarjeta de carga + barras de carga de 12 semanas). **✅** Capturas.
- **5.6** Borra el código muerto de las vistas viejas (Semana, Plan, Tendencias, Más, eficiencia).
  Estados vacíos: prueba con un `data.json` recortado (sin `ultima_corrida`, sin `progreso.corridas`, plan
  sin semana activa) y que ninguna vista truene. **✅**
- Commit: "v3 F5: frontend Hoy / Progreso / Detalles".

### 🔍 Checkpoint R3 — revisión visual
Opus revisa capturas de las 3 vistas (400 px y escritorio, claro y oscuro) y cruza números con `data.json`.

## F6 — Publicar 🤖

- **6.1** Actualiza `README.md` (2 pestañas + Detalles, plan de 3 corridas, `plan/gen_plan.py`) y la tabla de
  seguimiento de este documento.
- **6.2** `pytest` verde → `git pull --rebase` (el repo recibe commits `chore: keepalive`) → `git push` →
  `gh workflow run deploy.yml` → `gh run watch <id> --exit-status`. **✅** Run en verde.
- **6.3** Verifica en vivo: `curl -s https://pegongorasep.github.io/garmin-dashboard/data.json` trae
  `progreso`, `ultima_corrida` y `plan.inicio == "2026-11-16"`, y no contiene nombres de actividad.

### 🔍 Checkpoint R4 — final
Opus abre el sitio en vivo a 400 px y escritorio.

---

## Cómo hacer capturas

1. `.venv/bin/python dashboard/build.py --day 2026-11-14 --plan-start 2026-11-09` (semana con datos) y
   `.venv/bin/python -m http.server -d site 8000` en segundo plano.
2. Chrome headless no baja de ~500 px de ancho: para 400 px crea en el scratchpad un HTML con
   `<iframe src="http://localhost:8000/#hoy" width="400" height="2400">` y captúralo.
   ```
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars \
     --window-size=420,2400 --virtual-time-budget=4000 --screenshot=<scratchpad>/hoy-400.png file://<scratchpad>/marco.html
   ```
   Escritorio: `--window-size=1280,2400` directo a `http://localhost:8000/#hoy`. Oscuro: agrega
   `--force-dark-mode` (si no cambia, `--blink-settings=preferredColorScheme=0`).
3. `--virtual-time-budget` evita la captura en "Cargando…". Mira cada captura antes de seguir.
4. Al terminar, regenera sin flags (`build.py`) para no dejar un `data.json` de prueba.

---

## Seguimiento

| Fase | Estado |
|---|---|
| F1 Plan y config | ✅ |
| F2 Datos trote/caminata | ✅ |
| F3 Métricas · R1 | ⬜ |
| F4 Build · R2 | ⬜ |
| F5 Frontend · R3 | ⬜ |
| F6 Publicar · R4 | ⬜ |
