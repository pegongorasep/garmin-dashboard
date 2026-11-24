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
from tipos import POR_ID  # noqa: E402

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
# Calidad sin la estructura "calentar · N×(trabajo, recuperación) · enfriar".
# progresivo: (minutos Z2 tranquilos, minutos Z3 al final) por bloque.
PROGRESIVO = [(6, 8), (6, 10), (6, 12)]
# fartlek: (trabajo Z3, recuperación) irregulares por bloque; la última recuperación no se hace.
FARTLEK = [[(2, 2), (3, 2), (1, 2), (3, 2), (2, 2)],
           [(3, 2), (4, 2), (2, 2), (4, 2), (3, 2)],
           [(3, 2), (5, 2), (2, 2), (5, 2), (4, 2), (2, 2)]]
ETIQUETA_CALIDAD = {"progresivo": "Progresivo", "fartlek": "Fartlek"}
CALIDAD_TODOS = ["tempo_z3", "threshold", "intervalos", "progresivo", "fartlek"]
# Corrida variada (solo con `corrida.variada: true`): tipos que rotan por semana de carga.
VARIADA_TIPOS = {"solo_z2": ["ascendente", "densidad", "rotativo", "descendente"],
                 "z2_poca_z3": ["espiga", "piramide", "ascendente", "rotativo", "descendente", "densidad"]}
Z3_VARIADA_MAX = 6      # minutos máximos de Z3 en una variada de z2_poca_z3
Z3_VARIADA_PCT = 0.20   # ... y como máximo 20 % de la sesión


def redondea5(x: float) -> int:
    return int(x / 5 + 0.5) * 5


def suave(minutos: int) -> int:
    return SUAVE.get(minutos) or max(10, redondea5(minutos * 0.72))


def paso(minutos, zona="Z2", nota="", kind="run", **extra):
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
    pasos = [{"kind": "repeat", "times": n, "steps": [paso(t), paso(1, "Z1", kind="walk")]}] if n else []
    if resto >= 2:
        pasos += [paso(resto - 1), paso(1, "Z1", kind="walk")]
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


def pasos_calidad_libre(tipo: str, bloque: int):
    """(pasos, minutos de trabajo en Z3) de progresivo y fartlek. Sin calentamiento ni enfriamiento: esos 5' van
    aparte (el sitio los dibuja y no cuentan); los 10' Z2 del inicio son parte de la sesión."""
    b = min(bloque, 3) - 1
    calen = paso(10, "Z2", "suave")
    if tipo == "progresivo":
        tranq, z3 = PROGRESIVO[b]
        return [calen, paso(tranq, "Z2", "ritmo cómodo"), paso(z3, "Z3", "sube hasta aquí poco a poco")], z3
    pares, pasos = FARTLEK[b], [calen]
    for i, (trabajo, rec) in enumerate(pares):
        pasos.append(paso(trabajo, "Z3"))
        if i < len(pares) - 1:
            pasos.append(paso(rec, kind="run", nota="suave"))
    return pasos, sum(t for t, _ in pares)


def sesion_calidad(tipo: str, bloque: int) -> dict:
    if tipo in ETIQUETA_CALIDAD:
        pasos, trabajo_z3 = pasos_calidad_libre(tipo, bloque)
        zona, minutos_obj, etiqueta = "Z3", trabajo_z3, ETIQUETA_CALIDAD[tipo]
    else:
        zona, bloques, etiqueta = CALIDAD[tipo]
        veces, trabajo, rec = bloques[min(bloque, 3) - 1]
        minutos_obj = veces * trabajo
        pasos = [paso(10, "Z2", "suave"),
                 {"kind": "repeat", "times": veces, "steps": [paso(trabajo, zona), paso(rec, kind="run", nota="suave")]}]
    s = sesion("calidad", "calidad", f"Calidad · {etiqueta}", suma(pasos), pasos,
               calidad_tipo=tipo, objetivo={"zona": zona, "minutos": minutos_obj})
    s["easy"]["steps"] = [paso(s["easy"]["minutes"])]
    return s


# --- corrida variada ---

def tope_z3(minutos: int) -> int:
    """Máximo de minutos en Z3 de una variada de z2_poca_z3: 6' y ≤ 20 % de la sesión."""
    return min(Z3_VARIADA_MAX, int(minutos * Z3_VARIADA_PCT))


def _escalera(B, z3, cap3, sube):
    if z3:
        c = min(cap3, max(1, round(B * 0.2)))
        a = max(1, round((B - c) * 0.4))
        tramos = [(a, "Z1"), (B - c - a, "Z2"), (c, "Z3")]
    else:
        a = max(1, round(B * 0.4))
        tramos = [(a, "Z1"), (B - a, "Z2")]
    return tramos if sube else tramos[::-1]


def _espiga(B, cap3):
    c = min(cap3, max(1, round(B * 0.15)))
    resto = B - c
    a = max(1, round(resto * 0.2))
    medio = resto - 2 * a
    b = medio // 2
    return [(a, "Z1"), (medio - b, "Z2"), (c, "Z3"), (b, "Z2"), (a, "Z1")]


PIRAMIDE_MIN = 13   # minutos de cuerpo: 4 pausas de 1' + bloques 1-2-3-2-1 de al menos 1' por unidad


def _piramide(B, cap3):
    if B < PIRAMIDE_MIN:   # no cabe (el plan ya evita pedirla así); queda una espiga
        return _espiga(B, cap3)
    trabajo = B - 4   # 4 pausas de 1' en Z1
    b1 = max(1, round(trabajo / 9))
    b2 = max(b1 + 1, round(2 * trabajo / 9))
    while trabajo - 2 * b1 - 2 * b2 <= b2 and b2 > b1 + 1:
        b2 -= 1
    b3 = trabajo - 2 * b1 - 2 * b2
    c = max(0, min(cap3, b3 - 1))
    centro = [(b3 - c, "Z2")] + ([(c, "Z3")] if c else [])
    return [(b1, "Z2"), (1, "Z1"), (b2, "Z2"), (1, "Z1"), *centro, (1, "Z1"), (b2, "Z2"), (1, "Z1"), (b1, "Z2")]


def _densidad(B, z3, cap3):
    """Picos iguales; descansos de 1× y luego 2× el pico. El sobrante va al inicio en Z2 (con Z3) o se reparte entre
    los picos de Z2 (sin Z3), de uno en uno desde el primero."""
    for n in range(5, 1, -1):
        descansos = [1, 1, 2, 2][:n - 1]
        unidades = n + sum(descansos)
        if B >= unidades and (not z3 or n <= cap3):
            break
    u = 1 if z3 else B // unidades
    sobra = B - u * unidades
    tramos = [(sobra, "Z2")] if sobra and z3 else []
    extra = [0] * n if z3 else [sobra // n + (i < sobra % n) for i in range(n)]
    for i in range(n):
        tramos.append((u + extra[i], "Z3" if z3 else "Z2"))
        if i < n - 1:
            tramos.append((u * descansos[i], "Z1"))
    return tramos


def _rotativo(B, z3, cap3):
    """Ciclos iguales de bajo-medio(-alto); se elige el tamaño de ciclo que deja menos sobrante (va al inicio en Z1)."""
    if z3:
        opciones = [(k, B // k) for k in range(min(cap3, 4), 0, -1) if B // k >= 3]
        k, largo = min(opciones, key=lambda o: B - o[0] * o[1])
        a = max(1, round((largo - 1) * 0.3))
        ciclo = [(a, "Z1"), (largo - 1 - a, "Z2"), (1, "Z3")]
    else:
        largo = min((3, 4, 5), key=lambda L: (B % L, L))
        k, a = B // largo, 1 if largo == 3 else 2
        ciclo = [(a, "Z1"), (largo - a, "Z2")]
    sobra = B - k * largo
    return ([(sobra, "Z1")] if sobra else []) + ciclo * k


Z1_INICIO_MAX = 2   # el cuerpo puede empezar en Z1 como escalón, no como calentamiento (ese va aparte)


def tramos_variada(tipo: str, B: int, z3: bool, cap3: int) -> list:
    """[(minutos, zona)] del cuerpo de la variada (sin calentar ni enfriar); suma exactamente B. Si empieza en Z1, a lo
    más Z1_INICIO_MAX minutos: lo demás pasa al tramo siguiente."""
    tramos = _tramos_variada(tipo, B, z3, cap3)
    if len(tramos) > 1 and tramos[0][1] == "Z1" and tramos[0][0] > Z1_INICIO_MAX:
        sobra = tramos[0][0] - Z1_INICIO_MAX
        tramos = [(Z1_INICIO_MAX, "Z1"), (tramos[1][0] + sobra, tramos[1][1]), *tramos[2:]]
    return tramos


def _tramos_variada(tipo: str, B: int, z3: bool, cap3: int) -> list:
    if tipo == "ascendente":
        return _escalera(B, z3, cap3, True)
    if tipo == "descendente":
        return _escalera(B, z3, cap3, False)
    if tipo == "espiga":
        return _espiga(B, cap3)
    if tipo == "piramide":
        return _piramide(B, cap3)
    if tipo == "densidad":
        return _densidad(B, z3, cap3)
    if tipo == "rotativo":
        return _rotativo(B, z3, cap3)
    raise ValueError(f"tipo de variada desconocido: {tipo}")


def comprimir(tramos: list) -> list:
    """Agrupa tramos consecutivos que se repiten (periodo 2–4, ≥ 2 veces) en {"veces", "tramos"}."""
    out, i = [], 0
    while i < len(tramos):
        for p in (2, 3, 4):
            k = 1
            while tramos[i:i + p] == tramos[i + k * p:i + (k + 1) * p] and len(tramos[i + k * p:i + (k + 1) * p]) == p:
                k += 1
            if k >= 2:
                out.append({"veces": k, "tramos": tramos[i:i + p]})
                i += k * p
                break
        else:
            out.append(tramos[i])
            i += 1
    return out


def pasos_variada(tipo: str, minutos: int, caminatas: bool, z3: bool) -> list:
    """El cuerpo del tipo en los `minutos` de la sesión. Sin calentamiento ni enfriamiento: esos 5' van aparte (el sitio
    los dibuja y no cuentan). Z1 = caminata si `caminatas`."""
    mk = lambda m, z, **kw: paso(m, z, kind="walk", **kw) if caminatas and z == "Z1" else paso(m, z, **kw)  # noqa: E731
    pasos = []
    for t in comprimir(tramos_variada(tipo, minutos, z3, tope_z3(minutos))):
        if isinstance(t, dict):
            pasos.append({"kind": "repeat", "times": t["veces"], "steps": [mk(m, z) for m, z in t["tramos"]]})
        else:
            pasos.append(mk(*t))
    return pasos


def sesion_variada(tipo: str, minutos: int, caminatas: bool, z3: bool, bloque: int) -> dict:
    pasos = pasos_variada(tipo, minutos, caminatas, z3)
    s = sesion("z2b", "variada", f"Variada · {POR_ID[tipo]['nombre']}", minutos, pasos, variada_tipo=tipo)
    return con_suave_caminatas(s, caminatas, bloque)


# --- prueba de la última semana ---

PRUEBA_MIN = 30        # minutos de la prueba a FC fija y de trote continuo
PRUEBA_5K_MIN = 35     # estimado de unos 5 km a tope (los minutos reales dependen de la persona)
NOTA_FC_FIJA = "FC fija a la mitad de Z2 en ruta plana; alerta en el reloj"
NOTA_TROTE_CONTINUO = "trota en Z2 sin caminar si puedes los 30'; camina solo si pasas el techo"
NOTA_5K = "5 km a tope; lo que cuenta es tu tiempo"


def sesion_prueba(cfg: dict) -> dict:
    """La Larga de la última semana se cambia por una prueba (id `prueba`, tipo `prueba`) para medir la mejora:
    calidad → 5 km a tope; con caminatas → trote continuo; si no → 30' a FC fija. No hay versión suave de una prueba."""
    if cfg["intensidad"] == "calidad":
        tipo, minutos, pasos, nombre = "5k", PRUEBA_5K_MIN, [paso(PRUEBA_5K_MIN, "Z4", NOTA_5K)], "Prueba · 5 km"
    elif cfg["caminatas"]:
        tipo, minutos, pasos, nombre = "trote_continuo", PRUEBA_MIN, [paso(PRUEBA_MIN, "Z2", NOTA_TROTE_CONTINUO)], "Prueba · trote continuo"
    else:
        tipo, minutos, pasos, nombre = "fc_fija", PRUEBA_MIN, [paso(PRUEBA_MIN, "Z2", NOTA_FC_FIJA)], "Prueba · 30 min a FC fija"
    s = sesion("prueba", "prueba", nombre, minutos, pasos, prueba=tipo)
    s["easy"] = {"name": "Prueba", "minutes": minutos, "steps": [dict(p) for p in pasos]}
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
    variada = cfg.get("variada", False)
    nb = bloque + 1
    picos = intensidad == "z2_poca_z3" and not caminatas and bloque >= 1 and not descarga and not variada

    def z2(id_, nombre, minutos, con_picos=False):
        pasos = pasos_con_picos(minutos) if con_picos else pasos_z2(minutos, False, caminatas, nb)
        return con_suave_caminatas(sesion(id_, "z2", nombre, minutos, pasos), caminatas, nb)

    sesiones = [z2("z2a", "Z2 #1", z2a, picos)]
    focus = f"Larga {larga}'" if not descarga else "Descarga"
    if intensidad == "calidad" and not descarga:
        tipos = cfg["calidad_tipos"] or (CALIDAD_TODOS if variada else [])
        tipo = tipos[n_carga % len(tipos)]
        sesiones.append(sesion_calidad(tipo, nb))
        focus += f" · calidad: {ETIQUETA_CALIDAD.get(tipo) or CALIDAD[tipo][2]}"
    elif variada and intensidad != "calidad" and not descarga:
        tipos = VARIADA_TIPOS[intensidad]
        tipo = tipos[n_carga % len(tipos)]
        if tipo == "piramide" and z2b < PIRAMIDE_MIN:   # sesión muy corta: el siguiente tipo que no repita al vecino
            vecinos = {tipos[(n_carga - 1) % len(tipos)], tipos[(n_carga + 1) % len(tipos)]}
            tipo = next(t for t in (tipos[(n_carga + j) % len(tipos)] for j in range(1, len(tipos)))
                        if t not in vecinos and t != "piramide")
        sesiones.append(sesion_variada(tipo, z2b, caminatas, intensidad == "z2_poca_z3", nb))
        focus += f" · variada: {POR_ID[tipo]['nombre']}"
    else:
        sesiones.append(z2("z2b", "Z2 #2", z2b))
    if n == cfg["plan_semanas"]:   # última semana: la Larga se cambia por la prueba
        sesiones.append(sesion_prueba(cfg))
        focus = "Descarga · prueba" if descarga else focus.replace(f"Larga {larga}'", "Prueba")
    else:
        sesiones.append(con_suave_caminatas(
            sesion("larga", "larga", "Larga", larga, pasos_z2(larga, True, caminatas, nb)), caminatas, nb))
    if picos:
        focus += " · picos Z3 opcionales"
    if caminatas:
        focus += f" · trote {TROTE_POR_BLOQUE[nb - 1]}'/camina 1'"
    return {"n": n, "block": bloque + 1, "kind": "descarga" if descarga else "carga", "focus": focus,
            "sessions": sesiones}


def minutos_en(pasos: list, zonas: set) -> int:
    return sum(p["times"] * minutos_en(p["steps"], zonas) if p["kind"] == "repeat" else
               (p["minutes"] if p["zone"] in zonas else 0) for p in pasos)


def verificar(plan: dict, cfg: dict = None) -> None:
    intensidad = (cfg or {}).get("intensidad")
    for w in plan["weeks"]:
        con_z3 = 0
        for s in w["sessions"]:
            if s["tipo"] == "prueba":
                assert suma(s["steps"]) == s["minutes"] == s["easy"]["minutes"], (w["n"], "prueba")
                assert s["prueba"] in ("fc_fija", "trote_continuo", "5k"), (w["n"], "tipo de prueba")
                assert w["n"] == len(plan["weeks"]), (w["n"], "la prueba va solo en la última semana")
                if intensidad == "solo_z2":
                    assert not zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], "prueba solo_z2 con Z3+")
                continue
            assert suma(s["steps"]) == s["minutes"], (w["n"], s["id"])
            assert suma(s["easy"]["steps"]) == s["easy"]["minutes"], (w["n"], s["id"], "suave")
            assert not zonas_de(s["easy"]["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], s["id"], "suave con Z3+")
            if intensidad == "solo_z2":
                assert not zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], s["id"], "solo_z2 con Z3+")
            if s["tipo"] == "variada":
                assert w["kind"] == "carga", (w["n"], "variada en descarga")
                z3 = minutos_en(s["steps"], {"Z3", "Z4", "Z5"})
                assert z3 <= min(Z3_VARIADA_MAX, s["minutes"] * Z3_VARIADA_PCT), (w["n"], "variada con demasiada Z3")
                assert not minutos_en(s["steps"], {"Z4", "Z5"}), (w["n"], "variada con Z4+")
            if s["tipo"] == "larga":
                assert not zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"}, (w["n"], "larga con Z3+")
            con_z3 += bool(zonas_de(s["steps"]) & {"Z3", "Z4", "Z5"})
        assert con_z3 <= 1, (w["n"], "más de una sesión con Z3+")
        if w["kind"] == "descarga":
            assert not any(s["tipo"] in ("calidad", "variada") for s in w["sessions"]), (w["n"], "descarga con calidad o variada")


def generar(cfg: dict) -> dict:
    semanas, n_carga = [], 0
    for n in range(1, cfg["plan_semanas"] + 1):
        w = semana(n, cfg, n_carga)
        n_carga += w["kind"] == "carga"
        semanas.append(w)
    plan = {"start": cfg["plan_start"], "weeks": semanas}
    verificar(plan, cfg)
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
