---
name: reloj
description: Manda las sesiones de la semana del plan al reloj de Pedro (entrenamientos en Garmin Connect). Úsala cuando diga "manda la semana al reloj" o /reloj.
---

# /reloj: mandar la semana al reloj (solo Pedro)

Solo en este repo (motor de Pedro); no es de la plantilla. Nunca leas `~/.garminconnect` ni `.env`.

1. Corre la simulación (no escribe nada en Garmin):
   `.venv/bin/python reloj.py semana` (o `--semana N` si Pedro pide otra).
2. Muéstrale el resumen: qué se borra, qué se sube (nombre y pasos) y los pendientes.
3. Si hay pendientes (sesiones mandadas antes que siguen sin hacerse), pregúntale por cada una si la borra o la
   conserva, con el texto que imprime el script.
4. Con su "sí", corre lo mismo con `--si`, más `--borrar-pendientes` o `--conservar-pendientes` según lo que eligió
   (si no hay pendientes no hace falta). Nunca uses `--si` sin su confirmación.
5. Dile qué quedó y que **sincronice el reloj** (abrir Garmin Connect con el reloj cerca): Garmin los deja en cola y
   el reloj los baja al sincronizar. En el reloj: START › Correr › menú › Entrenamiento › Entrenamientos.

Si dice que no hay sesión de Garmin (o caducó): pídele que corra en la Terminal de la Mac (no con `!` dentro de Claude,
porque pide contraseña): `cd ~/Desktop/garmin && .venv/bin/python reloj.py login`. Si Garmin falla de otra forma,
cuéntalo en una línea, no reintentes y sugiere `.venv/bin/python reloj.py lista` para revisar qué quedó.
