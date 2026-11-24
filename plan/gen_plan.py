"""Genera plan/plan.json (3 corridas por semana) según el nivel y la intensidad de config.yaml.

Uso: python plan/gen_plan.py [--config config.yaml] [--out plan/plan.json]
Por defecto lee y escribe en USER_DIR (GARMIN_USER_DIR o la raíz del repo).

Progresión: bloques de 3 semanas de carga + 1 de descarga. Los incrementos están definidos para
base_min = {z2: 20, larga: 40} (la tabla de Pedro) y se escalan en proporción a la base de cada
persona, redondeando a 5'. Si `semanas` != 12 se recorta el patrón, y más allá del bloque 3 se repite
el bloque 3 (sin subir más). La versión suave usa SUAVE para los minutos conocidos y ~72 % redondeado a 5'
para los demás.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
from ajustes import USER_DIR, cargar_config  # noqa: E402

# Incrementos sobre la base (z2 = 20', larga = 40'), por posición en el bloque: (carga1, carga2, carga3, descarga)
DELTA_Z2A = [(0, 0, 0, 0), (5, 5, 5, 0), (10, 10, 10, 5)]
DELTA_Z2B = [(0, 0, 5, 0), (5, 5, 10, 0), (10, 10, 10, 5)]
DELTA_LARGA = [(0, 5, 10, -10), (10, 15, 20, 0), (20, 25, 30, 5)]
REF_Z2, REF_LARGA = 20, 40
SUAVE = {20: 15, 25: 20, 30: 20, 40: 30, 45: 30, 50: 35, 55: 40, 60: 40, 65: 45, 70: 50}
NOTA_Z2 = "arranca suave; camina si pasas el techo"
NOTA_LARGA = "ritmo cómodo; si pasas el techo, camina hasta bajar"
NOTA_CAMINATAS = "si una semana te sientes bien, puedes subir al siguiente escalón"
TROTE_POR_BLOQUE = [3, 5, 8]   # minutos de trote por cada 1' de caminata
# (zona, [(repeticiones, minutos de trabajo, minutos de recuperación) por bloque])
CALIDAD = {
    "tempo_z3": ("Z3", [(2, 10, 3), (2, 12, 3), (2, 15, 3)], "Tempo Z3"),
    "threshold": ("Z4", [(4, 5, 2), (5, 5, 2), (4, 6, 2)], "Threshold"),
    "intervalos": ("Z4", [(6, 2, 2), (8, 2, 2), (6, 3, 2)], "Intervalos"),
}


def redondea5(x: float) -> int:
    return int(x / 5 + 0.5) * 5


def suave(minutos: int) -> int:
    return SUAVE.get(minutos) or max(10, redondea5(minutos * 0.72))


def paso(minutos, zona="Z1-Z2", nota="", kind="run", **extra):
    return {"kind": kind, "minutes": minutos, "zone": zona, "note": nota, **extra}


def suma(pasos: list) -> int:
    return sum(p["times"] * suma(p["steps"]) if p["kind"] == "repeat" else p["minutes"] for p in pasos)


def zonas_de(pasos: list) -> set:
    return {z for p in pasos for z in (zonas_de(p["steps"]) if p["kind"] == "repeat" else {p["zone"]})}


def pasos_con_picos(minutos: int) -> list:
    """25' -> 10 · 1 · 3 · 1 · 10; 30' -> 12 · 1 · 3 · 1 · 13."""
    antes = (minutos - 5) // 2
    pico = lambda: paso(1, "Z3", "opcional", optional=True)  # noqa: E731
    return [paso(antes, nota=NOTA_Z2), pico(), paso(3, "Z2"), pico(), paso(minutos - antes - 5)]


def pasos_caminatas(minutos: int, bloque: int) -> list:
    """Repeticiones de trote/caminata (1' de caminata); la última se ajusta para sumar `minutos`."""
    t = TROTE_POR_BLOQUE[min(max(bloque, 1), 3) - 1]
    n, resto = divmod(minutos, t + 1)
    pasos = [{"kind": "repeat", "times": n, "steps": [paso(t), paso(1, kind="walk")]}] if n else []
    if resto >= 2:
        pasos += [paso(resto - 1), paso(1, kind="walk")]
    elif resto == 1:
        pasos.append(paso(1))
    return pasos


def pasos_z2(minutos: int, larga: bool, caminatas: bool, bloque: int) -> list:
    if caminatas:
        return pasos_caminatas(minutos, bloque)
    return [paso(minutos, nota=NOTA_LARGA if larga else NOTA_Z2)]


def sesion(id_, tipo, nombre, minutos, pasos, **extra):
    s = suave(minutos)
    return {"id": id_, "tipo": tipo, "name": nombre, "minutes": minutos, "steps": pasos, **extra,
            "easy": {"name": "Suave", "minutes": s, "steps": [paso(s)]}}


def con_suave_caminatas(s: dict, caminatas: bool, bloque: int) -> dict:
    if caminatas:
        s["easy"]["steps"] = pasos_caminatas(s["easy"]["minutes"], bloque)
        s["nota"] = NOTA_CAMINATAS
    return s


def sesion_calidad(tipo: str, bloque: int) -> dict:
    zona, bloques, etiqueta = CALIDAD[tipo]
    veces, trabajo, rec = bloques[min(bloque, 3) - 1]
    pasos = [paso(10, "Z2", "calentamiento", kind="warmup"),
             {"kind": "repeat", "times": veces, "steps": [paso(trabajo, zona), paso(rec, kind="run", nota="suave")]},
             paso(5, "Z1-Z2", "enfriamiento", kind="cooldown")]
    s = sesion("calidad", "calidad", f"Calidad · {etiqueta}", suma(pasos), pasos,
               calidad_tipo=tipo, objetivo={"zona": zona, "minutos": veces * trabajo})
    s["easy"]["steps"] = [paso(s["easy"]["minutes"])]
    return s


def escala(tabla, base, ref, bloque, pos, minimo=10):
    return max(minimo, redondea5(base + tabla[bloque][pos] * base / ref))


def semana(n: int, cfg: dict, n_carga: int) -> dict:
    """`n_carga`: cuántas semanas de carga van antes de esta (para rotar los tipos de calidad)."""
    bloque, pos = min((n - 1) // 4, 2), (n - 1) % 4
    descarga = pos == 3
    b = {"z2": 20, "larga": 40, **cfg["base_min"]}
    z2a = escala(DELTA_Z2A, b["z2"], REF_Z2, bloque, pos)
    z2b = escala(DELTA_Z2B, b["z2"], REF_Z2, bloque, pos)
    larga = escala(DELTA_LARGA, b["larga"], REF_LARGA, bloque, pos)
    caminatas, intensidad = cfg["caminatas"], cfg["intensidad"]
    nb = bloque + 1
    picos = intensidad == "z2_poca_z3" and not caminatas and bloque >= 1 and not descarga

    def z2(id_, nombre, minutos, con_picos=False):
        pasos = pasos_con_picos(minutos) if con_picos else pasos_z2(minutos, False, caminatas, nb)
        return con_suave_caminatas(sesion(id_, "z2", nombre, minutos, pasos), caminatas, nb)

    sesiones = [z2("z2a", "Z2 #1", z2a, picos)]
    focus = f"Larga {larga}'" if not descarga else "Descarga"
    if intensidad == "calidad" and not descarga:
        tipo = cfg["calidad_tipos"][n_carga % len(cfg["calidad_tipos"])]
        sesiones.append(sesion_calidad(tipo, nb))
        focus += f" · calidad: {CALIDAD[tipo][2]}"
    else:
        sesiones.append(z2("z2b", "Z2 #2", z2b))
    sesiones.append(con_suave_caminatas(
        sesion("larga", "larga", "Larga", larga, pasos_z2(larga, True, caminatas, nb)), caminatas, nb))
    if picos:
        focus += " · picos Z3 opcionales"
    if caminatas:
        focus += f" · trote {TROTE_POR_BLOQUE[nb - 1]}'/camina 1'"
    return {"n": n, "block": bloque + 1, "kind": "descarga" if descarga else "carga", "focus": focus,
            "sessions": sesiones}


def verificar(plan: dict) -> None:
    for w in plan["weeks"]:
        con_z3 = 0
        for s in w["sessions"]:
            assert suma(s["steps"]) == s["minutes"], (w["n"], s["id"])
            assert suma(s["easy"]["steps"]) == s["easy"]["minutes"], (w["n"], s["id"], "suave")
            assert not zonas_de(s["easy"]["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], s["id"], "suave con Z3+")
            if s["tipo"] == "larga":
                assert not zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], "larga con Z3+")
            con_z3 += bool(zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"})
        assert con_z3 <= 1, (w["n"], "más de una sesión con Z3+")
        if w["kind"] == "descarga":
            assert not any(s["tipo"] == "calidad" for s in w["sessions"]), (w["n"], "descarga con calidad")


def generar(cfg: dict) -> dict:
    semanas, n_carga = [], 0
    for n in range(1, cfg["plan_semanas"] + 1):
        w = semana(n, cfg, n_carga)
        n_carga += w["kind"] == "carga"
        semanas.append(w)
    plan = {"start": cfg["plan_start"], "weeks": semanas}
    verificar(plan)
    return plan


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(USER_DIR / "config.yaml"))
    ap.add_argument("--out", default=str(USER_DIR / "plan" / "plan.json"))
    args = ap.parse_args()
    plan = generar(cargar_config(args.config))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
    print(f"OK: {out} ({len(plan['weeks'])} semanas)")


if __name__ == "__main__":
    main()
