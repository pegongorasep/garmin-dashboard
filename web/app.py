"""Rutas y arranque de la web. `crear_app()` arma la app (las pruebas le pasan su propia base y su propio correo)."""
import json
import logging
import secrets
import re
from datetime import datetime, timezone
from html import escape

from markupsafe import Markup
from sqlalchemy import select
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard import i18n
from dashboard.ajustes import ConfigError

from . import ROOT, actividad_web, admin, aprende, ajustes_web, auth, calculo, coach, conexion, correo, cuenta, feed, garmin_key, google, mcp_servidor, grupos, oauth, onboarding, persona, perfil, plan_nuevo, plan_web, sync_web, tubo
from .privacidad import VERSION_AVISO
from .config import WEB, Settings, desde_entorno
from .db import crear_motor, crear_sesiones
from .modelos import AvisoOculto, Usuario
from .permisos import puede_editar, puede_ver

log = logging.getLogger("web")
SITE = ROOT / "site"
# Archivos del sitio que se sirven tal cual. `data.json` NO está aquí a propósito: sale de /data.json, por usuario.
# `catalogo.html` tampoco está aquí: solo sale por /diseno, para el admin.
ESTATICOS_SITE = {"base.js": "text/javascript", "app.js": "text/javascript", "charts.js": "text/javascript",
                  "iconos.js": "text/javascript", "componentes.js": "text/javascript", "actualizar.js": "text/javascript", "franja.js": "text/javascript", "vista_comun.js": "text/javascript", "vista_plan.js": "text/javascript", "vista_progreso.js": "text/javascript", "vista_grupo.js": "text/javascript", "vistas.js": "text/javascript", "tema.js": "text/javascript", "catalogo.js": "text/javascript",
                  "styles.css": "text/css", "tokens.css": "text/css", "componentes.css": "text/css",
                  "sw.js": "text/javascript", "manifest.webmanifest": "application/manifest+json",
                  "icono-192.png": "image/png", "icono-512.png": "image/png", "icono-maskable-512.png": "image/png",
                  "apple-touch-icon.png": "image/png", "dibujo-github.svg": "image/svg+xml"}
FUENTES = {"Lexend-latin.woff2"}
def negritas(texto) -> Markup:
    """Escapa el texto y convierte **x** en <strong>x</strong> (para los textos de i18n que llevan negritas)."""
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(texto))))


def pie_sitio(idioma: str, csrf: str = "", ruta: str = "/") -> str:
    """Pie y registro del service worker que la web agrega al sitio, en el idioma de quien lo ve."""
    opciones = "".join(
        f'<option value="{c}" lang="{c}"{" selected" if c == idioma else ""}>{i18n.t("idioma." + c, idioma)}</option>' for c in ("es", "en"))
    form = (f'<form class="pie-idioma" method="post" action="/idioma"><input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
            f'<input type="hidden" name="siguiente" value="{escape(ruta, quote=True)}">'
            f'<label for="pie-idioma-sel" class="sr">{i18n.t("idioma.titulo", idioma)}</label>'
            f'<svg class="ico-svg" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z"/></svg><select id="pie-idioma-sel" name="idioma">{opciones}</select>'
            f'<noscript><button type="submit">{i18n.t("idioma.guardar", idioma)}</button></noscript></form>') if csrf else ""
    return (f'<footer class="pie"><p>{i18n.t("pie.consejo", idioma)}</p>'
            f'<div class="pie-fila">{form}<p>{i18n.t("pie.datos", idioma)} · <a href="/privacidad">{i18n.t("pie.privacidad", idioma)}</a></p></div></footer>'
            f'<script src="/actualizar.js" data-texto="{i18n.t("sitio.version_nueva", idioma)}" data-accion="{i18n.t("sitio.version_actualizar", idioma)}" '
            f'data-cuerpo="{i18n.t("sitio.version_cuerpo", idioma)}" data-luego="{i18n.t("sitio.version_luego", idioma)}" '
            f'data-actualizando="{i18n.t("sitio.version_actualizando", idioma)}"></script>'
            f'<script src="/franja.js" data-campo="{escape(csrf, quote=True)}" data-solicitando="{escape(i18n.t("sync.solicitando", idioma), quote=True)}" data-fallo="{escape(i18n.t("sync.solicitud_error", idioma), quote=True)}"></script>')


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
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
    plantillas.env.filters["negritas"] = negritas
    app.mount("/estaticos", StaticFiles(directory=str(WEB / "estaticos")), name="estaticos")

    @app.middleware("http")
    async def idioma_de_la_peticion(request: Request, call_next):
        """Idioma: cuenta (si hay sesión) > cookie `idioma` > Accept-Language > es."""
        disp = i18n.idiomas()
        elegido = None
        if request.cookies.get(auth.COOKIE_SESION):
            db = sesiones()
            try:
                u = auth.usuario_de_sesion(db, request.cookies.get(auth.COOKIE_SESION))
                elegido = u.idioma if u and u.idioma in disp else None
            finally:
                db.close()
        if elegido is None and request.cookies.get("idioma") in disp:
            elegido = request.cookies["idioma"]
        elegido = elegido or i18n.elegir(request.headers.get("accept-language")) or i18n.DEFECTO
        request.state.idioma = elegido
        request.state.t = lambda clave, **vars: i18n.t(clave, elegido, **vars)
        return await call_next(request)

    @app.middleware("http")
    async def cabeceras(request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("Content-Security-Policy", CSP)
        # HSTS solo por https (Cloud Run termina TLS y avisa con x-forwarded-proto); en local/http no
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto", "").split(",")[0].strip() == "https":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
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
                                                             "t": request.state.t, "idioma": request.state.idioma,
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

    def mandar_codigo(db, usuario, idioma: str = "es") -> None:
        codigo = auth.crear_codigo(db, settings.secret_key, usuario)
        if codigo:
            enviar(settings, usuario.correo, i18n.t("correo.codigo_asunto", idioma),
                   i18n.t("correo.codigo_texto", idioma, codigo=codigo))

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
            mandar_codigo(db, u, u.idioma or request.state.idioma)
        return render(request, "entrar.html", mensaje=request.state.t("entrar.mensaje_liga"), correo=auth.normalizar_correo(str(form.get("correo", ""))))   # siempre lo mismo

    @app.post("/entrar/codigo")
    async def entrar_codigo(request: Request, db=Depends(get_db)):
        form = await formulario(request)
        correo_in = str(form.get("correo", ""))
        u = auth.gastar_codigo(db, settings.secret_key, correo_in, str(form.get("codigo", "")))
        if u is None:
            return render(request, "entrar.html", status=400, mensaje=request.state.t("entrar.mensaje_liga"),
                          correo=auth.normalizar_correo(correo_in), error=request.state.t("entrar.codigo_mal"))
        resp = RedirectResponse(oauth.destino_login(request.cookies.get(oauth.COOKIE_VOLVER, ""), onboarding.completo(db, u)), 303)
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
            return render(request, "invitacion.html", status=400, nota=None, token=token, error=request.state.t("invitacion.correo_invalido"))
        u = auth.aceptar_invitacion(db, token, correo_in) or auth.buscar_por_correo(db, correo_in)
        if u:
            mandar_codigo(db, u, u.idioma or request.state.idioma)
        return render(request, "invitacion.html", mensaje=request.state.t("entrar.mensaje_liga"), correo=auth.normalizar_correo(correo_in))   # igual exista o no la cuenta

    @app.post("/idioma")
    async def cambiar_idioma(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        nuevo = str(form.get("idioma", ""))
        if nuevo not in i18n.idiomas():
            raise HTTPException(400, "Idioma no válido")
        if usuario:
            usuario.idioma = nuevo
            db.commit()
        resp = RedirectResponse(oauth.ruta_relativa(str(form.get("siguiente", "/"))), 303)
        resp.set_cookie("idioma", nuevo, max_age=365 * 86400, httponly=True, secure=settings.cookie_segura, samesite="lax", path="/")
        return resp

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
    actividad_web.montar(app, get_db, actual, render, formulario, settings)
    plan_nuevo.montar(app, get_db, actual, render, formulario, settings)   # antes de plan_web: /plan/nuevo no choca con /plan/{...}
    plan_web.montar(app, get_db, actual, render, formulario, settings)
    coach.montar(app, get_db, actual, render, formulario, settings)
    oauth.montar(app, get_db, actual, render, formulario, settings)
    oauth.montar_conexiones(app, get_db, actual, render, formulario, settings)
    perfil.montar(app, get_db, actual, render, formulario, settings)
    grupos.montar(app, get_db, actual, render, formulario, settings)
    feed.montar(app, get_db, actual, formulario, settings)
    persona.montar(app, get_db, actual, settings)
    aprende.montar(app, get_db, actual, render, formulario, settings)
    cuenta.montar(app, get_db, actual, render, formulario, settings)
    admin.montar(app, get_db, actual, render, formulario, settings)
    google.montar(app, get_db, actual, render, settings, poner_sesion)
    conexion.montar(app, get_db, actual, render, settings, formulario)
    sync_web.montar(app, get_db, actual, settings, formulario)
    garmin_key.montar(app, get_db, actual, render, settings, formulario)
    mcp_servidor.montar(app, settings)

    @app.get("/instalar")
    def instalar(request: Request, siguiente: str = "/"):
        return render(request, "instalar.html", siguiente=oauth.ruta_relativa(siguiente))

    # --- dashboard por usuario ---

    @app.get("/")
    def inicio(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return render(request, "inicio.html")
        if not onboarding.completo(db, usuario):
            return RedirectResponse("/perfil", 303)   # nombre y aviso de privacidad, una vez (E1)
        cookie = request.cookies.get(auth.COOKIE_CSRF)
        nueva = cookie is None
        cookie = cookie or secrets.token_urlsafe(24)
        campo = auth.campo_csrf(settings.secret_key, cookie)
        html = (SITE / "index.html").read_text().replace("</main>", "</main>" + pie_sitio(request.state.idioma, campo, "/"), 1)
        # Nombre, avisos ya entendidos y token CSRF van solo en esta página (nunca en data.json). Las páginas no se
        # guardan en el service worker; no-store por si acaso.
        ocultos = {a.aviso_id: a.huella for a in db.scalars(select(AvisoOculto).where(AvisoOculto.usuario_id == usuario.id))}
        attrs = {"data-nombre": usuario.nombre or "", "data-avisos-ocultos": json.dumps(ocultos), "data-csrf": campo,
                 "data-grupos": str(calculo.contar_grupos(db, usuario))}
        html = html.replace('<main id="app">', '<main id="app" ' + " ".join(f'{k}="{escape(v, quote=True)}"' for k, v in attrs.items()) + ">", 1)
        resp = HTMLResponse(html, headers={"Cache-Control": "no-store"})
        if nueva:
            resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=settings.cookie_segura, samesite="lax", path="/")
        return resp

    @app.post("/avisos/ocultar")
    async def ocultar_aviso(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """«Entendido»: la persona da por visto un aviso hasta que cambie su huella. Solo en su propia cuenta."""
        form = await formulario(request)
        if usuario is None or not puede_editar(db, usuario, usuario.id):
            raise HTTPException(403)
        aviso_id, huella = str(form.get("id", "")), str(form.get("huella", ""))
        if not re.fullmatch(r"[a-z_]{1,20}", aviso_id) or not re.fullmatch(r"[0-9a-f]{1,16}", huella):
            raise HTTPException(422)
        fila = db.get(AvisoOculto, (usuario.id, aviso_id))
        if fila is None:
            db.add(AvisoOculto(usuario_id=usuario.id, aviso_id=aviso_id, huella=huella))
        else:
            fila.huella = huella
        db.commit()
        return JSONResponse({"ok": True})

    @app.get("/diseno")
    def diseno(usuario=Depends(actual)):
        """Catálogo del sistema de diseño: solo el admin; a los demás (y sin sesión) un 404 como si no existiera."""
        if usuario is None or not usuario.es_admin:
            raise HTTPException(404)
        return FileResponse(SITE / "catalogo.html", media_type="text/html")

    def data_de(request: Request, db, usuario, atleta_id: int, pref: str = "") -> Response:
        if not puede_ver(db, usuario, atleta_id):
            raise HTTPException(404)   # 404 y no 403: no confirma que exista
        atleta = db.get(Usuario, atleta_id)
        try:
            salida = calculo.calcular(db, atleta, app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None), pref,
                                      request.state.idioma,
                                      sync=sync_web.sync_ui(settings, atleta) if atleta.id == getattr(usuario, 'id', None) else None,
                                      editable=puede_editar(db, usuario, atleta_id))
            return JSONResponse({**salida, "idioma": request.state.idioma})   # el sitio se pinta en el idioma de quien lo ve
        except calculo.SinConfig:
            raise HTTPException(404)
        except ConfigError as e:
            log.error("config inválida de %s: %s", atleta_id, e)
            return JSONResponse({"error": "Tus ajustes no son válidos."}, status_code=500)
        except calculo.DataInvalido:
            return JSONResponse({"error": "No se pudo preparar tu información."}, status_code=500)

    @app.get("/data.json")
    def data_json(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        return data_de(request, db, usuario, usuario.id)

    @app.get("/a/{atleta_id}/data.json")
    def data_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return data_de(request, db, usuario, atleta_id, "" if usuario is not None and usuario.id == atleta_id else f"/a/{atleta_id}")

    @app.get("/a/{atleta_id}")
    def sitio_atleta_sin_slash(atleta_id: int):
        return RedirectResponse(f"/a/{atleta_id}/", 308)

    @app.get("/a/{atleta_id}/")
    def sitio_atleta(atleta_id: int, request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """El mismo sitio, visto por el coach: los archivos van con ruta absoluta y data.json sigue relativo (/a/<id>/data.json)."""
        if not puede_ver(db, usuario, atleta_id):
            raise HTTPException(404)
        cookie = request.cookies.get(auth.COOKIE_CSRF)
        nueva = cookie is None
        cookie = cookie or secrets.token_urlsafe(24)
        pie = pie_sitio(request.state.idioma, auth.campo_csrf(settings.secret_key, cookie), request.url.path)
        html = (SITE / "index.html").read_text().replace("</main>", "</main>" + pie, 1)
        html = re.sub(r'(href|src)="([\w.-]+\.(?:css|js))"', r'\1="/\2"', html)
        resp = HTMLResponse(html)
        if nueva:
            resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=settings.cookie_segura, samesite="lax", path="/")
        return resp

    @app.get("/fuentes/{archivo}")
    def fuente(archivo: str):
        if archivo not in FUENTES:
            raise HTTPException(404)
        return FileResponse(SITE / "fuentes" / archivo, media_type="font/woff2",
                            headers={"Cache-Control": "public, max-age=31536000, immutable"})

    @app.get("/i18n/{archivo}")
    @app.get("/a/{atleta_id}/i18n/{archivo}")   # el sitio del coach pide los textos con ruta relativa
    def textos_sitio(archivo: str, atleta_id: int | None = None):
        """Los textos del sitio (JS) en un idioma: salen del catálogo, nunca atrasados. Son públicos (no llevan datos)."""
        idioma = archivo[:-5] if archivo.endswith(".json") else ""
        if idioma not in i18n.idiomas():
            raise HTTPException(404)
        return JSONResponse(i18n.catalogo_sitio(idioma), headers={"Cache-Control": "no-cache"})

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
