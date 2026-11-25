# Plan v4.4: mandar las sesiones al reloj (solo Pedro)

Requisitos aprobados por Pedro (2026-11-25): [`REQUISITOS.md`](REQUISITOS.md) §12. Base: `stable` = 5eedbe8.

Quién: 🤖 Sonnet ejecuta F2–F4 sin detenerse; 🔍 Opus revisa, prueba con la cuenta de Pedro y publica.
**No hagas push, tags ni workflows. No corras nada que escriba en Garmin** (`borrar`, `semana --si`): las
pruebas reales las hace Opus con Pedro. Leer (`lista`, `--dry-run`) sí se vale.

## Reglas

- **No leas `.env`** ni `~/.garminconnect` (tokens). Correr `garmin_connect.py` y `reloj.py lista` sí se vale.
- `reloj.py` y su lógica son **solo de Pedro**: nada en `template/`, en `motor.yml`, en `requirements.txt` ni en
  `data.json`. La dependencia está fijada en `requirements-reloj.txt` (`garminconnect==0.3.20`, ya en `.venv`).
- Los IDs de Garmin (entrenamientos, dispositivo) solo viven en `data/reloj.json` (gitignored, nunca publicado).
- Reusa lo que ya existe: `build.load_data`, `build.load_plan`, `ajustes.cargar_config`, `build.week_assignment`
  (estado `hecha`/`pendiente` de cada sesión), `metrics.week_index`. No dupliques la lógica del plan.
- Lógica pura separada de la red, con pruebas en `tests/test_reloj.py` que no usen la red ni `garminconnect` real.
- pytest verde (`.venv/bin/python -m pytest -q`); textos en español; un commit local por fase
  (`v4.4 F<n>: …`) con las líneas de coautoría que te pasen. Dudas a `docs/DUDAS.md` (sección "v4.4").

---

## F1 — Login, lista y borrar ✅ (Opus, 2026-11-25)

`reloj.py` en la raíz: `login` (solo en la Terminal; tokens en `~/.garminconnect`), `lista`, `borrar ID…`.
Probado con la cuenta de Pedro: se borraron 29 entrenamientos viejos. Notas de la librería 0.3.20:
- `Garmin().login(str(TOKENS))` carga los tokens; sin ellos o vencidos lanza excepción → `cliente()` sale con el
  mensaje de cómo hacer login.
- `delete_workout` de un entrenamiento de plan de Garmin Coach da 400 "ATP plan id": se reporta y se sigue.

## F2 — Armar los entrenamientos (lógica pura)

En `reloj.py` (o `dashboard/reloj_plan.py` si queda más limpio; sin importar `garminconnect` ahí):
- `semana_actual(hoy, config, plan)` → número de semana del plan (con `semanas_repetidas`), o `None` si no hay.
- `entrenamiento(sesion, n)` → dict listo para subir (formato de `RunningWorkout` de `garminconnect.workout`, o el
  JSON equivalente que acepta `upload_workout`):
  - nombre `S{n} · {sesion.name} · {minutes}'` (p. ej. `S3 · Z2 #1 · 20'`); descripción
    `"Plan del dashboard"` (marca para reconocerlos);
  - deporte correr; un paso por cada `steps[]` **en el mismo orden**, por **tiempo** (`minutes × 60` s);
  - `kind: run` → paso de intervalo; caminata → paso de recuperación; objetivo **zona de FC** con `zoneNumber`
    = número de la zona del paso (`"Z2"` → 2). Si un paso no tiene zona, sin objetivo;
  - la `note` del paso como descripción del paso (vacía → sin descripción);
  - no agregues calentamiento ni enfriamiento que el plan no traiga. Solo la versión normal (no `easy`).
- `clasificar(enviados, estado)` → `(borrar_sin_preguntar, pendientes)`: de los enviados antes (`data/reloj.json`),
  los de sesiones `hecha` se borran sin preguntar; los `pendiente` van a la lista para preguntar.
- Pruebas: una sesión Z2 simple, una variada con varias zonas, una con caminatas (novato), la prueba de la
  semana 12, nombre y orden de pasos, `semana_actual` con una semana repetida, `clasificar`.

## F3 — Comando `semana`

`reloj.py semana [--semana N] [--si] [--borrar-pendientes] [--conservar-pendientes]`:
1. Corre primero `garmin_connect.py` (datos al día para saber qué está hecho); si falla, sigue con lo que haya y avísalo.
2. Lee `data/reloj.json` (`{"semana": n, "enviados": [{"id", "sesion", "nombre"}], "dispositivo": id}`; si no
   existe, vacío) y clasifica con el estado de **la semana de esos enviados** (`build.week_assignment` con un día
   de esa semana).
3. **Sin `--si` (por defecto) no escribe nada**: imprime qué va a subir (nombre y pasos `20' Z2`), qué va a borrar,
   y los pendientes como pregunta ("`S3 · Z2 #2 · 25'` sigue pendiente"). Sale con código 0.
4. Con `--si`: si hay pendientes y no vino `--borrar-pendientes` ni `--conservar-pendientes`, se niega y lo dice.
   Borra lo que toca (fallos: avisa y sigue; un enviado que ya no existe en Garmin cuenta como borrado), sube cada
   entrenamiento, lo manda al reloj (`push_workout_to_device`; dispositivo = `get_primary_training_device()`, o el
   último usado si no hay; guárdalo en `reloj.json`) y escribe `data/reloj.json` **después de cada subida** (si se
   corta a la mitad, no se pierden los IDs). Los pendientes conservados siguen en `enviados`.
5. Al final: "En tu reloj: Entrenamiento › Entrenamientos" y la lista de lo que quedó.
- Errores de sesión → el mensaje de `login`. Otros errores de Garmin → dilo en una línea y no reintentes
  (una subida puede quedar hecha aunque la respuesta falle: sugiere `reloj.py lista` para revisar).
- Prueba el `--dry-run` real (sin `--si`) contra la cuenta de Pedro y pega la salida en DUDAS.

## F4 — Skill y documentación

- `.claude/skills/reloj/SKILL.md` **en la raíz** (no en `template/`): cuando Pedro diga "manda la semana al reloj"
  o `/reloj`: corre `semana` sin `--si`, muéstrale el resumen, pregunta por los pendientes si hay, y con su sí
  corre `--si` (con la opción de pendientes que eligió). Si no hay sesión: dile que corra el login en la Terminal
  (no con `!`). Nunca leas `~/.garminconnect`.
- `CLAUDE.md` raíz, sección Comandos: una línea de `reloj.py` (login en la Terminal; `/reloj`).
- `docs/REQUISITOS.md` §12: marca "construido, falta probar en el reloj".
