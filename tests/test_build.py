import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import build  # noqa: E402

from ajustes import cargar_config  # noqa: E402

CONFIG = cargar_config(ROOT / "tests" / "fixtures")
# El fixture es de la semana del 26 oct: usa una copia del config con ese inicio de plan.
CONFIG_FIXTURE = {**CONFIG, "plan_start": "2026-10-26"}
AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Merida"))  # miércoles, semana 2

PROHIBIDAS = ["activityId", "activityName", "ownerDisplayName", "ownerFullName", "userProfilePk",
              "userProfilePK", "userProfileId", "uuid", "activityUUID", "displayName", "locationName",
              "profileImageUrl", "ownerProfileImageUrlSmall", "fullName", "emailAddress",
              "startLatitude", "startLongitude", "endLatitude", "endLongitude",
              "splitSummaries", "splits"]
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
    assert len(p["dias"]) == 84 and len(p["semanas"]) == 12 and set(p["resumen"]) == {"4", "8", "12"}
    assert set(salida["detalles"]) >= {"distribucion", "carga", "carga_anterior", "carga_semanas",
                                       "fc_max", "umbrales"}
    assert len(salida["detalles"]["carga_semanas"]) == 12
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
    assert [c["sesion"] for c in p["corridas"]] == ["Z2 #1", "Z2 #1"]
    assert p["corridas"][0]["pct_trote"] == 66.7 and p["corridas"][0]["ritmo_trote_s"] == 400
    ultima = p["semanas"][-1]
    assert ultima["inicio"] == "2026-11-02" and ultima["minutos"] == 30 and ultima["min_trote"] == 20
    assert ultima["min_camina"] == 10 and ultima["plan_min"] == 100   # semana 2 del ejemplo: 25+25+50
    assert p["semanas"][-2]["plan_min"] == 80                         # semana 1: 20+20+40
    assert p["semanas"][0]["plan_min"] is None
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
    assert ses["steps"][0]["lpm"] == [125, 151]   # Z1-Z2 con reposo 60 y máx 190
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
    out = build.build(data, plan, {**CONFIG_FIXTURE, "semana_tipica": {}}, AHORA)
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
    c = out["plan"]["estado_sesiones"][0]["corrida"]
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
    assert len(semanas) == 12
    s = semanas[out["semana_hoy_idx"]]
    assert s["n"] == 1 and s["estado"] == "actual" and s["stats"]["corridas"] == 1
    assert s["sesiones"][0]["estado"] == "hecha" and s["extras"] == []
    assert s["dias"][3]["corrida"]["sesion_nombre"] == "Z2 #1"
    futura = semanas[1]
    assert futura["estado"] == "futura" and futura["stats"]["corridas"] == 0
    assert {e["estado"] for e in futura["sesiones"]} == {"pendiente"}


def test_semanas_hoy_fuera_del_plan(salida):
    out = build.build(fixture(), build.load(ROOT / "plan" / "plan.example.json"), CONFIG, AHORA)
    assert len(out["semanas_hoy"]) == 3                       # 2 del plan de ejemplo + la semana de hoy (sin plan)
    # el plan empieza el 9 nov: se abre en la semana 1 como vista previa
    assert out["semanas_hoy"][out["semana_hoy_idx"]]["n"] == 1
    s = next(x for x in out["semanas_hoy"] if x["inicio"] == "2026-11-02")
    assert s["n"] is None and s["plan"] is None and s["sesiones"] == []
    assert s["inicio"] == "2026-11-02" and s["stats"]["corridas"] == 1 and len(s["extras"]) == 1


def test_semana_con_cuatro_corridas_trae_un_extra():
    data = fixture()
    data["activities"] = [_act(10, "2026-11-02", "running"), _act(11, "2026-11-03", "running"),
                          _act(12, "2026-11-07", "running", minutos=50), _act(13, "2026-11-08", "running", minutos=30)]
    s = _semana(data, date(2026, 11, 8), date(2026, 11, 2))
    assert s["stats"]["corridas"] == 4 and s["estado"] == "actual"
    assert [e["estado"] for e in s["sesiones"]] == ["hecha", "hecha", "hecha"]
    assert len(s["extras"]) == 1 and s["extras"][0]["fecha"] == "2026-11-08" and s["extras"][0]["minutos"] == 30
    assert s["dias"][6]["corrida"] == {"minutos": 30, "sesion_nombre": "Extra", "estado": "extra"}
    assert s["dias"][5]["corrida"]["sesion_nombre"] == "Larga"


def test_semana_pasada_sesion_sin_hacer_es_no_hecha():
    data = fixture()
    data["activities"] = [_act(10, "2026-11-03", "running")]
    s = _semana(data, date(2026, 11, 12), date(2026, 11, 2))
    assert s["estado"] == "pasada"
    assert [e["estado"] for e in s["sesiones"]] == ["hecha", "no_hecha", "no_hecha"]
    assert s["sesiones"][1]["corrida"] is None
    assert s["plan"] == {"total": 3, "hechas": 1, "incompletas": 0, "plan_min": 100}


def test_semana_futura_todo_pendiente_y_planeado():
    data = {**fixture(), "activities": []}
    s = _semana(data, date(2026, 10, 28), date(2026, 11, 2))
    assert s["estado"] == "futura" and s["stats"]["corridas"] == 0
    assert {e["estado"] for e in s["sesiones"]} == {"pendiente"}
    assert [d["planeado"] for d in s["dias"]] == ["crossfit", "crossfit", None, "crossfit", None, "larga", "larga"]
    assert all(d["luz"] is None for d in s["dias"])


def test_dia_futuro_martes_planeado_cf():
    s = _semana({**fixture(), "activities": []}, date(2026, 11, 2), date(2026, 11, 2))
    assert s["dias"][1]["planeado"] == "crossfit" and s["dias"][2]["planeado"] is None


def test_otras_del_dia_toma_te_maximo_y_suma_minutos():
    data = fixture()
    data["activities"] = [_act(20, "2026-11-02", "strength_training", minutos=14, aerobicTrainingEffect=2.2),
                          _act(21, "2026-11-02", "hiit", minutos=16, aerobicTrainingEffect=3.4)]
    data["details"] = {"20": {"rpe": 5.0}, "21": {"rpe": 7.0}}
    s = _semana(data, date(2026, 11, 4), date(2026, 11, 2))
    assert s["dias"][0]["otras"] == [{"cat": "crossfit", "te": 3.4, "rpe": 7.0, "minutos": 30}]
    assert s["dias"][1]["otras"] == []


# --- v3.2 F2 ---

def test_mejora_y_composicion_en_el_json(salida):
    mj = salida["progreso"]["mejora"]
    assert set(mj) == {"frase", "modo", "semanas", "corridas"} and len(mj["semanas"]) == 8
    assert mj["semanas"][-1]["inicio"] == "2026-11-02" and mj["semanas"][-1]["minutos"] == 30
    assert [c["pct_trote"] for c in mj["corridas"]] == [66.7, 66.7]
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
    assert [c["id"] for c in ui["categorias"]] == ["fuerza", "hiit", "cardio"]
    assert [c["clase"] for c in ui["categorias"]] == ["azul", "aqua", "violeta"]
    assert ui["nombre_intensa"] == "HIIT" and ui["titulo"] == "Mi base" and ui["acciones_url"] is None
    assert ui["textos"]["semana"].endswith("Fuerza lunes. HIIT miércoles. Cardio viernes. Día de pierna: lunes.")
    assert ui["textos"]["incluye"] == "Incluye Fuerza, HIIT, Cardio y corridas."
    lun = next(d for s in out["semanas_hoy"] for d in s["dias"] if d["fecha"] == "2026-11-02")
    assert sorted(o["cat"] for o in lun["otras"]) == ["fuerza", "hiit"]
    assert set(out["detalles"]["carga"]) >= {"fuerza", "hiit", "cardio", "run", "total"}
    assert set(out["detalles"]["carga_semanas"][0]["cargas"]) == {"fuerza", "hiit", "cardio"}
    assert out["detalles"]["fc_max"]["configurada"] is False


def test_acciones_url_desde_variable(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "amigo/mi-dashboard")
    ui = build.build_ui(CONFIG_CORREDOR, build.load(ROOT / "plan" / "plan.example.json"))
    assert ui["acciones_url"] == "https://github.com/amigo/mi-dashboard/actions/workflows/deploy.yml"


# --- v4 F3: calidad, mejora por ritmo, primer día, InBody opcional ---

sys.path.insert(0, str(ROOT / "plan"))
import gen_plan  # noqa: E402

VACIO = {"daily_summaries": [], "sleep": [], "hrv": [], "activities": [], "details": {}, "hr_zones": [],
         "meta": {}, "inbody": None}


def test_primer_dia_sin_datos_y_plan_futuro():
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-12-07"}
    plan = gen_plan.generar(cfg)
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
    out = build.build(VACIO, gen_plan.generar(cfg), cfg, datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("America/Mexico_City")))
    assert out["hoy"]["tarjeta"]["texto"] == "Primera sincronización lista. Garmin tarda en mandar el historial; regresa en unas horas"
    assert out["semanas_hoy"][out["semana_hoy_idx"]]["n"] == 1 and out["semanas_hoy"][out["semana_hoy_idx"]]["estado"] == "actual"


def test_plan_futuro_con_datos_dice_cuando_empieza():
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-12-07", "semana_tipica": {}}
    out = build.build(fixture(), gen_plan.generar(cfg), cfg, AHORA)
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
    plan = gen_plan.generar(CONFIG_CORREDOR)
    out = build.build(data, plan, {**CONFIG_CORREDOR, "plan_start": "2026-11-09"}, datetime(2026, 11, 24, 12, 0, tzinfo=ZoneInfo("America/Mexico_City")))
    mj = out["progreso"]["mejora"]
    assert mj["modo"] == "ritmo"
    assert mj["frase"].endswith("a la misma FC vas 0:25/km más rápido que hace 4 semanas.")
    assert [r["ritmo_s"] for r in mj["ritmo"]] == [400, 400, 375, 375]


def test_mejora_con_caminatas_sigue_en_trote(salida):
    assert salida["progreso"]["mejora"]["modo"] == "trote" and "ritmo" not in salida["progreso"]["mejora"]


def test_sesion_de_calidad_en_el_json():
    plan = gen_plan.generar({**CONFIG_CORREDOR, "calidad_tipos": ["threshold"]})
    out = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)
    s = next(x for x in out["plan"]["semanas"][0]["sessions"] if x["tipo"] == "calidad")
    assert s["estructura"] == "10' Z2 · 4×5' threshold (2' suave) · 5' suave"
    assert s["objetivo"]["zona"] == "Z4" and s["objetivo"]["minutos"] == 20 and len(s["objetivo"]["lpm"]) == 2
    assert s["calidad_tipo"] == "threshold"
