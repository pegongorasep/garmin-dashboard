"""P2: saltos (repetir / retomar) en el calendario del plan y en plan_vivo."""
import copy
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path[:0] = [str(ROOT / "dashboard"), str(ROOT / "plan"), str(ROOT)]
import metrics as m  # noqa: E402
import motor_v6 as v6  # noqa: E402
from ajustes import normalizar_config  # noqa: E402
from test_motor_v6 import entrada  # noqa: E402
from test_web_cuentas import CONFIG  # noqa: E402
from web import plan_vivo  # noqa: E402
from web.errores import ErrorT  # noqa: E402

INI = date(2026, 11, 9)
LUN = lambda i: INI + timedelta(weeks=i)   # noqa: E731  lunes de la semana del calendario i (0 = primera)
HOY = LUN(4) + timedelta(days=2)            # miércoles de la semana 5


def crudo_con(corrida=None, **resto):
    c = copy.deepcopy(CONFIG)
    c["corrida"] = {**c["corrida"], **(corrida or {})}
    return {**c, **resto}


def cfg_de(crudo, hoy=HOY):
    return plan_vivo.con_pausas(normalizar_config(crudo), hoy)


def plan_corto(n=12):
    return {"start": INI.isoformat(), "weeks": [{"n": i, "kind": "carga", "sessions": []} for i in range(1, n + 1)]}


def plan_carrera(km=10, hasta=14):
    return v6.generar_v6(entrada(inicio=INI.isoformat(), meta={"km": km, "semanas_hasta": hasta}))


def crudo_carrera(plan):
    return crudo_con({"semanas": len(plan["weeks"]),
                      "metas": [{"id": "c1", "tipo": "carrera", "fecha": "2027-02-14", "distancia_km": 10, "nombre": "10K", "en_plan": True}]})


# --- secuencia ---

def test_secuencia_sin_saltos_igual_que_antes():
    assert m.secuencia_semanas(INI, [2], 4, ["2026-11-16"]) == [1, None, 2, 2, 3, 4]
    assert m.secuencia_semanas(INI, [], 3, [], []) == [1, 2, 3]


def test_repetir_alarga_una_semana():
    salto = [{"lunes": LUN(5).isoformat(), "semana": 5, "quita": []}]
    sec = m.secuencia_semanas(INI, [], 12, [], salto)
    assert sec == [1, 2, 3, 4, 5, 5, 6, 7, 8, 9, 10, 11, 12] and len(sec) == 13


def test_retomar_desde_x():
    sec = m.secuencia_semanas(INI, [], 12, [], [{"lunes": LUN(4).isoformat(), "semana": 3, "quita": []}])
    assert sec[:7] == [1, 2, 3, 4, 3, 4, 5] and len(sec) == 4 + 10   # actual 5, x 3: tres semanas más


def test_salto_con_quita_mantiene_el_largo():
    sec = m.secuencia_semanas(INI, [], 12, [], [{"lunes": LUN(5).isoformat(), "semana": 5, "quita": [11]}])
    assert len(sec) == 12 and 11 not in sec and sec[-1] == 12 and sec[4:6] == [5, 5]


def test_salto_y_pausa_juntos():
    pausa = [LUN(2).isoformat()]
    sec = m.secuencia_semanas(INI, [], 12, pausa, [{"lunes": LUN(5).isoformat(), "semana": 4, "quita": []}])
    # calendario: 1, 2, pausa, 3, 4, (salto en la semana 6 del calendario) 4, 5, ...
    assert sec[:8] == [1, 2, None, 3, 4, 4, 5, 6] and len(sec) == 12 + 1 + 1 + 1 - 1 + 0 or sec.count(None) == 1
    assert sec.count(None) == 1 and sec[-1] == 12


def test_varios_saltos_en_orden_de_fecha_y_quita_acumulada():
    s1 = {"lunes": LUN(5).isoformat(), "semana": 5, "quita": [11]}
    s2 = {"lunes": LUN(7).isoformat(), "semana": 6, "quita": [10]}
    a = m.secuencia_semanas(INI, [], 12, [], [s2, s1])
    assert a == m.secuencia_semanas(INI, [], 12, [], [s1, s2])
    assert 10 not in a[7:] and 11 not in a[5:]


def test_saltos_mal_formados_se_ignoran():
    malos = [{"lunes": "ayer", "semana": 2}, {"semana": 2}, {"lunes": LUN(1).isoformat(), "semana": "x"}, "x", None]
    assert m.secuencia_semanas(INI, [], 5, [], malos) == [1, 2, 3, 4, 5]
    c = normalizar_config(crudo_con({"saltos": malos + [{"lunes": LUN(1).isoformat(), "semana": 1}, {"lunes": "2026-11-10", "semana": 1}]}))
    assert c["saltos"] == [{"lunes": LUN(1).isoformat(), "semana": 1, "quita": []}]


def test_config_sin_saltos_funciona():
    c = normalizar_config(crudo_con())
    assert c["saltos"] == [] and m.semana_del_plan(HOY, c) == 5
    assert m.semana_del_plan(HOY, {"plan_start": "2026-11-09", "plan_semanas": 12}) == 5


def test_semana_del_plan_y_en_pausa_respetan_saltos():
    c = cfg_de(crudo_con({"saltos": [{"lunes": LUN(5).isoformat(), "semana": 5, "quita": []}]}))
    assert [m.semana_del_plan(LUN(i), c) for i in (4, 5, 6)] == [5, 5, 6]
    assert m.semana_del_plan(LUN(12), c) == 12 and m.semana_del_plan(LUN(13), c) is None


# --- repetir / retomar ---

def test_repetir_agrega_salto_y_devuelve_info():
    crudo = crudo_con()
    nuevo, info = plan_vivo.repetir(crudo, plan_corto(), cfg_de(crudo), HOY)
    assert nuevo["corrida"]["saltos"] == [{"lunes": LUN(5).isoformat(), "semana": 5, "quita": []}]
    assert crudo == crudo_con()   # no muta
    assert info == {"k": 1, "quita": [], "fin": (LUN(13) - timedelta(days=1)).isoformat(), "objetivo": False}
    assert [m.semana_del_plan(LUN(i), cfg_de(nuevo)) for i in (4, 5, 6)] == [5, 5, 6]


def test_retomar_desde_x_y_fuera_de_rango():
    crudo = crudo_con()
    nuevo, info = plan_vivo.retomar(crudo, plan_corto(), cfg_de(crudo), HOY, 3)
    assert nuevo["corrida"]["saltos"] == [{"lunes": LUN(4).isoformat(), "semana": 3, "quita": []}]
    assert info["k"] == 2 and info["fin"] == (LUN(14) - timedelta(days=1)).isoformat()   # actual 5, x 3: dos semanas más
    cfg = cfg_de(nuevo)
    assert [m.semana_del_plan(LUN(i), cfg) for i in (3, 4, 5, 6)] == [4, 3, 4, 5]
    nuevo, info = plan_vivo.retomar(crudo, plan_corto(), cfg_de(crudo), HOY, 5)   # x = la actual: nada se mueve
    assert info["k"] == 0 and [m.semana_del_plan(LUN(i), cfg_de(nuevo)) for i in (4, 5)] == [5, 6]
    for mala in (0, 6, -1, "x"):
        with pytest.raises(ErrorT):
            plan_vivo.retomar(crudo, plan_corto(), cfg_de(crudo), HOY, mala)


def test_sin_semana_en_curso_no_se_puede():
    crudo = crudo_con()
    with pytest.raises(ErrorT):
        plan_vivo.repetir(crudo, plan_corto(), cfg_de(crudo, LUN(30)), LUN(30))   # fuera del plan
    pausado = plan_vivo.agregar_evento(crudo, "enfermedad", LUN(4).isoformat(), None)
    with pytest.raises(ErrorT):
        plan_vivo.repetir(pausado, plan_corto(), cfg_de(pausado), HOY)   # en pausa


def test_viaje_se_queda_en_su_fecha_y_cae_en_otra_semana_del_plan():
    crudo = plan_vivo.agregar_evento(crudo_con(), "viaje", LUN(6).isoformat(), (LUN(6) + timedelta(days=4)).isoformat(), correr=True)
    plan = plan_corto()
    for w in plan["weeks"]:
        w["sessions"] = [{"id": "z2a", "tipo": "z2", "name": "Z2 #1", "minutes": 30, "steps": [],
                          "easy": {"minutes": 20, "steps": []}}]
    cfg = cfg_de(crudo)
    assert [w["n"] for w in plan_vivo.plan_efectivo(plan, cfg)["weeks"] if w.get("evento") == "viaje"] == [7]
    nuevo, _ = plan_vivo.repetir(crudo, plan, cfg, HOY)
    cfg2 = cfg_de(nuevo)
    # el viaje sigue en la semana del calendario 6; ahora esa semana es la 6 del plan (antes la 7)
    assert m.semana_del_plan(LUN(6), cfg2) == 6
    assert [w["n"] for w in plan_vivo.plan_efectivo(plan, cfg2)["weeks"] if w.get("evento") == "viaje"] == [6]


def test_carrera_objetivo_se_detecta():
    plan = plan_carrera()
    cfg = cfg_de(crudo_carrera(plan))
    assert plan_vivo.carrera_objetivo(plan, cfg)["id"] == "c1"
    assert plan_vivo.carrera_objetivo(plan_corto(), cfg) is None
    assert plan_vivo.carrera_objetivo(plan, cfg_de(crudo_con()))["km"] == 10   # sin meta en la config: la del plan


def _calendario(crudo, plan, hoy):
    cfg = cfg_de(crudo, hoy)
    sec = m.secuencia_de(cfg)
    return {w["n"]: [i for i, n in enumerate(sec) if n == w["n"]] for w in plan["weeks"]}, len(sec)


def test_carrera_objetivo_taper_y_carrera_en_su_fecha():
    plan = plan_carrera()
    crudo = crudo_carrera(plan)
    antes, largo = _calendario(crudo, plan, HOY)
    nuevo, info = plan_vivo.repetir(crudo, plan, cfg_de(crudo), HOY)
    assert info["objetivo"] and info["k"] == 1 and info["quita"] == [11]   # la última de carga antes del taper (12 es descarga)
    despues, largo2 = _calendario(nuevo, plan, HOY)
    assert largo2 == largo == 14 and despues[13] == antes[13] and despues[14] == antes[14]
    assert 11 not in [n for n in m.secuencia_de(cfg_de(nuevo))]
    assert info["fin"] == (LUN(14) - timedelta(days=1)).isoformat()
    # retomar a la semana 3 (k = 2): se quitan las 2 últimas de carga
    nuevo, info = plan_vivo.retomar(crudo, plan, cfg_de(crudo), HOY, 3)
    assert info["k"] == 2 and info["quita"] == [10, 11]
    despues, largo3 = _calendario(nuevo, plan, HOY)
    assert largo3 == 14 and despues[14] == antes[14]


def test_dos_saltos_seguidos_no_quitan_la_misma_semana():
    plan = plan_carrera()
    crudo = crudo_carrera(plan)
    n1, i1 = plan_vivo.repetir(crudo, plan, cfg_de(crudo), HOY)
    n2, i2 = plan_vivo.repetir(n1, plan, cfg_de(n1, LUN(5) + timedelta(days=1)), LUN(5) + timedelta(days=1))
    assert i1["quita"] == [11] and i2["quita"] == [10] and len(m.secuencia_de(cfg_de(n2))) == 14


def test_carrera_objetivo_sin_semanas_de_carga_no_se_permite():
    plan = plan_carrera(hasta=7)   # 1-3 carga, 4 descarga, 5 carga? el resto es taper
    crudo = crudo_carrera(plan)
    hoy = LUN(len(plan["weeks"]) - 3) + timedelta(days=2)    # ya sin carga por delante
    with pytest.raises(ErrorT) as ex:
        plan_vivo.repetir(crudo, plan, cfg_de(crudo, hoy), hoy)
    assert ex.value.clave == "err.sin_carga_antes_taper"
    with pytest.raises(ErrorT):
        plan_vivo.retomar(crudo, plan, cfg_de(crudo, hoy), hoy, 1)
