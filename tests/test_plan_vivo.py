"""Plan vivo (metas, eventos, sesiones flexibles, sensor)."""
import copy
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

import build
import planes_v6
import metrics as m
import reloj_plan as rp
import tipos
import validar
from ajustes import ConfigError, normalizar_config
from test_web_ajustes import CONFIG, HOY, crudo, listo, plan_de, tok
from test_web_cuentas import csrf_de
from web import cambios, plan_vivo
from web.modelos import Ajustes, Cambio, Plan, Usuario

ROOT = Path(__file__).parent.parent
HOY_D = date(2026, 11, 25)       # semana 3 del plan que empieza el 2026-11-09
LUNES = lambda n: date(2026, 11, 9) + timedelta(weeks=n - 1)   # noqa: E731  lunes de la semana n (sin repetidas)


def cfg_de(crudo_, hoy=HOY_D):
    return plan_vivo.con_pausas(normalizar_config(crudo_), hoy)


def plan_base(crudo_=CONFIG):
    return planes_v6.generar(normalizar_config(crudo_))


def con(corrida=None, **resto):
    c = copy.deepcopy(CONFIG)
    c["corrida"] = {**c["corrida"], **(corrida or {})}
    return {**c, **resto}


def fecha_semana(n, dia=2):
    return (LUNES(n) + timedelta(days=dia)).isoformat()


# --- identidad: sin metas ni eventos nada cambia ---

def test_sin_metas_ni_eventos_el_plan_es_el_mismo_objeto():
    p, cfg = plan_base(), cfg_de(CONFIG)
    assert cfg["pausas"] == [] and cfg["metas"] == [] and cfg["eventos"] == []
    assert plan_vivo.plan_efectivo(p, cfg) is p
    assert build.eventos_plan(cfg) == {}


def test_data_json_sin_eventos_no_trae_claves_nuevas():
    cfg = cfg_de(CONFIG)
    ahora = datetime(2026, 11, 25, 12, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Merida"))
    datos = {"daily_summaries": [], "sleep": [], "hrv": [], "activities": [], "details": {}, "hr_zones": [], "meta": {},
             "historial": None, "inbody": None}
    d = build.build(datos, plan_base(), cfg, ahora)
    assert "eventos" not in d["plan"] and "avisos" not in d and "evento" not in json.dumps(d["plan"]["semanas"])
    assert d["plan"]["semana_actual"] == 3 and validar.problemas(d) == []


# --- pausas (viaje sin correr, enfermedad) ---

def test_viaje_sin_correr_pausa_la_semana_y_el_plan_se_reanuda_donde_iba():
    c = plan_vivo.agregar_evento(CONFIG, "viaje", fecha_semana(3, 1), fecha_semana(3, 5), correr=False)
    cfg = cfg_de(c)
    assert cfg["pausas"] == [LUNES(3).isoformat()]
    assert [m.semana_del_plan(LUNES(n), cfg) for n in (1, 2, 3, 4, 5)] == [1, 2, None, 3, 4]
    assert m.en_pausa(HOY_D, cfg) and not m.en_pausa(date(2026, 11, 18), cfg)
    assert plan_vivo.plan_efectivo(plan_base(c), cfg)["weeks"] == plan_base()["weeks"]   # el plan no se toca
    assert build.ultima_semana(cfg, plan_base()) == LUNES(13)   # 12 semanas + 1 de pausa


def test_la_tarjeta_de_hoy_dice_que_el_plan_esta_en_pausa():
    c = plan_vivo.agregar_evento(CONFIG, "viaje", fecha_semana(3, 0), fecha_semana(3, 6), correr=False)
    cfg = cfg_de(c)
    ahora = datetime(2026, 11, 25, 12, 0, tzinfo=__import__("zoneinfo").ZoneInfo("America/Merida"))
    datos = {"daily_summaries": [{"calendarDate": "2026-11-24", "heartRate": {"restingValue": 55}}], "sleep": [], "hrv": [],
             "activities": [], "details": {}, "hr_zones": [], "meta": {}, "historial": None, "inbody": None}
    d = build.build(datos, plan_base(), cfg, ahora)
    t = d["hoy"]["tarjeta"]
    assert t["tipo"] == "pausa" and "pausa" in t["texto"] and t["sesion_id"] is None
    assert d["plan"]["semana_actual"] is None and d["plan"]["eventos"][0]["tipo"] == "viaje"
    assert validar.problemas(d) == []
    assert len(d["semanas_hoy"]) == 13   # el calendario incluye la semana de pausa


def test_enfermedad_abierta_pausa_hasta_hoy_y_ya_estoy_bien_la_cierra():
    c = plan_vivo.agregar_evento(CONFIG, "enfermedad", fecha_semana(2, 3), None)
    assert cfg_de(c, HOY_D)["pausas"] == [LUNES(2).isoformat(), LUNES(3).isoformat()]   # abierta: llega hasta hoy
    assert cfg_de(c, date(2026, 11, 17))["pausas"] == [LUNES(2).isoformat()]
    (e,) = normalizar_config(c)["eventos"]
    c2 = plan_vivo.cerrar_evento(c, e["id"], fecha_semana(3, 0))
    assert cfg_de(c2, date(2026, 12, 30))["pausas"] == [LUNES(2).isoformat(), LUNES(3).isoformat()]   # ya no crece
    cfg = cfg_de(c2)
    assert [m.semana_del_plan(LUNES(n), cfg) for n in (1, 2, 3, 4, 5)] == [1, None, None, 2, 3]
    c3 = plan_vivo.quitar_evento(c2, e["id"])
    assert cfg_de(c3)["pausas"] == [] and plan_vivo.quitar_evento is not None
    with pytest.raises(ConfigError):
        plan_vivo.quitar_evento(c3, e["id"])


def test_pausas_y_repetidas_juntas():
    c = con({"semanas_repetidas": [2]})
    c = plan_vivo.agregar_evento(c, "lesion", fecha_semana(4, 0), fecha_semana(4, 6))
    cfg = cfg_de(c)
    assert [m.semana_del_plan(LUNES(n), cfg) for n in range(1, 7)] == [1, 2, 2, None, 3, 4]


def test_evento_invalido():
    with pytest.raises(ConfigError, match="regreso"):
        plan_vivo.agregar_evento(CONFIG, "viaje", "2026-12-01", None)
    with pytest.raises(ConfigError, match="anterior"):
        plan_vivo.agregar_evento(CONFIG, "viaje", "2026-12-05", "2026-12-01")
    with pytest.raises(ConfigError):
        plan_vivo.agregar_evento(CONFIG, "vacaciones", "2026-12-01", "2026-12-05")


# --- viaje con correr / carrera: solo cambian sus semanas ---

def test_viaje_sigo_igual_no_cambia_el_plan_ni_pausa():
    c = plan_vivo.agregar_evento(CONFIG, "viaje", fecha_semana(5, 1), fecha_semana(5, 4), modo="igual")
    cfg, base = cfg_de(c), plan_base()
    p = plan_vivo.plan_efectivo(base, cfg)
    assert cfg["pausas"] == [] and cfg["eventos"][0]["correr"] is False
    assert all(a["kind"] == b["kind"] and a["sessions"] == b["sessions"] for a, b in zip(base["weeks"], p["weeks"]))
    assert p["weeks"][4]["evento"] == "viaje_igual"


def test_config_vieja_con_correr_true_sigue_siendo_menos():
    crudo = {**CONFIG, "corrida": {**(CONFIG.get("corrida") or {}), "eventos": [
        {"id": "x", "tipo": "viaje", "desde": fecha_semana(5, 1), "hasta": fecha_semana(5, 4), "correr": True}]}}
    cfg, base = cfg_de(crudo), plan_base()
    assert cfg["eventos"][0]["modo"] == "menos"
    w = plan_vivo.plan_efectivo(base, cfg)["weeks"][4]
    assert [s["id"] for s in w["sessions"]] == ["z2a", "z2b"]


def semanas_distintas(a, b):
    return [x["n"] for x, y in zip(a["weeks"], b["weeks"]) if x != y]


def test_viaje_con_correr_deja_dos_z2_cortas_solo_esa_semana():
    c = plan_vivo.agregar_evento(CONFIG, "viaje", fecha_semana(5, 1), fecha_semana(5, 4), correr=True)
    cfg, base = cfg_de(c), plan_base()
    p = plan_vivo.plan_efectivo(base, cfg)
    assert semanas_distintas(base, p) == [5] and cfg["pausas"] == []
    w = p["weeks"][4]
    assert w["evento"] == "viaje" and [s["id"] for s in w["sessions"]] == ["z2a", "z2b"] and len({s["minutes"] for s in w["sessions"]}) == 1
    assert w["sessions"][0]["minutes"] == base["weeks"][4]["sessions"][0]["easy"]["minutes"]
    planes_v6.verificar(p)
    assert [x["n"] for x in p["weeks"]] == list(range(1, 13))


def test_carrera_despues_del_plan_solo_se_guarda_y_se_ve():
    c = plan_vivo.agregar_carrera(CONFIG, "2027-03-14", None, "")
    cfg, base = cfg_de(c), plan_base()
    assert plan_vivo.plan_efectivo(base, cfg)["weeks"] == base["weeks"]
    assert build.eventos_plan(cfg)["eventos"] == [{"tipo": "carrera", "desde": "2027-03-14", "hasta": "2027-03-14",
                                                   "nombre": "Carrera", "distancia_km": None}]
    (meta,) = cfg["metas"]
    assert normalizar_config(plan_vivo.quitar_meta(c, meta["id"]))["metas"] == []


def test_metas_invalidas():
    for bad in ({"fecha": "no", "distancia_km": 10}, {"fecha": "2027-01-10", "distancia_km": "mucho"}, {"fecha": "2027-01-10", "distancia_km": 900}):
        with pytest.raises(ConfigError):
            normalizar_config(con({"metas": [{"tipo": "carrera", **bad}]}))


# --- repetir semana ---

def test_repetir_semana_y_deshacer_por_el_historial(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.post("/plan/repetir", data={"csrf": tok(cl)})
    assert r.status_code == 303
    assert crudo(web_ctx, uid)["corrida"]["semanas_repetidas"] == [3]
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
        assert c.descripcion == "Repitió la semana 3"
    d = cl.get("/data.json").json()
    assert d["plan"]["semanas_repetidas"] == [3] and len(d["semanas_hoy"]) == 13
    cl.post(f"/historial/{c.id}/deshacer", data={"csrf": tok(cl)})
    assert crudo(web_ctx, uid) == CONFIG


# --- escalera ---

CAMINATAS = con({"caminatas": True, "nivel": "novato"})


def trotes(p, n):
    """Minutos de trote de la primera sesión con repeticiones de la semana n."""
    w = p["weeks"][n - 1]
    for s in w["sessions"]:
        for st in s["steps"]:
            if st["kind"] == "repeat":
                return st["steps"][0]["minutes"]


# --- sesiones flexibles ---

LARGA_8_1 = [{"kind": "repeat", "times": 6, "steps": [{"kind": "run", "minutes": 8, "zone": "Z2", "note": ""},
                                                       {"kind": "walk", "minutes": 1, "zone": "Z1", "note": ""}]},
             {"kind": "run", "minutes": 10, "zone": "Z2", "note": ""}]


def test_larga_8_1_por_6_mas_10_continuo_pasa_por_todo_el_motor():
    plan = plan_base()
    larga = next(s for s in plan["weeks"][3]["sessions"] if s["id"] == "larga")
    nuevo = plan_vivo.editar_sesion(plan, 4, "larga", copy.deepcopy(LARGA_8_1))
    s = next(x for x in nuevo["weeks"][3]["sessions"] if x["id"] == "larga")
    assert s["minutes"] == 64 and planes_v6.suma(s["steps"]) == 64
    assert nuevo["weeks"][3]["sessions"][0] == plan["weeks"][3]["sessions"][0] and larga["minutes"] != 64
    assert plan["weeks"][3]["sessions"][2] == larga   # el plan original no se tocó
    # build: silueta, rachas, convert_steps
    zonas = [("Z1", 100, 120), ("Z2", 121, 140), ("Z3", 141, 150), ("Z4", 151, 160), ("Z5", 161, 190)]
    cs = build.convert_session(s, zonas)
    assert cs["minutes"] == 64 and sum(x[0] for x in cs["silueta"]) == 64 and sum(r["min"] for r in cs["rachas"]) == 64
    assert cs["steps"][0]["kind"] == "repeat" and cs["steps"][0]["times"] == 6 and cs["forma"] == "trote_caminata"
    assert cs["silueta"][:2] == [[8, "Z2"], [1, "Z1"]] and len(cs["silueta"]) == 13
    # reloj: repetición como grupo de Garmin
    w = rp.entrenamiento(s, 4)
    pasos = w["workoutSegments"][0]["workoutSteps"]
    assert w["estimatedDurationInSecs"] == 64 * 60 and pasos[0]["type"] == "RepeatGroupDTO" and pasos[0]["numberOfIterations"] == 6
    assert [q["stepType"]["stepTypeKey"] for q in pasos[0]["workoutSteps"]] == ["interval", "recovery"] and pasos[1]["endConditionValue"] == 600.0
    assert rp.resumen_pasos(s["steps"]) == "6× (8' Z2 + 1' Z1 caminar) · 10' Z2"


def test_filas_del_formulario_a_pasos_y_de_vuelta():
    filas = [{"tipo": "trote", "min": "8", "zona": "Z2", "grupo": 1, "nota": ""}, {"tipo": "caminata", "min": "1", "zona": "Z1", "grupo": 1},
             {"tipo": "trote", "min": "10", "zona": "Z2", "grupo": 0}]
    pasos = plan_vivo.pasos_de_filas(filas, {1: 6})
    assert pasos == [{"kind": "repeat", "times": 6, "steps": [{"kind": "run", "minutes": 8, "zone": "Z2", "note": ""},
                                                               {"kind": "walk", "minutes": 1, "zone": "Z1", "note": ""}]},
                     {"kind": "run", "minutes": 10, "zone": "Z2", "note": ""}]
    assert plan_vivo.filas_de(pasos)[0][:2] == [{"tipo": "trote", "min": 8, "zona": "Z2", "grupo": 1, "nota": "", "opcional": False},
                                               {"tipo": "caminata", "min": 1, "zona": "Z1", "grupo": 1, "nota": "", "opcional": False}]
    assert plan_vivo.filas_de(pasos)[1] == {1: 6}
    malos = [([{"tipo": "trote", "min": "0", "zona": "Z2"}], {}), ([{"tipo": "trote", "min": "5", "zona": "Z9"}], {}),
             ([{"tipo": "salto", "min": "5", "zona": "Z2"}], {}), ([{"tipo": "trote", "min": "x", "zona": "Z2"}], {}),
             ([{"tipo": "trote", "min": "5", "zona": "Z2", "grupo": 1}], {1: 1}), ([], {}),
             ([{"tipo": "trote", "min": "5", "zona": "Z2", "grupo": 1}, {"tipo": "trote", "min": "5", "zona": "Z2", "grupo": 0},
               {"tipo": "trote", "min": "5", "zona": "Z2", "grupo": 1}], {1: 3})]
    for filas_malas, veces in malos:
        with pytest.raises(ConfigError):
            plan_vivo.pasos_de_filas(filas_malas, veces)


def test_no_se_edita_la_calidad():
    p = plan_base(con({"intensidad": "calidad", "calidad_tipos": ["intervalos"]}))
    n, cal = next((w["n"], x) for w in p["weeks"] for x in w["sessions"] if x["tipo"] == "calidad")
    with pytest.raises(ConfigError, match="no se edita"):
        plan_vivo.editar_sesion(p, n, cal["id"], [{"kind": "run", "minutes": 20, "zone": "Z2", "note": ""}])
    with pytest.raises(ConfigError, match="ya no existe"):
        plan_vivo.editar_sesion(p, 1, "nada", [])


def test_editor_de_sesion_por_la_web(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.get("/plan/sesion/4/larga")
    assert r.status_code == 200 and 'name="min_1"' in r.text and "Larga" in r.text
    datos = {"csrf": tok(cl), "filas": "4",
             "tipo_1": "trote", "min_1": "8", "zona_1": "Z2", "grupo_1": "1",
             "tipo_2": "caminata", "min_2": "1", "zona_2": "Z1", "grupo_2": "1",
             "tipo_3": "trote", "min_3": "10", "zona_3": "Z2", "grupo_3": "0", "min_4": "", "veces_1": "6"}
    r = cl.post("/plan/sesion/4/larga", data=datos)
    assert r.status_code == 303
    p = plan_de(web_ctx, uid)
    s = next(x for x in p["weeks"][3]["sessions"] if x["id"] == "larga")
    assert s["minutes"] == 64 and s["steps"][0]["times"] == 6
    d = cl.get("/data.json").json()
    assert validar.problemas(d) == [] and any(x["minutes"] == 64 for x in d["plan"]["semanas"][3]["sessions"])
    assert "6" in cl.get("/plan/sesion/4/larga").text
    # error: grupo sin repeticiones
    r = cl.post("/plan/sesion/4/larga", data={**datos, "csrf": tok(cl), "veces_1": ""})
    assert r.status_code == 400 and "repetirse" in r.text
    # calidad/prueba o sesión inexistente
    assert cl.get("/plan/sesion/4/nada").status_code == 404
    assert cl.get("/plan/sesion/99/larga").status_code == 404
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
    cl.post(f"/historial/{c.id}/deshacer", data={"csrf": tok(cl)})
    assert plan_de(web_ctx, uid) == plan_base()


# --- sensor ---

def test_sensor_muneca_no_calcula_deriva():
    cfg_banda, cfg_muneca = normalizar_config(CONFIG), normalizar_config(con(perfil={**CONFIG["perfil"], "sensor": "muñeca"}))
    assert cfg_banda["sensor"] == "banda" and cfg_muneca["sensor"] == "muñeca"
    with pytest.raises(ConfigError):
        normalizar_config(con(perfil={**CONFIG["perfil"], "sensor": "dedo"}))
    # corrida de 60' a ritmo parejo con serie de FC: con banda hay deriva, con muñeca no
    serie = [[t, t * 3.0, 140 + t / 360] for t in range(0, 3601, 5)]
    a = {"activityId": 1, "id": "x1", "startTimeLocal": "2026-11-20 07:00:00", "duration": 3600, "distance": 10800,
         "averageHR": 150, "activityType": {"typeKey": "running"}, "name": None,
         "hrTimeInZone_1": 0, "hrTimeInZone_2": 3600, "hrTimeInZone_3": 0, "hrTimeInZone_4": 0, "hrTimeInZone_5": 0}
    det = {"x1": {"serie": serie}}
    cfg = {**cfg_banda, "zonas": [("Z1", 100, 120), ("Z2", 121, 160), ("Z3", 161, 170), ("Z4", 171, 180), ("Z5", 181, 190)]}
    fb = m.run_rows([a], det, cfg)[0]
    fm = m.run_rows([a], det, {**cfg, "sensor": "muñeca"})[0]
    assert fb["deriva_pct"] is not None and fm["deriva_pct"] is None and fm["deriva_ok"] is None


def test_sensor_muneca_en_el_dashboard_dice_por_que(web_ctx):
    uid, cl = listo(web_ctx)
    c = copy.deepcopy(CONFIG)
    c["perfil"]["sensor"] = "muñeca"
    with web_ctx.sesiones() as db:
        db.get(Ajustes, uid).config = c
        db.commit()
    d = cl.get("/data.json").json()
    assert "muñeca" in d["progreso"]["mejora"]["deriva"]["motivo"]


# --- siguiente bloque ---

# --- páginas del plan vivo (formularios) ---

def test_viaje_enfermedad_carrera_por_la_web_con_historial_y_deshacer(web_ctx):
    uid, cl = listo(web_ctx)
    assert "Ajustar mi plan" in cl.get("/plan/acciones").text
    r = cl.post("/plan/viaje", data={"csrf": tok(cl), "desde": "2026-12-01", "hasta": "2026-12-06", "correr": "no"})
    assert r.status_code == 303
    r = cl.post("/plan/viaje", data={"csrf": tok(cl), "desde": "2026-12-10", "hasta": "2026-12-01", "correr": "si"})
    assert r.status_code == 400 and "anterior" in r.text
    assert cl.post("/plan/enfermedad", data={"csrf": tok(cl), "tipo": "lesion", "desde": "2026-11-25"}).status_code == 303
    assert cl.post("/plan/carrera", data={"csrf": tok(cl), "nombre": "10K", "fecha": "2027-01-10", "distancia_km": "10"}).status_code == 303
    assert cl.post("/plan/carrera", data={"csrf": tok(cl), "nombre": "Vieja", "fecha": "2026-01-10"}).status_code == 400
    c = crudo(web_ctx, uid)["corrida"]
    assert sorted(e["tipo"] for e in c["eventos"]) == ["lesion", "viaje"] and c["metas"][0]["nombre"] == "10K"
    d = cl.get("/data.json").json()
    assert validar.problemas(d) == []
    assert {e["tipo"] for e in d["plan"]["eventos"]} == {"viaje", "lesion", "carrera"}
    assert d["hoy"]["tarjeta"]["tipo"] == "pausa"
    html = cl.get("/plan/acciones").text
    assert "Ya estoy bien" in html and "10K" in html
    ev = next(e for e in c["eventos"] if e["tipo"] == "lesion")
    assert cl.post(f"/plan/evento/{ev['id']}/cerrar", data={"csrf": tok(cl)}).status_code == 303
    assert next(e for e in crudo(web_ctx, uid)["corrida"]["eventos"] if e["id"] == ev["id"])["hasta"] == "2026-11-25"
    assert cl.post("/plan/evento/nada/quitar", data={"csrf": tok(cl)}).status_code == 400
    with web_ctx.sesiones() as db:
        descs = [x.descripcion for x in db.query(Cambio).order_by(Cambio.id)]
    assert descs[0].startswith("Agregó un viaje del 01/12/2026 al 06/12/2026") and any("la carrera «10K»" in x for x in descs)
    # deshacer todo, de atrás para adelante
    with web_ctx.sesiones() as db:
        ids = [x.id for x in db.query(Cambio).order_by(Cambio.id.desc())]
    for i in ids:
        cl.post(f"/historial/{i}/deshacer", data={"csrf": tok(cl)})
    assert crudo(web_ctx, uid) == CONFIG
    assert "plan" not in cl.get("/data.json").json()["plan"].get("eventos", {}) and "eventos" not in cl.get("/data.json").json()["plan"]


def test_ajustes_conserva_metas_y_eventos(web_ctx):
    from test_web_ajustes import guardar
    uid, cl = listo(web_ctx)
    cl.post("/plan/carrera", data={"csrf": tok(cl), "nombre": "10K", "fecha": "2027-01-10", "distancia_km": "10"})
    guardar(cl, titulo="Cambié el título")
    assert crudo(web_ctx, uid)["corrida"]["metas"][0]["nombre"] == "10K"


def test_el_coach_agrega_un_viaje_y_el_atleta_se_entera(web_ctx):
    from test_web_ajustes import Coach, entrar
    uid_a, cl_a = listo(web_ctx, "atleta@x.com")
    uid_c, cl_c = listo(web_ctx, "coach@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    r = cl_c.post(f"/a/{uid_a}/plan/viaje", data={"csrf": tok(cl_c), "desde": "2026-12-01", "hasta": "2026-12-06", "correr": "si"})
    assert r.status_code == 303 and r.headers["location"] == f"/a/{uid_a}/plan/acciones?ok=1"
    assert "Modo coach · Viendo a" in cl_c.get(f"/a/{uid_a}/plan/acciones").text
    assert crudo(web_ctx, uid_a)["corrida"]["eventos"][0]["modo"] == "menos"
    d = cl_a.get("/data.json").json()
    assert d["avisos"][0]["texto"].endswith("cambió tus ajustes") and d["avisos"][0]["url"].startswith("/historial#c")
    assert cl_a.get("/plan/acciones").status_code == 200


def test_sin_acceso_otro_no_toca_el_plan(web_ctx):
    uid_a, cl_a = listo(web_ctx, "a@x.com")
    uid_b, cl_b = listo(web_ctx, "b@x.com")
    csrf = tok(cl_b)
    for ruta, datos in (("viaje", {"desde": "2026-12-01", "hasta": "2026-12-05"}), ("enfermedad", {}), ("repetir", {}),
                        ("escalon/subir", {}), ("siguiente-bloque", {}), ("sesion/4/larga", {"filas": "0"})):
        assert cl_b.post(f"/a/{uid_a}/plan/{ruta}", data={"csrf": csrf, **datos}).status_code == 404, ruta
    assert crudo(web_ctx, uid_a) == CONFIG and plan_de(web_ctx, uid_a) == plan_base()
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).count() == 0


# --- /reloj y compatibilidad ---

def test_reloj_plan_con_semana_en_pausa_y_con_repeticiones():
    cfg = cfg_de(plan_vivo.agregar_evento(CONFIG, "viaje", fecha_semana(3, 0), fecha_semana(3, 6), correr=False))
    assert rp.semana_actual(HOY_D, cfg, plan_base()) is None
    assert rp.semana_actual(LUNES(4), cfg, plan_base()) == 3
    assert rp.semana_actual(HOY_D, cfg_de(CONFIG), plan_base()) == 3


def test_el_plan_de_pedro_sin_metas_ni_eventos_queda_identico():
    if not (ROOT / "config.yaml").exists() or not (ROOT / "plan" / "plan.json").exists():
        pytest.skip("no hay archivos personales")
    from ajustes import cargar_config
    cfg = cargar_config(ROOT)
    plan = json.loads((ROOT / "plan" / "plan.json").read_text())
    web = plan_vivo.con_pausas({**cfg, "modo": "web"}, HOY_D)
    assert web["pausas"] == [] and plan_vivo.plan_efectivo(plan, web) is plan


def test_plan_redirige_a_la_pestana_y_el_menu_no_trae_plan_vivo(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.get("/plan")
    assert r.status_code == 303 and r.headers["location"] == "/#plan"
    ui = cl.get("/data.json").json()["ui"]
    assert ui["editar_urls"] and ui["plan_acciones"]
    assert all(a["url"].startswith("/plan/acciones") for a in ui["plan_acciones"])
    assert "Plan vivo" not in [i["texto"] for i in ui["menu"]]
    assert cl.get("/plan/acciones").status_code == 200
    assert cl.post("/plan/repetir", data={"csrf": tok(cl)}).headers["location"] in ("/?ok=plan#plan", "/plan/acciones?ok=1")


def test_ui_del_plan_trae_valores_por_defecto_en_pages():
    from dashboard import ajustes, build, validar
    cfg = ajustes.cargar_config(build.ROOT)
    d = build.build(build.load_data(build.ROOT), build.load_plan(build.ROOT), cfg, __import__("datetime").datetime(2026, 11, 25))
    assert d["ui"]["plan_acciones"] == [] and d["ui"]["editar_urls"] == {}
    d["ui"]["plan_acciones"] = [{"texto": "X", "url": "/plan/acciones"}]
    assert validar.problemas(d) == []


def test_solo_el_modo_menos_vuelve_descarga_la_semana_5_pegada_a_la_4():
    """Semana 4 es descarga natural. «Sigo igual» y «pausa» dejan la 5 en carga (con o sin carrera); «menos» la vuelve ligera."""
    for meta in (None, 9, 10):
        base = CONFIG if meta is None else plan_vivo.agregar_carrera(CONFIG, fecha_semana(meta, 6), 10, "10K")
        tipos_ = {}
        for modo in ("igual", "pausa", "menos"):
            c = plan_vivo.agregar_evento(base, "viaje", fecha_semana(5, 1), fecha_semana(5, 4), modo=modo)
            p = plan_vivo.plan_efectivo(plan_base(), cfg_de(c))
            tipos_[modo] = (p["weeks"][3]["kind"], p["weeks"][4]["kind"])
        assert tipos_["igual"] == ("descarga", "carga") and tipos_["pausa"] == ("descarga", "carga")
        assert tipos_["menos"] == ("descarga", "descarga")


def test_una_meta_ya_no_cambia_semanas_del_plan_v6():
    """Las carreras entran al plan con `motor_v6.con_carrera`; `plan_efectivo` ya no las pinta encima."""
    cfg, base = cfg_de(plan_vivo.agregar_carrera(CONFIG, fecha_semana(6, 5), 10, "10K")), plan_base()
    assert plan_vivo.plan_efectivo(base, cfg) is base


def test_una_segunda_carrera_en_un_plan_con_carrera_da_un_mensaje_claro():
    import motor_v6
    from web.errores import ErrorT
    plan = motor_v6.generar_v6({"nivel": "base", "dias": 3, "inicio": "2026-11-09", "evidencia": planes_v6.EVIDENCIA["base"], "inicio_minutos": 100,
                                "meta": {"tipo": "carrera", "km": 10, "semanas_hasta": 12}})
    assert (plan["meta"].get("carrera") or {}).get("km") == 10
    cfg = cfg_de(CONFIG)
    with pytest.raises(ErrorT, match="otra carrera"):
        plan_vivo.agregar_carrera_en_plan(CONFIG, plan, cfg, fecha_semana(8, 5), 5, "5K", HOY_D)
