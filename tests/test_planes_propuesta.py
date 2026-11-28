"""P3: vista previa de «Repetir o retomar» (/plan/propuesta.json), POST de retomar y MCP."""
import copy

from web import calculo
from web.modelos import Ajustes, CacheData, Cambio, Plan, Usuario
from ayudas import CONFIG, crudo, crudo_carrera, HOY, listo, plan_carrera, tok


def _con_carrera(ctx, uid):
    plan = plan_carrera()
    with ctx.sesiones() as db:
        db.get(Ajustes, uid).config = crudo_carrera(plan)
        db.get(Plan, uid).plan = plan
        db.commit()


def _estado(ctx, uid):
    with ctx.sesiones() as db:
        c = db.get(CacheData, uid)
        return (copy.deepcopy(db.get(Ajustes, uid).config), db.get(Ajustes, uid).version, db.query(Cambio).count(),
                None if c is None else (c.huella, c.calculado))


def test_propuesta_repetir_no_escribe_nada(web_ctx):
    uid, cl = listo(web_ctx)
    cl.get("/data.json")   # llena la caché
    antes = _estado(web_ctx, uid)
    r = cl.get("/plan/propuesta.json?accion=repetir")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    j = r.json()
    assert j["aviso"] is None and j["info"]["k"] == 1 and j["info"]["quita"] == [] and j["info"]["objetivo"] is False
    assert j["aplicar"] == {"url": "/plan/repetir", "semana": None}
    assert len(j["plan"]["semanas"]) == 12 and j["plan"]["semana_actual"] == 3
    assert _estado(web_ctx, uid) == antes
    assert antes[0] == CONFIG   # los ajustes guardados siguen intactos


def test_propuesta_retomar(web_ctx):
    uid, cl = listo(web_ctx)
    j = cl.get("/plan/propuesta.json?accion=retomar&semana=1").json()
    assert j["info"]["k"] == 2 and j["aplicar"] == {"url": "/plan/retomar", "semana": 1}
    assert j["plan"]["semana_actual"] == 1
    for malo in ("accion=retomar&semana=9", "accion=retomar&semana=x", "accion=retomar", "accion=otra", ""):
        r = cl.get(f"/plan/propuesta.json?{malo}")
        assert r.status_code == 400 and r.json()["error"], malo
    assert crudo(web_ctx, uid) == CONFIG


def test_propuesta_con_carrera_objetivo_avisa_y_quita(web_ctx):
    uid, cl = listo(web_ctx)
    _con_carrera(web_ctx, uid)
    j = cl.get("/plan/propuesta.json?accion=retomar&semana=1").json()
    assert j["info"]["objetivo"] and j["info"]["quita"] == [10, 11]
    assert j["aviso"].startswith("No se recomienda") and "10, 11" in j["aviso"]
    assert len(j["plan"]["semanas"]) == 14
    j = cl.get("/plan/propuesta.json?accion=repetir").json()
    assert j["info"]["quita"] == [11] and "11" in j["aviso"]


def test_propuesta_sin_semana_en_curso_es_400(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        a = db.get(Ajustes, uid)
        c = copy.deepcopy(a.config)
        c["corrida"]["inicio"] = "2026-06-01"   # el plan ya terminó
        a.config = c
        db.commit()
    r = cl.get("/plan/propuesta.json?accion=repetir")
    assert r.status_code == 400 and "semana" in r.json()["error"]


def test_post_retomar_crea_cambio_y_se_deshace(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "2"})
    assert r.status_code == 303
    assert crudo(web_ctx, uid)["corrida"]["saltos"] == [{"lunes": "2026-11-23", "semana": 2, "quita": []}]
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
        assert c.descripcion == "Retomó desde la semana 2"
    assert cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "9"}).status_code == 400
    assert cl.post("/plan/retomar", data={"csrf": tok(cl)}).status_code == 400
    assert cl.post("/plan/retomar", data={"semana": "1"}).status_code in (400, 403)   # sin CSRF
    with web_ctx.sesiones() as db:   # el cambio se fecha con el reloj real: se alinea con el de la prueba
        db.get(Cambio, c.id).fecha = HOY.replace(tzinfo=None)
        db.commit()
    cl.post(f"/historial/{c.id}/deshacer", data={"csrf": tok(cl)})
    assert crudo(web_ctx, uid) == CONFIG


def test_post_retomar_con_carrera_anota_las_semanas_quitadas(web_ctx):
    uid, cl = listo(web_ctx)
    _con_carrera(web_ctx, uid)
    cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "1"})
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).one().descripcion == "Retomó desde la semana 1; se quitaron las semanas 10, 11"


def test_permisos_de_propuesta_y_retomar(web_ctx):
    uid_a, _ = listo(web_ctx, "a@x.com")
    _, cl_b = listo(web_ctx, "b@x.com")
    assert cl_b.get(f"/a/{uid_a}/plan/propuesta.json?accion=repetir").status_code == 404
    assert cl_b.post(f"/a/{uid_a}/plan/retomar", data={"csrf": tok(cl_b), "semana": "1"}).status_code == 404
    assert crudo(web_ctx, uid_a) == CONFIG
    anonimo = web_ctx.cliente()
    assert anonimo.get("/plan/propuesta.json?accion=repetir", follow_redirects=False).status_code == 303


def test_coach_ve_propuesta_con_prefijo(web_ctx):
    from web.modelos import Coach
    uid_a, _ = listo(web_ctx, "atleta@x.com")
    uid_c, cl_c = listo(web_ctx, "coach@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    j = cl_c.get(f"/a/{uid_a}/plan/propuesta.json?accion=retomar&semana=1").json()
    assert j["aplicar"]["url"] == f"/a/{uid_a}/plan/retomar"
    ui = cl_c.get(f"/a/{uid_a}/data.json").json()["ui"]
    assert ui["propuesta_url"] == f"/a/{uid_a}/plan/propuesta.json" and ui["retomar_url"] == f"/a/{uid_a}/plan/retomar"


def test_ui_trae_las_opciones_de_retomar_con_fechas(web_ctx):
    uid, cl = listo(web_ctx)
    ui = cl.get("/data.json").json()["ui"]
    assert ui["propuesta_url"] == "/plan/propuesta.json" and ui["retomar_url"] == "/plan/retomar"
    assert ui["retomar_opciones"] == [{"semana": 1, "desde": "2026-11-09", "hasta": "2026-11-15"},
                                      {"semana": 2, "desde": "2026-11-16", "hasta": "2026-11-22"}]
    # tras repetir, la secuencia cambia: la semana 3 ya pasó y es una opción más
    cl.post("/plan/repetir", data={"csrf": tok(cl)})
    web_ctx.app.state.reloj = lambda: HOY.replace(day=2, month=12)   # miércoles de la semana siguiente (otra vez la 3)
    ui = cl.get("/data.json").json()["ui"]
    assert [o["semana"] for o in ui["retomar_opciones"]] == [1, 2]


def test_ui_sin_semana_en_curso_no_ofrece_nada(web_ctx):
    uid, cl = listo(web_ctx)
    web_ctx.app.state.reloj = lambda: HOY.replace(year=2025)
    ui = cl.get("/data.json").json()["ui"]
    assert ui["propuesta_url"] is None and ui["retomar_opciones"] == []


def test_calcular_propuesta_no_toca_la_cache(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        nuevo = copy.deepcopy(CONFIG)
        d = calculo.calcular_propuesta(db, u, nuevo, HOY.replace(tzinfo=None))
        assert "plan" in d and db.get(CacheData, uid) is None


def test_mcp_repetir_semana_con_semana_retoma(web_ctx):
    from web import mcp_servidor
    uid, _ = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        r = mcp_servidor.repetir_semana(db, u, HOY.replace(tzinfo=None), None, semana=1)
        assert r["hecho"] == "Retomó desde la semana 1 (IA)"
        assert db.query(Cambio).one().descripcion == "Retomó desde la semana 1 (IA)"
        r = mcp_servidor.repetir_semana(db, u, HOY.replace(tzinfo=None), None)
        assert r["hecho"].startswith("Repitió la semana")
