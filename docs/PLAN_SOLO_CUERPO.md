# Modo «Solo cuerpo» (acordado con Pedro, 2026-11-27)

Algunas personas solo quieren registrar sus mediciones InBody, sin entrenamiento ni Garmin.

## Decisiones
- **Quién elige:** la persona, en el onboarding (`/bienvenida`), justo después del consentimiento: «¿Qué quieres usar?»
  - **Entrenamiento con Garmin + cuerpo**: el flujo de hoy, sin cambios.
  - **Solo mediciones de cuerpo.**
- **Cuerpo se salta** el repo de GitHub, la key de Garmin y las preguntas del plan. El onboarding queda completo con
  consentimiento + uso=cuerpo (zona horaria y título usan los valores por defecto).
- **Qué ven:** solo la sección Cuerpo: evolución (peso, grasa, músculo; la vista Progreso→Cuerpo del sitio), historial y
  «Agregar medición» (`/cuerpo/nuevo`). Sin Hoy, sin Plan, sin elementos de entrenamiento/Garmin/repo en el menú.
- **Cambiar después:** en Ajustes, «Activar entrenamiento con Garmin» pasa a completo y regresa a los pasos que se
  saltó. Las mediciones se conservan.
- **Igual que antes:** acceso por invitación, el ZIP de «Mis datos», `/admin` y el coach MCP (las herramientas de
  mediciones funcionan; las de entrenamiento devuelven un `Rechazo` claro si no hay plan).
- **Sin subir fotos** por ahora.

## Fases (un agente Sonnet y un commit cada una)
### C1 «Solo cuerpo: modalidad y bienvenida»
- `Usuario.uso` (nulo = completo; «cuerpo»), con migración. Por defecto completo: las cuentas existentes no cambian.
- Onboarding: el paso de la pregunta y los saltos. `onboarding.estado`/`completo` conocen la modalidad (también el
  destino de `/instalar` tras el login).
- El cambio en Ajustes. Textos con `t()` y claves en `i18n/es.yaml` + `en.yaml`.
- Pruebas: elegir cuerpo completa el onboarding sin repo; completo no cambia; el cambio a completo lleva al paso del
  repo; las mediciones se conservan.

### C2 «Solo cuerpo: el sitio muestra solo Cuerpo»
- `/` de un usuario cuerpo muestra el sitio solo con la vista Cuerpo: `web/calculo` arma un data.json mínimo
  (cuerpo/inbody + ui + idioma, con `ui.solo_cuerpo: true`) sin datos de Garmin ni plan; el JS oculta las demás
  pestañas cuando `ui.solo_cuerpo`.
- La clave nueva lleva valor por defecto y entrada en la lista blanca (`validar.py`/pruebas).
- Sin mediciones: estado vacío amable con el botón «Agregar medición».
- Verificar con `--dump-dom` (es y en); pruebas del data.json mínimo y de que completo no cambia.

## Reglas
- Compatibilidad: valores por defecto en todo; `validar.py` en verde; no tocar reloj ni el login de Garmin.
- Si algo es ambiguo, la opción más simple, anotada en `docs/DUDAS.md` («v5 solo cuerpo»).
