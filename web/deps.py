"""Dependencias compartidas de las rutas (`APIRouter`): leen de `request.app.state`, que arma `crear_app()`.

Cada app tiene su propio `app.state` (settings, sesiones, plantillas), así que varias apps en un proceso no se mezclan.
Los módulos nuevos usan estas funciones con `router = APIRouter()`; los viejos (`montar(...)`) reciben las mismas funciones.
"""
import secrets

from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response

from . import auth


def settings(request: Request):
    return request.app.state.settings


def get_db(request: Request):
    db = request.app.state.sesiones()
    try:
        yield db
    finally:
        db.close()


def actual(request: Request, db=Depends(get_db)):
    """El usuario de la sesión, o None."""
    return auth.usuario_de_sesion(db, request.cookies.get(auth.COOKIE_SESION))


def render(request: Request, nombre: str, status: int = 200, **ctx) -> Response:
    cfg = request.app.state.settings
    cookie = request.cookies.get(auth.COOKIE_CSRF)
    nueva = cookie is None
    cookie = cookie or secrets.token_urlsafe(24)
    resp = request.app.state.plantillas.TemplateResponse(
        request, nombre, {"csrf": auth.campo_csrf(cfg.secret_key, cookie), "t": request.state.t,
                          "idioma": request.state.idioma, "settings": cfg, **ctx}, status_code=status)
    if nueva:
        resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=cfg.cookie_segura, samesite="lax", path="/")
    return resp


async def formulario(request: Request):
    """Campos del formulario POST, con el token CSRF ya verificado (403 si falla)."""
    form = await request.form()
    if not auth.csrf_valido(request.app.state.settings.secret_key, request.cookies.get(auth.COOKIE_CSRF), form.get("csrf")):
        raise HTTPException(403, "Token CSRF inválido")
    return form
