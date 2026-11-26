# Login v2: Google + código por correo + invitación a instalar (acordado con Pedro el 2026-11-26)

Revisar el código actual con grep/offset:
- `web/auth.py`: invitaciones, LigaLogin, sesiones.
- `web/app.py`: /entrar, /entrar/liga, /invitacion.
- `web/oauth.py`: la cookie `COOKIE_VOLVER` y `volver_seguro`, que sirven para regresar al conector de IA después de entrar. Debe seguir funcionando con los dos métodos nuevos.

## Decisiones
- **Google («Continuar con Google») es la entrada principal.** Sigue exigiendo invitación: no hay cuentas sin ella.
- **Respaldo por correo:** un **código de 6 dígitos** que se escribe en la misma pantalla. Reemplaza a la liga más el botón «Entrar» (la liga deja de enviarse).
- **Sin contraseñas. Sin Apple.**
- **Invitación a instalar:** después de entrar, por cualquiera de los dos métodos, preguntar una vez si se quiere instalar la app.

## L1: «Login: Continuar con Google (con invitación)»
- **Configuración:**
  - Ajustes `GOOGLE_CLIENT_ID` y `GOOGLE_CLIENT_SECRET`, vacíos por defecto. Si están vacíos, el botón de Google no aparece y todo lo demás funciona igual.
  - URL de retorno: `BASE_URL/entrar/google/vuelta`.
- **Flujo:**
  - `GET /entrar/google?inv=<token opcional>` redirige a Google con `state`, `nonce` y PKCE S256 (en una cookie HttpOnly corta, 10 minutos). Scope `openid email`.
  - El retorno valida `state`, intercambia el código y verifica el ID token con el JWKS de Google (`jwt.PyJWKClient`; pyjwt ya está instalado). Revisa `iss`, `aud`, `exp`, `nonce` y `email_verified=true`. Sin Authlib, salvo que ya esté instalado.
- **Cómo se identifica la cuenta:**
  - por `google_sub` (columna nueva, única y nula, en Usuario; requiere migración);
  - si no, por correo verificado (entonces guarda `google_sub`);
  - si no, y hay una invitación válida (`inv`), crea la cuenta con ese correo y gasta la invitación;
  - si no, muestra «Necesitas una invitación» y no crea nada.
- **Botones:**
  - `/entrar` y `/invitacion/<token>` muestran primero «Continuar con Google», con los macros del sistema. La página de invitación pasa `inv`.
  - En Ajustes (o `/privacidad`, donde quede más simple): «Ligar mi cuenta de Google», para cuando el correo de Google es distinto al de la cuenta. Requiere sesión y usa el mismo flujo con `ligar=1`.
- **Después de entrar:** respetar `COOKIE_VOLVER` (conector) con `volver_seguro`. Si no hay cookie, seguir el destino de L3; mientras L3 no exista, ir a `/`, o a `/bienvenida` si falta el onboarding.
- **Pruebas (simular el intercambio de token y el JWKS):**
  - invitación más Google crea la cuenta;
  - Google sin invitación y sin cuenta se rechaza;
  - una cuenta existente se identifica por correo y guarda su sub;
  - state malo, nonce malo y `email_verified=false` se rechazan;
  - ligar una cuenta de Google;
  - la redirección al conector sigue funcionando.
- **Documentación:** los pasos para que Pedro cree el cliente OAuth van en `docs/DUDAS.md` (login v5) y en el resumen.

## L2: «Login: código de 6 dígitos por correo»
- **Código:**
  - Al pedirlo desde `/entrar` o `/invitacion/<token>` se manda un correo con un código de 6 dígitos, válido 10 minutos, guardado solo como hash. Reusar la tabla LigaLogin o crear otra.
  - Máximo 5 intentos por código y el límite por hora actual. Comparar en tiempo constante.
- **Misma pantalla:** tras pedirlo, la página muestra el campo del código. Se envía con CSRF a `POST /entrar/codigo`, que crea la sesión.
- **Mensajes:** mantener el mensaje neutro (no revelar si la cuenta existe).
- **Liga vieja:** ya no se envía. `/entrar/liga/<token>` puede seguir funcionando hasta que venzan las ligas existentes, o quitarse. Elegir lo más simple y anotarlo en DUDAS.
- **Después de entrar:** igual que L1 (cookie del conector, luego L3).
- **Pruebas:**
  - el código correcto crea una sesión;
  - 5 códigos incorrectos lo bloquean;
  - un código vencido falla;
  - el código sirve una sola vez;
  - invitación más código crea la cuenta.
- **Texto del correo:** «Tu código para entrar a Ahí la Llevas: 123456 (vale 10 minutos)».

## L3: «Login: invitación a instalar la app»
- **Después de entrar** (Google o código), cuando no hay cookie del conector y el onboarding está completo, ir a `/instalar?siguiente=/`. Validar `siguiente` como ruta relativa, igual que `volver_seguro`.
- **`/instalar`** es una página del sistema con macros:
  - **Android/Chrome:** botón «Instalar app» que usa `beforeinstallprompt`.
  - **iPhone:** instrucciones cortas, «Toca Compartir → Agregar a pantalla de inicio», con el ícono `compartir` si existe.
  - **Siempre:** «Ahora no» va a `siguiente`.
- **JS mínimo, en un archivo estático aparte:**
  - Si la página ya corre como app instalada (`display-mode: standalone`) o la persona ya dijo «Ahora no» (localStorage, con try/catch), redirige a `siguiente` de inmediato.
- **Pruebas:** tras entrar con código o Google, la redirección va a `/instalar`; un `siguiente` malo va a `/`.

Un agente y un commit por pieza, en orden L1 → L2 → L3. Sin capturas. Reporte de máximo 10 líneas.
