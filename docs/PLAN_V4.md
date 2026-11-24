# Plan v4: template para que cualquiera use el dashboard con su Garmin y su plan

Requisitos aprobados por Pedro (2026-11-24): ver §Requisitos abajo (resumen también en
[`REQUISITOS.md` §9](REQUISITOS.md)). Base: v3.2 publicado ([`PLAN_V3_2.md`](PLAN_V3_2.md)).

Quién: 🤖 Sonnet ejecuta F0–F5 sin detenerse; 🔍 Opus revisa, publica y prepara el piloto (F6). **No hagas push.**

## Reglas

Las de siempre:
- **No leas, imprimas ni copies `.env`.** Correr `garmin_connect.py` (que lo usa por dentro) sí se vale.
- Pasos chicos y verifica cada uno. `.venv/bin/python -m pytest -q` verde siempre.
- La lógica va en Python; el JS solo pinta. Textos en español. Sin librerías en el sitio.
- Privacidad por lista blanca: el `data.json` público no lleva IDs de Garmin, nombres de actividades, GPS,
  nombre ni fecha de nacimiento. Nunca un token de GitHub en el código del sitio.
- Un commit local por fase (`v4 F<n>: …`).
- Antes de tocar gráficas, colores o CSS, carga el skill `dataviz`.
- Si algo choca con el código, decide lo más simple que cumpla el requisito y anótalo en `docs/DUDAS.md`
  (sección "v4"); no te detengas.

**Regla de oro de F0–F2:** con la config de Pedro, `site/data.json` y lo que se ve en pantalla deben quedar
**iguales** a hoy (salvo cambios de texto que este plan pida explícitamente). Antes de F0 guarda una copia de
referencia: `.venv/bin/python dashboard/build.py && cp site/data.json <scratchpad>/data_ref_v32.json` y
compárala al cerrar cada fase (`diff` de JSON normalizado con `python -m json.tool --sort-keys`). Las únicas
diferencias permitidas son claves nuevas y las que el plan nombra; anótalas en DUDAS.

## Requisitos

1. **Template, no app.** Cada persona tiene un repo chiquito con lo suyo (config, plan, InBody opcional) y su
   propio GitHub Pages público. El código vive solo en el repo de Pedro (fuente de verdad).
2. **Se actualiza solo.** El workflow del amigo llama al workflow de Pedro; cada publicación (3 al día) usa el
   código de la etiqueta `stable`. Pedro usa `main`. Pedro mueve `stable` cuando probó en su página.
3. **Las instrucciones de Claude también se actualizan solas:** `CLAUDE.md` y `.claude/skills/` del amigo los
   copia el workflow desde `stable`. Lo personal vive solo en `config.yaml` y `plan/`.
4. **Actividades genéricas** por el tipo de Garmin: categorías (fuerza, HIIT, cardio, movilidad; Pedro tiene una
   sola: "CrossFit"), configurables, máximo 4 + corrida. Semana típica por día y días de pierna.
5. **Plan de 3 corridas por semana según nivel:**
   - novato → **solo Z2** (con caminatas trote/caminata si aún no corre 20' seguidos);
   - intermedio → **Z2 con poquita Z3** (lo que hace Pedro: picos de Z3 opcionales en bloques 2 y 3);
   - corredor → **Z2 + 1 sesión de calidad + Larga** (calidad rota entre los tipos que elija: Z3 tempo,
     threshold, intervalos; descarga cada 4 semanas sin calidad).
   - Cualquiera puede elegir "solo Z2" (p. ej. "ya hago mi Z3–Z4 en HIIT").
6. **Configuración con Claude Code:** `/setup` la primera vez, `/ajustar` para cambios, `/revision` semanal.
   Nada de formularios ni ajustes dentro del sitio.
7. **Dashboard:** misma estructura (Hoy + Progreso). Cambia: categorías en calendario y carga, textos desde la
   config, tarjeta de sesión de calidad, "Cómo vas mejorando" según haya caminatas o no, estado de primer día,
   InBody opcional (sin archivo no sale la sección), enlace "Jalar datos" al repo de cada quien.

## Estructura objetivo

Repo de Pedro (`pegongorasep/garmin-dashboard`) = **motor** + los archivos personales de Pedro:

```
config.yaml                 ← NUEVO: personal de Pedro (reemplaza dashboard/config.json)
plan/plan.json, plan/inbody.json        ← personales (igual que hoy)
dashboard/  (build.py, metrics.py, ajustes.py NUEVO, defaults.yaml NUEVO)
plan/gen_plan.py            ← generador genérico (lee config.yaml)
garmin_connect.py
site/
.github/workflows/motor.yml ← NUEVO: workflow reutilizable (workflow_call)
.github/workflows/deploy.yml← Pedro: llama a motor.yml con motor_ref = su commit
template/                   ← NUEVO: lo que recibe cada amigo
  CLAUDE.md
  .claude/skills/setup/SKILL.md
  .claude/skills/ajustar/SKILL.md
  .claude/skills/revision/SKILL.md
  config.example.yaml
  README.md
  .gitignore
  .github/workflows/deploy.yml
  .github/workflows/keepalive.yml
CLAUDE.md                   ← NUEVO: para Pedro (desarrollo del motor)
```

Repo de un amigo (creado desde `template/`):

```
config.yaml   plan/plan.json   plan/inbody.json (opcional)
CLAUDE.md  .claude/skills/…   ← administrados: los sobreescribe el workflow
.github/workflows/deploy.yml  keepalive.yml   README.md  .gitignore
```

**Directorio de usuario:** todo el código lee los archivos personales desde `USER_DIR` = variable de entorno
`GARMIN_USER_DIR` si existe, si no la raíz del repo. De ahí salen `config.yaml`, `plan/`, y ahí se escribe
`data/`. El sitio construido sigue en `<motor>/site/`.

---

## F0 — Config en `config.yaml` y directorio de usuario 🤖

1. Agrega `pyyaml` a `requirements.txt` (versión fija, como las demás).
2. `dashboard/ajustes.py` con `USER_DIR` y `cargar_config(user_dir) -> dict`: lee `config.yaml`, lo combina con
   `dashboard/defaults.yaml` y devuelve el **mismo dict plano que hoy usa el código** (más las claves nuevas).
   Así build/metrics casi no cambian. Valida y truena con mensaje claro en español si falta algo obligatorio.
3. Forma de `config.yaml` (comentada, en español). Con la de Pedro:

   ```yaml
   perfil:
     titulo: Base aeróbica          # encabezado del sitio
     zona_horaria: America/Merida
     edad: 29
     fc_max: 189                    # opcional; si falta: 220 - edad
     fc_max_piso: 183               # opcional
     fc_max_correa_desde: 2026-10-26  # opcional: desde cuándo usa correa en sus sesiones intensas
   corrida:
     nivel: intermedio              # novato | intermedio | corredor
     intensidad: z2_poca_z3         # solo_z2 | z2_poca_z3 | calidad
     calidad_tipos: []              # de: tempo_z3, threshold, intervalos (solo si intensidad = calidad)
     caminatas: false               # true = sesiones de trote/caminata (novato que no corre 20' seguidos)
     inicio: 2026-11-09             # lunes
     semanas: 12
     base_min: {z2: 20, larga: 40}  # minutos con los que arranca
     semanas_repetidas: []
   actividades:
     categorias:
       - {id: crossfit, nombre: CrossFit, letra: CF, tipos: [hiit, strength_training], intensa: true}
     semana: {lun: crossfit, mar: crossfit, jue: crossfit}
     dias_pierna: []                # p. ej. [lun]
   inbody: true
   ```

   Lo demás (zone_pcts, done_ratio, ceiling_tolerance_min, rhr_tolerance_bpm, sleep_min_hours, rpe_heavy,
   max_hr_review_above, run_types) va en `defaults.yaml` y se puede sobreescribir con una sección `umbrales:`.
   Categorías por defecto para quien no las ponga:
   - fuerza (`strength_training`, letra F),
   - hiit (`hiit`, letra H, intensa),
   - cardio (`cycling`, `indoor_cycling`, `road_biking`, `mountain_biking`, `lap_swimming`,
     `open_water_swimming`, `indoor_rowing`, `rowing`, `elliptical`, `stair_climbing`, letra B),
   - movilidad (`yoga`, `pilates`, letra M).

   `walking` y lo no listado no se muestran.
4. `garmin_connect.py`, `build.py` y `gen_plan.py` usan `USER_DIR` (config, plan, data). Borra `dashboard/config.json`.
5. Los tests no dependen de los archivos personales: crea `tests/fixtures/config.yaml` (copia de la de Pedro)
   y que `test_build.py` use eso. Los tests que usan `data/` local siguen saltándose si no hay datos.
6. `run_local.sh` sigue funcionando igual.

**Aceptación:** pytest verde; `diff` contra la referencia sin diferencias.

## F1 — Actividades genéricas 🤖

1. `classify` devuelve `"run"`, el `id` de la categoría, o `None`. Todo lo que hoy dice `"crossfit"` en Python
   pasa a ser genérico:
   - `crossfit_del_dia` → `otras_del_dia`: lista por categoría con te, rpe y minutos;
   - `week_load`: una clave por categoría + run;
   - `signal_rpe`: RPE máximo de ayer en categorías `intensa`;
   - `today_card`: día de la semana típica sin corrida → `tipo: "otra"` con el nombre de la categoría;
   - `planeado`: el `id` de la categoría planeada;
   - `max_hr_progress`: sesiones `intensa` desde `fc_max_correa_desde`; si no está configurada, no se calcula
     y la tarjeta dice un texto genérico.
2. **Días de pierna:** si ayer fue día de pierna (planeado o real en `dias_pierna`) y lo sugerido hoy es la
   Larga o la calidad, `today_card` agrega aviso: "Ayer pierna: hoy mejor la Z2 y deja la Larga para mañana"
   (o "la calidad"). Test.
3. `data.json` agrega un bloque `ui`:
   - `titulo`;
   - `categorias` `[{id, nombre, letra, clase}]` (clase de color en orden fijo);
   - `nombre_intensa`: el nombre si hay una sola categoría intensa, si no `null`;
   - `acciones_url`: `https://github.com/$GITHUB_REPOSITORY/actions/workflows/deploy.yml`, o `null` sin la variable;
   - `textos` para "Cómo funciona" (días de corrida/otras actividades armados desde la config).
4. Frontend (`app.js`, `vistas.js`, `index.html`) sin "CrossFit" fijo:
   - **Calendario:** marca con `letra` y color de la categoría; la leyenda se arma con las categorías que
     aparecen. Pedro sigue viendo "CF = CrossFit · número = Training Effect aeróbico…".
   - **Señal RPE:** `RPE del ${nombre_intensa} de ayer` si hay una sola intensa, si no "RPE de tu sesión
     intensa de ayer".
   - **Carga semanal:** barras apiladas por categoría + corrida. Valida la paleta con el script del skill
     `dataviz` (claro y oscuro).
   - **Intensidad de la semana:** la nota dice "Incluye {categorías} y corridas".
   - **Encabezado:** `<h1>` y `document.title` desde `ui.titulo`; el enlace "Jalar datos de Garmin" usa
     `ui.acciones_url` y se oculta si es `null`.
   - **Cómo funciona:** desde `ui.textos`.

**Aceptación:** pytest verde, con tests nuevos para una config de ejemplo con 3 categorías (fuerza, hiit,
cardio) y día de pierna. `diff` de Pedro: solo claves nuevas o renombradas (anótalas). Capturas de Pedro iguales.

## F2 — Generador de plan por nivel 🤖

`plan/gen_plan.py --config <config.yaml> --out <plan.json>`, por defecto `USER_DIR`. Mismo formato de
`plan.json` que hoy (`weeks[].sessions[]` con `id`, `tipo`, `name`, `minutes`, `steps`, `easy`).

1. **Progresión común:** 12 semanas, bloques de 3 de carga + 1 de descarga. Con `base_min` = {z2: 20,
   larga: 40} debe dar **exactamente** la tabla actual de Pedro. Para otras bases, los incrementos se escalan
   proporcionalmente y se redondean a 5'. La versión suave usa la misma regla que hoy. Si `semanas` ≠ 12,
   repite el patrón de bloques; documenta cómo.
2. **Por intensidad:**
   - `solo_z2`: Z2 #1, Z2 #2 y Larga, sin picos.
   - `z2_poca_z3`: la de Pedro, con picos de Z3 opcionales en Z2 #1 de los bloques 2 y 3.
   - `calidad`: sesiones `z2a` (Z2), `calidad` (tipo `calidad`) y `larga`.
     - La calidad lleva calentamiento 10' Z2, bloque principal y enfriamiento 5' Z1-Z2.
     - Rota los tipos elegidos en las semanas de carga.
     - En descarga es una Z2 normal.
     - Bloques principales, progresando por bloque:
       - `tempo_z3`: 2×10' Z3 con 3' suave → 2×12' → 2×15'.
       - `threshold` (Z4): 4×5' con 2' suave → 5×5' → 4×6'.
       - `intervalos` (Z4): 6×2' con 2' suave → 8×2' → 6×3'.
     - Cada paso del bloque es `{kind: "run", zone: "Z3"|"Z4", minutes}` y la recuperación es
       `{kind: "walk"|"run", zone: "Z1-Z2"}`.
     - La sesión lleva `objetivo: {zona, minutos}`, la suma de minutos de trabajo.
   - `caminatas: true`: los pasos de Z2 y Larga son repeticiones trote/caminata (`run` Z1-Z2 + `walk`).
     - Bloque 1 es 3'/1', bloque 2 es 5'/1' y bloque 3 es 8'/1'.
     - Ajusta la última repetición para que la suma dé los minutos de la sesión.
     - La nota dice "si una semana te sientes bien, puedes subir al siguiente escalón".
3. **`verificar()`** genérico:
   - las sumas cuadran;
   - la Larga y la versión suave nunca llevan Z3 ni Z4;
   - máximo 1 sesión con Z3+ por semana;
   - la descarga no lleva calidad.
4. `docs/PLAN_ENTRENAMIENTO.md` de Pedro no cambia. El `plan/plan.json` de Pedro no se regenera en el repo
   (es suyo). Solo hay un test que compara lo generado con su config contra él.
5. **Backend de la sesión de calidad:**
   - `assign_sessions` asigna a `calidad` la primera corrida no-Larga de la semana con ≥ 50 % de los minutos
     objetivo en Z3 o más. Las demás llenan la Z2 en orden.
   - `run_check` de calidad: "bien" si los minutos en la zona objetivo son ≥ `done_ratio` × objetivo, usando
     `zone_minutes`. Avisa si pasó mucho tiempo por encima de esa zona.
   - Tests de los tres tipos.

**Aceptación:**
- La config de Pedro genera su `plan.json` idéntico (test).
- Hay un test por combinación: novato con caminatas, intermedio, corredor con calidad de 1, 2 y 3 tipos,
  y corredor solo_z2.

## F3 — UI nuevo 🤖

1. **Tarjeta de sesión de calidad** (Hoy, "Tus corridas" y vista previa de la sesión):
   - estructura legible ("10' Z2 · 4×5' threshold (2' suave) · 5' suave");
   - zona objetivo con sus lpm;
   - al hacerla, "Minutos en Z4: 17 de 20 ✓".
   - Reusa los componentes de pasos que ya existen.
2. **"Cómo vas mejorando":**
   - Si en las últimas 4 semanas alguna corrida tuvo caminatas, se queda como hoy (% trote).
   - Si no, cambia "% trote por corrida" por **"Ritmo en Z2"**: ritmo de las corridas cuyo promedio de FC
     cayó en Z2, de la misma fuente que la gráfica de ritmo de Progreso.
   - `mejora_frase` tiene la variante equivalente ("a la misma FC vas 0:25/km más rápido que hace 4 semanas").
   - La lógica va en Python.
3. **Primer día:**
   - Si no hay actividades ni días de salud, Hoy muestra "Primera sincronización lista. Garmin tarda en
     mandar el historial; regresa en unas horas" y la semana 1 del plan. No debe haber errores en consola.
   - Si el plan empieza en el futuro: "Tu plan empieza el lun 7 dic" con la semana 1 de vista previa.
   - Tests de build con `data/` vacío.
4. **Composición corporal:** sin `plan/inbody.json` o con `inbody: false`, la sección no sale (verifica que no
   quede tarjeta vacía).
5. **Capturas** con `scratchpad/shot.sh`, o el método local en localhost:8000, de tres escenarios:
   - Pedro, que debe verse igual que v3.2;
   - un corredor con calidad, 3 categorías y día de pierna;
   - un usuario nuevo sin datos.

   Para los escenarios 2 y 3 usa datos de prueba (fixtures o datos de Pedro con otra config). Cada uno a
   400 px y 1100 px, en claro y oscuro.

**Aceptación:** pytest verde, capturas revisadas por ti mismo y problemas corregidos.

## F4 — Workflow compartido y `stable` 🤖

1. **`.github/workflows/motor.yml`**, con `on: workflow_call`:
   - inputs: `motor_ref` (string, default `stable`);
   - secret: `PERSONAL_API_KEY` (required).
   - Pasos:
     1. `actions/checkout` del repo que llama, en la raíz: es el `USER_DIR`.
     2. `actions/checkout` de `pegongorasep/garmin-dashboard` en `motor_ref`, en `motor/`.
     3. Python 3.12 e instalación de `motor/requirements.txt`.
     4. Caché de `data/activity_details.json`, igual que hoy.
     5. `python motor/garmin_connect.py`, con `GARMIN_USER_DIR=${{ github.workspace }}`.
     6. `python motor/dashboard/build.py`.
     7. `python motor/dashboard/validar.py` (nuevo: revisa que `data.json` exista, tenga las claves de la
        lista blanca y no tenga claves prohibidas). No corre pytest; eso es del repo de Pedro.
     8. Upload Pages de `motor/site` y deploy, en un segundo job, como hoy.
     9. **Sincroniza instrucciones**, solo si `github.repository != 'pegongorasep/garmin-dashboard'`:
        copia `motor/template/CLAUDE.md` y `motor/template/.claude/` a la raíz y hace commit
        "chore: instrucciones al día (motor <sha corto>)" solo si cambió algo.
        No toca `.github/workflows/` (GITHUB_TOKEN no puede).
2. **`.github/workflows/deploy.yml` de Pedro:**
   - mismo cron y `workflow_dispatch`;
   - `jobs.publicar.uses: ./.github/workflows/motor.yml` con `motor_ref: ${{ github.sha }}`, el secret
     explícito y `permissions: {contents: write, pages: write, id-token: write}`.
   - En el repo de Pedro, el job aparte corre `pytest` antes (o como paso previo); si falla, no publica.
3. **`template/.github/workflows/deploy.yml`** (unas 15 líneas):
   - `uses: pegongorasep/garmin-dashboard/.github/workflows/motor.yml@stable`;
   - mismo cron, `workflow_dispatch`, secret explícito (`secrets: inherit` no sirve entre dueños distintos)
     y los permisos.
   - `template/.github/workflows/keepalive.yml` es copia del de Pedro.
4. **Etiqueta `stable`:** no la crees. Documenta en `CLAUDE.md` de Pedro cómo moverla:
   `git tag -f stable <sha> && git push -f origin stable`. Opus la crea al publicar.
5. **Prueba local del flujo:**
   - En el scratchpad arma un "repo de amigo" de prueba: `config.yaml` de corredor, `plan/` generado con
     `gen_plan.py` y `data/` copiado de los datos de Pedro.
   - Corre `GARMIN_USER_DIR=<ese dir> .venv/bin/python dashboard/build.py` y `validar.py`.
   - Si `actionlint` está instalado, valida los YAML; si no, revisa a mano y anótalo.

## F5 — Template e instrucciones para Claude Code 🤖

Escribe para alguien que no sabe programar y para su Claude Code. Todo en español, claro y corto.

1. **`template/CLAUDE.md`:**
   - Qué es el proyecto, de dónde viene el código (motor de Pedro, etiqueta `stable`) y qué archivos son suyos
     y cuáles administrados.
   - Reglas de seguridad:
     - la key de Garmin nunca en el chat: la persona la escribe con `! gh secret set PERSONAL_API_KEY`;
     - nunca leer `.env`;
     - no publicar GPS, IDs ni nombres de actividades;
     - nunca un token en el sitio.
   - "Si no existe `config.yaml`, ofrece correr `/setup`."
   - Cómo ver la página localmente: clonar el motor en `.motor/` (en `.gitignore`), `GARMIN_USER_DIR=.` y servir.
2. **`/setup`** (`template/.claude/skills/setup/SKILL.md`), paso a paso:
   1. Revisa requisitos: `gh auth status` (si falla, pide `! gh auth login`), python3, que el repo exista en GitHub.
   2. Preguntas de nivel: tiempo corriendo y veces por semana, minutos seguidos sin caminar, si hace
      HIIT/CrossFit/algo intenso. Clasifica con la tabla y **sugiere** la intensidad:

      | Nivel | Señales | Sugerencia |
      |---|---|---|
      | novato | < 3 meses o no corre 20' seguidos | `solo_z2`, `caminatas: true` si no corre 20' seguidos |
      | intermedio | 20–40' seguidos, 1–3 veces/semana | `z2_poca_z3` |
      | corredor | 45'+ seguidos, 3+ veces/semana por 3+ meses | `calidad` y preguntar qué tipos |

      Si hace algo intenso: "Tu 20 % intenso ya sale de tu {actividad}; te sugiero `solo_z2`". La persona
      acepta o cambia.
   3. `base_min`: con lo que corre hoy, sin pasarse (Z2 ≈ lo que corre cómodo, Larga ≈ su corrida más larga
      reciente). Como Pedro: plan basado en su volumen real.
   4. Perfil:
      - edad y FC máx si la sabe;
      - zona horaria;
      - actividades: qué hace y qué días, cómo las registra en Garmin (para mapear los tipos) y días de pierna;
      - fecha de inicio (próximo lunes);
      - si tiene InBody (y cómo pasar la foto después).
   5. Escribe `config.yaml`, clona el motor en `.motor/` y genera `plan/plan.json`. Muestra un resumen de las
      primeras 4 semanas para que lo apruebe.
   6. Pide la key: "en Garmin Connect saca tu Personal API key; luego escribe aquí `! gh secret set
      PERSONAL_API_KEY` y pégala cuando te la pida". Nunca en el chat.
   7. Activa Pages (`gh api -X POST repos/{owner}/{repo}/pages -f build_type=workflow`; si ya existe, PUT),
      commit y push, `gh workflow run deploy.yml`, espera con `gh run watch` y da el link
      `https://{owner}.github.io/{repo}/`.
3. **`/ajustar`:** cambia nivel, intensidad, tipos de calidad, actividades, días o inicio.
   - Edita `config.yaml` y regenera el plan solo si cambió algo del plan.
   - Si el plan ya empezó, conserva las semanas pasadas: genera desde la semana actual y advierte.
   - Commit, push y publica.
4. **`/revision`:** revisión semanal como la que Pedro hace con Claude.
   - Lee el `data.json` publicado (curl a su Pages).
   - Resume la semana: corridas vs plan, zonas, señales de recuperación, carga.
   - Sugiere ajustes conservadores: repetir semana con `semanas_repetidas`, bajar un escalón de caminatas.
   - Los aplica solo si la persona acepta.
5. **`template/README.md`** para humanos, en 5 pasos:
   1. Crear cuenta de GitHub e instalar Claude Code y `gh`.
   2. "Use this template" para crear el repo (público).
   3. Clonarlo y abrir Claude Code en la carpeta.
   4. Escribir "hola" (o `/setup`).
   5. Listo.

   Explica también qué se publica y qué no.
6. **`template/config.example.yaml`** comentado y **`template/.gitignore`** (`.env`, `.venv/`, `.motor/`,
   `data/`, `__pycache__/`, `.DS_Store`).
7. **`CLAUDE.md` de Pedro:**
   - flujo de trabajo: plan → Sonnet ejecuta → Opus revisa y publica;
   - comandos: pytest con `.venv`, deploy, `gh run watch`, `git pull --rebase` antes de push;
   - reglas de seguridad;
   - cómo mover `stable` y regla: solo después de ver bien su página;
   - el motor debe seguir funcionando con configs viejas (claves nuevas siempre con default).
8. Actualiza el `README.md` de Pedro: qué es el motor y cómo invitar a alguien.

**Aceptación:**
- Simulación: en un dir temporal copia `template/` y, siguiendo `/setup` a mano sin GitHub, llega a
  `config.yaml` y `plan.json` válidos.
- Anota en DUDAS cualquier paso que no se pueda probar sin GitHub real.

## F6 — Revisión y piloto 🔍

1. Opus:
   - revisa todo;
   - corre pytest y el `diff` de Pedro;
   - revisa las capturas;
   - hace push a `main` y verifica que la página de Pedro se publica igual;
   - crea la etiqueta `stable`.
2. Opus propone a Pedro marcar el repo como template o crear un repo `garmin-dashboard-template` con el
   contenido de `template/`, y le pide permiso antes de crear repos.
3. Piloto: el amigo lo instala solo con `/setup`; anotamos dónde se atora.

## Seguimiento

| Fase | Estado |
|---|---|
| F0 Config y USER_DIR | ✅ |
| F1 Actividades genéricas | ✅ |
| F2 Generador por nivel | ✅ |
| F3 UI nuevo | ✅ |
| F4 Workflow compartido | ⬜ |
| F5 Template e instrucciones | ⬜ |
| F6 Revisión Opus + publicar + piloto | ⬜ |
