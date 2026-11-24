# Plan v4.1: Mi entreno — carreras, récords, pestaña Cuerpo estilo InBody, menos scroll y tema oscuro

Requisitos aprobados por Pedro (2026-11-24), ver §Requisitos. Base: v4 publicado ([`PLAN_V4.md`](PLAN_V4.md)).
Datos InBody: `plan/inbody.json` (Opus ya capturó la hoja completa del 13 nov; no cambies los números).

Quién: 🤖 Sonnet ejecuta F1–F6 sin detenerse; 🔍 Opus revisa y publica. **No hagas push ni muevas `stable`.**

## Reglas

Las de `PLAN_V4.md` §Reglas, todas siguen:
- no leas `.env`;
- pytest verde (`.venv/bin/python -m pytest -q`);
- la lógica en Python y el JS solo pinta;
- español, sin librerías;
- privacidad por lista blanca, y `dashboard/validar.py` se actualiza con las claves nuevas;
- un commit local por fase (`v4.1 F<n>: …`) con las líneas de coautoría;
- carga el skill `dataviz` antes de gráficas, colores o CSS;
- dudas a `docs/DUDAS.md` (sección "v4.1") sin detenerte.

También:
- **Todo automático.** Nada de esto puede requerir que la persona registre algo a mano; todo sale de Garmin o
  de la config que se llena en `/setup`. La única excepción es InBody, que ya es opcional.
- **Compatibilidad:** configs viejas sin las claves nuevas deben seguir funcionando, con defaults.
- **Template:** lo nuevo de config va también en `template/config.example.yaml` y en `/setup` y `/ajustar`
  cuando aplique.

## Requisitos

1. **Título "Mi entreno":** en la config de Pedro y como default del template. `/setup` pregunta el título.
2. **Carreras, detectadas solas:**
   - Una corrida es carrera si Garmin trae `eventType.typeKey == "race"`, o si su nombre (que nunca se
     publica) contiene, sin importar mayúsculas ni acentos, `carrera`, `race`, `5k`, `10k`, `21k`, `42k`,
     `medio maraton`, `maraton` o `marathon`.
   - También es carrera si su fecha está en `corrida.carreras: [YYYY-MM-DD, …]` (para las pasadas; se agrega
     con `/ajustar`). Pedro: `carreras: [2026-11-21]`.
   - La carrera sigue contando como su sesión del plan, como hoy: la del 21 nov es su Larga.
   - Stats por carrera:
     - distancia, tiempo, ritmo promedio;
     - FC promedio y máxima, minutos por zona;
     - km más rápido (`fastestSplit_1000`) y ritmo por km, si hay tramos en los detalles (si no, se omite);
     - cadencia y desnivel;
     - comparación con la carrera anterior de distancia parecida (±10 %).
3. **Mejores marcas como las de Garmin:**
   - 1 km, 1 milla, 5K, 10K, medio maratón, maratón y **corrida más larga** (distancia, con su tiempo y fecha).
   - **Solo las que ya hizo.**
   - Vienen de Garmin, con historial completo, no solo de los últimos ~110 días que hoy se bajan.
4. **3 pestañas: Hoy, Progreso y Cuerpo.** Cada tarjeta agrupa un tema, con botones para cambiar de vista
   en vez de tarjetas apiladas. En pantallas ≥ 900 px, 2 columnas.
5. **Cuerpo estilo InBody,** con el mismo orden y lectura que la hoja:
   1. Análisis músculo-grasa.
   2. Historial de composición corporal, con la marca del prime.
   3. Puntuación InBody con su historial.

   Además, la grasa visceral con su rango, al lado de la puntuación.
6. **Tema oscuro por defecto,** con un botón ☾/☀ en el encabezado que se recuerda por dispositivo.

---

## F1 — Config, título y tema 🤖

1. `config.yaml` de Pedro: `perfil.titulo: Mi entreno` y `corrida.carreras: [2026-11-21]`. Defaults:
   `titulo: Mi entreno` y `carreras: []`. Agrégalo en `template/config.example.yaml` y en `/setup` (pregunta el
   título con "Mi entreno" como sugerencia) y en `/ajustar` ("la del 21 nov fue carrera" → agrega la fecha).
2. **Tema:**
   - Dark por defecto: si no hay elección guardada, el script pone `data-theme="dark"` en `<html>` **antes** de
     pintar (script inline mínimo en `<head>`, para que no parpadee).
   - Botón ☾/☀ en el encabezado, con `aria-label` "Cambiar a tema claro/oscuro". Alterna `data-theme` y lo
     guarda en `localStorage` (envuelto en try/catch).
   - Revisa que todos los colores de `styles.css` estén definidos para `[data-theme="dark"]` y
     `[data-theme="light"]`. Lo que hoy depende solo de `prefers-color-scheme` debe responder al atributo.
   - `<meta name="color-scheme">` acorde.
   - Las gráficas SVG usan los tokens y se ven bien en los dos temas.

## F2 — Carreras y mejores marcas (Python) 🤖

1. **`garmin_connect.py`:**
   - Además de lo de hoy, guarda `data/historial_corridas.json` con **todas** las corridas de la cuenta, sin
     límite de fecha, paginando la lista de actividades hasta el final.
   - Por corrida guarda solo: `startTimeLocal`, `activityType.typeKey`, `distance`, `duration`, `fastestSplit_*`
     (todas las claves que empiecen así) y `eventType.typeKey`.
   - Antes, prueba si la Personal API expone récords personales (p. ej. `/personalrecord-service/…`). Si
     responde, úsalo como fuente y anota en DUDAS el endpoint y la forma. Si no, calcula desde el historial.
   - No guardes nombres en este archivo.
   - Para la detección por nombre, `build.py` usa `data/activities.json`, que ya trae `activityName` y nunca se
     publica.
2. **`metrics.py`:**
   - `es_carrera(activity, config) -> bool`, con las 3 reglas del requisito 2. Tests con eventType race, nombre
     con acentos y mayúsculas, fecha en config y un caso negativo.
   - `stats_carrera(activity, details, config) -> dict` con lo del requisito 2: ritmo en s/km, zonas en minutos
     y `km`, que es la lista de ritmos por km si hay tramos.
   - `comparar_carrera(carrera, anteriores)`: la carrera anterior de distancia ±10 % y las diferencias de
     tiempo, ritmo y FC.
   - `mejores_marcas(historial) -> list`:
     - para 1K, milla, 5K, 10K, 21.1K y 42.2K, el mínimo de `fastestSplit_<m>` (con 1000, 1609, 5000, 10000,
       21098 y 42195);
     - más la corrida más larga por `distance`;
     - cada una con `{clave, nombre, tiempo_s, ritmo_s, fecha, distancia_km}`;
     - solo las que existan.
   - Tests.
3. **`build.py` → `data.json`:**
   - `carreras`: lista de carreras, de la más nueva a la más vieja, con sus stats y comparación, y sin nombre,
     ID ni GPS.
   - `mejores_marcas`: la lista de arriba.
   - Las carreras en las filas de corridas (semana, Tus corridas, tabla) llevan `carrera: true`.
   - Actualiza la lista blanca de `validar.py`.

**Aceptación:**
- Con los datos de Pedro, la del 21 nov sale como carrera: 5.05 km, ~41:00, FC prom. 145, máx. 176.
- `mejores_marcas` trae al menos 1K, milla, 5K y corrida más larga.
- pytest verde.

## F3 — Composición estilo InBody (Python) 🤖

En `metrics.composicion(inbody)`, agrega al resultado lo necesario para pintar sin cálculos en JS:

1. **`musculo_grasa`** (de la última medición que traiga `musculo_grasa`): para peso, MME y masa grasa, el valor
   en kg, el `pct`, la `escala` y el rango `normal`.
   - Calcula la **posición del final de la barra** en la escala de la hoja: es por tramos, porque la escala de
     grasa no es lineal (40, 60, 80, 100, 160, 220…). Cada tick ocupa el mismo ancho e interpola dentro del
     tramo. Devuelve `pos` entre 0 y 1 y `zona` (bajo, normal o alto).
   - Igual para `obesidad` (IMC y PGC).
   - Si `pct_estimado`, márcalo para que la UI ponga "≈".
2. **`historial`**: por medición, fecha, peso, MME y PGC (todas las mediciones), con `es_prime` marcado.
3. **`puntuacion`**: `[{fecha, puntos}]` de las mediciones que la traigan, con la diferencia contra la anterior.
   Por ahora es un solo punto (75); la UI lo soporta.
4. **`visceral`**: el valor de la última medición con su rango y zona.
5. También publica `control_peso`, `investigacion`, `segmental_magra` y `segmental_grasa` tal cual, para
   mostrarlos en una sección que se abre (ver F5). Todo eso ya está aprobado para publicarse.
6. Sin `musculo_grasa`, por ejemplo con InBody de otra persona con menos datos, cada parte se omite sola.

Tests con `plan/inbody.json`: peso en zona alto, pos coherente con 133 % en su escala, grasa 240 % en la escala
no lineal, prime marcado y puntuación 75.

## F4 — Navegación: Hoy, Progreso y Cuerpo 🤖

1. **Barra inferior:** Hoy · Progreso · Cuerpo, con hashes `#hoy`, `#progreso` y `#cuerpo`. Detalles queda como
   enlace al final de Progreso y de Cuerpo (`#detalles`). Los hashes viejos siguen funcionando.
2. **Componente nuevo `tarjetaConVistas(titulo, resumen, vistas[])`:**
   - Usa botones tipo segmentos, del mismo estilo que el toggle de periodo, con `role="tablist"` y
     `aria-selected`.
   - Cambia solo la gráfica o contenido de abajo.
   - Recuerda la vista elegida en memoria (no hace falta guardarla).
3. **Hoy:**
   - Banner de la sesión con el semáforo integrado: un chip chico "Recuperación: verde · ver señales" que abre
     las señales. Ya no hay tarjeta aparte al final.
   - Selector de semana.
   - **Una sola tarjeta** "Esta semana" con las stats arriba y el calendario abajo.
   - Tus corridas.
   - Si la última carrera fue hace ≤ 7 días, una tarjeta destacada "Tu carrera del sáb 21" con sus 4 números
     principales (distancia, tiempo, ritmo y FC promedio) y un enlace a Progreso → Carreras.
   - "Cómo vas mejorando" se mueve a Progreso.
4. **Progreso,** de arriba abajo:
   1. Toggle de periodo (4, 8 o 12 semanas).
   2. **Fila de números:** corridas por semana, min por semana, km por semana y ritmo en Z2 (o % trote si hay
      caminatas), con el cambio contra el periodo anterior.
   3. "Cómo vas mejorando": la frase y sus 2 mini gráficas actuales.
   4. **Corridas**, con `tarjetaConVistas`: Volumen · Ritmo · % trote. "% trote" se oculta si no hubo
      caminatas en el periodo. La tabla de corridas va en "Ver como tabla" dentro de la misma tarjeta.
   5. **Mejores marcas:** una cuadrícula de mosaicos (5K 38:12, 4 nov…), solo las que existan; la más larga
      con distancia y tiempo. Un récord de los últimos 30 días lleva una marca "nuevo".
   6. **Carreras:**
      - lista, de la más nueva a la más vieja;
      - cada carrera se abre con sus stats completas: ritmo por km como barras pequeñas, minutos por zona y la
        comparación con la anterior;
      - sin carreras: "Cuando marques una actividad como Carrera en Garmin, aparece aquí".
   7. **Plan de 12 semanas,** como hoy.
5. **Cuerpo:**
   - **Recuperación**, con `tarjetaConVistas`: HRV · FC reposo · Sueño, con la misma leyenda de diario y
     promedio de 7 días.
   - **Composición corporal** (F5).
   - **FC máxima y zonas**, la tarjeta que hoy está en Detalles.
   - Si no hay InBody, Cuerpo muestra solo recuperación y FC.
6. **≥ 900 px:**
   - El contenido usa una cuadrícula de 2 columnas. Las tarjetas anchas (calendario, Corridas, Composición)
     ocupan las 2.
   - En el teléfono todo queda en 1 columna.
   - Revisa que ninguna gráfica se desborde.

## F5 — Composición corporal estilo InBody (UI) 🤖

Una sola tarjeta "Composición corporal · {fecha}" que se lee como la hoja, con el mismo orden y nombres que
InBody. Los estilos son los del sitio: no copies logos ni tipografía de InBody.

1. **Análisis músculo-grasa:**
   - 3 filas: Peso, MME y Masa grasa, cada una con su unidad.
   - Encima, la franja Bajo · Normal · Alto, con la zona Normal sombreada.
   - Debajo de cada fila, los números de su escala, como en la hoja.
   - La barra horizontal llega a `pos`, con el valor al final ("93.8").
   - La barra de MME lleva "≈" si es estimada.
   - Abajo, **Análisis de obesidad** (IMC y PGC) con el mismo componente.
2. **Historial de composición corporal:**
   - 3 mini gráficas de línea alineadas (Peso, MME y PGC) con el valor sobre cada punto y las fechas abajo,
     como en la hoja.
   - La medición prime lleva una marca (anillo y "prime") en las 3.
   - Frase debajo: "Te faltan X % de grasa para tu prime" (de `meta`).
3. **Puntuación InBody:**
   - Número grande "75/100" con la diferencia contra la anterior.
   - Su historial en una mini gráfica de línea; con un solo punto, solo el punto y la nota "se llena con tus
     próximas mediciones".
   - Al lado, **grasa visceral** "10 · rango 1–9" con la etiqueta de su zona (ícono y texto, no solo color).
4. **"Ver hoja completa"** (`<details>`): control de peso, parámetros de investigación (TMB, cintura-cadera, grado
   de obesidad, con su rango), agua, proteínas y minerales con su rango, y segmental (magra y grasa por brazo,
   tronco y pierna) como tabla simple.
5. **Accesibilidad:** cada barra lleva `aria-label` con valor, % y zona. Hay tabla alternativa en "Ver hoja
   completa". Funciona en los dos temas.

## F6 — Capturas y autorevisión 🤖

Usa `scratchpad/shot.sh`, en `scratchpad/v41/`. Captura Hoy, Progreso, Cuerpo y Detalles a 400 px y 1100 px,
en oscuro y claro, con los datos de Pedro. Agrega:
- Hoy con `?sem=-1` (la semana de la carrera);
- Progreso con la carrera abierta;
- Cuerpo con "Ver hoja completa" abierta;
- el escenario de usuario nuevo sin datos (esc3 de v4) en Hoy, Progreso y Cuerpo.

Revísalas tú, ya que es la parte visual:
- que nada se encime ni se desborde;
- que las barras de InBody caigan donde caen en la hoja (Peso cerca de 130, MME cerca de 120, Grasa entre
  220 y 280);
- que el contraste esté bien en los dos temas.

Corrige lo que encuentres y actualiza la tabla de Seguimiento.

## Seguimiento

| Fase | Estado |
|---|---|
| F1 Config, título y tema | ✅ |
| F2 Carreras y marcas | ✅ |
| F3 Composición (Python) | ✅ |
| F4 Navegación 3 pestañas | ⬜ |
| F5 Composición InBody (UI) | ⬜ |
| F6 Capturas | ⬜ |
| Revisión Opus + publicar | ⬜ |
