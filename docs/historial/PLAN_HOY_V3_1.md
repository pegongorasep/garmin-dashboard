# Plan v3.1: pantalla Hoy centrada en la semana de corridas

Pedido de Pedro (2026-11-14): en la pantalla principal ver primero **sus estadísticas de corrida de la
semana** y luego **sus 3 corridas de la semana**. El semáforo es secundario: chico y abajo.
Base: v3 publicado ([`PLAN_CONSTRUCCION_V3.md`](PLAN_CONSTRUCCION_V3.md)). Solo cambia la vista **Hoy**
y lo que `build.py` le manda; Progreso y Detalles no se tocan.

Quién: 🤖 Sonnet ejecuta todo sin detenerse; 🔍 Opus revisa al final. **No hagas push.**

## Reglas

Las mismas de `PLAN_CONSTRUCCION_V3.md` §Reglas (no leer `.env`, pasos chicos con verificación, pytest
verde siempre, lógica en Python y el JS solo pinta, textos en español, sin librerías, privacidad por lista
blanca, commit local por fase). Antes de tocar CSS o la barra de progreso, carga el skill `dataviz`.

## Diseño objetivo (de arriba abajo)

```
[aviso "Repetir la semana" solo si aplica]
[banner chico: "Hoy CrossFit · próxima corrida: Z2 #2" | "El plan arranca el lunes 16 nov" | "Semana completa"]
┌ ESTA SEMANA · Semana 1 de 12 · carga ──┐
│ 1 de 3 corridas                        │
│ 38 / 80 min  ███████░░░░░░░  48 %      │
│ 4.4 km · 27' trotando · 71 % trote     │
│ vs semana pasada: ▼ 6 min · ▼ 0.9 km   │
└────────────────────────────────────────┘
┌ TUS 3 CORRIDAS ────────────────────────┐
│ ✓ Z2 #1 · jue 12 nov                   │
│   38' · 4.4 km · 71 % trote · 7:55 /km │
│   ! 2.7' sobre el techo (tolerancia 2')│
│   ▸ Ver detalle (barra trote/caminata, │
│     patrón, FC trotando)               │
│ ────────────────────────────────────── │
│ ▶ Larga · 30 min (versión suave)  HOY  │
│   Por: FC en reposo alta               │
│   30 min · Z1–Z2 · 126–151 lpm         │
│   ▸ Cómo crearla en Garmin Connect     │
│ ────────────────────────────────────── │
│ ○ Z2 #2 · 20 min                       │
│   ▸ Pasos, versión suave y Garmin      │
└────────────────────────────────────────┘
▸ 🟡 Recuperación: suave hoy   (al abrir: las 4 señales)
[aviso_zonas si viene]
Detalles: zonas, reglas, intensidad y carga →
```

Se **quitan** de Hoy: la tarjeta grande del semáforo, "Sesión de hoy", "Última corrida · ¿lo hice bien?",
la tira de 7 días y "Plan de la semana" (todo queda absorbido arriba). `semana.dias` y `ultima_corrida`
siguen en el JSON (no borres esos campos).

## F1 — Datos (`metrics.py` / `build.py`) 🤖

- **1.1** `metrics.motivo(sigs) -> str | None`: une con " · " las señales `fuera` (en orden hrv, rhr, sueno,
  rpe) con estos textos: hrv → "HRV baja", rhr → "FC en reposo alta", sueno → "Dormiste poco",
  rpe → "CrossFit pesado ayer". Si `hrv_baja` es true y hrv no está fuera, igual agrega "HRV baja".
  `None` si no hay ninguna. **✅** Tests: ninguna, una, dos, hrv_baja.
- **1.2** `today_card`: en los tipos `crossfit` y `hecha_hoy` agrega `proxima_id` = id de la sesión que
  elegiría `_elegir_pendiente` para **mañana** (`day + 1 día`), o `None`. En los demás tipos `proxima_id`
  = `None`. **✅** Test: martes con todo pendiente → `z2a`; viernes con z2a y z2b hechas → `larga`.
- **1.3** `build`: `hoy.tarjeta.motivo` = `motivo(sigs)` cuando la versión es `suave` o `descanso`; si no,
  `None`. **✅** Test con el fixture forzando una señal fuera.
- **1.4** `build_week` agrega: `plan_min` (suma de minutos de las sesiones de la semana del plan, o `None`),
  `min_camina`, `pct_trote` (= `min_trote / (min_trote + min_camina) × 100`, `None` si 0), y
  `anterior: {minutos, km, min_trote}` de la semana anterior (lun–dom completa). **✅** Test.
- **1.5** Cada elemento de `plan.estado_sesiones` gana `corrida`: `None` si pendiente; si no,
  `{minutos, km, pct_trote, ritmo_trote_s, fc_trote, caminatas, patron_trote_min, patron_camina_min,
  trote_min, camina_min, caminadora, min_sobre_techo, tolerancia_min, techo_ok}` de la corrida asignada
  (búscala por `(fecha, minutos)` como hace `last_run`; usa `run_walk` + `rw_json` + `run_check` con la sesión
  del plan). Factoriza lo común con `last_run` en una función, no lo copies. **✅** Test: con
  `--plan-start 2026-11-09 --day 2026-11-14` la z2a trae `km 4.36`, `pct_trote 71.4`, `techo_ok false`.
- **1.6** Privacidad y tamaño siguen verdes. Commit: "v3.1 F1: datos para la nueva pantalla Hoy".

## F2 — Vista Hoy (`site/app.js`, `site/styles.css`) 🤖

- **2.1** `renderHoy` con el orden del diseño. Banner (una línea, sin tarjeta grande):
  - `crossfit` → "Hoy CrossFit · próxima corrida: {nombre de proxima_id}" (sin `proxima_id`: "Hoy CrossFit").
  - `hecha_hoy` → "Corrida de hoy hecha · próxima: {nombre}" (o sin "próxima" si no hay).
  - `sin_plan` → "El plan arranca el {fechaCorta(plan.inicio)}".
  - `completa` → "Semana completa: hiciste las 3".
  - `sesion` → sin banner (la sesión de hoy se marca en la lista).
- **2.2** Tarjeta **Esta semana**: título "Esta semana · Semana n de 12 · carga|descarga" (sin plan activo:
  "Esta semana"). Número grande "h de 3 corridas" (+ " · 1 incompleta" si hay). Barra de progreso
  minutos / `plan_min` (una sola barra, color de acento, fondo de rejilla, tope visual en 100 % aunque pase,
  texto "38 / 80 min · 48 %"; sin `plan_min`: solo "38 min"). Línea "4.4 km · 27' trotando · 71 % trote"
  (omite lo que sea null). Línea "vs semana pasada: ▲/▼ X min · ▲/▼ Y km" (si la anterior es 0 en ambos:
  "Semana pasada sin corridas"). Si `hechas + incompletas == 0` y hay `ultima_corrida`:
  "Última corrida: {fecha} · 38' · 4.4 km".
- **2.3** Tarjeta **Tus 3 corridas** (sin plan activo: no se muestra). Una fila por sesión, en el orden del
  plan:
  - **Hecha / incompleta:** badge (✓ Hecha, ✓ Hecha · ajustada, ! Incompleta), "Nombre · fecha corta",
    línea "38' · 4.4 km · 71 % trote · 7:55 /km" (ritmo con "caminadora" si aplica), línea del techo
    (✓/! "2.7' sobre el techo (tolerancia 2')"). `<details>` "Ver detalle": barra trote/caminata
    (reusa `barraRW`) + `detalleTrote`.
  - **La de hoy** (`tarjeta.tipo == "sesion"` y `tarjeta.sesion_id == id`): fondo/borde resaltado y chip
    "HOY". Título "Nombre · N min" + "(versión suave)" si aplica. Línea "Por: {motivo}" si viene. Si la
    versión es `descanso`: "Hoy descanso o caminata ligera de 20–30' en Z1" + motivo, sin pasos. `aviso`
    de la tarjeta debajo (larga en fin de semana / sin datos). Pasos visibles (`pasoLi`) de la versión que
    toca; `<details>` "Cómo crearla en Garmin Connect".
  - **Pendiente:** "○ Nombre · N min" (+ " · sáb o dom" en la larga). `<details>` con pasos, versión suave y
    "Cómo crearla en Garmin Connect" (reusa `filaSesion` si encaja).
- **2.4** **Recuperación** como un solo `<details>` chico: summary con badge del color + "Recuperación: todo
  bien" (verde) / "suave hoy" (amarillo) / "descanso hoy" (rojo) / "sin datos de anoche" (sin_datos); al
  abrir, la lista de las 4 señales (reusa el markup actual de señales). `aviso_zonas` debajo si viene.
  "Repetir la semana" va **arriba de todo** como aviso cuando `repetir_semana`.
- **2.5** Borra de `app.js`/`styles.css` lo que ya nadie use (tarjeta grande del semáforo, `tarjetaHoy`,
  `tarjetaUltima`, `tarjetaPlanSemana`, `tira`, etc.). **✅** `grep` de cada función borrada sin usos.
- **2.6** Estados vacíos: `data.json` recortado sin `plan.semana_actual`, sin `ultima_corrida`, con
  `estado_sesiones` vacío: Hoy no truena. Commit: "v3.1 F2: Hoy con la semana de corridas primero".

## F3 — Capturas y autorevisión 🤖

Sigue "Cómo hacer capturas" de `PLAN_CONSTRUCCION_V3.md` (scratchpad `.../scratchpad/v31`). Escenarios,
cada uno a 400 px claro y oscuro + escritorio claro:
1. `--day 2026-11-14 --plan-start 2026-11-09` (z2a hecha, hoy sábado, Larga suave por FC reposo alta).
2. `--day 2026-11-17 --plan-start 2026-11-16` (martes de CrossFit, nada hecho, banner con próxima).
3. `--day 2026-11-12 --plan-start 2026-11-09` (corrida de hoy hecha).
4. `--day 2026-11-15` sin `--plan-start` (antes del plan: banner "arranca el lunes 16 nov").

Abre cada captura, corrige lo que se vea mal (desbordes a 400 px, textos "null"/"undefined", alineación).
Al final regenera `data.json` sin flags. Actualiza la tabla de seguimiento de abajo.

## Seguimiento

| Fase | Estado |
|---|---|
| F1 Datos | ✅ |
| F2 Vista Hoy | ✅ |
| F3 Capturas | ✅ |
| Revisión Opus + publicar | ✅ 2026-11-14 |
