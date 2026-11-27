# Investigación: cómo generar planes de carrera seguros y que sí mejoren (Ahí la Llevas)

Fecha: 2026-11-26. Es solo investigación: no cambié código. Las referencias numeradas [n] están al final.

**Resumen en 6 líneas**

1. Para principiantes y para quien ya hace CrossFit, **casi todo el running debe ser suave (Z1–Z2)**. La calidad (Z3+) se gana: no se elige.
2. El nivel **sale de Garmin** (frecuencia reciente, trote continuo más largo, minutos por semana), más **una sola pregunta en lenguaje llano**: "¿cuánto puedes trotar sin parar, platicando?".
3. Progresar **por tiempo, no por distancia**. El tope que más importa es el **de cada sesión**: ninguna sesión debe pasar de ~110 % de la más larga de los últimos 30 días [2]. Sumar volumen semanal de 10–20 % está bien, y más de 30 % en dos semanas es peligroso [3][4].
4. Novatos: **escalera trote/caminata** que empiece en 1' de trote y 1½–2' de caminata (Couch to 5K [9]). Hoy la escalera empieza en 3/1.
5. El plan **se adapta a lo que la persona hace**: si cumple, sube; si cumple a medias, repite la semana; si falta, baja un escalón.
6. El código actual **no usa `nivel` para nada**. Además el onboarding fuerza `variada: true` y deja preseleccionado `z2_poca_z3`. Por eso tu amiga novata tuvo Z3 desde la semana 1 (lo comprobé con una simulación, sección 4).

---

## 1. Teoría (con evidencia)

### 1.1 Distribución de intensidad (polarizada, piramidal, 80/20)

| Hallazgo | Fuente |
|---|---|
| En subélite, ~80 % del tiempo en Z1 (bajo VT1) mejoró más un 10 km que ~67 % en Z1 (−157 s contra −121 s en 5 meses). | Esteve-Lanao, Foster, Seiler y Lucía 2007 [5] |
| En recreativos, polarizado y "entre umbrales" mejoraron el 10K de forma parecida. Solo en un subgrupo que sí se polarizó la mejora fue mayor. | Muñoz et al. 2014 [6] |
| Meta-análisis: el polarizado sube más el VO2pico en intervenciones de **<12 semanas**. Con >12 semanas, todos los modelos se igualan, y no gana en las demás medidas de rendimiento. | Oliveira et al. 2024 [7] |
| Polarizado contra umbral (RCTs): ventaja pequeña del polarizado. | Rosenblat et al. 2019 [8] |
| 80/20 (Fitzgerald) es una aproximación por **tiempo**. "Bajo" significa debajo de VT1, o sea el talk test: puedes hablar en frases completas. | 80/20 Endurance [21] |

**Lo que implica para la app**

- **Novato y base corta:** ~95–100 % suave. El estímulo para ellos es correr más tiempo, y cualquier trote ya es estímulo. La NLstart2run encontró que **más intensidad la semana previa se asocia a más lesiones** en novatos [15].
- **Intermedio con base:** pirámide suave, ~85–90 % Z1–Z2, ~10 % Z3 y casi nada de Z4. Una sola sesión de calidad por semana.
- **Corredor con meta:** 80/20 por tiempo. 1–2 sesiones de calidad.
- **Gente de CrossFit (clave para tus usuarios):** el WOD ya es intensidad alta, casi toda en Z4–Z5. Si se cuenta todo su entrenamiento, alguien con 3 WODs por semana ya está muy por encima del 20 % intenso. **Para ellos el running debe ser casi todo Z2** y la calidad de correr debe ser opcional y rara. Es la principal razón para no ofrecer calidad "porque sí".

### 1.2 Cuándo meter calidad y de qué tipo

No hay ensayos que digan "a la semana N". El consenso de los textos (Daniels, Fitzgerald, Pfitzinger, Higdon) es **primero frecuencia y tiempo continuo, luego intensidad**. Daniels pide una fase I de "fundamentos y prevención de lesiones", de al menos varias semanas solo suave, antes de meter calidad. También pide mantener un nivel de volumen ~3 semanas antes de subirlo [22]. Para orden de introducción, de menos a más agresivo:

| Paso | Tipo | Qué es | Para quién |
|---|---|---|---|
| 0 | Solo Z2 | Continuo o trote/caminata | Todos al empezar |
| 1 | Aceleraciones (strides) | 4–6 × 15–20" rápidos y relajados al final de una Z2, con 1' suave entre cada una. Por el retraso de la FC no suben la zona. | Desde base corta, si corre 20' continuos |
| 2 | Picos Z3 opcionales / fartlek suave / progresivo | ≤6' de Z3 en total (hoy: `pasos_con_picos`, `variada` con tope de 6' y 20 %) | Intermedio con ≥6–8 semanas de base |
| 3 | Tempo Z3 | 2 × 8–15' | Intermedio con ≥30' continuos y ≥90'/semana |
| 4 | Threshold (cruise intervals) Z4 | 4–5 × 5' | Corredor, o intermedio con meta 10K+ |
| 5 | Intervalos VO2 Z4–Z5 | 6–8 × 2–3' | Corredor con meta 5K/10K, ≤1 vez por semana |

### 1.3 Progresión semanal: la regla del 10 % y lo que dice la evidencia

| Estudio | Qué encontró |
|---|---|
| **Buist 2008** (GRONORUN, RCT, 532 novatos) | Un programa de 13 semanas con la regla del 10 % **no redujo** lesiones frente a uno estándar de 8 semanas (20.8 % contra 20.3 %) [1]. |
| **Nielsen 2014** (JOSPT, 873 novatos con GPS) | Subir **>30 % en 2 semanas** se asoció a más lesiones "de distancia". No hubo diferencia clara entre <10 % y 10–30 % [3]. |
| **Damsted 2019** (medio maratón) | Subir 20–60 % por semana se asoció a más lesiones que <20 %, pero solo en los primeros 21 días [4]. |
| **Frandsen 2025** (BJSM, 5,205 corredores Garmin, 588k sesiones) | El predictor fue **la sesión**: correr >10 % más que la sesión más larga de los últimos 30 días subió el riesgo (HR 1.64 en picos pequeños, 2.28 en grandes). **El cociente semana a semana no predijo nada** [2]. |
| NLstart2run (1,696 novatos) | Más intensidad la semana previa se asoció a más lesiones [15]. |

**Tiempo contra distancia.** Para recreativos conviene **minutos**. Así el estímulo no depende del ritmo: un novato a 8:00/km y uno a 5:00/km reciben la misma carga interna. Además, el plan y el reloj ya trabajan en minutos. Los estudios usan km, pero la relación se traslada igual al tiempo.

**Regla práctica:** volumen semanal +10–15 % (hasta +20 % si es <90'/semana, con tope absoluto de +15'), ninguna sesión >110 % de la más larga en 30 días, y mantener 2–3 semanas antes de subir de nivel (Daniels).

### 1.4 La larga: qué fracción de la semana

- Daniels: la larga ≤25–30 % del volumen semanal, o 150', lo que sea menor [23].
- Con 3 días por semana esa regla es imposible: la larga queda en ~40 %. Lo razonable es **≤40 % con 3 días, ≤33 % con 4 y ≤30 % con 5+**, y **la larga ≤2× la Z2 típica de la semana**.
- La larga es justo la sesión que más tiende a "pasar de 110 %". Debe subir de a +5' y no más de 10 % de la mayor larga reciente [2].

### 1.5 Ciclos de descarga (3:1, 2:1)

- La evidencia controlada es escasa. Son heurísticas de coach. Fitzgerald recomienda 3:1 en base y para carreras largas, 2:1 en fase específica o carreras cortas, y **masters: cada tercera semana de descarga**. Friel usa microciclos de 9 días para atletas mayores [24].
- Hay poca evidencia, pero es barato y tiene sentido. Propuesta: **3:1 por defecto, y 2:1 con ≥50 años o con ≥3 sesiones intensas no-running por semana** (CrossFit o HIIT). En la escalera de novatos no hace falta descarga formal: los escalones repetidos cumplen esa función.
- Una descarga es −25–35 % de minutos, **misma frecuencia**, sin calidad. Hoy el código ya hace −20 a −35 % aprox., y está bien.

### 1.6 Trote/caminata (run/walk)

- **Couch to 5K (NHS)**: 9 semanas, 3 días [9].
  - S1: 1'/1½' ×8. S2: 1½'/2' ×6. S3: 1½/1½, 3/3 ×2. S4: 3/1½, 5/2½ ×2.
  - S5: 5/3/5/3/5, luego 8/5/8, luego **20' continuos**. S6: 5/3/8/3/5, 10/3/10, 25'.
  - S7: 25'. S8: 28'. S9: 30'. Siempre con 5' de caminata para calentar y 5' para enfriar.
- Ojo: el salto de S5 (8') a 20' continuos es muy grande. Mucha gente se atora ahí, así que la app debe permitir **repetir y subir por desempeño, no por calendario**.
- Galloway: el run/walk **no se ha demostrado** que reduzca lesiones (AAFP: "ningún estudio lo ha validado") [10]. Un estudio de 42 maratonistas (2016) halló tiempos iguales con menos dolor muscular y fatiga.
- Para retorno por hueso (Warden 2016) el protocolo usa caminar 9 / trotar 1 ×3 y avanza **solo si no hay síntomas ni durante, ni después, ni al día siguiente** [18].

### 1.7 Zonas de FC

**FC máx estimada**

- **Tanaka: 208 − 0.7·edad** (meta-análisis de 351 estudios, 18,712 sujetos). Error típico de ~10–11 lpm, contra ~12 de 220−edad [11]. En corredores recreativos 220−edad tiende a sobreestimar en jóvenes y subestimar en mayores. Hoy el código usa 220−edad.
- Con ±10 lpm de error, **la Z2 puede quedar una zona arriba o abajo**. Por eso conviene corregir con datos.

**Mejores fuentes, en orden**

1. FC máx observada **con banda** en una carrera o esfuerzo máximo (ya existe `fc_max_correa_desde`).
2. `maxHeartRateUsed` de Garmin (ya sube en `hr_zones`).
3. LTHR de Garmin: requiere banda. En un Fenix 7 fue "suficiente para recreativos", aunque subestima el rendimiento en el umbral [13].
4. Tanaka.

**Talk test**

- Poder hablar cómodo coincide aproximadamente con VT1 (Persinger 2004). Un estudio de 2011 lo ubica más cerca del umbral de lactato [12].
- Es la mejor ayuda para novatos y para días de calor. La regla sería: "si no puedes decir una frase completa, baja o camina".

**Muñeca contra banda**

- La muñeca va bien en estado estable (±15 lpm), pero falla en cambios de ritmo y al aire libre. La banda se acerca más al ECG [14].
- En los primeros 5–10' la muñeca suele "engancharse" a la cadencia.
- Para quien usa muñeca: ignorar picos de los primeros 5' y usar promedios de 30–60 s antes de avisar "te pasaste".

**Problemas de las zonas para novatos**

- **Deriva cardiaca**: la FC sube 10–20 lpm en 30' a ritmo constante, sobre todo con **calor y humedad** (Mérida) [16].
- El novato que obedece un techo estricto termina caminando cada vez más, y eso desmotiva.
- Ajustes razonables:
  - en los primeros 10' se permite un margen;
  - con calor, manda el talk test y el techo sube 5 lpm, o se acepta caminar sin que cuente como "fallo";
  - lo que se evalúa es **la tendencia en semanas** (ritmo a la misma FC, % trotado), no cada sesión.
- Karvonen (60–70 % de la reserva para Z2) es razonable si la FC en reposo es buena. Garmin da `restingValue` diario, ya en `daily`.

### 1.8 Frecuencia (días por semana)

- Wenger y Bell 1986: en personas poco en forma **2 días por semana ya suben el VO2máx**. Con VO2 >50 hacen falta ≥3. Las mayores ganancias están en ~4 sesiones de 35–45' [17].
- Para novatos, 3 días no consecutivos es el estándar (C25K, Higdon). Más días cortos son mejores que pocos días largos, por la regla de "no pasar de la sesión más larga".
- La ACSM recomienda progresar gradual en tiempo, frecuencia e intensidad para adherencia y seguridad [25].
- **Orden de progresión sugerido:** frecuencia (3 → 4), luego duración, luego intensidad.

### 1.9 Combinar con CrossFit y fuerza

**Interferencia**

- Wilson 2012: correr junto con pesas atenuó fuerza e hipertrofia.
- Schumann 2022 (meta-análisis actualizado): **no interfiere** con fuerza máxima ni con hipertrofia. Sí atenúa la **potencia explosiva**, sobre todo **en la misma sesión** [19].
- Para un recreativo la interferencia es menor. Lo que importa es la **fatiga** y el riesgo de llegar con piernas muertas a la sesión clave.

**Separación**

- ≥6 h entre fuerza y cardio; idealmente otro día [20].
- **Nunca larga ni calidad al día siguiente de pierna pesada.** Ya existe un aviso en `metrics.py:478`, pero el plan no programa con esto.

**La fuerza es protectora**

- Lauersen 2014: el entrenamiento de fuerza reduce las lesiones deportivas a **<⅓** (RR 0.315) [26]. El CrossFit de tus usuarios es un activo.

**Regla para la app:** días de pierna o WOD = días duros. La semana de correr pone las Z2 cortas el mismo día que un WOD suave o en días libres, y la larga o la calidad lejos de la pierna (≥1 día).

### 1.10 Taper para 5K, 10K y medio maratón

- Bosquet 2007 (meta-análisis): lo óptimo es **2 semanas, con el volumen bajando 41–60 % de forma exponencial, sin bajar intensidad ni frecuencia** [27]. Un meta-análisis de 2023 en fondistas llega a lo mismo (≤21 días).
- Guías de coach: 5K/10K de 7–10 días, medio de 10–14 días, maratón de 19–22 días [28].
- Para recreativos con poco volumen el taper es corto: **5K 1 semana (−30–40 %), 10K 7–10 días (−40 %), medio 2 semanas (−25 % y luego −50 %)**. Si hubo calidad, se conserva un toque corto (p. ej., 3–4 × 1' a ritmo de carrera). Si no hubo, se mantienen las Z2 cortas.

### 1.11 Regreso tras enfermedad, lesión o viaje

**Enfermedad**

- La "regla del cuello" no tiene evidencia sólida [29].
- La guía de retorno escalonado (BJSM, Elliott 2020, actualizada en 2022) pide **mínimo 5 días** con síntomas leves arriba del cuello. Con **fiebre o síntomas en pecho** no se corre hasta 24–48 h sin fiebre, y se vuelve por etapas: caminar, Z2 corta, Z2 normal, intensidad.

**Desentrenamiento**

- Con <4 semanas sin estímulo, el VO2máx cae rápido en entrenados (~4–14 %) y **las ganancias recientes se pierden por completo con >4 semanas** [30]. Para novatos, una pausa de 3–4 semanas equivale a reiniciar varios escalones.

**Lesión**

- *Tejido blando*: modelo de monitoreo de dolor (Silbernagel/Thomeé). Se acepta dolor ≤3–5/10 durante, si baja pronto y no aparece a la mañana siguiente [18].
- *Hueso* (dolor puntual en tibia o pie): **dolor 0/10**, parar y ver médico, y regresar con trote/caminata por pasos [18].
- La app **no debe diagnosticar**. Solo pregunta "¿te duele hoy?" y aplica un protocolo de vuelta conservador.

**Tabla de retorno propuesta (por días sin correr)**

| Días sin correr | Qué hacer |
|---|---|
| ≤7 | Repetir la última semana completada |
| 8–14 | Volver 2 semanas atrás (o 1 escalón). La primera semana al 70 %, sin calidad. |
| 15–28 | Volver ~½ del plan recorrido, o 2 escalones; 2 semanas sin calidad |
| >28 | Reclasificar el nivel con los datos nuevos (como plan nuevo) |
| Lesión | Siempre trote/caminata al reanudar; sube solo sin dolor al día siguiente |

### 1.12 Factores de riesgo en corredores nuevos

| Factor | Evidencia |
|---|---|
| Ser novato | 17.8 lesiones/1000 h contra 7.7 en recreativos (≈2.3×) [31] |
| Edad mayor, IMC alto, molestias musculoesqueléticas previas, sin experiencia corriendo | NLstart2run [15] |
| IMC >30 y >3 km la primera semana | Más riesgo; NNT 8.5 [32] |
| Lesión previa de correr | El predictor más fuerte en fondistas [33] |
| Picos de una sesión >10 % de la máxima en 30 días | Frandsen 2025 [2] |
| Pronación (con calzado neutro) | **No** aumentó el riesgo [34] |

---

## 2. Qué preguntar (mínimo y en lenguaje llano)

### 2.1 Lo que se infiere de Garmin (sin preguntar)

Datos que ya suben al tubo (`dashboard/paquete.py`): `activities` (duración, distancia, FC media y máx, tiempo por zona, tipo), `activity_details.splits` (tramos de **trote/caminata**) y `serie` (FC y metros por segundo), `historial_corridas`, `daily.restingValue` y `hr_zones.maxHeartRateUsed`.

| Dato | Cómo se calcula | Para qué |
|---|---|---|
| Frecuencia reciente | Carreras por semana en las últimas 4 y 8 semanas | Nivel, días sugeridos |
| Semanas activas | Semanas con ≥1 carrera de las últimas 8 | Consistencia, desentrenamiento |
| **Trote continuo más largo** | Tramo más largo sin caminata (de `splits` tipo trote, o de `serie` con velocidad > umbral de caminar), últimos 30–60 días | Pregunta clave sin preguntarla; base de la Z2 y la larga |
| Sesión más larga en 30 días | `max(duration)` de carreras | **Tope de la larga** (≤110 %) |
| Minutos típicos | Mediana de duración y suma semanal (4 semanas) | Volumen de arranque |
| % caminado | Minutos de caminata / total en las carreras | Escalón inicial |
| FC máx | Máx con banda en 6 meses > `maxHeartRateUsed` > Tanaka | Zonas |
| FC en reposo | Mediana de 14 días de `restingValue` | Karvonen |
| Ritmo a FC Z2 | Ritmo medio en tramos con FC en Z2 | Seguimiento de mejora (el `fc_fija` actual) |
| Fuerza / CrossFit | Días de la semana con `strength_training`/`hiit` (8 semanas) | Prellenar "días de pierna" y días duros |
| Carreras (`es_carrera`) | Ya existe | Experiencia y nivel corredor |
| VO2máx de Garmin | **No sube hoy**. Se podría agregar `vO2MaxValue` del resumen a la lista blanca. | Solo como tendencia, no para clasificar (es impreciso: +8 % en Fenix 3) [13] |

### 2.2 Cuestionario recomendado (≤6 preguntas, con ramas)

Cada pregunta trae **prellenado lo que dice Garmin**, con un texto tipo "vimos que…". La persona solo confirma.

| # | Pregunta (texto para la persona) | Opciones | Condición |
|---|---|---|---|
| 1 | **¿Qué quieres lograr?** | Empezar a correr · Correr más y más fácil · Prepararme para una carrera | Siempre |
| 1b | ¿Qué carrera y cuándo? | 5 km · 10 km · 21 km · otra; fecha | Solo si eligió carrera |
| 2 | **¿Cuántos días a la semana puedes correr?** | 2 · 3 · 4 · 5 (sugerido según la frecuencia reciente) + cuáles días | Siempre |
| 3 | **Hoy, ¿cuánto tiempo puedes trotar sin parar, a un ritmo en el que puedes platicar?** | Todavía no puedo trotar seguido · menos de 5 min · 5–10 · 10–20 · 20–30 · 30–45 · más de 45 | **Se omite** si Garmin tiene ≥4 carreras en 6 semanas (se muestra "vimos que tu trote seguido más largo fue de 18 min. ¿Es correcto?") |
| 4 | **¿Haces otro entrenamiento fuerte?** | No · Sí: ¿qué días hay pierna o WOD pesado? (chips prellenados) | Siempre (prellenado) |
| 5 | **¿Te duele algo al correr o tuviste una lesión en los últimos 3 meses?** | No · Tuve, ya estoy bien · Sí, me duele ahora | Siempre. "Me duele ahora": aviso de ver a un profesional y plan de retorno en trote/caminata |
| 6 | **¿Quieres incluir algunas partes más rápidas?** | No, todo suave (recomendado) · Sí, un poco | **Solo si** el nivel calculado es Base o Corredor **y** hay ≥8 semanas consistentes (o la meta es carrera con nivel ≥ Base) |

No se pregunta (ya se sabe o va en "opciones avanzadas"): edad (perfil), FC máx (Garmin), sensor (Garmin, o "¿usas banda en el pecho?" solo en avanzadas), semanas (salen de la meta o 12 por defecto), inicio (el próximo lunes), tipos de calidad (los elige el motor).

### 2.3 Cuando la respuesta y los datos no cuadran

| Situación | Regla |
|---|---|
| Dice **más** de lo que muestra Garmin (dice 30' y su mayor tramo es 12') | Se usan los datos. Mensaje: "Te pondremos 15', y si te sale fácil subes rápido". Sin datos recientes (sin reloj en carreras): se confía en la respuesta, pero la primera semana es de "prueba" al 80 %. |
| Dice **menos** que los datos (dice 10' y corre 40') | Se usan los datos, recortados al 90 % ("ya vienes de más; empezamos en 35'"). |
| Datos viejos (última carrera hace >4 semanas) | Se baja un nivel. A >8 semanas, el nivel queda como máximo en "Base corta". |
| Contesta "me duele ahora" | Nivel forzado a trote/caminata, sin calidad, con aviso médico. |
| Mucho CrossFit (≥3 días duros) y pide calidad | Se permite solo picos o fartlek suave, con aviso: "tu CrossFit ya es tu día intenso". |
| Meta de carrera con poco tiempo (menos semanas que el mínimo) | Se ofrece una distancia menor o "llegar trotando/caminando". No se comprime la progresión. |

---

## 3. Algoritmo estandarizado

### 3.1 Clasificación de nivel

Se toma `C` = trote continuo más largo (min), `F` = carreras por semana (promedio de 6 semanas), `V` = minutos por semana (promedio de 4 semanas) y `S` = semanas activas de las últimas 8.

| Nivel | Nombre para la persona | Reglas (se cumple cualquiera de la fila; se toma el **menor** nivel que encaje) |
|---|---|---|
| N0 | **Empezando** | C < 10 o F < 1 o sin carreras en 8 semanas |
| N1 | **Base corta** | 10 ≤ C < 25 o V < 75 o S < 4 |
| N2 | **Base** | C ≥ 25, F ≥ 2, V 75–150, S ≥ 6 |
| N3 | **Corredor** | C ≥ 50, F ≥ 3, V > 150, S ≥ 7 (y, ayuda, alguna carrera hecha) |

Ajustes: con lesión actual pasa a N0 en modo retorno; con >4 semanas sin correr se baja 1 nivel. El nivel **se recalcula cada bloque**, así nadie se queda en "novato" para siempre.

### 3.2 Plantillas de semana (por nivel y días)

Leyenda: **E** = Z2 fácil, **L** = larga, **Q** = calidad, **T/C** = trote/caminata, **A** = E + aceleraciones.

| Nivel | 2 días | 3 días | 4 días | 5 días |
|---|---|---|---|---|
| N0 | T/C · T/C | T/C · T/C · T/C (la última un poco más larga) | No se ofrece (máx. 3 hasta llegar a 20' continuos) | No |
| N1 | E · L | E · E · L | E · E · A · L | No se ofrece (máx. 4) |
| N2 | E · L | E · A/Q · L | E · Q · E · L | E · Q · E · E · L |
| N3 | E/Q · L | E · Q · L | E · Q · E · L | E · Q · E · Q* · L (*solo con meta) |

Reglas de días: nunca dos días seguidos para N0/N1. **L y Q no van el día después de pierna** y tampoco seguidas entre sí. Las E pueden ir el mismo día que un WOD suave, separadas ≥6 h.

### 3.3 Volumen inicial y progresión (en minutos)

| Nivel | Sesión E inicial | Larga inicial | Subida por semana de carga | Tope larga |
|---|---|---|---|---|
| N0 | Escalón según C (ver 3.6), 20–30' totales con caminata | La misma que las otras (+5' de caminata al final) | Por escalón (por desempeño) | — |
| N1 | min(C, 20), mínimo 10 | min(1.1·Lmax30, C + 10, 35) | E +0–5'; L +5' | ≤40 % semanal (3 días), ≤2× E |
| N2 | min(V/F·0.9, 35) | min(1.1·Lmax30, 60) | E +5' cada 2 semanas; L +5' | ≤35–40 %, ≤90' sin meta |
| N3 | según V | min(1.1·Lmax30, 90) | +5–10 % por semana | ≤30–33 %, ≤120' (≤150' medio/maratón) |

`Lmax30` es la sesión más larga en 30 días. Todas las cifras se redondean a 5'.

### 3.4 Cuándo se desbloquea Z3 / calidad

Se requieren **todas** estas condiciones:

| Condición | Valor |
|---|---|
| Nivel calculado | ≥ N2 (o N1 con meta 10K+ y ≥10 semanas de plan) |
| Semanas consistentes | ≥ 6–8 semanas seguidas con ≥80 % de sesiones hechas |
| Trote continuo | ≥ 30' en Z2 |
| Volumen | ≥ 90'/semana |
| Sin dolor | Sin evento de lesión en 8 semanas |
| Opt-in | La persona dijo "Sí, un poco" (pregunta 6) |

Escalera de calidad tras el desbloqueo (1 tipo nuevo por bloque, nunca dos peldaños de golpe):

| Bloque | Calidad (1 por semana, solo en semanas de carga) | Tope de tiempo intenso en la semana |
|---|---|---|
| 1 | Aceleraciones 4–6 × 15" (no cuentan como Z3) | — |
| 2 | Picos Z3 / fartlek suave / progresivo (≤6' Z3) | ≤5 % |
| 3 | Tempo Z3 2 × 8–12' | ≤10 % |
| 4+ (N3 o con meta) | Threshold 4 × 5' / intervalos 6 × 2' | ≤15–20 % |

Con ≥3 días de CrossFit o HIIT por semana, el tope baja un renglón.

### 3.5 Descargas

| Caso | Ciclo | Cómo |
|---|---|---|
| N0 en escalera | Sin descarga formal | Repetir escalón cuando cuesta |
| N1–N3, <50 años | 3:1 | Semana 4: −30 % minutos, misma frecuencia, sin Q |
| ≥50 años, o ≥3 WODs por semana | 2:1 | Semana 3: −25 % |
| Tras volver de pausa >7 días | La primera semana cuenta como descarga | |

### 3.6 Escalera trote/caminata (propuesta)

Se extiende la actual (`3/1, 5/1, 8/1, 12/1, continuo`) hacia abajo, con formato `trote/caminata` en minutos:

| Escalón | Trote / caminata | Bloque típico (sin calentar ni enfriar) | Entrada si C (min) = |
|---|---|---|---|
| E1 | 1 / 2 | 8 repeticiones (24') | "todavía no puedo" |
| E2 | 1 / 1 | 10 repeticiones (20') | < 3 |
| E3 | 2 / 1 | 7 repeticiones (21') | 3–5 |
| E4 | 3 / 1 | 6 repeticiones (24') | 5–8 |
| E5 | 5 / 1 | 4 repeticiones (24') | 8–12 |
| E6 | 8 / 1 | 3 repeticiones (27') | 12–18 |
| E7 | 12 / 1 | 2 repeticiones + 5' (30') | 18–25 |
| E8 | Continuo 20–30' | — | ≥ 25 (pasa a N1) |

- **Subir**: 3 sesiones del escalón hechas, sin dolor al día siguiente y con talk test ok (o ≥80 % del trote bajo el techo). Hoy `sugerir_subir_escalon` usa 2 semanas completas y está bien; con 3 días por semana, 1 semana basta.
- **Repetir**: si una sesión no se completa.
- **Bajar 1**: tras 8–14 días sin correr o con dolor leve. **Bajar 2**: con >14 días.
- Caminata a paso vivo. El trote a "ritmo de platicar" no tiene techo de FC estricto: el techo solo avisa.

### 3.7 Metas de carrera

| Distancia | Semanas mínimas desde N0 | desde N1 | desde N2 | desde N3 | Larga objetivo | Taper |
|---|---|---|---|---|---|---|
| 5 km | 9–12 (C25K) | 6–8 | 4–6 | 4 | 35–45' | 7 días, −30–40 % |
| 10 km | 16–20 | 10–12 | 8 | 6 | 60–75' | 7–10 días, −40 % |
| 21 km | No (primero 10K) | 16–20 | 12–14 | 10–12 | 100–120' | 14 días, −25 % y luego −50 % |
| 42 km | No | No | 18–20 (con ≥1 año corriendo) | 16–18 | 150' | 3 semanas |

Si no alcanzan las semanas, se ofrece "llegar con trote/caminata" o una distancia menor. La semana de carrera mantiene la frecuencia y quita la larga.

### 3.8 Adaptación por adherencia (cada lunes)

| Semana pasada | Acción |
|---|---|
| ≥80 % de sesiones hechas, sin días rojos | Avanzar |
| 50–79 %, o 2+ días rojos | **Repetir la semana** (hoy existe `semanas_repetidas` y el resumen sugiere repetir; hacerlo automático con un clic) |
| <50 % | Bajar 1 semana (o 1 escalón) |
| 0 sesiones, 1 semana | Repetir la anterior |
| ≥2 semanas sin correr | Tabla 1.11 |
| Larga hecha >110 % de la planeada | No pasa nada esta semana; la siguiente larga no sube |
| Muy fácil 3 semanas seguidas (FC baja, todo hecho) | Sugerir subir escalón o adelantar el desbloqueo (nunca automático) |

### 3.9 Guardarraíles (validaciones en `verificar`)

| Guardarraíl | Valor |
|---|---|
| Sesión más larga | ≤ 110 % de la mayor de los 30 días previos (en el plan y contra lo real) |
| Subida semanal de minutos (contra la última semana de carga) | ≤ 15 % (≤ 20 % o +15' si <90') |
| Rebote tras descarga | ≤ la última semana de carga + 5 % |
| Larga / semana | ≤ 40 % (3 días), ≤ 33 % (4), ≤ 30 % (5+) |
| Larga / E típica | ≤ 2.0× |
| Tiempo Z3+ semanal | 0 % (N0, N1, o sin desbloqueo); ≤ 10 % (N2); ≤ 20 % (N3) |
| Sesiones con Z3+ por semana | 0 (N0–N1), 1 (N2), ≤2 (N3 con meta y ≥5 días) |
| Z3+ en descarga o en semana 1 de cualquier plan | 0 |
| Pruebas máximas ("5 km a tope") | Solo N3, o N2 con calidad desbloqueada; si no, prueba a FC fija o trote continuo |
| Días seguidos | N0–N1: nunca; L/Q nunca el día después de pierna |

---

## 4. Crítica de `plan/gen_plan.py` (y del onboarding)

### 4.1 Simulación: la "novata" que crea hoy el onboarding

Usé la configuración que produce `web/onboarding.py:110` con los valores por defecto del formulario (`nivel: novato`, `intensidad: z2_poca_z3` preseleccionada, `variada: True` **forzada**, `z2: 20`, `larga: 40`, sin caminatas):

| Sem | Tipo | Sesiones (min) | Total | Min Z3 | Larga % |
|---|---|---|---|---|---|
| 1 | carga | z2 20 · **variada 20** · larga 40 | 80 | **3** | 50 % |
| 2 | carga | 20 · 20 · 45 | 85 | 4 | 53 % |
| 3 | carga | 20 · 25 · 50 | 95 | 5 | 53 % |
| 4 | descarga | 20 · 20 · 30 | 70 | 0 | 43 % |
| 5 | carga | 25 · 25 · 50 | 100 (+43 % contra la sem. 4) | 1 | 50 % |
| 9 | carga | 30 · 30 · 60 | 120 (+50 % contra la sem. 8) | 4 | 50 % |
| 11 | carga | 30 · 30 · 70 | 130 | 6 | 54 % |

Con `calidad` + intervalos, la semana 1 ya trae **6 × 2' en Z4** para cualquier nivel.

### 4.2 Problemas concretos

1. **`nivel` no se usa.** Solo se valida (`ajustes.py:198`) y se guarda. `gen_plan.py` no lo lee: un novato y un corredor reciben la misma tabla.
2. **Por qué la novata tuvo Z3 en la semana 1.** El onboarding pone `variada: True` siempre (`onboarding.py:111`) y el formulario preselecciona `z2_poca_z3` (`bienvenida.html:127`). Entonces `semana()` toma la rama `elif variada and intensidad != "calidad"`, y con `n_carga = 0` el primer tipo de `VARIADA_TIPOS["z2_poca_z3"]` es **"espiga"**, que lleva Z3. Los "picos" sí esperan al bloque 2 (`bloque >= 1`), pero la variada **no tiene esa espera**.
3. **Las entradas no tienen condiciones.** `calidad` se acepta con `nivel: novato`, y en la semana 1 da Z4. En el formulario se pueden marcar tipos de calidad con `solo_z2` (el backend los descarta, pero la UI confunde).
4. **La base es igual para todos (20'/40').** Una larga de 40' continuos en la semana 1 no es posible para quien no trota 10' seguidos, y las caminatas vienen **apagadas por defecto**.
5. **La escalera empieza en 3/1.** C25K empieza en 1/1½. Falta la parte baja para el verdadero principiante.
6. **La larga es ~50–54 % de la semana**, todas las semanas. Es 2–2.3× la Z2.
7. **La larga sube +5'/semana desde 40'** (+12.5 %, +11 %, +10 %…). Las primeras subidas pasan el umbral de 10 % de Frandsen 2025. Con bases chicas el escalado `redondea5` puede dar saltos relativos aún mayores (p. ej., base 15 da 15 → 20, +33 %).
8. **Rebote tras descarga de +43–50 %** en minutos semanales (sem. 4 → 5, sem. 8 → 9). Medido contra la semana de carga previa es moderado, pero conviene limitarlo.
9. **Siempre 3 corridas.** No hay pregunta de días por semana y no se usan `dias_pierna` para programar. Solo se usan para un aviso (`metrics.py:478`, `ayuda.py`).
10. **Progresión fija por calendario**: no mira lo que pasó. La adaptación existe, pero es manual (`repetir_semana`, `sugerir_subir_escalon`, el resumen de semana).
11. **Prueba "5 km a tope"** para cualquiera con `calidad`, incluido un novato.
12. **Zonas con 220−edad** por defecto (`ajustes.py:193`). Tanaka es más preciso, y una FC máx sobreestimada empuja la "Z2" hacia Z3 real en mayores de 40.
13. **Nunca más de 3 bloques** (se repite el 3), y al pasar a "siguiente bloque" la configuración no se recalcula con los datos.

### 4.3 Qué conservar (está bien hecho)

- `verificar()` como lugar de invariantes: se puede extender con los guardarraíles de 3.9, dependientes del nivel.
- La versión **"Suave"** de cada sesión (`easy`): excelente para días rojos.
- 3:1 con descargas sin calidad ni variada.
- Topes de la variada (Z3 ≤6' y ≤20 %, sin Z4), los "picos opcionales" desde el bloque 2 y `pasos_con_picos`.
- La escalera y `sugerir_subir_escalon` (subir por desempeño, solo sugerido).
- Las **pruebas** `fc_fija` y `trote_continuo`: son tests de campo seguros y miden justo lo que mejora en base aeróbica.
- El modelo de eventos de `plan_vivo.py`: una pausa no gasta semana, el viaje tiene 3 modos, la semana previa a carrera se suaviza y no hay dos descargas seguidas.
- `construir_plan`: las semanas pasadas no se tocan al rehacer el plan.

### 4.4 Cambios mínimos de alto impacto (si se quiere un parche antes del rediseño)

1. Onboarding: `variada` sin forzar a True, e `intensidad` por defecto `solo_z2`.
2. En `normalizar_config` o `generar`: si `nivel == "novato"`, forzar `intensidad = "solo_z2"` y `caminatas = True`. Con `intermedio` y `calidad`, solo threshold, tempo o progresivo.
3. Variada con Z3 solo desde el bloque 2 (igual que los picos).
4. Larga inicial = min(larga, 2 × z2); subida de larga ≤10 %.
5. Escalera con `1/2, 1/1, 2/1` antes de `3/1` (cambia el parseo de `trote_de`, porque hoy la caminata siempre es 1').

Por la regla de compatibilidad, cada clave nueva (`dias_semana`, `objetivo`, `nivel_auto`, `calidad_desbloqueada`) necesita un valor por defecto en `defaults.yaml` o en `cargar_config`.

---

## 5. Flujo propuesto: "Quiero un plan"

Principio: **el onboarding no pregunta nada del plan**. La persona entra, ve su Garmin y, cuando quiere, toca **"Quiero un plan"** (en Hoy y en Plan). La app **propone** y la persona **confirma o ajusta**. Respeta la regla de altura fija: cada pantalla reserva el espacio de la rama condicional (`em`/`lh`) y elegir no cambia la altura.

| Pantalla | Contenido | Lógica |
|---|---|---|
| **0. Lo que vimos** | Tarjeta: "En las últimas 6 semanas corriste **2 veces por semana**, tu trote seguido más largo fue de **18 min**, haces **CrossFit lun/mié/vie**". Botón **"Armar mi plan"**. | Sin datos de carreras: "Aún no vemos carreras en tu Garmin; te haremos una pregunta más". |
| **1. Tu meta** | 3 tarjetas: Empezar a correr · Correr más y más fácil · Prepararme para una carrera | Con "carrera" aparece la distancia y la fecha en la ranura reservada, con aviso si no alcanzan las semanas mínimas (3.7) y alternativa. |
| **2. Tus días** | "¿Cuántos días puedes correr?" (2–5, el sugerido marcado) y chips de días. Debajo, "días de pierna o WOD pesado" prellenados de Garmin. | N0: máximo 3. Se marcan en gris los días después de pierna para L/Q. |
| **3. Cuánto trotas hoy** | Solo si faltan datos: "¿Cuánto tiempo puedes trotar sin parar, a un ritmo en el que puedes platicar?" (7 opciones). Con datos: "Vimos 18 min. ¿Te parece bien?" Sí / "Puedo menos" / "Puedo más". | Conflictos según 2.3. |
| **4. ¿Algo te duele?** | No · Tuve algo, ya estoy bien · Sí, ahora | "Ahora": aviso y plan de retorno. |
| **5. Intensidad** | "¿Quieres incluir algunas partes más rápidas?" | **Solo aparece** si se cumple 3.4. Si no, la ranura dice "Por ahora todo suave: así se construye la base. Te avisaremos cuando estés lista/o para más" (misma altura). |
| **6. Vista previa** | Nombre del plan ("Base 12 semanas · trote/caminata 3/1 → continuo"). Gráfica fija de minutos por semana (barras carga/descarga). Las **2 primeras semanas en detalle**. Tres frases de "por qué así" ("todo suave porque…", "la larga sube de a 5'…", "si faltas, repetimos la semana"). Botones: **"Empezar el lunes 30"** · "Un poco más suave" · "Un poco más". | "Más suave" o "Un poco más" mueven ±1 escalón o ±10 % de volumen, **sin saltarse guardarraíles**. "Opciones avanzadas" (plegado) da acceso a lo de hoy (FC máx, sensor, tipos de calidad, semanas) para Pedro y usuarios avanzados, también con los guardarraíles. |
| **Después** | Cada lunes: "La semana pasada hiciste 3/3 → seguimos" o "2/3 → ¿repetimos la semana?" (un clic). Al terminar el bloque: se recalcula el nivel con los datos y se propone el siguiente (con desbloqueo de calidad si aplica). | 3.8 |

Formularios afectados: la sección p7 de `web/plantillas/bienvenida.html` pasa a ser solo "¿quieres un plan ahora o después?" (o se elimina). `#rehacer` en `plan.html` se convierte en este flujo, con "Opciones avanzadas" para los campos actuales.

---

## 6. Preguntas abiertas para Pedro

1. **¿El nivel es solo calculado, o la persona puede subirlo a mano?** Recomiendo: puede bajarlo libremente y subirlo solo desde "opciones avanzadas", con aviso.
2. **Días por semana:** ¿abrimos 2, 4 y 5 días ya, o seguimos en 3 y agregamos 4 después? Esto cambia `gen_plan` (hoy son 3 sesiones fijas) y el reloj (`reloj.py`).
3. **CrossFit = día duro siempre, o depende del tipo** (`strength_training` contra `hiit`)? ¿Usamos el RPE o el Training Effect de Garmin para decidir?
4. **Escalera:** ¿aceptas el formato `trote/caminata` con caminata variable (`1/2`, `1/1`, `2/1`) aunque cambie el parseo de `escalon`? (Las configuraciones viejas con `3/1` siguen siendo válidas.)
5. **Calor:** ¿subimos el techo de Z2 +5 lpm en días calurosos (habría que traer la temperatura) o solo usamos talk test y aceptamos más caminata?
6. **FC máx por defecto:** ¿cambiamos 220−edad por Tanaka? A las personas con plan ya hecho les movería las zonas. Opción: solo para planes nuevos.
7. **VO2máx de Garmin:** ¿lo agregamos a la lista blanca del tubo (`vO2MaxValue`) para mostrar tendencia? No clasificaría con él.
8. **Adaptación automática:** ¿la repetición de semana es automática o siempre un botón "¿repetimos?"? (Recomiendo el botón, con el default marcado.)
9. **Prueba final:** ¿quitamos "5 km a tope" para quien no sea N3, y usamos FC fija o trote continuo?
10. **Metas largas (21K/42K):** ¿las ofrecemos o las limitamos a 5K y 10K por ahora, dado el perfil de tus usuarios?
11. **Los planes vigentes** (la amiga novata y otros): ¿se regeneran desde la semana actual con las nuevas reglas, o solo aplican a planes nuevos?

---

## Referencias

1. Buist I. et al. *No effect of a graded training program on the number of running-related injuries in novice runners* (GRONORUN). AJSM 2008. https://research.rug.nl/en/publications/no-effect-of-a-graded-training-program-on-the-number-of-running-r/ · protocolo: https://link.springer.com/doi/10.1186/1471-2474-8-24
2. Frandsen J.S.B. et al. *How much running is too much? Identifying high-risk running sessions in a 5200-person cohort study*. BJSM 2025;59:1203–10. https://pmc.ncbi.nlm.nih.gov/articles/PMC12421110 · blog: https://blogs.bmj.com/bjsm/?p=11751
3. Nielsen R.O. et al. *Excessive progression in weekly running distance and risk of running-related injuries*. JOSPT 2014. https://vbn.aau.dk/da/publications/excessive-progression-in-weekly-running-distance-and-risk-of-runn · https://pmc.ncbi.nlm.nih.gov/articles/PMC4842282
4. Damsted C. et al. *The association between changes in weekly running distance and RRI preparing for a half marathon*. JOSPT 2019. https://events.lih.lu/crp/publication/the-association-between-changes-in-weekly-running-distance-and-running-related-injury-preparing-for-a-half-marathon-11906 · revisión: https://pmc.ncbi.nlm.nih.gov/articles/PMC9528699
5. Esteve-Lanao J., Foster C., Seiler S., Lucía A. *Impact of training intensity distribution on performance in endurance athletes*. JSCR 2007. https://abacus.universidadeuropea.com/entities/publication/7fbfa682-6302-499f-9a81-4e468521d082
6. Muñoz I. et al. *Does polarized training improve performance in recreational runners?* IJSPP 2014. https://pubmed.ncbi.nlm.nih.gov/23752040/
7. Oliveira P.S. et al. *Polarized training… systematic review and meta-analysis*. Sports Med 2024. https://pmc.ncbi.nlm.nih.gov/articles/PMC11329428
8. Rosenblat M.A. et al. *Polarized vs. threshold training intensity distribution… meta-analysis*. JSCR 2019. https://pubmed.ncbi.nlm.nih.gov/29182410/
9. NHS. *Couch to 5K running plan*. https://www.nhs.uk/better-health/get-active/get-running-with-couch-to-5k/couch-to-5k-running-plan
10. AAFP, *Tips from other journals* (walk-run no validado para lesiones). https://www.aafp.org/afp/2004/0401/p1781 · Galloway: https://runnersconnect.net/galloway-run-walk-run/
11. Tanaka H., Monahan K.D., Seals D.R. *Age-predicted maximal heart rate revisited*. JACC 2001. https://pubmed.ncbi.nlm.nih.gov/11153730/ · en maratonistas: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5862813/
12. Persinger R. et al. *Consistency of the talk test for exercise prescription*. MSSE 2004. https://paulogentil.com/pdf/Consistency%20of%20the%20talk%20test%20for%20exercise%20prescription.pdf · 2011: https://pubmed.ncbi.nlm.nih.gov/21774751/
13. Heiber et al. *Garmin Fenix 7 underestimates performance at the lactate threshold…* OAJSM 2024. https://www.dovepress.com/garmin-fnix-7-underestimates-performance-at-the-lactate-threshold-in-c-peer-reviewed-fulltext-article-OAJSM · Garmin LT: https://www8.garmin.com/manuals/webhelp/fenixchronos/EN-GB/GUID-1B0C9B93-01CD-4A0C-A30F-B815C0347159.html
14. Gillinov S. et al. *Variable accuracy of wearable heart rate monitors during aerobic exercise*. MSSE 2017. https://pubmed.ncbi.nlm.nih.gov/28709155/ · https://pmc.ncbi.nlm.nih.gov/articles/PMC5984393 · https://pmc.ncbi.nlm.nih.gov/articles/PMC7458324
15. Kluitenberg B. et al. *The NLstart2run study: incidence and risk factors of RRI in novice runners*. SJMSS 2015. https://research.rug.nl/en/publications/the-nlstart2run-study-incidence-and-risk-factors-of-running-relat/ · factores de entrenamiento: https://pure.amsterdamumc.nl/en/publications/the-nlstart2run-study-training-related-factors-associated-with-ru/
16. Deriva cardiaca: https://www.polar.com/en/guide/cardiac-drift-effect-on-training · desacople: https://www.trainingpeaks.com/learn/articles/aerobic-endurance-and-decoupling/
17. Wenger H.A., Bell G.J. *The interactions of intensity, frequency and duration of exercise training…* Sports Med 1986. https://pubmed.ncbi.nlm.nih.gov/3529283/
18. Retorno tras lesión: Warden 2016 (adaptado), BJSM blog: https://blogs.bmj.com/bjsm/2019/05/08/using-exercise-to-improve-bone-health-in-athletes-with-relative-energy-deficiency-in-sport/table-c-graded-return-to-run-program-for-bone-stress-injury-adapted-from-warden-et-al-2016 · modelo de dolor: https://runnersconnect.net/returning-from-running-injury/ · Stanford FASTR: https://fastr.stanford.edu/education/fastr-educational-graphics/wu-tsai-return-to-run-protocol_v1/
19. Schumann M. et al. *Compatibility of concurrent aerobic and strength training…* Sports Med 2022. https://pubmed.ncbi.nlm.nih.gov/34878640/ · Lundberg 2022: https://pmc.ncbi.nlm.nih.gov/articles/PMC9474354
20. Robineau J. et al. *Specific training effects of concurrent aerobic and strength exercises depend on recovery duration*. JSCR 2016. https://pubmed.ncbi.nlm.nih.gov/25546450/ · NSCA: https://www.nsca.com/education/articles/ptq/to-cardio-or-not-to-cardio-that-is-the-question-a-brief-review-of-concurrent-training/
21. 80/20 Endurance, zonas y pruebas: https://www.8020endurance.com/when-and-how-to-test-zones/
22. Daniels J. *Daniels' Running Formula* (fase I, mantener el volumen ~3 semanas): resúmenes en https://www.stack.com/?p=299744 y https://runnerclick.com/?p=27988
23. La larga como % semanal (Daniels): https://www.outsideonline.com/health/running/training-advice/running-101/mastering-the-long-run/ · https://marathonhandbook.com/mab/how-long-should-your-long-run-be/
24. Fitzgerald/Friel, masters: https://trainingpeaks.com/blog/training-for-masters-runners-part-1-the-extended-microcycle · https://www.goodreads.com/author_blog_posts/5083590-aging-matching-the-mesocycle-to-your-recovery
25. Garber C.E. et al. *ACSM Position Stand: Quantity and quality of exercise…* MSSE 2011. https://pubmed.ncbi.nlm.nih.gov/21694556/
26. Lauersen J.B. et al. *The effectiveness of exercise interventions to prevent sports injuries*. BJSM 2014. https://pubmed.ncbi.nlm.nih.gov/24100287/ · 2018: https://pubmed.ncbi.nlm.nih.gov/30131332/
27. Bosquet L. et al. *Effects of tapering on performance: a meta-analysis*. MSSE 2007. https://pubmed.ncbi.nlm.nih.gov/17762369/ · fondistas 2023: https://pmc.ncbi.nlm.nih.gov/articles/PMC10171681/
28. Duración del taper por distancia: https://newsnetwork.mayoclinic.org/?p=390101 · https://runnersconnect.net/5k-taper/ · https://www.outsideonline.com/health/running/racing/race-strategy/the-art-and-science-of-the-5k-10k-taper/
29. Retorno tras enfermedad respiratoria (regla del cuello, BJSM 2022): https://blogs.bmj.com/bjsm/wp-json/wp/v2/posts/10084 · revisión: https://pmc.ncbi.nlm.nih.gov/articles/PMC8805104 · Elliott 2020 (doi 10.1136/bjsports-2020-102637)
30. Mujika I., Padilla S. *Cardiorespiratory and metabolic characteristics of detraining in humans*. MSSE 2001. https://pubmed.ncbi.nlm.nih.gov/11252068/ · 2000: https://pubmed.ncbi.nlm.nih.gov/10966148/
31. Videbæk S. et al. *Incidence of running-related injuries per 1000 h of running…* Sports Med 2015. https://pubmed.ncbi.nlm.nih.gov/25951917/
32. Nielsen R.O. et al. *Running distance in week one and injury among obese novice runners*. https://pmc.ncbi.nlm.nih.gov/articles/PMC4060311
33. Van der Worp M. et al. (revisión de factores de riesgo en fondistas). https://pmc.ncbi.nlm.nih.gov/articles/PMC4473093/
34. Nielsen R.O. et al. *Foot pronation is not associated with increased injury risk in novice runners wearing a neutral shoe*. BJSM 2014. https://bjsm.bmj.com/content/bjsports/48/6/440.full.pdf
