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


def rpc(cl, token, metodo, params=None, id_=1, ruta="/mcp"):   # la URL tal cual la usan Claude y ChatGPT
    h = dict(HEAD)
    if token:
        h["Authorization"] = f"Bearer {token}"
    r = cl.post(ruta, headers=h, json={"jsonrpc": "2.0", "id": id_, "method": metodo, "params": params or {}})
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
        assert rpc(cl, tok, "tools/list", ruta="/mcp/").status_code == 200   # con diagonal también
        tools = cuerpo(rpc(cl, tok, "tools/list"))["result"]["tools"]
        nombres = {t["name"] for t in tools}
        assert nombres == {"resumen_hoy", "semana", "plan", "corridas_recientes", "progreso", "ver_ajustes", "historial", "mis_atletas"} | {"agregar_carrera", "agregar_evento", "editar_sesion", "repetir_semana", "registrar_inbody", "deshacer"}
        assert all("dolor" in t["description"] and "médico" in t["description"] for t in tools)
        for n in nombres - {"agregar_carrera", "agregar_evento", "editar_sesion", "repetir_semana", "registrar_inbody", "deshacer"}:
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


def _vias(web_ctx, uid):
    from web.modelos import Cambio
    with web_ctx.sesiones() as db:
        return [(c.via, c.autor_id) for c in db.query(Cambio).filter(Cambio.atleta_id == uid).all()]


def test_escrituras_registran_via_ia_y_se_deshacen(web_ctx):
    from web import cambios
    from web.modelos import Ajustes
    uid, _ = listo(web_ctx, "a@x.com")
    tok = token_para(web_ctx, uid)
    with web_ctx.cliente() as cl:
        err, txt = llamar(cl, tok, "agregar_evento", tipo="viaje", desde="2026-12-01", hasta="2026-12-05")
        assert not err, txt
        r = json.loads(txt)
        assert "deshacer" in r["para_deshacer"]
        with web_ctx.sesiones() as db:
            ev = db.get(Ajustes, uid).config["corrida"]["eventos"]
            assert ev[-1]["modo"] == "igual"
        err, txt = llamar(cl, tok, "agregar_evento", tipo="viaje", desde="2026-12-10", hasta="2026-12-12", modo="pausa")
        assert not err, txt
        err, txt = llamar(cl, tok, "agregar_carrera", fecha="2027-01-10", nombre="10K", distancia_km=10)
        assert not err, txt
        err, txt = llamar(cl, tok, "registrar_inbody", fecha="2026-11-20", peso_kg=80, mme_kg=35, pgc=20)
        assert not err, txt
        err, txt = llamar(cl, tok, "repetir_semana")
        assert not err, txt
        err, txt = llamar(cl, tok, "agregar_evento", tipo="viaje", desde="2026-12-01", hasta=None)
        assert err and "regreso" in txt
        err, txt = llamar(cl, tok, "agregar_carrera", fecha="2020-01-01")
        assert err
        err, txt = llamar(cl, tok, "agregar_evento", tipo="viaje", desde="2026-12-20", hasta="2026-12-22")
        cid = json.loads(txt)["cambio_id"]
        err, txt = llamar(cl, tok, "deshacer", cambio_id=cid)
        assert not err, txt
    vias = _vias(web_ctx, uid)
    assert vias and all(v == ("ia", uid) for v in vias)
    with web_ctx.sesiones() as db:
        ev = db.get(Ajustes, uid).config["corrida"]["eventos"]
        assert not any(e["desde"] == "2026-12-20" for e in ev)


def test_ia_de_otro_no_escribe_y_coach_si(web_ctx):
    a, _ = listo(web_ctx, "a@x.com")
    b, _ = listo(web_ctx, "b@x.com")
    c, _ = listo(web_ctx, "c@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=b, coach_id=c))
        db.commit()
    ta, tc = token_para(web_ctx, a), token_para(web_ctx, c)
    with web_ctx.cliente() as cl:
        err, txt = llamar(cl, ta, "agregar_carrera", fecha="2027-02-01", atleta=b)
        assert err and "No tienes acceso" in txt
        err, txt = llamar(cl, tc, "agregar_carrera", fecha="2027-02-01", atleta=b)
        assert not err, txt
        err, txt = llamar(cl, ta, "deshacer", cambio_id=json.loads(txt)["cambio_id"])
        assert err
    assert _vias(web_ctx, b) == [("ia", c)]


def test_conexiones_lista_revoca_y_el_token_revocado_da_401(web_ctx):
    from test_web_cuentas import csrf_de
    uid, cl = listo(web_ctx, "a@x.com")
    tok = token_para(web_ctx, uid)
    with web_ctx.sesiones() as db:
        from web.modelos import ClienteOAuth
        db.add(ClienteOAuth(client_id="c", nombre="Claude", redirect_uris=["https://claude.ai/cb"]))
        db.commit()
        tid = db.query(TokenOAuth).one().id
    r = cl.get("/conexiones")
    assert r.status_code == 200 and "Claude" in r.text and "Revocar" in r.text
    assert "/ayuda/conector" in r.text and "/mcp" in cl.get("/ayuda/conector").text
    r = cl.post(f"/conexiones/{tid}/revocar", data={"csrf": csrf_de(r.text)})
    assert r.status_code == 303
    with web_ctx.cliente() as c2:
        assert rpc(c2, tok, "tools/list").status_code == 401


def test_sin_plan_las_herramientas_de_plan_dan_rechazo_claro(web_ctx):
    from web.modelos import Usuario
    uid, _ = listo(web_ctx, "a@x.com")
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid).sin_plan = True
        db.commit()
    tok = token_para(web_ctx, uid)
    with web_ctx.cliente() as cl:
        for herr, args in [("plan", {}), ("semana", {}), ("repetir_semana", {}),
                           ("agregar_evento", {"tipo": "viaje", "desde": "2026-12-01"})]:
            err, txt = llamar(cl, tok, herr, **args)
            assert err and "no tiene plan de running" in txt, (herr, txt)
        err, txt = llamar(cl, tok, "resumen_hoy")
        assert "no tiene plan de running" not in txt
