"""Genera plan/plan.json (plan v2: 3 corridas por semana) a partir de la tabla de PLAN_ENTRENAMIENTO.md.

Uso: python plan/gen_plan.py
"""
import json
from pathlib import Path

INICIO = "2026-11-16"
# (n, bloque, tipo, z2a, z2b, larga, picos Z3 en z2a)
TABLA = [
    (1, 1, "carga", 20, 20, 40, False),
    (2, 1, "carga", 20, 20, 45, False),
    (3, 1, "carga", 20, 25, 50, False),
    (4, 1, "descarga", 20, 20, 30, False),
    (5, 2, "carga", 25, 25, 50, True),
    (6, 2, "carga", 25, 25, 55, True),
    (7, 2, "carga", 25, 30, 60, True),
    (8, 2, "descarga", 20, 20, 40, False),
    (9, 3, "carga", 30, 30, 60, True),
    (10, 3, "carga", 30, 30, 65, True),
    (11, 3, "carga", 30, 30, 70, True),
    (12, 3, "descarga", 25, 25, 45, False),
]
SUAVE = {20: 15, 25: 20, 30: 20, 40: 30, 45: 30, 50: 35, 55: 40, 60: 40, 65: 45, 70: 50}
TOTALES = [80, 85, 95, 70, 100, 105, 115, 80, 120, 125, 130, 95]
NOTA_Z2 = "arranca suave; camina si pasas el techo"
NOTA_LARGA = "ritmo cómodo; si pasas el techo, camina hasta bajar"


def paso(minutos, zona="Z1-Z2", nota="", **extra):
    return {"kind": "run", "minutes": minutos, "zone": zona, "note": nota, **extra}


def pasos_con_picos(minutos):
    """25' -> 10 · 1 · 3 · 1 · 10; 30' -> 12 · 1 · 3 · 1 · 13."""
    antes = 10 if minutos == 25 else 12
    despues = minutos - antes - 5
    pico = lambda: paso(1, "Z3", "opcional", optional=True)  # noqa: E731
    return [paso(antes, nota=NOTA_Z2), pico(), paso(3, "Z2"), pico(), paso(despues)]


def sesion(id_, tipo, nombre, minutos, picos=False):
    pasos = pasos_con_picos(minutos) if picos else [paso(minutos, nota=NOTA_LARGA if tipo == "larga" else NOTA_Z2)]
    suave = SUAVE[minutos]
    return {"id": id_, "tipo": tipo, "name": nombre, "minutes": minutos, "steps": pasos,
            "easy": {"name": "Suave", "minutes": suave, "steps": [paso(suave)]}}


def semana(n, bloque, kind, a, b, larga, picos):
    focus = f"Larga {larga}'" if kind == "carga" else "Descarga"
    if picos:
        focus += " · picos Z3 opcionales"
    return {"n": n, "block": bloque, "kind": kind, "focus": focus,
            "sessions": [sesion("z2a", "z2", "Z2 #1", a, picos), sesion("z2b", "z2", "Z2 #2", b),
                         sesion("larga", "larga", "Larga", larga)]}


def suma(pasos):
    return sum(p["minutes"] for p in pasos)


def verificar(plan):
    for w in plan["weeks"]:
        for s in w["sessions"]:
            assert suma(s["steps"]) == s["minutes"], (w["n"], s["id"])
            assert suma(s["easy"]["steps"]) == s["easy"]["minutes"], (w["n"], s["id"], "suave")
            assert not any(p["zone"] == "Z3" for p in s["easy"]["steps"])
            if s["tipo"] == "larga":
                assert not any(p["zone"] == "Z3" for p in s["steps"])
    assert [sum(s["minutes"] for s in w["sessions"]) for w in plan["weeks"]] == TOTALES
    assert len(plan["weeks"]) == 12


def generar() -> dict:
    plan = {"start": INICIO, "weeks": [semana(*fila) for fila in TABLA]}
    verificar(plan)
    return plan


if __name__ == "__main__":
    destino = Path(__file__).parent / "plan.json"
    destino.write_text(json.dumps(generar(), ensure_ascii=False, indent=2) + "\n")
    print(f"OK: {destino} (12 semanas)")
