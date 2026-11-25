# Plan: sistema de diseño «Anillo» en Ahí la Llevas

Fecha: 2026-11-25. Pausa la tanda C de [`PLAN_V5.md`](PLAN_V5.md): esto va primero, así las páginas de la tanda C
nacen con el diseño.

Fuente: el sistema de diseño de Pedro, https://claude.ai/artifact/GdNbumpxoUi28PPgwVKkCd (estilo Anillo: Lexend,
fondo azul pizarra, verde de Z2 como acento, oscuro por defecto; tokens, README y 11 componentes).

Orden (lo pidió Pedro): **células** (tokens: color, tipografía, espacio, radios, sombras, íconos) → **componentes**
(hechos solo con células) → **pantallas** (hechas solo con componentes).

## Decisiones (Pedro, 2026-11-25)

| Tema | Decisión |
|---|---|
| Fuente de verdad | **El artifact del sistema de diseño.** Lo que falta se diseña primero ahí, Pedro lo revisa, y solo después se programa. El repo guarda una copia fija de `tokens.json` y se actualiza a propósito. |
| Navegación | **Un solo Plan.** La pestaña Plan del dashboard trae los botones del plan vivo (carrera, viaje, enfermo, repetir, escalón) y «Editar» en cada sesión. Ajustes, Historial, InBody, Privacidad y Salir van en un **menú ☰ arriba**. Abajo siguen 3 pestañas (Hoy · Plan · Progreso). La página `/plan` aparte desaparece. |
| Amigos en GitHub Pages | Reciben el diseño nuevo igual (mismo `site/`). En Pages no hay menú ☰ ni botones de plan (no hay web), como hoy. |
| Tipografía | Lexend **guardada en la app** (archivos woff2 400/600/700 en el sistema y en `site/`), sin pedirla a Google. |

## Lo que le falta al sistema (inventario contra la app actual)

**Células**
- Colores que la app usa y el sistema no tiene: `axis` (ejes de gráficas), categorías de actividad para la carga
  semanal (`cat-1`…`cat-4`, hoy azul, aqua, violeta y amarillo), `sin-dato` (días sin dato en gráficas y calendario).
- Archivos de la fuente Lexend (`fonts/`).
- Íconos como archivos: los 8 de actividad (correr, medalla, mancuerna, rayo, bici, nadar, caminar, yoga) y los de
  interfaz: menú ☰, ayuda ?, tema ☀/☾, editar, cerrar, flecha, copiar, deshacer, check.
- Notas de tamaño de pantalla (700 px y 900 px) y de movimiento (150 ms) en el README.

**Componentes que faltan** (todos los usa hoy la app o la web):

| Grupo | Componentes |
|---|---|
| Controles | Botón (principal, secundario, peligro, deshabilitado, cargando), Campo (texto, número, fecha, lista, ayuda y error), Casilla y opción, Chip (formalizar), Copiar (texto + botón) |
| Navegación | Encabezado (logo, «actualizado hace…», ?, tema, ☰), Menú (el desplegable del ☰), Pestañas secundarias (Corridas · Km · Cuerpo; 4 · 8 · 12 semanas), Desplegable («Ver pasos», semanas del plan), Pasos (el avance del onboarding) |
| Datos | Silueta de varias zonas (con minutos, lpm y leyenda), FilaSesion (sesión cerrada con silueta y «Editar»), BarraTroteCaminata, Gráfica (barras, barras apiladas y línea: ejes, rejilla, leyenda y tooltip, con las reglas de `dataviz`), Tabla (con scroll lateral), Ranking (marcas y carreras), Señales (recuperación: HRV, FC en reposo, sueño), HojaInBody (barras con rango normal y puntuación) |
| Contenedores | BannerCambio («Pedro cambió tu semana 7 · Ver · Deshacer»), FilaHistorial, EstadoVacío, Formulario (grupos de campos), Confirmación (para acciones peligrosas), Pie (aviso de privacidad y «Datos de Garmin») |
| Marca | Ícono de la app y favicon ya existen; falta la pantalla de error de carga (Cargando con mensaje) |

---

## D0 — Completar el sistema de diseño 🔍 (Opus, en el artifact; Pedro revisa)

Se trabaja en el artifact, por grupos, con una revisión de Pedro al cerrar cada grupo:

- **D0a, células**: los colores que faltan (validados con el script de `dataviz` en los dos temas, contraste ≥ 4.5:1
  en texto), la fuente Lexend como archivos, los íconos como archivos (mismo trazo de 1.75 px) y las notas del
  README. Se marca el ✓ blanco sobre `ok` (3.3:1) como pendiente si Pedro quiere cambiarlo.
- **D0b, controles y navegación**: README y preview de cada componente, en los dos temas. Se adelanta
  **Graficas** (pedido de Pedro): siluetas de una zona, pirámide y muchos intervalos (las repeticiones se juntan en
  un corchete «10 × 1′ Z5 + 1′ Z1»), barras sencillas y apiladas por semana (sin datos, meta) y línea de tendencia,
  con las reglas de `dataviz` (marcas finas, una sola escala, leyenda con 2 o más series, tooltip).
- **D0c, datos y contenedores**: igual, con el resto de los componentes de datos.
- **D0d, pantallas como guía**: una sección del README por pantalla (Hoy, Plan, Progreso, Ayuda, Entrar, Bienvenida,
  Ajustes, Historial, InBody) que dice qué componentes lleva y en qué orden. No son componentes nuevos.

Pedro aprueba D0 → empieza el código.

## D1 — Células en código 🤖 (Sonnet)

1. `diseno/tokens.json` = copia exacta del sistema (Opus la baja del artifact). `diseno/LEEME.md` dice de qué
   versión es y cómo actualizarla.
2. `scripts/tokens.py` genera `site/tokens.css`: variables para los dos temas (`oscuro` por defecto en
   `:root`, `claro` con `[data-theme="light"]` y `prefers-color-scheme`, como hoy), clases de tipografía
   (`.t-titular`, `.t-cuerpo`, …), espaciado y radios. Prueba: el `tokens.css` del repo es igual al que genera el
   script; toda `var(--x)` usada en CSS o JS existe en los tokens.
3. Fuente: `site/fuentes/Lexend-{400,600,700}.woff2` con `@font-face` (`font-display: swap`) y respaldo del sistema.
4. Íconos: `site/iconos.js` toma los SVG del sistema (mismos nombres de hoy y los nuevos). `validar.py` acepta los
   nombres nuevos.
5. Renombrar variables viejas a las del sistema (`--ok-ink` → `--on-ok`, `--s1` → `--serie-1`, `--walk` →
   `--caminata`, `--focus` sigue, etc.). Las páginas Jinja de la web cargan el mismo `tokens.css` y la base;
   `web/estaticos/web.css` se reduce a lo que no sea componente.

## D2 — Componentes en código 🤖

1. `site/componentes.css`: un bloque por componente del sistema, con los mismos nombres de clase que su preview, y
   solo `var(--token)` (prueba: ningún color, tamaño de letra ni radio sueltos fuera de `tokens.css`).
2. `site/componentes.js`: una función por componente (`tarjeta()`, `aviso()`, `barraZonas()`, `silueta()`,
   `grafica()`, …) que arma el HTML; `vistas.js` y `app.js` solo las llaman. El JS solo pinta.
3. `web/plantillas/componentes.html`: macros Jinja con el mismo HTML para las páginas de la web (botón, campo,
   aviso, tarjeta, pasos, confirmación, pie…).
4. **Sección «Sistema de diseño»** (pedido de Pedro: poder entrar siempre a ver cómo se ve todo):
   `site/catalogo.html` con todos los componentes y datos de ejemplo, usando las mismas funciones de
   `componentes.js` que la app (no copias). Arriba, un botón para cambiar entre oscuro y claro. Incluye la sección
   **Gráficas** con todos los ejemplos del componente (siluetas con muchos intervalos, barras, línea).
   - En la web: `/diseno`, solo para el admin (Pedro), con liga en el menú ☰ («Sistema de diseño»). A cualquier
     otra persona le responde 404.
   - En local: `./run_local.sh` lo sirve en `http://localhost:8000/catalogo.html`.
   - En las Pages de los amigos no se publica.
   - Prueba: cada componente del sistema tiene su bloque en `componentes.css` y su ejemplo en el catálogo; `/diseno`
     da 404 a quien no es admin.

## D3 — Pantallas 🤖

1. **Hoy, Plan, Progreso y Ayuda** rehechas con los componentes; estructura y datos iguales que hoy.
2. **Encabezado**: logo + «actualizado hace…» + ? + tema; en la web también ☰ con el Menú (Ajustes, Historial,
   InBody, Privacidad, Salir, y Coach y Admin cuando existan). `ui.menu` pasa a llevar esos destinos.
3. **Plan unido** (solo en la web): la pestaña Plan muestra los botones del plan vivo y «Editar» en cada sesión.
   Nuevo en `data.json`: `ui.plan_acciones` (lista de `{texto, url}`, default `[]`; en Pages vacío) y
   `ui.editar_sesion` (bool, default `false`). Los botones abren las mismas páginas/formularios de hoy (carrera,
   viaje, enfermo, editor de sesión), ya con el diseño nuevo. `/plan` redirige a `/#plan`.
4. **Cargando**: la pantalla del logo armándose mientras llega `data.json`; si falla, el mensaje de error.
5. **Páginas de la web** con macros: entrar, invitación, liga, bienvenida (con Pasos y Copiar), ajustes, confirmar,
   historial, InBody, privacidad, mensaje, salir y los formularios del plan.
6. Regla de oro: el `data.json` de Pedro no cambia salvo las claves nuevas de `ui`. `validar.py` y pruebas al día.
7. Capturas automáticas (Chrome sin ventana) de cada pantalla a 390 px y 1280 px, en oscuro y claro, en
   `<scratchpad>/capturas/` para la revisión de Opus.

## D4 — Revisión y publicación 🔍 (Opus)

Revisa capturas y catálogo, push, despliega la web y Pages, Pedro lo prueba en su celular, se mueve `stable`
(los amigos reciben el diseño) y se sincroniza la plantilla si cambió `template/`. Después sigue la tanda C, cuyas
páginas (coach, conexiones, privacidad, admin, consentimiento OAuth) se hacen con estos componentes.
