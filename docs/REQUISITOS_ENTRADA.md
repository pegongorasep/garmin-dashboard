# Requisitos: entrada libre y registro a mano (parte 2)

Escrito el 2026-11-27. **Requisitos acordados; todavía no hay plan ni código.** Reemplaza la parte 2 de
`REQUISITOS_CONEXION.md`. La parte 1 (conexión y sincronización) va aparte, en `PLAN_CONEXION.md`.

Marcas: **[acordado]** lo decidió o confirmó Pedro · **[pendiente]** por revisar.

## Por qué

Entrar a la app no debe exigir nada. Garmin, InBody, plan y grupos se agregan después, y quien no tiene Garmin también
puede usarla.

## Orden de construcción

- **[acordado]** 1) entrada libre, 2) registro a mano, 3) grupos, 4) plan sin reloj (al final).
- **[acordado]** Planear y construir cuando termine la parte 1: las dos tocan la bienvenida y el inicio.

## Registro

- **[acordado]** Solo pide invitación y registro. No pregunta qué se quiere usar ni pide GitHub o Garmin.
- **[acordado]** Pantalla 1 (desde la liga de invitación): «Continuar con Google», o correo y código.
- **[acordado]** Pantalla 2: nombre, apellido (los grupos exigen ambos) y casilla del aviso de privacidad (datos de
  salud, porque lo anotado a mano, como pulso o InBody, también lo es). Después, el inicio.
- **[acordado]** Desaparecen «¿Qué quieres usar?» y los modos «completo» y «solo cuerpo». Todos tienen todo y cada
  sección vacía dice cómo llenarla.
- **[acordado]** Quien hoy está en «solo cuerpo» conserva sus datos y ve las demás opciones.
- **[acordado]** Las invitaciones no cambian: solo la de cuenta (la crea el admin) crea cuentas; la liga de grupo sirve
  a quien ya tiene cuenta.

## Primer inicio

- **[acordado]** De arriba a abajo: tarjeta de Garmin, «+ Registrar actividad», y luego armar plan, unirse a un grupo y
  agregar InBody.
- **[acordado]** Tarjeta: «¿Tienes un Garmin? Conéctalo. Es el paso más importante: tus corridas y tu sueño llegan
  solos. Necesitas una computadora.» [Conectar] · Mandarme la liga · No tengo Garmin
- **[acordado]** «No tengo Garmin» quita la tarjeta; la opción de conectar queda en Ajustes.
- **[acordado]** InBody desde el inicio abre lo que hoy hay en Cuerpo.

## Registro a mano

- **[acordado]** Para todas las actividades y para todas las personas, también quienes tienen Garmin.
- **[acordado]** Botón «+» siempre visible en el inicio.
- **[acordado]** Una sola pantalla: tipo, fecha (hoy), distancia, tiempo, esfuerzo 1–10 opcional y «+ Más» (FC y nota).
- **[acordado]** Tipos: **Correr preseleccionado** (es la prioridad), Caminar, CrossFit, Gimnasio y «Otra», que abre una
  lista desplegable:

  | Actividad | Distancia |
  |---|---|
  | Bicicleta | km |
  | Natación | metros |
  | Senderismo | km |
  | Elíptica | no |
  | Yoga o movilidad | no |
  | Deporte (fútbol, tenis, pádel…) | no |
  | Otra actividad | opcional |

- **[acordado]** Obligatorio: distancia y tiempo en correr y caminar; en las demás, tiempo. El ritmo se calcula y se
  muestra solo en correr y caminar. Si no aplica la distancia, se oculta dejando su espacio (altura fija).
- **[acordado]** Al guardar regresa al inicio y ya cuenta en la semana. Se puede editar y borrar.
- **[acordado]** Duplicados con Garmin: **no se manejan** por ahora (muy raro); si pasa, se borra el registro a mano.

## Grupos

- **[acordado]** Cualquiera puede unirse, con o sin Garmin.
- **[acordado]** Lo registrado a mano cuenta igual, aparece en la actividad del grupo (con reacciones y comentarios) y
  lleva la marca «a mano».
- **[acordado]** Quien no tiene plan muestra kilómetros y días de la semana, sin comparación. La privacidad por persona
  funciona como hoy.

## Plan sin reloj (última fase)

- **[acordado]** Se incluye.
- **[acordado]** A quien no tiene historial se le pregunta cuántos días corre por semana y cuánto dura su corrida más
  larga; el plan arranca un poco por debajo de lo que responda.
- **[acordado]** Se siguen mostrando las zonas (Zona 1, Zona 2…) **y además** una descripción por sensación («suave:
  puedes platicar sin cortarte»). No se sabe si la persona tiene otro reloj o sensor que le diga sus zonas.
- **[acordado]** Recordatorio en el plan, «¿Corriste? Anótalo»: el ajuste de cada lunes baja la carga si no ve corridas.
- **[pendiente]** Revisar cómo calcula el trote continuo sin los detalles del reloj (`plan/nivel.py`).

## Notas técnicas

- No existe el registro a mano. El motor v6 usa de las actividades fecha, tipo y duración, y no calcula zonas de FC
  (el sitio las traduce con las de Garmin; sin ellas va solo el nombre de la zona y su descripción).
- `web/grupos.py` (`unirse_get` y `unirse_post`) rechaza a `uso == "cuerpo"` y exige nombre y apellido.
- `web/onboarding.py` hoy lleva por la guía antes del inicio; la guía nueva de la parte 1 debe quedar como algo que se
  abre desde la tarjeta, y el consentimiento de privacidad pasa al registro.
- «Mandarme la liga» sale en la parte 1; la tarjeta lo reutiliza.
