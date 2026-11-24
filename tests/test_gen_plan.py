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
    for sem in p["weeks"][:-1]:
        assert [s["id"] for s in sem["sessions"]] == ["z2a", "z2b", "larga"]
        for s in sem["sessions"]:
            assert not tiene(s["steps"], "Z3") and "siguiente escalón" in s["nota"]
            assert g.suma(s["steps"]) == s["minutes"]
    assert [s["id"] for s in p["weeks"][-1]["sessions"]] == ["z2a", "z2b", "prueba"]
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
        larga = "prueba" if wk["n"] == 12 else "larga"
        assert tipos_s == (["z2", "calidad", larga] if wk["kind"] == "carga" else ["z2", "z2", larga])
    # rota entre los tipos elegidos solo en semanas de carga
    usados = [wk["sessions"][1]["calidad_tipo"] for wk in cargas]
    assert usados == [tipos[i % len(tipos)] for i in range(len(cargas))]
    for wk in cargas:
        c = wk["sessions"][1]
        # 10' Z2 como tramo normal; sin calentamiento ni enfriamiento (van aparte y no cuentan)
        assert c["steps"][0]["kind"] == "run" and c["steps"][0]["minutes"] == 10 and c["steps"][0]["zone"] == "Z2"
        assert not {p["kind"] for p in c["steps"]} & {"warmup", "cooldown"}
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


def mz(z):
    """Minutos por zona Z0..Z5 a partir de (Z1..Z5) en minutos."""
    return {"Z0": 0.0, **{f"Z{i + 1}": float(v) for i, v in enumerate(z)}}


@pytest.mark.parametrize("tipo,z,ok_z3,ok_z2", [
    ("tempo_z3", (10, 15, 16, 0, 0), True, True),     # Z3 o más: 16 de 20 (80 %) ; Z2 o más: 31 de 36
    ("tempo_z3", (10, 15, 12, 0, 0), False, True),    # 12 de 20 = 60 %
    ("tempo_z3", (10, 5, 14, 8, 0), True, False),     # lo de Z4 cuenta para Z3 (22 de 20), pero Z2 o más: 27 de 36 = 75 % -> ok
])
def test_run_check_plan_vs_real_calidad(tipo, z, ok_z3, ok_z2):
    _, w = planes(intensidad="calidad", calidad_tipos=[tipo])
    ses = w[1]["sessions"][1]
    r = m.run_check(activ(z), ses, BASE, mz(z))["plan_vs_real"]
    assert [x["zona"] for x in r] == ["Z3", "Z2"]                       # de la más alta a la más baja
    assert (r[0]["plan_min"], r[1]["plan_min"]) == (20, 36)
    assert r[0]["ok"] is ok_z3
    assert r[1]["ok"] is (ok_z2 or sum(z[1:]) >= 0.7 * 36)


def test_plan_vs_real_los_minutos_altos_cuentan_para_la_zona_de_abajo():
    pasos = [{"kind": "run", "minutes": 10, "zone": "Z2", "note": ""},
             {"kind": "repeat", "times": 2, "steps": [{"kind": "run", "minutes": 2, "zone": "Z4", "note": ""},
                                                       {"kind": "run", "minutes": 2, "zone": "Z1", "note": ""}]}]
    r = m.plan_vs_real(pasos, {"Z0": 0, "Z1": 4, "Z2": 4, "Z3": 0, "Z4": 2, "Z5": 0})
    assert r == [{"zona": "Z4", "plan_min": 4, "hecho_min": 2.0, "pct": 50, "ok": False, "arriba_min": 0, "mucho_arriba": False},
                 {"zona": "Z2", "plan_min": 14, "hecho_min": 6.0, "pct": 43, "ok": False}]
    todo_mas_arriba = m.plan_vs_real(pasos, {"Z0": 0, "Z1": 0, "Z2": 0, "Z3": 0, "Z4": 14, "Z5": 0})
    assert [x["ok"] for x in todo_mas_arriba] == [True, True] and todo_mas_arriba[1]["pct"] == 100


def test_plan_vs_real_umbral_del_70_y_una_sola_zona():
    pasos = [{"kind": "run", "minutes": 20, "zone": "Z2", "note": ""}]
    assert m.plan_vs_real(pasos, mz((0, 14, 0, 0, 0)))[0]["ok"] is True       # 14 de 20 = 70 %
    r = m.plan_vs_real(pasos, mz((0, 13.9, 0, 0, 0)))
    assert len(r) == 1 and r[0]["ok"] is False and r[0]["pct"] == 70
    assert m.plan_vs_real([{"kind": "run", "minutes": 5, "zone": "Z1", "note": ""}], mz((5, 0, 0, 0, 0))) == []   # Z1 y Z0 no se evalúan


def test_plan_vs_real_ignora_pasos_opcionales_y_zona_unica():
    pasos = [{"kind": "run", "minutes": 10, "zone": "Z1-Z2", "note": ""},          # planes viejos: Z1-Z2 = Z2
             {"kind": "run", "minutes": 1, "zone": "Z3", "note": "opcional", "optional": True}]
    r = m.plan_vs_real(pasos, mz((0, 10, 1, 0, 0)))
    assert [(x["zona"], x["plan_min"]) for x in r] == [("Z2", 10)] and r[0]["hecho_min"] == 11.0


def test_run_check_con_suave_compara_contra_la_version_suave():
    _, w = planes(intensidad="calidad", calidad_tipos=["tempo_z3"])
    ses = w[1]["sessions"][1]
    r = m.run_check(activ((0, 20, 0, 0, 0)), ses, BASE, mz((0, 20, 0, 0, 0)), suave=True)["plan_vs_real"]
    assert [x["zona"] for x in r] == ["Z2"] and r[0]["ok"] is True
    assert "plan_vs_real" not in m.run_check(activ((0, 20, 0, 0, 0)), ses, BASE)       # sin minutos por zona
    assert "plan_vs_real" not in m.run_check(activ((0, 20, 0, 0, 0)), None, BASE, mz((0, 20, 0, 0, 0)))   # sin sesión


# --- v4.2 F2: corrida variada, tipos y siluetas ---

NIVELES_PRUEBA = {"novato": {"z2": 15, "larga": 20}, "intermedio": {"z2": 20, "larga": 40}, "corredor": {"z2": 30, "larga": 60}}


def _z3(pasos):
    return g.minutos_en(pasos, {"Z3", "Z4", "Z5"})


def test_todas_las_combinaciones_generan_y_pasan_verificar():
    for (nivel, base), inten, cam, var in product(NIVELES_PRUEBA.items(), ("solo_z2", "z2_poca_z3", "calidad"),
                                                  (False, True), (False, True)):
        tipos = ["tempo_z3"] if inten == "calidad" and not var else []
        p = g.generar(cfg(nivel=nivel, base_min=base, intensidad=inten, caminatas=cam, variada=var, calidad_tipos=tipos))
        assert len(p["weeks"]) == 12


def test_variada_apagada_no_cambia_nada():
    sin = g.generar(cfg())
    con_false = g.generar(cfg(variada=False))
    assert sin == con_false == json.loads((ROOT / "plan" / "plan.json").read_text())
    assert not any(s["tipo"] == "variada" for w in sin["weeks"] for s in w["sessions"])


def test_variada_estructura_de_la_semana():
    p, w = planes(intensidad="z2_poca_z3", variada=True)
    carga = w[2]["sessions"]
    assert [s["id"] for s in carga] == ["z2a", "z2b", "larga"] and carga[1]["tipo"] == "variada"
    assert carga[1]["name"].startswith("Variada · ") and carga[1]["variada_tipo"]
    assert not _z3(carga[0]["steps"]) and not _z3(carga[2]["steps"])      # Z2 #1 sin picos aunque sea z2_poca_z3
    assert carga[1]["minutes"] == g.escala(g.DELTA_Z2B, 20, g.REF_Z2, 0, 1)   # mismos minutos que Z2 #2
    for n in (4, 8, 12):                                                   # descarga: todo continuo
        assert [s["tipo"] for s in w[n]["sessions"]] == ["z2", "z2", "prueba" if n == 12 else "larga"]


def test_variada_rotacion_por_intensidad():
    def tipos(inten):
        p = g.generar(cfg(intensidad=inten, variada=True))
        return [s["variada_tipo"] for wk in p["weeks"] for s in wk["sessions"] if s["tipo"] == "variada"]
    assert tipos("solo_z2") == ["ascendente", "densidad", "rotativo", "descendente", "ascendente", "densidad",
                                "rotativo", "descendente", "ascendente"]
    z3 = tipos("z2_poca_z3")
    assert z3[0] == "espiga" and z3[2] == "ascendente" and z3[3] == "rotativo" and z3[4] == "descendente"
    assert set(z3) <= {"espiga", "piramide", "ascendente", "rotativo", "descendente", "densidad"}
    assert all(a != b for a, b in zip(z3, z3[1:]))      # nunca la misma dos semanas seguidas


def test_variada_solo_z2_sin_z3_y_z2_poca_z3_con_tope():
    p = g.generar(cfg(intensidad="solo_z2", variada=True, caminatas=False))
    assert all(not _z3(s["steps"]) for wk in p["weeks"] for s in wk["sessions"])
    for base in ({"z2": 20, "larga": 40}, {"z2": 35, "larga": 70}, {"z2": 10, "larga": 20}):
        p = g.generar(cfg(intensidad="z2_poca_z3", variada=True, caminatas=False, base_min=base))
        for wk in p["weeks"]:
            for s in wk["sessions"]:
                if s["tipo"] == "variada":
                    assert 0 < _z3(s["steps"]) <= min(6, s["minutes"] * 0.2), (wk["n"], s["name"], s["minutes"])
                    assert not g.minutos_en(s["steps"], {"Z4", "Z5"})
                    # sin calentamiento ni enfriamiento propios: van aparte y no cuentan
                    assert not {x.get("note") for x in s["steps"]} & {"calentamiento", "enfriamiento"}
                    assert not {x["kind"] for x in s["steps"]} & {"warmup", "cooldown"}


def test_variada_con_caminatas_z1_son_caminata_y_el_resto_trote():
    p = g.generar(cfg(intensidad="z2_poca_z3", variada=True, caminatas=True, base_min={"z2": 20, "larga": 40}))
    def planos(pasos):
        for x in pasos:
            yield from planos(x["steps"]) if x["kind"] == "repeat" else [x]
    for wk in p["weeks"]:
        for s in wk["sessions"]:
            if s["tipo"] == "variada":
                for x in planos(s["steps"]):
                    assert (x["kind"] == "walk") == (x["zone"] == "Z1"), (wk["n"], x)


def test_variada_pasos_enteros_suman_y_tienen_zona_exacta():
    for tipo, M in product(["ascendente", "descendente", "espiga", "piramide", "densidad", "rotativo"], range(10, 61)):
        for z3 in (False, True):
            if z3 is False and tipo in ("espiga", "piramide"):
                continue
            pasos = g.pasos_variada(tipo, M, False, z3)
            assert g.suma(pasos) == M, (tipo, M, z3)
            assert g.zonas_de(pasos) <= ({"Z1", "Z2", "Z3"} if z3 else {"Z1", "Z2"}), (tipo, M)
            assert all(isinstance(x["minutes"], int) and x["minutes"] >= 1 for x in planos_planos(pasos))
            if z3:
                assert _z3(pasos) <= g.tope_z3(M), (tipo, M)


def planos_planos(pasos):
    for x in pasos:
        yield from planos_planos(x["steps"]) if x["kind"] == "repeat" else [x]


def test_calidad_variada_usa_los_5_y_progresivo_fartlek_sin_variada():
    p = g.generar(cfg(intensidad="calidad", variada=True, calidad_tipos=[]))
    tipos = [s["calidad_tipo"] for wk in p["weeks"] for s in wk["sessions"] if s["tipo"] == "calidad"]
    assert tipos[:5] == ["tempo_z3", "threshold", "intervalos", "progresivo", "fartlek"]
    assert not any(s["tipo"] == "variada" for wk in p["weeks"] for s in wk["sessions"])
    p = g.generar(cfg(intensidad="calidad", calidad_tipos=["progresivo", "fartlek"]))
    cal = [s for wk in p["weeks"] for s in wk["sessions"] if s["tipo"] == "calidad"]
    assert [s["calidad_tipo"] for s in cal[:2]] == ["progresivo", "fartlek"]
    for s in cal:
        assert s["objetivo"]["zona"] == "Z3" and g.minutos_en(s["steps"], {"Z3"}) == s["objetivo"]["minutos"]


def test_descarga_sin_variada_ni_calidad_y_verificar_lo_vigila():
    p = g.generar(cfg(intensidad="calidad", variada=True, calidad_tipos=[]))
    mala = json.loads(json.dumps(p))
    mala["weeks"][3]["sessions"][1]["tipo"] = "variada"
    with pytest.raises(AssertionError):
        g.verificar(mala)
    solo = g.generar(cfg(intensidad="solo_z2", variada=True))
    solo["weeks"][0]["sessions"][0]["steps"][0]["zone"] = "Z3"
    with pytest.raises(AssertionError):
        g.verificar(solo, cfg(intensidad="solo_z2"))


def test_variada_empieza_en_z1_a_lo_mas_2_minutos():
    """El calentamiento va aparte: el cuerpo puede empezar en Z1 como escalón (1–2'), no como calentamiento."""
    for tipo, M in product(["ascendente", "descendente", "espiga", "piramide", "densidad", "rotativo"], range(10, 61)):
        for z3 in (False, True):
            if z3 is False and tipo in ("espiga", "piramide"):
                continue
            m, z = g.tramos_variada(tipo, M, z3, g.tope_z3(M))[0]
            assert z != "Z1" or m <= g.Z1_INICIO_MAX, (tipo, M, z3)


# --- v4.3 F6: prueba de la última semana ---

@pytest.mark.parametrize("kw,prueba,zona", [
    ({"intensidad": "solo_z2"}, "fc_fija", "Z2"), ({"intensidad": "z2_poca_z3"}, "fc_fija", "Z2"),
    ({"intensidad": "solo_z2", "caminatas": True}, "trote_continuo", "Z2"),
    ({"intensidad": "calidad", "calidad_tipos": ["tempo_z3"]}, "5k", "Z4")])
def test_la_larga_de_la_ultima_semana_es_la_prueba(kw, prueba, zona):
    p, w = planes(**kw)
    ult = w[12]["sessions"][-1]
    assert (ult["id"], ult["tipo"], ult["prueba"]) == ("prueba", "prueba", prueba)
    assert [x["zone"] for x in ult["steps"]] == [zona] and g.suma(ult["steps"]) == ult["minutes"]
    assert ult["easy"]["minutes"] == ult["minutes"] and ult["easy"]["steps"] == ult["steps"]     # no hay versión suave
    assert "prueba" in w[12]["focus"].lower()
    assert all(s["tipo"] != "prueba" for n, wk in w.items() if n != 12 for s in wk["sessions"])
    g.verificar(p, cfg(**kw))


def test_prueba_en_otras_duraciones_del_plan():
    p = g.generar(cfg(plan_semanas=8))
    assert p["weeks"][-1]["sessions"][-1]["id"] == "prueba" and p["weeks"][-2]["sessions"][-1]["id"] == "larga"


def test_solo_cambia_la_larga_de_la_semana_12():
    p, antes = planes(intensidad="z2_poca_z3"), None
    sin = g.generar(cfg(intensidad="z2_poca_z3", plan_semanas=13))["weeks"][:11]
    assert sin == p[0]["weeks"][:11]
