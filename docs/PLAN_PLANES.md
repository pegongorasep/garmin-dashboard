# Plan: planes fijos, repetir o retomar y carreras de paso (`REQUISITOS_PLANES.md`)

Escrito el 2026-11-27. Sonnet ejecuta, una fase = un commit local (`Planes P<n>: …`); Opus revisa cada fase. Se publica
al final, preguntando a Pedro. Ninguna fase toca `motor.yml`, `scripts/subir.py`, `garmin_connect.py` ni
`dashboard/paquete.py` (`stable` no se mueve). Toda clave nueva de config lleva valor por defecto.

## Diseño

- **Saltos**: `corrida.saltos = [{"lunes": "AAAA-MM-DD", "semana": X, "quita": [n…]}]` (por defecto `[]`). Desde ese
  lunes el plan sigue en la semana X; `quita` son semanas del plan que ya no se harán (solo con carrera objetivo).
  Repetir la semana N = `{lunes: próximo lunes, semana: N}`; retomar desde X = `{lunes: este lunes, semana: X}`.
  `metrics.secuencia_semanas` los aplica (junto con `semanas_repetidas` y `pausas`, que siguen valiendo).
- **Carrera de paso**: una meta con `de_paso: true` (por defecto false). `plan_vivo.plan_efectivo` la aplica por fecha,
  como los viajes: en la semana del plan que cae en esa fecha, la sesión larga (o la más larga) se vuelve la carrera.
- **Vista previa**: `GET /plan/propuesta.json?accion=repetir|retomar&semana=X` devuelve el data.json calculado con los
  ajustes propuestos (sin guardar ni cachear); el sitio pinta la vista de bloques del Plan con esos datos en modo
  propuesta, más el aviso y «Sí, aplicar» / «No».

## Fases

- **P1. Sin ajuste semanal.** Quitar `semanal.ajustar_plan` de `build` (el cambio sin commit en `dashboard/build.py` ya
  quita la llamada: inclúyelo) y borrar `ajustar_plan`, `ajuste_texto` en Hoy/Plan del sitio y sus textos y pruebas
  (incluidas las de la parte 2 que esperaban que bajara la carga). `motor_v6.ajustar_semana`: se borra; el simulador
  simula el plan fijo. Golden actualizado. Prueba: la semana en curso sale igual al plan guardado aunque la anterior se
  haya corrido poco.
- **P2. Saltos.** `corrida.saltos` con defaults y validación en `ajustes`; `secuencia_semanas` los aplica; todo lo que
  calcule el fin del plan o la semana en curso los respeta. `plan_vivo.repetir(crudo, plan, cfg, hoy)` y
  `plan_vivo.retomar(crudo, plan, cfg, hoy, X)`: con carrera objetivo calculan `quita` (últimas semanas de carga antes
  del taper) o `ErrorT` si no alcanza. Eventos (viajes, carreras) siguen por fecha. Pruebas de calendario: repetir,
  retomar, con viaje, con carrera objetivo (taper y carrera en su fecha), sin semanas de carga.
- **P3. Vista previa y botones.** En Plan, «Repetir o retomar» → elegir «esta semana» o una anterior (lista con sus
  fechas) → vista previa (`/plan/propuesta.json`; el sitio pinta la sección de bloques completa en modo propuesta con
  el aviso de carrera objetivo, las semanas que se quitan y el fin nuevo) → «Sí, aplicar» (POST con CSRF, cambio en el
  historial) o «No». También bajo `/a/<id>` para el coach. Reemplaza el `/plan/repetir` de hoy. MCP: `repetir_semana`
  con `semana` opcional (retomar). Sube `sw.js`.
- **P4. Deshacer solo esta semana.** Un cambio de repetir o retomar se deshace solo si se hizo en la semana en curso
  (zona horaria de la persona); después, `NoSeDeshace` con mensaje claro. Pruebas.
- **P5. Carrera de paso.** El diálogo «Agregar carrera» con las dos opciones bien separadas: «Carrera de paso (sigo con
  mi plan)» (nombre, fecha, km opcional; `de_paso: true`) y «Entrenar para esta carrera» (liga a `/plan/nuevo` con
  carrera, fecha y km puestos). `plan_efectivo` pone la carrera en lugar de la larga de su semana; una corrida ese día
  cuenta como esa sesión. Se quita `agregar_carrera_en_plan`/`con_carrera` y quitar una carrera ya no rehace el plan.
  MCP `agregar_carrera` = de paso. Pruebas: plan con y sin carrera objetivo, repetir con carrera de paso (se queda en su
  fecha).
- **P6. Dos semanas sin correr.** Hoy (Python decide, JS pinta en ranura reservada): con plan en curso y 14 días sin
  corridas, sugiere «Retomar desde la semana X» (última completa, o la 1) → vista previa, y «Crear plan nuevo». Se puede
  ocultar (`avisos_ocultos`). Pruebas.
- **P7. Documentos.** `CLAUDE.md` (motor: solo al crear; saltos; carreras de paso), `REQUISITOS_PLANES.md` marcado
  hecho, `docs/DUDAS.md`.

## Orden y revisión

P1 → P7 en orden. En cada fase: agente Sonnet nuevo, `.venv/bin/python -m pytest -q`, `dashboard/validar.py` y
`.venv/bin/python -m plan.simulador` en verde, commit local; Opus revisa el diff antes de la siguiente. Al final, Opus
pregunta a Pedro si publica.
