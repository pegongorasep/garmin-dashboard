"""Conectar con GitHub: instalación de la GitHub App en la copia de la persona (ruta y vuelta) y disparo de corridas.
El token de usuario que sale del `code` solo vive durante la petición: nunca se guarda ni se registra."""
import base64
import hashlib
import hmac
import json
import logging
import secrets

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import onboarding, sincronizar, tubo
from .github_app import GitHubApp, GitHubError
from .modelos import Usuario, VinculoPendiente

log = logging.getLogger("web.conexion")
COOKIE = "gh_estado"
SEGUNDOS = 900
DESTINOS = {"guia": "/bienvenida?paso={paso}", "conectado": "/conexiones?"}


def app_de(app, settings) -> GitHubApp:
    """La GitHub App de esta web (las pruebas dejan una falsa en app.state.github_app)."""
    return getattr(app.state, "github_app", None) or GitHubApp(settings)


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
    except Exception as e:   # noqa: BLE001  el fallo de GitHub nunca tumba a quien llama
        log.warning("no se pudo disparar %s para %s: %s", tipo, u.id, getattr(e, "status", type(e).__name__))
        sincronizar.terminar(db, sinc, ok=False, error="otra")
    return sinc


def _firma(secret: str, datos: str) -> str:
    return hmac.new(secret.encode(), datos.encode(), hashlib.sha256).hexdigest()


def montar(app, get_db, actual, render, settings) -> None:
    def destino(para, codigo=None, ok=False):
        if para == "conectado":
            return "/conexiones?" + (f"error={codigo}" if codigo else "ok=conectado")
        return "/bienvenida?paso=4" if ok else f"/bienvenida?paso=3&error={codigo}"

    def falla(para, codigo):
        resp = RedirectResponse(destino(para, codigo), 303)
        resp.delete_cookie(COOKIE, path="/conectar/github")
        return resp

    @app.get("/conectar/github")
    def empezar(request: Request, para: str = "guia", usuario=Depends(actual), db=Depends(get_db)):
        if not settings.app_github:
            return render(request, "mensaje.html", status=404, titulo="404", texto="")
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if not onboarding.estado(db, usuario)["consentimiento"]:
            return RedirectResponse("/bienvenida", 303)
        para = para if para in DESTINOS else "guia"
        estado = secrets.token_urlsafe(24)
        cuerpo = base64.urlsafe_b64encode(json.dumps({"s": estado, "u": usuario.id, "p": para}).encode()).decode()
        resp = RedirectResponse(app_de(app, settings).url_instalar(estado), 303)
        resp.set_cookie(COOKIE, f"{cuerpo}.{_firma(settings.secret_key, cuerpo)}", max_age=SEGUNDOS, httponly=True,
                        secure=settings.cookie_segura, samesite="lax", path="/conectar/github")
        return resp

    @app.get("/conectar/github/vuelta")
    def vuelta(request: Request, state: str = "", code: str = "", installation_id: str = "",
               usuario=Depends(actual), db=Depends(get_db)):
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
        gh = app_de(app, settings)
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
            pend = db.get(VinculoPendiente, usuario.id)
            if pend is not None:
                db.delete(pend)
        usuario.gh_instalacion = inst
        db.commit()
        resp = RedirectResponse(destino(para, ok=True), 303)
        resp.delete_cookie(COOKIE, path="/conectar/github")
        return resp
