"""Rutas y arranque de la web. `crear_app()` arma la app (las pruebas le pasan su propia base y su propio correo)."""
import logging
import secrets
import re
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ajustes import ConfigError

from . import ROOT, admin, ajustes_web, auth, calculo, coach, correo, cuenta, google, mcp_servidor, oauth, onboarding, plan_web, tubo
from .privacidad import VERSION_AVISO
from .config import WEB, Settings, desde_entorno
from .db import crear_motor, crear_sesiones
from .modelos import Usuario
from .permisos import puede_ver

log = logging.getLogger("web")
SITE = ROOT / "site"
# Archivos del sitio que se sirven tal cual. `data.json` NO está aquí a propósito: sale de /data.json, por usuario.
# `catalogo.html` tampoco está aquí: solo sale por /diseno, para el admin.
ESTATICOS_SITE = {"base.js": "text/javascript", "app.js": "text/javascript", "charts.js": "text/javascript",
                  "iconos.js": "text/javascript", "componentes.js": "text/javascript", "vistas.js": "text/javascript",
                  "styles.css": "text/css", "tokens.css": "text/css", "componentes.css": "text/css",
                  "sw.js": "text/javascript", "manifest.webmanifest": "application/manifest+json",
                  "icono-192.png": "image/png", "icono-512.png": "image/png", "icono-maskable-512.png": "image/png",
                  "apple-touch-icon.png": "image/png"}
FUENTES = {"Lexend-latin.woff2"}
PIE_SITIO = ('<footer class="pie"><p>Esto no es consejo médico: si algo duele, para.</p>'
             '<p>Datos de Garmin · <a href="/privacidad">Aviso de privacidad</a></p></footer>'
             '<script>if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js").catch(function () {});</script>')
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def crear_app(settings: Settings | None = None, motor=None, enviar=None, reloj=None) -> FastAPI:
    settings = settings or desde_entorno()
    motor = motor or crear_motor(settings.database_url)
    sesiones = crear_sesiones(motor)
    enviar = enviar or correo.enviar
    app = FastAPI(title="Ahí la Llevas", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.motor, app.state.sesiones, app.state.enviar = settings, motor, sesiones, enviar
    app.state.reloj = reloj or (lambda: datetime.now(timezone.utc))   # las pruebas lo cambian para fijar «hoy»
    plantillas = Jinja2Templates(directory=str(WEB / "plantillas"))
    app.mount("/estaticos", StaticFiles(directory=str(WEB / "estaticos")), name="estaticos")

    @app.middleware("http")
    async def cabeceras(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        if not request.url.path.startswith("/estaticos"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def get_db():
        db = sesiones()
        try:
            yield db
        finally:
            db.close()

    def actual(request: Request, db=Depends(get_db)):
        return auth.usuario_de_sesion(db, request.cookies.get(auth.COOKIE_SESION))

    # --- ayudas de plantillas y CSRF ---

    def render(request: Request, nombre: str, status: int = 200, **ctx) -> Response:
        cookie = request.cookies.get(auth.COOKIE_CSRF)
        nueva = cookie is None
        cookie = cookie or secrets.token_urlsafe(24)
        resp = plantillas.TemplateResponse(request, nombre, {"csrf": auth.campo_csrf(settings.secret_key, cookie),
                                                             "settings": settings, **ctx}, status_code=status)
        if nueva:
            resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=settings.cookie_segura,
                            samesite="lax", path="/")
        return resp

    async def formulario(request: Request):
        """Campos del formulario POST, con el token CSRF ya verificado (403 si falla)."""
        form = await request.form()
        if not auth.csrf_valido(settings.secret_key, request.cookies.get(auth.COOKIE_CSRF), form.get("csrf")):
            raise HTTPException(403, "Token CSRF inválido")
        return form

    def poner_sesion(resp: Response, valor: str) -> None:
        resp.set_cookie(auth.COOKIE_SESION, valor, max_age=auth.DIAS_SESION * 86400, httponly=True,
                        secure=settings.cookie_segura, samesite="lax", path="/")

    def mandar_codigo(db, usuario) -> None:
        codigo = auth.crear_codigo(db, settings.secret_key, usuario)
        if codigo:
            enviar(settings, usuario.correo, "Tu código para entrar a Ahí la Llevas",
                   f"Tu código para entrar a Ahí la Llevas: {codigo} (vale 10 minutos)\n\n"
                   "Si no lo pediste tú, ignora este correo.")

    # --- salud ---

    @app.get("/salud")
    def salud():
        return {"ok": True}   # sin tocar la base: Cloud Run lo usa como sonda de arranque

    # --- cuentas ---

    @app.get("/entrar")
    def entrar_form(request: Request, usuario=Depends(actual)):
        if usuario:
            return RedirectResponse("/", 303)
        return render(request, "entrar.html")

    @app.post("/entrar")
    async def entrar(request: Request, db=Depends(get_db)):
        form = await formulario(request)
        u = auth.buscar_por_correo(db, str(form.get("correo", "")))
        if u:
            mandar_codigo(db, u)
        return render(request, "entrar.html", mensaje=auth.MENSAJE_LIGA, correo=auth.normalizar_correo(str(form.get("correo", ""))))   # siempre lo mismo

    @app.post("/entrar/codigo")
    async def entrar_codigo(request: Request, db=Depends(get_db)):
        form = await formulario(request)
        correo_in = str(form.get("correo", ""))
        u = auth.gastar_codigo(db, settings.secret_key, correo_in, str(form.get("codigo", "")))
        if u is None:
            return render(request, "entrar.html", status=400, mensaje=auth.MENSAJE_LIGA,
                          correo=auth.normalizar_correo(correo_in), error="Código incorrecto o vencido. Pide uno nuevo si hace falta.")
        resp = RedirectResponse(oauth.volver_seguro(request.cookies.get(oauth.COOKIE_VOLVER, "")), 303)
        poner_sesion(resp, auth.crear_sesion(db, u))
        resp.delete_cookie(oauth.COOKIE_VOLVER, path="/")
        return resp

    @app.get("/entrar/liga/{token}")
    def liga_form(request: Request, token: str, db=Depends(get_db)):
        # GET solo muestra el botón: los escáneres de correo abren las ligas y gastarían el token
        return render(request, "liga.html", no_valida=auth.liga_vigente(db, token) is None)

    @app.post("/entrar/liga/{token}")
    async def liga(request: Request, token: str, db=Depends(get_db)):
        await formulario(request)
        u = auth.gastar_liga(db, token)
        if u is None:
            return render(request, "liga.html", status=400, no_valida=True)
        volver = request.cookies.get(oauth.COOKIE_VOLVER, "")
        resp = RedirectResponse(oauth.volver_seguro(volver), 303)   # conexión de una IA a medias
        poner_sesion(resp, auth.crear_sesion(db, u))
        resp.delete_cookie(oauth.COOKIE_VOLVER, path="/")
        return resp

    @app.get("/invitacion/{token}")
    def invitacion_form(request: Request, token: str, db=Depends(get_db)):
        inv = auth.invitacion_vigente(db, token)
        return render(request, "invitacion.html", no_valida=inv is None, nota=inv.nota if inv else None, token=token)

    @app.post("/invitacion/{token}")
    async def invitacion(request: Request, token: str, db=Depends(get_db)):
        form = await formulario(request)
        correo_in = str(form.get("correo", ""))
        if auth.invitacion_vigente(db, token) is None:
            return render(request, "invitacion.html", status=400, no_valida=True)
        if not auth.correo_valido(correo_in):
            return render(request, "invitacion.html", status=400, nota=None, token=token, error="Escribe un correo válido.")
        u = auth.aceptar_invitacion(db, token, correo_in) or auth.buscar_por_correo(db, correo_in)
        if u:
            mandar_codigo(db, u)
        return render(request, "invitacion.html", mensaje=auth.MENSAJE_LIGA, correo=auth.normalizar_correo(correo_in))   # igual exista o no la cuenta

    @app.get("/salir")
    def salir_form(request: Request):
        return render(request, "salir.html")

    @app.post("/salir")
    async def salir(request: Request, db=Depends(get_db)):
        await formulario(request)
        auth.cerrar_sesion(db, request.cookies.get(auth.COOKIE_SESION))
        resp = RedirectResponse("/", 303)
        resp.delete_cookie(auth.COOKIE_SESION, path="/")
        resp.headers["Clear-Site-Data"] = '"cache"'   # el service worker guarda el último data.json: no dejarlo en un equipo compartido
        return resp

    @app.get("/privacidad")
    def privacidad(request: Request):
        return render(request, "privacidad.html", version=VERSION_AVISO)

    tubo.montar(app, get_db, settings)
    onboarding.montar(app, get_db, actual, render, formulario, settings)
    ajustes_web.montar(app, get_db, actual, render, formulario, settings)
    plan_web.montar(app, get_db, actual, render, formulario, settings)
    coach.montar(app, get_db, actual, render, formulario, settings)
    oauth.montar(app, get_db, actual, render, formulario, settings)
    oauth.montar_conexiones(app, get_db, actual, render, formulario, settings)
    cuenta.montar(app, get_db, actual, render, formulario, settings)
    admin.montar(app, get_db, actual, render, formulario, settings)
    google.montar(app, get_db, actual, render, settings, poner_sesion)
    mcp_servidor.montar(app, settings)

    # --- dashboard por usuario ---

    @app.get("/")
    def inicio(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return render(request, "inicio.html")
        e = onboarding.estado(db, usuario)
        if not (e["consentimiento"] and e["ajustes"]):
            return RedirectResponse("/bienvenida", 303)
        html = (SITE / "index.html").read_text().replace("</main>", PIE_SITIO + "</main>", 1)
        return HTMLResponse(html)

    @app.get("/diseno")
    def diseno(usuario=Depends(actual)):
        """Catálogo del sistema de diseño: solo el admin; a los demás (y sin sesión) un 404 como si no existiera."""
        if usuario is None or not usuario.es_admin:
            raise HTTPException(404)
        return FileResponse(SITE / "catalogo.html", media_type="text/html")

    def data_de(db, usuario, atleta_id: int, pref: str = "") -> Response:
        if not puede_ver(db, usuario, atleta_id):
            raise HTTPException(404)   # 404 y no 403: no confirma que exista
        atleta = db.get(Usuario, atleta_id)
        try:
            return JSONResponse(calculo.calcular(db, atleta, app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None), pref))
        except calculo.SinConfig:
            raise HTTPException(404)
        except ConfigError as e:
            log.error("config inválida de %s: %s", atleta_id, e)
            return JSONResponse({"error": "Tus ajustes no son válidos."}, status_code=500)
        except calculo.DataInvalido:
            return JSONResponse({"error": "No se pudo preparar tu información."}, status_code=500)

    @app.get("/data.json")
    def data_json(usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        return data_de(db, usuario, usuario.id)

    @app.get("/a/{atleta_id}/data.json")
    def data_atleta(atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return data_de(db, usuario, atleta_id, "" if usuario is not None and usuario.id == atleta_id else f"/a/{atleta_id}")

    @app.get("/a/{atleta_id}")
    def sitio_atleta_sin_slash(atleta_id: int):
        return RedirectResponse(f"/a/{atleta_id}/", 308)

    @app.get("/a/{atleta_id}/")
    def sitio_atleta(atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        """El mismo sitio, visto por el coach: los archivos van con ruta absoluta y data.json sigue relativo (/a/<id>/data.json)."""
        if not puede_ver(db, usuario, atleta_id):
            raise HTTPException(404)
        html = (SITE / "index.html").read_text().replace("</main>", PIE_SITIO + "</main>", 1)
        html = re.sub(r'(href|src)="([\w.-]+\.(?:css|js))"', r'\1="/\2"', html)
        return HTMLResponse(html)

    @app.get("/fuentes/{archivo}")
    def fuente(archivo: str):
        if archivo not in FUENTES:
            raise HTTPException(404)
        return FileResponse(SITE / "fuentes" / archivo, media_type="font/woff2",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/{archivo}")   # siempre al final: el resto del sitio, solo la lista de arriba
    def sitio(archivo: str):
        tipo = ESTATICOS_SITE.get(archivo)
        if tipo is None:
            raise HTTPException(404)
        return FileResponse(SITE / archivo, media_type=tipo)

    return app


def __getattr__(nombre):
    """`uvicorn web.app:app`: la app se arma (con las variables de entorno) solo cuando alguien la pide."""
    if nombre == "app":
        globals()["app"] = crear_app()
        return globals()["app"]
    raise AttributeError(nombre)
