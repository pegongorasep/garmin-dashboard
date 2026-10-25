# Requisitos — Garmin: dashboard + plan de base aeróbica

Estado: **APROBADO v2** (2026-10-24) por Pedro.

## 0. Objetivo

Sumar 2 corridas por semana al CrossFit (3–4 días) para construir base aeróbica en zonas bajas, con un plan
de 12 semanas que se ajuste a la carga del CrossFit y a la recuperación (HRV, FC en reposo, sueño), y un
dashboard público que se actualiza solo, visible en Mac y celular.

## 1. Datos y conexión (✅ hecho)

- Garmin Connect **Personal API** (solo lectura). Key en `.env`; token JWT de 24 h (se pide cada vez).
- `garmin_connect.py` descarga a `data/`: actividades (todo el historial), resúmenes diarios, sueño, HRV,
  body battery, estrés, zonas de FC y perfil.
- Limitación: **no se puede escribir en Garmin** (ni cambiar ajustes ni mandar entrenamientos al reloj).

## 2. Zonas de FC (decidido)

| Parámetro | Valor |
|---|---|
| Método | Karvonen (% de FC de reserva) — igual que el fisio y que el reloj |
| Zonas | Z1 50–60 · Z2 60–70 · Z3 70–80 · Z4 80–90 · Z5 90–100 % |
| FC reposo | La del reloj (promedio 7 días, medida dormido — igual que con el fisio) |
| FC máx provisional | **190** (≈ 220 − 29 = 191) → Z2 ≈ 138–151 con reposo 60 |
| FC máx definitiva | Pico con correa en HIIT de CrossFit durante 2–3 semanas **+ 3 lpm**; mínimo 183; si sale > 200 se revisa |
| Recalcular zonas | Cuando cambie la FC máx o el reposo promedio se mueva ≥ 3 lpm |

## 3. Hábitos de registro (lo que hace Pedro)

1. En Garmin Connect: apagar **auto-detectar FC máx** y poner **190**. Reposo: dejar en promedio.
2. **Correa de pecho también en CrossFit** (humedecerla antes).
3. Grabar **fuerza y HIIT como dos actividades** del CrossFit.
4. **Autoevaluación = Siempre** en los perfiles Correr, HIIT y Fuerza (RPE 1–10 + cómo te sentiste).
5. **Dormir con el reloj** todas las noches (HRV y sueño).
6. Corridas: siempre con correa (ya lo hace).

## 4. Dashboard

### 4.1 Funcionamiento
- Publicado en **GitHub Pages, público** (sin login — decisión de Pedro). Visible en Mac y celular; diseño responsive.
- **GitHub Action** que baja los datos de Garmin y vuelve a publicar el sitio:
  - automático en horario programado (propuesta: 3 veces al día — 7:00, 13:00 y 19:00 hora de Mérida);
  - y manual con el botón "Run workflow" de GitHub cuando quieras datos al momento.
- La API key vive solo como **secreto de GitHub** (`PERSONAL_API_KEY`); nunca en el código ni en el sitio.
- Al ser público, el sitio publica **solo las métricas necesarias** (FC, HRV, sueño, duración, zonas, RPE):
  sin nombre, IDs de Garmin, foto, ni nombres de lugar de las actividades.
- En español.

### 4.2 Vistas
Diseño pensado primero para celular, con barra de pestañas abajo: **Hoy · Semana · Plan · Tendencias · Más**.

1. **Hoy** — semáforo 🟢🟡🔴 con la sesión de hoy (o su versión suave) y por qué: HRV de anoche vs rango
   base, FC reposo vs promedio 7 días, sueño, RPE del CrossFit de ayer, cada una con ✓/⚠. Si hoy es CrossFit
   lo dice; si es día libre y hay corrida pendiente, sugiere reponerla.
2. **Semana** — tira de 7 días (CrossFit / corrida hecha / pendiente / descanso), corridas hechas de 2,
   carga semanal (RPE × min) vs semana anterior, y distribución de intensidad de toda la semana
   (CrossFit incluido): barra con las **5 zonas, cada una con su color**, agrupadas en
   **Z1–Z2 bajo = 80 %** (meta) · **Z3 limbo** (lo menos posible, sin meta numérica) ·
   **Z4–Z5 alto = 20 %** (modelo polarizado). Es **solo referencia**. El tiempo en **Z0** (< 50 % de reserva) es descanso y
   **no cuenta**.
3. **Plan** — tarjetas de las sesiones de la semana con pasos para copiar a Garmin Connect y su estado
   (hecha / pendiente / ajustada); línea de las 12 semanas con bloques, descargas y semana actual.
4. **Tendencias** — selector 4/8/12 semanas: HRV (con banda de rango base), FC reposo, sueño, carga semanal
   (CrossFit y corridas apiladas).
5. **Más**
   - **Corridas**: lista (duración, FC prom, % en Z1–Z2) y gráfica de **eficiencia aeróbica** (ritmo a FC de Z2).
   - **FC máxima**: progreso de la medición (clases con correa, pico, FC máx estimada) y tabla de zonas actual.
   - **Cómo funciona**: reglas del semáforo y link a los docs.

### 4.3 Fuera de alcance (por ahora)
- Seguimiento de elevaciones de talón (siguen en el plan como recomendación, sin registro).
- Body Battery y estrés.
- Avisos/notificaciones al celular.
- Notas personales.

## 5. Plan de entrenamiento

### 5.1 Estructura
- Duración: **12 semanas = 3 bloques de 4** (3 semanas subiendo + 1 de descarga), como el fisio.
- **2 corridas por semana**, en días **sin CrossFit**, por la tarde-noche (calor).
- Prescripción **por tiempo** con techo de FC: "trota hasta el techo, camina hasta bajar".
- **Corrida A (variada)** — formatos del fisio adaptados a trote/caminata: espiga, pirámide 1-2-3,
  ascendente/descendente, intervalos con densidad (1:1, 1:2, 1:3). **Puede llegar a Z3**, como en los
  entrenos del fisio (picos cortos dentro de la sesión).
- **Corrida B (continua suave)** — Z1–Z2, la duración sube poco a poco.
- Z4–Z5 no van en las corridas (ya las da el CrossFit). Se reevalúa después de la semana 12.
- La barra 80/20 del dashboard es **solo referencia**; no cambia el plan.

### 5.2 Progresión
- **Arranca ya** con zonas provisionales; Pedro usa la correa en CrossFit desde ahora para medir la FC máx.
- Arranque conservador (viene de gripe + migraña).
- **Una sola variable a la vez** (duración, o proporción de trote, o intensidad — nunca dos).
- Semana 4 de cada bloque: descarga, todo continuo Z1–Z2.
- Si una semana se siente pesada → repetir la anterior.

### 5.3 Pantorrillas
- Elevaciones de talón a una pierna, 2–3 × 10–15, 2 veces por semana.

### 5.4 Cómo encaja con el CrossFit
- CrossFit lun/mar/jue (+ a veces mié o vie) → corridas en los días libres.
- **Días flexibles**: preferencia miércoles + (viernes o sábado), pero no fijos.
- Si se falla una corrida, se repone en otro día libre **de la misma semana**; no se arrastra a la siguiente.
- Nunca correr el mismo día que CrossFit.
- Si el CrossFit del día anterior tuvo **RPE ≥ 8** → la corrida de hoy pasa a su versión suave.

### 5.5 Ajuste por recuperación (semáforo)
Lo calcula el **dashboard automáticamente** cada día. Además hay **revisión semanal opcional** con Claude
para ajustes grandes (subir volumen, repetir semana, recalcular zonas).

- 🟢 Normal: HRV dentro de tu rango base, reposo ≤ promedio + 4, sueño ≥ 6.5 h → sesión como está.
- 🟡 Precaución: una señal fuera → versión suave (Corrida B corta o −30 % de tiempo).
- 🔴 Alerta: dos o más señales fuera, o HRV "baja" → descanso o caminata ligera.
- 🔴 dos días seguidos o enfermedad → repetir la semana.

### 5.6 Entrega
- Cada sesión como lista de pasos para crearla en Garmin Connect (con alertas de FC en el reloj).

### 5.7 Fase 2 (opcional, semana 5+)
- Si todo va bien: 10 min de bici suave Z1–Z2 al final del CrossFit. Se decide con datos.

## 6. Preguntas abiertas
1. ¿Algo del documento que quieras cambiar antes de aprobarlo?

Resuelto: polarizado 80 % Z1–Z2 / Z3 mínimo / 20 % Z4–Z5, Z0 excluido ✅ · horario 7:00 / 13:00 / 19:00 ✅ · privacidad (solo métricas necesarias) ✅ · cuenta GitHub sí,
`gh` ya instalado (falta `gh auth login`) ✅
