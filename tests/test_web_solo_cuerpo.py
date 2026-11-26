from test_web_cuentas import csrf_de, entrar, post, crear_usuario
from web.modelos import Consentimiento, InBody, Usuario
from web.privacidad import VERSION_AVISO


def nuevo(ctx, correo="c@x.com", uso=None, consentido=True):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        if consentido:
            db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.get(Usuario, uid).uso = uso
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def token(cl, url="/bienvenida"):
    return csrf_de(cl.get(url).text)


def test_pregunta_de_uso_tras_el_aviso_y_cuerpo_completa_sin_repo(web_ctx):
    uid, cl = nuevo(web_ctx)
    r = cl.get("/bienvenida")
    assert "¿Qué quieres usar?" in r.text and "Solo mediciones de cuerpo" in r.text
    r = cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "cuerpo"})
    assert r.status_code == 303 and r.headers["location"] == "/"
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert u.uso == "cuerpo" and u.repo_id is None and u.github_owner is None
    assert cl.get("/").status_code == 200   # onboarding completo: ya no lo manda a /bienvenida
    assert cl.get("/bienvenida").headers["location"] == "/"


def test_completo_sigue_el_paso_a_paso(web_ctx):
    uid, cl = nuevo(web_ctx)
    r = cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "completo"})
    assert r.headers["location"] == "/bienvenida"
    assert "¿Qué quieres usar?" not in cl.get("/bienvenida").text
    assert "usuario de GitHub" in cl.get("/bienvenida").text
    assert cl.get("/").headers["location"] == "/bienvenida"
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).uso == "completo"


def test_sin_aviso_no_se_puede_elegir(web_ctx):
    uid, cl = nuevo(web_ctx, consentido=False)
    assert cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "cuerpo"}).status_code == 403


def test_cuenta_vieja_con_repo_no_ve_la_pregunta(web_ctx):
    uid, cl = nuevo(web_ctx)
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid).github_owner = "pepe"
        db.commit()
    assert "¿Qué quieres usar?" not in cl.get("/bienvenida").text


def test_cambio_a_completo_lleva_al_repo_y_conserva_mediciones(web_ctx):
    uid, cl = nuevo(web_ctx, uso="cuerpo")
    pagina = cl.get("/ajustes")
    assert pagina.status_code == 200 and "Activar entrenamiento con Garmin" in pagina.text
    r = cl.post("/cuerpo/nuevo", data={"csrf": csrf_de(cl.get("/cuerpo/nuevo").text), "fecha": "2026-11-20", "peso_kg": "80"})
    assert r.status_code == 303
    r = cl.post("/ajustes/uso", data={"csrf": csrf_de(pagina.text)})
    assert r.status_code == 303 and r.headers["location"] == "/bienvenida"
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).uso == "completo"
        assert db.query(InBody).count() == 1
    assert "usuario de GitHub" in cl.get("/bienvenida").text
    assert cl.get("/").headers["location"] == "/bienvenida"


def test_ajustes_uso_sin_sesion_va_a_entrar(web_ctx):
    cl = web_ctx.cliente()
    cl.get("/entrar")
    assert cl.post("/ajustes/uso", data={"csrf": "x"}).status_code in (303, 403)
