---
name: ajustar
description: Cambia nivel, tipo de plan (solo Z2, poca Z3, calidad), tipos de calidad, caminatas, actividades, días de pierna o fecha de inicio, y vuelve a publicar.
---

# /ajustar: cambiar la configuración

Habla en español, claro y corto. No pidas la key ni leas `.env`.

1. Pregunta qué quiere cambiar (nivel, intensidad, tipos de calidad, caminatas, actividades, días, pierna, inicio,
   minutos base) y por qué, si no es obvio.
2. Edita **solo** `config.yaml`. Valores válidos: ver `config.example.yaml`.
3. Si cambió algo **del plan** (nivel, intensidad, calidad_tipos, caminatas, inicio, semanas, base_min), hay que
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
