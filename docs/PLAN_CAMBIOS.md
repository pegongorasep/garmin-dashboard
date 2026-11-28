# Plan: cambios, resumen de la IA y orden

Requisitos acordados con Pedro para el historial de cambios (`web/cambios.py`, `/historial`, MCP, banners del inicio).

## 1. Resumen de la IA
- Columna nueva `Cambio.nota` (Text, nullable; migración 0022).
- Toda herramienta MCP que escribe acepta `resumen` (sin límite de largo): «Siempre manda `resumen`: explica a la persona en
  lenguaje normal qué cambiaste y por qué; corto si se puede, tan largo como haga falta para describir todo».
- Sin resumen se guarda igual (`nota` = None). La herramienta `historial` devuelve la nota.

## 2. Historial: cada fila
- Encabezado (quién · cuándo · vía) y descripción, como hoy.
- Con nota: bloque con la nota (saltos de línea respetados, escapada). Si pasa de ~5 líneas se muestra colapsada
  (alto fijo en `lh`) con «Ver más» / «Ver menos».
- Dentro de ese bloque, al final, un segundo colapsable independiente «Ver detalle», siempre cerrado al cargar, con todas las
  líneas de `resumen(c)` (sin tope). Sin nota, «Ver detalle» va solo, también cerrado.
- Abrir o cerrar solo cambia la altura de esa tarjeta (`<details>`, sin JS).

## 3. Aceptar y deshacer en orden, por área
Las áreas son `plan`, `ajustes` e `inbody`, cada una por separado. Un cambio pertenece a las áreas de las claves de su `despues`.

| Acción | Quién | Regla |
|---|---|---|
| Aceptar («Entendido») | solo el atleta, cambios ia/coach | Solo el pendiente más viejo de cada una de sus áreas. Pendiente = ia/coach, no visto, no deshecho. El servidor lo valida. |
| Deshacer | atleta o coach con permiso | Solo si, para cada área que tocó, lo guardado hoy es igual a `c.despues[área]` (cubre ediciones propias encima y cambios ya deshechos). Se mantienen las reglas viejas (ya deshecho, ia/coach visto, `antes` con None, «Deshacer:», saltos de la misma semana). Al deshacer, el cambio queda visto. |

Ejemplo con tres cambios 1, 2, 3 de la IA sobre el plan, todos pendientes:
1. Solo 1 tiene «Entendido»; solo 3 tiene «Deshacer».
2. Aceptas 1 y deshaces 3: ahora 2 tiene los dos botones.
3. Aceptas 2: 1 ya no se deshace (visto).
- Un InBody pendiente no bloquea aceptar un cambio del plan. Una edición propia en la web encima bloquea deshacer el anterior.
- Donde un botón no toca: gris, «Acepta primero el anterior» / «Deshaz primero el más reciente».
- Las instantáneas actuales y los pendientes se calculan una vez por página. La herramienta MCP `deshacer` y `_guardar` usan la
  misma regla; el MCP no acepta cambios. `/historial/visto` (sin id) sigue marcando todo.

## 4. Banner de InBody en el inicio
Si el cambio solo toca `inbody` y es el pendiente más viejo de inbody, `avisos[].cerrable = true` (ausente = no cerrable).
El banner muestra «Ver» y una ✕ («Entendido») que hace POST a `/historial/{id}/visto` con CSRF y colapsa el banner. Plan y
ajustes: solo «Ver».

## 5. Margen
Separación vertical entre banners de `#avisos-web` igual a la de las tarjetas del inicio (`--space-12`).
