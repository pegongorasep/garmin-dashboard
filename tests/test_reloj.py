import pytest
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
from dashboard import reloj_plan as rp

CONFIG = {"plan_start": "2026-11-09", "semanas_repetidas": [], "plan_semanas": 12}
PLAN = json.loads((ROOT / "plan" / "plan.json").read_text())


def run(m, z="Z2", nota="", kind="run"):
    return {"kind": kind, "minutes": m, "zone": z, "note": nota}


Z2 = {"id": "z2a", "name": "Z2 #1", "minutes": 20, "steps": [run(20, nota="suave")]}


def test_z2_simple():
    w = rp.entrenamiento(Z2, 3)
    assert w["workoutName"] == "S3 · Z2 #1 · 20'"
    assert w["description"] == "Plan del dashboard"
    assert w["sportType"]["sportTypeKey"] == "running"
    assert w["estimatedDurationInSecs"] == 1200
    (p,) = w["workoutSegments"][0]["workoutSteps"]
    assert p["stepType"]["stepTypeKey"] == "interval" and p["endConditionValue"] == 1200.0
    assert p["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone" and p["zoneNumber"] == 2
    assert p["description"] == "suave"


def test_nota_vacia_y_sin_zona():
    pasos = rp.pasos_garmin([run(5, nota=""), run(5, z=None)])
    assert "description" not in pasos[0]
    assert pasos[1]["targetType"]["workoutTargetTypeKey"] == "no.target" and "zoneNumber" not in pasos[1]


def test_variada_orden_y_zonas():
    s = {"name": "Fartlek", "minutes": 20, "steps": [run(10), run(3, "Z3", "fuerte"), run(2, "Z2"), run(5, "Z4")]}
    pasos = rp.entrenamiento(s, 5)["workoutSegments"][0]["workoutSteps"]
    assert [p["zoneNumber"] for p in pasos] == [2, 3, 2, 4]
    assert [p["stepOrder"] for p in pasos] == [1, 2, 3, 4]
    assert [p["endConditionValue"] for p in pasos] == [600.0, 180.0, 120.0, 300.0]


def test_caminatas_con_repeticion():
    s = {"name": "Z2 #1", "minutes": 15, "steps": [
        {"kind": "repeat", "times": 3, "steps": [run(4), run(1, "Z1", kind="walk")]}]}
    w = rp.entrenamiento(s, 1)
    assert w["estimatedDurationInSecs"] == 900
    (g,) = w["workoutSegments"][0]["workoutSteps"]
    assert g["type"] == "RepeatGroupDTO" and g["numberOfIterations"] == 3 and g["endConditionValue"] == 3.0
    trote, camina = g["workoutSteps"]
    assert trote["stepType"]["stepTypeKey"] == "interval" and camina["stepType"]["stepTypeKey"] == "recovery"
    assert camina["zoneNumber"] == 1 and (trote["stepOrder"], camina["stepOrder"]) == (2, 3)
    assert trote["childStepId"] == camina["childStepId"] == 1


def test_prueba_semana_12():
    sem = next(w for w in PLAN["weeks"] if w["n"] == 12)
    prueba = next(s for s in sem["sessions"] if s.get("tipo") == "prueba")
    w = rp.entrenamiento(prueba, 12)
    assert w["workoutName"].startswith("S12 · Prueba") and w["workoutName"].endswith("· 30'")
    assert w["estimatedDurationInSecs"] == 1800


def test_zona_rango_toma_la_primera():
    assert rp.numero_zona("Z1-Z2") == 1 and rp.numero_zona("Z5") == 5 and rp.numero_zona("") is None


def test_resumen_pasos():
    pasos = [run(10), {"kind": "repeat", "times": 2, "steps": [run(4), run(1, "Z1", kind="walk")]}]
    assert rp.resumen_pasos(pasos) == "10' Z2 · 2× (4' Z2 + 1' Z1 caminar)"


def test_semana_actual_con_repetida():
    assert rp.semana_actual(date(2026, 11, 24), CONFIG, PLAN) == 3
    assert rp.semana_actual(date(2026, 11, 24), {**CONFIG, "semanas_repetidas": [2]}, PLAN) == 2
    assert rp.semana_actual(date(2026, 11, 1), CONFIG, PLAN) is None


def test_clasificar():
    env = [{"id": 1, "sesion": "z2a"}, {"id": 2, "sesion": "z2b"}, {"id": 3, "sesion": "larga"}, {"id": 4, "sesion": "x"}]
    estado = [{"id": "z2a", "estado": "hecha"}, {"id": "z2b", "estado": "pendiente"}, {"id": "larga", "estado": "incompleta"}]
    borrar, pend = rp.clasificar(env, estado)
    assert [e["id"] for e in borrar] == [1] and [e["id"] for e in pend] == [2, 3, 4]
    assert rp.clasificar([], estado) == ([], [])


def test_reloj_acepta_plan_por_ruta():
    pytest.importorskip("garminconnect")   # reloj.py lo importa al inicio; en CI no está instalado
    import subprocess
    r = subprocess.run([sys.executable, str(ROOT / "reloj.py"), "semana", "--help"], capture_output=True, text=True)
    assert "--plan" in r.stdout
