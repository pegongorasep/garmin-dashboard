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
