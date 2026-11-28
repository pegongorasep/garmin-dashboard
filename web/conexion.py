"""Conectar con GitHub: instalación de la GitHub App en la copia de la persona (ruta y vuelta) y disparo de corridas.
El token de usuario que sale del `code` solo vive durante la petición: nunca se guarda ni se registra."""
import base64
import hashlib
import hmac
import json
import logging
import secrets

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import onboarding, sincronizar, tubo
from .deps import actual, formulario, get_db, render, settings as get_settings
from .github_app import GitHubApp, GitHubError, InstalacionPerdida
from .modelos import Cambio, Usuario, ahora

log = logging.getLogger("web.conexion")
COOKIE = "gh_estado"
SEGUNDOS = 900
DESTINOS = {"guia": "/bienvenida?paso={paso}", "conectado": "/conexiones?", "ajustes": "/conexiones?"}


def app_de(app, settings) -> GitHubApp:
    """La GitHub App de esta web (las pruebas dejan una falsa en app.state.github_app)."""
    return getattr(app.state, "github_app", None) or GitHubApp(settings)


DESCRIPCION_SUELTA = "GitHub App desinstalada: se soltó la instalación"


def soltar_instalacion(db: Session, u: Usuario) -> None:
    """La app ya no está en la copia de la persona: se olvida la instalación, se cierran sin ruido las sincronizaciones
    vivas (no programadas) y se deja constancia. La web responde entonces como si nunca hubiera autorizado."""
    for s in sincronizar._vivas(db, u.id, False):
        db.delete(s)
    if u.gh_instalacion:
        db.add(Cambio(atleta_id=u.id, autor_id=None, via="sistema", visto=True, descripcion=DESCRIPCION_SUELTA))
    u.gh_instalacion = None
    db.commit()


def disparar(db: Session, u: Usuario, tipo: str, gh: GitHubApp, rama: str | None = None):
    """Pide una sincronización de `tipo` y dispara la corrida en el repo de la persona. Si GitHub falla, la
    sincronización queda en error `otra` (la franja ofrece Reintentar). Regresa la sincronización o None."""
    if not (u.gh_instalacion and u.repo):
        return None
    sinc, nueva = sincronizar.pedir(db, u, tipo)
    if not nueva:
        return sinc
    try:
        if not rama:
            rama = next((r["default_branch"] for r in gh.repos_de_instalacion(u.gh_instalacion)
                         if r["id"] == u.repo_id), "main")
        gh.disparar(u.gh_instalacion, u.repo, rama)
    except InstalacionPerdida:
        log.warning("la instalación de %s ya no existe: se suelta", u.id)
        soltar_instalacion(db, u)
        return None
    except Exception as e:   # noqa: BLE001  el fallo de GitHub nunca tumba a quien llama
        log.warning("no se pudo disparar %s para %s: %s", tipo, u.id, getattr(e, "status", type(e).__name__))
        sincronizar.terminar(db, sinc, ok=False, error="otra")
    return sinc


SECRETO = "PERSONAL_API_KEY"
LIGAS_POR_HORA = 3
DESCRIPCION_LIGA = "Liga de la guía mandada al correo"


def _norm(nombre: str) -> str:
    return "".join(ch for ch in nombre.lower() if ch.isalnum())


def estado_secreto(secretos: list[dict]) -> tuple[str, str | None]:
    """('listo'|'nombre_mal'|'falta', nombre parecido). Parecido: igual sin mayúsculas/espacios/guiones, o el único secreto."""
    nombres = [s["name"] for s in secretos]
    if SECRETO in nombres:
        return "listo", None
    for n in nombres:
        if _norm(n) == _norm(SECRETO):
            return "nombre_mal", n
    if len(nombres) == 1:
        return "nombre_mal", nombres[0]
    return "falta", None


def _gh_listo(usuario) -> bool:
    return bool(usuario.gh_instalacion and usuario.repo)


def sinc_json(s) -> dict | None:
    if s is None:
        return None
    return {"estado": s.estado, "tipo": s.tipo, "paso": s.paso, "hechos": s.hechos, "total": s.total, "error": s.error}


def _firma(secret: str, datos: str) -> str:
    return hmac.new(secret.encode(), datos.encode(), hashlib.sha256).hexdigest()


router = APIRouter()


def destino(para, codigo=None, ok=False):
    if para in ("conectado", "ajustes"):
        if codigo:
            return f"/conexiones?error={codigo}"
        return "/ajustes" if para == "ajustes" else "/"   # C11b: quien viene del aviso de Hoy regresa a Hoy
    return "/bienvenida?paso=4" if ok else f"/bienvenida?paso=3&error={codigo}"

def falla(para, codigo):
    resp = RedirectResponse(destino(para, codigo), 303)
    resp.delete_cookie(COOKIE, path="/conectar/github")
    return resp

@router.get("/conectar/github")
def empezar(request: Request, para: str = "guia", usuario=Depends(actual), db=Depends(get_db), settings=Depends(get_settings)):
    if not settings.app_github:
        return render(request, "mensaje.html", status=404, titulo="404", texto="")
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    if not onboarding.completo(db, usuario):
        return RedirectResponse("/perfil", 303)
    para = para if para in DESTINOS else "guia"
    estado = secrets.token_urlsafe(24)
    cuerpo = base64.urlsafe_b64encode(json.dumps({"s": estado, "u": usuario.id, "p": para}).encode()).decode()
    resp = RedirectResponse(app_de(request.app, settings).url_instalar(estado), 303)
    resp.set_cookie(COOKIE, f"{cuerpo}.{_firma(settings.secret_key, cuerpo)}", max_age=SEGUNDOS, httponly=True,
                    secure=settings.cookie_segura, samesite="lax", path="/conectar/github")
    return resp

@router.get("/conectar/github/vuelta")
def vuelta(request: Request, state: str = "", code: str = "", installation_id: str = "",
           usuario=Depends(actual), db=Depends(get_db), settings=Depends(get_settings)):
    if not settings.app_github:
        return render(request, "mensaje.html", status=404, titulo="404", texto="")
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    crudo = request.cookies.get(COOKIE, "")
    cuerpo, _, firma = crudo.rpartition(".")
    try:
        c = json.loads(base64.urlsafe_b64decode(cuerpo + "=" * (-len(cuerpo) % 4)))
        valido = (hmac.compare_digest(firma, _firma(settings.secret_key, cuerpo)) and state
                  and hmac.compare_digest(str(c.get("s")), state) and c.get("u") == usuario.id)
    except Exception:   # noqa: BLE001
        c, valido = None, False
    para = c.get("p", "guia") if valido and c.get("p") in DESTINOS else "guia"
    if not valido:
        return falla(para, "estado")
    if not code:
        return falla(para, "cancelado")
    gh = app_de(request.app, settings)
    try:
        token = gh.token_de_usuario(code)
        try:
            inst = int(installation_id)
        except ValueError:
            return falla(para, "instalacion")
        if inst not in gh.instalaciones_del_usuario(token):
            return falla(para, "instalacion")
        del token
        repos = gh.repos_de_instalacion(inst)
    except (GitHubError, Exception) as e:   # noqa: BLE001
        log.warning("vuelta de GitHub falló: %s", getattr(e, "status", type(e).__name__))
        return falla(para, "github")
    if len(repos) != 1:
        return falla(para, "repos")
    repo = repos[0]
    if usuario.repo_id and usuario.repo_id != repo["id"]:
        return falla(para, "otra_copia")
    if db.scalar(select(Usuario.id).where(Usuario.repo_id == repo["id"], Usuario.id != usuario.id,
                                          Usuario.borrado.is_(None))):
        return falla(para, "ajena")
    if not usuario.repo_id:
        if not repo["private"]:
            return falla(para, "publica")
        tubo.vincular(db, usuario, repo["full_name"], repo["id"], None,
                      f"Repo vinculado con la app de GitHub: {repo['full_name']}")
        if not usuario.github_owner:
            usuario.github_owner = repo["full_name"].split("/")[0]
    usuario.gh_instalacion = inst
    db.commit()
    resp = RedirectResponse(destino(para, ok=True), 303)
    resp.delete_cookie(COOKIE, path="/conectar/github")
    return resp

@router.get("/api/conexion/estado")
def api_estado(request: Request, usuario=Depends(actual), db=Depends(get_db), settings=Depends(get_settings)):
    if usuario is None:
        return JSONResponse({"error": "Entra primero."}, status_code=401)
    viva = sincronizar.actual(db, usuario.id)
    sinc = viva or sincronizar.ultima_terminada(db, usuario.id)
    out = {"conectado": _gh_listo(usuario), "secreto": None, "nombre": None, "sinc": sinc_json(sinc),
           "viva": viva is not None, "error": None}
    if out["conectado"]:
        try:
            out["secreto"], out["nombre"] = estado_secreto(
                app_de(request.app, settings).secretos(usuario.gh_instalacion, usuario.repo))
        except InstalacionPerdida:
            soltar_instalacion(db, usuario)
            out["conectado"], out["sinc"], out["viva"] = False, None, False
        except Exception as e:   # noqa: BLE001
            log.warning("no se pudieron leer los secretos de %s: %s", usuario.id, getattr(e, "status", type(e).__name__))
            out["error"] = "otra"
    return out

@router.post("/api/conexion/comprobar")
async def api_comprobar(request: Request, usuario=Depends(actual), db=Depends(get_db), settings=Depends(get_settings)):
    await formulario(request)   # CSRF
    if usuario is None:
        return JSONResponse({"error": "Entra primero."}, status_code=401)
    if not _gh_listo(usuario):
        return JSONResponse({"error": "sin_conexion"}, status_code=409)
    gh = app_de(request.app, settings)
    try:
        secreto, _ = estado_secreto(gh.secretos(usuario.gh_instalacion, usuario.repo))
    except InstalacionPerdida:
        soltar_instalacion(db, usuario)
        return JSONResponse({"error": "sin_conexion"}, status_code=409)
    except Exception:   # noqa: BLE001
        return JSONResponse({"error": "otra"}, status_code=502)
    if secreto != "listo":
        return JSONResponse({"error": secreto}, status_code=409)
    viva = sincronizar.actual(db, usuario.id)
    if viva is None:
        ult = sincronizar.ultima_terminada(db, usuario.id)
        if ult is not None and ult.estado == "ok" and ult.tipo in ("comprobacion", "historial"):
            return {"sinc": sinc_json(ult), "nueva": False}   # ya quedó comprobada: no se vuelve a disparar
    antes = viva.id if viva else None
    sinc = disparar(db, usuario, "comprobacion", gh)
    return {"sinc": sinc_json(sinc), "nueva": sinc is not None and sinc.id != antes}

@router.post("/bienvenida/liga")
async def liga_por_correo(request: Request, usuario=Depends(actual), db=Depends(get_db), settings=Depends(get_settings)):
    """Celular: manda por correo la liga a la guía para abrirla en la computadora (3 por hora)."""
    await formulario(request)
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    desde = ahora() - timedelta(hours=1)
    mandadas = db.scalar(select(func.count()).select_from(Cambio).where(
        Cambio.atleta_id == usuario.id, Cambio.descripcion == DESCRIPCION_LIGA, Cambio.fecha > desde))
    if mandadas >= LIGAS_POR_HORA:
        return RedirectResponse("/bienvenida?liga=limite", 303)
    db.add(Cambio(atleta_id=usuario.id, autor_id=None, via="sistema", visto=True, descripcion=DESCRIPCION_LIGA))
    db.commit()
    t = request.state.t
    request.app.state.enviar(settings, usuario.correo, t("conexion.liga_asunto"),
                             t("conexion.liga_texto", liga=settings.base_url.rstrip("/") + "/bienvenida"))
    return RedirectResponse("/bienvenida?liga=ok", 303)
