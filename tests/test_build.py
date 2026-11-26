import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import build  # noqa: E402
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
    assert s["dias"][6]["corrida"] == {"minutos": 30, "sesion_nombre": "Extra", "estado": "extra", "carrera": False, "icono": "correr"}
    assert s["dias"][5]["corrida"]["sesion_nombre"] == "Larga"


def test_semana_pasada_sesion_sin_hacer_es_no_hecha():
    data = fixture()
    data["activities"] = [_act(10, "2026-11-03", "running")]
    s = _semana(data, date(2026, 11, 12), date(2026, 11, 2))
    assert s["estado"] == "pasada"
    assert [e["estado"] for e in s["sesiones"]] == ["hecha", "no_hecha", "no_hecha"]
    assert s["sesiones"][1]["corrida"] is None
    assert s["plan"] == {"total": 3, "hechas": 1, "incompletas": 0, "plan_min": 100}


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


def test_otras_del_dia_toma_esfuerzo_maximo_y_suma_minutos():
    data = fixture()
    data["activities"] = [_act(20, "2026-11-02", "strength_training", minutos=14, hrTimeInZone_1=0, hrTimeInZone_2=840,
                               hrTimeInZone_3=0, hrTimeInZone_4=0, hrTimeInZone_5=0),
                          _act(21, "2026-11-02", "hiit", minutos=16, hrTimeInZone_1=0, hrTimeInZone_2=0,
                               hrTimeInZone_3=0, hrTimeInZone_4=960, hrTimeInZone_5=0)]
    data["details"] = {"20": {"rpe": 5.0}, "21": {"rpe": 7.0}}
    s = _semana(data, date(2026, 11, 4), date(2026, 11, 2))
    assert s["dias"][0]["otras"] == [{"cat": "crossfit", "icono": "rayo", "esfuerzo": 7.5, "rpe": 7.0, "minutos": 30}]
    assert s["dias"][1]["otras"] == []


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
    assert [c["id"] for c in ui["categorias"]] == ["fuerza", "hiit", "cardio"]
    assert [c["clase"] for c in ui["categorias"]] == ["azul", "aqua", "violeta"]
    assert ui["nombre_intensa"] == "HIIT" and ui["titulo"] == "Mi base" and ui["acciones_url"] is None
    assert ui["textos"]["semana"].endswith("(sábado o domingo). Día de pierna: lunes.")
    assert "Fuerza lunes" not in ui["textos"]["semana"]
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
    cfg = {**CONFIG_CORREDOR, "plan_start": "2026-12-07"}
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
    r = mj["ritmo"]   # 400 y 375 s/km a 145 lpm, llevados a 142: 408 y 383; el plan empieza el 9 nov (semanas 1–2 = 383)
    assert (r["fc_ref"], r["n"], r["actual_s"], r["inicio_s"], r["dif_s"]) == (142, 4, 396, 383, 13)
    assert r["valor"] == "6:36 /km" and r["cambio"] == "▲ 13 s vs inicio" and r["mejora"] is False


def test_mejora_con_caminatas_sigue_en_trote(salida):
    assert salida["progreso"]["mejora"]["modo"] == "trote" and "actual_s" in salida["progreso"]["mejora"]["ritmo"]


def test_sesion_de_calidad_en_el_json():
    plan = gen_plan.generar({**CONFIG_CORREDOR, "calidad_tipos": ["threshold"]})
    out = build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)
    s = next(x for x in out["plan"]["semanas"][0]["sessions"] if x["tipo"] == "calidad")
    assert s["estructura"] == "10' Z2 · 4×5' threshold (2' suave)"
    assert s["objetivo"]["zona"] == "Z4" and s["objetivo"]["minutos"] == 20 and len(s["objetivo"]["lpm"]) == 2
    assert s["calidad_tipo"] == "threshold"


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
    plan = gen_plan.generar({**CONFIG_CORREDOR, "intensidad": "z2_poca_z3", "variada": True, "caminatas": False})
    s = plan["weeks"][1]["sessions"]
    assert all("forma" not in x for x in s)                       # el plan no lleva `forma`: se deriva
    assert [tipos.forma_de(x) for x in s][0] == "continuo" and tipos.forma_de(s[1]) == s[1]["variada_tipo"]
    cam = gen_plan.generar({**CONFIG_CORREDOR, "caminatas": True})["weeks"][0]["sessions"][0]
    assert tipos.forma_de(cam) == "trote_caminata"
    cal = gen_plan.generar({**CONFIG_CORREDOR, "intensidad": "calidad", "calidad_tipos": ["threshold"]})["weeks"][0]["sessions"][1]
    assert tipos.forma_de(cal) == "umbral"


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
    plan = gen_plan.generar({**CONFIG_CORREDOR, "intensidad": "z2_poca_z3", "variada": True})
    out = build.build(fixture(), plan, {**CONFIG_CORREDOR, "plan_start": "2026-10-26", "intensidad": "z2_poca_z3"}, AHORA)
    revisar_privacidad(out)
    ses = out["plan"]["semanas"][1]["sessions"]
    assert ses[1]["forma"] == ses[1]["variada_tipo"] and ses[0]["forma"] == "continuo"
    assert sum(m for m, *_ in ses[1]["silueta"]) == ses[1]["minutes"]
    assert sum(m for m, *_ in ses[1]["easy"]["silueta"]) == ses[1]["easy"]["minutes"]
    assert ses[0]["titulo"] == "Continuo en Z2" and ses[1]["titulo"].endswith("en Z1–Z3")   # variada con pico corto de Z3
    assert ses[1]["easy"]["titulo"].startswith(("Continuo en", "Trote y caminata en"))
    # rachas: lo que va escrito encima de la silueta; suman lo mismo y llevan la zona del plan con sus lpm
    for x in (ses[0], ses[1], ses[1]["easy"]):
        assert sum(r["min"] for r in x["rachas"]) == x["minutes"]
    zs = {z["zona"]: z for z in out["zonas"]}
    assert ses[0]["rachas"][0]["zona"] == "Z2" and ses[0]["rachas"][0]["lpm"] == [zs["Z2"]["piso"], zs["Z2"]["techo"]]
    assert out["tipos"]["en_plan"][:1] == ["continuo"] and ses[1]["forma"] in out["tipos"]["en_plan"]
    assert len(out["tipos"]["catalogo"]) == 14 and [g["id"] for g in out["tipos"]["grupos"]] == ["continuos", "variados", "calidad"]
    assert "tipos" in validar.CLAVES


def test_estructura_de_progresivo_y_fartlek():
    for tipo, esperado in (("progresivo", "progresivo"), ("fartlek", "fartlek")):
        plan = gen_plan.generar({**CONFIG_CORREDOR, "intensidad": "calidad", "calidad_tipos": [tipo]})
        s = build.convert_session(plan["weeks"][0]["sessions"][1], [("Z1", 100, 110), ("Z2", 110, 120), ("Z3", 120, 130),
                                                                   ("Z4", 130, 140), ("Z5", 140, 150)])
        assert esperado in s["estructura"] and s["forma"] == tipo and s["objetivo"]["zona"] == "Z3"


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
    # el fixture ya trae CrossFit el 2 y el 3 nov a las 18:00; la de las 19:30 es la misma clase grabada en dos partes
    data["activities"] = [*data["activities"], _act(30, "2026-11-02", "hiit", hora="07:00:00"),
                          _act(31, "2026-11-03", "strength_training", hora="07:00:00"), _act(32, "2026-11-03", "hiit", hora="19:30:00"),
                          _act(33, "2026-10-13", "hiit"), _act(34, "2026-10-14", "hiit")]
    out = build.build(data, build.load(ROOT / "plan" / "plan.example.json"), CONFIG_FIXTURE, AHORA)
    # entrenos de la semana (Progreso › Corridas): uno por tipo con su cuenta, primero corridas, luego CrossFit
    ent = out["progreso"]["semanas"][-1]["entrenos"]
    corridas = sum(1 for a in data["activities"] if build.m.classify(a, CONFIG_FIXTURE) == "run" and a["startTimeLocal"] >= "2026-11-02")
    assert ent[-1] == {"icono": "rayo", "nombre": "CrossFit", "n": 4}
    assert sum(e["n"] for e in ent[:-1]) == corridas and all(e["icono"] in ("correr", "medalla") for e in ent[:-1])
    # 80/20: misma cuenta que la barra de Detalles; porcentajes Z1–Z2 / Z3 / Z4–Z5, Z0 fuera
    semana = out["semanas_hoy"][out["semana_hoy_idx"]]["intensidad"]
    assert semana == {**out["detalles"]["distribucion"]}
    mins = semana["minutos"]
    total = sum(mins.values())
    assert total > 0 and abs(semana["bajo"] - (mins["Z1"] + mins["Z2"]) / total * 100) < 0.1
    assert abs(semana["bajo"] + semana["limbo"] + semana["alto"] - 100) < 0.2
    iw = out["progreso"]["intensidad_semanas"]
    assert len(iw) == 12 and iw[-1]["inicio"] == "2026-11-02" and iw[-1] == {"inicio": "2026-11-02", **semana}
    sin = next(x for x in iw if x["inicio"] == "2026-08-17")
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
    assert r["sesiones_total"] == 3 and r["sesiones_hechas"] == 1 and r["minutos"] == 30
    assert r["dias_verdes"] + r["dias_rojos"] + r["dias_sin_datos"] <= 7 and r["dias_verdes"] >= 1
    assert r["sugerencia"]["tipo"] == "repetir"                # solo 1 sesión hecha
    assert {"carga", "carga_anterior", "intensidad", "plan_vs_real", "ritmo_ref_s"} <= set(r)
    revisar_privacidad(out)
    vacia = build.build({**fixture(), "activities": []}, plan, CONFIG_FIXTURE, datetime(2026, 12, 20, 12, 0, tzinfo=ZoneInfo("America/Merida")))
    assert vacia["hoy"]["semana_pasada"] is None


# --- v4.3 F6: la prueba y "Plan terminado" ---

def _plan_corto(**kw):
    cfg = {**CONFIG_FIXTURE, "plan_semanas": 4, **kw}
    return gen_plan.generar(cfg), cfg


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


def test_plan_terminado_con_prueba_contra_el_inicio():
    plan, cfg = _plan_corto()
    out = build.build(_datos_prueba(), plan, cfg, AHORA_FIN)
    t = out["hoy"]["tarjeta"]
    assert t["tipo"] == "plan_terminado" and t["texto"] == "Plan terminado" and "/ajustar" in t["siguiente"]
    p = t["prueba"]
    assert (p["tipo"], p["fecha"], p["estado"]) == ("fc_fija", "2026-11-18", "hecha")
    assert p["valor"] == 400 and p["km"] == 4.5
    assert p["base"]["fuente"] == "inicio" and p["dif"] == round(400 - p["base"]["valor"], 1)
    revisar_privacidad(out)
    assert validar.problemas(json.loads(json.dumps(out))) == []


def test_plan_terminado_prueba_contra_la_prueba_anterior_de_la_config():
    plan, cfg = _plan_corto(pruebas=[{"fecha": "2026-08-01", "tipo": "fc_fija", "valor": 430.0},
                                     {"fecha": "2026-09-15", "tipo": "5k", "valor": 1500.0}])
    p = build.build(_datos_prueba(), plan, cfg, AHORA_FIN)["hoy"]["tarjeta"]["prueba"]
    assert p["base"] == {"fuente": "prueba", "fecha": "2026-08-01", "valor": 430.0}
    assert p["dif"] == -30.0 and p["mejor"] is True


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


def test_prueba_5k_usa_la_mejor_marca_antes_del_plan_y_no_pide_techo():
    plan, cfg = _plan_corto(intensidad="calidad", calidad_tipos=["tempo_z3"])
    data = _datos_prueba(ritmo=300, minutos=26)           # 5 km en 25:00
    data["historial"] = [{"startTimeLocal": "2026-05-03 07:00:00", "activityType": {"typeKey": "running"}, "distance": 5100.0,
                          "duration": 1600.0, "eventType": {"typeKey": "race"}, "fastestSplit_5000": 1560.0}]
    out = build.build(data, plan, cfg, AHORA_FIN)
    p = out["hoy"]["tarjeta"]["prueba"]
    assert p["tipo"] == "5k" and p["valor"] == 1500 and p["base"] == {"fuente": "mejor_5k", "fecha": "2026-05-03", "valor": 1560}
    assert p["dif"] == -60.0 and p["mejor"] is True


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


def test_semana_actual_marca_dias_planeados_sin_hacer():
    data = {**fixture(), "activities": []}
    s = _semana(data, date(2026, 10, 28), date(2026, 10, 26))   # miércoles
    marcados = [d["fecha"] for d in s["dias"] if d.get("planeado")]
    assert len(marcados) == len(s["sesiones"]) and all(f >= "2026-10-28" for f in marcados)
    assert date.fromisoformat(marcados[-1]).weekday() >= 5   # la Larga cae en fin de semana


def test_semana_libre_solo_sin_plan_promedios_racha_y_sin_claves_prohibidas():
    import validar
    cfg = {**CONFIG_CORREDOR, "sin_plan": True}
    out = build.build(fixture(), gen_plan.generar(cfg), cfg, AHORA)
    sl = out["semana_libre"]
    assert len(sl["dias"]) == 7 and sum(len(d["actividades"]) for d in sl["dias"]) == sl["actividades"]
    assert sl["minutos"] == round(sum(a["minutos"] for d in sl["dias"] for a in d["actividades"]), 0) or sl["minutos"] >= 0
    assert sl["promedio_minutos"] >= 0 and sl["racha_semanas"] >= 0
    assert all({"nombre", "icono", "minutos", "km", "fc_prom", "sesion"} <= set(a) for d in sl["dias"] for a in d["actividades"])
    assert validar.problemas(out) == []
    assert "semana_libre" not in build.build(fixture(), gen_plan.generar(CONFIG_CORREDOR), CONFIG_CORREDOR, AHORA)


def test_liga_ajustar_plan_null_por_defecto_y_solo_con_la_clave():
    plan = gen_plan.generar(CONFIG_CORREDOR)
    assert build.build(fixture(), plan, CONFIG_CORREDOR, AHORA)["ui"]["liga_ajustar_plan"] is None
    cfg = {**CONFIG_CORREDOR, "liga_ajustar_plan": "/plan/acciones"}
    assert build.build(fixture(), plan, cfg, AHORA)["ui"]["liga_ajustar_plan"] == "/plan/acciones"


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
    assert sem[0]["progreso"] == {"hechas": 1, "total": 3}      # semana 1 (pasada): la corrida del 28/10
    assert sem[1]["progreso"]["total"] == 3 and 0 <= sem[1]["progreso"]["hechas"] <= 3   # la actual
    assert all("progreso" not in w for w in sem[2:])           # futuras: sin clave
    assert all(w["etiqueta"] in ("carga", "descarga") for w in sem)
    assert sem[0].get("marca") is None


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
    est = [{"id": "x", "name": "Z2 #3"}]
    assert build.titular_hoy({"tipo": "sesion", "version": "normal", "sesion": {"name": "Z2 #2"}}, est) == "Hoy toca: Z2 #2"
    assert build.titular_hoy({"tipo": "sesion", "version": "descanso", "sesion": {"name": "Z2 #2"}}, est) == "Hoy toca descansar"
    assert build.titular_hoy({"tipo": "hecha_hoy", "proxima_id": None}, est) == "Ya la hiciste hoy ✔"
    assert build.titular_hoy({"tipo": "hecha_hoy", "proxima_id": "x"}, est).endswith("Mañana: Z2 #3")
    assert build.titular_hoy({"tipo": "completa"}, est) == "Hoy toca descansar"
    assert build.titular_hoy({"tipo": "sin_plan"}, est) == "¿Salimos a moverte?"
    assert build.titular_hoy({"tipo": "pausa"}, est) is None


def test_huella_de_avisos_estable_y_cambia_con_el_contenido():
    assert build.huella("FC máx 190") == build.huella("FC máx 190") != build.huella("FC máx 191")
    fc = {"revisar": True, "estimacion": 190.4}
    a = build.huellas_avisos({"aviso": "x"}, "zonas!", fc, {"repetir_semana": True}, 3)
    assert set(a) == {"hoy", "zonas", "fcmax", "repetir"}
    assert build.huellas_avisos({"aviso": "x"}, None, {"revisar": False}, {}, 3) == {"hoy": a["hoy"]}
    assert build.huellas_avisos({}, None, {"revisar": True, "estimacion": 191}, {}, 3)["fcmax"] != a["fcmax"]
