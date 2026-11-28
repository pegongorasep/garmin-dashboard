# Plan: formulario «Quiero un plan» (nivel primero, calidad a elegir, ajuste de volumen)

Un solo commit. Archivos: `web/plan_nuevo.py`, `web/plantillas/plan_nuevo.html`, `plan/motor_v6.py`, `i18n/*.yaml`, pruebas.

## Formulario
- Con corridas de Garmin: igual que hoy (evidencia + nivel calculado preseleccionado, editable).
- Sin corridas: el paso 1 es elegir el nivel, con descripción (Empezando «No corro o apenas empiezo», Base «Corro algo, pero no muy seguido»,
  Corredor «Corro varias veces por semana»). Se quita «automático».
  - Empezando: sin preguntas de frecuencia ni corrida larga; el inicio es el piso del nivel.
  - Base y Corredor: en el paso 2 se pregunta frecuencia y corrida más larga (fijan inicio y evidencia); el nivel lo decide la persona y,
    si las respuestas indican uno menor, aviso `pn.nivel_alto` en la vista previa.
- Días de correr: 3 por defecto, 2–5.
- Entrenamiento intenso: un selector 0–5 (prellenado con los días intensos de Garmin). El motor solo usa la cantidad.
- Se quita la pregunta de dolor (los planes viejos con `meta.dolor` no se tocan).

## Calidad (Base y Corredor)
- «¿Qué quieres mejorar?» igual para ambos: base / velocidad / carrera (`mas_tiempo` viejo = `base`).
- «¿Desde qué semana meter calidad?»: «Todavía no» o semana 2–8; Base 4, Corredor 2.
- Motor: entrada `calidad_desde` (int >= 2, `None` = sin calidad; si falta, rige `calidad_desbloqueada` como antes). La semana 1 nunca;
  solo semanas de carga (si cae en descarga, la siguiente de carga); la escalera arranca en la etapa inicial del nivel en esa semana
  y sube un peldaño por bloque contando desde ahí. Con calidad elegida, Base se comporta como desbloqueada (tope de días y de larga).
- Aviso en la vista previa si eligió calidad y su corrida más larga es < 20 min.

## Vista previa: ajuste de volumen
- «Volumen de inicio: N min/semana (+X %)» con «− 5 %» y «+ 5 %» (campo `ajuste_pct`, múltiplo de 5). Abajo hasta el piso del nivel, arriba +30 %.
- Avisos en una ranura de altura reservada: +15 a +20 % aviso; +25 a +30 % aviso fuerte; «Llegaste al máximo de tu nivel» cuando el motor
  limitó alguna semana por el tope del nivel (`meta.tope_alcanzado`, solo con ajuste > 0).
- Se guardan `ajuste_pct` y `calidad_desde` en `plan.meta`. Confirmar regenera idéntico (las respuestas viajan en ocultos).

## Fuera de alcance
- Simulador (`plan/simulador.py`): no es criterio; revisión en Fase 2.

## Ronda 2
- «Tu carrera» (distancia y fecha) solo se ve con «Una carrera» elegida (CSS `:has()` en `paginas.css`, sin JS; aquí la altura sí cambia, excepción acordada).
  El servidor sigue ignorando km y fecha con otro objetivo; carrera sin fecha da error en el campo.
- Se quitan la FC máxima (`fc_max`) y el tiempo de carrera (`tiempo`) del formulario. La edad es obligatoria sin ajustes; con ajustes sigue opcional y se
  conserva su `fc_max`. Los planes y configs viejos con `fc_max` o `meta.tiempo_carrera` no se tocan. Se quitan las claves i18n sin uso.
- Botones de volumen: cada uno salta al siguiente `ajuste_pct` (múltiplo de 5, dentro de piso del nivel…+30 %) cuyo plan tiene otros minutos en la semana 1
  (`saltos_volumen`, genera un plan por candidato). La etiqueta muestra el salto real («+ 10 %»). Sin valor, el botón se desactiva; el de subir muestra
  «Llegaste al máximo de tu nivel» o, si más días por semana sí subirían, «Con N días por semana no sube más; con más días sí».
  El texto «Volumen de inicio» usa los minutos reales de la semana 1.
- Ranura bajo el volumen más chica (5.5lh): recomendación siempre visible («Recomendado: no subir más de 10–20 %»), aviso amarillo desde +15 %, texto fuerte desde +25 %.
- Vista previa: volumen, gráfica «Minutos por semana» (igual), desplegable «Ver el plan completo» (la misma `tarjetaPlan` de la pestaña Plan, solo lectura),
  «Por qué», Confirmar / Cambiar respuestas. Los datos salen de `calculo.calcular_propuesta(plan=…, editable=False)` (build + lista blanca, sin guardar nada).
- `POST …/plan/nuevo/vista.json` (CSRF, mismos permisos) devuelve lo que pinta el paso 3; `web/estaticos/plan_nuevo.js` repinta fila, ranura, gráfica, «Por qué»
  y tarjeta conservando la semana vista y si el desplegable estaba abierto. Sin JS, los botones siguen siendo un POST normal.
- `site/vistas.js` solo arranca (`iniciar()`) si existe `#app`; `base.js` acepta `window.RUTA_I18N`. `sw.js` VERSION v83.
