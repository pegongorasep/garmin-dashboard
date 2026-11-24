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
