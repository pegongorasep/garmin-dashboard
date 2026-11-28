# Requisitos: planes fijos, repetir o retomar y carreras de paso

Acordado con Pedro el 2026-11-27. Plan por fases: `docs/PLAN_PLANES.md`.

## Por qué

Con el ajuste semanal automático, la semana del 23 al 29 de noviembre de Pedro salió de 16, 19 y 23 minutos en lugar de
20, 25 y 50. El motor recalculaba las semanas anteriores con objetivos que nadie eligió, y el resultado no cuadraba con su
explicación. La app no debe cambiar sesiones a escondidas.

## Lo acordado

1. **El motor solo genera el plan al crearlo** (`/plan/nuevo`), con preferencias, historial, días, calidad y objetivo. La
   persona lo revisa antes de empezar. **Ya no hay ajuste semanal automático** (ni modo de sugerencias semanales).
2. **Repetir esta semana**: la semana siguiente vuelve a ser la misma; el resto se recorre y el plan dura una semana más.
3. **Retomar desde la semana X** (cualquier semana de la 1 a la actual, sin tope): desde este lunes toca la X, luego la
   X+1…; el plan dura (actual − X) semanas más.
4. Al repetir o retomar **solo se recorre el entrenamiento**. Los viajes, las enfermedades y las carreras se quedan en su
   fecha (un viaje cae sobre otra semana del plan y esa es la que se aligera). Las mediciones (sesiones de prueba) son
   parte de su semana y se recorren con ella. No se recalcula nada: solo se reacomodan semanas que ya existen.
5. **Vista previa**: antes de aplicar se ve **la sección de bloques del Plan completa, tal cual se ve hoy**, pero con la
   propuesta (semana repetida, fechas nuevas, fin nuevo del plan) y abajo «Sí, aplicar» / «No».
6. **Plan con carrera objetivo** (armado para una carrera): repetir o retomar muestra «No se recomienda: tu plan está
   pensado para tu carrera». Se permite si quedan semanas de carga antes del taper: para que el taper y la carrera sigan
   en su fecha, se quitan las últimas semanas de carga antes del taper (la vista previa dice cuáles). Si no quedan, no se
   permite y se sugiere crear un plan nuevo.
7. **Deshacer** repetir o retomar: solo durante la misma semana en que se hizo. Ya en la siguiente queda fijo.
8. **Agregar carrera** ofrece dos caminos, bien distintos en pantalla:
   - **Carrera de paso (sigo con mi plan)**: nombre, fecha y distancia (libre, opcional). No recalcula nada: la carrera
     **es la larga de esa semana** (reemplaza la sesión larga; si se corre ese día, cuenta como la larga hecha). Se
     puede quitar cuando sea. También dentro de un plan con carrera objetivo.
   - **Entrenar para esta carrera**: abre `/plan/nuevo` con la carrera ya puesta; sale un plan nuevo y el anterior queda
     en el historial.
   - No se suaviza nada antes ni después de una carrera: cada sesión ya trae su versión suave para elegir en Hoy.
   - «Agregar carrera» ya no rehace el plan a media marcha.
9. **Si pasan 2 semanas sin correr** (ni Garmin ni a mano) con un plan en curso, Hoy sugiere «Retomar desde la semana X»
   (la última completa; si no hay, la 1), que abre la misma vista previa, o «Crear plan nuevo». Nada cambia solo.
10. Todo cambio queda en el historial de Cambios. Lo que ya existe (planes con carrera ya metida, semanas repetidas
    viejas) se deja como está, solo que siga funcionando.
