# Plan: entrada libre y registro a mano (parte 2, `REQUISITOS_ENTRADA.md`)

Escrito el 2026-11-27. Se ejecuta **cuando termine la parte 1** (`PLAN_CONEXION.md`, hasta C12). Sonnet ejecuta, una
fase = un commit local (`Entrada E<n>: …`); Opus revisa cada fase. **Nada se publica sin preguntarle a Pedro** (push y
`web.yml` al final de cada tanda, si él dice).

Ninguna fase toca `motor.yml`, `scripts/subir.py`, `garmin_connect.py` ni `dashboard/paquete.py`: **`stable` no se mueve**.
Los cambios en `dashboard/` y `plan/` solo corren en la web.

## Decisiones (aprobadas por Pedro el 2026-11-27)

Las propuso Opus y Pedro las aprobó todas; lo demás viene de los requisitos.

1. **[acordado] Pantalla 2 = `/perfil` la primera vez**: nombre, apellido y la casilla del aviso en un solo formulario
   (crea el `Consentimiento`). Quien ya tiene nombre pero no aceptó la versión vigente del aviso ve la misma pantalla
   con sus datos puestos. Ya no se pasa por `/bienvenida` para el aviso.
2. **[acordado] «Completo» = nombre + apellido + aviso vigente.** `/` ya no manda a `/bienvenida`; `/bienvenida` solo es
   la guía de Garmin, que se abre desde la tarjeta o desde Ajustes, aunque la persona ya tenga plan.
3. **[acordado] «No tengo Garmin»** se guarda en `avisos_ocultos` (`aviso_id = "garmin"`): no hace falta migración. La
   tarjeta sale a quien no tiene copia conectada (`repo_id` vacío) y no la quitó.
4. **[acordado] Primeros pasos** (armar plan, unirse a un grupo, agregar InBody): cada uno se va cuando ya está hecho
   (tiene plan, tiene grupo, tiene una medición). «+ Registrar actividad» es un renglón fijo arriba de Hoy que **no se
   va nunca**, también para quien tiene Garmin.
5. **[acordado] Las actividades a mano se guardan aparte** (tabla `actividades_manuales`) y la web las mete en la lista de
   actividades **con la forma de Garmin** (`activityType.typeKey`, `startTimeLocal`, `distance`, `duration`,
   `averageHR`, `manual: true`; el esfuerzo va como `rpe` en sus detalles). Así la semana, el ajuste de cada lunes,
   Progreso, Juntos y el coach (MCP) las ven sin una segunda lógica.
6. **[acordado] Tipo → categoría, fijo para las de a mano** (sin depender de la config de cada persona): Correr → corrida;
   Caminar → `caminar` (nueva); CrossFit → `hiit`; Gimnasio → `fuerza`; Bicicleta, Natación, Elíptica → `cardio`; Yoga o
   movilidad → `movilidad`; Senderismo, Deporte, Otra actividad → `otra` (nueva). Las categorías que falten en la config
   de alguien se agregan al normalizarla. **[acordado]** **Todas** las caminatas de Garmin (`walking`), sin duración
   mínima, también caen en `caminar`. Caminar no cuenta como corrida en el plan.
7. **[acordado] La nota es privada**: la ven la persona y su coach; nunca sale a grupos ni al feed. La FC sí sale como
   `fc_prom` (igual que una de Garmin).
8. **[acordado] Trote continuo (el pendiente de `plan/nivel.py`)**: una corrida a mano cuenta para el volumen (minutos y
   corridas por semana) pero **no para el trote continuo**, porque no se sabe si fue seguida o con caminatas. Sin reloj,
   el trote continuo es la respuesta de «¿cuánto dura tu corrida más larga?» y el nivel que se calcula llega **a lo más a
   «base»**; la persona puede elegir otro, con el aviso que ya existe (`pn.nivel_alto`).
9. **[acordado] «Un poco por debajo»** = 80 % de (días por semana × corrida más larga), redondeado hacia abajo a 5', con
   el piso de su nivel.
10. **[acordado] «¿Corriste? Anótalo»** aparece siempre para quien no tiene Garmin conectado, con liga al formulario
    de Correr y la fecha local de hoy. Se mantiene visible después de registrar una actividad.
11. **[acordado]** Quien está en «solo cuerpo» pasa a todos-tienen-todo con `sin_plan = True`. La columna `uso` se queda
    en la tabla (nadie la lee) para no romper respaldos; se borra en otra ocasión.

## Tanda A: entrada libre

- **E1. Registro en dos pantallas.** La pantalla 1 ya existe (`/invitacion/{token}`: Google o correo y código); solo se
  revisa que no pregunte nada más. `/perfil` la primera vez lleva la casilla del aviso (decisión 1) y al guardar va a `/`.
  `onboarding.completo` según la decisión 2; `/`, `/entrar/codigo`, Google y `oauth.destino_login` usan la regla nueva.
  Se quitan «¿Qué quieres usar?» (`/bienvenida/uso` y su plantilla) y el paso «Aviso» de la guía. Pruebas: invitación →
  perfil → inicio sin pasar por `/bienvenida`; perfil sin casilla no avanza; aviso nuevo pide aceptarlo otra vez.
- **E2. Todos tienen todo.** `calculo.config_de`: quien no tiene ajustes usa los de fábrica con `sin_plan` aunque no tenga
  copia (se quita la condición de `repo_id`). Migración 0019: `uso = 'cuerpo'` → `uso = NULL, sin_plan = true`. Se borra
  «solo cuerpo» en Python (`solo_cuerpo`, `cuerpo_sin_ajustes`, `MENU_CUERPO`), en `site/vistas.js`, en Ajustes
  (`/ajustes/uso`, `ajustes_cuerpo.html`) y en la tabla de `/admin`. **Estados vacíos**: con cero datos (sin Garmin, sin
  InBody), cada sección de Hoy, Progreso y Ajustes dice cómo llenarse; `build.build` no truena con datos vacíos (prueba).
  Prueba con una persona de «solo cuerpo» migrada: conserva sus mediciones y ve todo lo demás.
- **E3. Primer inicio.** En Hoy, de arriba a abajo: tarjeta de Garmin (texto acordado; [Conectar] abre la guía de la parte
  1, «Mandarme la liga» reutiliza el correo de la parte 1, «No tengo Garmin» la quita), «+ Registrar actividad» (lleva al
  formulario de E5; por eso E3 se hace después de E5, ver «Orden»), y los primeros pasos (decisión 4; InBody abre `/cuerpo`). Python decide qué se muestra (`ui.primer_inicio`, con
  valores por defecto en el sitio); el JS solo pinta, con ranuras reservadas (quitar la tarjeta no mueve lo de abajo
  de forma brusca: colapsa, no cambia de altura al elegir). `guia_activa` ya no exige «sin ajustes». En Ajustes →
  Conexiones, «Conectar Garmin» siempre que no esté conectado. Textos en `i18n/es.yaml` y `en.yaml`.

## Tanda B: registro a mano

- **E4. Modelo y motor.** Migración 0020: tabla `actividades_manuales` (usuario, fecha, tipo, distancia_m, duracion_s,
  esfuerzo 1–10, fc_prom, nota ≤ 280, creada, actualizada). `web/manual.py`: tabla de tipos (unidad de distancia u
  oculta, obligatorios), validación y `a_actividad` (decisión 5; `id = "m<id>"`, `startTimeLocal` = la fecha a mediodía).
  `calculo.datos_de` las agrega; la huella de la caché cuenta sus filas y su última fecha. `metrics.classify` usa el mapa
  fijo (decisión 6) para `manual: true`; `normalizar_config` agrega `caminar` y `otra` si faltan; `unir_encadenadas` no
  junta las de a mano; todas las caminatas de Garmin van a `caminar` (sin umbral de duración). `validar` admite `manual` en las filas. `cuenta.py`: «Mis datos» las incluye y borrar la cuenta
  las borra. Pruebas: cuenta en la semana, en `ajustar_semana` (real_prev) y en la tarjeta del grupo; una de Garmin y una
  a mano el mismo día no se juntan.
- **E5. Formulario.** `GET/POST /actividad/nueva` (`?tipo=&fecha=` opcionales), `GET/POST /actividad/{id}` (editar) y
  `POST /actividad/{id}/borrar`; también bajo `/a/<id>` para el coach (`permisos.puede_editar`); CSRF en todo POST. Una
  pantalla: tipo (botones Correr preseleccionado, Caminar, CrossFit, Gimnasio, Otra → lista), fecha (hoy, en su zona
  horaria; no futura), distancia (km o metros según el tipo; oculta con su espacio guardado), tiempo (h:mm:ss o mm:ss),
  esfuerzo opcional y «+ Más» (FC promedio y nota; expandir sí puede crecer). Obligatorios según los requisitos; el ritmo
  lo calcula Python y sale en la fila de la actividad. Al guardar → `/#hoy`.
- **E6. En el sitio.** En el detalle del día, la fila de una actividad a mano lleva la marca «a mano» y «Editar» (`ui.editar_manual`, ruta
  por actividad; el coach ve la suya con prefijo). Subir la versión de la caché del service worker.

## Tanda C: grupos

- **E7. Grupos con o sin Garmin.** `web/grupos.py`: se quitan los rechazos de «cuerpo» (y su estado en
  `grupo_unirse.html`). `grupos_resumen`: la tarjeta «libre» (km y días, sin comparación) ya no exige `repo_id`. Feed:
  la fila trae `manual` y Juntos pinta «a mano»; reacciones y comentarios igual (si se edita el tiempo, la clave cambia y
  sus reacciones se quedan atrás, como con Garmin). La nota nunca sale (`CAMPOS_DETALLE` no la tiene; prueba). Prueba
  de un grupo con una persona con Garmin y otra sin.

## Tanda D: plan sin reloj

### Guía de ejecución para Terra

1. **Hoy al estrenar la cuenta.** En el cálculo web, distinguir copia conectada, permiso para sincronizar, última subida exitosa e historial pendiente. La ausencia de actividades por sí sola no demuestra una sincronización. En Hoy comprobar cuatro casos con el reloj de la prueba fijo: cuenta vacía, primera actividad manual, primera comprobación real e historial listo. La cuenta vacía ofrece registrar y conectar. La actividad manual aparece en el calendario y resumen. Mostrar instrucciones de FC de Garmin solo cuando corresponda y usar la fecha de la última subida para el encabezado. Conservar la acción de autorizar para copias antiguas.
2. **Interacción de conexión.** Junto al envío por correo explicar «¿Estás en celular? Necesitas una computadora para conectar Garmin» y etiquetar la acción «Enviarme la guía por correo». Al pulsar Sincronizar, bloquear inmediatamente otro envío y anunciar la solicitud en la misma ranura. Transferir el estado al progreso real. Recuperar el botón ante rechazo, pérdida de red o fin de la corrida. Probar doble clic con una respuesta demorada y reintento tras error.
3. **E8.** Combinar actividades guardadas y manuales para medir volumen. Detectar corridas de Garmin dentro de la ventana del motor y respetar la espera de historial. Sin ellas, preguntar frecuencia actual (1–7) y minutos de la corrida más larga. Aplicar las decisiones 8 y 9 en Python, mantener las respuestas al avanzar, volver y confirmar, también para coach. Probar que 3 días × 31 minutos dan 70 minutos iniciales, el piso del nivel y la elección de un nivel superior con aviso. Agregar una persona sin reloj al simulador.
4. **E9.** Compartir la descripción de esfuerzo por zona entre los pasos de sesión de Hoy y Plan en español e inglés. Incluir el rango solo con zonas reales de Garmin. Comparar una misma sesión con y sin zonas, revisar el cambio esperado en los datos golden y comprobar que una cuenta con reloj conserva sus rangos.
5. **E10.** Si puede editar y no tiene Garmin, enlazar siempre desde Hoy y Plan al formulario con Correr y la fecha local de hoy. Comprobar también cuentas sin plan, coach sin permiso y atleta conectado. Verificar que el lunes el ajuste responda al volumen manual real.
6. **Revisión.** Ejecutar las pruebas de cada fase, el simulador, pytest completo y el validador de privacidad. Revisar el diff y recorrer el alta hasta registrar la primera corrida. Documentar cualquier comprobación que el entorno impida. La entrega de esta tanda es local para revisión de Pedro.

- **E8. Preguntas sin historial.** `/plan/nuevo` paso 1: si no hay corridas de Garmin en las semanas que mira
  `nivel.py`, en lugar de «Lo que vimos en tu Garmin» pregunta días por semana (1–7) y corrida más larga (minutos).
  `nivel.py`: entrada nueva con esas respuestas (decisiones 8 y 9); las corridas a mano cuentan para el volumen y no para
  el trote continuo. Quien está conectado sigue esperando su historial como hoy. Persona «sin reloj» en
  `plan/personas.yaml`; el simulador y sus pruebas pasan.
- **E9. Zonas por sensación.** Cada «Zona N» del plan y de Hoy lleva además su descripción («suave: puedes platicar sin
  cortarte», etc., textos en i18n). Sin zonas de Garmin, solo el nombre y la descripción (sin rango de FC). Golden de
  build actualizado.
- **E10. «¿Corriste? Anótalo».** El recordatorio de la decisión 10 en Hoy/Plan (Python decide; el JS pinta en una ranura
  reservada). Prueba de que una semana sin corridas a mano baja la carga del lunes siguiente (`ajustar_semana`) y que
  anotarlas la mantiene.
- **E11. Documentos.** `CLAUDE.md` (registro, registro a mano, sin «solo cuerpo»), `REQUISITOS_ENTRADA.md` marcado
  hecho con las decisiones de arriba, `docs/DUDAS.md`.

## Orden y revisión

E1 → E2 → E4 → E5 → E3 → E6 → E7 → E8 → E9 → E10 → E11 (E3 va después de E5 para que el «+» del primer inicio ya lleve
al formulario). En cada fase: un agente Sonnet nuevo, `.venv/bin/python -m pytest -q` y `dashboard/validar.py` en verde,
commit local; Opus revisa el diff antes de la siguiente. Al terminar cada tanda, Opus pregunta a Pedro si publica.

## Lo que hace Pedro

1. Aprobar las decisiones (hecho el 2026-11-27).
2. Decir cuándo publicar cada tanda y probar con una cuenta sin Garmin (la invitación la crea el admin).
3. Si cambia el texto del aviso de privacidad por los datos de salud anotados a mano, subir su versión (pide aceptarlo
   de nuevo a todos).
