---
name: revision
description: Revisión semanal: lee los datos publicados, resume la semana (corridas vs plan, zonas, recuperación, carga) y sugiere ajustes conservadores.
---

# /revision: revisión semanal

Habla en español, claro y corto. No pidas la key ni leas `.env`. Solo lectura hasta que la persona acepte un cambio.

1. Obtén la URL de su página: `gh repo view --json nameWithOwner` → `https://{owner}.github.io/{repo}/`.
   Baja los datos: `curl -s https://{owner}.github.io/{repo}/data.json` (guárdalo en un archivo temporal).
   Si está vacío o es el primer día, dile que Garmin tarda unas horas.
2. Resume la semana (de lunes a hoy), con números del JSON:
   - **Corridas vs plan:** `plan.estado_sesiones` (hecha / incompleta / pendiente) y `semanas_hoy[]` (minutos y km
     vs `plan_min`). Si hay calidad, `corrida.calidad` dice "minutos en la zona objetivo: X de Y".
   - **Zonas:** `detalles.distribucion` (meta ~80 % en Z1–Z2; limbo Z3 lo mínimo).
   - **Recuperación:** `hoy.semaforo` y `hoy["señales"]` (HRV, FC en reposo, sueño) y `hoy.ayer` (esfuerzo de la sesión de ayer, calculado con la FC); tendencias en
     `progreso.dias`.
   - **Carga:** `detalles.carga` vs `carga_anterior`. Una subida de más de ~30 % merece cautela.
   - **Cómo vas mejorando:** `progreso.mejora.frase`.
3. Sugiere ajustes **conservadores** y explica el porqué:
   - Semana mala (semáforo rojo varios días, sesiones incompletas, dolor): repetir la semana con
     `semanas_repetidas: [n]` en `config.yaml`.
   - Con caminatas, si todo salió fácil: puede subir un escalón; si cuesta, no subir.
   - Con calidad, si no llega a los minutos objetivo varias semanas: bajar a `z2_poca_z3` o `solo_z2`.
4. Solo si la persona acepta, aplica el cambio en `config.yaml` (si afecta el plan, sigue los pasos de `/ajustar`),
   commit, push y publica.
