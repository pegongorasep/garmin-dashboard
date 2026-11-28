"""F6a: OAuth 2.1 del conector (registro, PKCE, códigos, tokens, refresh)."""
import base64
import hashlib
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

from web.modelos import CodigoOAuth, TokenOAuth
from ayudas import csrf_de, listo

REDIR = "https://claude.ai/api/mcp/auth_callback"
VERIF = "v" * 50
RETO = base64.urlsafe_b64encode(hashlib.sha256(VERIF.encode()).digest()).rstrip(b"=").decode()


def registrar(cl, nombre="Claude", uris=(REDIR,)):
    return cl.post("/oauth/registro", json={"client_name": nombre, "redirect_uris": list(uris),
                                            "token_endpoint_auth_method": "none"})


def params(cid, **cambia):
    p = {"response_type": "code", "client_id": cid, "redirect_uri": REDIR, "code_challenge": RETO,
         "code_challenge_method": "S256", "state": "xyz", "resource": "https://ahilallevas.test/mcp"}
    p.update(cambia)
    return {k: v for k, v in p.items() if v is not None}


def consentir(cl, p, decision="permitir"):
    pag = cl.get("/oauth/autorizar", params=p)
    assert pag.status_code == 200, pag.text
    campos = {k: v for k, v in p.items()}
    return cl.post("/oauth/autorizar", data={"csrf": csrf_de(pag.text), "decision": decision, **campos})


def codigo_de(r):
    assert r.status_code == 303
    q = parse_qs(urlsplit(r.headers["location"]).query)
    assert q["state"] == ["xyz"]
    return q["code"][0]


def canjear(cl, cid, codigo, **cambia):
    d = {"grant_type": "authorization_code", "client_id": cid, "code": codigo, "redirect_uri": REDIR, "code_verifier": VERIF}
    d.update(cambia)
    return cl.post("/oauth/token", data=d)


def listo_con_cliente(web_ctx):
    uid, cl = listo(web_ctx, "a@x.com")
    cid = registrar(cl).json()["client_id"]
    return uid, cl, cid


def test_metadatos_y_registro(web_ctx):
    cl = web_ctx.cliente()
    m = cl.get("/.well-known/oauth-authorization-server").json()
    assert m["code_challenge_methods_supported"] == ["S256"] and m["registration_endpoint"].endswith("/oauth/registro")
    assert m["issuer"] == "https://ahilallevas.test"
    r = cl.get("/.well-known/oauth-protected-resource").json()
    assert r["resource"] == "https://ahilallevas.test/mcp" and r["authorization_servers"] == ["https://ahilallevas.test"]
    assert registrar(cl).status_code == 201
    assert registrar(cl, uris=["http://localhost:3000/cb"]).status_code == 201
    assert registrar(cl, uris=["http://evil.com/cb"]).status_code == 400
    assert registrar(cl, uris=[]).status_code == 400


def test_flujo_completo_y_refresh_rota(web_ctx):
    uid, cl, cid = listo_con_cliente(web_ctx)
    pag = cl.get("/oauth/autorizar", params=params(cid))
    assert "Claude quiere ver y cambiar tu plan en Ahí la Llevas" in pag.text
    assert "claude.ai" in pag.headers["content-security-policy"]
    r = canjear(cl, cid, codigo_de(consentir(cl, params(cid))))
    assert r.status_code == 200
    t = r.json()
    assert t["token_type"] == "Bearer" and t["expires_in"] == 3600
    from web import oauth
    with web_ctx.sesiones() as db:
        assert oauth.usuario_de_token(db, t["access_token"], datetime(2026, 11, 25)).id == uid
        fila = db.query(TokenOAuth).one()
        assert t["access_token"] not in (fila.acceso_hash, fila.refresh_hash) and len(fila.acceso_hash) == 64
    r2 = cl.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": cid, "refresh_token": t["refresh_token"]})
    assert r2.status_code == 200
    n = r2.json()
    assert n["access_token"] != t["access_token"] and n["refresh_token"] != t["refresh_token"]
    with web_ctx.sesiones() as db:
        assert db.query(TokenOAuth).count() == 1
        assert oauth.usuario_de_token(db, t["access_token"], datetime(2026, 11, 25)) is None   # el viejo ya no sirve
        assert oauth.usuario_de_token(db, n["access_token"], datetime(2026, 11, 25)).id == uid
    viejo = cl.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": cid, "refresh_token": t["refresh_token"]})
    assert viejo.status_code == 400 and viejo.json()["error"] == "invalid_grant"   # el refresh anterior no se reusa


def test_pkce_malo_y_codigo_reusado(web_ctx):
    uid, cl, cid = listo_con_cliente(web_ctx)
    cod = codigo_de(consentir(cl, params(cid)))
    r = canjear(cl, cid, cod, code_verifier="x" * 50)
    assert r.status_code == 400 and r.json()["error"] == "invalid_grant"
    assert canjear(cl, cid, cod).status_code == 400   # el intento fallido ya lo gastó
    cod = codigo_de(consentir(cl, params(cid)))
    assert canjear(cl, cid, cod).status_code == 200
    r = canjear(cl, cid, cod)
    assert r.status_code == 400 and "ya se usó" in r.json()["error_description"]
    with web_ctx.sesiones() as db:
        assert db.query(TokenOAuth).count() == 0   # al reusar un código se cierran los tokens que dio
    # sin PKCE o con "plain" ni se llega al consentimiento
    r = cl.get("/oauth/autorizar", params=params(cid, code_challenge_method="plain"))
    assert r.status_code == 303 and "error=invalid_request" in r.headers["location"]
    r = cl.get("/oauth/autorizar", params=params(cid, code_challenge=None))
    assert r.status_code == 303 and "error=invalid_request" in r.headers["location"]


def test_codigo_vencido_y_token_vencido(web_ctx):
    uid, cl, cid = listo_con_cliente(web_ctx)
    cod = codigo_de(consentir(cl, params(cid)))
    base = web_ctx.app.state.reloj()
    web_ctx.app.state.reloj = lambda: base + timedelta(minutes=11)
    r = canjear(cl, cid, cod)
    assert r.status_code == 400 and "venció" in r.json()["error_description"]
    web_ctx.app.state.reloj = lambda: base
    t = canjear(cl, cid, codigo_de(consentir(cl, params(cid)))).json()
    from web import oauth
    ahora = base.astimezone(timezone.utc).replace(tzinfo=None)
    with web_ctx.sesiones() as db:
        assert oauth.usuario_de_token(db, t["access_token"], ahora + timedelta(minutes=59)).id == uid
        assert oauth.usuario_de_token(db, t["access_token"], ahora + timedelta(minutes=61)) is None
    web_ctx.app.state.reloj = lambda: base + timedelta(days=31)
    r = cl.post("/oauth/token", data={"grant_type": "refresh_token", "client_id": cid, "refresh_token": t["refresh_token"]})
    assert r.status_code == 400   # el refresh dura 30 días


def test_redirect_uri_cliente_y_resource(web_ctx):
    uid, cl, cid = listo_con_cliente(web_ctx)
    r = cl.get("/oauth/autorizar", params=params(cid, redirect_uri="https://evil.com/cb"))
    assert r.status_code == 400 and "location" not in r.headers   # sin redirigir a una dirección no registrada
    assert cl.get("/oauth/autorizar", params=params("no-existe")).status_code == 400
    r = cl.get("/oauth/autorizar", params=params(cid, resource="https://otro.com/mcp"))
    assert r.status_code == 303 and "error=invalid_target" in r.headers["location"]
    cod = codigo_de(consentir(cl, params(cid)))
    assert canjear(cl, cid, cod, redirect_uri="https://claude.ai/otra").status_code == 400
    cod = codigo_de(consentir(cl, params(cid)))
    assert canjear(cl, cid, cod, resource="https://otro.com/mcp").status_code == 400
    otro = registrar(cl, "Otra").json()["client_id"]
    cod = codigo_de(consentir(cl, params(cid)))
    assert canjear(cl, otro, cod).status_code == 400   # el código es del cliente que lo pidió


def test_consentimiento_exige_sesion_csrf_y_escapa_el_nombre(web_ctx):
    uid, cl, cid = listo_con_cliente(web_ctx)
    anon = web_ctx.cliente()
    pag = anon.get("/oauth/autorizar", params=params(cid))
    assert "Entra primero" in pag.text and "Permitir" not in pag.text
    assert anon.post("/oauth/autorizar", data={"csrf": "malo", **params(cid), "decision": "permitir"}).status_code == 403
    assert cl.post("/oauth/autorizar", data={"csrf": "malo", **params(cid), "decision": "permitir"}).status_code == 403
    xss = registrar(cl, '<script>alert(1)</script>').json()["client_id"]
    pag = cl.get("/oauth/autorizar", params=params(xss)).text
    assert "<script>alert(1)" not in pag and "&lt;script&gt;" in pag
    r = consentir(cl, params(cid), "negar")
    assert r.status_code == 303 and "error=access_denied" in r.headers["location"] and "state=xyz" in r.headers["location"]
    with web_ctx.sesiones() as db:
        assert db.query(CodigoOAuth).count() == 0


def test_sin_sesion_vuelve_al_consentimiento_despues_de_entrar(web_ctx):
    uid, _ = listo(web_ctx, "a@x.com")
    cl = web_ctx.cliente()
    cid = registrar(cl).json()["client_id"]
    cl.get("/oauth/autorizar", params=params(cid))
    cl.post("/entrar", data={"csrf": csrf_de(cl.get("/entrar").text), "correo": "a@x.com"})
    from ayudas import codigo_de
    r = cl.post("/entrar/codigo", data={"csrf": csrf_de(cl.get("/entrar").text), "correo": "a@x.com", "codigo": codigo_de(web_ctx)})
    assert r.status_code == 303 and r.headers["location"].startswith("/oauth/autorizar?") and f"client_id={cid}" in r.headers["location"]
