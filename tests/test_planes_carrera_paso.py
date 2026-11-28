"""P5: carrera de paso (reemplaza la larga de su semana, el plan guardado no cambia), «Entrenar para esta carrera» y MCP."""
import copy
import json
from datetime import date, timedelta

import metrics as m
import planes_v6
from ajustes import normalizar_config
from test_planes_saltos import cfg_de, crudo_carrera, crudo_con, plan_carrera
from test_web_ajustes import CONFIG, HOY, crudo, listo, tok
from test_web_mcp import cuerpo, llamar, rpc, token_para
from web import plan_vivo
from web.modelos import Ajustes, Cambio, Plan

INI = date(2026, 11, 9)
LUN = lambda n: INI + timedelta(weeks=n - 1)   # noqa: E731  lunes de la semana n (sin saltos)
HOY_D = date(2026, 11, 25)                     # semana 3


def plan_base():
    return planes_v6.generar(normalizar_config(CONFIG))


def con_carrera(n=6, km=10, nombre="10K de prueba", crudo_=None):
    return plan_vivo.agregar_carrera(crudo_ or CONFIG, (LUN(n) + timedelta(days=5)).isoformat(), km, nombre)


def ses(plan, n):
    return next(w for w in plan["weeks"] if w["n"] == n)["sessions"]


def test_la_carrera_reemplaza_la_larga_de_su_semana_y_el_plan_guardado_no_cambia():
    plan, antes = plan_base(), None
    antes = copy.deepcopy(plan)
    c = con_carrera()
    assert c["corrida"]["metas"][-1]["de_paso"] is True and "semanas" not in c["corrida"] or c["corrida"].get("semanas") == CONFIG["corrida"].get("semanas")
    cfg = cfg_de(c)
    efectivo = plan_vivo.plan_efectivo(plan, cfg)
    assert plan == antes   # el plan guardado no se toca
    larga = next(s for s in ses(plan, 6) if s["tipo"] == "larga")
    carrera = next(s for s in ses(efectivo, 6) if s["name"].startswith("Carrera: "))
    assert carrera["name"] == "Carrera: 10K de prueba" and carrera["id"] == larga["id"] and carrera["tipo"] == "larga"
    assert carrera["minutes"] == min(larga["minutes"], 50) and carrera["km"] == 10
    assert [s["id"] for s in ses(efectivo, 6)] == [s["id"] for s in ses(plan, 6)]
    assert all(efectivo["weeks"][i] == plan["weeks"][i] for i in range(12) if i != 5)
    assert ses(efectivo, 6) != ses(plan, 6)


def test_sin_km_la_carrera_dura_lo_de_la_larga():
    plan = plan_base()
    efectivo = plan_vivo.plan_efectivo(plan, cfg_de(con_carrera(km=None)))
    larga = next(s for s in ses(plan, 6) if s["tipo"] == "larga")
    carrera = next(s for s in ses(efectivo, 6) if s["id"] == larga["id"])
    assert carrera["minutes"] == larga["minutes"] and "km" not in carrera


def test_dentro_de_un_plan_con_carrera_objetivo_tambien():
    plan = plan_carrera()
    c = crudo_carrera(plan)
    c = plan_vivo.agregar_carrera(c, (LUN(4) + timedelta(days=6)).isoformat(), 5, "5K amiga")
    efectivo = plan_vivo.plan_efectivo(plan, cfg_de(c))
    assert any(s["name"] == "Carrera: 5K amiga" for s in ses(efectivo, 4))
    assert efectivo["weeks"][-1] == plan["weeks"][-1]   # la carrera objetivo no se toca
    assert plan_vivo.carrera_objetivo(plan, cfg_de(c))["id"] == "c1"


def test_semana_en_pausa_o_fuera_del_plan_solo_es_evento():
    plan = plan_base()
    pausa = plan_vivo.agregar_evento(con_carrera(), "enfermedad", LUN(6).isoformat(), (LUN(6) + timedelta(days=3)).isoformat())
    assert all(s["name"].startswith("Carrera: ") is False for w in plan_vivo.plan_efectivo(plan, cfg_de(pausa))["weeks"] for s in w["sessions"])
    fuera = plan_vivo.agregar_carrera(CONFIG, "2027-09-12", 10, "Lejos")
    assert plan_vivo.plan_efectivo(plan, cfg_de(fuera)) == plan
    from dashboard import build
    assert build.eventos_plan(cfg_de(fuera))["eventos"][0]["nombre"] == "Lejos"


def test_la_semana_conserva_su_marca_de_carrera():
    from dashboard import build
    cfg = cfg_de(con_carrera())
    w = plan_vivo.plan_efectivo(plan_base(), cfg)["weeks"][5]
    assert build.marca_semana(w, LUN(6), cfg) == "carrera"


def test_repetir_deja_la_carrera_en_su_fecha_y_reemplaza_la_larga_de_la_semana_que_ahora_cae_ahi():
    plan = plan_base()
    c = con_carrera(n=6)
    nuevo, info = plan_vivo.repetir(c, plan, cfg_de(c, HOY_D), HOY_D)   # repite la semana 3: todo se recorre una semana
    cfg = cfg_de(nuevo, HOY_D)
    assert info["k"] == 1
    efectivo = plan_vivo.plan_efectivo(plan, cfg)
    assert m.semana_del_plan(LUN(6) + timedelta(days=5), cfg) == 5   # la fecha de la carrera cae ahora en la semana 5 del plan
    assert any(s["name"].startswith("Carrera: ") for s in ses(efectivo, 5))
    assert not any(s["name"].startswith("Carrera: ") for s in ses(efectivo, 6))
    assert nuevo["corrida"]["metas"] == c["corrida"]["metas"]


def test_quitar_la_carrera_de_paso_no_rehace_nada():
    plan = plan_base()
    c = con_carrera()
    cfg = cfg_de(c)
    mid = cfg["metas"][0]["id"]
    sin, plan_n = plan_vivo.quitar_meta_en_plan(c, plan, cfg, mid, HOY_D)
    assert plan_n is None and sin["corrida"]["metas"] == [] and sin["corrida"].get("semanas") == c["corrida"].get("semanas")
    assert plan_vivo.plan_efectivo(plan, cfg_de(sin)) is plan


def test_una_corrida_ese_dia_cuenta_como_la_sesion_de_carrera():
    plan = plan_base()
    c = con_carrera(km=10)
    efectivo = plan_vivo.plan_efectivo(plan, cfg_de(c))
    semana = next(w for w in efectivo["weeks"] if w["n"] == 6)
    cfg = cfg_de(c)
    carrera = next(s for s in semana["sessions"] if s.get("carrera"))
    dia = (LUN(6) + timedelta(days=5)).isoformat()
    corridas = [{"fecha": (LUN(6) + timedelta(days=1)).isoformat(), "minutos": 20, "luz": "verde"},
                {"fecha": dia, "minutos": 48, "luz": "verde"}]
    estado = {e["id"]: e for e in m.assign_sessions(semana, corridas, cfg)}
    assert estado[carrera["id"]]["estado"] == "hecha" and estado[carrera["id"]]["fecha"] == dia
    # una carrera corta (5K en 25 min) también cuenta, aunque la larga del plan fuera de más minutos
    c5 = con_carrera(km=5)
    semana5 = next(w for w in plan_vivo.plan_efectivo(plan, cfg_de(c5))["weeks"] if w["n"] == 6)
    est = {e["id"]: e for e in m.assign_sessions(semana5, [{"fecha": dia, "minutos": 25, "luz": "amarillo"}], cfg_de(c5))}
    assert est[carrera["id"]]["estado"] == "hecha"


def test_data_json_pinta_la_carrera(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        db.get(Ajustes, uid).config = con_carrera()
        db.commit()
    d = cl.get("/data.json").json()
    nombres = [s["name"] for w in d["plan"]["semanas"] for s in w["sessions"]]
    assert "Carrera: 10K de prueba" in nombres


# --- web: agregar y quitar ---

def test_post_carrera_agrega_de_paso_sin_tocar_el_plan(web_ctx):
    uid, cl = listo(web_ctx)
    plan_antes = copy.deepcopy(plan_base())
    r = cl.post("/plan/carrera", data={"csrf": tok(cl), "nombre": "Mi 10K", "fecha": "2026-12-20", "distancia_km": "10"}, follow_redirects=False)
    assert r.status_code == 303
    metas = crudo(web_ctx, uid)["corrida"]["metas"]
    assert len(metas) == 1 and metas[0]["de_paso"] is True and metas[0]["nombre"] == "Mi 10K"
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == plan_antes
        assert db.query(Cambio).order_by(Cambio.id.desc()).first().descripcion == "Agregó la carrera de paso «Mi 10K» el 20/12/2026"
    mid = metas[0]["id"]
    assert cl.post(f"/plan/meta/{mid}/quitar", data={"csrf": tok(cl)}, follow_redirects=False).status_code == 303
    assert crudo(web_ctx, uid)["corrida"].get("metas") == []
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == plan_antes
    # fecha pasada: rechazada
    r = cl.post("/plan/carrera", data={"csrf": tok(cl), "fecha": "2026-01-01"})
    assert r.status_code == 400


def test_el_dialogo_ofrece_las_dos_opciones(web_ctx):
    uid, cl = listo(web_ctx)
    h = cl.get("/plan/acciones").text
    assert "Carrera de paso: sigo con mi plan" in h and "Esa semana la carrera es tu sesión larga. El plan no cambia." in h
    assert "Quiero entrenar para esta carrera" in h and 'method="get" action="/plan/nuevo"' in h and 'name="carrera" value="1"' in h


# --- /plan/nuevo con la carrera puesta ---

def test_plan_nuevo_con_parametros_deja_la_carrera_puesta(web_ctx):
    from test_web_plan_nuevo import lunes_siguiente
    uid, cl = listo(web_ctx)
    fecha = (lunes_siguiente() + timedelta(weeks=12, days=5)).isoformat()
    r = cl.get(f"/plan/nuevo?carrera=1&fecha={fecha}&km=21&nombre=X")
    assert r.status_code == 200 and 'name="carrera" value="1"' in r.text and f'name="fecha" value="{fecha}"' in r.text and 'name="km" value="21"' in r.text
    r = cl.post("/plan/nuevo/preguntas", data={"csrf": tok(cl), "nivel": "base", "frecuencia_actual": "3", "corrida_larga": "40", "carrera": "1", "fecha": fecha, "km": "21"})
    assert r.status_code == 200
    assert f'value="{fecha}"' in r.text and 'value="21" selected' in r.text or 'value="21" checked' in r.text
    assert 'value="carrera" checked' in r.text
    # sin parámetros o con parámetros malos, nada puesto y sin error
    for q in ("", "?carrera=1&fecha=no&km=7", "?carrera=1&fecha=2020-01-01&km=10"):
        r = cl.get("/plan/nuevo" + q)
        assert r.status_code == 200 and 'name="carrera"' not in r.text


# --- MCP ---

def test_mcp_agregar_carrera_es_de_paso(web_ctx):
    uid, _ = listo(web_ctx, "a@x.com")
    t = token_para(web_ctx, uid)
    plan_antes = copy.deepcopy(plan_base())
    with web_ctx.cliente() as cl:
        err, txt = llamar(cl, t, "agregar_carrera", fecha="2027-01-10", nombre="10K", distancia_km=10)
        assert not err, txt
        assert "carrera de paso" in json.loads(txt)["hecho"]
        err, txt = llamar(cl, t, "agregar_carrera", fecha="2020-01-01")
        assert err
        tools = {x["name"]: x for x in cuerpo(rpc(cl, t, "tools/list"))["result"]["tools"]}
        assert "carrera de paso" in tools["agregar_carrera"]["description"]
    meta = crudo(web_ctx, uid)["corrida"]["metas"][-1]
    assert meta["de_paso"] is True and meta["distancia_km"] == 10 and meta["fecha"] == "2027-01-10"
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == plan_antes
