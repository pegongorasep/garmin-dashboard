"""Red de seguridad de «Unificar U2»: el data.json de datos sintéticos no debe cambiar ni una clave ni un valor existente
(solo se admiten claves nuevas). Se regenera a propósito con `GOLDEN_REGENERAR=1`; nunca usa los datos reales de nadie."""
import json
import os
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from test_build import AHORA, CONFIG_FIXTURE, ROOT, build, fixture

GOLDEN = Path(__file__).parent / "fixtures" / "golden_semana.json"
TZ = ZoneInfo("America/Merida")


def datos_ricos():
    """El fixture + corridas y entrenos en cuatro semanas más (algunas sin trote/caminata, una con dos corridas el mismo día)."""
    d = fixture()
    base = d["activities"][1]
    for i, (dia, mins, km) in enumerate([("2026-10-21", 25, 3.0), ("2026-10-23", 40, 5.5), ("2026-10-24", 50, 7.0), ("2026-10-26", 30, 4.0),
                                         ("2026-10-30", 35, 4.8), ("2026-10-30", 20, 2.5), ("2026-11-04", 28, 3.9)]):
        d["activities"].append({**deepcopy(base), "activityId": 100 + i, "activityUUID": f"u{100 + i}", "startTimeLocal": f"{dia} 07:00:00",
                                "duration": mins * 60.0, "distance": km * 1000, "splitSummaries": []})
    d["activities"].append({**deepcopy(d["activities"][0]), "activityId": 200, "activityUUID": "u200", "startTimeLocal": "2026-10-27 18:00:00"})
    return d


def fixture_sin_zonas():
    d = fixture()
    d["hr_zones"] = [{"sport": "DEFAULT", "maxHeartRateUsed": 190, "restingHeartRateUsed": 64}]   # sin pisos de Garmin: el plan no pinta lpm
    return d


CASOS = {
    "plan_mie": (datos_ricos, {}, AHORA),
    "plan_dom": (datos_ricos, {}, datetime(2026, 11, 8, 20, 0, tzinfo=TZ)),
    "plan_lun_sig": (datos_ricos, {}, datetime(2026, 11, 9, 9, 0, tzinfo=TZ)),
    "plan_sin_corridas": (fixture, {}, datetime(2026, 11, 18, 9, 0, tzinfo=TZ)),
    "libre": (datos_ricos, {"sin_plan": True}, AHORA),
    "pausa_repetida": (datos_ricos, {"semanas_repetidas": [2], "pausas": ["2026-11-02"]}, datetime(2026, 11, 11, 9, 0, tzinfo=TZ)),
    "web_sin_zonas": (fixture_sin_zonas, {"garmin_conectado": False, "garmin_ultima_subida": None}, AHORA),
}


def generar(nombre):
    datos, extra, ahora = CASOS[nombre]
    plan = build.load(ROOT / "plan" / "plan.example.json")
    out = json.loads(json.dumps(build.build(datos(), plan, {**CONFIG_FIXTURE, **extra}, ahora)))
    out.pop("ui", None)   # depende del entorno (git remote, URL del repo): no es del golden
    return out


def diferencias(esperado, real, ruta=""):
    """Rutas donde `real` no conserva lo de `esperado` (claves nuevas en `real` se permiten; en listas, mismo largo)."""
    if isinstance(esperado, dict):
        if not isinstance(real, dict):
            return [ruta]
        return [x for k, v in esperado.items() for x in (diferencias(v, real[k], f"{ruta}/{k}") if k in real else [f"{ruta}/{k} falta"])]
    if isinstance(esperado, list):
        if not isinstance(real, list) or len(real) != len(esperado):
            return [ruta]
        return [x for i, (a, b) in enumerate(zip(esperado, real)) for x in diferencias(a, b, f"{ruta}[{i}]")]
    return [] if esperado == real else [f"{ruta}: {esperado!r} -> {real!r}"]


def test_regenerar():
    if os.environ.get("GOLDEN_REGENERAR"):
        GOLDEN.write_text(json.dumps({n: generar(n) for n in CASOS}, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")


@pytest.mark.parametrize("nombre", list(CASOS))
def test_golden(nombre):
    esperado = json.loads(GOLDEN.read_text(encoding="utf-8"))[nombre]
    assert diferencias(esperado, generar(nombre)) == []


def test_una_sola_fuente():
    from dashboard import metrics as m
    from dashboard import semanal
    out = generar("plan_lun_sig")
    con_progreso = [w for w in out["plan"]["semanas"] if "progreso" in w]
    assert con_progreso
    for w in con_progreso:
        s = next(s for s in out["semanas_hoy"] if s["n"] == w["n"])
        assert w["progreso"] == {"hechas": s["plan"]["hechas"], "total": s["plan"]["total"], "pct": s["plan"]["pct"]}
    mie = generar("plan_mie")
    hoy = next(s for s in mie["semanas_hoy"] if s["estado"] == "actual")
    assert mie["semana"]["plan_min"] == hoy["plan"]["plan_min"]
    assert (mie["semana"]["hechas"], mie["semana"]["sesiones_total"]) == (hoy["plan"]["hechas"], hoy["plan"]["total"])
    assert mie["semana"]["minutos"] == hoy["stats"]["minutos"]
    assert semanal.minutos_plan(None) is None and semanal.minutos_plan({"sessions": [{"minutes": 20}, {"minutes": 35}]}) == 55
    assert semanal.volumen({"minutos": 30, "km": 4.5}, "km") == 4.5 and semanal.volumen({"minutos": 30, "km": 4.5}) == 30
    assert semanal.conteo([{"estado": "hecha"}, {"estado": "incompleta"}, {"estado": "pendiente"}]) == {"hechas": 1, "incompletas": 1, "total": 3}
    est = [{"estado": "pendiente", "tipo": t} for t in ("facil", "facil", "calidad", "larga")]
    assert m.faltan(est) == [{"k": "facil", "n": 2}, {"k": "calidad"}, {"k": "larga"}]
    assert m.faltan([{"estado": "hecha", "tipo": "larga"}]) == [] and m.faltan_texto([{"estado": "hecha", "tipo": "larga"}]) == ""
    assert "2" in m.faltan_texto(est)
