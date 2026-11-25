# Mi dashboard de entrenamiento (Garmin)

Este repo publica una página personal con tus corridas, tu recuperación y tu plan de entrenamiento, usando tus datos
de Garmin Connect. Quien lo usa normalmente no programa: explícale todo en español, claro y corto, y haz tú los
cambios en los archivos.

## De dónde viene el código

El código (el "motor") NO vive aquí: está en `pegongorasep/garmin-dashboard`, etiqueta `stable`. Cada publicación
(3 veces al día) lo baja y construye la página. Por eso este repo solo tiene lo personal.

**Archivos tuyos (los editas tú o Claude):**
- `config.yaml`: nivel, tipo de plan, actividades, fecha de inicio. Ver `config.example.yaml`.
- `plan/plan.json`: el plan de semanas, generado desde `config.yaml` (no lo edites a mano).
- `plan/inbody.json`: opcional, mediciones de composición corporal.

**Archivos administrados (NO los edites, el workflow los sobreescribe):**
- `CLAUDE.md` y `.claude/skills/` (estas instrucciones).
- `.github/workflows/`: los cambia el dueño del motor; si hace falta actualizarlos, avisa a la persona.

## Qué hacer al empezar

- Si **no existe `config.yaml`**, ofrece correr `/setup` (configuración inicial paso a paso).
- Para cambiar el plan o las actividades: `/ajustar`. Para la revisión semanal: `/revision`.

## Si la página dejó de actualizarse

Mira el último run: `gh run list -L 3` y `gh run view <id> --log-failed`. Si dice "Garmin rechazó la key" (o "mi key
expiró"), la key venció: que cree otra en https://connect.garmin.com/app/settings/personalApiToken (**Create Key**,
la expiración más larga, copiarla, decir *listo*) y tú la guardas desde el portapapeles como en `/setup` paso 6. Luego `gh workflow run
deploy.yml` y `gh run watch`. Si es otro error, explícalo en palabras simples.

## Reglas de seguridad (siempre)

1. **La key de Garmin nunca va en el chat.** La persona solo la copia en Garmin y dice *listo*; tú la mandas del
   portapapeles a GitHub sin imprimirla (comandos en `/setup`, paso 6). Si la pega en la conversación, dile que la
   borre en Garmin Connect y cree otra.
2. **Nunca leas, imprimas ni copies `.env`** (si existe).
3. **No publiques GPS, IDs de Garmin ni nombres de actividades.** El sitio solo muestra números agregados; no
   agregues campos nuevos al `data.json`.
4. **Nunca pongas un token de GitHub en el sitio ni en archivos del repo.**
5. No hagas `git push --force` ni borres el repo; pregunta antes de cualquier cosa destructiva.

## Ver la página en tu computadora (opcional)

```sh
git clone --depth 1 --branch stable https://github.com/pegongorasep/garmin-dashboard .motor   # .motor/ está en .gitignore
python3 -m venv .venv && .venv/bin/pip install pyyaml
# data/ viene de Garmin; sin datos igual se ve el primer día
GARMIN_USER_DIR=. .venv/bin/python .motor/dashboard/build.py
.venv/bin/python -m http.server -d .motor/site 8000      # abre http://localhost:8000
```

`GARMIN_USER_DIR=.` le dice al motor que tus archivos (config, plan, data) están en esta carpeta.
Para generar el plan: `GARMIN_USER_DIR=. .venv/bin/python .motor/plan/gen_plan.py`.

## Flujo de cambios

Edita `config.yaml` → regenera el plan si cambió algo del plan → `git add -A && git commit` → `git pull --rebase` →
`git push` → `gh workflow run deploy.yml` → `gh run watch`. La página queda en
`https://<usuario>.github.io/<repo>/`.
