# «Aprende» (acordado con Pedro, 2026-11-27)

Artículos cortos de teoría, de 2 a 3 minutos cada uno. Pedro los revisa más o menos EN LA APP y dice lo que no le gusta.

## Decisiones
- **Sección:** web `/aprende` (índice) y `/aprende/{slug}` (artículo). Jinja en el servidor con tokens y componentes del sistema de diseño. Requiere sesión, como el resto. Entrada «Aprende» en el menú de la web y en el menú del sitio (el `menu` del data.json que sirve la web), con valor por defecto.
- **Archivos de contenido:** `aprende/es/<slug>.yaml` con `titulo`, `resumen` (una línea), `minutos`, `secciones: [{titulo, parrafos, lista (opcional)}]` y `fuentes` (opcional, nombres cortos, sin ligas). Motivo: los textos largos no caben en el catálogo plano. Los textos de interfaz (títulos, botones, aviso) van en el catálogo, es + en.
- **Inglés:** se traduce después de que Pedro apruebe el español. Mientras, `/aprende` en inglés muestra el artículo en español con una nota del catálogo («Available in Spanish for now»).
- **Cierre de cada artículo:** «Esto no es consejo médico: si algo duele, para.» (`pie.consejo`).
- **Tono:** español mexicano sencillo, de «tú», frases cortas, números concretos, sin exageraciones ni modas. Solo consenso general (polarizado 80/20, ~10 % como guía, semanas de descarga…). Se dice cuándo algo es regla de dedo y no ley. Se liga con los conceptos de la app: zonas Z1–Z5, semáforo de recuperación, versión suave, trote/caminata, descarga.
- **Artículos (11, de 400 a 600 palabras):** `zonas`, `zona-2`, `long-run`, `volumen`, `semana`, `calidad`, `trote-caminata`, `fuerza`, `recuperacion`, `dolor`, `carrera`.
- **Índice:** tarjetas con título, resumen y «N min».

## Fase única: «Aprende: sección y artículos»
- Rutas, plantillas, lector (con caché), entradas de menú e i18n.
- Los 11 artículos en español.
- Pruebas: cada archivo carga con sus campos; el índice los lista; el artículo se pinta; slug desconocido da 404; requiere sesión; el slug no puede salirse de la carpeta (solo `[a-z0-9-]`).
- Dockerfile: `COPY aprende/ aprende/` (en producción ya se rompió antes por no copiar `i18n/`).
- Los enlaces contextuales («¿Por qué zona 2?») vienen DESPUÉS de que Pedro revise.

## Reglas
- Claves nuevas con valor por defecto; `validar.py` en verde; la lógica en Python; ante la duda, lo más simple, anotado en DUDAS.
