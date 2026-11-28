"""F6a: OAuth 2.1 para el conector MCP. Metadatos (RFC 8414 y 9728), registro dinámico (RFC 7591), código con PKCE S256
y tokens opacos (solo su hash en la base). Sin librerías nuevas: se escribe directo con lo que ya está instalado."""
import base64
import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import hash_token, nuevo_token
from .deps import actual, formulario, get_db, render
from .onboarding import ERRORES_CONEXION
from .modelos import ClienteOAuth, CodigoOAuth, TokenOAuth, Usuario

MIN_CODIGO = 10
MIN_ACCESO = 60
DIAS_REFRESH = 30
MAX_URIS = 10
COOKIE_VOLVER = "oauth_volver"
ENTRADA = "/oauth/autorizar"


def volver_seguro(valor: str) -> str:
    """Adónde regresa /entrar/liga: solo una ruta relativa a la pantalla de consentimiento; si no, al inicio (sin redirección abierta)."""
    if valor.startswith(ENTRADA + "?") and "\\" not in valor and "\r" not in valor and "\n" not in valor:
        return valor
    return "/"


def ruta_relativa(valor: str) -> str:
    """Ruta relativa del propio sitio ('/algo'); si no lo es, '/' (sin redirección abierta)."""
    if (valor.startswith("/") and not valor.startswith("//") and "\\" not in valor and "\r" not in valor
            and "\n" not in valor and ":" not in valor.split("?")[0]):
        return valor
    return "/"


def destino_login(cookie_volver: str, onboarding_completo: bool) -> str:
    """Adónde va la persona tras entrar: conector a medias, o invitación a instalar la app, o inicio."""
    if cookie_volver:
        return volver_seguro(cookie_volver)
    return "/instalar?siguiente=/" if onboarding_completo else "/"


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


router = APIRouter()


def _base(request: Request) -> str:
    return request.app.state.settings.base_url.rstrip("/")


def _ahora(request: Request):
    return request.app.state.reloj().replace(tzinfo=None)   # UTC sin zona, como todo lo que se guarda


def json_(datos, status=200, extra=None):
    return JSONResponse(datos, status_code=status, headers={"Cache-Control": "no-store", **(extra or {})})

def error_token(codigo: str, descripcion: str, status: int = 400):
    return json_({"error": codigo, "error_description": descripcion}, status)

# --- metadatos ---

@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/mcp")
def meta_recurso(request: Request):
    base = _base(request)
    recurso = f"{base}/mcp"
    return json_({"resource": recurso, "authorization_servers": [base], "bearer_methods_supported": ["header"]})

@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/mcp")
def meta_servidor(request: Request):
    base = _base(request)
    return json_({"issuer": base, "authorization_endpoint": f"{base}{ENTRADA}", "token_endpoint": f"{base}/oauth/token",
                  "registration_endpoint": f"{base}/oauth/registro", "response_types_supported": ["code"],
                  "grant_types_supported": ["authorization_code", "refresh_token"],
                  "code_challenge_methods_supported": ["S256"], "token_endpoint_auth_methods_supported": ["none"],
                  "scopes_supported": ["plan"]})

# --- registro dinámico ---

@router.post("/oauth/registro")
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
        return None, "oauth.cliente_malo"
    return c, None

def redir_error(p, codigo):
    q = {"error": codigo}
    if p.get("state"):
        q["state"] = p["state"]
    sep = "&" if "?" in p["redirect_uri"] else "?"
    return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), 303)

def problema_params(p, base: str) -> str | None:
    recurso = f"{base}/mcp"
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

@router.get(ENTRADA)
def autorizar_form(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    p = {k: request.query_params.get(k) or "" for k in CAMPOS}
    c, err = revisar(db, p)
    if err:
        return render(request, "oauth_consentimiento.html", status=400, error=request.state.t(err), cliente="")
    malo = problema_params(p, _base(request))
    if malo:
        return redir_error(p, malo)
    if usuario is None:
        resp = pagina(request, p, c, entrar=True)
        resp.set_cookie(COOKIE_VOLVER, f"{ENTRADA}?{request.url.query}", max_age=1800, httponly=True,
                        secure=request.app.state.settings.cookie_segura, samesite="lax", path="/")
        return resp
    return pagina(request, p, c, campos=[(k, p[k]) for k in CAMPOS if p[k]])

@router.post(ENTRADA)
async def autorizar(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    form = await formulario(request)
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    p = {k: str(form.get(k) or "") for k in CAMPOS}
    c, err = revisar(db, p)
    if err:
        return render(request, "oauth_consentimiento.html", status=400, error=request.state.t(err), cliente="")
    malo = problema_params(p, _base(request))
    if malo:
        return redir_error(p, malo)
    if form.get("decision") != "permitir":
        return redir_error(p, "access_denied")
    codigo = nuevo_token()
    db.add(CodigoOAuth(codigo_hash=hash_token(codigo), client_id=c.client_id, usuario_id=usuario.id,
                       redirect_uri=p["redirect_uri"], code_challenge=p["code_challenge"],
                       resource=p["resource"] or None, expira=_ahora(request) + timedelta(minutes=MIN_CODIGO)))
    db.commit()
    q = {"code": codigo}
    if p["state"]:
        q["state"] = p["state"]
    sep = "&" if "?" in p["redirect_uri"] else "?"
    return RedirectResponse(p["redirect_uri"] + sep + urlencode(q), 303)

# --- tokens ---

@router.post("/oauth/token")
async def token(request: Request, db=Depends(get_db)):
    base = _base(request)
    recurso = f"{base}/mcp"
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
        cod.usado_en = _ahora(request)   # se gasta aunque lo demás falle
        db.commit()
        if cod.expira <= _ahora(request):
            return error_token("invalid_grant", "El código venció.")
        if cod.redirect_uri != str(f.get("redirect_uri") or ""):
            return error_token("invalid_grant", "redirect_uri no coincide.")
        if not pkce_ok(str(f.get("code_verifier") or ""), cod.code_challenge):
            return error_token("invalid_grant", "PKCE no coincide.")
        if res and cod.resource and res.rstrip("/") != cod.resource.rstrip("/"):
            return error_token("invalid_target", "resource no coincide con la autorización.")
        salida, _ = _tokens_nuevos(db, None, _ahora(request), client_id=cid, usuario_id=cod.usuario_id, resource=cod.resource)
        return json_(salida)
    if tipo == "refresh_token":
        t = db.scalar(select(TokenOAuth).where(TokenOAuth.refresh_hash == hash_token(str(f.get("refresh_token") or ""))))
        if t is None or t.client_id != cid or t.expira_refresh <= _ahora(request):
            return error_token("invalid_grant", "Refresh token inválido o vencido.")
        salida, _ = _tokens_nuevos(db, t, _ahora(request), client_id=cid, usuario_id=t.usuario_id, resource=t.resource)
        return json_(salida)
    return error_token("unsupported_grant_type", "grant_type no soportado.")


def conexiones_de(db: Session, usuario_id: int) -> list[dict]:
    """Las IAs conectadas a la cuenta (una fila por conexión), para /conexiones."""
    filas = db.execute(select(TokenOAuth, ClienteOAuth.nombre).join(ClienteOAuth, ClienteOAuth.client_id == TokenOAuth.client_id)
                       .where(TokenOAuth.usuario_id == usuario_id).order_by(TokenOAuth.creado.desc())).all()
    return [{"id": t.id, "nombre": n, "creado": t.creado, "ultimo_uso": t.ultimo_uso} for t, n in filas]


@router.get("/conexiones")
def conexiones(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    return render(request, "conexiones.html", atleta=usuario, pref="", lista=conexiones_de(db, usuario.id),
                  ok=request.query_params.get("ok"),
                  error=(request.state.t(f"conexion.err_{request.query_params['error']}")
                         if request.query_params.get("error") in ERRORES_CONEXION else None))

@router.post("/conexiones/{token_id}/revocar")
async def revocar_conexion(request: Request, token_id: int, usuario=Depends(actual), db: Session = Depends(get_db)):
    await formulario(request)
    revocar(db, token_id, usuario.id)
    return RedirectResponse("/conexiones?ok=revocada", 303)

@router.get("/ayuda/conector")
def ayuda_conector(request: Request, usuario=Depends(actual)):
    return render(request, "conector.html", atleta=usuario, pref="", url_mcp=request.app.state.settings.base_url.rstrip("/") + "/mcp")
