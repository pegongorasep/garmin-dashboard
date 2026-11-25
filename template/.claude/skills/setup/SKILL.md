---
name: setup
description: Configuración inicial del dashboard: pregunta nivel, actividades y fecha, escribe config.yaml, genera el plan y publica la página. Úsala si no existe config.yaml o la persona dice "hola" o "empezar".
---

# /setup: configuración inicial

Habla en español, claro y corto, sin jerga. Una o dos preguntas a la vez. **Nunca pidas ni muestres la key de Garmin
en el chat ni leas `.env`.** Si algo falla, explica qué pasó y qué hacer, sin culpar.

## 1. Requisitos
- `gh auth status`. Si falla, pide que la persona escriba `! gh auth login` (GitHub.com → HTTPS → navegador).
- `python3 --version` (3.10 o más). Si falta, instálalo (Mac: `brew install python@3.12`; Windows:
  `winget install Python.Python.3.12`). En Windows usa `.venv\Scripts\python` donde aquí dice `.venv/bin/python`.
- Que el repo exista en GitHub: `gh repo view --json nameWithOwner,visibility`. Debe ser **público** (Pages gratis);
  si es privado, `gh repo edit --visibility public --accept-visibility-change-consequences` (pregunta antes).

## 2. Nivel
Pregunta: cuánto tiempo lleva corriendo y cuántas veces por semana; cuántos minutos corre seguidos sin caminar;
si hace HIIT, CrossFit o algo intenso. Clasifica y **sugiere**; la persona acepta o cambia:

| Nivel | Señales | Sugerencia |
|---|---|---|
| novato | < 3 meses o no corre 20' seguidos | `intensidad: solo_z2`, `caminatas: true` si no corre 20' seguidos |
| intermedio | 20–40' seguidos, 1–3 veces/semana | `intensidad: z2_poca_z3` |
| corredor | 45'+ seguidos, 3+ veces/semana por 3+ meses | `intensidad: calidad`; pregunta qué tipos quiere (`tempo_z3`, `threshold`, `intervalos`, `progresivo`, `fartlek`; si no elige, rotan los 5) |

En el config pon siempre `variada: true` (una corrida por semana es "variada": formatos como espiga, pirámide o escalera según su nivel; es lo que verá en la pestaña Plan). Solo ponla en `false` si la persona prefiere todo continuo.

Si hace algo intenso, dilo así: "Tu 20 % intenso ya sale de tu {actividad}; te sugiero `solo_z2`". Cualquiera puede
elegir `solo_z2`.

## 3. Minutos de arranque (`base_min`)
Con lo que corre hoy, sin pasarse: `z2` ≈ lo que corre cómodo; `larga` ≈ su corrida más larga reciente.
Mejor quedarse corto: el plan sube solo.

## 4. Perfil
Pregunta y anota: el título de su página (sugiere "Mi entreno"; va en `perfil.titulo`); edad y FC máxima si la sabe (si no, déjalo: se usa 220 - edad y el reloj la corrige);
zona horaria; qué otras actividades hace y **cómo las registra en Garmin** (no preguntes en qué días: solo se marca lo que Garmin registró) (para mapear los tipos:
`strength_training`, `hiit`, `cycling`, `yoga`...; máximo 4 categorías, `intensa: true` a las intensas); días de
pierna (solo si quiere el aviso de la larga tras pierna); fecha de inicio (el próximo lunes); y si tiene InBody (`inbody: true`; luego pasa la foto de la hoja y tú
llenas `plan/inbody.json` con el formato de `plan/inbody.json` del motor, `.motor/plan/inbody.json`).

## 5. Escribir y generar
- Escribe `config.yaml` (usa `config.example.yaml` como guía).
- Clona el motor: `git clone --depth 1 --branch stable https://github.com/pegongorasep/garmin-dashboard .motor`
  y `python3 -m venv .venv && .venv/bin/pip install pyyaml`.
- `GARMIN_USER_DIR=. .venv/bin/python .motor/plan/gen_plan.py` genera `plan/plan.json`.
  Si marca un error de configuración, corrige `config.yaml`.
- Muestra un resumen de las **primeras 4 semanas** (minutos por sesión) y pide aprobación. Ajusta si no le gusta.

## 6. La key de Garmin
Dale estos pasos, uno por uno, y espera a que confirme:
1. "Entra a Garmin Connect en la web (con tu cuenta) y abre https://connect.garmin.com/app/settings/personalApiToken"
2. "Toca **Create Key**, acepta los términos y elige **la expiración más larga** que te deje."
3. "Toca **Create** y copia la key (solo se muestra una vez). **No la pegues en el chat.** Toca **Done**."
4. Con la key todavía copiada: "Escribe aquí `! pbpaste | gh secret set PERSONAL_API_KEY` y da Enter" (Mac). En
   Windows: `! powershell -c "Get-Clipboard | gh secret set PERSONAL_API_KEY"`. Nunca `! gh secret set` solo: el `!`
   no deja escribir y guardaría la key vacía.

Revisa con `gh secret list` que aparezca `PERSONAL_API_KEY` (sin valor: GitHub no lo muestra). La prueba real es la
primera publicación (paso 7): si dice "Garmin rechazó la key", la key se copió mal; que la copie otra vez y repita. Pregunta qué
expiración eligió y dile: "Cuando expire, la página deja de actualizarse; crea otra igual y dime 'mi key expiró'."
Si pegó la key en el chat, dile que la borre en esa misma página de Garmin y cree otra.

## 7. Publicar
0. Ajusta los 3 `cron` de `.github/workflows/deploy.yml` (están en UTC) para que caigan ~7:00, 13:00 y 19:00 en
   su zona horaria. Es el único cambio permitido en ese archivo.
1. Activa Pages: `gh api -X POST repos/{owner}/{repo}/pages -f build_type=workflow`; si ya existe,
   `gh api -X PUT repos/{owner}/{repo}/pages -f build_type=workflow`.
2. `git add -A && git commit -m "Configuración inicial" && git pull --rebase && git push`.
3. `gh workflow run deploy.yml` y `gh run watch` hasta que termine (1–3 minutos).
4. Da el link: `https://{owner}.github.io/{repo}/`. Explícale que el primer día puede verse vacío: Garmin tarda
   unas horas en mandar el historial, y que se actualiza solo 3 veces al día.

Si el run falla, lee el error con `gh run view --log-failed` (sin mostrar secretos) y explícalo.
