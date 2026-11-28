# Plan: estados vacíos y animaciones (2026-11-28)

**Estado: aprobado por Pedro el 2026-11-28; construido (A1 a A5).**

Muestra aprobada (referencia visual): https://claude.ai/artifact/LRpjoz5N1p4KgTWHRmMig2
Cada animación responde a un momento: **vacío** (se anima una vez por apertura de la app y por pantalla), **espera**
(se repite hasta que llegan los datos) o **logro** (una sola vez).

De la muestra salen los dibujos, tiempos y curvas: leer con la herramienta Artifact los archivos `project/ahi.css` y
`project/{Main,Progreso,Plan,Juntos,Cumplida}.dc.html`. Los botones punteados son solo de la muestra. Donde la muestra y
este plan difieran (tarjeta compacta de Hoy, nombre «Grupos»), manda el plan.

## Decisiones de Pedro

1. Las cuatro pestañas quedan fijas: Hoy, Plan, Progreso y la de grupos. Plan y grupos muestran su estado vacío.
2. Las 5 barras del logo son los primeros pasos: cuenta, Garmin, plan, grupo, InBody. Todo paso (menos cuenta) se puede saltar.
3. La pestaña de grupos se llama **«Grupos»** / «Groups» (antes «Juntos»). Solo cambia el texto visible (la pestaña,
   «← Juntos» y «Alguien de Juntos»; «Juntos llevan {km} km» se queda). Las rutas `#juntos` y `/api/juntos` se quedan.

## Reglas para todas las fases

- Python decide el estado y las ligas (`ui.*`); el JS solo pinta. Sin la clave nueva, el sitio se ve como hoy.
- Sin librerías: SVG y CSS. Colores solo de `tokens.css`. Todo lo animado va dentro de `prefers-reduced-motion: no-preference`;
  el estado en reposo es el final.
- Altura fija: el dibujo reserva su caja; ninguna animación mueve contenido.
- Textos en `i18n/es.yaml` y `en.yaml`; correr el build para `site/i18n/*.json`.
- Archivo nuevo de `site/` y `VERSION` de `sw.js`: receta de AGENTS.md.
- Sin scripts dentro del HTML (trabajo de CSP en curso en `main`): los ejemplos del catálogo van en `site/catalogo.js`.
- Se construye en la rama `animaciones` (worktree aparte). Antes de publicar cada fase: `git rebase main`, resolver
  `VERSION` de `sw.js` (la siguiente a la de `main`), regenerar `site/i18n/*.json` y repetir las pruebas.
- Vista de coach (`ui.coach`): sin pestaña de grupos, sin barras y sin celebración; los botones de plan y registro
  solo si puede editar, con su prefijo `/a/<id>`.
- No toca archivos de `stable` ni la base (los pasos saltados usan `avisos_ocultos`).
- Una fase = un commit `Animaciones A<n>: …`, pruebas en verde (`.venv/bin/python -m pytest -q -n auto`), publicar por fase.

## Textos (es; el inglés dice lo mismo)

| Momento | Título | Texto | Botón (y liga secundaria) |
|---|---|---|---|
| Hoy, falta Garmin | Conecta tu Garmin | Tus corridas y tu sueño llegan solos. Necesitas una computadora. | Conectar · Enviarme la guía por correo (No tengo Garmin) |
| Hoy, llega el historial | Estamos trayendo tu último año | Puedes cerrar la app. Esto sigue solo. | — |
| Hoy compacta | N de 5 · Sigue: {paso} | — | según el paso (Saltar) |
| Progreso, sin Garmin | Aquí vas a ver cómo avanzas | Con tus corridas aparecen tus ritmos, tu volumen y tu intensidad. | Conectar Garmin (Registrar una corrida) |
| Progreso, esperando | Tu historial viene en camino | En cuanto llegue, aquí aparecen tus gráficas. | — |
| Progreso, sin corridas | Falta tu primera corrida | Sal a correr y sincroniza. O anótala a mano. | Registrar una corrida |
| Plan, sin plan | Tu plan empieza aquí | Contesta unas preguntas y te armamos las semanas según lo que ya corres. | Armar mi plan |
| Plan, esperando | Tu plan empieza aquí | Para armarlo a tu medida esperamos a que llegue tu historial. | Esperando tu historial… (deshabilitado) |
| Grupos, sin grupo | Entrena con tu gente | Arma un grupo, o abre la liga que te mandaron. | Crear un grupo |
| Grupos, sin actividad | Tu grupo está listo | Aquí aparecerá lo que entrenen. Invita a quien ya tiene cuenta. | Crear liga de invitación |

La gráfica de Progreso siempre lleva la palabra «Ejemplo».

## Fases

**A1. Pestañas fijas y nombre** (`site/vistas.js` `tabsDef` y `mostrarVista`, `site/vista_grupo.js`, `site/vista_plan.js`)
- Plan siempre visible; grupos siempre visible en la web propia (hoy exige `nGrupos() > 0`).
- Grupos sin ningún grupo: solo estado vacío «Entrena con tu gente», botón «Crear un grupo» (`/grupos/nuevo`) y la línea
  «o abre la liga que te mandaron». Sin pedir el feed ni «nuevo».
- Con grupo y feed vacío: botón «Crear liga de invitación» a `/grupos/<id>` (con varios grupos, a `/grupos`); el texto aclara
  que es para quien ya tiene cuenta.
- Agregar este plan a `docs/README.md`.
- Pruebas: `tests/test_web_grupos.py`, `test_web_sin_plan.py`, `test_i18n.py`.

**A2. Dibujos: Plan y grupos**
- `site/arte.js` nuevo (barras, gráfica, anillo, personas) y `DS.estadoVacio` acepta `arte` y una acción secundaria;
  ejemplos en `catalogo.html`.
- Plan: sin plan («Armar mi plan») y esperando historial (botón deshabilitado, anillo en espera). Al volver de crear el plan
  (`?ok=plan`) entran una vez el anillo real y las semanas.

**A3. Progreso**
- Python: `ui.vacios.progreso = {estado: "sin_garmin"|"esperando"|"sin_corridas", conectar, registrar}`.
- Sin Garmin (o saltado: solo registrar), esperando (gráfica en bucle, sin botón), sin corridas (registrar). Se va el texto
  que pide conectar a quien ya conectó.
- Pruebas: los tres estados y el coach sin permiso, en `tests/test_web_primer_inicio.py` o un archivo propio.

**A4. Hoy: primeros pasos con barras** (`web/primer_inicio.py`, `primerInicio` en `site/app.js`)
- `primer_inicio` da los 5 pasos con `hecho` (cumplido o saltado), url y el siguiente. Saltar: `avisos_ocultos` con
  `garmin` (ya existe), `paso_plan`, `paso_grupo`, `paso_inbody`.
- Barras encendidas = número de pasos hechos. Botón principal = siguiente paso, en orden Garmin, plan, grupo, InBody
  (plan espera si falta el historial). Garmin conserva «Enviarme la guía» y «No tengo Garmin».
- La tarjeta se queda mientras falte cualquier paso. Grande mientras falte Garmin (o llegue el historial); después,
  compacta: barras chicas, «N de 5 · Sigue: <paso>», botón del siguiente paso y «Saltar», con altura fija. Cada paso
  cumplido o saltado enciende su barra una vez. Con 5/5 las barras brincan una vez y la tarjeta se va.
- Historial en camino: las barras se arman en bucle. Sin datos aún: ocultar las tarjetas vacías de semana y recuperación.
- «+ Registrar actividad» se queda. En la vista de coach se queda la lista «Primeros pasos» de hoy, sin barras.
- Pruebas (`tests/test_web_primer_inicio.py`): orden del siguiente paso, saltar cada uno, 5/5 sin tarjeta, plan esperando
  historial, y una cuenta que ya existe con pasos pendientes (ve la compacta).

**A5. Sesión cumplida** (`tarjetaEstaSemana`, `recargarDatos`)
- El teléfono guarda (localStorage) semana, ids de sesiones hechas y % de minutos vistos. Si hay una hecha nueva: el anillo
  (mide **minutos**) avanza del % anterior al nuevo, se llena el día y se dibuja la palomita. Semana completa: dos ondas y
  brinca el logo.
- No sale la primera vez, ni en otra semana que la actual; si Hoy no está a la vista, espera a que se abra. Reemplaza a la
  animación de entrada del anillo esa vez. Sin texto nuevo.

## Fuera de este plan

Siluetas de carga y transición entre pestañas.

## Verificar al final

Cuenta nueva en `./run_web.sh --temporal`, en celular, claro y oscuro, con «reducir movimiento» activado y apagado.
