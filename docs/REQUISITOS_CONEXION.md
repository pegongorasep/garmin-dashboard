# Requisitos: conexión con Garmin, sincronización y entrada libre

Escrito el 2026-11-27. Parte 1 construida y probada en producción: la GitHub App vincula la copia y arranca las
sincronizaciones. El código de seis dígitos se retiró en C12.

Marcas: **[acordado]** lo decidió Pedro · **[propuesto]** se le propuso y falta que lo confirme · **[pendiente]** sin hablar.

## Por qué

- Una amiga se atoró conectando su Garmin: en GitHub, en «Run workflow», sin saber cuándo regresar ni cuándo acababa.
- Entrar a la app no debería exigir nada; Garmin, InBody y lo demás se agregan después.

## Alcance

1. **Parte 1: conexión y sincronización** (se planea primero; no depende de la parte 2).
2. **Parte 2: entrada libre** (registro sin pedir nada, registro a mano, grupos, plan sin reloj).

---

# Parte 1: conexión y sincronización

## Reglas

- **[acordado]** A la app se entra solo con correo o Google. GitHub aparece únicamente al conectar Garmin.
- **[acordado]** La web nunca recibe ni guarda la key de Garmin (políticas de Garmin ya revisadas).
- **[acordado]** Cada persona crea su propia copia (crearla por ella exigiría permiso de administración).
- **[acordado]** La persona autoriza a Ahí la Llevas en GitHub (GitHub App) y la web arranca la corrida y muestra el avance.
- **[propuesto]** Quien ya está conectado sigue igual; para tener el botón de sincronizar autoriza una vez.
- **[propuesto]** Las 3 descargas programadas al día se conservan y no muestran la franja.

## Flujo de conexión

| Paso | Dónde | La persona | La app |
|---|---|---|---|
| 1. Cuenta | GitHub | La crea, si no tiene | Explica que sirve Google |
| 2. Copia | GitHub | Toca «Create repository» | Da el botón |
| 3. Autorizar | GitHub | Elige solo su copia | Comprueba que la instalación sea suya y la copia correcta |
| 4. Key | Garmin y GitHub | La crea y la pega | Da las dos ligas y el nombre para copiar |
| 5. «Ya la puse» | Ahí la Llevas | Espera | Revisa el nombre del secreto y baja 1 día |
| 6. Conectado | Ahí la Llevas | Usa la app | Arranca sola la descarga de historial |
| 7. Historial listo | Ahí la Llevas | Puede armar su plan | Aviso dentro de la app, **sin correo** |

- **[acordado]** La comprobación baja solo **1 día**. Ya conectada, otra corrida trae **365 días de actividades** (sueño y
  recuperación: 16 semanas, como hoy) y la persona cae en el inicio con la franja de sincronización.
- **[propuesto]** Armar el plan se activa cuando llega el historial.
- Con esto sobran: escribir el usuario de GitHub, buscar «Actions», el código de 6 dígitos y la segunda corrida manual.

### Errores [propuesto]

| Problema | Mensaje | Botón |
|---|---|---|
| No eligió su copia, o eligió de más | «Elige solo tu copia ahilallevas-datos» | Cambiar acceso |
| No está la key | «Todavía no veo tu key» | Ponerla |
| Nombre mal escrito | «Se llama X y debe ser PERSONAL_API_KEY» | Corregirlo |
| Garmin la rechaza | «Garmin rechazó tu key. Crea otra» | Ir a Garmin |
| Otra falla | «No pudimos bajar tus datos» | Intentar otra vez |
| Falla el historial | Sigue conectada: «Falta tu historial» | Reintentar |

## Franja de sincronización (componente nuevo)

- **[acordado]** No es un diálogo: franja fija hasta arriba, no estorba y no se puede cerrar.
- **[acordado]** En reposo todo queda como hoy. Solo mientras sincroniza se ve en **todas** las pantallas (incluidas las
  páginas del servidor como Ajustes, Historial y Cuerpo, que no muestran «Actualizado hace…»).
- **[acordado]** Botón «Sincronizar» junto a «Actualizado hace…» (hoy ahí está la liga «jalar datos» hacia GitHub,
  `site/vistas.js`, `pintarEncabezado`).
- **[acordado]** Solo manual: no arranca al abrir la app. Excepción: al conectar Garmin (comprobación e historial).
- **[acordado]** Barra con progreso real y estatus llamativos. En el historial dice que baja 365 días.
- **[propuesto]** Flota fija para que nada brinque; misma altura en todos los estados; al terminar los números se
  actualizan sin recargar; al volver a abrir la app muestra por dónde va; si ya hay una corrida no se duplica; en error
  dice por qué y qué tocar.

### Estatus [propuesto]

Cada texto corresponde a algo que de verdad está pasando.

| Momento | Mensaje |
|---|---|
| Arranca | Despertando tu sincronización… |
| Prepara | Calentando motores… |
| Busca | Buscando actividades en tu Garmin… |
| Encuentra | Encontramos 12 actividades |
| Baja detalles | Bajando tus kilómetros · 5 de 12 |
| Salud | Revisando tu sueño y recuperación… |
| Sube y calcula | Haciendo cuentas… |
| Termina | ✓ ¡Listo! 3 actividades nuevas |
| Sin novedades | ✓ Todo al día |

El conteo es real: el programa conoce el total tras pedir la lista y debe avisarle a la web cada tanto (hoy no avisa).

## Pedir solo lo que falta

- **[acordado]** La web pide **días desde la última descarga exitosa + 7**, máximo 365, para actividades, historial de
  corridas, sueño y recuperación. Una descarga fallida no cuenta.
- Excepciones: comprobación = 1 día; historial = 365 días y 16 semanas de salud.
- Es seguro: `web/datos.py` solo agrega o actualiza, nunca borra.
- No alcanza: cambios a actividades de hace más de una semana o un reloj que tarde más en sincronizar.
  **[propuesto]** «Volver a traer los últimos 30 días» en Ajustes.

## Key caducada

- **[acordado]** Correo cuando la key caduca (es el único correo de esta parte).
- **[propuesto]** Si Garmin rechaza la key: aviso en el inicio + correo → guía corta (crear key, reemplazarla en GitHub,
  «Ya la cambié») → comprobación de 1 día → se traen los días que faltaron.
- La app no puede saber cuándo caduca; Garmin, según sus preguntas frecuentes, avisa cerca de una semana antes.

## Quitar las pruebas de la descarga de Pedro

- **[acordado]** Quitar el job `pruebas` de `.github/workflows/deploy.yml`. Medido: corrida de 2 min 49 s, de ellos unos
  2 min 15 s son pruebas. Ya corren en `web.yml`; a cambio, un commit sin desplegar podría llegar a su tubo sin probarse.

## Verificado en la prueba en vivo (2026-11-27)

Con la cuenta de GitHub y la key de Pedro; app y copia de prueba ya borradas.

- Instalar y autorizar en un solo recorrido: vuelven `code`, `installation_id`, `setup_action` y `state` (igual al enviado).
  Opciones de la app: «Request user authorization (OAuth) during installation», webhook apagado.
- La instalación se comprobó contra `GET /user/installations` (GitHub advierte que `installation_id` se puede falsificar).
- Permisos suficientes: `actions: write`, `secrets: read` (más `metadata: read`). Secrets solo da nombres y fechas.
- Después basta la llave privada de la app (JWT → token de instalación); no hace falta guardar el token de la persona.
- Una copia nueva de la plantilla corre sin activar nada.
- `workflow_dispatch` respondió **204 sin id** (la documentación habla de 200 con id): hay que buscar la corrida en la lista.
- El avance por pasos se lee de los jobs de la corrida; el error de key (401) se lee en el log.
- Se detectan: secreto ausente, secreto con otro nombre y key falsa.
- Corrida sin historial largo: unos 40 s (bajar datos, de 6 a 18 s).
- En la página de la app, el client secret y la llave privada están en **Credentials** (la llave en «Key pairs» → «New key»).

**Sin probar:** cuenta de GitHub nueva (prueba con la amiga), app pública, reconectar con la app ya instalada.

## Notas técnicas para el plan

- `motor.yml`, `scripts/subir.py` y `garmin_connect.py` van por `stable`: los cambios llegan a todas las copias.
- `web/tubo.py`: `instrucciones_de` decide «primera» por no haber ninguna subida buena; con la comprobación de 1 día hace
  falta marcar aparte que el historial sigue pendiente. Hoy pide 120 días por defecto.
- `garmin_connect.py`: la salud es un argumento posicional (16 semanas) y `ARGS_OK` en `scripts/subir.py` solo admite
  `--dias-actividades` y `--historial-desde`. Hace falta un argumento para limitar salud. `scripts/subir.py` y
  `garmin_connect.py` deben seguir compatibles entre sí y con la web desplegada.
- El avance necesita un endpoint nuevo con el mismo token OIDC, y que el workflow avise también cuando falla.
- El mensaje de key rechazada sugiere `gh secret set`: la web debe mostrar sus propias palabras.
- La plantilla que usa producción es `garmin-dashboard-template` (`web/config.py`) y todavía pide permisos de Pages.
  `PLANTILLA_V5_REPO` apunta a otro nombre, que no apareció entre los repos de GitHub.
- Falta registrar la app definitiva (pública). Su llave privada y client secret van en Secret Manager; no guardar tokens
  de usuario. Revisar contra la regla «nunca un token de GitHub en el sitio» y actualizar `CLAUDE.md`.
- Revisar el aviso de privacidad por el permiso de GitHub.
- Reutilizable: `web/google.py` como patrón del flujo con `state`; correos con lo que ya usa `web/correo.py`.

## Pendiente de afinar antes del plan

1. Pantallas de la guía: texto de cada paso, capturas (GitHub está en inglés), versión en celular, cuándo regresar.
   Base propuesta: un botón por pantalla, la liga abre en otra pestaña, la web recuerda el paso.
2. Tarjeta del primer inicio. **[acordado]** que recomiende conectar Garmin («es el paso más importante si tienes uno»)
   y diga que se necesita computadora. **[propuesto]**:
   > **¿Tienes un Garmin? Conéctalo.** Es el paso más importante: tus corridas, sueño y recuperación llegan solos.
   > Necesitas una computadora y unos minutos. [Conectar] [Mandarme la liga al correo] [No tengo Garmin]
3. Quienes ya están conectados: dónde se les invita a autorizar.
4. Desconectar y reconectar Garmin.
5. **[hecho]** El código de 6 dígitos se retiró al validar la GitHub App en producción; las copias nuevas se vinculan al autorizarla.
6. Confirmar todo lo marcado **[propuesto]**.

---

# Parte 2: entrada libre (después)

- **[acordado]** Entrar solo pide invitación y registro; no se pregunta qué quiere usar ni se pide GitHub o Garmin.
- **[propuesto]** Liga de invitación → correo y código → nombre y casilla del aviso de privacidad en la misma pantalla.
- **[propuesto]** Inicio vacío con: registrar actividad, conectar Garmin, InBody, armar plan, unirse a un grupo. Sin modos
  «completo» o «solo cuerpo»; donde no hay datos se dice cómo agregarlos.
- **[acordado]** Registro a mano de todas las actividades, con **correr preseleccionado** (prioridad), también para quien
  tiene Garmin. Se afina después.
- **[propuesto]** Formulario: tipo (Correr, Caminar, CrossFit, Gimnasio, Otra), fecha, distancia si aplica, tiempo,
  esfuerzo 1–10 opcional, FC y nota en «+ Más»; ritmo calculado. Editar y borrar.
- **[propuesto]** Duplicado manual/Garmin (mismo día y duración parecida): gana Garmin y se conserva el esfuerzo puesto.
- **[propuesto]** Cualquiera puede unirse a grupos; lo manual cuenta igual, marcado «a mano».
- **[propuesto]** Plan sin reloj (por tiempo y sensación, arranque suave) al final.
- **[pendiente]** Si el plan sin reloj entra en la primera versión; cuánto depende el motor v6 de la FC.

Hoy en el código: no existe el registro a mano; sin Garmin solo hay «solo cuerpo», que no puede unirse a grupos
(`web/grupos.py`, `unirse_post`).
