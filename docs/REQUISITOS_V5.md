# v5: Ahí la Llevas — web con usuarios (solo amigos, por invitación) — aprobado por Pedro (2026-11-25)

Plan de construcción: [`PLAN_V5.md`](PLAN_V5.md).

Fecha: 2026-11-25. Una sola web con cuentas. **El repo de cada amigo es solo el tubo de datos; la web es el
cerebro.** El motor de Python (`dashboard/`, `plan/`) se reutiliza; el sitio JS sigue pintando un `data.json`
por usuario.

## 1. Decisiones (Pedro, 2026-11-25)

| Tema | Decisión |
|---|---|
| Quién entra | Solo amigos de Pedro, **por invitación**. Sin registro público. Gratis, sin anuncios. |
| Datos de Garmin | **Híbrido**: cada amigo tiene su repo privado con su Personal API key como secreto; su GitHub Action baja sus datos, quita lo sensible y los manda a la web. **La key nunca sale de su cuenta** (los términos de la Personal API prohíben compartirla con terceros, Pedro incluido). |
| Coach IA | La web funciona **sin IA** (botones). Quien quiera conecta **su propia IA (Claude o ChatGPT)** por un **conector MCP** (estándar abierto, un solo conector para ambos); a Pedro le cuesta $0. **Sin resumen semanal con IA.** Claude Code no es necesario. |
| Coach humano | Un usuario da **acceso de coach** a otro (p. ej. a Pedro): un solo nivel, **ver y editar** plan y ajustes; se quita cuando quiera. El coach usa la web o su IA (las herramientas aceptan el atleta). El atleta sigue usando su propia IA y sus botones. |
| Avisos | Todo cambio hecho por el coach o por la IA queda en el historial y el atleta ve un **aviso en la web con botón de deshacer** ("Pedro cambió tu semana 7"). Sin correos. |
| Invitaciones | **Solo Pedro** (único admin) crea invitaciones. |
| InBody | **Formulario** en la web; quien tenga IA le pasa la foto y la IA lo llena con el conector. |
| Plan | **Plan vivo**: metas (carrera con fecha, base aeróbica), bloques encadenados, eventos (viaje, enfermedad, lesión) que ajustan semanas. |
| Social | **Privado**, pero el modelo de datos permite compartir después (el acceso de coach es el primer caso). |
| Deportes | Correr + otras actividades (CrossFit, gym…) que cuentan como carga y en el 80/20, como hoy. |
| Reloj | `/reloj` se queda **solo de Pedro y local**. |

## 2. Flujo de datos

```
 Garmin ──(key del amigo)──▶ Repo privado del amigo (Actions, 3 veces al día)
                               │  baja datos, quita IDs/nombres/GPS, firma con OIDC de GitHub
                               ▼
                             Web (FastAPI + Postgres)
                               │  config, plan vivo, motor dashboard/, data.json por usuario
                     ┌─────────┼──────────┐
                     ▼         ▼          ▼
                 El amigo   Coach      Su IA: Claude o ChatGPT (conector MCP)
```

- **Repo del amigo** = archivo chiquito que llama `motor.yml@stable` del repo de Pedro. Todo el código de
  bajada vive en el repo de Pedro: pedir datos nuevos = cambiar `garmin_connect.py` y mover `stable`; nadie toca
  su repo.
- El archivo del amigo nace con todo lo necesario (`id-token: write` para OIDC) y **un solo secreto**
  (`PERSONAL_API_KEY`). Si algún día hay que cambiarlo, la web avisa con un botón directo a GitHub.
- La web verifica el token **OIDC de GitHub Actions** (repo = el que conectó ese usuario). Sin tokens extra.
- Cada subida dice qué versión del motor corrió; si un repo se atrasa o no manda datos en 24 h, la web avisa
  (Actions apagado, key vencida) con los pasos para arreglarlo.
- **Historial**: la web puede pedir "baja el historial de X" y la siguiente corrida lo incluye.
- **Actualizar ahora**: liga a "Run workflow" del repo del amigo.
- Los cálculos los hace la web con los datos guardados: un cambio de plan se ve **al instante**.
- Repos privados: ~180 min/mes de Actions de 2,000 gratis.

## 3. Qué ofrece la web

1. **Cuenta**: liga por correo (sin contraseñas). Invitación = liga de un solo uso que crea Pedro.
2. **Onboarding** (~5 min, reemplaza `/setup`): cuenta → botón "Crear mi copia en GitHub" (plantilla, privada)
   → pegar la key de Garmin en los secretos del repo (liga directa, pasos con capturas, sin comandos) → activar
   Actions → la web confirma "ya llegaron tus datos" → preguntas del plan (nivel, intensidad, actividades, fecha
   de inicio, sensor: banda o muñeca).
3. **Dashboard**: lo de hoy (Hoy · Plan · Progreso · Ayuda), por usuario, privado.
4. **Ajustes** (reemplaza `/ajustar`): lo que hoy cambia `config.yaml`.
5. **Plan vivo**: botones "agregar carrera", "voy de viaje", "estoy enfermo/lastimado", "repetir semana".
6. **Sesiones flexibles**: pasos y repeticiones libres (p. ej. Larga con pausas 8'/1' y el resto continuo);
   escalera de trote/caminata por persona (3/1 → 5/1 → 8/1 → 12/1 → continuo).
7. **Sensor**: con pulso de muñeca no se muestran las métricas que dependen de banda (p. ej. deriva).
8. **Coach**: dar/quitar acceso; el coach ve la lista de sus atletas.
9. **Privacidad**: aviso, consentimiento expreso, descargar mis datos, borrar mi cuenta.
10. **Conector MCP** (Claude o ChatGPT): leer resumen/semana/sesiones, hacer los mismos cambios que los botones
    y capturar InBody desde una foto. Un coach puede usarlo sobre sus atletas.
12. **Historial y deshacer**: cada cambio guarda quién (atleta, coach, IA) y qué; aviso en la web con deshacer.
13. **Admin (Pedro)**: crear invitaciones, ver usuarios y si su repo manda datos.
11. **PWA**: instalable en el celular.

## 4. Reglas que no cambian

- Lógica en Python; el JS solo pinta; textos en español; sin librerías de JS.
- Lo que sube el repo y el `data.json` salen de **listas blancas** (sin IDs de Garmin, nombres de actividades,
  GPS, nombre ni fecha de nacimiento). El `data.json` ya **no es público**: solo su dueño y sus coaches.
- La web **nunca recibe ni guarda keys de Garmin**.
- Compatibilidad: claves nuevas con valor por defecto; repos atrasados siguen funcionando.

## 5. Legal (LFPDPPP 2025)

- FC, HRV, sueño y composición corporal = **datos sensibles** → consentimiento expreso (casilla al registrarse,
  guardada con fecha y versión del aviso).
- Aviso de privacidad integral + simplificado: datos, cuáles son sensibles, finalidades, encargados (hosting,
  correo, GitHub, Garmin) y cómo ejercer derechos ARCO (correo + botones de descargar/borrar).
- "No es consejo médico" y reglas de seguridad fijas (dolor = parar). Atribución "datos de Garmin".
- Al borrar la cuenta se borran sus datos de la web; su repo es suyo.

## 6. Stack

| Pieza | Elección |
|---|---|
| Backend | Python 3.12 + FastAPI; importa `dashboard/` y `plan/` |
| Base de datos | Postgres + SQLAlchemy + Alembic; config y plan como JSON |
| Páginas | Sitio JS actual (dashboard) + plantillas Jinja2 (login, onboarding, ajustes); sin librerías de JS |
| Login | Liga por correo con Resend |
| Subida de datos | Endpoint que verifica OIDC de GitHub Actions (PyJWT) |
| Conector | SDK oficial `mcp` de Python montado en el mismo FastAPI + OAuth (Authlib) |
| Hosting | **$0/mes**: Google Cloud Run (web, se duerme sin uso) + Neon Postgres Free + respaldo nocturno a Cloud Storage; dominio `ahilallevas.com` en Cloudflare (Pedro, 2026-11-25). Plan B: Render Starter ~7 USD/mes |
| Pruebas | pytest + pruebas de API; gate en GitHub Actions antes de desplegar |
| Código | Mismo repo, carpeta `web/`; `template/` pasa a ser el tubo |

## 7. Fases tentativas (se detallan en PLAN_V5.md)

1. Servidor, login por invitación y dashboard por usuario (con los datos de Pedro).
2. Repos como tubo: OIDC, subida, onboarding guiado.
3. Ajustes y plan vivo (metas, eventos, sesiones flexibles).
4. Acceso de coach.
5. Conector MCP con OAuth.
6. Privacidad: aviso, consentimiento, descargar y borrar.
7. Migrar a Pedro y a los amigos actuales.

## 8. Pendiente

1. ~~Nombre~~: **Ahí la Llevas** (Pedro, 2026-11-25). Dominio: `ahilallevas.com` (comprado por Pedro en Cloudflare, 2026-11-25).
2. Confirmar detalles del conector MCP en ChatGPT al planear esa fase.
3. ~~Aprobación final~~ (Pedro, 2026-11-25) → [`PLAN_V5.md`](PLAN_V5.md).
