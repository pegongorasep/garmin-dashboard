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
AHORA = datetime(2026, 11, 4, 12, 0, tzinfo=ZoneInfo("America/Merida"))  # miércoles, semana 2

PROHIBIDAS = ["activityId", "activityName", "ownerDisplayName", "ownerFullName", "userProfilePk",
              "userProfilePK", "userProfileId", "uuid", "activityUUID", "displayName", "locationName",
              "profileImageUrl", "ownerProfileImageUrlSmall", "fullName", "emailAddress",
              "startLatitude", "startLongitude"]
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
                "hrTimeInZone_4": 0, "hrTimeInZone_5": 0, **kw}
    dias = [f"2026-10-{d:02d}" for d in range(20, 32)] + ["2026-11-01", "2026-11-02", "2026-11-03", "2026-11-04"]
    return {
        "daily_summaries": [{"calendarDate": d, "displayName": "Persona Inventada",
                             "heartRate": {"restingValue": 60}} for d in dias],
        "sleep": [{"calendarDate": d, "sleepTimeSeconds": 25000, "userProfilePK": 99} for d in dias],
        "hrv": [{"calendarDate": d, "lastNightAvg": 34, "status": "BALANCED",
                 "baseline": {"lowUpper": 28, "balancedLow": 30, "balancedUpper": 38}} for d in dias],
        "activities": [act(1, "2026-11-02", "hiit"), act(2, "2026-11-03", "running"),
                       act(3, "2026-10-28", "running"), act(4, "2026-11-03", "hiit")],
        "details": {"1": {"rpe": 6.0, "feel": 50}, "2": {"rpe": 4.0, "feel": 50}, "3": {"rpe": None, "feel": None}},
        "hr_zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 203, "restingHeartRateUsed": 64}],
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
    return build.build(fixture(), plan, CONFIG, AHORA)


def test_forma_y_json_valido(salida):
    json.dumps(salida)
    for k in ("generado", "zonas", "aviso_zonas", "hoy", "semana", "plan", "tendencias", "corridas", "fc_max"):
        assert k in salida
    assert salida["plan"]["semana_actual"] == 2
    assert len(salida["semana"]["dias"]) == 7 and len(salida["zonas"]) == 5
    assert len(salida["tendencias"]["dias"]) == 84 and len(salida["tendencias"]["semanas"]) == 12
    assert salida["generado"].startswith("2026-11-04T12:00")
    assert salida["datos_al"].startswith("2026-11-04T11:00")  # 17:00 UTC = 11:00 Mérida


def test_plan_convertido_a_lpm(salida):
    pasos = salida["plan"]["semanas"][0]["sessions"][0]["steps"]
    assert pasos[0]["lpm"] == [125, 138]          # Z1 con reposo 60
    assert pasos[1]["steps"][0]["lpm"] == [138, 151]  # Z2
    assert pasos[2]["zone"] == "Z1-Z2" and pasos[2]["lpm"] == [125, 151]


def test_corrida_asignada_a_sesion(salida):
    est = salida["plan"]["estado_sesiones"]
    assert [e["estado"] for e in est] == ["hecha", "pendiente"]
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
