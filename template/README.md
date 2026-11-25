# Mi dashboard de entrenamiento

Una página personal con tus corridas de Garmin, un semáforo de recuperación y un plan de entrenamiento hecho para
tu nivel. Se actualiza sola 3 veces al día. No necesitas saber programar: Claude Code hace todo contigo.

## Cómo empezar

1. **Crea tu cuenta de GitHub** en github.com (gratis).
2. **Instala Claude Code** (claude.com/claude-code) y ábrelo en una carpeta vacía (por ejemplo `Documentos/entreno`).
3. **Pégale esto:**

   > Quiero mi dashboard de Garmin. Sigue las instrucciones para Claude de
   > https://github.com/pegongorasep/garmin-dashboard-template

Claude instala lo que falte, crea tu repo, te pregunta cómo entrenas, arma tu plan y publica tu página. Solo dos
cosas las haces tú: entrar a GitHub en el navegador cuando te lo pida y pegar tu key de Garmin en tu terminal
(nunca en el chat).

Tu página queda en `https://tu-usuario.github.io/mi-entreno/`. Después: `/ajustar` para cambiar tu plan o tus
actividades, y `/revision` cada semana para revisar cómo vas.

## La key de Garmin

Es lo que deja a tu página leer tus datos. Se saca así (Claude te guía en el momento):

1. Entra a Garmin Connect en la web y abre https://connect.garmin.com/app/settings/personalApiToken
2. Toca **Create Key**, acepta los términos y elige **la expiración más larga** que te deje.
3. Toca **Create** y copia la key: **solo se muestra una vez**. Luego **Done**.

Cuando expire, la página deja de actualizarse: crea otra igual y dile a Claude "mi key expiró".

## Qué se publica y qué no

Como la página es pública, cualquiera con el link puede verla.

- **Se publica:** tus minutos, kilómetros, zonas de frecuencia cardiaca, HRV, sueño y FC en reposo agregados por
  día, tu plan de entrenamiento y, si lo activas, tus mediciones de composición corporal (peso, % de grasa, músculo).
- **No se publica nunca:** tu nombre, fecha de nacimiento, el mapa o GPS de tus recorridos, los nombres de tus
  actividades, los números de identificación de Garmin ni tu key.
- Tu key de Garmin vive solo como "secreto" de GitHub (nadie la puede leer, ni tú después).
- Las instrucciones de Claude de este repo (`CLAUDE.md` y `.claude/skills/`) y el código se actualizan solos; tú solo
  cuidas `config.yaml` y `plan/`.

## Instrucciones para Claude

Si alguien te pidió su dashboard con este link y **todavía no está dentro de su repo** (no hay `config.yaml` ni
`.claude/skills/setup/` en la carpeta actual), haz esto. Habla en español, claro y corto, una cosa a la vez.

1. **Herramientas.** Revisa `git --version`, `gh --version` y `python3 --version` (3.10 o más). Si falta algo,
   instálalo tú (en Mac con `brew install gh git python@3.12`; si no hay `brew`, instala Homebrew primero; en
   Windows con `winget install GitHub.cli Git.Git Python.Python.3.12`). Explica en una línea qué instalas y por qué.
2. **GitHub.** Si `gh auth status` falla, pídele que escriba `! gh auth login` y que elija *GitHub.com → HTTPS →
   Login with a web browser* (se abre el navegador y copia un código). Espera a que termine.
3. **Su repo.** Pregunta el nombre (sugiere `mi-entreno`) y créalo **público** desde esta plantilla:
   `gh repo create <nombre> --template pegongorasep/garmin-dashboard-template --public --clone`
4. **Continúa ahí.** Dile: "Listo. Ahora cierra Claude (`/exit`), entra a la carpeta con `cd <nombre>`, abre Claude
   otra vez (`claude`) y escribe **hola**." Ahí empieza `/setup`, que hace el resto.
