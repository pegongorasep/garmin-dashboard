"""Motor v6 (plan/motor_v6.py): reglas del motor, personas del simulador, ajuste semanal y compatibilidad con el resto de la app
(entrenamientos del reloj en simulación, asignación de sesiones, semana de carrera con 2–5 sesiones)."""
import copy
import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "plan"))
import build  # noqa: E402
import gen_plan  # noqa: E402
import metrics as m  # noqa: E402
import motor_v6 as v6  # noqa: E402
import reloj_plan as rp  # noqa: E402
import simulador as sim  # noqa: E402
from ajustes import cargar_config  # noqa: E402

LUNES = "2026-11-30"
EV_BASE = {"semanas_consistentes": 8, "trote_continuo_min": 35, "minutos_sem_prom": 95, "sesion_max_30d": 35, "dias_intensos": []}


def entrada(**kw):
    return {"nivel": "base", "dias": 3, "inicio": LUNES, "inicio_minutos": 100, "evidencia": dict(EV_BASE), "edad": 35, **kw}


def minutos(w):
    return sum(s["minutes"] for s in w["sessions"])


def pasos_planos(pasos):
    for p in pasos:
        if p["kind"] == "repeat":
            for _ in range(p["times"]):
                yield from pasos_planos(p["steps"])
        else:
            yield p


def z3(s):
    return sum(p["minutes"] for p in pasos_planos(s["steps"]) if p["zone"] in ("Z3", "Z4", "Z5"))


# --- el simulador con v6: la matriz de reglas ---

def test_v6_cumple_todas_las_reglas_en_las_8_personas():
    """Sin excepciones: ninguna regla falla (✓ o «no aplica») con el ajuste semanal."""
    resultados = sim.simular_todas("v6")
    assert len(resultados) == 8
    for r in resultados:
        assert [x["clave"] for x in r["reglas"] if x["ok"] is False] == [], r["persona"]["id"]
        assert r["motor"] == "v6"


@pytest.mark.parametrize("dias", [2, 3, 4, 5])
@pytest.mark.parametrize("adherencia", [1.0, 0.8, 0.6])
def test_v6_reglas_con_2_a_5_dias_y_adherencias(dias, adherencia):
    """Con otros números de sesiones por semana y con adherencia baja las reglas siguen cumpliéndose (la de la carrera con adherencia baja
    no aplica: el plan se encoge solo con el ajuste y la «semana de carrera» ya no es un taper contra el pico)."""
    for p in sim.cargar_personas():
        q = {**p, "dias_semana": dias, "adherencia": {"base": adherencia, "huecos": p["adherencia"]["huecos"]}}
        r = sim.simular(q, "v6")
        mal = [x["clave"] for x in r["reglas"] if x["ok"] is False and not (x["clave"] == "taper" and adherencia < 1)]
        assert mal == [], (p["id"], dias, adherencia, mal)


def test_v6_es_determinista_y_esta_registrado():
    assert "v6" in sim.MOTORES and callable(sim.motor("v6"))
    assert sim.simular_todas("v6") == sim.simular_todas("v6")


def test_sin_ajuste_el_plan_v6_no_cumple_sube_real_con_adherencia_baja():
    """El ajuste es lo que hace cumplir `sube_real_10`: el plan crudo de una persona que cumple 60 % no la cumple."""
    p = sim.persona_por_id("cumple_60")
    crudo = sim.analizar(p, sim._motor_v6(p), "v6")
    assert next(x for x in crudo["reglas"] if x["clave"] == "sube_real_10")["ok"] is False
    assert next(x for x in sim.simular(p, "v6")["reglas"] if x["clave"] == "sube_real_10")["ok"] is True


# --- el plan: esquema y forma ---

def test_esquema_como_gen_plan_mas_meta_y_dia():
    plan = v6.generar_v6(entrada())
    assert set(plan) == {"start", "weeks", "meta"} and plan["meta"]["motor"] == "v6" and v6.es_v6(plan)
    assert not v6.es_v6({"start": LUNES, "weeks": []})
    for w in plan["weeks"]:
        assert {"n", "block", "kind", "focus", "sessions"} <= set(w)
        for s in w["sessions"]:
            assert {"id", "tipo", "name", "minutes", "steps", "easy", "dia"} <= set(s)
            assert gen_plan.suma(s["steps"]) == s["minutes"] and gen_plan.suma(s["easy"]["steps"]) == s["easy"]["minutes"]
    gen_plan.verificar(plan, {"intensidad": None})
    v6.verificar(plan)


def test_gen_plan_actual_sigue_igual_y_sin_meta():
    plan = gen_plan.generar(cargar_config(ROOT / "tests" / "fixtures"))
    assert "meta" not in plan and not v6.es_v6(plan)


@pytest.mark.parametrize("nivel", ["empezando", "base", "corredor"])
@pytest.mark.parametrize("dias", [2, 3, 4, 5])
def test_cuantas_sesiones_por_semana(nivel, dias):
    ev = {**EV_BASE, "trote_continuo_min": 0 if nivel == "empezando" else 60, "semanas_consistentes": 8, "minutos_sem_prom": 0 if nivel == "empezando" else 170}
    plan = v6.generar_v6(entrada(nivel=nivel, dias=dias, evidencia=ev, inicio_minutos=60 if nivel == "empezando" else 170))
    esperados = min(dias, 3) if nivel == "empezando" else dias
    assert {len(w["sessions"]) for w in plan["weeks"]} == {esperados}
    assert plan["meta"]["dias"] == esperados
    if dias > esperados:
        assert [a["clave"] for a in plan["meta"]["avisos"]] == ["dias_limitados"]


def test_base_sin_calidad_max_4_dias():
    plan = v6.generar_v6(entrada(dias=5, evidencia={**EV_BASE, "semanas_consistentes": 2}))
    assert plan["meta"]["dias"] == 4 and not plan["meta"]["calidad"]


def test_dias_unicos_y_ids_unicos():
    for dias in (2, 3, 4, 5):
        for w in v6.generar_v6(entrada(nivel="corredor", dias=dias, inicio_minutos=200))["weeks"]:
            assert len({s["dia"] for s in w["sessions"]}) == len(w["sessions"]) and len({s["id"] for s in w["sessions"]}) == len(w["sessions"])


# --- reglas sueltas ---

def test_semana_1_viene_de_inicio_minutos_y_sube_max_10():
    plan = v6.generar_v6(entrada(inicio_minutos=100))
    tot = [minutos(w) for w in plan["weeks"]]
    assert tot[0] == 100
    cargas = [(w["n"], minutos(w)) for w in plan["weeks"] if w["kind"] == "carga"]
    for (_, a), (_, b) in zip(cargas, cargas[1:]):
        assert b <= a * 1.10 + 1e-9


def test_tras_descarga_vuelve_al_volumen_de_antes_no_mas():
    plan = v6.generar_v6(entrada())
    tot = {w["n"]: minutos(w) for w in plan["weeks"]}
    kinds = {w["n"]: w["kind"] for w in plan["weeks"]}
    assert kinds[4] == "descarga" and tot[4] < tot[3] * 0.75 and tot[5] == tot[3]


def test_descarga_3_a_1_y_2_a_1():
    normal = [w["kind"] for w in v6.generar_v6(entrada())["weeks"]]
    assert [i + 1 for i, k in enumerate(normal) if k == "descarga"] == [4, 8, 12]
    mayor = [w["kind"] for w in v6.generar_v6(entrada(edad=52))["weeks"]]
    assert [i + 1 for i, k in enumerate(mayor) if k == "descarga"] == [3, 6, 9, 12]
    intensos = [w["kind"] for w in v6.generar_v6(entrada(dias_intensos=[0, 2, 4]))["weeks"]]
    assert [i + 1 for i, k in enumerate(intensos) if k == "descarga"] == [3, 6, 9, 12]


def test_larga_tope_y_sesion_110():
    for dias in (2, 3, 4, 5):
        plan = v6.generar_v6(entrada(nivel="corredor", dias=dias, inicio_minutos=190, evidencia={**EV_BASE, "sesion_max_30d": 65, "trote_continuo_min": 65}))
        previas = [65]
        for w in plan["weeks"]:
            tot, larga = minutos(w), next(s for s in w["sessions"] if s["tipo"] == "larga")
            assert larga["minutes"] <= v6.UMBRALES["larga_tope_pct"][dias] * tot + 1e-9
            assert max(s["minutes"] for s in w["sessions"]) <= max(previas[-4:]) * 1.1 + 1e-9
            previas.append(max(s["minutes"] for s in w["sessions"]))


def test_escalera_empezando_de_1_2_a_continuo():
    plan = v6.generar_v6(entrada(nivel="empezando", inicio_minutos=60, evidencia={"trote_continuo_min": 0, "sesion_max_30d": 0}))
    esc = [v6._escalon_de_pasos(w["sessions"][0]["steps"]) for w in plan["weeks"]]
    assert esc[0] == (1, 2) and esc[1] == (1, 1) and esc[2] == (2, 1)      # 1/2 → 1/1 → 2/1 una por semana (3 días)
    assert esc[3] == esc[2] and plan["weeks"][3]["kind"] == "descarga"     # la descarga no sube de escalón
    assert esc[-1] is None                                                 # al final, trote continuo
    assert all(z3(s) == 0 for w in plan["weeks"] for s in w["sessions"])


def test_escalera_con_2_dias_sube_cada_2_semanas():
    plan = v6.generar_v6(entrada(nivel="empezando", dias=2, inicio_minutos=40, evidencia={"trote_continuo_min": 0}))
    esc = [v6._escalon_de_pasos(w["sessions"][0]["steps"]) for w in plan["weeks"][:4]]
    assert esc[0] == esc[1] == (1, 2) and esc[2] == (1, 1)


def test_escalon_de_entrada_segun_trote_continuo():
    assert [v6.escalon_de_entrada(c) for c in (0, 2, 4, 6, 10, 15, 20, 30)] == [0, 1, 2, 3, 4, 5, 6, 7]


def test_calidad_solo_con_base_y_en_orden():
    sin = v6.generar_v6(entrada(evidencia={**EV_BASE, "semanas_consistentes": 5}))
    assert not sin["meta"]["calidad"] and all(z3(s) == 0 and s["tipo"] != "calidad" for w in sin["weeks"] for s in w["sessions"])
    nov = v6.generar_v6(entrada(nivel="empezando", inicio_minutos=60, evidencia={"trote_continuo_min": 20, "semanas_consistentes": 8, "minutos_sem_prom": 120}))
    assert not nov["meta"]["calidad"]
    con = v6.generar_v6(entrada(objetivo="velocidad", semanas=16, evidencia={**EV_BASE, "semanas_consistentes": 8}))
    tipos = [(w["n"], s["calidad_tipo"]) for w in con["weeks"] for s in w["sessions"] if s["tipo"] == "calidad"]
    orden = [t for _, t in tipos]
    assert orden[0] == "fartlek" or all(t in ("fartlek", "tempo_z3", "intervalos") for t in orden)
    assert min(n for n, _ in tipos) > 1                                    # nunca en la semana 1
    assert all(w["kind"] == "carga" for w in con["weeks"] if any(s["tipo"] == "calidad" for s in w["sessions"]))
    pos = {t: i for i, t in enumerate(["fartlek", "tempo_z3", "intervalos"])}
    assert [pos[t] for t in orden] == sorted(pos[t] for t in orden)         # un peldaño nuevo por bloque, sin retroceder
    assert "intervalos" in orden                                           # velocidad llega a VO2


def test_objetivo_define_el_tipo_de_calidad():
    base = v6.generar_v6(entrada(nivel="corredor", inicio_minutos=190, objetivo="base", dias=4, evidencia={**EV_BASE, "trote_continuo_min": 60}))
    carrera = v6.generar_v6(entrada(nivel="corredor", inicio_minutos=190, objetivo="carrera", dias=4, semanas=16, evidencia={**EV_BASE, "trote_continuo_min": 60}))
    sacar = lambda p: {s["calidad_tipo"] for w in p["weeks"] for s in w["sessions"] if s["tipo"] == "calidad"}  # noqa: E731
    assert "intervalos" not in sacar(base) and "threshold" not in sacar(base)
    assert "threshold" in sacar(carrera)


def test_tope_de_trabajo_en_z3_y_un_renglon_menos_con_intensos():
    ev = {**EV_BASE, "semanas_consistentes": 8}
    pocos = v6.generar_v6(entrada(evidencia=ev, semanas=16, dias=3))
    muchos = v6.generar_v6(entrada(evidencia=ev, semanas=16, dias=3, dias_intensos=[0, 2, 4]))
    for plan in (pocos, muchos):
        for w in plan["weeks"]:
            assert sum(z3(s) for s in w["sessions"]) <= 0.10 * minutos(w) + 1e-9      # ≤ 10 % de la semana en Base
            assert sum(1 for s in w["sessions"] if z3(s)) <= 1
    tipos = lambda p: [s["calidad_tipo"] for w in p["weeks"] for s in w["sessions"] if s["tipo"] == "calidad"]  # noqa: E731
    assert len(tipos(muchos)) <= len(tipos(pocos))                                    # con 3 intensos la calidad llega después


def test_sin_calidad_ni_larga_el_dia_despues_de_un_dia_intenso():
    intensos = [0, 1, 3, 4]
    plan = v6.generar_v6(entrada(dias_intensos=intensos, evidencia={**EV_BASE, "semanas_consistentes": 8}, edad=40))
    for w in plan["weeks"]:
        for s in w["sessions"]:
            if s["tipo"] in ("larga", "calidad"):
                assert (s["dia"] - 1) % 7 not in intensos, (w["n"], s["id"], s["dia"])


def test_empezando_nunca_dos_dias_seguidos():
    plan = v6.generar_v6(entrada(nivel="empezando", inicio_minutos=60, evidencia={"trote_continuo_min": 0}))
    for w in plan["weeks"]:
        dias = sorted(s["dia"] for s in w["sessions"])
        assert all(b - a > 1 for a, b in zip(dias, dias[1:])) and (dias[0] + 7 - dias[-1] > 1)


def test_dia_preferido_de_la_larga():
    plan = v6.generar_v6(entrada(dia_larga=5))
    assert {s["dia"] for w in plan["weeks"] for s in w["sessions"] if s["tipo"] == "larga"} == {5}


# --- carreras ---

def test_carrera_10k_taper_y_semana_de_carrera():
    plan = v6.generar_v6(entrada(meta={"km": 10, "semanas_hasta": 8}))
    assert len(plan["weeks"]) == 8 and plan["meta"]["carrera"] == {"km": 10, "semanas": 8}
    ult = plan["weeks"][-1]
    assert ult["evento"] == "carrera" and "10K" in ult["focus"] and all(s["tipo"] != "larga" for s in ult["sessions"])
    assert len(ult["sessions"]) == 2                                      # misma frecuencia menos la larga
    assert plan["weeks"][-2]["evento"] == "descarga_carrera"
    pico = max(minutos(w) for w in plan["weeks"][:-2])
    assert 0.40 * pico <= minutos(ult) <= 0.70 * pico


def test_carrera_por_fecha_y_dia_libre():
    plan = v6.generar_v6(entrada(meta={"km": 5, "fecha": "2027-01-10"}))      # domingo de la semana 6
    assert len(plan["weeks"]) == 6
    sem = plan["weeks"][-1]
    assert all(s["dia"] not in (6, 5) for s in sem["sessions"])              # ni el día de la carrera ni el anterior


@pytest.mark.parametrize("km,esperado", [(5, 1), (10, 2), (21, 2), (42, 3)])
def test_taper_semanas_por_distancia(km, esperado):
    plan = v6.generar_v6(entrada(nivel="corredor", dias=4, inicio_minutos=190, evidencia={**EV_BASE, "trote_continuo_min": 60},
                                 meta={"km": km, "semanas_hasta": 24}))
    assert sum(1 for w in plan["weeks"] if w.get("evento") in ("carrera", "descarga_carrera")) == esperado


def test_aviso_si_no_alcanza_el_tiempo():
    corto = v6.generar_v6(entrada(meta={"km": 21, "semanas_hasta": 6}))
    assert any(a["clave"] == "carrera_poco_tiempo" and a["minimas"] == 12 for a in corto["meta"]["avisos"])
    nunca = v6.generar_v6(entrada(nivel="empezando", inicio_minutos=60, evidencia={"trote_continuo_min": 0}, meta={"km": 42, "semanas_hasta": 20}))
    assert any(a["clave"] == "carrera_no_recomendada" for a in nunca["meta"]["avisos"])
    bien = v6.generar_v6(entrada(meta={"km": 10, "semanas_hasta": 10}))
    assert not [a for a in bien["meta"]["avisos"] if a["clave"].startswith("carrera")]


def test_carrera_invalida():
    with pytest.raises(ValueError):
        v6.generar_v6(entrada(meta={"km": 15, "semanas_hasta": 8}))
    with pytest.raises(ValueError):
        v6.generar_v6(entrada(meta={"km": 10, "fecha": "2026-01-01"}))
    with pytest.raises(ValueError):
        v6.generar_v6(entrada(nivel="experto"))


def test_permitir_mas_sube_hasta_15_y_avisa_el_motor_no_lo_anima():
    normal = v6.generar_v6(entrada(evidencia={**EV_BASE, "semanas_consistentes": 2}))
    mas = v6.generar_v6(entrada(permitir_mas=True, evidencia={**EV_BASE, "semanas_consistentes": 2}))
    assert minutos(mas["weeks"][1]) > minutos(normal["weeks"][1]) and minutos(mas["weeks"][1]) <= 100 * 1.15
    assert minutos(normal["weeks"][1]) <= 110


def test_entrada_incompleta_usa_defaults():
    plan = v6.generar_v6({"nivel": "base", "inicio": LUNES})
    assert len(plan["weeks"]) == 12 and plan["weeks"][0]["sessions"] and len(plan["weeks"][0]["sessions"]) == 3


def test_inicio_se_lleva_al_lunes():
    assert v6.generar_v6(entrada(inicio="2026-12-03"))["start"] == "2026-11-30"


# --- ajustar_semana ---

def plan_plano(*semanas):
    """Plan hecho a mano: (kind, [minutos]) por semana; la última sesión es la larga."""
    ws = []
    for n, (kind, ms) in enumerate(semanas, 1):
        ses = []
        for i, mm in enumerate(ms):
            larga = i == len(ms) - 1
            ses.append(v6._sesion("larga" if larga else f"z2{'abcd'[i]}", "larga" if larga else "z2", "Larga" if larga else f"Z2 #{i + 1}", mm,
                                  v6.pasos_continuo(mm, larga)))
        ws.append({"n": n, "block": 1, "kind": kind, "focus": "", "sessions": ses})
    return {"start": LUNES, "weeks": ws}


def test_ajustar_topa_a_110_de_lo_real():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))      # 100 y 110
    w = v6.ajustar_semana(plan, 2, 60)
    assert minutos(w) <= 66 and w["ajuste"]["tope"] == 66 and w["ajuste"]["ajustada"] and w["ajuste"]["planeado"] == 110
    assert next(s for s in w["sessions"] if s["tipo"] == "larga")["minutes"] <= 0.4 * minutos(w) + 1
    for s in w["sessions"]:
        assert gen_plan.suma(s["steps"]) == s["minutes"] == gen_plan.suma(s["easy"]["steps"]) or s["easy"]["minutes"] <= s["minutes"]


def test_ajustar_no_cambia_si_ya_cabe_ni_sube_nunca():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))
    w = v6.ajustar_semana(plan, 2, 100)
    assert minutos(w) == 110 and w["ajuste"]["ajustada"] is False and w["ajuste"]["tope"] == 110
    w = v6.ajustar_semana(plan, 2, 500)
    assert minutos(w) == 110                                                 # hacer de más no sube lo planeado


def test_ajustar_sin_dato_o_semana_1_devuelve_la_semana_igual():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))
    assert v6.ajustar_semana(plan, 2, None) == plan["weeks"][1]
    assert v6.ajustar_semana(plan, 1, 50) == plan["weeks"][0]


def test_ajustar_es_pura():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))
    copia = copy.deepcopy(plan)
    v6.ajustar_semana(plan, 2, 20)
    assert plan == copia


def test_ajustar_tras_hueco_una_sesion_de_regreso():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))
    w = v6.ajustar_semana(plan, 2, 0)
    assert w["ajuste"]["tope"] == v6.UMBRALES["ajuste_tras_hueco_min"] and minutos(w) <= 30


def test_ajustar_junta_las_sesiones_de_menos_de_10():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [33, 33, 44]))
    w = v6.ajustar_semana(plan, 2, 20)                                       # tope 22: tres sesiones serían de 7
    assert len(w["sessions"]) < 3 and all(s["minutes"] >= 10 for s in w["sessions"]) and minutos(w) <= 22
    assert any(s["tipo"] == "larga" for s in w["sessions"])                  # la larga se queda


def test_ajustar_topa_la_sesion_a_110_de_la_mas_larga_real():
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [30, 30, 44]))
    w = v6.ajustar_semana(plan, 2, 100, max_sesion_real_min=30)
    assert max(s["minutes"] for s in w["sessions"]) <= 33


def test_ajustar_tras_descarga_no_frena_el_regreso():
    plan = plan_plano(("carga", [30, 30, 40]), ("descarga", [20, 20, 28]), ("carga", [30, 30, 40]))
    # lo real de la descarga (68 planeados × 0.9 = 61) equivale a 90 en una semana normal: se pueden planear los 100
    w = v6.ajustar_semana(plan, 3, 61)
    assert 95 <= minutos(w) <= 98                                            # estimado: 61 × 100/68 ≈ 89 → tope 97 (sin la estimación serían 67)
    w2 = v6.ajustar_semana(plan, 3, 61, real_normal_min=90)
    assert 95 <= minutos(w2) <= 99                                           # con lo real de la semana normal a la mano: tope int(90 × 1.1) = 99
    w3 = v6.ajustar_semana(plan, 3, 30, real_normal_min=50)
    assert minutos(w3) <= 55


def test_ajustar_no_rebota_sobre_una_semana_ya_ajustada():
    """Si la semana anterior se planeó más baja (ya ajustada), esta no pasa de 110 % de ella aunque el plan original diga más."""
    plan = plan_plano(("carga", [30, 30, 40]), ("carga", [10, 10, 12]), ("carga", [40, 40, 50]))
    w = v6.ajustar_semana(plan, 3, 500)
    assert minutos(w) <= int(32 * 1.1)


def test_ajustar_calidad_que_no_cabe_pasa_a_z2():
    plan = v6.generar_v6(entrada(objetivo="velocidad", evidencia={**EV_BASE, "semanas_consistentes": 8}))
    n = next(w["n"] for w in plan["weeks"] if any(s["tipo"] == "calidad" for s in w["sessions"]))
    w = v6.ajustar_semana(plan, n, minutos(plan["weeks"][n - 2]) * 0.4)
    assert not any(s["tipo"] == "calidad" for s in w["sessions"]) or all(z3(s) <= 6 for s in w["sessions"])
    assert len({s["id"] for s in w["sessions"]}) == len(w["sessions"])


def test_foco_se_actualiza_al_ajustar():
    plan = v6.generar_v6(entrada())
    w = v6.ajustar_semana(plan, 2, 50)
    larga = next(s for s in w["sessions"] if s["tipo"] == "larga")
    assert f"Larga {larga['minutes']}'" in w["focus"]


# --- el resto de la app con 2, 4 y 5 sesiones ---

PLANES = {f"{niv}-{d}": v6.generar_v6(entrada(nivel=niv, dias=d, inicio_minutos=60 if niv == "empezando" else 150, meta={"km": 10, "semanas_hasta": 12},
                                                evidencia={**EV_BASE, "trote_continuo_min": 0 if niv == "empezando" else 60, "minutos_sem_prom": 140}))
          for niv in ("empezando", "base", "corredor") for d in (2, 3, 4, 5)}


@pytest.mark.parametrize("clave", sorted(PLANES))
def test_el_convertidor_del_reloj_arma_cada_sesion(clave):
    """Simulación del reloj (sin Garmin): cada sesión del plan se convierte en un entrenamiento válido."""
    for w in PLANES[clave]["weeks"]:
        for s in w["sessions"]:
            e = rp.entrenamiento(s, w["n"])
            assert e["estimatedDurationInSecs"] == s["minutes"] * 60 == rp.minutos_pasos(s["steps"]) * 60
            pasos = e["workoutSegments"][0]["workoutSteps"]
            assert pasos and rp.nombre_entrenamiento(s, w["n"]) == e["workoutName"]

            def revisa(lista, ordenes):
                for p in lista:
                    ordenes.append(p["stepOrder"])
                    if p["type"] == "RepeatGroupDTO":
                        assert p["numberOfIterations"] >= 1 and p["workoutSteps"]
                        revisa(p["workoutSteps"], ordenes)
                    else:
                        assert p["endConditionValue"] >= 60 and p["endConditionValue"] % 60 == 0    # ningún paso de 0 minutos
                        assert p["stepType"]["stepTypeKey"] in ("interval", "recovery")
            ordenes = []
            revisa(pasos, ordenes)
            assert ordenes == sorted(set(ordenes)) and ordenes[0] == 1             # stepOrder único y creciente
            assert rp.resumen_pasos(s["steps"])


def test_reloj_calidad_y_trote_caminata_llegan_con_zonas():
    plan = PLANES["corredor-4"]
    cal = next(s for w in plan["weeks"] for s in w["sessions"] if s["tipo"] == "calidad")
    zonas = {p.get("zoneNumber") for p in rp.entrenamiento(cal, 5)["workoutSegments"][0]["workoutSteps"]}
    assert 2 in zonas
    tc = next(s for s in PLANES["empezando-3"]["weeks"][0]["sessions"])
    assert any(p["stepType"]["stepTypeKey"] == "recovery" or p["type"] == "RepeatGroupDTO" for p in rp.entrenamiento(tc, 1)["workoutSegments"][0]["workoutSteps"])


@pytest.mark.parametrize("clave", sorted(PLANES))
def test_build_convierte_y_asigna_sesiones(clave):
    """build.convert_week y metrics.assign_sessions (hechas/total) con cualquier número de sesiones."""
    cfg = cargar_config(ROOT / "tests" / "fixtures")
    zonas = build.zones(cfg) if hasattr(build, "zones") else []
    for w in PLANES[clave]["weeks"]:
        cw = build.convert_week(w, zonas)
        assert len(cw["sessions"]) == len(w["sessions"])
        corridas = [{"fecha": "2026-12-05", "minutos": s["minutes"], "luz": "verde", "zonas": {}} for s in w["sessions"]]   # una corrida por sesión
        estado = m.assign_sessions(w, corridas, cfg)
        assert len(estado) == len(w["sessions"]) and {e["id"] for e in estado} == {s["id"] for s in w["sessions"]}
        assert sum(e["estado"] == "hecha" for e in estado) >= len(w["sessions"]) - 1 or len(w["sessions"]) <= 1
        assert build.cumplimiento_semana(len(w["sessions"]), len(w["sessions"])) == "completa"


def test_semana_de_carrera_y_descarga_previa_con_4_sesiones():
    """plan_vivo conserva el número de sesiones y ids únicos (antes asumía 3: z2a, z2b, larga)."""
    from web import plan_vivo
    plan = v6.generar_v6(entrada(dias=4, nivel="corredor", inicio_minutos=150, evidencia={**EV_BASE, "semanas_consistentes": 8, "trote_continuo_min": 60},
                                 objetivo="velocidad"))
    cfg = {**cargar_config(ROOT / "tests" / "fixtures"), "plan_start": plan["start"], "plan_semanas": 12, "semanas_repetidas": [], "pausas": [],
           "eventos": [], "metas": [{"id": "x", "tipo": "carrera", "fecha": "2027-02-14", "distancia_km": 10, "nombre": "10K"}]}
    efectivo = plan_vivo.plan_efectivo(plan, cfg)
    for w in efectivo["weeks"]:
        ids = [s["id"] for s in w["sessions"]]
        assert len(ids) == len(set(ids))
    carrera = next(w for w in efectivo["weeks"] if w.get("evento") == "carrera")
    assert len(carrera["sessions"]) == 3
    previa = next(w for w in efectivo["weeks"] if w.get("evento") == "descarga_carrera")
    assert len(previa["sessions"]) == 4


def test_plan_i18n_entiende_el_foco_de_v6():
    import plan_i18n
    assert "aceleraciones" in plan_i18n.focus("Larga 40' · aceleraciones")
    assert plan_i18n.focus("Descarga · trote 1'/camina 2'").startswith("Descarga")
    assert "1'/camina 2'" in plan_i18n.focus("Larga 22' · trote 1'/camina 2'")


def test_umbrales_en_un_solo_dict():
    assert isinstance(v6.UMBRALES, dict) and {"progresion_pct", "descarga_pct", "taper", "calidad_escalera", "escalera"} <= set(v6.UMBRALES)
    assert date.fromisoformat(LUNES).weekday() == 0
