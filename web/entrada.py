"""Cuentas y entrada: /salud, entrar (código o liga), invitaciones, idioma, salir y el aviso de privacidad."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from dashboard import i18n

from . import auth, oauth, onboarding
from .deps import actual, formulario, get_db, poner_sesion, render
from .privacidad import VERSION_AVISO

router = APIRouter()


def _mandar_codigo(request: Request, db, usuario, idioma: str = "es") -> None:
    settings = request.app.state.settings
    codigo = auth.crear_codigo(db, settings.secret_key, usuario)
    if codigo:
        request.app.state.enviar(settings, usuario.correo, i18n.t("correo.codigo_asunto", idioma),
                                 i18n.t("correo.codigo_texto", idioma, codigo=codigo))


@router.get("/salud")
def salud():
    return {"ok": True}   # sin tocar la base: Cloud Run lo usa como sonda de arranque


@router.get("/entrar")
def entrar_form(request: Request, usuario=Depends(actual)):
    if usuario:
        return RedirectResponse("/", 303)
    return render(request, "entrar.html")

@router.post("/entrar")
async def entrar(request: Request, db=Depends(get_db)):
    form = await formulario(request)
    u = auth.buscar_por_correo(db, str(form.get("correo", "")))
    if u:
        _mandar_codigo(request, db, u, u.idioma or request.state.idioma)
    return render(request, "entrar.html", mensaje=request.state.t("entrar.mensaje_liga"), correo=auth.normalizar_correo(str(form.get("correo", ""))))   # siempre lo mismo

@router.post("/entrar/codigo")
async def entrar_codigo(request: Request, db=Depends(get_db)):
    form = await formulario(request)
    correo_in = str(form.get("correo", ""))
    u = auth.gastar_codigo(db, request.app.state.settings.secret_key, correo_in, str(form.get("codigo", "")))
    if u is None:
        return render(request, "entrar.html", status=400, mensaje=request.state.t("entrar.mensaje_liga"),
                      correo=auth.normalizar_correo(correo_in), error=request.state.t("entrar.codigo_mal"))
    resp = RedirectResponse(oauth.destino_login(request.cookies.get(oauth.COOKIE_VOLVER, ""), onboarding.completo(db, u)), 303)
    poner_sesion(resp, auth.crear_sesion(db, u), request.app.state.settings)
    resp.delete_cookie(oauth.COOKIE_VOLVER, path="/")
    return resp

@router.get("/entrar/liga/{token}")
def liga_form(request: Request, token: str, db=Depends(get_db)):
    # GET solo muestra el botón: los escáneres de correo abren las ligas y gastarían el token
    return render(request, "liga.html", no_valida=auth.liga_vigente(db, token) is None)

@router.post("/entrar/liga/{token}")
async def liga(request: Request, token: str, db=Depends(get_db)):
    await formulario(request)
    u = auth.gastar_liga(db, token)
    if u is None:
        return render(request, "liga.html", status=400, no_valida=True)
    volver = request.cookies.get(oauth.COOKIE_VOLVER, "")
    resp = RedirectResponse(oauth.volver_seguro(volver), 303)   # conexión de una IA a medias
    poner_sesion(resp, auth.crear_sesion(db, u), request.app.state.settings)
    resp.delete_cookie(oauth.COOKIE_VOLVER, path="/")
    return resp

@router.get("/invitacion/{token}")
def invitacion_form(request: Request, token: str, db=Depends(get_db)):
    inv = auth.invitacion_vigente(db, token)
    return render(request, "invitacion.html", no_valida=inv is None, nota=inv.nota if inv else None, token=token)

@router.post("/invitacion/{token}")
async def invitacion(request: Request, token: str, db=Depends(get_db)):
    form = await formulario(request)
    correo_in = str(form.get("correo", ""))
    if auth.invitacion_vigente(db, token) is None:
        return render(request, "invitacion.html", status=400, no_valida=True)
    if not auth.correo_valido(correo_in):
        return render(request, "invitacion.html", status=400, nota=None, token=token, error=request.state.t("invitacion.correo_invalido"))
    u = auth.aceptar_invitacion(db, token, correo_in) or auth.buscar_por_correo(db, correo_in)
    if u:
        _mandar_codigo(request, db, u, u.idioma or request.state.idioma)
    return render(request, "invitacion.html", mensaje=request.state.t("entrar.mensaje_liga"), correo=auth.normalizar_correo(correo_in))   # igual exista o no la cuenta

@router.post("/idioma")
async def cambiar_idioma(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    form = await formulario(request)
    nuevo = str(form.get("idioma", ""))
    if nuevo not in i18n.idiomas():
        raise HTTPException(400, "Idioma no válido")
    if usuario:
        usuario.idioma = nuevo
        db.commit()
    resp = RedirectResponse(oauth.ruta_relativa(str(form.get("siguiente", "/"))), 303)
    resp.set_cookie("idioma", nuevo, max_age=365 * 86400, httponly=True, secure=request.app.state.settings.cookie_segura, samesite="lax", path="/")
    return resp

@router.get("/salir")
def salir_form(request: Request):
    return render(request, "salir.html")

@router.post("/salir")
async def salir(request: Request, db=Depends(get_db)):
    await formulario(request)
    auth.cerrar_sesion(db, request.cookies.get(auth.COOKIE_SESION))
    resp = RedirectResponse("/", 303)
    resp.delete_cookie(auth.COOKIE_SESION, path="/")
    resp.headers["Clear-Site-Data"] = '"cache"'   # el service worker guarda el último data.json: no dejarlo en un equipo compartido
    return resp

@router.get("/privacidad")
def privacidad(request: Request):
    return render(request, "privacidad.html", version=VERSION_AVISO)
