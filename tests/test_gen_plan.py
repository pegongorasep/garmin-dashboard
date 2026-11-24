import json
import sys
from itertools import product
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "plan"))
import gen_plan as g  # noqa: E402
import metrics as m  # noqa: E402
from ajustes import cargar_config  # noqa: E402

BASE = cargar_config(ROOT / "tests" / "fixtures")


def cfg(**kw):
    return {**BASE, **kw}


def planes(**kw):
    p = g.generar(cfg(**kw))
    return p, {w["n"]: w for w in p["weeks"]}


def tiene(pasos, zona):
    return g.zonas_de(pasos) >= {zona}


def test_pedro_genera_su_plan_exacto():
    assert g.generar(BASE) == json.loads((ROOT / "plan" / "plan.json").read_text())


def test_cli_escribe_el_archivo(tmp_path, monkeypatch):
    out = tmp_path / "x" / "plan.json"
    monkeypatch.setattr(sys, "argv", ["gen_plan", "--config", str(ROOT / "tests" / "fixtures" / "config.yaml"), "--out", str(out)])
    g.main()
    assert json.loads(out.read_text())["weeks"][0]["sessions"][2]["minutes"] == 40


def test_novato_con_caminatas():
    p, w = planes(nivel="novato", intensidad="solo_z2", caminatas=True, base_min={"z2": 15, "larga": 20})
    assert len(p["weeks"]) == 12
    for sem in p["weeks"]:
        assert [s["id"] for s in sem["sessions"]] == ["z2a", "z2b", "larga"]
        for s in sem["sessions"]:
            assert not tiene(s["steps"], "Z3") and "siguiente escalón" in s["nota"]
            assert g.suma(s["steps"]) == s["minutes"]
    # bloque 1: 3'/1'; bloque 2: 5'/1'; bloque 3: 8'/1'
    for n, trote in ((1, 3), (5, 5), (9, 8)):
        rep = w[n]["sessions"][0]["steps"][0]
        assert rep["kind"] == "repeat" and [x["minutes"] for x in rep["steps"]] == [trote, 1]
        assert [x["kind"] for x in rep["steps"]] == ["run", "walk"]
    assert "trote 3'/camina 1'" in w[1]["focus"]
    assert w[1]["sessions"][0]["minutes"] == 15 and w[1]["sessions"][2]["minutes"] == 20


def test_caminatas_ajusta_la_ultima_repeticion():
    for minutos, bloque in product(range(10, 61), (1, 2, 3)):
        assert g.suma(g.pasos_caminatas(minutos, bloque)) == minutos


def test_intermedio_z2_poca_z3_tiene_picos_en_bloques_2_y_3():
    _, w = planes()
    assert not tiene(w[1]["sessions"][0]["steps"], "Z3") and tiene(w[5]["sessions"][0]["steps"], "Z3")
    assert not tiene(w[8]["sessions"][0]["steps"], "Z3")
    assert all(s["steps"][1].get("optional") for s in [w[5]["sessions"][0]])


def test_solo_z2_no_lleva_picos():
    p, _ = planes(intensidad="solo_z2")
    assert not any(tiene(s["steps"], "Z3") for wk in p["weeks"] for s in wk["sessions"])


def test_base_escalada_y_redondeada():
    _, w = planes(base_min={"z2": 30, "larga": 60})
    assert [s["minutes"] for s in w[1]["sessions"]] == [30, 30, 60]
    assert [s["minutes"] for s in w[3]["sessions"]] == [30, 40, 75]   # +5 z2b y +10 larga escalados x1.5 (37.5 -> 40)
    assert all(s["minutes"] % 5 == 0 for wk in g.generar(cfg(base_min={"z2": 25, "larga": 35}))["weeks"] for s in wk["sessions"])


@pytest.mark.parametrize("tipos", [["tempo_z3"], ["threshold", "intervalos"], ["tempo_z3", "threshold", "intervalos"]])
def test_corredor_con_calidad(tipos):
    p, w = planes(nivel="corredor", intensidad="calidad", calidad_tipos=tipos)
    cargas = [wk for wk in p["weeks"] if wk["kind"] == "carga"]
    for wk in p["weeks"]:
        tipos_s = [s["tipo"] for s in wk["sessions"]]
        assert tipos_s == (["z2", "calidad", "larga"] if wk["kind"] == "carga" else ["z2", "z2", "larga"])
    # rota entre los tipos elegidos solo en semanas de carga
    usados = [wk["sessions"][1]["calidad_tipo"] for wk in cargas]
    assert usados == [tipos[i % len(tipos)] for i in range(len(cargas))]
    for wk in cargas:
        c = wk["sessions"][1]
        assert c["steps"][0]["kind"] == "warmup" and c["steps"][0]["minutes"] == 10 and c["steps"][0]["zone"] == "Z2"
        assert c["steps"][-1]["kind"] == "cooldown" and c["steps"][-1]["minutes"] == 5
        trabajo = c["steps"][1]["steps"][0]
        assert trabajo["zone"] == c["objetivo"]["zona"] and c["objetivo"]["minutos"] == c["steps"][1]["times"] * trabajo["minutes"]
        assert not tiene(c["easy"]["steps"], c["objetivo"]["zona"])


def test_calidad_progresion_por_bloque():
    _, w = planes(intensidad="calidad", calidad_tipos=["tempo_z3"])
    def bloque(n):
        c = w[n]["sessions"][1]["steps"][1]
        return c["times"], c["steps"][0]["minutes"], c["steps"][1]["minutes"]
    assert [bloque(1), bloque(5), bloque(9)] == [(2, 10, 3), (2, 12, 3), (2, 15, 3)]
    _, w = planes(intensidad="calidad", calidad_tipos=["threshold"])
    assert [bloque(n) for n in (1, 5, 9)] == [(4, 5, 2), (5, 5, 2), (4, 6, 2)]
    _, w = planes(intensidad="calidad", calidad_tipos=["intervalos"])
    assert [bloque(n) for n in (1, 5, 9)] == [(6, 2, 2), (8, 2, 2), (6, 3, 2)]


def test_corredor_solo_z2():
    p, _ = planes(nivel="corredor", intensidad="solo_z2")
    assert not any(s["tipo"] == "calidad" or tiene(s["steps"], "Z3") for wk in p["weeks"] for s in wk["sessions"])


def test_semanas_distintas_de_12():
    p, _ = planes(plan_semanas=8)
    assert len(p["weeks"]) == 8
    p, w = planes(plan_semanas=16)
    assert len(p["weeks"]) == 16 and w[13]["kind"] == "carga" and w[16]["kind"] == "descarga"
    assert [s["minutes"] for s in w[13]["sessions"]][2] == [s["minutes"] for s in w[9]["sessions"]][2]


def test_verificar_detecta_errores():
    p = g.generar(BASE)
    p["weeks"][0]["sessions"][0]["minutes"] += 5
    with pytest.raises(AssertionError):
        g.verificar(p)
    p = g.generar(cfg(intensidad="calidad", calidad_tipos=["tempo_z3"]))
    p["weeks"][3]["sessions"][1] = g.sesion_calidad("tempo_z3", 1)
    with pytest.raises(AssertionError):
        g.verificar(p)


# --- backend de la calidad ---

def corrida(fecha, minutos, z=(0, 0, 0, 0, 0)):
    return {"fecha": fecha, "minutos": minutos, "luz": "verde", "zonas": {f"Z{i + 1}": v for i, v in enumerate(z)}}


def test_assign_calidad_primera_corrida_con_50_pct_en_z3_o_mas():
    _, w = planes(intensidad="calidad", calidad_tipos=["tempo_z3"])
    semana = w[1]            # objetivo 20' de Z3
    runs = [corrida("2026-11-10", 30, (5, 20, 5, 0, 0)),      # solo 5' en Z3: no es calidad
            corrida("2026-11-12", 41, (10, 20, 8, 3, 0)),     # 11' >= 10: calidad
            corrida("2026-11-14", 45)]
    est = {e["id"]: e for e in m.assign_sessions(semana, runs, BASE)}
    assert est["calidad"]["fecha"] == "2026-11-12" and est["z2a"]["fecha"] == "2026-11-10"
    assert est["larga"]["fecha"] == "2026-11-14"
    sin = {e["id"]: e for e in m.assign_sessions(semana, runs[:1], BASE)}
    assert sin["calidad"]["estado"] == "pendiente" and sin["z2a"]["fecha"] == "2026-11-10"


def activ(z):
    return {"activityType": {"typeKey": "running"}, "duration": sum(z) * 60,
            **{f"hrTimeInZone_{i + 1}": v * 60 for i, v in enumerate(z)}}


@pytest.mark.parametrize("tipo,z,ok,arriba", [
    ("tempo_z3", (10, 15, 16, 0, 0), True, False),      # 16 de 20 >= 70 %
    ("tempo_z3", (10, 15, 12, 0, 0), False, False),
    ("tempo_z3", (10, 5, 14, 8, 0), True, True),        # 8' en Z4: pasó de la zona
    ("threshold", (10, 15, 4, 17, 0), True, False),     # 17 de 20
    ("threshold", (10, 15, 4, 12, 3), False, False),
    ("intervalos", (10, 15, 2, 9, 4), True, True),      # 9 de 12 y 4' en Z5 (> 25 % de 12)
])
def test_run_check_calidad(tipo, z, ok, arriba):
    _, w = planes(intensidad="calidad", calidad_tipos=[tipo])
    ses = w[1]["sessions"][1]
    r = m.run_check(activ(z), ses, BASE)["calidad"]
    assert r["ok"] is ok and r["mucho_arriba"] is arriba
    assert r["zona"] == ses["objetivo"]["zona"] and r["objetivo_min"] == ses["objetivo"]["minutos"]
    assert "calidad" not in m.run_check(activ(z), w[1]["sessions"][0], BASE)
