"""Parte 2, E3: primer inicio (ui.primer_inicio): tarjeta de Garmin, «+ Registrar actividad» y primeros pasos."""
from dashboard import validar
from test_web_ajustes import listo
from test_web_coach import dar
from test_web_cuentas import crear_usuario, entrar
from web.modelos import Ajustes, Consentimiento, InBody, Grupo, MiembroGrupo, Usuario
from web.privacidad import VERSION_AVISO


def nuevo(ctx, correo="n@x.com"):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def pi(cl, url="/data.json"):
    d = cl.get(url).json()
    assert validar.problemas(d) == []
    return d["ui"]["primer_inicio"]


def test_cuenta_nueva_registra_primera_corrida_desde_hoy(web_ctx):
    from test_web_actividad import datos, enviar

    _, cl = nuevo(web_ctx)
    antes = cl.get("/data.json").json()
    assert antes["datos_al"] is None
    assert antes["hoy"]["tarjeta"]["tipo"] != "primera_sync"
    assert antes["semana_libre"]["actividades"] == 0
    registrar = antes["ui"]["primer_inicio"]["registrar"]
    respuesta = enviar(cl, registrar, datos(fecha=antes["generado"][:10]))
    assert respuesta.status_code == 303 and respuesta.headers["location"] == "/#hoy"
    despues = cl.get("/data.json").json()
    assert despues["datos_al"] is None
    assert despues["semana_libre"]["actividades"] == 1
    assert despues["semana_libre"]["minutos"] == 30


def test_tarjeta_garmin_sin_copia_conectado_y_oculta(web_ctx):
    uid, cl = nuevo(web_ctx)
    assert pi(cl)["garmin"] == {"conectar": "/bienvenida", "liga": "/bienvenida/liga", "ocultar": "/avisos/ocultar"}
    token = cl.get("/").text.split('data-csrf="')[1].split('"')[0]
    assert cl.post("/avisos/ocultar", data={"id": "garmin", "huella": "0"}).status_code == 403   # sin CSRF
    assert cl.post("/avisos/ocultar", data={"id": "garmin", "huella": "0", "csrf": token}).json() == {"ok": True}
    assert pi(cl)["garmin"] is None   # oculta
    uid2, cl2 = nuevo(web_ctx, "c@x.com")
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid2)
        u.repo_id, u.repo = 123, "x/y"
        db.commit()
    assert pi(cl2)["garmin"] is None   # conectado


def test_registrar_siempre_esta_tambien_con_garmin(web_ctx):
    uid, cl = nuevo(web_ctx)
    assert pi(cl)["registrar"] == "/actividad/nueva"
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid).repo_id = 5
        db.commit()
    p = pi(cl)
    assert p["registrar"] == "/actividad/nueva" and p["garmin"] is None


def test_cada_primer_paso_se_va_al_cumplirse(web_ctx):
    uid, cl = nuevo(web_ctx)
    ids = lambda: [p["id"] for p in pi(cl)["pasos"]]
    assert ids() == ["plan", "grupo", "inbody"]
    with web_ctx.sesiones() as db:
        db.add(InBody(usuario_id=uid, fecha="2026-11-20", valores={"fecha": "2026-11-20", "peso_kg": 80.0}))
        db.commit()
    assert ids() == ["plan", "grupo"]
    with web_ctx.sesiones() as db:
        g = Grupo(nombre="G", creado_por=uid)
        db.add(g)
        db.commit()
        db.add(MiembroGrupo(grupo_id=g.id, usuario_id=uid))
        db.commit()
    assert ids() == ["plan"]
    with web_ctx.sesiones() as db:
        from test_web_ajustes import CONFIG
        import copy
        db.add(Ajustes(usuario_id=uid, config=copy.deepcopy(CONFIG)))
        db.commit()
    assert ids() == []


def test_coach_ve_registrar_con_prefijo_sin_garmin_ni_grupos(web_ctx):
    uid_a, atleta = listo(web_ctx, "atleta@x.com")
    uid_c, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    dar(atleta, "coach@x.com")
    p = pi(coach, f"/a/{uid_a}/data.json")
    assert p["garmin"] is None and p["registrar"] == f"/a/{uid_a}/actividad/nueva"
    assert all(x["id"] != "grupo" for x in p["pasos"])


def test_conexiones_de_ajustes_muestra_conectar_sin_copia(web_ctx):
    uid, cl = nuevo(web_ctx)
    cl.post("/avisos/ocultar", data={"id": "garmin", "huella": "0", "csrf": cl.get("/").text.split('data-csrf="')[1].split('"')[0]})
    html = cl.get("/ajustes").text
    assert 'href="/bienvenida"' in html and "Conectar Garmin" in html   # también si quitó la tarjeta


def test_guia_activa_ya_no_exige_sin_ajustes():
    from types import SimpleNamespace as S
    from web.onboarding import guia_activa
    e = {"consentimiento": True, "datos": False, "vinculado": False, "ajustes": True}
    assert guia_activa(S(app_github=True), S(gh_instalacion=None), e)
