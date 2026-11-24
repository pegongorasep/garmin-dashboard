# Dudas y hallazgos

## 1.2 RPE en el detalle de actividad (2026-10-24)

- Se pidió el detalle de **una** actividad: una corrida (2026-10-21) con `GET /activity-service/activity/{id}`. Guardado en `data/sample_activity_detail.json`.
- Claves de primer nivel: `activityId, activityUUID, activityName, userProfileId, isMultiSportParent, activityTypeDTO, eventTypeDTO, accessControlRuleDTO, timeZoneUnitDTO, metadataDTO, summaryDTO, locationName, splitSummaries`.
- Claves de `summaryDTO`: aerobicTrainingEffectMessage, anaerobicTrainingEffect, anaerobicTrainingEffectMessage, averageHR, averageMovingSpeed, averagePower, averageRunCadence, averageSpeed, averageTemperature, avgElevation, avgGradeAdjustedSpeed, bmrCalories, calories, differenceBodyBattery, **directWorkoutFeel**, **directWorkoutRpe**, distance, duration, elapsedDuration, elevationGain, elevationLoss, endLatitude, endLongitude, groundContactTime, maxElevation, maxHR, maxPower, maxRunCadence, maxSpeed, maxTemperature, maxVerticalSpeed, minActivityLapDuration, minElevation, minHR, minPower, minTemperature, moderateIntensityMinutes, movingDuration, normalizedPower, startLatitude, startLongitude, startTimeGMT, startTimeLocal, steps, strideLength, totalWork, trainingEffect, trainingEffectLabel, verticalOscillation, verticalRatio, vigorousIntensityMinutes, waterEstimated.
- **El RPE sí existe**: `summaryDTO.directWorkoutRpe = 50` y `summaryDTO.directWorkoutFeel = 50` en esta corrida.
- **Escala**: RPE guardado ×10 (50 = RPE 5). El script divide entre 10. `feel` también viene en pasos de 25 (0, 25, 50, 75, 100); se guarda tal cual, sin interpretar.
- Pendiente de confirmar con más datos: si las actividades antiguas (sin autoevaluación) traen la clave en `null` o ausente. El código guarda `null` en ambos casos.
- Nota de privacidad: el detalle trae coordenadas y `locationName`; por eso `activity_details.json` guarda solo `rpe` y `feel`.

## 1.3 Resultado real del pull (2026-10-24)

- 16 actividades de corrida/CrossFit en la ventana de 120 días; 8 con RPE, 8 sin RPE (`null`): los 2 HIIT más recientes (22 y 23 oct), el HIIT del 5 oct y 5 actividades más antiguas. Confirma que la autoevaluación estaba apagada en HIIT/fuerza; las corridas recientes sí traen RPE (4–5).
- Las 5 corridas recientes con RPE traen `feel` = 50; las antiguas, 75 o 100.
- Ojo: el caché solo salta las actividades que ya tienen RPE, así que las que están en `null` se vuelven a pedir en cada corrida (8 peticiones extra, ~9 s totales). Es intencional: Pedro puede poner el RPE después en Garmin Connect.
- `strength_training` no aparece en la ventana; el CrossFit actual se registra solo como `hiit`.

## F2 Supuestos de `dashboard/metrics.py` (2026-10-24)

- `day`, `week_start` son `date`; el semáforo se devuelve como texto: `verde` / `amarillo` / `rojo`. `traffic_light` devuelve un dict `{color, fuera, repetir_semana}`; `prev_light` es el color de ayer (o `None`).
- Las señales se devuelven en un dict con claves `hrv`, `rhr`, `sueno`, `rpe`. La de HRV lleva además `hrv_baja`.
- Zonas: el techo de cada zona es el piso de la siguiente (Z5 llega a la FC máx), así Z2 = 138–151 con 190/60. Los pisos y techos comparten el límite (p. ej. 151 es techo de Z2 y piso de Z3).
- RPE de ayer: si ayer hubo CrossFit pero ninguna sesión tiene RPE, la señal es `sin_dato` (no `ok`). Con CrossFit de varias sesiones se toma el máximo de las que sí tienen RPE.
- `plan_status` recibe las corridas hechas como `[{"fecha", "luz"}]` en orden. Devuelve `estado` = `hecha` | `pendiente` y `ajustada` como booleano aparte (en vez de un tercer estado).
- `today_card`: si hoy es lun/mar/jue, ya hay una corrida registrada hoy y quedan sesiones pendientes, muestra la siguiente sesión. Las ramas de CrossFit tienen prioridad sobre el semáforo; en CrossFit solo se agrega el aviso de "repetir semana".
- `week_load` cuenta en `sin_rpe` las actividades de corrida/CrossFit de la semana sin RPE. Firma: `week_load(activities, details, week_start, config)`.
- `max_hr_progress`: "semanas medidas" = semanas lun–dom distintas con al menos una sesión de CrossFit con `maxHR` desde `strap_in_crossfit_since`. No distingue si esa sesión se grabó con correa.
- `watch_zone_mismatch` acepta la lista de `hr_zones.json` y usa el perfil `DEFAULT` (o el primero). **Hallazgo real**: el reloj usa FC máx **203** y reposo 64 (Z1 desde 134); el dashboard usa 190. Hay que cambiar el reloj a 190, como pide REQUISITOS §3.1, o las barras de zonas por actividad no son comparables con las del plan.
- Eficiencia = velocidad (m/min) ÷ FC prom, solo para `running`; en caminadora es `None`.
- `rhr_7d` considera la ventana [day−7, day−1].

## Correcciones tras R2 (2026-10-24)

- `today_card` ahora devuelve `tipo = "hecha_hoy"` si ya hay corrida hoy (y no es día de CrossFit por actividad registrada). Orden: CrossFit → hecha_hoy → completa → sesion.
- Texto del sueño en h:mm ("Sueño 6 h 29 min, mínimo 6 h 30 min"); `valor` sigue en horas decimales.
- **Repetir semana**: `dashboard/config.json` tiene `"semanas_repetidas": []` (números de semana del plan que se repitieron; una semana puede aparecer más de una vez). `week_index(day, plan_start, repetidas)` empuja el resto del plan una semana por cada repetición. **La revisión semanal (Claude) es quien edita esta lista** cuando el aviso "repetir la semana" se confirma; el dashboard solo avisa, no la modifica.

## F3 Supuestos de `dashboard/build.py` (2026-10-24)

- `semana.dias[].tipo`: días pasados = `crossfit` / `corrida` / `descanso` según lo que se registró (si hay ambos, `crossfit`); hoy = lo registrado o `hoy`; días futuros = `futuro`. No se usa "pendiente" por día; las corridas pendientes salen de `plan.estado_sesiones`.
- Antes del inicio del plan (`semana_actual` = null) la tarjeta de hoy es `sin_plan` ("Hoy no hay semana de plan activa"); lo agregué a `today_card` porque sin sesiones devolvía "Semana completa", que era engañoso.
- Las zonas del plan en lpm usan `max_hr` del config y el reposo promedio de 7 días de hoy (60 si no hay dato). Un paso "Z1-Z2" va del piso de Z1 al techo de Z2.
- Se agregó `datos_al` (hora local de la última descarga, de `pulled_at_utc`), `rhr_promedio_7d` y `umbrales` al JSON; no estaban en la forma del plan pero el frontend los necesita.
- `plan/plan.json` (de Opus) ya existía y se usa; `plan.example.json` solo es el respaldo.
- La prueba de privacidad con datos reales compara contra los `activityName` y los datos del perfil de `data/` (se salta si no hay `data/`).

## F5 (5.1–5.4) Frontend (2026-10-24)

- Colores de zona (orden bajo -> alto, azul · verde · violeta · naranja · ciruela), distintos de los de estado. Claro: `#2a78d6 #1baf7a #6250d6 #eb6834 #a8326e`; oscuro: `#3987e5 #199e70 #9085e9 #e5632f #c0417f`. Ambos pasan `validate_palette.js` (adyacentes). Se descartó azul-verde-amarillo-naranja-rojo porque amarillo/naranja/rojo no se separan (ΔE normal 7–12 < 15). Z3 es violeta ("en medio" entre frío y cálido).
- Avisos del validador: en claro, el verde Z2 queda en 2.74:1 contra la superficie (WARN de contraste): se compensa con leyenda con etiquetas, tooltip y vista de tabla. En oscuro la separación tritan Z4/Z5 es 4.0 (el validador pasa por el ΔE de visión normal 16 y deutan 15.7).
- El sitio está en español, sin librerías ni CDN. Se probó con Chrome headless (400 px dentro de un iframe y 1280 px, claro y oscuro).
- Las pestañas Plan, Tendencias y Más son marcadores de posición hasta 5.5–5.7.

## F5 (5.5–5.8) (2026-10-24)

- Las gráficas son SVG a mano (`site/charts.js`); las vistas Plan, Tendencias y Más están en `site/vistas.js`.
- Las series de las gráficas usan dos colores categóricos (azul = CrossFit y todas las líneas, naranja = corrida), distintos del orden de zonas pero con los mismos tonos que Z1 y Z4. Se distinguen por leyenda y tooltip; no se validaron como pareja aparte.
- Los links a docs apuntan a `https://github.com/pegongorasep/garmin-dashboard/blob/main/docs/` (repo previsto en F6); no resuelven hasta publicar.
- Estados vacíos probados con un `data.json` recortado en una carpeta temporal (arreglos vacíos y nulos): ninguna vista lanza error ni muestra el mensaje de fallo. Cada vista además está envuelta en try/catch y muestra "No se pudo mostrar esta sección" si faltaran claves.
- Se probó con un script en Chrome headless: la cruz y el tooltip de línea, el tooltip por barra, el selector de 4 semanas y el cambio de semana del plan funcionan.
- **F5 colores**: la caminata usa un gris neutro (`--walk` `#8f8d86` claro / `#8a8882` oscuro) frente al azul del trote (`--s1`). `validate_palette.js` pasa separación (ΔE normal 18.5 / 17.0), CVD y contraste ≥ 3:1 en claro y oscuro, pero marca "chroma floor" (lee gris) a propósito: la caminata es lo "no trote" y siempre va con etiqueta directa y leyenda.
- **F5 capturas**: Chrome headless sigue el modo del sistema, así que claro/oscuro se forzaron con `--blink-settings=preferredColorScheme=1/0`.
- **F2/F3**: `run_check` recibe un tercer argumento opcional `config` para leer `ceiling_tolerance_min` (la firma del plan era `(activity, session)`; sin config usa 2).
- **F4**: `ultima_corrida.sesion` y `progreso.corridas[].sesion` emparejan corrida y sesión por `(fecha, minutos)` de la asignación de su semana.

## v3.1

- `proxima_id` en `today_card` solo se llena en `crossfit` y `hecha_hoy`; si no hay `status` (sin plan activo) queda `None`.
- `estado_sesiones[].corrida` va en plano (sin objeto `trote` anidado); si Garmin no dio tramos, los campos de trote/caminata son `null` y la vista dice que no hubo tramos.
- "Última corrida: …" en la tarjeta Esta semana solo sale si además no hay minutos de corrida esta semana (si no, repetía lo que ya muestra la tarjeta, p. ej. antes del plan).
- La tarjeta de "HOY" se resalta con fondo de página y borde azul de acento (no amarillo) para no confundirla con una alerta.
- La barra de progreso es un solo color de acento (`--s1`) sobre la rejilla; el valor siempre va en texto ("38 / 80 min · 48 %") y con `role="progressbar"`.
- La función de `app.js` se llama `tarjetaTusCorridas` porque `vistas.js` ya tenía `tarjetaCorridas` (tabla de Progreso).
- La fecha de la fila hecha usa `fechaCorta` existente ("jueves 12 nov"), no la abreviada del esquema.

## v3.2 (2026-11-14)

Decisiones que se apartan del plan o que el plan dejaba abiertas:

- **Parámetro de captura.** `#hoy?sem=+1` / `#hoy?sem=-2` es un desplazamiento **relativo** a la semana de hoy (`semana_hoy_idx`); solo se lee al arrancar (`leerSemanaInicial`). `mostrarVista` ignora lo que va después de `?`.
- **Captura 3.** Con `--day 2026-11-24` la semana de hoy es la 3, así que la semana 1 se ve con `sem=-2` (no `-1`).
- **Captura 5.** Con `--day 2026-11-04` la semana 2–8 nov no tiene corridas hasta hoy (las de Garmin en caché son del 5 nov en adelante), así que no sale ningún "Extra". Se agregó `esc5b` con `--day 2026-11-08` (corrida del jue 5 nov sin sesión = Extra, y CrossFit con TE). Las dos quedan en las capturas.
- **Claves v3.1.** `semana` y `plan.estado_sesiones` se dejaron en `data.json` (el plan permitía borrarlas, pero los tests de v3.1 las usan y cuestan pocos KB); el JS ya no lee `semana`.
- **`corrida_de_sesion`** ahora devuelve `None` cuando `e["fecha"]` es `None` (pendiente o no hecha) y la lógica común de la corrida quedó en `corrida_plana`, usada también por los extras.
- **`mejora`.** El % trote promedio de la frase y la gráfica incluyen corridas en caminadora (el trote/caminata viene de los tramos de Garmin y no depende del lugar); Progreso sigue excluyéndolas del % trote. La frase cuenta corridas por semana = corridas ÷ 4, y omite "(antes …)" si las 4 semanas anteriores no tienen corridas. Si solo las anteriores tienen: "Últimas 4 semanas: sin corridas (antes … por semana)."
- **`composicion`** se carga desde `plan/inbody.json` vía `load_data()` (clave `inbody` en `data`), para que `build()` siga con la misma firma. `puntuacion` y `grasa_visceral` solo salen si existen.
- **Calendario.** Día con corrida y CrossFit a la vez muestra ambos (círculo + "CF" abajo). Estados del círculo: hecha = acento, incompleta = advertencia, Extra = neutro con borde. El TE se muestra siempre con 1 decimal.
- **Línea InBody** se parte en dos líneas a 400 px: fecha · grasa · músculo, y debajo la visceral con su badge ("por encima" si > 9); así no desborda ni deja separadores colgando. Color bueno = `--bien-ink` (verde de texto, más oscuro que `--ok` para contraste).
- **`lineChart`/`barChart` extendidos** sin romper usos previos: `clase`, `nombre`, `extra` (más series, mismo eje), `verticales`, `fmtX`, `etiquetaFinal` (la etiqueta va abajo del punto si la serie venía bajando). Paleta s1/s2 validada con `validate_palette.js`: claro `#2a78d6,#eb6834` sobre `#fcfcfb` y oscuro `#3987e5,#d95926` sobre `#1a1a19`, todo PASS (CVD ΔE ≥ 24.7). Masa grasa = s2 (naranja), músculo = s1 (azul), en las dos gráficas de composición.
- **Capturas.** Claro/oscuro con `--blink-settings=preferredColorScheme=1|0` (el sistema está en oscuro y `--force-dark-mode` no basta). Un iframe de 5000 px sale en blanco; Progreso se captura a 4300 px. Con `--day` pasados, `progreso` usa también actividades posteriores del caché (solo afecta pruebas visuales).
- **Semanas futuras** muestran "Plan: 3 sesiones · 85 min" (sin barra) en vez de "0 de 3".

## v4

- **Regla de oro / referencia.** `site/data.json` de v3.2 guardada en el scratchpad (`data_ref_v32.json`); se compara con un script que imprime claves nuevas (+), quitadas (−) y valores distintos (~). `generado` cambia con el reloj y se ignora. `build.py` no tiene reloj fijo; la comparación es inmediata (mismo día) y `datos_al` no cambia.
- **F0.** `config.yaml` se parsea con fechas YAML (`2026-11-09` llega como `date`); `cargar_config` las normaliza a texto ISO. `plan_start` debe ser lunes (error claro si no). `fc_max_piso` por defecto = `fc_max`. `dashboard/config.json` borrado. Dependencia: `pyyaml>=6.0` (las demás tampoco están fijas exactas, se mantuvo el estilo `>=`).
- **F0.** `garmin_connect.py` pide detalles (RPE) de corridas + todos los tipos de las categorías (`tipos_con_detalle`), no solo los de CrossFit.
- **F1 diferencias permitidas en `data.json` (Pedro).** `semanas_hoy[].dias[].crossfit` -> `otras` (lista `[{cat, te, rpe, minutos}]`); `planeado: "cf"` -> `"crossfit"` (id de la categoría); `detalles.carga_semanas[].carga_crossfit` -> `cargas: {crossfit: …}`; `hoy.tarjeta.tipo "crossfit"` -> `"otra"` + `categoria`; claves nuevas `ui`, `detalles.fc_max.configurada`, `detalles.umbrales.max_hr_review_above`. Verificado con un normalizador de la referencia: el resto es idéntico.
- **F1 capturas de Pedro.** Pixel-idénticas a las de v3.2 en Hoy, Progreso y Detalles (400 y 1100 px, claro/oscuro), salvo que en una captura la barra inferior fija no salió (glitch de captura). Chrome headless no baja de ~500 px de ancho: a 400 px se usa un iframe y se recorta con `sips`.
- **F1 colores de categoría.** `clase` = nombre de color (`azul`, `aqua`, `violeta`, `amarillo`) y depende de cuántas categorías hay (1: azul; 2: azul/aqua; 3: azul/aqua/violeta; 4: azul/amarillo/violeta/aqua). La corrida siempre es naranja y va al final de la pila; se eligieron esas órdenes para que el validador de `dataviz` pase (CVD y visión normal, adyacentes, claro y oscuro). Amarillo/aqua en claro quedan <3:1 de contraste: se cumple con leyenda visible, tooltip y tabla de datos; las letras del calendario van en tinta, el color es solo una raya.
- **F1 `today_card`.** Una actividad hecha hoy ocupa el día solo si su categoría es `intensa` (como antes con CrossFit); las no intensas solo cuentan si es el día típico y no hubo corrida. Aviso de pierna solo cuando lo sugerido es Larga o calidad; no cambia la sesión sugerida.
- **F1 `acciones_url`** sale de `GITHUB_REPOSITORY`; en local queda `null` y el enlace se oculta (en capturas de Pedro se fijó la variable). El test de privacidad permite esa única URL.
- **F1** `document.title` = `Garmin · {titulo}` (antes "base aeróbica" en minúscula).
- **F2 escalado de la progresión.** Los incrementos de la tabla de Pedro se guardan como deltas sobre base 20'/40' (tres bloques × [carga1, carga2, carga3, descarga]) y se escalan con `base × (1 + delta/ref)`, redondeo a 5' (mitades hacia arriba, mínimo 10'). Con la base de Pedro reproduce `plan/plan.json` exacto (test).
- **F2 versión suave.** Minutos conocidos usan la tabla de v3.2; los demás ~72 % redondeado a 5' (mín. 10'). 45' -> 30' de la tabla de Pedro es irregular y por eso se conserva como tabla.
- **F2 `semanas` != 12.** Se recorta el patrón (p. ej. 8 = dos bloques); más de 12 repite el bloque 3 sin subir más. `week_index` recibe `total` (`plan_semanas`) en lugar del 12 fijo.
- **F2 calidad.** Sesiones de carga: `z2a`, `calidad` (tipo `calidad`, `calidad_tipo`, `objetivo`), `larga`; en descarga: `z2a`, `z2b`, `larga` (la calidad se vuelve Z2). Cada repetición lleva su recuperación (la última se junta con el enfriamiento de 5'); la recuperación es `run` Z1-Z2 con nota "suave". `minutes` de la sesión = suma real (p. ej. tempo 2x10' = 41').
- **F2 caminatas.** Los pasos son `repeat` de [trote t', caminata 1'] con t = 3/5/8 por bloque; el resto se cubre con una repetición final ajustada. La nota "si una semana te sientes bien…" va en `nota` de la sesión (sin picos de Z3 cuando hay caminatas). `convert_session` ahora pasa `nota`, `objetivo` y `calidad_tipo`.
- **F2 `run_check` de calidad.** Agrega `calidad: {zona, min_zona, objetivo_min, ok, min_arriba, mucho_arriba}`; `ok` = min_zona >= done_ratio × objetivo; `mucho_arriba` = minutos sobre la zona > max(2', 25 % del objetivo). Solo aparece en sesiones de calidad (Pedro: sin cambios en `data.json`). Asignación: `week_runs` agrega `zonas` por corrida; la calidad es la primera corrida no-Larga con >= 50 % del objetivo en Z3+.
- **F3 capturas.** Tres escenarios, cada vista a 400 y 1100 px en claro y oscuro, en `scratchpad/v4/`: `pedro_*` (idéntico a v3.2: se comparó byte a byte contra `pedro_old_*`; en 400 px algunas difieren solo en la barra inferior fija, que a veces no sale en la captura), `esc2_*` (corredor con calidad, 3 categorías, día de pierna, sin InBody, sin caminatas -> modo ritmo; datos de Pedro con otra config, más dos Z2 y una calidad sintéticas) y `esc3_*` (usuario nuevo sin datos, plan que empieza el 7 dic). No hay errores de consola en ninguna (se verificó que no aparece "No se pudo mostrar esta sección").
- **F3 "Cómo vas mejorando".** Modo `ritmo` si hay corridas en las últimas 4 semanas calendario y ninguna tuvo caminatas; si no hay corridas recientes se queda en `trote`. Ritmo en Z2 = `ritmo_trote_s` (la fuente de la gráfica de Progreso) o, si Garmin no dio tramos, minutos/km de la corrida; solo aire libre y FC promedio dentro de Z2. La tarjeta de Progreso ("% del tiempo trotando", "Ritmo trotando") no cambia: sin caminatas queda vacía o con el ritmo total.
- **F3 primer día / plan futuro.** `hoy.tarjeta.tipo = "primera_sync"` cuando no hay actividades ni días de salud; con plan futuro agrega ". Tu plan empieza el lun 7 dic". `semana_hoy_idx` apunta a la semana 1 mientras hoy < inicio del plan (vista previa); las semanas pasadas siguen accesibles con ‹. Con datos pero plan futuro, un día típico de actividad sigue diciendo "Hoy es {categoría}".
- **F3 calidad.** La sesión en `plan.semanas[].sessions[]` trae `estructura` ("10' Z2 · 4×5' threshold (2' suave) · 5' suave") y `objetivo.lpm`. Al hacerla, "Minutos en Z4: 17 de 20 ✓" reemplaza la línea de techo de Z2.
- **F3** `build.py --out` nuevo (ruta de salida), usado para construir los escenarios sin tocar `site/data.json`.
- **F4 sin `actionlint`.** No está instalado: los cinco YAML se parsearon con PyYAML (estructura de jobs correcta) y se revisaron a mano. Nada de esto se probó en GitHub real: `uses: ./.github/workflows/motor.yml` con `motor_ref: ${{ github.sha }}`, el `checkout` del motor en `motor/`, `secrets` explícitos, el push de "instrucciones al día" y el reparto de permisos entre `build` (contents/pages/id-token) y `deploy` (pages/id-token) quedan para el primer run real (F6).
- **F4 concurrencia.** El grupo `pages` está solo en el `deploy.yml` de quien llama, no en `motor.yml`: el mismo grupo en el llamador y en el llamado se bloquea a sí mismo.
- **F4 pytest de Pedro.** Es un job `pruebas` antes de `publicar` (`needs`), no un paso dentro de `motor.yml`; si falla, no se publica.
- **F4 sincronización de instrucciones.** Copia `template/CLAUDE.md` y reemplaza `.claude/skills/` completa (para que desaparezcan skills quitadas); no toca el resto de `.claude/` (p. ej. `settings.local.json`) ni `.github/workflows/`. Los cron del template están en UTC (los de Pedro, para Mérida); `/setup` debería ajustarlos a la zona del usuario si importa.
- **F4 prueba local.** "Repo de amigo" en `scratchpad/amigo/` (config de corredor con calidad, `gen_plan.py`, `data/` de Pedro): `GARMIN_USER_DIR=… build.py --out …` y `validar.py` OK. `validar.py` no corre en el job de Pedro más allá del paso común de `motor.yml`.
- **F5 simulación sin GitHub.** En `scratchpad/sim/repo/` se copió `template/`, se hizo `config.yaml` de corredor con calidad (2 tipos), se puso el motor en `.motor/` (copia local en lugar de `git clone`), y `gen_plan.py`, `build.py` y `validar.py` terminaron bien. La sincronización de instrucciones del workflow se probó en un repo git local con remoto bare (copia, commit, push, segundo run sin cambios y sin tocar `.claude/settings.local.json`).
- **F5 no probable sin GitHub real:** `gh auth status` / `gh repo view`, `gh secret set PERSONAL_API_KEY` (la key la teclea la persona), `gh api … /pages` (POST y, si ya existe, PUT), `gh workflow run`, `gh run watch`, "Use this template", y que `uses: …/motor.yml@stable` funcione entre dueños distintos (requiere que `stable` exista y el repo del motor sea público).
- **F5 `/ajustar` con plan ya empezado.** Como `gen_plan.py` siempre genera desde la semana 1, la skill genera el plan nuevo a un temporal y mezcla: semanas `n < k` del viejo y `n >= k` del nuevo (k = semana actual), con advertencia de que los minutos pueden saltar. No se probó con un caso real.
- **F5 memoria de Pedro.** La nota `project_dashboard_live.md` (fuera del repo) aún dice que la revisión semanal edita `dashboard/config.json`; ahora es `config.yaml` (sección `corrida.semanas_repetidas`, `perfil.fc_max`).

## v4.1

- **F1 tema.** El script de `<head>` pone `data-theme` (guardado o `dark`) antes de pintar; sin JS queda el CSS por sistema. Para capturas se agregó `?tema=claro|oscuro` (solo lee y no guarda; va antes del `#`, p. ej. `index.html?tema=claro#hoy`). El botón muestra ☀ en oscuro (pasa a claro) y ☾ en claro. `localStorage` clave `tema`.
- **F1 `perfil.titulo`.** El default del código ahora es "Mi entreno"; `corrida.carreras` se valida (fechas AAAA-MM-DD), se deduplica y ordena.
- **F2 Personal API sin récords.** Se probaron `/personalrecord-service/personalrecord/prs/me`, `/prs`, `/personalrecord`, `/prs/me/all`, `/userstats-service/personalrecord(s)` y `/personalrecord-service/personalrecords`: todos 404. Las mejores marcas se calculan del historial (`fastestSplit_<m>`), que sí trae la lista de actividades. Tampoco existen `/splits`, `/typedsplits`, `/split_summaries`, `/laps` (404).
- **F2 ritmo por km.** `/activity-service/activity/{id}/details` (200) trae la serie `sumDistance`/`sumDuration`; `garmin_connect.py` la reduce a segundos por km completo (`ritmos_km`, solo para carreras, sin GPS) y la guarda en `activity_details.json`. El resto de la serie se descarta. Km parcial final (p. ej. los últimos 50 m) no se muestra.
- **F2 `historial_corridas.json`.** Solo corridas (`run_types`), con los campos del plan. Sin él (amigos antes de su primer pull largo) `build.py` usa las actividades ya bajadas. Las carreras viejas del historial (sin nombre) se detectan por `eventType` o por fecha en la config, y salen con distancia, tiempo y ritmo (sin FC ni zonas).
- **F2 `es_carrera`.** Solo corridas (`run_types`). Nombre: `carrera`, `race` (inicio de palabra), `5k/10k/21k/42k` (no `15k`), `maraton`, `marathon`, tras quitar acentos y mayúsculas. "Medio maratón" ya queda cubierto por `maraton`.
- **F2 `mejores_marcas`.** Incluye `nuevo` (récord de los últimos 30 días). Corridas en caminadora cuentan (Garmin también las usa). La milla usa su propio `fastestSplit_1609` y el ritmo se da por km. 10K, medio y maratón solo salen si existe su `fastestSplit` (Pedro aún no ha corrido 10 km).
- **F2 carreras.** Claves extra `hace_dias` y `reciente` (≤ 7 días) para que la vista Hoy no calcule nada; `comparacion` = diferencias esta − anterior (negativo = más rápido).
- **F2 `carrera: true/false`** también en `ultima_corrida`, `estado_sesiones[].corrida`, `semanas_hoy[].sesiones[].corrida`, `extras`, `dias[].corrida` y `progreso.corridas[]`.
- **F3 forma del resultado.** Lo nuevo de `composicion`: `historial`, `puntuacion`, `visceral` y `hoja` (barras ya con `pos`, `normal_pos`, `zona`; más `control_peso`, `investigacion`, `composicion_corporal` y `segmental_*` tal cual). `hoja` sale de la última medición que traiga `musculo_grasa`. Se agregó `composicion_corporal` (agua, proteínas, minerales con su rango) porque F5 lo pide en "Ver hoja completa". No se publican altura ni edad de la hoja.
- **F3 `pos` y zona.** Se calcula sobre el % de la hoja (peso, MME, grasa) con la escala por tramos; IMC y PGC sobre su valor. `zona` compara contra el rango normal de la hoja (MME 117 % con normal 90–110 sale "alto"; su % es estimado).
- **F4 frase de periodo.** La frase `progreso.resumen[periodo]` ("Trotas 98 % del tiempo…") ya no se pinta: el plan lista Progreso sin ella y la fila de números (`progreso.numeros`, calculada en Python con cambio contra el periodo anterior) la sustituye. El dato sigue en `data.json`.
- **F4 números.** Ritmo en Z2 si no hubo caminatas en las últimas 4 semanas (mismo `modo` de "Cómo vas mejorando"); si no, % trote. `progreso.numeros.caminatas[periodo]` decide si aparece la vista "% trote" de Corridas.
- **F4 Recuperación en Cuerpo** usa siempre las últimas 12 semanas (84 días); ya no depende del toggle de periodo, que es de Progreso.
- **F4 Detalles** ya no trae "FC máxima y zonas" (se movió a Cuerpo) y solo se llega por el enlace al final de Progreso y Cuerpo.
- **F4 tarjeta de carrera en Hoy** va después de "Tus corridas" (orden del plan); si existe, "Tus corridas" y ella se reparten las 2 columnas en ≥ 900 px. El enlace abre y lleva a la carrera más nueva en Progreso.
- **F4 "Ver como tabla".** Corridas tiene la tabla de todas las corridas debajo y, solo en Volumen, otra "Ver semanas como tabla" (el volumen es por semana y no sale de la tabla de corridas).
- **F4 grilla.** Con `grid-auto-flow: row dense` en ≥ 900 px el orden visual puede diferir un poco del del DOM para rellenar huecos.
- **F5 `hoja.rangos`.** Para "Ver hoja completa" Python entrega los parámetros de investigación y la composición (agua, proteínas, minerales, masa grasa, peso) ya con `min`, `max` y `zona`, para que el JS no compare rangos.
- **F5 barras.** Franja Bajo·Normal·Alto y zona Normal sombreada con la misma geometría que la barra (`normal_pos`); los números de la escala van en su posición real (ticks igual de separados). Valor al final de la barra; si `pos` > 0.8 va dentro de la barra en tinta de página. La zona sale también como texto con ícono (▼ ✓ ▲) y en el `aria-label`.
- **F5 historial.** Puntos igual de separados (como la hoja) en 3 mini gráficas alineadas; Peso en gris neutro, MME en azul (`--s1`) y PGC en naranja (`--s2`), los mismos colores de las gráficas anteriores. Fechas solo bajo la última. La "puntuación" con un solo punto muestra el punto y la nota.
- **F5 tablas alternativas** dentro de "Ver hoja completa": barras (valor, % estándar, normal, zona), control de peso, rangos, segmental y mediciones.
- **F6 capturas.** En `scratchpad/v41/`: Pedro (hoy, progreso, cuerpo, detalles) a 400 y 1100 px, oscuro y claro; además `hoy` con `?sem=-1`, `progreso` con la carrera abierta, `cuerpo` con "Ver hoja completa" abierta, y `esc3_*` (usuario nuevo sin datos) en Hoy, Progreso y Cuerpo (400 y 1100, oscuro). Para abrir esos estados sin clics se agregaron `#progreso?carrera` y `#cuerpo?hoja` (solo se leen al cargar; son para capturas). Sin errores de consola en Pedro ni en esc3.
- **F6 correcciones tras revisar.** La etiqueta "prime" chocaba con las fechas del eje en la mini gráfica de PGC (más espacio inferior); la zona Normal sombreada era casi invisible en oscuro (ahora 13 % de la tinta); las tablas de "Ver hoja completa" se cortaban a 400 px (texto más chico y con salto de línea).
- **F6 no verificado.** Contraste medido a ojo (no se corrió `validate_palette.js` de nuevo: no hay colores nuevos de serie; Peso usa `--ink-2`). Cuerpo en 1100 px con `grid-auto-flow: dense` coloca FC y zonas junto a Recuperación.


## v4.2

- **F1 banner.** Sin actividad intensa hoy, el banner dice "Próxima corrida: <sesión>" (antes no decía nada con la sesión de hoy). Con una actividad intensa registrada: "Hoy: CrossFit ✓ · próxima corrida: …". `today_card.categoria` y `tipo: "otra"` se conservan; ya no hay `semana_tipica` en la config plana.
- **F1 `actividades.semana`.** Ya no se valida (ni siquiera una categoría inexistente truena); se ignora. El fixture de pruebas la conserva a propósito para vigilar la tolerancia.
- **F2 id y tipo de la variada.** La sesión variada conserva `id: "z2b"` (así lo asignan las corridas y `proxima_id`) pero con `tipo: "variada"` y `variada_tipo: "<id del catálogo>"` (solo en planes con `variada: true`, así el plan de Pedro sigue byte a byte).
- **F2 sesiones muy cortas.** Calentar/enfriar son 5' con sesión ≥ 20'; con 14–19' son 3' y con menos, 2' (si no, el cuerpo quedaba vacío con bases chicas de novato). La pirámide pide ≥ 13' de cuerpo (4 pausas + 1-2-3-2-1); si toca y no cabe, se usa el siguiente tipo de la rotación que no repita al de la semana vecina (ocurre con z2b ≤ 25').
- **F2 forma de cada tipo en la sesión.** Con solo Z1/Z2 la "escalera" solo tiene dos escalones (Z1 → Z2); con z2_poca_z3 son tres (Z1 → Z2 → Z3 corto). La densidad usa picos de 1' (Z3) con descansos de 1', 1', 2', 2' en Z1 (con solo Z2: picos de Z2) y el sobrante de minutos va al inicio.
- **F2 Z3 de la variada.** `tope = min(6', 20 % de la sesión)`; sale de la fórmula `int(min * 0.2)`. Z4/Z5 nunca. La tolerancia de "minutos sobre el techo" de esa corrida sube lo que el plan pide en Z3 (`run_check`).
- **F2 calidad.** `progresivo` = 10' Z2 · 6' Z2 · (8/10/12)' Z3 · 5' suave; `fartlek` = 5 o 6 tramos Z3 irregulares con pausas de 2' (objetivo = minutos en Z3). Con `variada: true` y calidad sin `calidad_tipos`, rotan los 5 (se llena en `ajustes.cargar_config`).
- **F2 `tipos` en data.json.** `{catalogo, grupos, en_plan}`; `en_plan` sale de las formas derivadas de todas las sesiones del plan (también las de semanas pasadas).
- **F3 "Intensidad de la semana" (barra 80/20 completa de Detalles).** Quedó en Plan, debajo de las reglas (es la regla 80/20 con la semana actual); en Progreso › Corridas irá la gráfica por semana (F6) y en Hoy la barra compacta.
- **F3 Carga semanal** pasó a Progreso › Corridas (al final) y "FC máxima y zonas" a Plan. Alias vivos: `#cuerpo`, `#detalles`, `#cuerpo?hoja`, `#progreso?carrera`.
- **F4 colores de la silueta (`--g1..--g5`).** Claro: `#7d7b75 #2a78d6 #139c82 #d9780f #c42f34`. Oscuro: `#96948e #4590e8 #2bb89b #ee9a2c #ee5a54`. Validador (`validate_palette.js`, pares adyacentes, superficies `#fcfcfb` y `#1a1a19`): claro = contraste pasa (todos ≥ 3:1), CVD pasa (peor par verde↔naranja ΔE 11.3 protan), piso de visión normal pasa (peor rojo↔naranja 16.3); oscuro = contraste pasa, CVD pasa (peor rojo↔naranja ΔE 10.5), piso normal pasa (15.5). Marcas que el validador señala y se aceptaron: (1) "chroma floor" del gris Z1 (es gris por diseño de Garmin; se distingue por su altura y la leyenda con texto); (2) en oscuro la banda de luminosidad (verde L 0.70 y naranja L 0.75, banda 0.48–0.67): subirlos fue necesario para separar naranja de rojo ≥ 15. Un verde "puro" quedaba a ΔE 4 del naranja con protanopía, por eso el verde es azulado (teal).
- **F4 chips de zona vs silueta.** Dentro de una sesión la silueta usa los colores Garmin (Z1 gris, Z2 azul…) y la lista de pasos de abajo conserva los colores de zona del resto del sitio (Z1 azul, Z2 verde…). Se respetó "no cambies los colores del resto"; puede confundir al estar juntos: decisión para Opus (recolorear `pasoLi` con `--g*` es una línea de CSS/JS).
- **F4 silueta con ancho virtual.** SVG con `viewBox` 300 y `preserveAspectRatio="none"` (trazo `non-scaling-stroke`), para que funcione dentro de un `<details>` cerrado sin conocer el ancho. Un tramo de 1' en una sesión de 60' mide ~5 px a 400 px de ancho (se ve como una muesca; el tooltip lo nombra).
- **F4 captura.** `#plan?abrir` / `#hoy?abrir` despliega todas las sesiones y "Ver todos los tipos" (solo para capturas, como `?carrera`).
