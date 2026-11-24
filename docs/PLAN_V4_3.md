# Plan v4.3: medir la mejora, esfuerzo sin RPE, resumen semanal, prueba final

Requisitos aprobados por Pedro (2026-11-24): [`REQUISITOS.md`](REQUISITOS.md) §11. Base: v4.2.7 publicado (`stable`).

Quién: 🤖 Sonnet ejecuta F1–F7 sin detenerse; 🔍 Opus revisa y publica. **No hagas push, tags ni workflows.**

## Reglas

Las de v4 / v4.1 / v4.2, todas siguen:
- **no leas `.env`**. Correr `garmin_connect.py` sí se vale (lo lee por dentro); hazlo en F1 para tener series reales;
- pytest verde (`.venv/bin/python -m pytest -q`); las pruebas no dependen de `GITHUB_REPOSITORY` ni de la red;
- lógica en Python, el JS solo pinta; textos en español; sin librerías de JS;
- lista blanca: toda clave nueva de `data.json` va en `dashboard/validar.py`. **Las series de FC nunca salen en
  `data.json`** (solo los resultados calculados);
- compatibilidad: toda clave nueva de config lleva default (`dashboard/defaults.yaml` / `ajustes.cargar_config`);
  claves que se retiran (`rpe_heavy`) se toleran y se ignoran; el sitio tolera claves ausentes en `data.json`;
- un commit local por fase (`v4.3 F<n>: …`) con las líneas de coautoría que te pasen;
- carga el skill `dataviz` antes de tocar gráficas, colores o CSS;
- dudas a `docs/DUDAS.md` (sección "v4.3") sin detenerte; elige lo más simple y anótalo;
- **la barra 80/20 de Hoy no se toca** (§11.7).

---

## F1 — Serie de FC por corrida + utilidades 🤖

**`garmin_connect.py`**
- Para cada corrida (RUN_TYPES), además de lo que ya pide, baja la serie de `/activity-service/activity/{id}/details`
  (el mismo endpoint de `ritmos_km`) y guarda en la entrada de `activity_details.json` una clave `serie`:
  lista de `[seg, metros, fc]` muestreada **cada 5 s** (redondeada a enteros; sin lat/lon ni nada más). Busca los
  índices por `metricDescriptors` (`sumDuration`, `sumDistance`, `directHeartRate`); si falta alguno, `serie = []`.
- Las carreras reusan esa misma llamada para `ritmos_km` (no pidas `/details` dos veces).
- Caché (`detalle_vigente`): una corrida está completa si tiene `splits` y `serie` (y `ritmos_km` si es carrera).
  **El RPE ya no obliga a volver a pedir**, salvo actividades de los últimos 7 días sin RPE (Pedro puede ponerlo
  después). Las no-corridas con RPE `null` y más de 7 días tampoco se vuelven a pedir.
- Corre `garmin_connect.py` una vez al final de la fase y revisa que las corridas recientes traigan `serie`.

**`dashboard/metrics.py`** (funciones puras, con pruebas sobre series sintéticas):
- `minutos_zona_serie(serie, zonas)` → minutos en Z0..Z5 con **las zonas del dashboard** (piso/techo como `zones()`).
- `zona_minutos(activity, details, zonas)` → la serie si existe; si no, `hrTimeInZone_*` del reloj con
  Z0 = duración − suma. Esta es la fuente para F2–F4.
- `fc_referencia(zonas)` → `round((piso Z2 + techo Z2) / 2)`.

## F2 — Esfuerzo y carga sin RPE; semáforo con 3 señales 🤖

**Esfuerzo** (`metrics.esfuerzo(minutos_z0_z5)`): pesos `ESFUERZO = {Z0: 1, Z1: 2, Z2: 3, Z3: 5.5, Z4: 7.5, Z5: 9.5}`;
promedio ponderado en **la mitad más dura de la sesión** (ordena los minutos de Z5 hacia Z0 y toma la mitad del
total). 1 decimal. Sin minutos → `None`. **Carga** = esfuerzo × minutos de la actividad.
- Prueba con los casos de §11 (Z2 continuo 28' → 3.0; HIIT 15' Z4 + 5' Z5 + 20' suave → 8.0).

**Carga**: `session_load` y `week_load` usan esta carga para corridas y todas las categorías; se va `sin_rpe` (el
sitio quita el `*`, la nota "sesiones sin RPE" y la columna "Sin RPE"; la gráfica se llama "Carga semanal
(esfuerzo × min)").

**Registro**: cada actividad publicada (corridas en Progreso, "otras del día" del calendario, carreras) lleva
`esfuerzo` y `rpe` (el manual, o `null`). En el sitio se muestran los dos: "Esfuerzo 8.7 · RPE 7" (RPE solo si
existe). El número del calendario para actividades no-corrida pasa de Training Effect a **esfuerzo**; la nota dice
"número = esfuerzo calculado con tu FC (1–10)".

**Semáforo**: `signals()` devuelve solo `hrv`, `rhr`, `sueno`. Se va `signal_rpe` y su texto en "Cómo funciona".
- Nuevo `hoy.ayer`: `{categoria, esfuerzo, rpe}` de la actividad no-corrida de ayer con más esfuerzo (o `null`).
  Varias del mismo día: el esfuerzo más alto. En el sitio, debajo de las señales: "Ayer: CrossFit, esfuerzo 8.7".
- `motivo()`: si hay señal fuera y `ayer.esfuerzo ≥ esfuerzo_duro` (default **8**, en `defaults.yaml`), agrega
  " después de un día duro" ("HRV baja después de un día duro").
- `rpe_heavy` en configs viejas: se ignora sin error. Sácalo de `defaults.yaml`, `template/config.example.yaml` y
  skills.
- Antes de cerrar: tabla en `DUDAS.md` de esfuerzo vs RPE manual para las actividades de Pedro que tienen RPE.

## F3 — Ritmo a FC de referencia y deriva cardiaca 🤖

**Ritmo a FC ref** (`metrics.ritmo_fc_ref(fila, zonas)`): `ritmo_trote_s × fc_trote / fc_ref` (de los tramos RWD que
ya se calculan). Solo si es al aire libre, no carrera, y `fc_trote` está dentro de Z2 (piso ≤ fc ≤ techo); si no,
`None`. Para corridas sin tramos RWD (todo trote), usa ritmo y FC promedio de la actividad con la misma regla.
- Reemplaza "ritmo trotando" en `progress_summary` y el cálculo `ritmo_z2` de `mejora_frase` (los dos modos usan
  ahora esta métrica). Frase: "a 144 lpm: 7:48 → 7:35 /km" (ritmo promedio de cada periodo).
- `progreso.corridas[]` lleva `ritmo_ref_s`; la pestaña **Ritmo** de la tarjeta Corridas grafica ese valor (punto por
  corrida + promedio móvil de 4) con el título "Ritmo a {fc_ref} lpm". Vista de tabla igual.
- **Arregla de paso** la inconsistencia de §5 de la revisión: la frase de cada periodo y los recuadros de números
  usan el mismo conjunto de corridas; si no hay corridas comparables para la frase, la frase dice cuál falta
  ("Sin corridas en Z2 en las 8 semanas anteriores para comparar el ritmo") en vez de "Aún no hay corridas".

**Deriva** (`metrics.deriva(serie, fila)`): solo si duración ≥ 40 min y `pct_trote ≥ 90` (o sin tramos de caminata).
- Quita los primeros 10 min y las muestras de caminata (velocidad < 70 % de la mediana).
- **Parejo**: ritmo de cada km completo (después de los 10 min) dentro de ±15 % del ritmo mediano; si no, `None`
  con motivo `"no pareja"`.
- Velocidad ÷ FC (promedios por tiempo) en la primera mitad vs la segunda: `deriva_pct = (EF1 − EF2) / EF1 × 100`,
  1 decimal. `ok = deriva_pct < 5`.
- Se publica en la corrida (`deriva_pct`, `deriva_ok`), sale en "¿lo hice bien?" ("Deriva 4.1 % ✓") y como
  pestaña/gráfica "Deriva" en Progreso › Corridas (solo corridas con valor; línea en 5 %).
- "Cómo funciona": qué es el ritmo a FC ref, que el calor lo afecta (ver la tendencia), y qué es la deriva.

## F4 — Plan vs real por zona 🤖

`metrics.plan_vs_real(pasos, minutos_z)`:
- Minutos planeados por zona de los pasos (con `repeat`; zona única con `tipos.zona_unica`), sin Z0/Z1.
- Para cada zona planeada Z ≥ Z2: **acumulado** planeado en Z o más vs hecho en Z o más (así lo de una zona más
  alta cuenta para la de abajo). `pct = hecho / plan × 100`, `ok = hecho ≥ done_ratio × plan` (0.7, el que ya existe).
- Devuelve `[{zona, plan_min, hecho_min, pct, ok}]` de la zona más alta a la más baja.
- Va en `run_check` como `plan_vs_real` para toda corrida asignada a una sesión (usa `zona_minutos` de F1). Sustituye
  a `calidad_check` (quítalo y ajusta sus pruebas). La regla del techo (`min_sobre_techo`, `techo_ok`) no cambia.
- Sitio, en "¿lo hice bien?" y en las corridas hechas de "Tus corridas": una fila por zona "Z3 o más · 2 de 4 min ·
  50 %" con ✓/⚠ (texto, no solo color). Si solo hay una zona planeada: "Z2 · 19 de 20 min ✓".

## F5 — Resumen de la semana pasada en Hoy 🤖

`build.resumen_semana_pasada(hoy, …)` → `hoy.semana_pasada` (o `null` si la semana pasada no tiene ni corridas ni plan):
- `sesiones` "hechas de total" (del plan, si lo había), `minutos` y `plan_min`, `km`, `pct_trote`, `dias_verdes` de 7
  (semáforo de cada día con `light_on`; `sin_datos` no cuenta como verde y se reporta aparte), distribución 80/20
  (la de `intensidad_semana`), `carga` y `carga_anterior`, ritmo a FC ref promedio vs la semana anterior, y el
  `plan_vs_real` de cada sesión hecha.
- `sugerencia` por reglas, en este orden: `< 2 sesiones hechas` (con plan) o `≥ 2 días rojos` → "Considera repetir
  la semana (con /ajustar)"; `carga > 1.3 × carga_anterior` → "Semana pesada: cuida la recuperación"; todo hecho y
  sin días rojos → "Sigue el plan"; si no, sin sugerencia. Umbrales en `defaults.yaml`.
- Sitio: arriba en Hoy, **debajo de "Próxima corrida"**, toda la semana. Una línea: "Semana pasada: 3 de 3 ·
  85 / 85 min · 6 de 7 días verdes · ✓ Sigue el plan"; al tocarla (`details`) el resto.
- `/revision` (skill del template): menciona que el resumen ya está en Hoy y se enfoca en platicar y ajustes grandes.

## F6 — Prueba al terminar el plan 🤖

**`gen_plan.py`**: en la **última semana del plan** la Larga se cambia por una sesión `tipo: "prueba"`, id `prueba`:
- `intensidad` `solo_z2` / `z2_poca_z3` sin caminatas → `prueba: "fc_fija"`: 30' en Z2, nota "FC fija a la mitad de
  Z2 en ruta plana; alerta en el reloj". Se mide km en los 30'.
- con caminatas → `prueba: "trote_continuo"`: 30' de trote en Z2 caminando solo si pasas el techo; se mide el
  **% de trote** (con la serie no se sabe bien cuándo caminaste; anota en `DUDAS.md` que esto simplifica
  "minutos de trote continuo" de §11.6 para que Opus lo confirme con Pedro).
- `calidad` → `prueba: "5k"`: 5 km a tope (minutos = estimado 35'); se mide el tiempo de 5 km.
- `easy` = la misma sesión (no hay versión suave de una prueba). `verificar()` la acepta.
- **El plan de Pedro sí cambia**, solo la Larga de la semana 12: regenera `plan/plan.json` y ajusta la prueba de
  byte a byte para que compare contra el nuevo archivo (y que todo lo demás siga igual: compáralo con git).

**`build.py` / `metrics.py`**:
- Asignación: la prueba se asigna como la Larga pero en cualquier día de la semana.
- `build.prueba_resultado` → resultado (`km` en los primeros 30' de la serie, `pct_trote`, o tiempo de 5 km con
  `ritmos_km`/la serie), y su comparación: contra la **última prueba** de `corrida.pruebas` en config
  (`[{fecha, tipo, valor}]`, default `[]`) o, si no hay, contra la base: ritmo a FC ref promedio (o % trote) de las
  semanas 1–2 del plan; en `5k`, contra la mejor marca de 5 km antes del inicio del plan, o sin comparación.
- Después de la última semana, la tarjeta de Hoy es `tipo: "plan_terminado"`: "Plan terminado" + resultado de la
  prueba vs el inicio (o "Falta la prueba" si no la hizo) + "Corre /ajustar para el siguiente bloque".
- **`/ajustar`** (template): al empezar un bloque nuevo, agrega el resultado de la prueba a `corrida.pruebas` y lo
  usa para proponer el siguiente plan. `config.example.yaml` documenta `pruebas`.

## F7 — Cierre 🤖

- "Cómo funciona" y textos de `ui` al día (esfuerzo, semáforo de 3 señales, ritmo a FC ref, deriva, plan vs real,
  prueba). `docs/REQUISITOS.md` §11 estado → "construido, falta publicar".
- `validar.py` con todas las claves nuevas; corre `build.py` + `validar.py` con los datos de Pedro y con los usuarios
  de prueba de `scratchpad/esc42` si existen (si no, con un config de novato y uno de corredor en una carpeta temporal).
- Capturas en Chrome headless (420 px y 1280 px, claro y oscuro) de Hoy y Progreso › Corridas; revisa que nada se
  encime. Anota en `DUDAS.md` lo que no te convenza.
- `docs/PLAN_V4_3.md`: marca cada fase hecha.
