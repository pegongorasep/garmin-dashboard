import json
import re
from pathlib import Path
from datetime import timedelta

from ajustes import leer_config_yaml
from web import auth
from web.modelos import Ajustes, Coach, Consentimiento, LigaLogin, Sesion, Usuario, ahora


CONFIG = json.loads(json.dumps(leer_config_yaml(Path(__file__).parent / "fixtures" / "config.yaml"), default=str))


def csrf_de(html: str) -> str:
    return re.search(r'name="csrf" value="([^"]+)"', html).group(1)


def post(cl, url, **campos):
    """GET a la página (para la cookie y el token CSRF) y luego POST con el token."""
    r = cl.get(url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **campos})


def liga_de(ctx) -> str:
    return re.search(r"https://ahilallevas\.test(/entrar/liga/\S+)", ctx.enviados[-1][2]).group(1)


def entrar(ctx, cl, correo):
    post(cl, "/entrar", correo=correo)
    url = liga_de(ctx)
    r = cl.get(url)
    cl.post(url, data={"csrf": csrf_de(r.text)})
    return cl


def crear_usuario(ctx, correo="a@x.com", con_ajustes=False):
    with ctx.sesiones() as db:
        u = Usuario(correo=correo)
        db.add(u)
        db.commit()
        if con_ajustes:
            db.add(Ajustes(usuario_id=u.id, config=CONFIG))
            db.add(Consentimiento(usuario_id=u.id, version_aviso="2026-12"))
            db.commit()
        return u.id


def test_invitacion_de_un_solo_uso(web_ctx):
    with web_ctx.sesiones() as db:
        token = auth.crear_invitacion(db, None, "Adrián")
        # en la base solo queda el hash
        assert token not in str(db.execute(auth.select(auth.Invitacion.token_hash)).scalars().all())
    cl = web_ctx.cliente()
    assert "Adrián" in cl.get(f"/invitacion/{token}").text
    r = post(cl, f"/invitacion/{token}", correo="Nuevo@Ejemplo.com")
    assert auth.MENSAJE_LIGA in r.text
    assert len(web_ctx.enviados) == 1 and web_ctx.enviados[0][0] == "nuevo@ejemplo.com"
    # segunda vez: ya no sirve
    assert "ya se usó" in cl.get(f"/invitacion/{token}").text
    otro = web_ctx.cliente()
    r = otro.post(f"/invitacion/{token}", data={"csrf": csrf_de(otro.get("/entrar").text), "correo": "otro@ejemplo.com"})
    assert r.status_code == 400
    with web_ctx.sesiones() as db:
        assert auth.buscar_por_correo(db, "otro@ejemplo.com") is None


def test_invitacion_vencida(web_ctx):
    with web_ctx.sesiones() as db:
        token = auth.crear_invitacion(db, None)
        inv = db.get(auth.Invitacion, auth.hash_token(token))
        inv.expira = ahora() - timedelta(seconds=1)
        db.commit()
    assert "ya se usó o venció" in web_ctx.cliente().get(f"/invitacion/{token}").text


def test_invitacion_con_correo_existente_no_se_gasta_ni_revela(web_ctx):
    crear_usuario(web_ctx, "ya@x.com")
    with web_ctx.sesiones() as db:
        token = auth.crear_invitacion(db, None)
    r = post(web_ctx.cliente(), f"/invitacion/{token}", correo="ya@x.com")
    assert auth.MENSAJE_LIGA in r.text and len(web_ctx.enviados) == 1
    with web_ctx.sesiones() as db:
        assert auth.invitacion_vigente(db, token) is not None


def test_login_misma_respuesta_exista_o_no(web_ctx):
    crear_usuario(web_ctx, "si@x.com")
    cl = web_ctx.cliente()
    a = post(cl, "/entrar", correo="si@x.com")
    b = post(cl, "/entrar", correo="no@x.com")
    assert auth.MENSAJE_LIGA in a.text and auth.MENSAJE_LIGA in b.text
    assert [e[0] for e in web_ctx.enviados] == ["si@x.com"]


def test_limite_de_cinco_ligas_por_hora(web_ctx):
    crear_usuario(web_ctx, "si@x.com")
    cl = web_ctx.cliente()
    for _ in range(7):
        post(cl, "/entrar", correo="si@x.com")
    assert len(web_ctx.enviados) == 5


def test_liga_un_uso_y_sesion(web_ctx):
    crear_usuario(web_ctx, "si@x.com", con_ajustes=False)
    cl = web_ctx.cliente()
    post(cl, "/entrar", correo="si@x.com")
    url = liga_de(web_ctx)
    # abrir la liga (un escáner de correo) no la gasta
    page = cl.get(url)
    assert "Entrar a Ahí la Llevas" in page.text and cl.get(url).status_code == 200
    r = cl.post(url, data={"csrf": csrf_de(page.text)})
    assert r.status_code == 303 and r.headers["location"] == "/"
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=lax" in cookie
    r = cl.get("/")   # sin consentimiento ni plan: al onboarding
    assert r.status_code == 303 and r.headers["location"] == "/bienvenida"
    # la liga ya no vale
    assert "ya se usó o venció" in web_ctx.cliente().get(url).text
    assert cl.post(url, data={"csrf": csrf_de(cl.get("/salir").text)}).status_code == 400


def test_liga_vencida(web_ctx):
    crear_usuario(web_ctx, "si@x.com")
    post(web_ctx.cliente(), "/entrar", correo="si@x.com")
    with web_ctx.sesiones() as db:
        for liga in db.query(LigaLogin):
            liga.expira = ahora() - timedelta(minutes=1)
        db.commit()
    assert "ya se usó o venció" in web_ctx.cliente().get(liga_de(web_ctx)).text


def test_salir_borra_la_sesion(web_ctx):
    crear_usuario(web_ctx, "si@x.com")
    cl = entrar(web_ctx, web_ctx.cliente(), "si@x.com")
    assert cl.get("/data.json").status_code == 404   # sesión válida, sin ajustes
    r = post(cl, "/salir")
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        assert db.query(Sesion).count() == 0
    assert cl.get("/data.json").status_code == 401


def test_sesion_vence_a_los_60_dias_y_se_renueva(web_ctx):
    uid = crear_usuario(web_ctx, "si@x.com")
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        valor = auth.crear_sesion(db, u)
        s = db.get(Sesion, auth.hash_token(valor))
        s.ultima_vez, s.expira = ahora() - timedelta(hours=2), ahora() + timedelta(days=1)
        db.commit()
        assert auth.usuario_de_sesion(db, valor).id == uid
        assert db.get(Sesion, auth.hash_token(valor)).expira > ahora() + timedelta(days=59)
        s.expira = ahora() - timedelta(seconds=1)
        db.commit()
        assert auth.usuario_de_sesion(db, valor) is None


def test_post_sin_csrf_o_con_csrf_falso_da_403(web_ctx):
    crear_usuario(web_ctx, "si@x.com")
    cl = web_ctx.cliente()
    assert cl.post("/entrar", data={"correo": "si@x.com"}).status_code == 403
    cl.get("/entrar")
    assert cl.post("/entrar", data={"correo": "si@x.com", "csrf": "falso"}).status_code == 403
    # el token de otra cookie tampoco sirve
    otro = web_ctx.cliente()
    token_ajeno = csrf_de(otro.get("/entrar").text)
    assert cl.post("/entrar", data={"correo": "si@x.com", "csrf": token_ajeno}).status_code == 403
    assert web_ctx.enviados == []
    assert web_ctx.cliente().post("/salir", data={}).status_code == 403


def test_nadie_ve_el_data_json_de_otro(web_ctx):
    a = crear_usuario(web_ctx, "a@x.com", con_ajustes=True)
    b = crear_usuario(web_ctx, "b@x.com", con_ajustes=True)
    cl = entrar(web_ctx, web_ctx.cliente(), "a@x.com")
    assert cl.get(f"/a/{b}/data.json").status_code == 404
    assert cl.get("/a/9999/data.json").status_code == 404
    # con acceso de coach sí (ver F5), y quitarlo lo corta
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=b, coach_id=a))
        db.commit()
    assert cl.get(f"/a/{b}/data.json").status_code != 404
    with web_ctx.sesiones() as db:
        db.query(Coach).delete()
        db.commit()
    assert cl.get(f"/a/{b}/data.json").status_code == 404


def test_permisos_puede_ver_y_editar(web_ctx):
    from web.permisos import puede_editar, puede_ver
    a = crear_usuario(web_ctx, "a@x.com")
    b = crear_usuario(web_ctx, "b@x.com")
    with web_ctx.sesiones() as db:
        ua, ub = db.get(Usuario, a), db.get(Usuario, b)
        assert puede_ver(db, ua, a) and puede_editar(db, ua, a)
        assert not puede_ver(db, ua, b) and not puede_editar(db, ua, b) and not puede_ver(db, None, a)
        ua.es_admin = True   # el admin no ve a los demás
        assert not puede_ver(db, ua, b)


def test_sin_sesion_no_hay_data_y_el_sitio_no_sirve_data_json_del_disco(web_ctx):
    cl = web_ctx.cliente()
    assert cl.get("/data.json").status_code == 401
    assert "Entrar" in cl.get("/").text
    for nombre in ("app.js", "vistas.js", "charts.js", "iconos.js", "styles.css"):
        assert cl.get("/" + nombre).status_code == 200
    for nombre in ("index.html", "../config.yaml", "plan.json", ".env"):
        assert cl.get("/" + nombre).status_code == 404
    assert cl.get("/salud").json() == {"ok": True}


def test_cabeceras_de_seguridad(web_ctx):
    r = web_ctx.cliente().get("/")
    assert r.headers["x-frame-options"] == "DENY" and "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
