"""F6a: OAuth 2.1 para el conector MCP. Metadatos (RFC 8414 y 9728), registro dinámico (RFC 7591), código con PKCE S256
y tokens opacos (solo su hash en la base). Sin librerías nuevas: se escribe directo con lo que ya está instalado."""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_token, nuevo_token
from .modelos import ClienteOAuth, CodigoOAuth, TokenOAuth, Usuario

MIN_CODIGO = 10
MIN_ACCESO = 60
DIAS_REFRESH = 30
MAX_URIS = 10
COOKIE_VOLVER = "oauth_volver"
ENTRADA = "/oauth/autorizar"


def uri_valida(uri: str) -> bool:
    """https, o http solo en localhost/127.0.0.1 (pruebas); sin fragmento ni credenciales."""
    try:
        p = urlsplit(uri)
        host = p.hostname
    except ValueError:
        return False
    if len(uri) > 500 or p.fragment or p.username or p.password or not host:
        return False
    return p.scheme == "https" or (p.scheme == "http" and host in ("localhost", "127.0.0.1"))


def pkce_ok(verifier: str, challenge: str) -> bool:
    if not (43 <= len(verifier) <= 128):
        return False
    esperado = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return hmac.compare_digest(esperado, challenge)


def _tokens_nuevos(db: Session, fila: TokenOAuth | None, ahora, *, client_id, usuario_id, resource) -> tuple[dict, TokenOAuth]:
    acceso, refresh = nuevo_token(), nuevo_token()
    if fila is None:
        fila = TokenOAuth(client_id=client_id, usuario_id=usuario_id, resource=resource, creado=ahora)
        db.add(fila)
    fila.acceso_hash, fila.refresh_hash = hash_token(acceso), hash_token(refresh)
    fila.expira_acceso = ahora + timedelta(minutes=MIN_ACCESO)
    fila.expira_refresh = ahora + timedelta(days=DIAS_REFRESH)
    db.commit()
    return {"access_token": acceso, "token_type": "Bearer", "expires_in": MIN_ACCESO * 60, "refresh_token": refresh}, fila


def usuario_de_token(db: Session, token: str | None, ahora) -> Usuario | None:
    """Para el servidor MCP (F6b): el usuario dueño de un token de acceso vigente."""
    if not token:
        return None
    t = db.scalar(select(TokenOAuth).where(TokenOAuth.acceso_hash == hash_token(token)))
    if t is None or t.expira_acceso <= ahora:
        return None
    u = db.get(Usuario, t.usuario_id)
    return u if u and u.borrado is None else None


def revocar(db: Session, token_id: int, usuario_id: int) -> bool:
    """Borra la conexión (F6c la llama desde /conexiones)."""
    t = db.get(TokenOAuth, token_id)
    if t is None or t.usuario_id != usuario_id:
        return False
    db.delete(t)
    db.commit()
    return True


def montar(app, get_db, actual, render, formulario, settings) -> None:
    base = settings.base_url.rstrip("/")
    recurso = f"{base}/mcp"

    def ahora():
        return app.state.reloj().replace(tzinfo=None)   # UTC sin zona, como todo lo que se guarda

    def json_(datos, status=200, extra=None):
        return JSONResponse(datos, status_code=status, headers={"Cache-Control": "no-store", **(extra or {})})

    def error_token(codigo: str, descripcion: str, status: int = 400):
        return json_({"error": codigo, "error_description": descripcion}, status)

    # --- metadatos ---

    @app.get("/.well-known/oauth-protected-resource")
    @app.get("/.well-known/oauth-protected-resource/mcp")
    def meta_recurso():
        return json_({"resource": recurso, "authorization_servers": [base], "bearer_methods_supported": ["header"]})

    @app.get("/.well-known/oauth-authorization-server")
    @app.get("/.well-known/oauth-authorization-server/mcp")
    def meta_servidor():
        return json_({"issuer": base, "authorization_endpoint": f"{base}{ENTRADA}", "token_endpoint": f"{base}/oauth/token",
                      "registration_endpoint": f"{base}/oauth/registro", "response_types_supported": ["code"],
                      "grant_types_supported": ["authorization_code", "refresh_token"],
                      "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"],
                      "scopes_supported": ["plan"]})

    # --- registro dinámico ---

    @app.post("/oauth/registro")
    async def registro(request: Request, db=Depends(get_db)):
        try:
            datos = json.loads(await request.body())
        except ValueError:
            datos = None
        if not isinstance(datos, dict):
            return json_({"error": "invalid_client_metadata", "error_description": "Se esperaba un JSON."}, 400)
        uris = datos.get("redirect_uris")
        if (not isinstance(uris, list) or not 1 <= len(uris) <= MAX_URIS
                or not all(isinstance(u, str) and uri_valida(u) for u in uris)):
            return json_({"error": "invalid_redirect_uri",
                          "error_description": "redirect_uris: https (o http://localhost), entre 1 y 10."}, 400)
        if datos.get("token_endpoint_auth_method", "none") != "none":
            return json_({"error": "invalid_client_metadata", "error_description": "Solo clientes públicos (none)."}, 400)
        nombre = str(datos.get("client_name") or "Una IA").strip()[:100] or "Una IA"
        cid = secrets.token_urlsafe(24)
        db.add(ClienteOAuth(client_id=cid, nombre=nombre, redirect_uris=uris))
        db.commit()
        return json_({"client_id": cid, "client_name": nombre, "redirect_uris": uris, "token_endpoint_auth_method": "none",
                      "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"]}, 201)

    # --- autorización ---

    def revisar(db, p) -> tuple[ClienteOAuth | None, str | None]:
        """(cliente, error). Los errores de client_id/redirect_uri NO redirigen: se muestran en la página."""
        c = db.get(ClienteOAuth, p.get("client_id") or "")
        if c is None or p.get("redirect_uri") not in c.redirect_uris:
            return None, "Esta conexión no es válida (cliente o dirección de regreso desconocidos)."
        return c, None

    def redir_error(p, codigo):
        q = {"error": codigo}
        if p.get("state"):
            q["state"] = p["state"]
        sep = "&" if "?" in p["redirect_uri"] else "?"
        return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), 303)

    def problema_params(p) -> str | None:
        if p.get("response_type") != "code":
            return "unsupported_response_type"
        if not p.get("code_challenge") or p.get("code_challenge_method") != "S256":
            return "invalid_request"
        if p.get("resource") and p["resource"].rstrip("/") not in (recurso, base):
            return "invalid_target"
        return None

    CAMPOS = ("response_type", "client_id", "redirect_uri", "code_challenge", "code_challenge_method", "state", "resource", "scope")

    def pagina(request, p, c, **ctx):
        resp = render(request, "oauth_consentimiento.html", cliente=c.nombre if c else "", **ctx)
        if c:   # el formulario termina en una redirección a la IA: CSP form-action debe permitir ese origen
            o = urlsplit(p["redirect_uri"])
            origen = f"{o.scheme}://{o.netloc}"
            from .app import CSP
            resp.headers["Content-Security-Policy"] = CSP.replace("form-action 'self'", f"form-action 'self' {origen}")
        return resp

    @app.get(ENTRADA)
    def autorizar_form(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        p = {k: request.query_params.get(k) or "" for k in CAMPOS}
        c, err = revisar(db, p)
        if err:
            return render(request, "oauth_consentimiento.html", status=400, error=err, cliente="")
        malo = problema_params(p)
        if malo:
            return redir_error(p, malo)
        if usuario is None:
            resp = pagina(request, p, c, entrar=True)
            resp.set_cookie(COOKIE_VOLVER, f"{ENTRADA}?{request.url.query}", max_age=1800, httponly=True,
                            secure=settings.cookie_segura, samesite="lax", path="/")
            return resp
        return pagina(request, p, c, campos=[(k, p[k]) for k in CAMPOS if p[k]])

    @app.post(ENTRADA)
    async def autorizar(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        p = {k: str(form.get(k) or "") for k in CAMPOS}
        c, err = revisar(db, p)
        if err:
            return render(request, "oauth_consentimiento.html", status=400, error=err, cliente="")
        malo = problema_params(p)
        if malo:
            return redir_error(p, malo)
        if form.get("decision") != "permitir":
            return redir_error(p, "access_denied")
        codigo = nuevo_token()
        db.add(CodigoOAuth(codigo_hash=hash_token(codigo), client_id=c.client_id, usuario_id=usuario.id,
                           redirect_uri=p["redirect_uri"], code_challenge=p["code_challenge"],
                           resource=p["resource"] or None, expira=ahora() + timedelta(minutes=MIN_CODIGO)))
        db.commit()
        q = {"code": codigo}
        if p["state"]:
            q["state"] = p["state"]
        sep = "&" if "?" in p["redirect_uri"] else "?"
        return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), 303)

    # --- tokens ---

    @app.post("/oauth/token")
    async def token(request: Request, db=Depends(get_db)):
        f = await request.form()
        tipo, cid = f.get("grant_type"), str(f.get("client_id") or "")
        if db.get(ClienteOAuth, cid) is None:
            return error_token("invalid_client", "client_id desconocido.", 401)
        res = str(f.get("resource") or "")
        if res and res.rstrip("/") not in (recurso, base):
            return error_token("invalid_target", "resource no es este servidor.")
        if tipo == "authorization_code":
            cod = db.scalar(select(CodigoOAuth).where(CodigoOAuth.codigo_hash == hash_token(str(f.get("code") or ""))))
            if cod is None or cod.client_id != cid:
                return error_token("invalid_grant", "Código inválido.")
            if cod.usado_en is not None:
                # código reusado: señal de robo; se cierran los tokens que salieron de él
                for t in db.scalars(select(TokenOAuth).where(TokenOAuth.client_id == cid, TokenOAuth.usuario_id == cod.usuario_id,
                                                              TokenOAuth.creado >= cod.usado_en)):
                    db.delete(t)
                db.commit()
                return error_token("invalid_grant", "El código ya se usó.")
            cod.usado_en = ahora()   # se gasta aunque lo demás falle
            db.commit()
            if cod.expira <= ahora():
                return error_token("invalid_grant", "El código venció.")
            if cod.redirect_uri != str(f.get("redirect_uri") or ""):
                return error_token("invalid_grant", "redirect_uri no coincide.")
            if not pkce_ok(str(f.get("code_verifier") or ""), cod.code_challenge):
                return error_token("invalid_grant", "PKCE no coincide.")
            if res and cod.resource and res.rstrip("/") != cod.resource.rstrip("/"):
                return error_token("invalid_target", "resource no coincide con la autorización.")
            salida, _ = _tokens_nuevos(db, None, ahora(), client_id=cid, usuario_id=cod.usuario_id, resource=cod.resource)
            return json_(salida)
        if tipo == "refresh_token":
            t = db.scalar(select(TokenOAuth).where(TokenOAuth.refresh_hash == hash_token(str(f.get("refresh_token") or ""))))
            if t is None or t.client_id != cid or t.expira_refresh <= ahora():
                return error_token("invalid_grant", "Refresh token inválido o vencido.")
            salida, _ = _tokens_nuevos(db, t, ahora(), client_id=cid, usuario_id=t.usuario_id, resource=t.resource)
            return json_(salida)
        return error_token("unsupported_grant_type", "grant_type no soportado.")
