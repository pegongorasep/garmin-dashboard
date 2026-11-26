# Modo «Sin plan» (acordado con Pedro, 2026-11-27)

Mucha gente solo quiere ver lo que hizo, no seguir un plan. Para las cuentas **nuevas**, «sin plan» es lo predeterminado.

## Decisiones
- **Onboarding** (`uso` = completo): después del aviso/uso se pregunta «¿Quieres un plan de running?», con **«No, solo ver cómo voy»** preseleccionado. Con «No» se salta el cuestionario del plan; el repo de GitHub y la key de Garmin siguen haciendo falta. El onboarding queda completo al conectar el repo.
- **Cuentas con plan** (Pedro y su amiga) se quedan exactamente igual.
- **Bandera `sin_plan`**: columna `usuarios.sin_plan` en la web (migración 0012, `false` para lo existente) y clave raíz `sin_plan` en el config (por defecto `false` en `dashboard/defaults.yaml`). El motor la expone como `ui.sin_plan`.
- **Motor**: sin plan se construye con un plan vacío (`weeks: []`); el data.json sigue pasando `validar`.
- **Hoy sin plan = «tu semana»** (bloque `semana_libre` calculado en Python): actividades por día, minutos y km contra el promedio de 4 semanas, tiempo en zonas, carga/recuperación si existe, racha de semanas activas. Pestaña Plan oculta o tarjeta «Sin plan · Quiero un plan». Progreso igual.
- **Ajustes**: «Quiero un plan de running» (sin_plan=false y al cuestionario) y «Quitar mi plan» (sin_plan=true; el plan guardado se queda).
- **Tarjeta de grupos**: para quien no tiene plan, días activos, minutos de la semana y última actividad; sin adherencia/meta/etapa.
- **Coach MCP**: las herramientas del plan responden con un `Rechazo` («no tienes plan; actívalo en Ajustes»); las de resumen siguen.
- **Reloj**: nada que hacer (solo `reloj.py`, local de Pedro).

## Fases
- **L1** modo y bienvenida (bandera, pregunta del onboarding, Ajustes, data.json sin plan).
- **L2** Hoy muestra tu semana (`semana_libre`, pestaña Plan).
- **L3** grupos y coach.
