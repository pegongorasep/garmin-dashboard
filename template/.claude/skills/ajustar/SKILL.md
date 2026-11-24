---
name: ajustar
description: Cambia nivel, tipo de plan (solo Z2, poca Z3, calidad), tipos de calidad, corrida variada (`variada: true|false`), caminatas, actividades, días de pierna, título, carreras pasadas o fecha de inicio, y vuelve a publicar.
---

# /ajustar: cambiar la configuración

Habla en español, claro y corto. No pidas la key ni leas `.env`.

1. Pregunta qué quiere cambiar (nivel, intensidad, tipos de calidad, caminatas, actividades (cómo las registra en Garmin), días de pierna, inicio,
   minutos base, título de la página) y por qué, si no es obvio.
2. Edita **solo** `config.yaml`. Valores válidos: ver `config.example.yaml`.
   - "La del 21 nov fue carrera" (o "marca esa corrida como carrera"): agrega la fecha `2026-11-21` a
     `corrida.carreras` (lista de fechas AAAA-MM-DD). Es solo para carreras pasadas que Garmin no marcó; las nuevas se
     detectan solas si en Garmin las marcas como Carrera o su nombre dice carrera, 5k, 10k, medio maratón, etc.
     No se regenera el plan.
   - **Bloque nuevo (el plan terminó):** la última semana trae una prueba (`prueba` en Hoy › "Plan terminado":
     `hoy.tarjeta.prueba` en `data.json` con `tipo`, `fecha`, `valor`, `base` y `mejor`). Antes de generar el plan nuevo,
     agrega su resultado a `corrida.pruebas` como `{fecha, tipo, valor}` (usa tal cual `valor`; si la prueba es `null`,
     no se hizo: pregunta si quiere repetirla). Úsalo para proponer el siguiente plan: si `mejor` es verdadero y la
     mejora es clara, sube nivel o `base_min`; si no mejoró, repite el nivel y revisa sueño y carga. Nuevo `inicio` (lunes).
     Si la prueba fue `trote_continuo` y `seguido` es verdadero (trotó los 30' sin caminar), propón quitar las
     caminatas (`caminatas: false`): la siguiente prueba será a FC fija y sus `km` sirven de referencia.
3. Si cambió algo **del plan** (nivel, intensidad, calidad_tipos, caminatas, variada, inicio, semanas, base_min), hay que
   regenerarlo; si solo cambió actividades, días o título, **no** se regenera.
   - Asegura el motor: si no existe `.motor/`, clónalo (`git clone --depth 1 --branch stable
     https://github.com/pegongorasep/garmin-dashboard .motor`); si existe, `git -C .motor pull`.
     También `python3 -m venv .venv && .venv/bin/pip install pyyaml` si falta.
   - **Si el plan ya empezó** (`inicio` ya pasó) hay que conservar las semanas pasadas. No cambies `inicio`.
     Genera el plan nuevo a un archivo temporal: `GARMIN_USER_DIR=. .venv/bin/python .motor/plan/gen_plan.py --out /tmp/plan_nuevo.json`.
     Calcula la semana actual `k` = (días desde `inicio`) // 7 + 1 (cuenta `semanas_repetidas`: cada una empuja
     el resto una semana; ante la duda pregunta en qué semana va). Arma `plan/plan.json` con las semanas `n < k`
     del plan viejo y las `n >= k` del nuevo (mismo formato: `{"start": ..., "weeks": [...]}`).
     **Advierte:** las semanas pasadas no cambian, pero desde la semana `k` los minutos siguen la progresión del plan
     nuevo y pueden saltar; muéstrale la semana `k-1` y la `k` lado a lado antes de aprobar.
   - Si el plan **no** ha empezado: `GARMIN_USER_DIR=. .venv/bin/python .motor/plan/gen_plan.py` (sobreescribe
     `plan/plan.json`). En ambos casos muestra un resumen de las próximas 4 semanas.
4. Pide confirmación del resumen. Luego `git add -A && git commit -m "Ajuste: <qué>" && git pull --rebase && git push`,
   `gh workflow run deploy.yml` y `gh run watch`. Da el link de su página.
