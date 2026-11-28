# Plan v4.2: pestaña Plan, tipos de entreno con siluetas, variada para nuevos, íconos y 80/20

Requisitos aprobados por Pedro (2026-11-24): [`REQUISITOS.md`](REQUISITOS.md) §10. Base: v4.1 publicado
([`PLAN_V4_1.md`](PLAN_V4_1.md)).

Quién: 🤖 Sonnet ejecuta F1–F7 sin detenerse; 🔍 Opus revisa y publica. **No hagas push, tags ni workflows.**

## Reglas

Las de v4 / v4.1, todas siguen:
- no leas `.env` (no hace falta correr `garmin_connect.py` en este plan; usa los `data/` que ya hay);
- pytest verde (`.venv/bin/python -m pytest -q`), y las pruebas no dependen de `GITHUB_REPOSITORY`;
- lógica en Python, el JS solo pinta; español; sin librerías;
- lista blanca: toda clave nueva de `data.json` va en `dashboard/validar.py`;
- un commit local por fase (`v4.2 F<n>: …`) con las líneas de coautoría;
- carga el skill `dataviz` antes de gráficas, colores, íconos o CSS;
- dudas a `docs/DUDAS.md` (sección "v4.2") sin detenerte.

También:
- **Compatibilidad:** configs viejas sin las claves nuevas siguen funcionando (defaults en
  `dashboard/defaults.yaml` / `ajustes.cargar_config`); claves viejas que se retiran (`actividades.semana`) se
  **toleran y se ignoran**, sin error. El sitio tolera claves ausentes en `data.json`.
- **El plan de Pedro no cambia:** tras F2, `gen_plan.py` con su `config.yaml` debe reproducir `plan/plan.json`
  byte a byte (hay prueba; mantenla).
- **Template:** lo nuevo de config va en `template/config.example.yaml`, `/setup` y `/ajustar`.

---

## F1 — Sin CrossFit asumido y sin "¿Larga?" 🤖

- Quita `actividades.semana` de `config.yaml` de Pedro, de `template/config.example.yaml`, de `/setup` (ya no
  pregunta días, solo **cómo registra cada actividad en Garmin**) y de `/ajustar`. `ajustes.py` la ignora si
  viene (sin `semana_tipica` en el config plano, o vacía).
- `build.py`: el calendario ya no pinta días futuros con categorías planeadas ni "¿Larga?"
  (`dia_de_semana` → `planeado` desaparece; `app.js:307` deja de usarlo). Días futuros: vacíos.
- `build_ui` (`build.py:517`) ya no arma frases de "CrossFit lun, mar y jue".
- `metrics.today_card`: sin `tipica`. Si hoy hay una actividad intensa registrada → "Hoy: CrossFit ✓ · próxima
  corrida: …"; si no, solo "Próxima corrida: …" + recuperación. Nunca "Hoy CrossFit" por adivinanza.
- `metrics.aviso_pierna`: solo cuenta lo que **Garmin registró** ayer (quita `semana_tipica`). Sigue
  requiriendo `dias_pierna` configurado.
- Pruebas: config con `actividades.semana` vieja no truena; calendario futuro sin planeados; banner sin
  actividad hoy no dice CrossFit.

## F2 — Tipos de entreno y corrida variada (Python) 🤖

### Catálogo
Nuevo módulo `dashboard/tipos.py` con `CATALOGO`: lista ordenada de
`{id, nombre, grupo, descripcion, forma}`.
- `grupo`: `"continuos"` (Continuos), `"variados"` (Variados — los del fisio), `"calidad"` (De calidad).
  En el sitio no se nombra al fisio.
- `forma`: lista de tramos `[duracion_relativa, nivel]`, nivel 0–1 (0 = reposo, 1 = máximo). Solo describe el
  patrón; **no lleva zonas ni colores**. Tramos de transición permitidos (`[d, n1, n2]` = rampa) para que
  calentamiento y enfriamiento se vean como subidas/bajadas.
- Tipos (id → idea de la forma):
  - continuos: `continuo` (rampa, plano medio-bajo largo, rampa; la descripción dice que **la Larga es un
    continuo más largo**), `trote_caminata` (dientes: trote medio, caminata baja, repetido).
  - variados: `espiga` (sube por escalones a un pico corto y baja igual), `piramide` (bloques de trabajo
    1-2-3-2-1 con recuperaciones bajas), `ascendente` (escalera que sube), `descendente` (escalera que baja),
    `densidad` (picos iguales con descansos de 1× y luego 2× su duración, se nota la diferencia), `rotativo`
    (ciclo bajo-medio-alto repetido).
  - calidad: `progresivo` (sube poco a poco hasta el final), `tempo` (rampa, plano alto sostenido, rampa),
    `umbral` (2–3 bloques altos largos, descansos cortos), `vo2` (picos muy altos y cortos), `fartlek`
    (cambios irregulares), `carrera` (sostenido alto con remate al final).
- `descripcion`: una línea en español claro, sin números de zona ("subes poco a poco hasta un pico corto y bajas
  igual").

### Variada en `plan/gen_plan.py`
- Config nueva `corrida.variada` (default **false**; con false todo sale como hoy). `/setup` la pone en
  `true`; `/ajustar` puede cambiarla.
- Con `variada: true`:
  - Semana de carga: **Z2 #1** continuo (sin picos Z3, aunque la intensidad sea `z2_poca_z3`), **Variada ·
    <Nombre>** en lugar de Z2 #2 (mismos minutos que tendría Z2 #2), **Larga** continua Z1–Z2.
  - Descarga: las tres continuas (como hoy).
  - Los tipos rotan por semana de carga (igual que `calidad_tipos` hoy, con `n_carga`):
    - `solo_z2` → `ascendente`, `densidad`, `rotativo`, `descendente`, todos **solo con Z1 y Z2**.
    - `z2_poca_z3` → `espiga`, `piramide`, `ascendente`, `rotativo`, `descendente`, `densidad`, con
      **Z3 corto**: máximo 6' de Z3 por sesión y ≤ 20 % de la sesión.
    - `calidad` → solo avanzados: la sesión de calidad existente, con `calidad_tipos` ampliados a
      `tempo_z3`, `threshold`, `intervalos`, `progresivo`, `fartlek` (`progresivo` y `fartlek` también se
      pueden elegir sin `variada`). Con `variada` y `calidad_tipos: []` → usar los 5.
  - Con `caminatas: true`: los tramos Z1 de la variada son `kind: "walk"`; los de Z2–Z3, trote.
  - Pasos con la estructura que ya existe (`paso`, `repeat`), cada uno con su zona exacta (`Z1`, `Z2`, `Z3`…;
    usa `Z1-Z2` solo donde hoy ya se usa). Calentamiento y enfriamiento de 5' en Z1. Duraciones enteras.
  - Cada sesión lleva `forma: "<id del catálogo>"` (también las que ya existen: Z2/Larga → `continuo`, con
    caminatas → `trote_caminata`, calidad → su tipo: `tempo_z3`→`tempo`, `threshold`→`umbral`,
    `intervalos`→`vo2`). **Ojo:** agregar `forma` cambiaría el `plan.json` de Pedro; en vez de escribirla en el
    plan, derívala en `build.py` (función `forma_de(sesion)`), así su plan queda byte a byte.
  - `verificar()` amplía: sumas exactas, máx. 1 sesión con Z3+ por semana, Larga sin Z3+, `solo_z2` sin Z3+,
    límites de Z3 de `z2_poca_z3`, descarga sin variada ni calidad.
- Pruebas: los 3 niveles × caminatas sí/no × variada sí/no generan sin error; rotación correcta; límites de
  zonas; Pedro byte a byte.

### Silueta de la sesión (para el sitio)
`build.py`: cada sesión convertida (`convert_session`) suma `silueta`: lista plana de
`[minutos, zona]` desplegando `repeat` (zona de un paso `walk` = `Z1`; `Z1-Z2` → `Z2`; un paso `optional` lleva
un tercer elemento `true`). Y `forma` (id). Al data.json también va `tipos`: el catálogo + `en_plan` (ids que
aparecen en el plan de la persona). Agrega estas claves a `validar.py`.

## F3 — Navegación: Hoy · Plan · Progreso (Corridas / Cuerpo) 🤖

- Pestañas de abajo: **Hoy**, **Plan**, **Progreso**. Rutas: `#hoy`, `#plan`, `#progreso` (= Corridas),
  `#progreso/cuerpo`. Alias que siguen sirviendo: `#cuerpo` → `#progreso/cuerpo`, `#detalles` → `#plan`,
  `#progreso?carrera` y `#cuerpo?hoja` (los de capturas de v4.1) siguen abriendo lo mismo.
- **Progreso** arriba tiene un control segmentado **Corridas | Cuerpo** (el mismo estilo de los botones de vista).
  El selector 4/8/12 semanas solo se ve en Corridas.
- **Plan**: 1) las 12 semanas (cuadrícula de bloques + sesiones de la semana elegida, como hoy en Progreso),
  2) Tipos de entreno (F4), 3) Zonas y reglas: la tarjeta "FC máxima y zonas" (sale de Cuerpo) y las reglas del
  plan que hoy están en Detalles.
- **Progreso › Corridas**: fila de números, Cómo vas mejorando (F6), Corridas, Intensidad por semana (F6),
  Mejores marcas, Carreras, Carga (de Detalles).
- **Progreso › Cuerpo**: Recuperación y Composición corporal.
- **Detalles desaparece** (su contenido ya quedó repartido; borra `enlaceDetalles`). Si algo de Detalles no
  encaja, ponlo al final de Plan y anótalo en DUDAS.
- 2 columnas en ≥ 900 px como hoy.

## F4 — Siluetas (UI) 🤖

Carga `dataviz` antes. Un componente `silueta(tramos, {color})` en `charts.js`, SVG a mano:
- **Línea** escalonada con esquinas suaves (y rampas donde la forma lo diga), 2px, sin ejes, sin números, sin
  rejilla. Ancho de cada tramo proporcional a su duración. Altura ~48px en tarjeta de catálogo, ~40px en sesión.
- **Catálogo** (sin color): línea en `--ink` (tinta del tema). Tarjetitas en rejilla (2 por fila en celular,
  3–4 en compu): silueta, nombre, descripción. Arriba los tipos `en_plan` con la etiqueta "En tu plan"; el resto
  bajo "Ver todos los tipos" (`details`). Agrupados por grupo. Nota corta: "La Larga es un continuo más largo".
- **Sesión del plan** (con color): la silueta de `silueta` (minutos+zona) con nivel por zona
  (Z1 0.25, Z2 0.45, Z3 0.65, Z4 0.82, Z5 0.97) y **cada tramo del color de su zona de Garmin**. Tramos
  opcionales punteados. Tokens **nuevos y exclusivos de la silueta** (no cambies los colores de zona del resto del
  sitio): `--g1` gris, `--g2` azul, `--g3` verde, `--g4` naranja, `--g5` rojo, con su versión para tema oscuro.
  Valida contraste contra las superficies de ambos temas con `validate_palette.js` (están en el orden fijo
  Z1→Z5; lo que importa es que se distingan y se lean sobre la tarjeta). Una mini leyenda solo con las zonas que
  aparecen ("Z1 · Z2 · Z3" con su punto de color), para que la identidad no sea solo color.
- Dónde: al abrir una sesión en **Hoy** (Tus corridas) y en la semana elegida de **Plan**, arriba de los pasos
  que ya se muestran (la receta con minutos y zonas ya existe en `pasoLi`; si hace falta, una línea resumen
  "5' Z1 · 3' Z2 · 2' Z3 · …"). La versión "Suave" también tiene su silueta.
- Hover/tap en un tramo: tooltip "3' · Z3" (en la silueta de sesión; el catálogo no lleva tooltip).

## F5 — Íconos SVG por actividad 🤖

- `site/iconos.js`: SVG en línea, trazo 1.75px, `stroke="currentColor"`, `fill="none"`, viewBox 24, dibujados a
  mano, estilo de línea simple y consistente: `correr` (monito corriendo), `medalla`, `mancuerna`, `rayo`,
  `bici`, `nadar`, `caminar`, `yoga`, `punto`. Siempre con `aria-hidden` y texto al lado o `title`.
- Python decide el ícono (el JS solo pinta): `ajustes`/`metrics` mapean typeKey de Garmin → ícono:
  running/treadmill_running/trail_running → `correr`; carrera → `medalla`; strength_training → `mancuerna`;
  hiit/cardio → `rayo`; cycling/indoor_cycling/virtual_ride/spinning → `bici`; lap_swimming/open_water_swimming
  → `nadar`; walking/hiking → `caminar`; yoga/pilates → `yoga`; otro → `punto`.
  Cada categoría de `ui.categorias` lleva `icono`: el de su primer tipo, o `icono:` de su config si viene
  (CrossFit de Pedro → `rayo`). Agrega `icono` a `config.example.yaml` (opcional) y a `validar.py`.
- Dónde: calendario de Hoy (el ícono sustituye la letra "CF"; debajo sigue el TE; quita la leyenda "CF =
  CrossFit", deja solo "número = Training Effect aeróbico de Garmin (0–5)"), días con corrida (ícono correr; si
  fue carrera, medalla), tarjeta de carrera de Hoy, lista de Carreras, Mejores marcas (medalla en la que salió
  de carrera), tabla de corridas (columna de sesión), leyenda de la gráfica de otros entrenos (F6).
- Muestra en `scratchpad/v42/iconos_{oscuro,claro}.png` (los 9 a 24px y 48px).

## F6 — Fuerza/HIIT en mejora y 80/20 🤖

- **Cómo vas mejorando**: `build_mejora` suma `otras` por semana: `{semana, conteos: {cat_id: n}}` (sesiones,
  no minutos) y en la frase "· CrossFit 3.2 por semana (antes 2.5)" por categoría (máx. 2 en la frase; si no
  hay categorías u ocurrencias, no sale). Nueva mini gráfica **"Otros entrenos por semana"** junto a "Minutos por
  semana": barras de conteo apiladas por categoría (colores de las categorías existentes, en orden fijo), 2px de
  separación, leyenda con ícono y nombre, tooltip "Semana del 9 nov · CrossFit 3". Eje separado: nunca en la
  misma gráfica que minutos.
- **80/20 en Hoy**: `semanas_hoy[i].intensidad = {minutos: {Z1..Z5}, bajo, limbo, alto}` con la misma cuenta
  que la barra de Detalles (corridas + actividades, Z0 fuera). En "Esta semana", debajo de los minutos, una
  barra delgada (reusa `zonaBar` en versión compacta: sin tabla, sin brackets) con la marca de 80 % y el texto
  "Bajo 72 % · meta 80 %". Sigue al selector de semana. Sin minutos en zonas → no se pinta.
- **Intensidad por semana** en Progreso › Corridas: barra apilada 100 % por semana (Bajo Z1–Z2 / Limbo Z3 /
  Alto Z4–Z5, colores de zona del sitio), línea de referencia en 80 % ("meta 80 % bajo"), tooltip con los tres
  %, tabla alternativa. Sigue el selector 4/8/12. Datos en `progreso.intensidad_semanas`.
- Todo a `validar.py`; pruebas de conteos y porcentajes.

## F7 — Capturas y autorevisión 🤖

`scratchpad/shot.sh` → `scratchpad/v42/`:
- Pedro: `hoy`, `plan`, `progreso` (Corridas), `progreso-cuerpo`, a 400 y 1100 px, oscuro y claro.
- Estados: sesión abierta en Hoy con silueta; Plan con "Ver todos los tipos" abierto; íconos.
- Usuario nuevo con `variada: true`: arma configs de prueba en `scratchpad/` (novato `solo_z2` con caminatas,
  intermedio `z2_poca_z3`, corredor `calidad`), genera su plan con `--config/--out` y construye con
  `GARMIN_USER_DIR` apuntando a una carpeta de prueba con los `data/` de Pedro copiados; captura Plan y Hoy de
  cada uno (semana 2 de carga, para ver la variada).
- Sin errores de consola. Revisa: nada encimado ni desbordado a 400 px; siluetas legibles en ambos temas; el
  catálogo se ve como formas distintas entre sí; los colores de zona de la silueta se distinguen.

Corrige lo que encuentres y actualiza la tabla.

## Seguimiento

| Fase | Estado |
|---|---|
| F1 Sin CrossFit asumido | ✅ |
| F2 Tipos y variada (Python) | ✅ |
| F3 Navegación Hoy · Plan · Progreso | ✅ |
| F4 Siluetas | ✅ |
| F5 Íconos | ✅ |
| F6 Fuerza/HIIT y 80/20 | ✅ |
| F7 Capturas | ✅ |
| Revisión Opus + publicar | ✅ publicado y `stable` 2026-11-24 |

## Ajuste v4.2.1 (2026-11-24, pedido de Pedro)

- Hoy › Tus corridas y Plan › 12 semanas: cada sesión muestra su silueta a color en la fila cerrada; al abrirla, leyenda,
  resumen y pasos (sin repetir la silueta). Se quitó "Cómo crearla en Garmin Connect".
- Progreso › Cómo vas mejorando: arriba de cada barra de "Minutos por semana", un ícono por entreno de la semana
  (corrida/medalla primero, luego cada categoría). Python manda `progreso.mejora.semanas[].iconos`; `validar.py` revisa los nombres.

## Ajuste v4.2.2 (2026-11-24, pedido de Pedro)

- Siluetas de sesión: arrancan abajo (zona 0), suben en rampa a su primer tramo y bajan al final, como las del catálogo.
- Los íconos de entrenos pasan de "Cómo vas mejorando" a Progreso › Corridas › Volumen (`progreso.semanas[].iconos`).
- Dos actividades de la misma categoría (no corrida) a menos de 3 h cuentan como una (`metrics.sin_repetidas`): íconos,
  "Otros entrenos por semana" y la frase de mejora.

## Ajuste v4.2.3 (2026-11-24, pedido de Pedro)

- Íconos sin repetir: `progreso.semanas[].entrenos` = [{icono, nombre, n}], uno por tipo; el sitio pinta el ícono y "2x".
- Silueta de sesión con título (`titulo`, p. ej. "Continuo en Z2", de `tipos.titulo_de`); las rampas de subida y bajada
  van en color de Z0 (`--g0`) y la leyenda incluye Z0.
- InBody: hojas completas del 25 may 2024 y del 8 oct 2026 en `plan/inbody.json`.

## Ajuste v4.2.4 (2026-11-24, pedido de Pedro)

- Hoy › Esta semana: barra 80/20 como la de Plan › Intensidad (26 px, corchetes, "meta 80 %") con zona y % dentro de
  cada tramo; cada tramo esconde lo que no le cabe (container queries) y en pantalla chica va solo el % más una leyenda.
- Plan › Cómo funciona: plegable, cerrada al abrir.
- Cuerpo › Puntuación InBody: se quitó el "null" suelto; la medición del 25 oct 2025 sale como hueco (puntos null, "—").

## Ajuste v4.2.5 (2026-11-24, pedido de Pedro)

- Siluetas a color: 5' de calentamiento y 5' de enfriamiento (Z0) a escala; arriba de cada racha de la misma zona,
  "6' Z2" (hasta 3 renglones si se juntan). Sin leyenda ni resumen; se quitaron del cuerpo de la sesión.
- Se quitó la gráfica "Otros entrenos por semana" (los íconos con 2x de Corridas ya lo dicen). `mejora.otras` sigue en
  el JSON por compatibilidad.

## Ajuste v4.2.6 (2026-11-24, aprobado por Pedro): Tus corridas sin repetir

- Cada sesión trae `rachas` (Python): minutos, zona como la dice el plan ("Z1–Z2", "caminata") y lpm de cada racha
  de la silueta. Encima de la silueta: "5 min / calentar", "20 min Z1–Z2 / 125–150 lpm", "5 min / enfriar"; con más
  de 3 rachas, un renglón sin lpm. Se acomodan midiendo su ancho (2 renglones; la que no cabe se esconde).
- Al abrir una sesión: sencilla (≤ 3 rachas, sin repeticiones) = solo las notas de sus pasos; si no, "Ver pasos"
  cerrado. Versión suave también en la fila de HOY.
- Plan: Intensidad junto a FC máxima, Cómo funciona abajo a todo lo ancho; la carrera de Hoy mide lo que su contenido.

## Ajuste v4.2.7 (2026-11-24, aprobado por Pedro): una zona por tramo, calentar/enfriar aparte

- Una sola zona por tramo en plan y sitio (`tipos.zona_unica` para planes viejos). Ver REQUISITOS §10.1–10.2.
- Siluetas compactas (más de una zona): minutos con línea del color del tramo + leyenda con lpm (`leyendaRachas`).
- Calentar/enfriar nunca cuentan: `rampas_de` decide si el sitio dibuja las rampas; el generador ya no las mete en
  calidad ni variadas; Z1 inicial de una variada ≤ 2' (`Z1_INICIO_MAX`).
