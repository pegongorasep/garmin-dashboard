# Mi dashboard de entrenamiento

Una página personal con tus corridas de Garmin, un semáforo de recuperación y un plan de entrenamiento hecho para
tu nivel. Se actualiza sola 3 veces al día. No necesitas saber programar: Claude Code hace la configuración contigo.

## Cómo empezar (5 pasos)

1. **Crea tu cuenta de GitHub** (github.com) e instala [Claude Code](https://claude.com/claude-code) y la
   herramienta `gh` (cli.github.com). Entra con `gh auth login`.
2. **Crea tu repo**: en la página de esta plantilla toca **Use this template → Create a new repository** y déjalo
   **público** (es lo que permite tener tu página gratis).
3. **Clónalo** en tu computadora (`gh repo clone tu-usuario/tu-repo`) y abre Claude Code dentro de esa carpeta.
4. **Escribe "hola"** (o `/setup`). Claude te hará unas preguntas sobre cómo corres y qué otro ejercicio haces,
   armará tu plan y publicará tu página. En un momento te pedirá la *Personal API key* de Garmin: la escribes tú
   en tu terminal, nunca en el chat.
5. **Listo.** Tu página queda en `https://tu-usuario.github.io/tu-repo/`.

Después: `/ajustar` para cambiar tu plan o tus actividades, y `/revision` cada semana para revisar cómo vas.

## Qué se publica y qué no

Como la página es pública, cualquiera con el link puede verla.

- **Se publica:** tus minutos, kilómetros, zonas de frecuencia cardiaca, HRV, sueño y FC en reposo agregados por
  día, tu plan de entrenamiento y, si lo activas, tus mediciones de composición corporal (peso, % de grasa, músculo).
- **No se publica nunca:** tu nombre, fecha de nacimiento, el mapa o GPS de tus recorridos, los nombres de tus
  actividades, los números de identificación de Garmin ni tu key.
- Tu key de Garmin vive solo como "secreto" de GitHub (nadie la puede leer, ni tú después).
- Las instrucciones de Claude de este repo (`CLAUDE.md` y `.claude/skills/`) y el código se actualizan solos; tú solo
  cuidas `config.yaml` y `plan/`.
