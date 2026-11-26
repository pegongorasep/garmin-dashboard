"""Login con Google (OpenID Connect, código + PKCE). Sigue exigiendo invitación: sin ella no se crean cuentas."""
import base64
import hashlib
import json
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt
from . import onboarding
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from . import auth, oauth
from .modelos import Usuario

AUTORIZAR = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
CERTS = "https://www.googleapis.com/oauth2/v3/certs"
EMISORES = ("https://accounts.google.com", "accounts.google.com")
COOKIE = "google_estado"
SEGUNDOS = 600
JWKS_SEGUNDOS = 3600


class GoogleError(Exception):
    pass


def canje_http(settings, codigo: str, verificador: str) -> str:
    """Cambia el código por el ID token (se reemplaza en pruebas con app.state.google_canje)."""
    r = httpx.post(TOKEN, timeout=10, data={
        "code": codigo, "client_id": settings.google_client_id, "client_secret": settings.google_client_secret,
        "redirect_uri": f"{settings.base_url}/entrar/google/vuelta", "grant_type": "authorization_code",
        "code_verifier": verificador})
    r.raise_for_status()
    return r.json()["id_token"]


def jwks_http() -> dict:
    r = httpx.get(CERTS, timeout=10)
    r.raise_for_status()
    return r.json()


def verificar_id_token(token: str, settings, jwks: dict, nonce: str) -> dict:
    """Claims del ID token o GoogleError (firma, iss, aud, exp, nonce, email_verified)."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        llaves = [k for k in jwt.PyJWKSet.from_dict(jwks).keys if k.key_id == kid]
        if not llaves:
            raise GoogleError("llave desconocida")
        c = jwt.decode(token, llaves[0].key, algorithms=["RS256"], audience=settings.google_client_id,
                       options={"require": ["exp", "iss", "aud"]})
    except jwt.PyJWTError as e:
        raise GoogleError(str(e))
    if c.get("iss") not in EMISORES:
        raise GoogleError("iss")
    if not secrets.compare_digest(str(c.get("nonce", "")), nonce):
        raise GoogleError("nonce")
    if c.get("email_verified") not in (True, "true") or not c.get("email") or not c.get("sub"):
        raise GoogleError("correo sin verificar")
    return c


def montar(app, get_db, actual, render, settings, poner_sesion) -> None:
    def b64(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).rstrip(b"=").decode()

    def jwks() -> dict:
        cache = app.state.__dict__.setdefault("google_jwks_cache", {"t": 0.0, "datos": None})
        if cache["datos"] is None or time.time() - cache["t"] > JWKS_SEGUNDOS:
            fetch = getattr(app.state, "google_jwks", None) or jwks_http
            cache["datos"], cache["t"] = fetch(), time.time()
        return cache["datos"]

    def rechazo(request, msg, status=400):
        return render(request, "mensaje.html", status=status, titulo=request.state.t("google.no_entrar"), texto=msg)

    @app.get("/entrar/google")
    def empezar(request: Request, inv: str = "", ligar: str = "", usuario=Depends(actual)):
        if not settings.google_client_id:
            return RedirectResponse("/entrar", 303)
        if ligar and usuario is None:
            return RedirectResponse("/entrar", 303)
        estado, nonce, verificador = (secrets.token_urlsafe(24) for _ in range(3))
        reto = b64(hashlib.sha256(verificador.encode()).digest())
        url = AUTORIZAR + "?" + urlencode({
            "client_id": settings.google_client_id, "redirect_uri": f"{settings.base_url}/entrar/google/vuelta",
            "response_type": "code", "scope": "openid email", "state": estado, "nonce": nonce,
            "code_challenge": reto, "code_challenge_method": "S256", "prompt": "select_account"})
        resp = RedirectResponse(url, 303)
        valor = b64(json.dumps({"s": estado, "n": nonce, "v": verificador, "i": inv, "l": bool(ligar)}).encode())
        resp.set_cookie(COOKIE, valor, max_age=SEGUNDOS, httponly=True, secure=settings.cookie_segura,
                        samesite="lax", path="/entrar/google")
        return resp

    @app.get("/entrar/google/vuelta")
    def vuelta(request: Request, state: str = "", code: str = "", error: str = "",
               usuario=Depends(actual), db=Depends(get_db)):
        crudo = request.cookies.get(COOKIE, "")
        try:
            c = json.loads(base64.urlsafe_b64decode(crudo + "=" * (-len(crudo) % 4)))
        except Exception:
            c = None
        if not c or not state or not secrets.compare_digest(str(c.get("s")), state) or error or not code:
            return rechazo(request, "La sesión de Google venció o no es válida. Intenta de nuevo.")
        try:
            canje = getattr(app.state, "google_canje", None) or canje_http
            claims = verificar_id_token(canje(settings, code, c["v"]), settings, jwks(), c["n"])
        except (GoogleError, httpx.HTTPError, KeyError):
            return rechazo(request, "No pudimos verificar tu cuenta de Google. Intenta de nuevo.")
        sub, correo = str(claims["sub"]), auth.normalizar_correo(claims["email"])
        existente = db.scalar(select(Usuario).where(Usuario.google_sub == sub, Usuario.borrado.is_(None)))

        if c.get("l"):   # ligar a la cuenta con sesión
            if usuario is None:
                return RedirectResponse("/entrar", 303)
            if existente is not None and existente.id != usuario.id:
                return rechazo(request, "Esa cuenta de Google ya está ligada a otra cuenta.")
            usuario.google_sub = sub
            db.commit()
            resp = RedirectResponse("/privacidad/mis-datos", 303)
            resp.delete_cookie(COOKIE, path="/entrar/google")
            return resp

        u = existente or auth.buscar_por_correo(db, correo)
        if u is not None and existente is None:
            if u.google_sub:   # esa cuenta ya tiene otra cuenta de Google
                return rechazo(request, "Esa cuenta ya está ligada a otra cuenta de Google.")
            u.google_sub = sub
            db.commit()
        if u is None and c.get("i"):
            u = auth.aceptar_invitacion(db, c["i"], correo)
            if u is not None:
                u.google_sub = sub
                db.commit()
        if u is None:
            return rechazo(request, "Necesitas una invitación para crear tu cuenta. Pídesela a Pedro.", 403)

        resp = RedirectResponse(oauth.destino_login(request.cookies.get(oauth.COOKIE_VOLVER, ""), onboarding.completo(db, u)), 303)
        poner_sesion(resp, auth.crear_sesion(db, u))
        resp.delete_cookie(oauth.COOKIE_VOLVER, path="/")
        resp.delete_cookie(COOKIE, path="/entrar/google")
        return resp
