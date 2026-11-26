import json
import time
from urllib.parse import parse_qs, urlsplit

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

from web import auth
from web.modelos import Usuario
from tests.test_web_cuentas import crear_usuario, entrar

LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(LLAVE.public_key()))
JWK.update(kid="k1", alg="RS256", use="sig")


def activar(ctx, **claims):
    """Google simulado: el canje devuelve un ID token firmado con `claims` (nonce se toma del flujo)."""
    ctx.settings.google_client_id, ctx.settings.google_client_secret = "cid", "sec"
    ctx.app.state.google_jwks = lambda: {"keys": [JWK]}

    def canje(settings, codigo, verificador):
        base = {"iss": "https://accounts.google.com", "aud": "cid", "exp": int(time.time()) + 300,
                "sub": "sub-1", "email": "nueva@x.com", "email_verified": True, "nonce": ctx.nonce}
        base.update(claims)
        base = {k: v for k, v in base.items() if v is not None}
        return jwt.encode(base, LLAVE, algorithm="RS256", headers={"kid": "k1"})
    ctx.app.state.google_canje = canje


def empezar(ctx, cl, **q):
    r = cl.get("/entrar/google", params=q)
    assert r.status_code == 303
    p = parse_qs(urlsplit(r.headers["location"]).query)
    assert p["code_challenge_method"] == ["S256"] and p["scope"] == ["openid email"]
    ctx.nonce = p["nonce"][0]
    return p["state"][0]


def vuelta(cl, estado, code="c"):
    return cl.get("/entrar/google/vuelta", params={"state": estado, "code": code})


def inv(ctx):
    with ctx.sesiones() as db:
        return auth.crear_invitacion(db, None)


def test_sin_cliente_no_hay_boton(web_ctx):
    assert "Continuar con Google" not in web_ctx.cliente().get("/entrar").text
    web_ctx.settings.google_client_id = "cid"
    assert "Continuar con Google" in web_ctx.cliente().get("/entrar").text
    t = inv(web_ctx)
    assert f"/entrar/google?inv={t}" in web_ctx.cliente().get(f"/invitacion/{t}").text


def test_invitacion_mas_google_crea_cuenta(web_ctx):
    activar(web_ctx)
    t = inv(web_ctx)
    cl = web_ctx.cliente()
    r = vuelta(cl, empezar(web_ctx, cl, inv=t))
    assert r.status_code == 303 and auth.COOKIE_SESION in r.headers["set-cookie"]
    with web_ctx.sesiones() as db:
        u = auth.buscar_por_correo(db, "nueva@x.com")
        assert u.google_sub == "sub-1"
        assert auth.invitacion_vigente(db, t) is None


def test_google_sin_invitacion_se_rechaza(web_ctx):
    activar(web_ctx)
    cl = web_ctx.cliente()
    r = vuelta(cl, empezar(web_ctx, cl))
    assert r.status_code == 403 and "invitación" in r.text
    with web_ctx.sesiones() as db:
        assert auth.buscar_por_correo(db, "nueva@x.com") is None


def test_cuenta_existente_por_correo_guarda_sub(web_ctx):
    crear_usuario(web_ctx, "nueva@x.com")
    activar(web_ctx)
    cl = web_ctx.cliente()
    assert vuelta(cl, empezar(web_ctx, cl)).status_code == 303
    with web_ctx.sesiones() as db:
        assert auth.buscar_por_correo(db, "nueva@x.com").google_sub == "sub-1"
    cl2 = web_ctx.cliente()   # la segunda vez entra por sub aunque el correo cambie
    activar(web_ctx, email="otro@x.com")
    assert vuelta(cl2, empezar(web_ctx, cl2)).status_code == 303


def test_estado_nonce_y_correo_sin_verificar(web_ctx):
    crear_usuario(web_ctx, "nueva@x.com")
    activar(web_ctx)
    cl = web_ctx.cliente()
    empezar(web_ctx, cl)
    assert vuelta(cl, "otro").status_code == 400
    activar(web_ctx, nonce="malo")
    cl = web_ctx.cliente()
    assert vuelta(cl, empezar(web_ctx, cl)).status_code == 400
    activar(web_ctx, email_verified=False)
    cl = web_ctx.cliente()
    assert vuelta(cl, empezar(web_ctx, cl)).status_code == 400
    activar(web_ctx, aud="otro")
    cl = web_ctx.cliente()
    assert vuelta(cl, empezar(web_ctx, cl)).status_code == 400


def test_ligar_cuenta_de_google(web_ctx):
    crear_usuario(web_ctx, "a@x.com")
    activar(web_ctx, email="distinto@gmail.com")
    cl = entrar(web_ctx, web_ctx.cliente(), "a@x.com")
    assert "Ligar mi cuenta de Google" in cl.get("/privacidad/mis-datos").text
    r = vuelta(cl, empezar(web_ctx, cl, ligar=1))
    assert r.status_code == 303 and r.headers["location"] == "/privacidad/mis-datos"
    with web_ctx.sesiones() as db:
        assert auth.buscar_por_correo(db, "a@x.com").google_sub == "sub-1"
        assert auth.buscar_por_correo(db, "distinto@gmail.com") is None


def test_ligar_sin_sesion_va_a_entrar(web_ctx):
    activar(web_ctx)
    assert web_ctx.cliente().get("/entrar/google?ligar=1").headers["location"] == "/entrar"


def test_google_respeta_la_cookie_del_conector(web_ctx):
    crear_usuario(web_ctx, "nueva@x.com")
    activar(web_ctx)
    cl = web_ctx.cliente()
    cl.cookies.set("oauth_volver", "/oauth/autorizar?client_id=x")
    r = vuelta(cl, empezar(web_ctx, cl))
    assert r.headers["location"] == "/oauth/autorizar?client_id=x"


def test_google_sin_cookie_y_con_plan_va_a_instalar(web_ctx):
    from tests.test_web_cuentas import crear_usuario as cu
    cu(web_ctx, "nueva@x.com", con_ajustes=True)
    activar(web_ctx)
    cl = web_ctx.cliente()
    r = vuelta(cl, empezar(web_ctx, cl))
    assert r.headers["location"] == "/instalar?siguiente=/"
