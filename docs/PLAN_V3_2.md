# Plan v3.2: semanas navegables, calendario, mejora y composición corporal

Requisitos aprobados: [`REQUISITOS.md` §8](REQUISITOS.md). Base: v3.1 publicado
([`PLAN_HOY_V3_1.md`](PLAN_HOY_V3_1.md)). Datos InBody: `plan/inbody.json` (ya existe, no lo cambies).

Quién: 🤖 Sonnet ejecuta todo sin detenerse; 🔍 Opus revisa al final. **No hagas push.**

## Reglas

Las mismas de `PLAN_CONSTRUCCION_V3.md` §Reglas:
- **No leas, imprimas ni copies `.env`.**
- Pasos chicos y verifica cada uno.
- `pytest` verde siempre.
- La lógica va en Python; el JS solo pinta.
- Textos en español.
- Sin librerías.
- Privacidad por lista blanca.
- Un commit local por fase.

Antes de tocar gráficas o CSS, carga el skill `dataviz`. Si algo del plan choca con el código, decide lo
más simple que cumpla el requisito y anótalo en `docs/DUDAS.md` (sección "v3.2"); no te detengas.

## Diseño objetivo de Hoy (de arriba abajo)

```
[aviso "Repetir la semana" si aplica] [banner chico como en v3.1]
        ‹  Semana 1 de 12 · 9–15 nov · carga  ›          ← selector; mueve las 3 tarjetas de abajo
┌ ESTA SEMANA ───────────────────────────┐
│ 2 corridas · 68 min · 7.9 km · 72 % trote │   ← TODAS las corridas reales de esa semana
│ Plan: 1 de 3 sesiones · 68 / 80 min ███░ │   ← secundario (sin plan: no sale)
│ Semana pasada: 44 min · 5.3 km          │
└────────────────────────────────────────┘
┌ lun  mar  mié  jue  vie  sáb  dom ─────┐
│  ·   CF   ·   ●38  ·   ●30   ◌        │  ● = corrida (color de su estado, minutos, sesión debajo)
│     2.8       Z2#1     Larga   Larga?  │  CF chico y gris con su intensidad (TE 2.8)
│ CF = CrossFit · número = Training Effect aeróbico (0–5) │  ◌ tenue = futuro planeado
└────────────────────────────────────────┘
┌ TUS CORRIDAS ──────────────────────────┐   ← filas de v3.1 (hecha/hoy/pendiente)
│ ✓ Z2 #1 · jue 12 nov …                  │      + "✗ No hecha" en semanas pasadas
│ ▶ Larga · 30 min (versión suave)  HOY   │      + filas "Extra" para corridas sin sesión
│ ○ Z2 #2 · 20 min                        │      semanas futuras: solo pendientes con pasos
│ + Extra · mié 11 nov · 25' · 3.0 km     │
└────────────────────────────────────────┘
┌ CÓMO VAS MEJORANDO ────────────────────┐   ← no depende del selector
│ frase resumen                           │
│ [minutos/semana, últimas 8 vs plan] [% trote por corrida] │
│ 13 nov · Grasa 27.1 % ▼3.0 · Músculo 39.1 kg ▲1.1 · Visceral 10 │
│ Tu prime: 22.3 % · te faltan 4.8 puntos  Ver progreso →          │
└────────────────────────────────────────┘
▸ 🟡 Recuperación: suave hoy   (como en v3.1)
[aviso_zonas] · Detalles →
```

## F1 — Semanas navegables (`build.py` / `metrics.py`) 🤖

Nueva clave de primer nivel **`semanas_hoy`**: una entrada por semana calendario (lun–dom). Nueva clave
**`semana_hoy_idx`**: el índice de la semana que contiene hoy.

- **1.1 Qué semanas entran.**
  - Todas las del plan: desde el lunes de `plan_start`, durante `len(plan.weeks) + len(semanas_repetidas)`
    semanas calendario.
  - Cada una se mapea a su semana del plan con `m.week_index`.
  - Si hoy cae fuera de ese rango, agrega también la semana de hoy (sin plan), en orden cronológico.
  - El tamaño del JSON debe seguir pasando su test; si no, recorta solo los pasos de semanas pasadas.

- **1.2 Forma de cada entrada:**
  ```
  {inicio, fin, n (o null), kind, block, estado: "pasada"|"actual"|"futura",
   stats: {corridas, minutos, km, min_trote, min_camina, pct_trote},        ← TODAS las corridas reales
   plan: {total, hechas, incompletas, plan_min} | null,
   anterior: {minutos, km, min_trote},                                     ← semana calendario previa
   dias: [7 × {fecha, dia_semana, luz, corrida: {minutos, sesion_nombre, estado} | null,
               corridas_n, crossfit: {te, rpe, minutos} | null, planeado: "cf" | "larga" | null}],
   sesiones: [como plan.estado_sesiones de v3.1, con `corrida` y `estado` ∈ hecha|incompleta|pendiente|no_hecha],
   extras: [{fecha, ...lo mismo que `corrida` de una sesión (corrida_json + trote)}]}
  ```

- **1.3 Reglas de cada campo:**
  - `stats` cuenta todas las corridas de la semana hasta `min(fin, hoy)`. Usa `_semana_corridas` y la misma
    fórmula de `pct_trote` que `build_week`.
  - `plan` es `null` si la semana no tiene semana del plan.
  - **Sesiones.**
    - Salen de `week_assignment(día de esa semana, …, hasta=min(fin, hoy))`.
    - En semanas futuras, todas quedan `pendiente`.
    - En semanas pasadas, una pendiente pasa a `no_hecha`.
    - Reutiliza `corrida_de_sesion`.
  - **Extras.**
    - Son las corridas de la semana que no quedaron asignadas a ninguna sesión. Compara por
      `(fecha, minutos)`, como ya lo hace `corrida_de_sesion`.
    - En semanas sin plan, todas las corridas son extras.
    - Usa la misma función común de la corrida (no copies código).
  - **CrossFit del día.**
    - `te` = el máximo `aerobicTrainingEffect` de las actividades CrossFit del día, redondeado a 1 decimal.
    - `rpe` = el máximo RPE de `details`, si existe.
    - `minutos` = la suma de las sesiones de CrossFit del día.
    - `null` si no hubo CrossFit.
  - **`dias[].corrida`.**
    - Es la corrida más larga del día.
    - `sesion_nombre` = el nombre de la sesión asignada, o `"Extra"`.
    - `corridas_n` = cuántas corridas hubo ese día.
  - **`planeado`** solo se llena en días futuros (`> hoy`) sin actividad:
    - `"cf"` si el día está en `crossfit_days`.
    - `"larga"` en sáb y dom si la Larga sigue pendiente.
    - `null` en los demás casos.
  - `luz` solo para días `<= hoy` (como en `build_week`).

- **1.4 Compatibilidad con v3.1.**
  - Las claves `semana` y `plan.estado_sesiones` se quedan, porque los tests y el JS de v3.1 las usan.
  - No dupliques lógica: si conviene, que `build_week` use el mismo constructor.
  - Puedes borrar las claves de v3.1 que el JS ya no use al final de F3, **solo** si actualizas los tests.

- **1.5 Tests (✅).** Con `--plan-start 2026-11-09 --day 2026-11-14`:
  - `semanas_hoy[semana_hoy_idx]` tiene `n == 1`, `stats.corridas == 1`, z2a `hecha` y ningún extra.
  - El jueves 12 trae `corrida.sesion_nombre == "Z2 #1"`.
  - La semana 2 es `futura`: sesiones pendientes y `stats.corridas == 0`.
  - Hay 12 semanas.

- **1.6 Tests sintéticos (✅).**
  - Semana con 4 corridas → 3 sesiones más 1 extra.
  - Semana pasada con una sesión sin hacer → `no_hecha`.
  - Día con strength (TE 2.2) y hiit (TE 3.4) → `crossfit.te == 3.4`, minutos sumados.
  - Día futuro martes → `planeado == "cf"`.

- **1.7 Privacidad.** `PROHIBIDAS` sigue verde; agrega a la lista blanca solo los campos nuevos.
- Commit: "v3.2 F1: semanas navegables con extras y CrossFit".

## F2 — Mejora y composición corporal (Python) 🤖

- **2.1 `progreso.mejora`.**
  - `frase`: compara las últimas 4 semanas calendario completas contra las 4 anteriores, en corridas por
    semana, minutos por semana y % trote promedio. Ejemplo: "Últimas 4 semanas: 1.5 corridas y 52 min por
    semana (antes 1.0 y 34); trote 71 % (antes 66 %)."
  - Omite lo que no tenga datos. Si no hay corridas en las 8 semanas: "Aún no hay corridas suficientes
    para comparar."
  - `semanas`: las 8 últimas semanas calendario, `[{inicio, minutos, plan_min | null}]`, incluida la actual.
  - `corridas`: las últimas 12 corridas, `[{fecha, pct_trote}]`; sin tramos, `pct_trote` = `null`.
  - Función pura en `metrics.py` con tests (✅): frase con datos, sin datos y con la mitad vacía.

- **2.2 `composicion`** (nueva clave de primer nivel; `null` si no existe `plan/inbody.json`):
  ```
  {mediciones: [{fecha, peso_kg, mme_kg, pgc, masa_grasa_kg, puntuacion?, grasa_visceral?}],  ← orden por fecha
   prime: {fecha, pgc, mme_kg, peso_kg, masa_grasa_kg},
   ultima: {…medición…, delta_pgc, delta_mme, delta_peso},   ← vs la medición anterior (null si es la única)
   meta: {faltan_pgc, mme_ok, faltan_mme},                   ← faltan_pgc = ultima.pgc − prime.pgc (≥ 0)
   visceral_rango: [1, 9]}
  ```
  - `masa_grasa_kg` = el valor del archivo, o `peso × pgc / 100` redondeado a 1 decimal.
  - `prime` = la medición con la fecha de `inbody.json.prime`; si falta, la de menor `pgc`.
  - Lista blanca: no publiques `nota` ni `hora`.
  - Los cálculos van en `metrics.composicion(inbody)`, con tests (✅): deltas, masa grasa calculada, meta
    con `faltan_pgc == 4.8` y `mme_ok == true` con los datos reales.

- Commit: "v3.2 F2: mejora y composición corporal".

## F3 — Vista Hoy (`site/app.js`, `site/styles.css`) 🤖

- **3.1 Selector.**
  - Una fila centrada: `‹ Semana n de 12 · 9–15 nov · carga ›`. Sin plan: "Semana del 9–15 nov".
  - Botones `<button>` con `aria-label` ("Semana anterior" / "Semana siguiente"), deshabilitados en los
    extremos.
  - El estado vive en una variable del módulo, que arranca en `semana_hoy_idx`.
  - Cambiar de semana vuelve a pintar solo Esta semana, el calendario y Tus corridas.
  - Si la semana elegida no es la actual, muestra un enlace chico "Volver a esta semana".

- **3.2 Esta semana** (la elegida). El título cambia según la semana: "Esta semana", "Semana pasada" o
  "Esa semana".
  - **Línea grande:** "N corridas · X min · Y km · Z % trote". Omite los nulls. Con 0 corridas:
    "Sin corridas" (en una semana futura: "Aún no empieza").
  - **Línea secundaria** (solo si hay plan): "Plan: h de 3 sesiones · X / plan_min min", con la barra de
    v3.1 más delgada.
  - **Comparación** contra `anterior`: la misma regla de v3.1, sin flechas engañosas a media semana.

- **3.3 Calendario.**
  - Una cuadrícula de 7 columnas que cabe en 400 px sin desbordar.
  - **Día con corrida:** círculo de color según el estado de la sesión (hecha = acento, incompleta =
    advertencia, Extra = neutro con borde), minutos adentro y nombre corto debajo ("Z2 #1", "Larga",
    "Extra"). Si hubo 2 corridas, agrega "+1".
  - **Día con CrossFit:** texto chico y gris "CF" con el TE debajo ("2.8"), o "RPE 7" si hay RPE.
  - **Día futuro con `planeado`:** "CF" o "Larga?" en tenue.
  - **Hoy:** borde marcado.
  - Leyenda de una línea debajo: "CF = CrossFit · número = Training Effect aeróbico de Garmin (0–5)".
  - `title`/`aria-label` por día con el texto completo.
  - La identidad no va solo en el color: el nombre corto siempre se ve.

- **3.4 Tus corridas** (la semana elegida). Reusa las filas de v3.1 (`filaSesion`, etc.).
  - **Semana actual:** igual que hoy, con la fila de HOY resaltada.
  - **Semana pasada:** las hechas e incompletas con su detalle; las `no_hecha` como "✗ No hecha · Nombre ·
    N min", gris y sin pasos.
  - **Semana futura:** solo las pendientes, con sus pasos en `<details>`. No menciones "hoy".
  - **Extras:** al final, como "+ Extra · fecha · 25' · 3.0 km · 70 % trote", con `<details>` "Ver
    detalle" (barra trote/caminata).
  - Sin plan: solo extras; si no hay: "Sin corridas esta semana".

- **3.5 Cómo vas mejorando.**
  - Frase, luego dos mini gráficas lado a lado (apiladas a 400 px), de unos 90 px de alto:
    - Barras de minutos por semana con marca del plan: reusa `barChart` con `meta`.
    - Línea de % trote por corrida con puntos: reusa `lineChart`.
  - Las dos llevan título corto, valor final etiquetado y tooltip/hover como las de Progreso.
  - Línea InBody: "13 nov · Grasa 27.1 % ▼3.0 · Músculo 39.1 kg ▲1.1 · Visceral 10 (sano 1–9)".
    - La visceral fuera de rango lleva el badge de advertencia con texto, no solo el color.
    - Bajar grasa y subir músculo son buenos (verde); lo contrario, en tinta neutra. No uses rojo.
  - Segunda línea: "Tu prime (25 may 2024): 22.3 % · te faltan 4.8 puntos de grasa" y "Músculo ya arriba
    de tu prime ✓" cuando `mme_ok`.
  - Enlace "Ver progreso →" que abre la pestaña Progreso.
  - Si `composicion` es null, se omite la parte InBody.

- **3.6 Recuperación**, avisos y Detalles: como en v3.1.
- **3.7 Limpieza.** Borra lo que ya nadie use; haz `grep` de cada función borrada. Estados vacíos: un
  `data.json` sin `semanas_hoy`, sin `composicion` o con `extras` vacío no debe tronar Hoy.
- Commit: "v3.2 F3: Hoy con selector, calendario y mejora".

## F4 — Progreso: Composición corporal (`site/vistas.js`) 🤖

Sección nueva **"Composición corporal"** al final de Progreso:
- **Meta.** Tarjeta de cabecera: "Superar tu prime: 22.3 % grasa · MME ≥ 38.4 kg"; hoy 27.1 % (faltan 4.8)
  y 39.1 kg ✓.
- **Recomposición.**
  - Masa grasa (kg) y masa muscular esquelética (kg) en **un solo eje**, como 2 series con leyenda y
    etiqueta directa.
  - Puntos en cada medición.
  - El prime marcado con una raya vertical tenue etiquetada "prime".
  - Eje x por fecha real: hay huecos de meses y deben verse.
- **% de grasa en el tiempo.** Línea con puntos y una raya horizontal en 22.3 % etiquetada "prime 22.3 %".
- **Tabla.** Fecha, peso, % grasa, masa grasa, MME, puntuación y visceral. La fila del prime lleva la marca
  "★ prime"; los guiones van donde falte el dato.
- **Gráficas.** Valida la paleta de 2 series con `scripts/validate_palette.js` del skill, en claro y en
  oscuro. Si `lineChart` no aguanta x por fecha o 2 series, extiéndelo sin romper sus usos.
- Commit: "v3.2 F4: composición corporal en Progreso".

## F5 — Capturas y autorevisión 🤖

Sigue "Cómo hacer capturas" de `PLAN_CONSTRUCCION_V3.md`. Guárdalas en
`/private/tmp/claude-501/-Users-pedro-antonio-Desktop-garmin/8c3aa7c4-849b-4665-ad17-2ae3fd068756/scratchpad/v32`.

Cada escenario va a 400 px en claro y en oscuro, más escritorio en claro:
1. Hoy: `--day 2026-11-14 --plan-start 2026-11-09` (semana 1 actual).
2. Hoy con el selector en la semana 2 (futura). Para la captura, abre la página con `#hoy?sem=+1` o un
   parámetro equivalente que solo lea el JS al arrancar; anótalo.
3. Hoy: `--day 2026-11-24 --plan-start 2026-11-09`, con el selector en la semana 1 (pasada: hechas,
   no_hecha).
4. Progreso completo (composición corporal).
5. `--day 2026-11-04` sin `--plan-start` (hoy fuera del plan, semana sin plan con corridas extra y CrossFit
   con TE).

Abre cada captura y corrige lo que se vea mal: desbordes a 400 px, "null" o "undefined", calendario
apretado, gráficas sin etiquetas, colores ilegibles en oscuro. Al final regenera `data.json` sin flags,
corre `pytest` y actualiza la tabla de seguimiento.

## Seguimiento

| Fase | Estado |
|---|---|
| F1 Semanas navegables | ⬜ |
| F2 Mejora y composición | ⬜ |
| F3 Vista Hoy | ⬜ |
| F4 Progreso composición | ⬜ |
| F5 Capturas | ⬜ |
| Revisión Opus + publicar | ⬜ |
