"""L1 «Sin plan»: la pregunta del onboarding, el modo sin plan, los interruptores de Ajustes y un data.json válido sin plan."""
from dashboard import validar
from test_web_cuentas import crear_usuario, csrf_de, entrar
from test_web_solo_cuerpo import nuevo, token
from web.modelos import Ajustes, Plan, Usuario


def vincular(ctx, uid):
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.github_owner, u.repo, u.repo_id = "pepe", "pepe/mi-entreno", 123
        db.commit()


def test_cuenta_nueva_por_defecto_sin_plan_y_completa_con_el_repo(web_ctx):
    uid, cl = nuevo(web_ctx)
    r = cl.get("/bienvenida")
    assert "¿Qué quieres usar?" in r.text and "¿Quieres un plan de running?" not in r.text   # F4: el plan se arma desde la app
    r = cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "completo"})   # sin tocar la pregunta: No
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).sin_plan is True
    assert cl.get("/").headers["location"] == "/bienvenida"   # sin repo aún no está completo
    vincular(web_ctx, uid)
    assert cl.get("/bienvenida").headers["location"] == "/"   # con el repo conectado, ya no hay cuestionario del plan
    assert cl.get("/").status_code == 200


def test_el_onboarding_ya_no_pregunta_el_plan_ni_lo_activa(web_ctx):
    uid, cl = nuevo(web_ctx)
    cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "completo", "plan": "si"})   # un cliente viejo mandaría esto: se ignora
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).sin_plan is True
    vincular(web_ctx, uid)
    assert cl.get("/").status_code == 200   # completo con el repo; el plan se arma en /plan/nuevo


def test_data_json_sin_plan_valido_con_ui_sin_plan(web_ctx):
    uid, cl = nuevo(web_ctx)
    cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "completo"})
    vincular(web_ctx, uid)
    d = cl.get("/data.json").json()
    assert validar.problemas(d) == []
    assert d["ui"]["sin_plan"] is True and d["plan"]["semanas"] == []
    assert not d["ui"].get("solo_cuerpo")


def test_ajustes_quiero_un_plan_lleva_al_cuestionario(web_ctx):
    uid, cl = nuevo(web_ctx)
    cl.post("/bienvenida/uso", data={"csrf": token(cl), "uso": "completo"})
    vincular(web_ctx, uid)
    pagina = cl.get("/ajustes")
    assert pagina.status_code == 200 and "Quiero un plan de running" in pagina.text   # sin ajustes: la página de ajustes sin plan
    r = cl.post("/ajustes/plan", data={"csrf": csrf_de(pagina.text), "accion": "quiero"})
    assert r.status_code == 303 and r.headers["location"] == "/plan/nuevo"
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).sin_plan is True   # sigue sin plan hasta que confirme el plan nuevo


def test_quitar_mi_plan_conserva_el_plan_y_con_plan_no_cambia_nada(web_ctx):
    uid = crear_usuario(web_ctx, "p@x.com", con_ajustes=True)
    cl = entrar(web_ctx, web_ctx.cliente(), "p@x.com")
    d = cl.get("/data.json").json()
    assert d["ui"]["sin_plan"] is False and d["plan"]["semanas"]   # el camino con plan sigue igual
    pagina = cl.get("/plan/acciones")
    assert "Quitar mi plan" in pagina.text and "Quiero un plan de running" not in pagina.text
    assert "Quitar mi plan" not in cl.get("/ajustes").text
    r = cl.post("/ajustes/plan", data={"csrf": csrf_de(pagina.text), "accion": "quitar"})
    assert r.status_code == 303 and r.headers["location"] == "/"
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).sin_plan is True and db.get(Ajustes, uid) is not None
    d = cl.get("/data.json").json()
    assert validar.problemas(d) == [] and d["ui"]["sin_plan"] is True and d["plan"]["semanas"] == []
    pagina = cl.get("/plan/acciones")
    assert "Quiero un plan de running" in pagina.text and "Quitar mi plan" not in pagina.text
    pagina = cl.get("/plan/acciones")
    r = cl.post("/ajustes/plan", data={"csrf": csrf_de(pagina.text), "accion": "quiero"})
    assert r.headers["location"] == "/plan/nuevo"   # el plan se arma ahí; hasta confirmarlo sigue sin plan
    assert 'href="/plan/nuevo"' in pagina.text
