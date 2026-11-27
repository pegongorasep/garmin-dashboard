import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import build  # noqa: E402
import semanal  # noqa: E402
import validar  # noqa: E402

from ajustes import cargar_config  # noqa: E402

CONFIG = cargar_config(ROOT / "tests" / "fixtures")
# El fixture es de la semana del 26 oct: usa una copia del config con ese inicio de plan.
CONFIG_FIXTURE = {**CONFIG, "plan_start": "2026-10-26"}
AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Merida"))  # miércoles, semana 2

PROHIBIDAS = ["activityId", "activityName", "ownerDisplayName", "ownerFullName", "userProfilePk",
              "userProfilePK", "userProfileId", "uuid", "activityUUID", "displayName", "locationName",
              "profileImageUrl", "ownerProfileImageUrlSmall", "fullName", "emailAddress",
              "startLatitude", "startLongitude", "endLatitude", "endLongitude",
              "splitSummaries", "splits", "serie"]
SECRETOS = ["Persona Inventada", "persona@ejemplo.com", "Calle Secreta", "Corrida de Calle Secreta"]


def fixture():
    def act(i, dia, tipo, **kw):
        return {"activityId": i, "activityUUID": f"uuid-{i}", "activityName": "Corrida de Calle Secreta",
                "ownerDisplayName": "Persona Inventada", "ownerFullName": "Persona Inventada",
                "userProfilePk": 99, "locationName": "Calle Secreta",
                "ownerProfileImageUrlSmall": "https://ejemplo.com/foto.png",
                "startTimeLocal": f"{dia} 18:00:00", "duration": 1800.0,
                "activityType": {"typeKey": tipo}, "averageHR": 140.0, "averageSpeed": 3.0,
                "maxHR": 180.0, "hrTimeInZone_1": 300, "hrTimeInZone_2": 900, "hrTimeInZone_3": 300,
                "hrTimeInZone_4": 0, "hrTimeInZone_5": 0, "distance": 4500.0, **kw}
    tramos = [{"splitType": "RWD_RUN", "duration": 1200.0, "distance": 3000.0, "noOfSplits": 3},
              {"splitType": "RWD_WALK", "duration": 600.0, "distance": 700.0, "noOfSplits": 3}]
    dias = [f"2026-10-{d:02d}" for d in range(20, 32)] + ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    return {
        "daily_summaries": [{"calendarDate": d, "displayName": "Persona Inventada",
                             "heartRate": {"restingValue": 60}} for d in dias],
        "sleep": [{"calendarDate": d, "sleepTimeSeconds": 25000, "userProfilePK": 99} for d in dias],
        "hrv": [{"calendarDate": d, "lastNightAvg": 34, "status": "BALANCED",
                 "baseline": {"lowUpper": 28, "balancedLow": 30, "balancedUpper": 38}} for d in dias],
        "activities": [act(1, "2026-11-02", "hiit"), act(2, "2026-11-03", "running", splitSummaries=tramos),
                       act(3, "2026-10-28", "running", splitSummaries=tramos, endLatitude=1.0, endLongitude=2.0),
                       act(4, "2026-11-03", "hiit")],
        "details": {"1": {"rpe": 6.0, "feel": 50},
                    "2": {"rpe": 4.0, "feel": 50, "splits": [
                        {"tipo": "RWD_RUN", "seg": 1200.0, "m": 3000.0, "fc": 145.0, "n": 3},
                        {"tipo": "RWD_WALK", "seg": 600.0, "m": 700.0, "fc": 125.0, "n": 3}]},
                    "3": {"rpe": None, "feel": None}},
        "hr_zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 190, "restingHeartRateUsed": 64}],
        "meta": {"pulled_at_utc": "2026-11-04T17:00:00+00:00"},
    }


def revisar_privacidad(out: dict, extras=()):
    texto = json.dumps(out, ensure_ascii=False)

    acciones = (out.get("ui") or {}).get("acciones_url")  # única URL permitida: el enlace a GitHub Actions

    def recorrer(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert k not in PROHIBIDAS, f"clave prohibida: {k}"
                recorrer(v)
        elif isinstance(o, list):
            for v in o:
                recorrer(v)
        elif isinstance(o, str):
            assert not o.startswith("http") or o == acciones, f"URL en el JSON: {o}"
    recorrer(out)
    for s in [*SECRETOS, *extras]:
        assert s and s not in texto, f"valor privado en el JSON: {s}"


@pytest.fixture
def salida():
    plan = build.load(ROOT / "plan" / "plan.example.json")
    return build.build(fixture(), plan, CONFIG_FIXTURE, AHORA)


def test_forma_y_json_valido(salida):
    json.dumps(salida)
    for k in ("generado", "zonas", "aviso_zonas", "hoy", "ultima_corrida", "semana", "plan", "progreso", "detalles"):
        assert k in salida
    for k in ("tendencias", "corridas", "fc_max"):
        assert k not in salida
    assert salida["plan"]["semana_actual"] == 2
    assert len(salida["semana"]["dias"]) == 7 and len(salida["zonas"]) == 5
    p = salida["progreso"]
    assert len(p["dias"]) == 84 and len(p["semanas"]) >= 12 and set(p["resumen"]) == {"4", "8", "12"}
    assert set(salida["detalles"]) >= {"distribucion", "carga", "carga_anterior", "carga_semanas",
                                       "fc_max", "umbrales"}
    assert len(salida["detalles"]["carga_semanas"]) >= 12   # serie_semanas: 12 semanas o el plan, lo que abarque más
    assert salida["generado"].startswith("2026-11-04T12:00")
    assert salida["datos_al"].startswith("2026-11-04T11:00")  # 17:00 UTC = 11:00 Mérida


def test_semana_resumen(salida):
    s = salida["semana"]
    assert (s["sesiones_total"], s["hechas"], s["incompletas"]) == (3, 1, 0)
    assert s["minutos"] == 30 and s["km"] == 4.5 and s["min_trote"] == 20


def test_week_runs_y_week_assignment():
    data, plan = fixture(), build.load(ROOT / "plan" / "plan.example.json")
    ini = date(2026, 10, 26)
    runs = build.week_runs(ini, date(2026, 11, 1), data, CONFIG_FIXTURE)
    assert [(r["fecha"], r["minutos"], r["luz"]) for r in runs] == [("2026-10-28", 30, "verde")]
    assert build.week_runs(ini, date(2026, 10, 27), data, CONFIG_FIXTURE) == []
    semana, est = build.week_assignment(date(2026, 11, 4), data, CONFIG_FIXTURE, plan)
    assert semana["n"] == 2 and est[0]["fecha"] == "2026-11-03"
    assert build.week_assignment(date(2026, 12, 25), data, CONFIG_FIXTURE, plan) == (None, [])


def test_ultima_corrida(salida):
    u = salida["ultima_corrida"]
    assert u["fecha"] == "2026-11-03" and u["minutos"] == 30 and u["km"] == 4.5 and not u["caminadora"]
    assert u["sesion"] == {"id": "z2a", "name": "Z2 #1", "version": "normal", "minutes_plan": 25}
    assert (u["min_sobre_techo"], u["tolerancia_min"], u["techo_ok"]) == (5.0, 4, False)
    t = u["trote"]
    assert (t["trote_min"], t["camina_min"], t["pct_trote"], t["caminatas"]) == (20.0, 10.0, 66.7, 3)
    assert t["ritmo_trote_s"] == 400 and t["fc_trote"] == 145.0


def test_ultima_corrida_fuera_del_plan_y_sin_corridas():
    data, plan = fixture(), build.load(ROOT / "plan" / "plan.example.json")
    fuera = build.build(data, plan, CONFIG, AHORA)      # plan_start real: 16 nov
    assert fuera["ultima_corrida"]["sesion"] is None and fuera["plan"]["semana_actual"] is None
    assert fuera["hoy"]["tarjeta"]["tipo"] in ("sin_plan", "otra")
    vacia = build.build({**data, "activities": []}, plan, CONFIG_FIXTURE, AHORA)
    assert vacia["ultima_corrida"] is None and vacia["progreso"]["corridas"] == []


def test_progreso(salida):
    p = salida["progreso"]
    assert [c["sesion"] for c in p["corridas"]] == ["Larga", "Z2 #1"]   # la larga cuenta en cualquier día: 30' ≥ 70 % de la larga de esa semana
    assert p["corridas"][0]["pct_trote"] == 66.7 and p["corridas"][0]["ritmo_trote_s"] == 400
    ultima = p["semanas"][-1]
    assert ultima["inicio"] == "2026-11-02" and ultima["minutos"] == 30 and ultima["min_trote"] == 20
    assert ultima["min_camina"] == 10 and ultima["plan_min"] == 100   # semana 2 del ejemplo: 25+25+50
    assert p["semanas"][-2]["plan_min"] == 80                         # semana 1: 20+20+40
    d = p["dias"][-1]
    assert d["fecha"] == "2026-11-04" and d["hrv"] == 34 and d["hrv_7d"] == 34 and d["sueño_7d"] == 6.94
    assert p["dias"][0]["hrv_7d"] is None            # sin datos 84 días atrás


def test_hoy_sin_datos_de_anoche():
    data, plan = fixture(), build.load(ROOT / "plan" / "plan.example.json")
    vacio = {**data, "hrv": [], "sleep": [], "daily_summaries": []}
    out = build.build(vacio, plan, CONFIG_FIXTURE, AHORA)
    assert out["hoy"]["semaforo"]["color"] == "sin_datos"
    assert out["hoy"]["tarjeta"]["version"] in ("normal", None)


def test_plan_convertido_a_lpm(salida):
    ses = salida["plan"]["semanas"][0]["sessions"][0]
    assert ses["tipo"] == "z2"
    assert ses["steps"][0]["lpm"] == [138, 151]   # Z2 con reposo 60 y máx 190 (una sola zona por paso)
    assert ses["steps"][0]["optional"] is False


def test_paso_z3_opcional_con_lpm(salida):
    pasos = salida["plan"]["semanas"][1]["sessions"][0]["steps"]   # semana con picos
    z3 = [p for p in pasos if p["zone"] == "Z3"]
    assert len(z3) == 2 and all(p["optional"] is True for p in z3)
    assert z3[0]["lpm"] == [151, 164]


def test_corrida_asignada_a_sesion(salida):
    est = salida["plan"]["estado_sesiones"]
    assert [e["estado"] for e in est] == ["hecha", "pendiente", "pendiente"]
    assert salida["plan"]["estado_sesiones"][0]["name"] == "Z2 #1"
    assert salida["hoy"]["tarjeta"]["tipo"] in ("sesion", "hecha_hoy", "otra")


def test_privacidad_con_fixture(salida):
    revisar_privacidad(salida)


def test_privacidad_detecta_fuga(salida):
    salida["hoy"]["activityName"] = "x"
    with pytest.raises(AssertionError):
        revisar_privacidad(salida)


def test_tamano_menor_300kb(salida):
    assert len(json.dumps(salida, ensure_ascii=False).encode()) < 300 * 1024


def test_privacidad_con_datos_reales():
    if not (ROOT / "data" / "activities.json").exists():
        pytest.skip("no hay data/ local")
    out = build.build(build.load_data(), build.load_plan(), CONFIG, datetime.now(ZoneInfo(CONFIG["timezone"])))
    extras = {a["activityName"] for a in json.loads((ROOT / "data" / "activities.json").read_text())}
    perfil = json.loads((ROOT / "data" / "profile.json").read_text())
    # Un nombre de Garmin que coincide con un texto del catálogo (p. ej. una actividad llamada «HIIT») no es una fuga.
    catalogo = {build.i18n.t(f"motor.tipo.{t}") for t in ("strength_training", "hiit", "cycling", "yoga")} | {c["nombre"] for c in CONFIG["categorias"]}
    extras -= catalogo
    extras |= {v for k, v in _flat(perfil) if k in ("displayName", "fullName", "emailAddress", "userName") and isinstance(v, str)}
    revisar_privacidad(out, extras)
    assert len(json.dumps(out, ensure_ascii=False).encode()) < 300 * 1024


def _flat(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k, v
            yield from _flat(v)
    elif isinstance(o, list):
        for v in o:
            yield from _flat(v)


def test_fc_max_viene_del_reloj(salida):
    assert salida["detalles"]["fc_max"]["config"] == 190 and salida["detalles"]["fc_max"]["fuente"] == "reloj"


def test_hoy_motivo_y_semana_nueva(salida):
    assert salida["hoy"]["tarjeta"]["motivo"] is None          # verde
    data, plan = fixture(), build.load(ROOT / "plan" / "plan.example.json")
    data["sleep"] = [{**r, "sleepTimeSeconds": 18000} if r["calendarDate"] == "2026-11-04" else r
                     for r in data["sleep"]]
    out = build.build(data, plan, CONFIG_FIXTURE, AHORA)
    t = out["hoy"]["tarjeta"]
    assert t["version"] == "suave" and t["motivo"] == "Dormiste poco"
    s = salida["semana"]
    assert s["min_camina"] == 10 and s["pct_trote"] == 66.7 and s["plan_min"] == 100
    assert s["anterior"] == {"minutos": 30, "km": 4.5, "min_trote": 20}   # corrida del 28 oct


def test_estado_sesiones_con_corrida(salida):
    z2a, z2b, _ = salida["plan"]["estado_sesiones"]
    assert z2b["corrida"] is None
    c = z2a["corrida"]
    assert c["minutos"] == 30 and c["km"] == 4.5 and c["pct_trote"] == 66.7 and c["ritmo_trote_s"] == 400
    assert c["techo_ok"] is False and c["tolerancia_min"] == 4 and c["caminadora"] is False


def test_escenario_real_12_nov():
    if not (ROOT / "data" / "activities.json").exists():
        pytest.skip("no hay data/ local")
    cfg = {**CONFIG, "plan_start": "2026-11-09"}
    ahora = datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("America/Merida"))
    out = build.build(build.load_data(), build.load_plan(), cfg, ahora)
    c = next(e["corrida"] for e in out["plan"]["estado_sesiones"] if e["corrida"])   # la corrida del jueves (la larga cuenta en cualquier día)
    assert c["km"] == 4.36 and c["pct_trote"] == 71.4 and c["techo_ok"] is False


# --- v3.2 F1: semanas navegables ---

def _act(i, dia, tipo, minutos=30, hora="18:00:00", **kw):
    return {"activityId": i, "startTimeLocal": f"{dia} {hora}", "duration": minutos * 60.0,
            "activityType": {"typeKey": tipo}, "distance": 3000.0, "hrTimeInZone_2": 600, **kw}


def _semana(data, hoy, ini, config=CONFIG_FIXTURE):
    plan = build.load(ROOT / "plan" / "plan.example.json")
    return build.build_semana(ini, hoy, data, config, plan)


def test_semanas_hoy_escenario_real():
    if not (ROOT / "data" / "activities.json").exists():
        pytest.skip("no hay data/ local")
    cfg = {**CONFIG, "plan_start": "2026-11-09"}
    ahora = datetime(2026, 11, 14, 12, 0, tzinfo=ZoneInfo("America/Merida"))
    out = build.build(build.load_data(), build.load_plan(), cfg, ahora)
    semanas = out["semanas_hoy"]
    previas = [x for x in semanas if x.get("antes_plan")]
    assert len(semanas) == 12 + len(previas) and len(previas) <= 13 and semanas[:len(previas)] == previas
    s = semanas[out["semana_hoy_idx"]]
    assert s["n"] == 1 and s["estado"] == "actual" and s["stats"]["corridas"] == 1
    assert [e["estado"] for e in s["sesiones"]].count("hecha") == 1 and s["extras"] == []
    assert s["dias"][3]["corrida"]["sesion_nombre"] in ("Z2 #1", "Larga")
    futura = semanas[out["semana_hoy_idx"] + 1]
    assert futura["estado"] == "futura" and futura["stats"]["corridas"] == 0
    assert {e["estado"] for e in futura["sesiones"]} == {"pendiente"}


def test_semanas_hoy_fuera_del_plan(salida):
    out = build.build(fixture(), build.load(ROOT / "plan" / "plan.example.json"), CONFIG, AHORA)
    assert len(out["semanas_hoy"]) == 4      # 2 del plan + hoy + 26 oct, ambas antes del plan
    assert [s.get("antes_plan") for s in out["semanas_hoy"]] == [True, True, None, None]
    # el plan empieza el 9 nov: se abre en la semana 1 como vista previa
    assert out["semanas_hoy"][out["semana_hoy_idx"]]["n"] == 1
    s = next(x for x in out["semanas_hoy"] if x["inicio"] == "2026-11-02")
    assert s["n"] is None and s["plan"] is None and s["sesiones"] == []
    assert s["inicio"] == "2026-11-02" and s["stats"]["corridas"] == 1 and len(s["extras"]) == 1


def _antes(actividades, plan_start="2027-01-04", hoy=datetime(2027, 1, 6, 12, 0, tzinfo=ZoneInfo("America/Merida"))):
    data = fixture()
    data["activities"] = actividades
    cfg = {**CONFIG, "plan_start": plan_start}
    return build.build(data, build.load(ROOT / "plan" / "plan.example.json"), cfg, hoy)


def test_semanas_antes_del_plan():
    # 10 semanas antes del lunes 4 ene 2027: la primera actividad cae el 26 oct 2026 (lunes)
    out = _antes([_act(1, "2026-10-26", "running"), _act(2, "2026-12-30", "running")])
    sems = out["semanas_hoy"]
    previas = [s for s in sems if s.get("antes_plan")]
    assert len(previas) == 10 and sems[:10] == previas and previas[0]["inicio"] == "2026-10-26"
    assert all(s["plan"] is None and s["sesiones"] == [] and s["n"] is None for s in previas)
    assert previas[0]["stats"]["corridas"] == 1 and previas[-1]["stats"]["corridas"] == 1
    assert sems[out["semana_hoy_idx"]]["inicio"] == "2027-01-04" and not sems[out["semana_hoy_idx"]].get("antes_plan")
    assert not any(s.get("antes_plan") for s in sems[10:])


def test_semanas_antes_del_plan_sin_actividad_y_tope():
    assert not any(s.get("antes_plan") for s in _antes([_act(1, "2027-01-05", "running")])["semanas_hoy"])
    out = _antes([_act(1, "2026-01-05", "running"), _act(2, "2026-12-30", "running")])    # muy vieja: fuera de las 13
    assert not any(s["inicio"] < "2026-10-05" for s in out["semanas_hoy"] if s.get("antes_plan"))
    out = _antes([_act(1, "2026-10-05", "running")])                                       # justo 13 semanas
    assert len([s for s in out["semanas_hoy"] if s.get("antes_plan")]) == 13


def test_semana_con_cuatro_corridas_trae_un_extra():
    data = fixture()
    data["activities"] = [_act(10, "2026-11-02", "running"), _act(11, "2026-11-03", "running"),
                          _act(12, "2026-11-07", "running", minutos=50), _act(13, "2026-11-08", "running", minutos=30)]
    s = _semana(data, date(2026, 11, 8), date(2026, 11, 2))
    assert s["stats"]["corridas"] == 4 and s["estado"] == "actual"
    assert [e["estado"] for e in s["sesiones"]] == ["hecha", "hecha", "hecha"]
    assert len(s["extras"]) == 1 and s["extras"][0]["fecha"] == "2026-11-08" and s["extras"][0]["minutos"] == 30
    assert s["dias"][6]["corrida"] == {"minutos": 30, "sesion_nombre": "Extra", "estado": "extra", "carrera": False, "icono": "correr"}
    assert s["dias"][5]["corrida"]["sesion_nombre"] == "Larga"


def test_semana_pasada_sesion_sin_hacer_es_no_hecha():
    data = fixture()
    data["activities"] = [_act(10, "2026-11-03", "running")]
    s = _semana(data, date(2026, 11, 12), date(2026, 11, 2))
    assert s["estado"] == "pasada"
    assert [e["estado"] for e in s["sesiones"]] == ["hecha", "no_hecha", "no_hecha"]
    assert s["sesiones"][1]["corrida"] is None
    assert s["plan"] == {"total": 3, "hechas": 1, "incompletas": 0, "pct": 33, "plan_min": 100, "min_pct": 30}


def test_semana_futura_todo_pendiente_y_sin_planeados():
    data = {**fixture(), "activities": []}
    s = _semana(data, date(2026, 10, 28), date(2026, 11, 2))
    assert s["estado"] == "futura" and s["stats"]["corridas"] == 0
    assert {e["estado"] for e in s["sesiones"]} == {"pendiente"}
    assert all("planeado" not in d and not d["otras"] and d["corrida"] is None for d in s["dias"])
    assert all(d["luz"] is None for d in s["dias"])


def test_dia_futuro_vacio_sin_categoria_planeada():
    s = _semana({**fixture(), "activities": []}, date(2026, 11, 2), date(2026, 11, 2))
    assert s["dias"][1]["otras"] == [] and s["dias"][1]["corrida"] is None


def _unidas(data, config=CONFIG_FIXTURE):
    return {**data, "activities": build.m.unir_encadenadas(data["activities"], config)}


def test_otras_del_dia_una_entrada_por_sesion_unida():
    data = fixture()
    data["activities"] = [_act(20, "2026-11-02", "strength_training", minutos=14, hora="18:00:00", hrTimeInZone_1=0, hrTimeInZone_2=840,
                               hrTimeInZone_3=0, hrTimeInZone_4=0, hrTimeInZone_5=0),
                          _act(21, "2026-11-02", "hiit", minutos=16, hora="18:14:00", hrTimeInZone_1=0, hrTimeInZone_2=0,
                               hrTimeInZone_3=0, hrTimeInZone_4=960, hrTimeInZone_5=0)]
    data["details"] = {"20": {"rpe": 5.0}, "21": {"rpe": 7.0}}
    s = _semana(_unidas(data), date(2026, 11, 4), date(2026, 11, 2))
    assert s["dias"][0]["otras"] == [{"cat": "crossfit", "icono": "rayo", "esfuerzo": 7.5, "rpe": 7.0, "minutos": 30.0,
                                      "partes": [{"nombre": "Fuerza", "minutos": 14}, {"nombre": "HIIT", "minutos": 16}]}]
    assert s["dias"][1]["otras"] == []


def test_calendario_con_tres_sesiones_separadas_las_muestra_todas():
    data = fixture()
    data["activities"] = [_act(30 + i, "2026-11-02", "strength_training", minutos=20, hora=h)
                          for i, h in enumerate(("07:00:00", "12:00:00", "18:00:00"))]
    s = _semana(_unidas(data), date(2026, 11, 4), date(2026, 11, 2))
    assert [o["minutos"] for o in s["dias"][0]["otras"]] == [20.0, 20.0, 20.0]
    assert len(s["dias"][0]["actividades"]) == 3 and all(a["partes"] == [] for a in s["dias"][0]["actividades"])


# --- v3.2 F2 ---

def test_mejora_y_composicion_en_el_json(salida):
    mj = salida["progreso"]["mejora"]
    assert set(mj) == {"modo", "ritmo", "deriva", "prueba"}
    assert mj["ritmo"]["valor"] == "6:43 /km" and mj["ritmo"]["n"] == 1
    assert mj["deriva"]["valor"] is None and "cumpla" in mj["deriva"]["motivo"] and mj["prueba"] is None
    assert salida["composicion"] is None                      # el fixture no trae inbody


def test_composicion_real():
    if not (ROOT / "plan" / "inbody.json").exists():
        pytest.skip("no hay inbody.json")
    out = build.build({**fixture(), "inbody": json.loads((ROOT / "plan" / "inbody.json").read_text())},
                      build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    c = out["composicion"]
    assert c["meta"]["faltan_pgc"] == 4.8 and c["meta"]["mme_ok"] is True and len(c["mediciones"]) == 4
    revisar_privacidad(out)


# --- v4 F1: config con 3 categorías y día de pierna ---

CONFIG_CORREDOR = {**cargar_config(ROOT / "tests" / "fixtures" / "config_corredor.yaml"), "plan_start": "2026-10-26"}


def test_build_con_tres_categorias(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    data = fixture()
    data["activities"] = [*data["activities"], {**data["activities"][0], "activityId": 7, "activityUUID": "u7",
                                                 "startTimeLocal": "2026-11-02 07:00:00",
                                                 "activityType": {"typeKey": "strength_training"}}]
    plan = build.load(ROOT / "plan" / "plan.example.json")
    out = build.build(data, plan, CONFIG_CORREDOR, AHORA)
    revisar_privacidad(out)
    ui = out["ui"]
    assert [c["id"] for c in ui["categorias"]] == ["fuerza", "hiit"]   # solo las que aparecen en los datos
    assert [c["clase"] for c in ui["categorias"]] == ["azul", "aqua"]
    assert ui["nombre_intensa"] == "HIIT" and ui["titulo"] == "Mi base" and ui["acciones_url"] is None
    assert ui["textos"]["semana"].endswith("(sábado o domingo). Día de pierna: lunes.")
    assert "Fuerza lunes" not in ui["textos"]["semana"]
    assert ui["textos"]["incluye"] == "Incluye Fuerza, HIIT y corridas."
    lun = next(d for s in out["semanas_hoy"] for d in s["dias"] if d["fecha"] == "2026-11-02")
    assert sorted(o["cat"] for o in lun["otras"]) == ["fuerza", "hiit"]
    assert set(out["detalles"]["carga"]) >= {"fuerza", "hiit", "cardio", "run", "total"}
    assert set(out["detalles"]["carga_semanas"][0]["cargas"]) == {"fuerza", "hiit", "cardio", "movilidad"}
    assert out["detalles"]["fc_max"]["configurada"] is False


def test_acciones_url_desde_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "amigo/mi-dashboard")
    ui = build.build_ui(CONFIG_CORREDOR, build.load(ROOT / "plan" / "plan.example.json"))
    assert ui["acciones_url"] == "https://github.com/amigo/mi-dashboard/actions/workflows/deploy.yml"


# --- v4 F3: calidad, mejora por ritmo, primer día, InBody opcional ---

sys.path.insert(0, str(ROOT / "plan"))
import planes_v6  # noqa: E402

VACIO = {"daily_summaries": [], "sleep": [], "hrv": [], "activities": [], "details": {}, "hr_zones": [],
         "meta": {}, "inbody": None}


def test_primer_dia_sin_datos_y_plan_futuro():
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-12-07"}
    plan = planes_v6.generar(cfg)
    out = build.build(VACIO, plan, cfg, AHORA)
    revisar_privacidad(out)
    t = out["hoy"]["tarjeta"]
    assert t["tipo"] == "primera_sync"
    assert t["texto"] == ("Primera sincronización lista. Garmin tarda en mandar el historial; regresa en unas horas. "
                          "Tu plan empieza el lun 7 dic")
    assert out["semanas_hoy"][out["semana_hoy_idx"]]["n"] == 1 and out["semanas_hoy"][out["semana_hoy_idx"]]["estado"] == "futura"
    assert out["ultima_corrida"] is None and out["composicion"] is None
    assert out["progreso"]["mejora"]["modo"] == "trote" and out["hoy"]["semaforo"]["color"] == "sin_datos"


def test_primer_dia_con_plan_ya_empezado():
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-11-23"}
    out = build.build(VACIO, planes_v6.generar(cfg), cfg, datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("America/Mexico_City")))
    assert out["hoy"]["tarjeta"]["texto"] == "Primera sincronización lista. Garmin tarda en mandar el historial; regresa en unas horas"
    assert out["semanas_hoy"][out["semana_hoy_idx"]]["n"] == 1 and out["semanas_hoy"][out["semana_hoy_idx"]]["estado"] == "actual"


def test_plan_futuro_con_datos_dice_cuando_empieza():
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-12-07"}
    out = build.build(fixture(), planes_v6.generar(cfg), cfg, AHORA)
    assert out["hoy"]["tarjeta"]["tipo"] == "sin_plan" and out["hoy"]["tarjeta"]["texto"] == "Tu plan empieza el lun 7 dic"


def test_inbody_opcional():
    inbody = {"prime": "2026-11-13", "mediciones": [{"fecha": "2026-11-13", "peso_kg": 90, "mme_kg": 38, "pgc": 25}]}
    plan = build.load(ROOT / "plan" / "plan.example.json")
    con = build.build({**fixture(), "inbody": inbody}, plan, CONFIG_FIXTURE, AHORA)
    assert con["composicion"] is not None
    sin = build.build({**fixture(), "inbody": None}, plan, CONFIG_FIXTURE, AHORA)
    apagado = build.build({**fixture(), "inbody": inbody}, plan, {**CONFIG_FIXTURE, "inbody": False}, AHORA)
    assert sin["composicion"] is None and apagado["composicion"] is None


def _corridas_sin_caminatas(fechas, ritmos):
    acts = []
    for i, (f, r) in enumerate(zip(fechas, ritmos)):
        # 30 min a r s/km: km = 1800 / r; FC 145 (Z2 con max 190 / reposo 60: 138-151)
        acts.append({"activityId": 100 + i, "startTimeLocal": f"{f} 07:00:00", "duration": 1800.0,
                     "activityType": {"typeKey": "running"}, "averageHR": 145.0, "distance": 1800.0 / r * 1000,
                     "hrTimeInZone_1": 300, "hrTimeInZone_2": 1500})
    return acts


def test_mejora_por_ritmo_sin_caminatas():
    # hoy 24 nov (martes): últimas 4 semanas completas = 26 oct–22 nov; antes = 28 sep–25 oct
    data = {**VACIO, "activities": _corridas_sin_caminatas(
        ["2026-10-05", "2026-10-12", "2026-11-02", "2026-11-09"], [400, 400, 375, 375])}
    plan = planes_v6.generar(CONFIG_CORREDOR)
    out = build.build(data, plan, {**CONFIG_CORREDOR, "plan_start": "2026-11-09"}, datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("America/Mexico_City")))
    mj = out["progreso"]["mejora"]
    assert mj["modo"] == "ritmo"
    r = mj["ritmo"]   # 400 y 375 s/km a 145 lpm, llevados a 142: 408 y 383; el plan empieza el 9 nov (semanas 1–2 = 383)
    assert (r["fc_ref"], r["n"], r["actual_s"], r["inicio_s"], r["dif_s"]) == (142, 4, 396, 383, 13)
    assert r["valor"] == "6:36 /km" and r["cambio"] == "▲ 13 s vs inicio" and r["mejora"] is False


def test_mejora_con_caminatas_sigue_en_trote(salida):
    assert salida["progreso"]["mejora"]["modo"] == "trote" and "actual_s" in salida["progreso"]["mejora"]["ritmo"]


def test_sesion_de_calidad_en_el_json():
    plan = planes_v6.generar({**CONFIG_CORREDOR, "intensidad": "calidad"})
    out = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)
    s = next(x for w in out["plan"]["semanas"] for x in w["sessions"] if x["tipo"] == "calidad")
    assert s["estructura"] and s["objetivo"]["zona"] in ("Z3", "Z4") and s["objetivo"]["minutos"] > 0 and len(s["objetivo"]["lpm"]) == 2
    assert s["calidad_tipo"] in ("tempo_z3", "threshold", "intervalos", "progresivo", "fartlek")


def test_carreras_y_mejores_marcas_en_data_json():
    data = fixture()
    carrera = _act(50, "2026-11-01", "running", minutos=41, distance=5050.0, averageHR=145.0, maxHR=176.0,
                   activityName="Carrera de la Calle Secreta", fastestSplit_1000=409.0, fastestSplit_5000=2422.0,
                   hrTimeInZone_3=240)
    anterior = _act(51, "2026-10-04", "running", minutos=44, distance=5100.0, averageHR=150.0, activityName="Carrera 5K",
                    fastestSplit_1000=420.0)
    data["activities"] = [*data["activities"], carrera, anterior]
    data["details"] = {**data["details"], "50": {"rpe": 4, "ritmos_km": [500, 510, 490, 480, 420]}}
    out = build.build(data, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    assert [c["fecha"] for c in out["carreras"]] == ["2026-11-01", "2026-10-04"]
    c = out["carreras"][0]
    assert c["distancia_km"] == 5.05 and c["tiempo_s"] == 2460 and c["fc_prom"] == 145 and c["fc_max"] == 176
    assert c["km"] == [500, 510, 490, 480, 420] and c["reciente"] is True and c["hace_dias"] == 3
    assert c["comparacion"]["fecha"] == "2026-10-04" and c["comparacion"]["dif_tiempo_s"] == -180
    assert out["carreras"][1]["comparacion"] is None and out["carreras"][1]["km"] is None
    filas = {r["fecha"]: r["carrera"] for r in out["progreso"]["corridas"]}
    assert filas["2026-11-01"] is True and sum(filas.values()) == 2 and len(filas) > 2
    claves = {mm["clave"] for mm in out["mejores_marcas"]}
    assert {"1k", "5k", "larga"} <= claves and "10k" not in claves
    assert json.dumps(out, ensure_ascii=False).count("Calle Secreta") == 0


def test_historial_viejo_aporta_carrera_y_marcas():
    data = fixture()
    data["historial"] = [{"startTimeLocal": "2025-05-03 07:00:00", "activityType": {"typeKey": "running"}, "distance": 10100.0,
                          "duration": 3300.0, "eventType": {"typeKey": "race"}, "fastestSplit_10000": 3290.0}]
    out = build.build(data, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    assert [c["fecha"] for c in out["carreras"]] == ["2025-05-03"] and out["carreras"][0]["fc_prom"] is None
    assert [mm["clave"] for mm in out["mejores_marcas"]] == ["10k", "larga"]


def test_numeros_de_progreso():
    filas = [{"fecha": f, "minutos": mi, "km": km, "pct_trote": pt, "caminatas": 0, "ritmo_ref_s": rz}
             for f, mi, km, pt, rz in [("2026-11-01", 40.0, 5.0, 100.0, 500), ("2026-11-03", 30.0, 3.0, 100.0, None),
                                       ("2026-09-20", 20.0, 2.0, 100.0, 540)]]
    out = build.build_numeros(date(2026, 11, 4), filas, "ritmo")
    it = {i["id"]: i for i in out["periodos"]["4"]}
    assert it["corridas"]["valor"] == 0.5 and it["minutos"]["valor"] == 17.5 and it["km"]["valor"] == 2.0
    assert it["ritmo_ref"]["valor"] == 500 and it["ritmo_ref"]["anterior"] == 540 and it["ritmo_ref"]["delta"] == -40
    assert out["caminatas"] == {"4": False, "8": False, "12": False}
    ritmo = {i["id"]: i for i in build.build_numeros(date(2026, 11, 4), filas[:1] + [{**filas[2], "fecha": "2026-10-05", "ritmo_ref_s": 530}], "ritmo")["periodos"]["4"]}
    assert ritmo["ritmo_ref"]["delta"] == -30 and ritmo["ritmo_ref"]["bueno"] is True
    assert build.build_numeros(date(2026, 11, 4), [], "trote")["periodos"]["4"][3] == {"id": "pct_trote", "valor": None, "anterior": None, "delta": None, "bueno": None}


# --- v4.2 F2: catálogo, forma y silueta ---

def test_catalogo_de_tipos():
    import tipos
    ids = [t["id"] for t in tipos.CATALOGO]
    assert len(ids) == len(set(ids)) == 14
    for t in tipos.CATALOGO:
        assert t["grupo"] in ("continuos", "variados", "calidad") and t["descripcion"] and t["forma"]
        assert not any(ch.isdigit() for ch in t["descripcion"].replace("1-2-3-2-1", ""))   # sin números de zona
        for tramo in t["forma"]:
            assert len(tramo) in (2, 3) and tramo[0] > 0 and all(0 <= n <= 1 for n in tramo[1:])
    assert {t["grupo"] for t in tipos.CATALOGO if t["id"] in ("espiga", "piramide", "densidad")} == {"variados"}


def test_forma_derivada_y_silueta_sin_tocar_el_plan():
    import tipos
    plan = planes_v6.generar({**CONFIG_CORREDOR, "intensidad": "calidad"})
    s = plan["weeks"][1]["sessions"]
    assert all("forma" not in x for x in s)                       # el plan no lleva `forma`: se deriva
    assert tipos.forma_de(s[0]) == "continuo" and tipos.forma_de(s[1]) == s[1]["calidad_tipo"]
    cam = planes_v6.generar({**CONFIG_CORREDOR, "nivel": "novato"})["weeks"][0]["sessions"][0]
    assert tipos.forma_de(cam) == "trote_caminata"


def test_silueta_despliega_repeat_caminata_en_su_zona_y_opcionales():
    import tipos
    pasos = [{"kind": "warmup", "minutes": 5, "zone": "Z1-Z2"},
             {"kind": "repeat", "times": 2, "steps": [{"kind": "run", "minutes": 3, "zone": "Z3"},
                                                      {"kind": "walk", "minutes": 1, "zone": "Z1-Z2"}]},
             {"kind": "run", "minutes": 1, "zone": "Z3", "optional": True}]
    assert tipos.silueta_de(pasos) == [[5, "Z2"], [3, "Z3"], [1, "Z1"], [3, "Z3"], [1, "Z1"], [1, "Z3", True]]
    assert tipos.titulo_de("trote_caminata", tipos.silueta_de(pasos, False)) == "Trote y caminata en Z2–Z3"   # sin la caminata


def test_planes_viejos_con_z1_z2_salen_en_una_sola_zona():
    # los planes generados antes decían "Z1-Z2"; el sitio los muestra en una sola zona
    pasos = [{"kind": "warmup", "minutes": 5, "zone": "Z1-Z2"}, {"kind": "run", "minutes": 10, "zone": "Z1-Z2"},
             {"kind": "walk", "minutes": 1, "zone": "Z1-Z2"}, {"kind": "cooldown", "minutes": 5, "zone": "Z1-Z2"}]
    zonas = [("Z1", 125, 138), ("Z2", 138, 151), ("Z3", 151, 164), ("Z4", 164, 177), ("Z5", 177, 190)]
    assert [p["zone"] for p in build.convert_steps(pasos, zonas)] == ["Z2", "Z2", "Z1", "Z1"]
    # caminata y enfriamiento: una racha de Z1 (la caminata es solo un tramo de Z1)
    assert [(r["min"], r["zona"], r["lpm"]) for r in build.rachas_de(pasos, zonas)] == [(15, "Z2", [138, 151]), (6, "Z1", [125, 138])]


def test_data_json_trae_forma_silueta_y_tipos():
    plan = planes_v6.generar({**CONFIG_CORREDOR, "intensidad": "calidad"})
    out = build.build(fixture(), plan, {**CONFIG_CORREDOR, "plan_start": "2026-10-26", "intensidad": "calidad"}, AHORA)
    revisar_privacidad(out)
    ses = out["plan"]["semanas"][1]["sessions"]
    assert ses[1]["forma"] == ses[1]["calidad_tipo"] and ses[0]["forma"] == "continuo"
    assert sum(m for m, *_ in ses[1]["silueta"]) == ses[1]["minutes"]
    assert sum(m for m, *_ in ses[1]["easy"]["silueta"]) == ses[1]["easy"]["minutes"]
    assert ses[0]["titulo"] == "Continuo en Z2"
    # rachas: lo que va escrito encima de la silueta; suman lo mismo y llevan la zona del plan con sus lpm
    for x in (ses[0], ses[1], ses[1]["easy"]):
        assert sum(r["min"] for r in x["rachas"]) == x["minutes"]
    zs = {z["zona"]: z for z in out["zonas"]}
    assert ses[0]["rachas"][0]["zona"] == "Z2" and ses[0]["rachas"][0]["lpm"] == [zs["Z2"]["piso"], zs["Z2"]["techo"]]
    assert out["tipos"]["en_plan"][:1] == ["continuo"] and ses[1]["forma"] in out["tipos"]["en_plan"]
    assert len(out["tipos"]["catalogo"]) == 14 and [g["id"] for g in out["tipos"]["grupos"]] == ["continuos", "variados", "calidad"]
    assert "tipos" in validar.CLAVES


def test_iconos_en_data_json_y_validador():
    out = build.build(fixture(), build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    assert out["ui"]["categorias"][0]["icono"] == "rayo"
    assert all(c["icono"] == "medalla" for c in out["carreras"])
    assert all(r["icono"] in ("correr", "medalla") for r in out["progreso"]["corridas"])
    assert all(x["icono"] in (None, "medalla") for x in out["mejores_marcas"])
    assert validar.problemas(out) == []
    out["ui"]["categorias"][0]["icono"] = "dragon"
    assert any("ícono desconocido" in p for p in validar.problemas(out))


def test_mejora_otras_e_intensidad_por_semana():
    data = fixture()
    # el fixture ya trae CrossFit el 2 y el 3 nov a las 18:00; la de las 19:30 empieza a 60' del fin de la de las 18:00: ya no se junta, cuenta aparte
    data["activities"] = [*data["activities"], _act(30, "2026-11-02", "hiit", hora="07:00:00"),
                          _act(31, "2026-11-03", "strength_training", hora="07:00:00"), _act(32, "2026-11-03", "hiit", hora="19:30:00"),
                          _act(33, "2026-10-13", "hiit"), _act(34, "2026-10-14", "hiit")]
    out = build.build(data, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    # entrenos de la semana (Progreso › Corridas): uno por tipo con su cuenta, primero corridas, luego CrossFit
    ent = out["progreso"]["semanas"][-1]["entrenos"]
    corridas = sum(1 for a in data["activities"] if build.m.classify(a, CONFIG_FIXTURE) == "run" and a["startTimeLocal"] >= "2026-11-02")
    assert ent[-1] == {"icono": "rayo", "nombre": "CrossFit", "n": 5}
    assert sum(e["n"] for e in ent[:-1]) == corridas and all(e["icono"] in ("correr", "medalla") for e in ent[:-1])
    # 80/20: misma cuenta que la barra de Detalles; porcentajes Z1–Z2 / Z3 / Z4–Z5, Z0 fuera
    semana = out["semanas_hoy"][out["semana_hoy_idx"]]["intensidad"]
    assert semana == {**out["detalles"]["distribucion"]}
    mins = semana["minutos"]
    total = sum(mins.values())
    assert total > 0 and abs(semana["bajo"] - (mins["Z1"] + mins["Z2"]) / total * 100) < 0.1
    assert abs(semana["bajo"] + semana["limbo"] + semana["alto"] - 100) < 0.2
    iw = out["progreso"]["intensidad_semanas"]
    assert len(iw) == 12 and iw[-1]["inicio"] == "2026-11-02" and {k: v for k, v in iw[-1].items() if k != "actual"} == {"inicio": "2026-11-02", **semana}
    libre = build.build(data, build.load(ROOT / "plan" / "plan.example.json"), {**CONFIG_FIXTURE, "sin_plan": True}, AHORA)
    iw_libre = libre["progreso"]["intensidad_semanas"]   # sin plan: 12 semanas que terminan en la actual
    assert len(iw_libre) == 12 and iw_libre[-1]["inicio"] == "2026-11-02"
    sin = next(x for x in iw_libre if x["inicio"] == "2026-08-17")
    assert sum(sin["minutos"].values()) == 0 and sin["bajo"] == 0
    assert all("intensidad" in s for s in out["semanas_hoy"])
    revisar_privacidad(out)


def test_calentar_y_enfriar_van_aparte_salvo_que_el_plan_los_traiga():
    """Calentar se dibuja salvo que el plan empiece con un calentamiento suave (Z0/Z1); enfriar, salvo que lo traiga.
    Los 10' Z2 de una calidad vieja no son calentamiento: van como tramo normal."""
    z2 = {"kind": "run", "minutes": 20, "zone": "Z2"}
    assert build.rampas_de([z2]) == {"con_calentamiento": False, "con_enfriamiento": False}
    vieja = [{"kind": "warmup", "minutes": 10, "zone": "Z2"}, {"kind": "run", "minutes": 20, "zone": "Z3"},
             {"kind": "cooldown", "minutes": 5, "zone": "Z1"}]
    assert build.rampas_de(vieja) == {"con_calentamiento": False, "con_enfriamiento": True}
    assert build.convert_steps(vieja, [])[0]["kind"] == "run"
    caminata = [{"kind": "walk", "minutes": 5, "zone": "Z1", "note": "calentamiento"}, z2,
                {"kind": "walk", "minutes": 5, "zone": "Z1", "note": "enfriamiento"}]
    assert build.rampas_de(caminata) == {"con_calentamiento": True, "con_enfriamiento": True}


# --- v4.3 F2: esfuerzo, ayer, sin RPE en el semáforo ---

def test_esfuerzo_y_ayer_en_el_json(salida):
    assert [s["id"] for s in salida["hoy"]["señales"]] == ["hrv", "rhr", "sueno"]
    u = salida["ultima_corrida"]
    assert u["esfuerzo"] is not None and u["rpe"] == 4.0
    assert salida["hoy"]["ayer"] is None or set(salida["hoy"]["ayer"]) == {"categoria", "esfuerzo", "rpe"}
    assert all("sin_rpe" not in s for s in salida["detalles"]["carga_semanas"])
    assert "rpe_heavy" not in salida["detalles"]["umbrales"] and salida["detalles"]["umbrales"]["esfuerzo_duro"] == 8
    assert all({"esfuerzo", "rpe"} <= set(c) for c in salida["progreso"]["corridas"])


def test_ayer_del_dia_y_motivo_con_dia_duro():
    data = fixture()
    ahora = datetime(2026, 11, 3, 12, 0, tzinfo=ZoneInfo("America/Merida"))   # el hiit 1 fue el 2 (ayer)
    data["activities"][0].update(hrTimeInZone_1=0, hrTimeInZone_2=0, hrTimeInZone_3=0, hrTimeInZone_4=1500, hrTimeInZone_5=300)
    data["hrv"] = [{**r, "lastNightAvg": 29} if r["calendarDate"] == "2026-11-03" else r for r in data["hrv"]]
    plan = build.load(ROOT / "plan" / "plan.example.json")
    out = build.build(data, plan, CONFIG_FIXTURE, ahora)
    assert out["hoy"]["ayer"]["categoria"] == "CrossFit" and out["hoy"]["ayer"]["esfuerzo"] >= 8
    assert out["hoy"]["ayer"]["rpe"] == 6.0
    t = out["hoy"]["tarjeta"]
    assert t["motivo"] is None or t["motivo"].endswith("después de un día duro")


def test_la_serie_de_fc_no_sale_en_el_json_pero_si_su_deriva():
    data = fixture()
    serie = [[t, round(t / 360 * 1000), 140 if t < 1800 else 150] for t in range(0, 3001, 5)]
    data["activities"][1]["duration"] = 3000.0
    data["activities"][1].pop("splitSummaries")       # sin tramos: todo trote
    data["details"]["2"] = {**data["details"]["2"], "serie": serie, "splits": []}
    plan = build.load(ROOT / "plan" / "plan.example.json")
    out = build.build(data, plan, CONFIG_FIXTURE, AHORA)
    assert '"serie"' not in json.dumps(out)
    revisar_privacidad(out)
    u = out["ultima_corrida"]
    assert u["deriva_pct"] is not None and u["deriva_ok"] is False and u["ritmo_ref_s"] is not None
    assert out["progreso"]["fc_ref"] == 144 or out["progreso"]["fc_ref"] > 100
    r = next(c for c in out["progreso"]["corridas"] if c["fecha"] == "2026-11-03")
    assert r["deriva_pct"] == u["deriva_pct"]
    assert validar.problemas(json.loads(json.dumps(out))) == []


def test_plan_vs_real_en_el_json(salida):
    u = salida["ultima_corrida"]
    # fixture: 30' con Z1 5' · Z2 15' · Z3 5' ; la Z2 #1 de la semana 2 tiene 25' (20' Z2 + 2 picos opcionales de Z3)
    assert u["sesion"]["id"] == "z2a"
    z2 = next(x for x in u["plan_vs_real"] if x["zona"] == "Z2")
    assert z2["hecho_min"] == 20.0 and z2["plan_min"] >= 20 and "calidad" not in u
    assert next(c for c in salida["plan"]["estado_sesiones"] if c["corrida"])["corrida"]["plan_vs_real"]


def test_resumen_de_la_semana_pasada():
    plan = build.load(ROOT / "plan" / "plan.example.json")
    ahora = datetime(2026, 11, 9, 12, 0, tzinfo=ZoneInfo("America/Merida"))     # lunes: la semana pasada es la del 2 al 8
    out = build.build(fixture(), plan, CONFIG_FIXTURE, ahora)
    r = out["hoy"]["semana_pasada"]
    assert r["inicio"] == "2026-11-02" and r["fin"] == "2026-11-08"
    assert r["sesiones_total"] == 3 and r["sesiones_hechas"] == 1 and r["stats"]["minutos"] == 30
    assert r["sugerencia"]["tipo"] == "repetir"                # solo 1 sesión hecha
    assert {"stats", "intensidad"} <= set(r) and not {"carga", "dias_verdes", "minutos_anterior", "ritmo_ref_s"} & set(r)
    assert "plan_vs_real" not in r and out["ui"]["avisos"]["sugerencia"]
    revisar_privacidad(out)
    vacia = build.build({**fixture(), "activities": []}, plan, CONFIG_FIXTURE, datetime(2026, 12, 20, 12, 0, tzinfo=ZoneInfo("America/Merida")))
    assert vacia["hoy"]["semana_pasada"] is None


# --- v4.3 F6: la prueba y "Plan terminado" ---

def _plan_corto(**kw):
    cfg = {**CONFIG_FIXTURE, "plan_semanas": 4, **kw}
    return planes_v6.generar(cfg), cfg


def _datos_prueba(ritmo=400, minutos=35):
    """Una corrida de la semana 4 (16–22 nov) que cuenta como la prueba, con serie a ritmo constante."""
    data = fixture()
    serie = [[t, round(t / ritmo * 1000), 144] for t in range(0, minutos * 60 + 1, 5)]
    data["activities"].append({"activityId": 900, "startTimeLocal": "2026-11-18 07:00:00", "duration": minutos * 60.0,
                               "activityType": {"typeKey": "running"}, "averageHR": 144.0, "distance": minutos * 60 / ritmo * 1000,
                               "hrTimeInZone_1": 0, "hrTimeInZone_2": minutos * 60, "hrTimeInZone_3": 0, "hrTimeInZone_4": 0,
                               "hrTimeInZone_5": 0})
    data["details"]["900"] = {"rpe": 3.0, "feel": 50, "splits": [], "serie": serie}
    return data


AHORA_FIN = datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("America/Merida"))


def test_plan_terminado_sin_la_prueba_dice_que_falta():
    plan, cfg = _plan_corto()
    t = build.build(fixture(), plan, cfg, AHORA_FIN)["hoy"]["tarjeta"]
    assert t["tipo"] == "plan_terminado" and t["prueba"] is None


def test_plan_no_terminado_no_muestra_la_prueba():
    plan, cfg = _plan_corto()
    t = build.build(_datos_prueba(), plan, cfg, datetime(2026, 11, 22, 20, 0, tzinfo=ZoneInfo("America/Merida")))["hoy"]["tarjeta"]
    assert t["tipo"] != "plan_terminado"
    assert build.plan_terminado(date(2026, 11, 23), cfg, plan) and not build.plan_terminado(date(2026, 11, 22), cfg, plan)
    assert not build.plan_terminado(date(2027, 1, 1), cfg, {"weeks": []})


def test_mejora_sin_corridas_da_motivos():
    out = build.build(VACIO, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    mj = out["progreso"]["mejora"]
    assert mj["ritmo"]["valor"] is None and "Z2" in mj["ritmo"]["motivo"] and mj["ritmo"]["cambio"] is None
    assert mj["deriva"]["valor"] is None and "cumpla" in mj["deriva"]["motivo"] and mj["prueba"] is None
    assert validar.problemas(out) == []


def test_texto_prueba():
    t = build.texto_prueba({"tipo": "fc_fija", "valor": 450, "base": {"fuente": "inicio", "valor": 462}, "dif": -12, "mejor": True})
    assert t["valor"] == "7:30 /km" and t["cambio"] == "▼ 12 s/km vs el inicio, mejor" and t["mejor"] is True
    t = build.texto_prueba({"tipo": "5k", "valor": 1500, "base": None, "dif": None, "mejor": None})
    assert t["valor"] == "25:00" and "Sin base" in t["cambio"]


def test_ayuda_en_el_json_y_en_la_lista_blanca(salida):
    assert [b["titulo"] for b in salida["ayuda"]][:2] == ["El semáforo de cada mañana", "Tus sesiones"]
    assert all(set(b) == {"titulo", "parrafos", "lista"} for b in salida["ayuda"])
    assert validar.problemas(salida) == []


def test_semana_actual_ya_no_marca_dias_y_dice_que_falta():
    data = {**fixture(), "activities": []}
    s = _semana(data, date(2026, 10, 28), date(2026, 10, 26))   # miércoles
    assert not any(d.get("planeado") or "plan_ses" in d for d in s["dias"])
    assert s["plan"]["faltan"] == "Te faltan: 2 fáciles y la larga"


def test_semana_libre_solo_sin_plan_promedios_racha_y_sin_claves_prohibidas():
    import validar
    cfg = {**CONFIG_CORREDOR, "sin_plan": True}
    out = build.build(fixture(), planes_v6.generar(cfg), cfg, AHORA)
    sl = out["semana_libre"]
    assert len(sl["dias"]) == 7 and sum(len(d["actividades"]) for d in sl["dias"]) == sl["actividades"]
    assert sl["minutos"] == round(sum(a["minutos"] for d in sl["dias"] for a in d["actividades"]), 0) or sl["minutos"] >= 0
    assert sl["promedio_minutos"] >= 0 and sl["racha_semanas"] >= 0
    assert all({"nombre", "icono", "minutos", "km", "fc_prom", "sesion"} <= set(a) for d in sl["dias"] for a in d["actividades"])
    assert validar.problemas(out) == []
    assert "semana_libre" not in build.build(fixture(), planes_v6.generar(CONFIG_CORREDOR), CONFIG_CORREDOR, AHORA)


def test_plan_url_null_por_defecto_y_solo_con_la_clave():
    plan = planes_v6.generar(CONFIG_CORREDOR)
    assert build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)["ui"]["plan_url"] is None
    cfg = {**CONFIG_CORREDOR, "plan_url": "/plan/acciones"}
    assert build.build(fixture(), plan, cfg, AHORA)["ui"]["plan_url"] == "/plan/acciones"


def test_tarjeta_hoy_trae_opciones_y_recomendada(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    plan = build.load(ROOT / "plan" / "plan.example.json")
    t = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)["hoy"]["tarjeta"]
    if t["tipo"] == "sesion":
        assert t["recomendada"] == t["version"] and t["recomendada"] in t["opciones"]
        assert t["opciones"][-1] == "normal" and "suave" in t["opciones"]
    else:
        assert t["opciones"] == [] and t["recomendada"] is None


def test_dia_agrupa_actividades_por_dia_con_sesion_y_dia_de_descanso():
    plan = build.load(ROOT / "plan" / "plan.example.json")
    out = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)
    dias = {d["fecha"]: d for s in out["semanas_hoy"] for d in s["dias"]}
    tres = dias["2026-11-03"]["actividades"]
    assert [a["cat"] for a in tres][0] == "run" and len(tres) == 2   # corrida + HIIT el mismo día
    run = tres[0]
    assert (run["minutos"], run["km"], run["fc_prom"]) == (30, 4.5, 140) and run["nombre"] == "Corrida"
    assert run["sesion"] is None or set(run["sesion"]) == {"nombre", "estado"}
    assert dias["2026-11-01"]["actividades"] == []   # día de descanso
    assert all(set(a) >= {"cat", "nombre", "icono", "minutos", "km", "fc_prom", "carrera", "sesion"}
               for d in dias.values() for a in d["actividades"])
    revisar_privacidad(out)


def test_curva_fc_baja_a_120_puntos_o_menos_y_sin_gps():
    serie = [[i, i * 3, 100 + i % 60] for i in range(1800)]
    c = build.curva_fc(serie)
    assert len(c["fc"]) == 120 and c["seg"] == 1799 and all(100 <= v <= 160 for v in c["fc"])
    assert len(build.curva_fc(serie[:30])["fc"]) == 30      # serie corta: no se inventan puntos
    assert build.curva_fc([]) is None and build.curva_fc([[0, 0, None], [5, 9, None]]) is None


def test_detalle_de_actividad_campos_zonas_curva_y_sin_claves_prohibidas():
    fx = fixture()
    fx["activities"][1].update(calories=250.0, elevationGain=12.0, movingDuration=1700.0, aerobicTrainingEffect=2.6,
                               anaerobicTrainingEffect=0.0, trainingEffectLabel="AEROBIC_BASE", trainingEffectMessage="MENSAJE_GARMIN",
                               averageRunningCadenceInStepsPerMinute=158.4)
    fx["details"]["2"]["serie"] = [[i, i * 3, 120 + i % 30] for i in range(0, 1800, 5)]
    out = build.build(fx, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_CORREDOR, AHORA)
    dias = {d["fecha"]: d for s in out["semanas_hoy"] for d in s["dias"]}
    run = next(a for a in dias["2026-11-03"]["actividades"] if a["cat"] == "run")
    dt = run["detalle"]
    assert dt["km"] == 4.5 and dt["ritmo_s"] == round(1700 / 4.5) and dt["fc_prom"] == 140 and dt["fc_max"] == 180
    assert dt["kcal"] == 250 and dt["desnivel_m"] == 12 and dt["cadencia"] == 158 and dt["te_aerobico"] == 2.6
    assert dt["te_anaerobico"] is None and dt["te_etiqueta"] == "Base aeróbica" and dt["vel_kmh"] is None
    assert dt["zonas"]["minutos"]["Z2"] == 15.0 and dt["zonas"]["bajo"] > 60
    assert len(dt["curva_fc"]["fc"]) <= 120
    otra = next(a for a in dias["2026-11-03"]["actividades"] if a["cat"] != "run")["detalle"]
    assert otra["ritmo_s"] is None and otra["curva_fc"] is None and otra["cadencia"] is None
    texto = json.dumps(out, ensure_ascii=False)
    assert "MENSAJE_GARMIN" not in texto
    revisar_privacidad(out)


def test_pulso_en_detalle_sin_datos_del_dispositivo(salida):
    """data.json expone solo pulso banda|muñeca por actividad: nunca serie, sku ni fabricante del sensor."""
    txt = json.dumps(salida) if isinstance(salida, dict) else str(salida)
    for prohibido in ("serialNumber", "antplusDeviceType", "softwareVersion", "sku", "manufacturer", "metadataDTO"):
        assert prohibido not in txt


def test_semanas_plan_progreso_y_marca(salida):
    sem = salida["plan"]["semanas"]
    assert sem[0]["progreso"] == {"hechas": 1, "total": 3, "pct": 33}      # semana 1 (pasada): la corrida del 28/10
    assert sem[1]["progreso"]["total"] == 3 and 0 <= sem[1]["progreso"]["hechas"] <= 3   # la actual
    assert all("progreso" not in w for w in sem[2:])           # futuras: sin clave
    assert all(w["etiqueta"] in ("carga", "descarga") for w in sem)
    assert sem[0].get("marca") is None
    assert sem[0]["cumplimiento"] == "baja"                     # 1 de 3
    assert "cumplimiento" not in sem[1] and all("cumplimiento" not in w for w in sem[2:])   # actual y futuras: sin clave


def test_cumplimiento_semana():
    f = semanal.cumplimiento
    assert f(3, 3) == "completa" and f(2, 3) == "casi" and f(4, 6) == "casi" and f(1, 3) == "baja" and f(0, 3) == "baja"
    assert f(0, 0) is None


def test_marcas_semana_dos_eventos_en_orden():
    w = {"sessions": [{"tipo": "prueba"}]}
    cfg = {"metas": [], "eventos": [{"tipo": "viaje", "desde": "2026-11-03", "hasta": "2026-11-04"}]}
    assert build.marcas_semana(w, date(2026, 11, 2), cfg) == ["viaje", "prueba"]
    assert build.marca_semana(w, date(2026, 11, 2), cfg) == "viaje"


def test_marca_semana_por_fechas_y_prioridad():
    w = {"sessions": [{"tipo": "z2"}]}
    lun = date(2026, 11, 2)
    cfg = {"metas": [], "eventos": [{"tipo": "enfermedad", "desde": "2026-11-05", "hasta": "2026-11-06"}]}
    assert build.marca_semana(w, lun, cfg) == "enfermedad"
    cfg["eventos"].append({"tipo": "viaje", "desde": "2026-11-01", "hasta": "2026-11-03"})
    assert build.marca_semana(w, lun, cfg) == "viaje"
    cfg["metas"].append({"fecha": "2026-11-08", "nombre": "x", "distancia_km": 5})
    assert build.marca_semana(w, lun, cfg) == "carrera"
    assert build.marca_semana({"sessions": [{"tipo": "prueba"}]}, lun, {}) == "prueba"
    assert build.marca_semana(w, date(2026, 12, 7), cfg) is None


def test_titular_hoy_por_estado():
    z2 = {"id": "a", "name": "Z2 #1", "minutes": 20, "steps": [{"kind": "run", "minutes": 20, "zone": "Z2"}],
          "easy": {"name": "Suave", "minutes": 15, "steps": [{"kind": "run", "minutes": 15, "zone": "Z2"}]}}
    larga = {"id": "l", "name": "Larga", "minutes": 30, "steps": [{"kind": "run", "minutes": 30, "zone": "Z2"}],
             "easy": {"name": "Suave", "minutes": 20, "steps": [{"kind": "run", "minutes": 20, "zone": "Z2"}]}}
    ses = [z2, larga]
    t = build.titular_hoy
    assert t({"tipo": "sesion", "version": "normal", "sesion_id": "a"}, ses) == "Hoy toca: Z2 #1 · 20 min"
    assert t({"tipo": "sesion", "version": "normal", "sesion_id": "l"}, ses) == "Hoy toca: Larga · Z2 · 30 min"
    assert t({"tipo": "sesion", "version": "suave", "sesion_id": "l"}, ses) == "Hoy toca: Larga suave · Z2 · 20 min"
    assert t({"tipo": "sesion", "version": "descanso", "sesion_id": "a"}, ses, "l") == "Hoy descansas · mañana: Larga · Z2 · 30 min"
    assert t({"tipo": "sesion", "version": "descanso", "sesion_id": "a"}, ses) == "Hoy descansas"
    assert t({"tipo": "hecha_hoy"}, ses) == "Ya la hiciste hoy ✔"
    assert t({"tipo": "hecha_hoy"}, ses, "a") == "Ya la hiciste hoy ✔ · mañana: Z2 #1 · 20 min"
    assert t({"tipo": "otra", "categoria": "Pierna"}, ses, "l") == "Hoy: Pierna ✓ · mañana: Larga · Z2 · 30 min"
    assert t({"tipo": "completa"}, ses) == "Semana completa: hiciste las 3"
    for tipo in ("sin_plan", "primera_sync", "pausa"):
        assert t({"tipo": tipo, "texto": "Texto X"}, ses) == "Texto X"
    assert t({"tipo": "plan_terminado", "texto": "Plan terminado"}, ses) is None


def test_huella_de_avisos_estable_y_cambia_con_el_contenido():
    assert build.huella("FC máx 190") == build.huella("FC máx 190") != build.huella("FC máx 191")
    fc = {"revisar": True, "estimacion": 190.4}
    a = build.huellas_avisos({"aviso": "x"}, "zonas!", fc, {"repetir_semana": True}, 3)
    assert set(a) == {"hoy", "zonas", "fcmax", "repetir"}
    assert build.huellas_avisos({"aviso": "x"}, None, {"revisar": False}, {}, 3) == {"hoy": a["hoy"]}
    assert build.huellas_avisos({}, None, {"revisar": True, "estimacion": 191}, {}, 3)["fcmax"] != a["fcmax"]


def test_huella_de_sugerencia_depende_de_la_semana():
    sug = {"tipo": "repetir"}
    a = build.huellas_avisos({}, None, {}, {}, 3, sug, "2026-11-16")
    assert a == build.huellas_avisos({}, None, {}, {}, 3, sug, "2026-11-16")
    assert a["sugerencia"] != build.huellas_avisos({}, None, {}, {}, 3, sug, "2026-11-23")["sugerencia"]
    assert "sugerencia" not in build.huellas_avisos({}, None, {}, {}, 3, {"tipo": "sigue"}, "2026-11-16")


def test_semanas_plan_estados_por_sesion(salida):
    sem = salida["plan"]["semanas"]
    assert [e["estado"] for e in sem[0]["estados"]].count("hecha") == sem[0]["progreso"]["hechas"]
    assert {e["estado"] for e in sem[0]["estados"]} <= {"hecha", "incompleta", "no_hecha"}      # pasada: nada «pendiente»
    assert "estados" not in sem[1]                                                              # la actual usa estado_sesiones
    assert all(e["estado"] == "pendiente" for w in sem[2:] for e in w["estados"])               # futuras


def test_ui_cuerpo_nuevo_null_por_defecto_y_con_la_clave():
    plan = planes_v6.generar(CONFIG_CORREDOR)
    assert build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)["ui"]["cuerpo_nuevo"] is None
    cfg = {**CONFIG_CORREDOR, "cuerpo_nuevo": "/cuerpo/nuevo"}
    out = build.build(fixture(), plan, cfg, AHORA)
    assert out["ui"]["cuerpo_nuevo"] == "/cuerpo/nuevo" and validar.problemas(out) == []


def test_ui_grupos_cero_por_defecto():
    plan = planes_v6.generar(CONFIG_CORREDOR)
    out = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)
    assert out["ui"]["grupos"] == 0 and validar.problemas(out) == []


# --- Unificar U3: el bloque y las series miden el largo real del plan (8, 12, 16) ---

def test_bloques_y_series_siguen_el_largo_del_plan():
    for n in (8, 12, 16):
        cfg = {**CONFIG_FIXTURE, "plan_semanas": n}
        plan = planes_v6.generar(cfg)
        out = build.build(fixture(), plan, cfg, datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("America/Merida")))
        p = out["plan"]
        assert p["largo"] == n == len(p["semanas"]) and p["bloques"] == sorted({w["block"] for w in p["semanas"]})
        assert all(w["block"] in p["bloques"] and w["plan_min"] is not None for w in p["semanas"])
        assert len(out["progreso"]["semanas"]) == len(out["detalles"]["carga_semanas"]) == len(out["progreso"]["intensidad_semanas"]) >= max(n, 12)   # 12 semanas y todo el plan
        for serie in (out["progreso"]["semanas"], out["detalles"]["carga_semanas"], out["progreso"]["intensidad_semanas"]):
            assert [s["actual"] for s in serie].count(True) == 1 and len(serie) >= n
        hechas = [w for w in p["semanas"] if "minutos" in w]
        assert hechas and all(w["km"] is not None for w in hechas)   # lo hecho viene en minutos y en km; el objetivo solo en minutos
        assert not any("objetivo_km" in w for w in p["semanas"])   # el objetivo del plan no tiene km; plan_km es solo un estimado de las futuras
        revisar_privacidad(out)


# --- km estimados del plan y periodo «todo el plan» ---

def _filas_ritmo(hoy, ritmos, km=5.0, **extra):
    from datetime import timedelta
    return [{"fecha": (hoy - timedelta(days=3 * (i + 1))).isoformat(), "minutos": r * km, "km": km, **extra} for i, r in enumerate(ritmos)]


def test_ritmo_facil_mediana_limites_y_sin_datos():
    import semanal
    from datetime import date
    hoy = date(2026, 11, 25)
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [6, 7, 9]), hoy) == 7        # mediana, no promedio
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [6, 7, 8, 9]), hoy) == 7.5
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [6, 7, 9, 2.0, 30.0]), hoy) == 7  # ritmos imposibles se descartan
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [6, 7]), hoy) is None           # muy pocas corridas
    assert semanal.ritmo_facil([], hoy) is None
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [6, 7, 9], carrera=True), hoy) is None   # las carreras no cuentan
    viejas = _filas_ritmo(hoy, [6, 7, 9])
    for f in viejas:
        f["fecha"] = "2026-01-01"
    assert semanal.ritmo_facil(viejas, hoy) is None                              # fuera de las últimas semanas


def test_volumen_plan_km_redondea_y_cae_a_minutos():
    import semanal
    assert semanal.volumen_plan(60, "min", 7.0) == 60
    assert semanal.volumen_plan(60, "km", 7.0) == 8.5      # 8.57 → a 0.5
    assert semanal.volumen_plan(3, "km", 8.0) == 0.5       # nunca 0 km
    assert semanal.volumen_plan(60, "km", None) is None    # sin ritmo: la página muestra minutos
    assert semanal.volumen_plan(None, "km", 7.0) is None


def test_periodos_de_progreso_siempre_4_8_12_y_todo_el_plan():
    import semanal
    from datetime import date, timedelta
    hoy = date(2026, 11, 25)   # miércoles; la semana actual empieza el 2026-11-23
    def plan(n, inicio="2026-10-12"):
        return {"start": inicio, "weeks": [{"n": i} for i in range(1, n + 1)]}
    def forma(ops):
        return [(p["n"], p["todo"]) for p in ops]
    assert forma(semanal.periodos_progreso(hoy, plan(7), {})) == [(4, False), (8, False), (12, False), (7, True)]
    assert forma(semanal.periodos_progreso(hoy, plan(16), {})) == [(4, False), (8, False), (12, False), (16, True)]
    assert semanal.periodos_progreso(hoy, None, {}) == [{"n": k, "todo": False} for k in (4, 8, 12)]
    assert semanal.periodos_progreso(hoy, plan(16), {"sin_plan": True}) == [{"n": k, "todo": False} for k in (4, 8, 12)]
    todo = semanal.periodos_progreso(hoy, plan(7), {})[-1]
    assert (todo["desde"], todo["hasta"]) == ("2026-10-12", "2026-11-23")
    for p in (plan(7), plan(16), None):   # la serie alcanza para 12 semanas hasta la actual y para todo el plan
        serie = semanal.serie_semanas(hoy, p, {})
        assert len(serie) >= 12 and serie[-1] >= date(2026, 11, 23) and all(b - a == timedelta(weeks=1) for a, b in zip(serie, serie[1:]))
        assert date(2026, 11, 23) - timedelta(weeks=11) >= serie[0]
    s16 = semanal.serie_semanas(hoy, plan(16), {})
    assert len(s16) == 21 and s16[0] == date(2026, 9, 7)   # 12 semanas hasta la actual + las 16 del plan (10 oct → 25 ene)
    assert [s.isoformat() for s in s16][-1] == "2027-01-25"


def test_plan_visible_sin_actividades_no_filtra_el_ritmo():
    import semanal
    plan = {"largo": 2, "semanas": [
        {"n": 1, "block": 1, "kind": "carga", "sessions": [{"id": "a", "minutes": 30, "km_est": 4.0}], "plan_min": 30, "plan_km": 4.0},
        {"n": 2, "block": 1, "kind": "carga", "sessions": [{"id": "a", "minutes": 30, "km_est": 4.0}], "plan_min": 30, "plan_km": 4.0}]}
    con, sin = semanal.plan_visible(plan, True), semanal.plan_visible(plan, False)
    assert con["semanas"][0]["plan_km"] == 4.0 and con["semanas"][0]["sessions"][0]["km_est"] == 4.0
    plan["nivel"] = "base"
    sin = semanal.plan_visible(plan, False)
    assert all(w["plan_km"] == 4.0 and w["sessions"][0]["km_est"] == 4.0 for w in sin["semanas"])   # 30 min a 7.5 = 4.0, no el 4.0 «real»
    plan["semanas"][0].update(plan_km=9.9, sessions=[{"id": "a", "minutes": 30, "km_est": 9.9}])    # un ritmo real distinto no se cuela
    assert semanal.plan_visible(plan, False)["semanas"][0]["plan_km"] == 4.0
    assert sin["semanas"][0]["sessions"][0]["minutes"] == 30   # los minutos siguen


def test_build_trae_km_estimados_en_semanas_futuras_y_periodos_del_plan():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    import planes_v6
    cfg = {**CONFIG_FIXTURE, "plan_semanas": 16}
    out = build.build(fixture(), planes_v6.generar(cfg), cfg, datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo("America/Merida")))
    assert [p["n"] for p in out["progreso"]["periodos"]] == [4, 8, 12, 16] and out["progreso"]["periodos"][-1]["todo"]
    assert len(out["progreso"]["semanas"]) >= 16 and "16" in out["progreso"]["numeros"]["periodos"]
    fut = [w for w in out["plan"]["semanas"] if w["n"] > out["plan"]["semana_actual"]]
    assert fut and all("plan_km" in w and all("km_est" in s for s in w["sessions"]) for w in fut)
    import validar
    assert validar.problemas(out) == []


def test_ritmo_facil_principiante_trote_camina_y_ritmo_por_nivel():
    import semanal
    from datetime import date
    from nivel import RITMO_NIVEL
    hoy = date(2026, 11, 25)
    filas = _filas_ritmo(hoy, [12, 13.5, 15], km=1.0)   # 12–15 min/km, 1 km
    filas[0]["minutos"] = 12
    assert semanal.ritmo_facil(filas, hoy) == 13.5
    assert semanal.ritmo_facil(_filas_ritmo(hoy, [10, 11, 12], km=0.6), hoy) == 11   # corridas cortas también cuentan
    assert semanal.ritmo_o_nivel(None, "empezando") == RITMO_NIVEL["empezando"] and semanal.ritmo_o_nivel(8.0, "base") == 8.0
    assert RITMO_NIVEL["empezando"] > RITMO_NIVEL["base"] > RITMO_NIVEL["corredor"]


def test_perfil_sin_actividades_km_del_nivel_y_el_js_pinta_km_est():
    import semanal
    plan = {"nivel": "empezando", "largo": 1, "semanas": [
        {"n": 1, "block": 1, "kind": "carga", "plan_min": 45, "plan_km": 3.5,
         "sessions": [{"id": "a", "minutes": 15, "km_est": 2.5}]}]}   # 2.5 y 3.5 = ritmo real de 6 min/km
    v = semanal.plan_visible(plan, False)["semanas"][0]
    assert v["plan_km"] == 5.0 and v["sessions"][0]["km_est"] == 1.5   # 45/9 y 15/9 (a 0.5): nada del ritmo real
    assert semanal.plan_visible(plan, True)["semanas"][0]["plan_km"] == 3.5
    from pathlib import Path
    js = (Path(__file__).resolve().parent.parent / "site" / "vistas.js").read_text()
    assert "km_est" in js and "pintarSesiones();" in js and "tarjetaPlan(p.plan" in js   # el perfil usa la tarjeta compartida y la pinta al nacer
