# Sistema de diseño «Ahí la Llevas» (estilo Anillo)

La fuente de verdad visual es el artifact **Design System** de Pedro
(https://claude.ai/artifact/GdNbumpxoUi28PPgwVKkCd). Esta carpeta guarda una copia de lo que el código necesita:

- `tokens.json`: colores (oscuro y claro), letra, espacios, radios y sombra. Copia exacta de `project/tokens.json`
  del artifact (versión 2, publicada el 2026-11-25).
- `iconos/*.svg`: los íconos de línea del sistema (`project/assets/Iconos`).
- La fuente Lexend vive en `site/fuentes/Lexend-latin.woff2` (`project/fonts`).

## Cómo se usa

`python scripts/tokens.py` genera `site/tokens.css` (variables, `@font-face` y clases `.t-*` de tipografía) y
`site/iconos.js`. No edites esos dos a mano: la prueba `tests/test_tokens.py` falla si no coinciden con esta carpeta,
o si algún CSS/JS usa una `var(--x)` que no existe.

## Cómo actualizar

1. Cambia el sistema en el artifact (Claude lo publica ahí primero).
2. Baja `project/tokens.json` y los SVG nuevos a esta carpeta.
3. Corre `python scripts/tokens.py` y las pruebas.
