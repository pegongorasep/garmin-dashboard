# Plan v4.5: Progreso sin repetir, km por semana, ayuda personalizada

Requisitos aprobados por Pedro (2026-11-25): [`REQUISITOS.md`](REQUISITOS.md) §13. Base: `main` (v4.4).

Quién: 🤖 Sonnet ejecuta F1–F4 sin detenerse; 🔍 Opus revisa y publica. **No hagas push, tags ni workflows.**

## Reglas
- **No leas `.env`** ni `~/.garminconnect`. Correr `garmin_connect.py` sí se vale.
- pytest verde (`.venv/bin/python -m pytest -q`); las pruebas no dependen de la red.
- Lógica en Python, el JS solo pinta; textos en español; sin librerías de JS. Carga el skill `dataviz` antes de
  tocar gráficas, colores o CSS.
- Lista blanca: toda clave nueva de `data.json` va en `dashboard/validar.py` (y en sus pruebas). El sitio tolera
  claves ausentes (data.json viejo → la sección no sale, sin errores).
- Compatibilidad con configs de amigos: prueba la ayuda con `config.example.yaml` de `template/` y con configs
  variadas (novato con caminatas, intermedio con picos, corredor con calidad, `variada` true/false) además de la de
  Pedro. Agrega pruebas en `tests/` para el armado de la ayuda.
- Un commit local por fase (`v4.5 F<n>: …`) con las líneas de coautoría que te pasen. Dudas a `docs/DUDAS.md`
  (sección "v4.5"); elige lo más simple y anótalo.
- Verifica cada fase con capturas en Chrome headless (~600 px de ancho y 1280 px), claro y oscuro.

## F1 — Pestaña Km en Corridas (§13.1)
- `build.py`: km por semana (lun–dom) de las corridas en el `progreso` que ya usa Volumen, si no está ya.
- `vistas.js`: pestaña **Km** en la tarjeta Corridas (mismo `barChart`, una serie, color `s1`), globito
  "Semana del … · 12.3 km", vista de tabla, respeta 4/8/12 semanas. Sin raya de plan.

## F2 — "Cómo vas mejorando" en cuadritos (§13.2)
- `build.py` / `metrics.py`: en `progreso.mejora` agrega lo que pintan los cuadritos ya calculado: ritmo actual
  (promedio de las últimas 4 corridas válidas), ritmo de inicio (semanas 1–2), diferencia en s y si mejora; última
  deriva válida (valor, fecha, ok); resultado de la prueba si existe (reusa `prueba_resultado`). Textos de "por
  qué no hay dato" desde Python.
- `app.js` (`tarjetaMejora`): sin gráficas ni frase; cuadritos con el estilo de `filaNumeros`. Verde = mejora,
  ámbar = empeora (colores de estado existentes, con flecha ▲/▼ y texto, nunca solo color). Borra `dibujarMejora`
  y lo que quede sin usar.

## F3 — "Marcas y carreras" (§13.3)
- Une `tarjetaMejoresMarcas` y `tarjetaCarreras` en una tarjeta: marcas arriba siempre; si hay carreras, debajo un
  subtítulo "Carreras" y la lista con `carreraDetalle` como hoy. Sin marcas ni carreras → la tarjeta no sale.

## F4 — Página de ayuda (§13.4)
- `build.py`: nueva clave `ayuda` en `data.json` (en la lista blanca) con bloques ya redactados para esa persona
  (p. ej. `[{titulo, parrafos: [...], lista: [...]}]`; texto plano, nada de HTML). Arma todo desde la config y el
  plan: semáforo y umbrales; las sesiones reales de su plan (nombres, cuántas por semana, cuál es la larga y en qué
  días); caminatas / picos Z3 / variada / calidad (con sus tipos) solo si aplican; solo su tipo de prueba; mejora
  (ritmo a FC ref con su lpm, deriva, esfuerzo); sus zonas con lpm. Reusa el texto actual de `tarjetaComoFunciona`
  como punto de partida, quitando lo que no aplique. Sin links a docs.
- `index.html` / `vistas.js`: botón **?** (con `aria-label="Ayuda"`) junto al botón de tema; abre la vista
  `#ayuda` (página aparte, sin pestaña abajo marcada; botón "← Volver"). Quita `tarjetaComoFunciona` de Plan.
- Pruebas: la ayuda de un novato con caminatas no menciona calidad; la de un corredor nombra sus tipos de calidad;
  cada una menciona solo su prueba; el número de sesiones sale del plan.
- Actualiza §13 de `REQUISITOS.md` a "construido, falta publicar".
