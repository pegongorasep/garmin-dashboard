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
