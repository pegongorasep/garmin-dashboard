"""Arranque de la web: `crear_app()` solo configura (settings, `app.state`, middlewares, errores y el orden de los routers).
Las rutas viven en cada módulo (`router = APIRouter()`, dependencias en `deps.py`); las pruebas le pasan su propia base y su propio correo."""
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard import i18n

from . import (actividad_web, admin, aprende, ajustes_web, auth, coach, conexion, correo, cuenta, cuentas_prueba, entrada, feed,
               garmin_key, google, grupos, mcp_servidor, oauth, onboarding, perfil, persona, plan_nuevo, plan_web, sitio, sync_web, tubo)
from .config import WEB, Settings, desde_entorno
from .db import crear_motor, crear_sesiones

CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


async def _idioma_de_la_peticion(request: Request, call_next):
    """Idioma: cuenta (si hay sesión) > cookie `idioma` > Accept-Language > es."""
    disp = i18n.idiomas()
    elegido = None
    if request.cookies.get(auth.COOKIE_SESION):
        db = request.app.state.sesiones()
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


async def _cabeceras(request: Request, call_next):
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


def crear_app(settings: Settings | None = None, motor=None, enviar=None, reloj=None) -> FastAPI:
    settings = settings or desde_entorno()
    motor = motor or crear_motor(settings.database_url)
    app = FastAPI(title="Ahí la Llevas", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings, app.state.motor, app.state.sesiones = settings, motor, crear_sesiones(motor)
    app.state.enviar = enviar or correo.enviar
    app.state.reloj = reloj or (lambda: datetime.now(timezone.utc))   # las pruebas lo cambian para fijar «hoy»
    app.state.plantillas = Jinja2Templates(directory=str(WEB / "plantillas"))
    app.state.plantillas.env.filters["negritas"] = sitio.negritas
    app.mount("/estaticos", StaticFiles(directory=str(WEB / "estaticos")), name="estaticos")
    app.middleware("http")(_idioma_de_la_peticion)
    app.middleware("http")(_cabeceras)

    # El orden importa: /plan/nuevo antes de /plan/{...}; el sitio (`/{archivo}`) siempre al final.
    for modulo in (entrada, tubo, onboarding, ajustes_web, actividad_web, plan_nuevo, plan_web, coach, oauth, perfil, grupos, feed,
                   persona, aprende, cuenta, admin, cuentas_prueba, google, conexion, sync_web, garmin_key):
        app.include_router(modulo.router)
    mcp_servidor.montar_mcp(app, settings)
    app.include_router(sitio.router)
    return app


def __getattr__(nombre):
    """`uvicorn web.app:app`: la app se arma (con las variables de entorno) solo cuando alguien la pide."""
    if nombre == "app":
        globals()["app"] = crear_app()
        return globals()["app"]
    raise AttributeError(nombre)
