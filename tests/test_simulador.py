"""Simulador de planes (plan/simulador.py): personas, simulación y reglas.
Las reglas REPORTAN: aquí solo se prueba que detectan un plan malo hecho a mano y aceptan uno bueno, no que el motor
v6 las cumpla (eso lo vigila tests/test_motor_v6.py)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "plan"))
import simulador as sim  # noqa: E402

BASE = {"sesiones": [30, 30, 30], "continuo": 30}


def persona(**kw):
    """Persona con base (8 semanas de 3 × 30'); `kw` sobreescribe campos."""
    p = {"id": "t", "nombre": "T", "edad": 35, "historial": [BASE] * 8}
    p.update(kw)
    return sim._normalizar_persona(p)


def plan(*semanas):
    """Cada semana: (kind, [minutos o (minutos, zona, tipo, dia)]). Sesiones de un solo paso en Z2 salvo que se diga."""
    weeks = []
    for i, (kind, ses) in enumerate(semanas, 1):
        out = []
        for j, s in enumerate(ses):
            m, zona, tipo, dia = ((s if isinstance(s, tuple) else (s,)) + (None,) * 4)[:4]
            zona, tipo = zona or "Z2", tipo or "z2"
            sesion = {"name": f"S{j}", "tipo": tipo, "minutes": m, "steps": [{"kind": "run", "minutes": m, "zone": zona, "note": ""}]}
            if dia is not None:
                sesion["dia"] = dia
            out.append(sesion)
        weeks.append({"n": i, "kind": kind, "focus": "", "sessions": out})
    return {"start": sim.INICIO, "weeks": weeks}


def regla(p, pl, clave):
    return next(r for r in sim.analizar(p, pl)["reglas"] if r["clave"] == clave)


def carga(*totales):
    return [("carga", [t // 3] * 3) for t in totales]


# --- personas y simulación ---

def test_personas_cargan():
    ps = sim.cargar_personas()
    assert len(ps) == 8 and len({p["id"] for p in ps}) == 8
    for p in ps:
        assert p["nombre"] and p["descripcion"]
        assert len(p["historial"]) in (0, 8)


def test_determinista():
    assert sim.simular_todas() == sim.simular_todas()


def test_todas_las_personas_simulan_con_todas_las_reglas():
    for r in sim.simular_todas():
        assert [x["clave"] for x in r["reglas"]] == sim.CLAVES and len(r["semanas"]) >= 4
        assert {x["ok"] for x in r["reglas"]} <= {True, False, None}


def test_adherencia_escala_y_huecos():
    p = persona(adherencia={"base": 0.6, "huecos": [[2, 3]]})
    r = sim.analizar(p, plan(*carga(90, 90, 90, 90)))["semanas"]
    assert [x["hecho_min"] for x in r] == [54, 0, 0, 54]
    assert r[3]["max30"] == 30   # la ventana mezcla historial y lo hecho (18'), no lo planeado


def test_novata_sin_datos_no_trae_z3_en_semana_1():
    r = sim.simular(sim.persona_por_id("novata_sin_datos"))
    z3 = next(x for x in r["reglas"] if x["clave"] == "sin_z3_novato")
    assert z3["ok"] is True and r["semanas"][0]["z3mas_min"] == 0 and r["sin_base"]


# --- reglas: un plan malo hecho a mano falla, uno bueno pasa ---

def test_sube_10():
    p = persona()
    assert regla(p, plan(*carga(90, 110)), "sube_10")["semanas_fallan"] == [2]
    assert regla(p, plan(*carga(90, 95, 100), ("descarga", [20, 20, 25]), *carga(100)), "sube_10")["ok"] is True
    mal = regla(p, plan(*carga(90, 95, 100), ("descarga", [20, 20, 25]), *carga(114)), "sube_10")
    assert mal["semanas_fallan"] == [5] and "tras descarga" in mal["detalle"]


def test_sube_real_10():
    assert regla(persona(), plan(*carga(90, 95, 100)), "sube_real_10")["ok"] is True
    assert regla(persona(adherencia={"base": 0.5}), plan(*carga(90, 90, 90)), "sube_real_10")["ok"] is True   # 50–90 %: repetir la semana vale
    mal = regla(persona(adherencia={"base": 0.5}), plan(*carga(90, 100, 110)), "sube_real_10")             # pero subir no
    assert mal["ok"] is False and mal["semanas_fallan"] == [2, 3]
    assert regla(persona(adherencia={"base": 0.4}), plan(*carga(90, 63, 44)), "sube_real_10")["ok"] is True   # < 50 %: paso atrás (≥ 70 %)
    assert regla(persona(adherencia={"base": 0.4}), plan(*carga(90, 50)), "sube_real_10")["ok"] is True        # bajar más de lo necesario no sube nada
    tras_hueco = regla(persona(adherencia={"base": 1.0, "huecos": [[1, 1]]}), plan(*carga(90, 90)), "sube_real_10")
    assert tras_hueco["semanas_fallan"] == [2]   # venía de 0 y planea 90'


def test_sesion_110():
    assert regla(persona(), plan(("carga", [30, 30, 33])), "sesion_110")["ok"] is True
    assert regla(persona(), plan(("carga", [20, 20, 40])), "sesion_110")["semanas_fallan"] == [1]
    sin_hist = regla(persona(historial=[]), plan(("carga", [20, 20, 40])), "sesion_110")
    assert sin_hist["ok"] is True   # sin referencia no hay tope; lo cubre inicio_real


def test_larga_40():
    assert regla(persona(), plan(("carga", [30, 30, 35])), "larga_40")["ok"] is True
    assert regla(persona(), plan(("carga", [20, 20, 40])), "larga_40")["semanas_fallan"] == [1]
    assert regla(persona(), plan(("carga", [20, 20, 30, 40])), "larga_40")["semanas_fallan"] == [1]   # 4 sesiones: tope 33 %


def test_sin_z3_novato():
    novata = persona(historial=[])
    mal = plan(("carga", [20, (20, "Z3", "variada"), 20]))
    assert regla(novata, mal, "sin_z3_novato")["semanas_fallan"] == [1]
    assert regla(novata, plan(("carga", [20, 20, 20])), "sin_z3_novato")["ok"] is True
    assert regla(persona(), mal, "sin_z3_novato")["ok"] is None   # con base no aplica


def test_sin_z3_se_desbloquea_con_el_tiempo():
    novata = persona(historial=[])
    semanas = [("carga", [30, 30, 35]) for _ in range(8)]
    semanas[7] = ("carga", [30, (30, "Z3", "variada"), 35])
    filas = sim.analizar(novata, plan(*semanas))["semanas"]
    assert [f["desbloqueado"] for f in filas] == [False] * 6 + [True, True]   # 6 semanas consistentes: desde la 7
    assert regla(novata, plan(*semanas), "sin_z3_novato")["ok"] is True


def test_descarga():
    assert regla(persona(), plan(*carga(90, 90, 90), ("descarga", [20, 20, 20]), *carga(90)), "descarga")["ok"] is True
    assert regla(persona(), plan(*carga(90, 90, 90, 90)), "descarga")["semanas_fallan"] == [4]
    mayor = persona(edad=52)   # cada 3 semanas
    assert regla(mayor, plan(*carga(90, 90, 90)), "descarga")["semanas_fallan"] == [3]
    assert regla(mayor, plan(*carga(90, 90), ("descarga", [20, 20, 20]), *carga(90, 90)), "descarga")["ok"] is True
    hiit = persona(intensos_semana={"dias": ["lun", "mié", "vie"], "tipo": "hiit"})
    assert regla(hiit, plan(*carga(90, 90, 90)), "descarga")["semanas_fallan"] == [3]


def test_inicio_real():
    assert regla(persona(), plan(*carga(95)), "inicio_real")["ok"] is True
    assert regla(persona(), plan(*carga(130)), "inicio_real")["semanas_fallan"] == [1]
    assert regla(persona(historial=[]), plan(("carga", [20, 20, 25])), "inicio_real")["ok"] is True
    assert regla(persona(historial=[]), plan(("carga", [20, 20, 40])), "inicio_real")["semanas_fallan"] == [1]


def test_taper():
    meta = {"distancia_km": 10, "semanas_hasta": 8}
    p = persona(meta=meta)
    plano = plan(*carga(*[90] * 8))
    bueno = plan(*carga(*[90] * 7), ("descarga", [18, 18, 18]))   # -40 %
    assert regla(p, plano, "taper")["semanas_fallan"] == [8]
    assert regla(p, bueno, "taper")["ok"] is True
    assert regla(persona(), plano, "taper")["ok"] is None
    assert regla(persona(meta={"distancia_km": 10, "semanas_hasta": 20}), plano, "taper")["ok"] is None


def test_post_intenso():
    p = persona(intensos_semana={"dias": ["lun"], "tipo": "hiit"})
    assert regla(p, plan(("carga", [30, 30, 30])), "post_intenso")["ok"] is None   # sin días en el plan
    malo = plan(("carga", [(30, "Z2", "z2", 2), (30, "Z2", "z2", 3), (30, "Z2", "larga", 1)]))   # larga el martes
    bueno = plan(("carga", [(30, "Z2", "z2", 1), (30, "Z2", "z2", 3), (30, "Z2", "larga", 5)]))
    assert regla(p, malo, "post_intenso")["semanas_fallan"] == [1]
    assert regla(p, bueno, "post_intenso")["ok"] is True
    dom = persona(intensos_semana={"dias": ["dom"], "tipo": "hiit"})   # el lunes sigue al domingo
    assert regla(dom, plan(("carga", [(30, "Z2", "calidad", 0)])), "post_intenso")["ok"] is False
