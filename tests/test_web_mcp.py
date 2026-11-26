"""F6b: servidor MCP en /mcp (lecturas) y la cookie de regreso del consentimiento."""
import json

from test_web_ajustes import listo
from web import oauth
from web.modelos import Coach, TokenOAuth

HEAD = {"Accept": "application/json, text/event-stream", "Content-Type": "application/json"}


def token_para(web_ctx, uid):
    with web_ctx.sesiones() as db:
        ahora = web_ctx.app.state.reloj().replace(tzinfo=None)
        t, _ = oauth._tokens_nuevos(db, None, ahora, client_id="c", usuario_id=uid, resource="https://ahilallevas.test/mcp")
        db.commit()
        return t["access_token"]


def rpc(cl, token, metodo, params=None, id_=1):
    h = dict(HEAD)
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = cl.post("/mcp/", headers=h, json={"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params or {}})
    return r


def cuerpo(r):
    txt = r.text
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        txt = next(l[5:] for l in txt.splitlines() if l.startswith("data:"))
    return json.loads(txt)


def llamar(cl, token, herramienta, **args):
    r = rpc(cl, token, "tools/call", {"name": herramienta, "arguments": args})
    assert r.status_code == 200, r.text
    res = cuerpo(r)["result"]
    return res.get("isError", False), res["content"][0]["text"]


def test_sin_token_o_token_malo_da_401_con_www_authenticate(web_ctx):
    uid, _ = listo(web_ctx, "a@x.com")
    with web_ctx.cliente() as cl:
        for tok in (None, "malo"):
            r = rpc(cl, tok, "tools/list")
            assert r.status_code == 401
            assert r.headers["www-authenticate"] == 'Bearer resource_metadata="https://ahilallevas.test/.well-known/oauth-protected-resource"'


def test_lecturas_propias_sin_serie_y_descripciones_en_espanol(web_ctx):
    uid, _ = listo(web_ctx, "a@x.com")
    tok = token_para(web_ctx, uid)
    with web_ctx.cliente() as cl:
        tools = cuerpo(rpc(cl, tok, "tools/list"))["result"]["tools"]
        nombres = {t["name"] for t in tools}
        assert nombres == {"resumen_hoy", "semana", "plan", "corridas_recientes", "progreso", "ver_ajustes", "historial", "mis_atletas"}
        assert all("dolor" in t["description"] and "médico" in t["description"] for t in tools)
        for n in nombres:
            err, txt = llamar(cl, tok, n)
            assert not err, (n, txt)
            assert '"serie"' not in txt
        err, txt = llamar(cl, tok, "semana")
        assert "sesiones_total" in txt


def test_el_token_de_a_no_lee_a_b_pero_el_coach_si_a_su_atleta(web_ctx):
    a, _ = listo(web_ctx, "a@x.com")
    b, _ = listo(web_ctx, "b@x.com")
    c, _ = listo(web_ctx, "c@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=b, coach_id=c))
        db.commit()
    ta, tc = token_para(web_ctx, a), token_para(web_ctx, c)
    with web_ctx.cliente() as cl:
        for n in ("semana", "ver_ajustes", "historial", "resumen_hoy"):
            err, txt = llamar(cl, ta, n, atleta=b)
            assert err and "No tienes acceso" in txt
        err, txt = llamar(cl, tc, "semana", atleta=b)
        assert not err and '"serie"' not in txt
        err, txt = llamar(cl, tc, "semana", atleta=a)   # el coach de B no es coach de A
        assert err
        err, txt = llamar(cl, tc, "mis_atletas")
        assert [x["id"] for x in json.loads(txt)["atletas"]] == [b]
        err, txt = llamar(cl, ta, "mis_atletas")
        assert json.loads(txt)["atletas"] == []


def test_token_revocado_da_401(web_ctx):
    uid, _ = listo(web_ctx, "a@x.com")
    tok = token_para(web_ctx, uid)
    with web_ctx.sesiones() as db:
        db.query(TokenOAuth).delete()
        db.commit()
    with web_ctx.cliente() as cl:
        assert rpc(cl, tok, "tools/list").status_code == 401


def test_volver_seguro_solo_acepta_ruta_relativa_al_consentimiento():
    ok = "/oauth/autorizar?client_id=1&state=x"
    assert oauth.volver_seguro(ok) == ok
    for malo in ("", "/", "https://evil.com", "//evil.com", "/oauth/autorizar", "/oauth/autorizarx?a=1", "/otra?x=1",
                 "/oauth/autorizar?a=\\\\evil.com", "/oauth/autorizar?a=1\r\nSet-Cookie: x=1", "javascript:alert(1)"):
        assert oauth.volver_seguro(malo) == "/"


def test_liga_no_redirige_fuera_con_cookie_manipulada(web_ctx):
    from test_web_cuentas import csrf_de
    from web import auth
    from web.modelos import Usuario
    uid, _ = listo(web_ctx, "a@x.com")
    cl = web_ctx.cliente()
    for cookie in ("https://evil.com", "//evil.com/oauth/autorizar?x=1", "/oauth/autorizar?x=1"):
        with web_ctx.sesiones() as db:
            t = auth.crear_liga(db, db.get(Usuario, uid))
        cl.cookies.set("oauth_volver", cookie)
        csrf = csrf_de(cl.get(f"/entrar/liga/{t}").text)
        r = cl.post(f"/entrar/liga/{t}", data={"csrf": csrf})
        assert r.status_code == 303, r.text
        assert r.headers["location"] == ("/oauth/autorizar?x=1" if cookie.startswith("/oauth/") else "/")
