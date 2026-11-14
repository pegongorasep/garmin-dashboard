import json
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import build  # noqa: E402

CONFIG = json.loads((ROOT / "dashboard" / "config.json").read_text())
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

    def recorrer(o):
        if isinstance(o, dict):
            for k, v in o.items():
                assert k not in PROHIBIDAS, f"clave prohibida: {k}"
                recorrer(v)
        elif isinstance(o, list):
            for v in o:
                recorrer(v)
        elif isinstance(o, str):
            assert not o.startswith("http"), f"URL en el JSON: {o}"
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
    assert fuera["hoy"]["tarjeta"]["tipo"] in ("sin_plan", "crossfit")
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
    assert salida["hoy"]["tarjeta"]["tipo"] in ("sesion", "hecha_hoy", "crossfit")


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
    out = build.build(data, plan, {**CONFIG_FIXTURE, "crossfit_days": []}, AHORA)
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
