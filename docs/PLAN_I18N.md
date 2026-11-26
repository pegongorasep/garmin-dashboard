# Español e inglés con un catálogo de textos (acordado con Pedro 2026-11-26)

## Decisiones
- **Alcance:** todo: pantallas de la web, el dashboard (Hoy/Plan/Progreso), correos y los textos que arma Python
  (notas del plan, avisos). **No** el conector de IA (MCP): sigue en español.
- **Elección de idioma:** la primera vez, el del navegador o teléfono (`Accept-Language`, o `navigator.language` en Pages).
  Se cambia en Ajustes y se guarda en la cuenta (`Usuario.idioma`, nulo, migración). Sin sesión, cookie `idioma`.
  Por defecto y respaldo: `es`. Prioridad: cuenta > cookie > navegador > es.
- **Catálogo** (como strings.xml): `i18n/es.yaml` y `i18n/en.yaml` en la raíz (los comparten el motor y la web).
  Claves planas con puntos (`hoy.titulo`, `entrar.boton_codigo`) y variables `{nombre}`. `es` es la referencia;
  una prueba revisa que ambos tengan las mismas claves y las mismas `{variables}`.
- **Python:** `dashboard/i18n.py` con `t(clave, idioma="es", **vars)`, `idiomas()` y `cargar()` (con caché).
  Una clave ausente cae a `es`; en pruebas lanza error.
- **Web:** `t` disponible en las plantillas, ya ligada al idioma de la petición (`request.state.idioma`); `<html lang>`;
  correos en el idioma de la persona.
- **JS del sitio:** el build escribe `site/i18n/es.json` y `site/i18n/en.json` (solo claves `sitio.`);
  data.json lleva `idioma` (por defecto "es", en la lista blanca); `base.js` expone `T(clave, vars)`; el JS solo pinta.
- **Páginas de amigos:** clave de config `idioma` (por defecto "es" en defaults.yaml); si no la pusieron, el sitio usa `navigator.language`.
- **Textos guardados en plan.json:** gen_plan escribe también `nombre_id` / `nota_id` (+ `vars`), opcionales; el build
  traduce cuando hay id y, sin id (planes viejos o texto libre), muestra el original. Compatible con planes viejos.
- El español queda exactamente como hoy; el inglés es natural y corto (términos de correr/fitness: "Long run", "Easy run").

## Fases (un agente Sonnet y un commit cada una, en orden)
- **I1 «Idiomas: catálogo y web (sistema)»:** `i18n/`, `dashboard/i18n.py` y pruebas del catálogo; `Usuario.idioma` + migración;
  elección de idioma en un middleware; global `t` de Jinja; selector en Ajustes; pasar al catálogo `base.html`, `entrar`,
  `invitacion`, `_codigo`, `instalar`, `mensaje` y los correos de entrada.
- **I2 «Idiomas: resto de la web»:** las demás plantillas de `web/plantillas/` (onboarding, formularios del plan, admin,
  mis datos, conexiones, ayuda) y los textos para el usuario en `web/*.py` (errores de formularios, avisos). No el MCP.
- **I3 «Idiomas: sitio (Hoy/Plan/Progreso)»:** `site/*.js` e `index.html` a `T()`; el build escribe `site/i18n/*.json`;
  `idioma` en data.json con entrada en la lista blanca; el catálogo en `/diseno`. Revisar con `--dump-dom` en es y en.
- **I4 «Idiomas: textos del plan y del cálculo»:** las cadenas que dashboard/ y plan/ meten en data.json (avisos, nombres
  de zonas, etiquetas, notas generadas); `nombre_id`/`nota_id` en gen_plan; el build/web pasa el idioma.
  Prueba: data.json en en no trae cadenas conocidas en español.
- **I5 «Idiomas: repaso del inglés y prueba anti-español»:** leer todo `en.yaml` y dejarlo natural y consistente; una prueba que
  busque texto literal en español fuera del catálogo en plantillas/JS (heurística: acentos/ñ/¿¡ en literales), con lista de excepciones.

## Reglas
- Compatibilidad: toda clave nueva lleva valor por defecto.
- `validar.py` y la lista blanca siguen en verde.
- No tocar el login del reloj ni de Garmin.
- Ante una duda, la opción más simple, anotada en `docs/DUDAS.md` (sección «v5 idiomas»).
