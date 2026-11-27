# Plan: conexión con Garmin y sincronización (parte 1 de `REQUISITOS_CONEXION.md`)

Escrito el 2026-11-27. Ejecuta Sonnet, una fase = un commit (`Conexión C<n>: …`); Opus revisa por tanda, hace push y
despliega. La GitHub App ya está probada en producción; desde C12 es el único camino para vincular una copia.

## Decisiones de esta sesión

- **[acordado]** Guía de 5 pantallas + comprobación (ver abajo). La key va en **una pantalla** para que no se pierda entre
  pantallas, con tres pasos: primero el nombre en GitHub, luego la key en Garmin y al final pegarla (si se copia el
  nombre después de la key, la borra del portapapeles). **Dibujos simplificados** (SVG), no capturas. La web **detecta sola** el
  secreto al volver a la pestaña; «Ya la puse» queda de respaldo. La pantalla 0 se queda.
- **[decidido por Opus; Pedro puede cambiarlo]** Lo que seguía pendiente:
  - Todo lo marcado [propuesto] en los requisitos queda aceptado.
  - Tarjeta del primer inicio: pasa a la **parte 2** (hoy nadie llega al inicio sin pasar por la guía). En la parte 1, su
    «Mandarme la liga al correo» vive en la pantalla 0 y en el aviso de celular.
  - Ya conectados: el botón «Sincronizar» aparece para todos; sin la app autorizada, tocarlo lleva a «Autoriza una vez»
    (pantalla 3 de la guía en modo «ya conectado»). También en Ajustes → Conexiones.
  - Desconectar: en Conexiones, «Desconectar Garmin» desliga la copia y la instalación (los datos se quedan) y explica
    cómo quitar la app en GitHub. Reconectar = la guía desde la pantalla 0; si la app ya estaba instalada, GitHub
    regresa con `setup_action=update` y se acepta igual.
  - Código de 6 dígitos: con la app encendida desaparece de la guía; quien estaba a medias cae en la pantalla que le toca
    de la guía nueva. `web.cli vincular` se queda. El código viejo del servidor se borra en C12, ya probada la app.

## La guía (pantallas)

| # | Pantalla | Botón | Regreso |
|---|---|---|---|
| 0 | Antes de empezar: copia, permiso y key; unos 5 min; computadora; «tus datos viven en tu copia privada; nunca vemos tu key» | Empezar | — |
| 1 | ¿Tienes cuenta de GitHub? | «Ya tengo» / «Crear una» (otra pestaña; tip «Continue with Google» y código por correo) | «Cuando veas tu inicio de GitHub, regresa» + «Ya la tengo» |
| 2 | Tu copia | «Crear mi copia» (otra pestaña, nombre y Private puestos); «solo toca el botón verde «Create repository»» + dibujo | «Cuando veas la página de ahilallevas-datos, regresa» + «Ya la creé» |
| 3 | Danos permiso | «Dar permiso» en la **misma pestaña**; «Only select repositories» → la copia → «Install & Authorize» + dibujo | Solo |
| 4 | Tu key, en este orden (el portapapeles guarda una sola cosa): ① GitHub: abrir secretos, copiar `PERSONAL_API_KEY` y pegarlo en «Name» (dejar la pestaña abierta); ② Garmin: crear la key y copiarla; ③ regresar a GitHub: pegarla en «Secret» y «Add secret» + dibujo | — | Solo al volver a la pestaña; «Ya la puse» de respaldo |
| → | Comprobando (1 día) dentro de la página, luego el inicio con la franja del historial | — | — |

Celular: aviso arriba «Es más fácil en computadora» con [Mandarme la liga], sin bloquear. Barra de pasos arriba; la web
recuerda la pantalla. Errores con la tabla de los requisitos. Altura fija: el texto de estado y los errores tienen ranura
reservada.

## Tanda A: servidor y motor (sin cambios visibles)

- **C1. Cliente de la GitHub App** (`web/github_app.py`). Variables `GITHUB_APP_ID`, `GITHUB_APP_SLUG`,
  `GITHUB_APP_CLIENT_ID`, `GITHUB_APP_CLIENT_SECRET`, `GITHUB_APP_PRIVATE_KEY` en `Settings`; `settings.app_github`
  = todas presentes. JWT RS256 → token de instalación (caché en memoria hasta 5 min antes de vencer). Funciones: cambiar
  `code` por token de usuario (se usa solo para `GET /user/installations` y se descarta), instalaciones del usuario,
  repos de una instalación, nombres y fechas de secretos, disparar `deploy.yml` (rama por defecto), corridas recientes,
  jobs de una corrida. httpx con transporte inyectable; pruebas con `httpx.MockTransport`.
- **C2. Modelo de sincronización.** Migración Alembic: `usuarios.gh_instalacion` (int, nulo) y
  `usuarios.historial_pendiente` (bool, falso); tabla `sincronizaciones` (usuario, tipo `comprobacion|historial|normal|
  treinta|programada`, estado `esperando|corriendo|ok|error`, error, paso, hechos, total, nuevas, run_id, fechas).
  `web/sincronizar.py`: `pedir` (no duplica si hay una viva; una viva sin noticias en 15 min caduca), `actual`,
  `dias_a_pedir` (última subida ok + 7, máx. 365).
- **C3. Tubo.** `instrucciones` responde según la sincronización viva (comprobación 1 día y 1 semana de salud;
  historial 365 y 16; treinta 30; normal o programada `dias_a_pedir`), **solo si el motor dice versión ≥ 2** (si no,
  lo de hoy). `POST /api/tubo/avance` con el mismo token OIDC (usa `run_id` y `event_name` del token; `schedule` crea
  una `programada` que no se pinta). La subida buena cierra la sincronización con `nuevas`; la comprobación buena marca
  `historial_pendiente` y pide el historial.
- **C4. Motor.** `garmin_connect.py`: `--semanas-salud N` (el posicional sigue) y avisos de avance (lista con total,
  detalle i de n, salud). `scripts/subir.py`: manda versión 2, `ARGS_OK` admite lo nuevo, `avance` y `fallo` (key
  rechazada 401, sin key, otro). `motor.yml`: avisa al arrancar y un paso `if: failure()`. `deploy.yml` de Pedro: sin el
  job `pruebas`. Motor viejo + web nueva y motor nuevo + web vieja siguen funcionando (pruebas de las dos combinaciones).

## Tanda B: conexión

- **C5. Autorizar con GitHub.** `/conectar/github` (state firmado, patrón de `web/google.py`) → instalación de la app;
  `/conectar/github/vuelta` comprueba `state`, cambia `code`, verifica la instalación contra `/user/installations`,
  exige **un solo repo**, que no sea de otra persona y, si la persona ya tenía copia, que sea la misma; guarda
  instalación y vincula. Errores → la pantalla 3 con su mensaje. Nunca se guarda el token de la persona.
- **C6. Guía nueva** en `/bienvenida` (con la app encendida): pantallas 0–4, comprobación dentro de la página,
  detección del secreto (`GET /api/conexion/estado`: falta / otro nombre / listo) al volver a la pestaña, aviso de
  celular, «Mandarme la liga» (correo con `web/correo.py`). Textos en `i18n/es.yaml` y `en.yaml`.
- **C7. Dibujos** SVG simplificados: «Create repository», «Only select repositories», «Name / Secret / Add secret».
  Con los tokens del diseño (claro y oscuro), texto de GitHub en inglés y una marca.

## Tanda C: franja y botón Sincronizar

- **C8. API de sincronizar.** `POST /api/sync` (CSRF; tipo normal o treinta) dispara la corrida; `GET /api/sync`
  devuelve estado, paso, hechos/total y texto. Mientras no haya avisos del motor, se leen los jobs de la corrida; una
  corrida fallida sin aviso → error «otra falla».
- **C9. La franja.** Componente nuevo (JS sin librerías). En el sitio, mientras sincroniza, el estatus **reemplaza** a
  «Actualizado hace…» en su misma ranura, con una barra delgada al pie del encabezado (nada cambia de altura); en las
  páginas del servidor, franja fija arriba que flota sin empujar nada. Misma altura en todos los estados, no se cierra, solo visible durante una sincronización (no las programadas), retoma al abrir. Estatus de
  los requisitos. «Actualizado hace…» y su botón siempre visibles. **[acordado]** Con la app encendida solo se soporta sincronizar con la app: el lugar de «jalar datos» dice siempre «Sincronizar» (sin autorizar, lleva a autorizar una vez); la liga manual a GitHub Actions solo queda mientras la app esté apagada y se borra en C12. Al terminar, el sitio vuelve
  a pedir sus datos y repinta sin recargar. «Falta tu historial» con [Reintentar]; armar el plan espera al historial.

## Tanda D: lo demás

- **C10. Conexiones.** Estado de Garmin, «Volver a traer los últimos 30 días», «Desconectar Garmin», invitación a
  autorizar para quien ya está conectado.
- **C11. Key caducada.** Al fallar con key rechazada: aviso en el inicio + un correo por incidente → guía corta (bloque
  de la key) que detecta el secreto nuevo por su fecha → comprobación de 1 día → la siguiente normal trae lo que faltó.
- **C11b. Pasar a la app a quien está con lo viejo.** **[acordado]** Desde que la app se encienda, lo manual ya no se
  soporta. Quien está conectado sin la app ve en el inicio un aviso fijo (no se cierra hasta autorizar): «Actualiza tu
  conexión: autoriza una vez y sincroniza desde aquí» → `/conectar/github?para=conectado`. Las descargas programadas siguen
  mientras tanto.
- **C12. Limpieza y documentos.** ✅ Se quitó el código de 6 dígitos (servidor, `subir.py`, plantillas y tabla) tras probar
  la app en producción. `CLAUDE.md`, `REQUISITOS_CONEXION.md` y la plantilla indican que la GitHub App es el único vínculo.

## Lo que hace Pedro (no se puede desde aquí)

1. Registrar la app pública en GitHub (permisos `actions: write`, `secrets: read`, `metadata: read`; «Request user
   authorization during installation»; sin webhook; callback y setup URL `https://ahilallevas.com/conectar/github/vuelta`).
2. Poner sus 5 valores en Secret Manager y en `web.yml`; desplegar.
3. Mover `stable` tras la tanda A (`git tag -f stable <sha> && git push -f origin stable`).
4. Probar con su cuenta y luego con la amiga. Revisar el aviso de privacidad (cambiar su versión pide aceptarlo de nuevo).
