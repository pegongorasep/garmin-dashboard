# Requisitos — Garmin: dashboard + plan de base aeróbica

Estado: **APROBADO v3** (2026-11-14) por Pedro — los cambios de v3 están en la §7 y **mandan sobre las
§4–5** donde choquen. v2 aprobado el 2026-10-24.

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

## 7. Cambios v3 (2026-11-14)

### 7.1 Plan
- Pasa al **plan v2** de [`PLAN_ENTRENAMIENTO.md`](PLAN_ENTRENAMIENTO.md) (aprobado): inicio **lun 16 nov 2026**,
  12 semanas, **3 sesiones por semana: Z2 #1, Z2 #2 y Larga**. CrossFit lun/mar/jue.
- Solo progresa el tiempo. Desde la semana 5, la Z2 #1 trae 2×1' de Z3 **opcionales**, dentro del tiempo.
- El tiempo de una sesión es el **tiempo de reloj** (incluye el arranque suave y las caminatas).
- `semanas_repetidas` vuelve a `[]`; el historial anterior se sigue viendo en las corridas.

### 7.2 Navegación: de 5 pestañas a 2
1. **Hoy** — todo lo de entrenar, en una pantalla:
   - Semáforo + la sesión de hoy (Z2 / Larga / CrossFit / Descanso) con pasos en lpm.
   - **Última corrida — "¿lo hice bien?"** (§7.4).
   - **Semana**: tira de 7 días, corridas "x de 3", km y minutos trotando de la semana.
   - **Plan de la semana** (semana n de 12): las 3 sesiones con su estado y pasos para copiar a Garmin.
2. **Progreso** — selector 4 / 8 / 12 semanas:
   - Una **frase de conclusión** arriba (ej. "Trotas 68 % del tiempo (hace 4 sem: 58 %) · ritmo trotando 7:40 → 7:25").
   - **% del tiempo trotando** por corrida y **ritmo trotando** por corrida.
   - **Volumen semanal**: minutos hechos vs plan, con km.
   - **Recuperación**: HRV, FC en reposo y sueño — punto diario + **línea de promedio de 7 días** (HRV con banda base).
   - Línea de las 12 semanas (bloques, descargas, semana actual) y lista de corridas.
3. **Detalles** (enlace al final, no pestaña): FC máx y zonas, cómo funciona, barra de intensidad 80/20 y
   carga RPE del CrossFit (solo referencia).

### 7.3 Semáforo
- Si **no hay datos de anoche** (HRV, FC reposo y sueño los tres sin dato) → estado **"sin datos"** (gris),
  no verde: muestra la sesión normal con "decide por cómo te sientes".
- Si falta solo alguna señal, decide con las que hay y marca las faltantes como "sin dato" (no como ✓).
- El resto de reglas no cambia.

### 7.4 Corridas
- **Trote vs caminata**: de los tramos que detecta Garmin (`splitSummaries` RWD_RUN / RWD_WALK) por corrida:
  minutos y % trotando, número de caminatas, **patrón detectado** (≈ trote/caminata promedio por tramo),
  **ritmo y FC trotando**. Barra trote/caminata en cada corrida.
- **Km** por corrida y por semana.
- **Asignación a sesiones** (automática, sin nombres): una corrida en sáb/dom que dure ≥ 70 % de la Larga
  → Larga; las demás llenan Z2 #1 y Z2 #2 en orden.
- **Estado de la sesión**: *hecha* si duró ≥ 70 % de lo planeado (o de su versión suave si ese día era 🟡/🔴,
  y entonces "ajustada"); si duró menos, *incompleta*; si no hay corrida, *pendiente*.
- **"¿Lo hice bien?"**: plan vs hecho — tiempo, km, minutos por encima del techo de Z2 (✓ si ≤ 2'; en la Z2 #1
  con picos opcionales se permiten 2' más), barra trote/caminata, ritmo trotando.

### 7.5 Privacidad
- Igual que v2. De los tramos solo se publican tiempos, distancias, ritmos y FC; nada de GPS ni nombres.

### 7.6 Fuera de v3
- Semáforo "estable" (que una sola noche baja de HRV no dé rojo). Se puede revisar después con datos.
- Botones manuales de hecha/no hecha (no hay dónde guardarlos).
- Asignar corridas por el nombre de la actividad en Garmin (Pedro no les pone nombre).

## 8. Cambios v3.2 (2026-11-14) — APROBADO por Pedro, falta plan de construcción

Ya hecho: el plan arranca el **lun 9 nov 2026** (la corrida del jue 12 = Z2 #1).

### 8.1 Pantalla Hoy, de arriba abajo
1. **Esta semana — siempre arriba y con TODAS las corridas reales** (aunque no haya plan activo, sean
   extra o en días no planeados): "N corridas · min · km · % trote". Lo del plan como dato secundario
   ("Plan: 2 de 3 sesiones · 78 / 80 min"). Sigue el selector de semana (8.2).
2. **Calendario de 7 días** (vuelve): corridas protagonistas (círculo de color, minutos, sesión);
   CrossFit chico y gris con su intensidad = RPE si existe, si no **Training Effect aeróbico de Garmin**
   (`aerobicTrainingEffect`, 0–5, 1 decimal); días futuros con lo planeado en tenue.
3. **Tus corridas** con selector **‹ Semana n de 12 ›** arriba: semanas pasadas (hechas, sin hacer,
   extras con sus datos), actual y futuras (plan con pasos). Las corridas que no caben en una sesión
   salen como **"Extra"**. "Esta semana" y el calendario siguen a la semana elegida.
4. **Cómo vas mejorando**: frase resumen + 2 mini gráficas (minutos por semana últimas 8 vs plan; % trote
   por corrida) + una línea de InBody ("13 nov · Grasa 27.1 % ▼3.0 · Músculo 39.1 kg ▲1.1 · Visceral 10").
   Tocar lleva a Progreso. Ritmo trotando solo en Progreso.
5. **Recuperación** colapsada (como en v3.1).

### 8.2 Composición corporal (InBody)
- Datos en `plan/inbody.json` (se capturan a mano de la foto mensual; se publica todo menos nombre, ID
  y fecha de nacimiento).
- Principal: **% de grasa (PGC)** y **músculo esquelético (MME)**; secundarios: peso, puntuación,
  grasa visceral (rango sano 1–9), masa grasa (kg = peso × PGC si no viene).
- **Prime** = la mejor medición (menor % de grasa): 25 may 2024 (22.3 %, MME 38.4, 86.2 kg). Se marca en
  las gráficas y se muestra la meta "superar tu prime" (cuánto falta en % de grasa; MME ≥ la del prime).
- Progreso: sección "Composición corporal": gráfica de recomposición (masa grasa y masa muscular, kg,
  un eje), % de grasa en el tiempo con la raya del prime, tabla de mediciones.

## 9. v4: template para otras personas (2026-11-24) — APROBADO por Pedro

Plan de construcción: [`PLAN_V4.md`](PLAN_V4.md).
- Template, no app. Cada quien tiene un repo chiquito (config, plan, InBody opcional) y su GitHub Pages público.
- El repo de Pedro es la fuente de verdad: el workflow del amigo llama al de Pedro con la etiqueta `stable`, así
  que las actualizaciones y las instrucciones de Claude llegan solas.
- Actividades genéricas por tipo de Garmin (fuerza, HIIT, cardio, movilidad), con semana típica y días de pierna.
- Plan de 3 corridas por semana según nivel: novato solo Z2 (con caminatas si hace falta), intermedio Z2 con
  poquita Z3, corredor Z2 + calidad (Z3 tempo / threshold / intervalos) + Larga. Siempre se puede elegir
  "solo Z2" si ya hace intensidad en HIIT.
- Configuración con Claude Code: `/setup`, `/ajustar`, `/revision`. Nada de ajustes dentro del sitio.
- Dashboard con la misma estructura. Cambia: categorías, textos desde la config, tarjeta de calidad, mejora según
  haya caminatas o no, estado de primer día, InBody opcional, enlace "Jalar datos" al repo de cada quien.

## 10. v4.2: Plan, tipos de entreno, íconos (2026-11-24) — APROBADO por Pedro

Plan de construcción: [`PLAN_V4_2.md`](PLAN_V4_2.md).
1. **Pestañas Hoy · Plan · Progreso** (Progreso con subpestañas **Corridas** y **Cuerpo**). Desaparece Detalles.
   Plan = 12 semanas + tipos de entreno + zonas y reglas. Corridas = lo de Progreso de hoy menos las 12 semanas,
   más intensidad y carga. Cuerpo = recuperación + composición InBody.
2. **Catálogo "Tipos de entreno"** (solo para conocerlos): siluetas de la FC en el tiempo, **sin color ni números**.
   Continuo, trote/caminata; los de Adrián ("Alex", el fisio): espiga, pirámide, ascendente, descendente,
   intervalos con densidad, rotativo; avanzados: progresivo, tempo, umbral, intervalos VO2, fartlek, carrera.
   La Larga es un continuo más largo (sin tarjeta propia).
3. **Silueta de cada sesión del plan pintada con los colores de zona de Garmin** (Z1 gris, Z2 azul, Z3 verde,
   Z4 naranja, Z5 rojo), solo en la silueta, no en el resto del sitio. Con receta corta (minutos y zonas).
4. **Plan con corrida variada para usuarios nuevos** (`/setup` pone `variada: true`): 1 variada + 1 Z2 + Larga
   Z2; solo Z2 → formatos de Adrián en Z1–Z2; poca Z3 → formatos de Adrián con un pico corto de Z3; corredor →
   solo avanzados. Descargas todo continuo. **El plan de Pedro no cambia.**
5. **No asumir CrossFit**: fuera la semana típica; solo se marca lo que Garmin registró. Fuera los "¿Larga?".
6. **Fuerza/HIIT en "Cómo vas mejorando"**: en la frase y en una gráfica de sesiones por semana.
7. **Íconos SVG por actividad** (corredor, medalla para carreras, mancuerna, rayo, bici, nadador, caminante,
   yoga, punto).
8. **Barra 80/20** de la semana en Hoy e **intensidad por semana** en Progreso › Corridas.

## 6. Preguntas abiertas
1. ¿Algo del documento que quieras cambiar antes de aprobarlo?

Resuelto: polarizado 80 % Z1–Z2 / Z3 mínimo / 20 % Z4–Z5, Z0 excluido ✅ · horario 7:00 / 13:00 / 19:00 ✅ · privacidad (solo métricas necesarias) ✅ · cuenta GitHub sí,
`gh` ya instalado (falta `gh auth login`) ✅

### 10.1 Una sola zona por tramo (2026-11-24) — APROBADO por Pedro

Como en los entrenos de Adrián, cada tramo va en **una sola zona**: trote = Z2, caminata = Z1, enfriamiento = Z1.
Se acabó el "Z1–Z2" en los pasos (era un rango inventado para marcar solo el techo). La regla de techo no cambia
(si pasas el techo de Z2, caminas; "¿lo hice bien?" cuenta los minutos sobre Z2). El generador escribe la zona
única; los planes viejos con "Z1-Z2" se muestran igual en una sola zona (`tipos.zona_unica`). "Bajo Z1–Z2" del 80/20
sigue: es la suma de zonas bajas, no un tramo.

### 10.2 Calentar y enfriar van aparte; etiquetas de la silueta (2026-11-24) — APROBADO por Pedro

- **Calentar 5' y enfriar 5' nunca cuentan** (son caminar, no se graban): los minutos de una sesión son solo lo que se
  graba en Garmin. El sitio dibuja la rampa de calentar salvo que el plan empiece con un calentamiento en Z0/Z1, y la
  de enfriar salvo que el plan traiga enfriamiento (planes viejos).
- El generador ya no pone calentamiento ni enfriamiento dentro de las sesiones: en las de calidad los 10' Z2 del
  inicio son un tramo normal; las variadas usan todos sus minutos en el cuerpo. El cuerpo puede empezar en Z1 a lo
  más 2' (como escalón, no como calentamiento); la densidad sin Z3 reparte el sobrante entre sus picos de Z2.
- La caminata no se asume: en la silueta es un tramo de Z1 como cualquier otro (alguien muy en forma trota suave en
  Z1). El título no la cuenta: "Trote y caminata en Z2".
- Silueta de una sola zona: "20 min Z2 / 138–150 lpm". Con más de una zona (compacta): arriba solo los minutos ("3′")
  con una línea del color del tramo (si dos chocan, una se alarga) y abajo una leyenda con zona y lpm.

## 11. v4.3: medir la mejora, esfuerzo sin RPE, resumen semanal, prueba final (2026-11-24) — construido, falta publicar

### 11.1 Ritmo a FC de referencia (reemplaza "ritmo trotando")
- Por corrida: ritmo de los tramos de trote llevado a la **FC de referencia = mitad de Z2** (≈144 lpm):
  ritmo × (FC trote ÷ FC ref). Es la eficiencia aeróbica (velocidad ÷ FC).
- Solo corridas al aire libre cuyo trote cayó en Z2; fuera carreras y caminadora.
- Progreso › Corridas: un punto por corrida + línea de promedio, en lugar de "ritmo trotando". La frase dice
  "a 144 lpm: 7:48 → 7:35 /km". "Cómo funciona" aclara que el calor lo afecta (ver tendencia, no una corrida suelta).

### 11.2 Deriva cardiaca
- Corridas de **≥ 40 min casi sin caminar** (≥ 90 % trote), **casi todas en Z2** (≥ 80 % del trote después de los
  10 min; una carrera a tope no cuenta) y **a ritmo parejo**. Si la corrida no cumple, no se muestra deriva. Parejo: después
  de los primeros 10 min, cada km a no más de ±15 % del ritmo mediano de esa corrida (cabe la baja normal por
  cansancio; no caben picos de Z3, sprints ni cambios bruscos, porque la FC tarda en alcanzar a la velocidad).
- Velocidad ÷ FC en la primera mitad vs la segunda, **sin los primeros 10 min** y sin tramos de caminata. Mide las
  dos formas de deriva: a ritmo constante sube la FC; a FC constante baja el ritmo. **< 5 % = buena base.**
- En "¿lo hice bien?" ("Deriva 4 % ✓") y tendencia en Progreso.
- Requiere bajar la serie de tiempo, distancia y FC de cada corrida (una petición por corrida, en caché, sin GPS).

### 11.3 Plan vs real por zona
- Con la misma serie de FC y las zonas del dashboard: por zona, **planeado vs hecho** ("Z3: 2 de 4 min, 50 %").
- Los minutos en una zona más alta cuentan para la de abajo. Una zona alta se cumple con el **70 %** (la FC tarda en subir).
- Pasarse del techo sigue como hoy.

### 11.4 Esfuerzo calculado (en vez de RPE)
- Valor por zona: Z0 1 · Z1 2 · **Z2 3** · Z3 5.5 · Z4 7.5 · Z5 9.5. **Esfuerzo (1–10)** = promedio en la mitad más
  dura de la sesión (los descansos no lo bajan). **Carga** = esfuerzo × minutos, para todas las actividades.
- Se registra en cada actividad junto al **RPE manual si existe** (los dos).
- Mismo día con varias sesiones de una categoría: "ayer" toma el esfuerzo más alto; las cargas se suman.
- **Sale del semáforo**: quedan HRV, FC reposo y sueño. El esfuerzo de ayer se muestra como dato ("Ayer: HIIT,
  esfuerzo 8.7"); si hubo una señal fuera después de un día duro, el motivo lo dice ("HRV baja después de un día duro").
- Las gráficas de carga usan esta carga. "Cómo funciona": la fuerza con FC baja da poca carga.

### 11.5 Resumen de la semana pasada (en Hoy, sin Claude)
- Arriba, debajo de "Próxima corrida", toda la semana: "Semana pasada: 3 de 3 · 85 / 85 min · 6 de 7 días verdes ·
  ✓ Sigue el plan". Al tocarlo: km, % trote, 80/20, carga vs anterior, ritmo a FC ref vs anterior, plan vs real.
- Sugerencia por reglas conservadoras (solo sugiere; repetir semana sigue siendo con `/ajustar`):
  todo hecho y recuperación bien → "Sigue el plan"; < 2 sesiones o ≥ 2 días rojos → "Considera repetir la semana";
  carga > 30 % sobre la anterior → "Semana pesada, cuida la recuperación".

### 11.6 Prueba al terminar el plan
- La semana 12 (descarga) cambia la Larga por una prueba, según el plan: base → **30 min a FC fija** (mitad de Z2,
  ruta plana, alerta en el reloj; se miden los km); novato con caminatas → 30' en Z2 sin caminar si puede; se mide el % de trote (Garmin no dice en qué orden
  trotaste y caminaste), y si trotó los 30' seguidos (≥ 95 %) también los km, para pasar a la prueba a FC fija; corredor →
  5 km a tope. Aplica también al plan de Pedro.
- La primera vez se compara contra el ritmo a FC ref de las semanas 1–2; luego prueba contra prueba.
- Al acabar el plan, Hoy muestra "Plan terminado" con el resultado vs el inicio y "Corre `/ajustar` para el siguiente
  bloque"; `/ajustar` lo usa para proponer el siguiente plan.

### 11.7 No cambia
- La barra 80/20 de Hoy se queda como está.

## 12. v4.4: mandar las sesiones al reloj (solo Pedro) (2026-11-25) — APROBADO por Pedro; construido, falta probar en el reloj

Solo en la computadora de Pedro. **No** va al workflow, ni a la plantilla, ni a los amigos.

### 12.1 Cómo entra a Garmin
- La Personal API oficial solo lee. Escribir entrenamientos usa las APIs internas de Garmin Connect con la librería
  no oficial `garminconnect` (ya en `.venv`, 0.3.20). Puede romperse si Garmin cambia algo: entonces avisa y no reintenta.
- Login **una sola vez** en la Terminal de la Mac (no dentro de Claude: el `!` no deja escribir): correo, contraseña
  y código MFA si lo pide. La contraseña **no se guarda**; solo los tokens de sesión en `~/.garminconnect`
  (fuera del repo). Si caducan, vuelve a pedir el login.
- No se instala un MCP de terceros: un script propio hace solo lo que necesitamos y la contraseña no pasa por código ajeno.

### 12.2 Qué manda
- Las sesiones **de la semana actual del plan** (cuenta `semanas_repetidas`; `--semana N` para otra), solo la
  versión normal (no la suave). Incluye la prueba de la semana 12.
- Cada sesión es un entrenamiento de **correr** en la biblioteca de Garmin (sin día en el calendario) y se envía
  al reloj. Nombre: `S3 · Z2 #1 · 20'`. En el reloj: Entrenamiento › Entrenamientos.
- Cada paso del plan = un paso por **tiempo** (sus minutos) con objetivo **zona de FC del reloj** (Z2 → zona 2).
  La nota del paso va como nota del paso. Sin calentar/enfriar extra (igual que el plan).
- Pasos de caminata (novato) = paso de recuperación en zona 1.

### 12.3 Cuándo y cómo
- A mano: Pedro le dice a Claude "manda la semana al reloj" (o `/reloj`), o lo ofrece la revisión semanal.
- Antes de subir, **borra solo los que mandó antes** (guarda sus IDs en `data/reloj.json`, que no se publica);
  nunca toca entrenamientos que Pedro hizo a mano. Si un borrado falla, sigue y avisa.
- Si alguno de los que mandó antes **sigue pendiente** (esa sesión del plan no está hecha según el dashboard),
  pregunta antes de borrarlo: "Z2 #2 de la semana 3 sigue pendiente, ¿la borro?". Los ya hechos se borran sin preguntar.
- Limpieza inicial (2026-11-25, ya hecha): se borraron los 29 entrenamientos viejos de Runna. Quedó "Benchmark Run",
  de un plan de Garmin Coach que ya no existe (Garmin no deja borrarlo: "ATP plan id"); no estorba. Borrar todo no
  es parte del script.
- Muestra qué va a mandar y pide confirmación; al final dice qué quedó en el reloj.
- Si Garmin rechaza la sesión (tokens vencidos), dice cómo volver a hacer el login.

### 12.4 No cambia
- La página, `data.json` y la Personal API siguen igual. Los IDs de Garmin de `data/reloj.json` nunca salen al sitio.
