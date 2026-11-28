"""Motor v6 (F3): genera un plan con las reglas de docs/INVESTIGACION_PLANES.md (§3 y §5) y las decisiones de Pedro.

`generar_v6(entrada) -> plan` con el esquema de plan (ver `pasos`) ({"start", "weeks": [{n, block, kind, focus,
sessions: [{id, tipo, name, minutes, steps, easy, ...}]}]}) más `plan["meta"]` ({"motor": "v6", ...}) y, en cada sesión,
`dia` (0 = lunes … 6 = domingo, el día sugerido).

Cómo afinarlo: todos los umbrales están en `UMBRALES` (aquí arriba) y cada regla es una función chica con su docstring
que dice de dónde sale. Orden de lectura: `generar_v6` -> `esqueleto` -> `volumen_*` -> `repartir` -> `pasos_*`.

Qué NO hace: no calcula zonas de FC (los pasos dicen Z1/Z2/…; el sitio las traduce con las zonas de Garmin) ni mira
cuánto hizo la persona: el plan es fijo y no se ajusta cada semana.
"""
import copy
import math
import re
import sys
from datetime import date, timedelta
from pathlib import Path

RAIZ = Path(__file__).parent.parent
for _p in (RAIZ / "dashboard", RAIZ / "plan"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import pasos as ps  # noqa: E402
from nivel import PISO_NIVEL  # noqa: E402

ZONAS_ALTAS = {"Z3", "Z4", "Z5"}
NIVELES = ("empezando", "base", "corredor")
OBJETIVOS = ("base", "velocidad", "carrera")

# ───────────────────────────── umbrales (todo lo afinable vive aquí) ─────────────────────────────
UMBRALES = {
    # Plan
    "semanas_defecto": 12,
    "dias_defecto": 3,
    "dias_min": 2,
    "dias_max": 5,
    "dias_max_empezando": 3,          # §3.2: N0 no ofrece 4–5 días
    "dias_max_base_sin_calidad": 4,   # §3.2: N1 («Base corta») máx. 4
    "sesion_min": 10,                 # una sesión de menos de 10' no vale la pena: se juntan los minutos en menos sesiones
    "inicio_sin_historial": 60,       # si la entrada no trae `inicio_minutos`: 3 × 20' de escalera
    # Progresión (Pedro: máx. +10 %; más solo con `permitir_mas`)
    "progresion_pct": 0.10,
    "progresion_mas_pct": 0.15,       # con permitir_mas=True (nunca se anima)
    "sesion_pct": 0.10,               # ninguna sesión > 110 % de la mayor de las últimas 4 semanas (§3.9)
    "ventana_semanas": 4,
    "tope_semana_min": {"empezando": 90, "base": 150, "corredor": 240},   # volumen semanal máximo por nivel (§3.1, §3.3)
    # Descargas (§3.5): 3:1, y 2:1 con 50+ años o 3+ días intensos
    "ciclo": 4,
    "ciclo_mayor": 3,
    "mayor_edad": 50,
    "intensos_dias": 3,
    "descarga_pct": 0.70,             # 3:1: −30 %
    "descarga_pct_mayor": 0.75,       # 2:1: −25 %
    # La larga (§3.3, §3.9)
    "larga_reparto": {2: 0.55, 3: 0.38, 4: 0.30, 5: 0.27},   # fracción de la semana que se intenta dar a la larga
    "larga_tope_pct": {2: 0.60, 3: 0.40, 4: 0.33, 5: 0.30},  # tope duro (2 días: ≤ 2× la otra ≈ 67 %)
    "larga_vs_facil": 2.0,
    "tope_larga_min": {"empezando": 30, "base": 75, "corredor": 105},
    "tope_larga_base_sin_calidad": 10,   # Base sin calidad desbloqueada: la larga ≤ trote continuo + 10' (§3.3 N1), mínimo 35'
    "tope_larga_base_sin_calidad_min": 35,
    "tope_larga_carrera": {5: 45, 10: 75, 21: 120, 42: 150},   # larga objetivo por distancia (§3.7)
    # Escalera de trote/caminata (§3.6): (trote, caminata) en minutos; el último escalón es trote continuo
    "escalera": [(1, 2), (1, 1), (2, 1), (3, 1), (5, 1), (8, 1), (12, 1), None],
    "escalera_entrada": [(0, 1), (3, 2), (5, 3), (8, 4), (12, 5), (18, 6), (25, 7)],   # (si C ≥ …, escalón de entrada) con C = trote continuo en min; sin trote (C = 0) → 0
    "sesiones_por_escalon": 3,        # se sube de escalón tras 3 sesiones: con 3 días es 1 semana, con 2 días son 2
    # Calidad (§3.4): solo con base. Escalera: 1 tipo nuevo por bloque
    "calidad_base_semanas": 6,        # semanas consistentes seguidas
    "calidad_base_continuo_min": 30,
    "calidad_base_volumen_min": 90,
    "calidad_corredor_continuo_min": 20,   # el nivel Corredor desbloquea, salvo que su evidencia diga que ni trota 20'
    "calidad_etapa_inicial": {"base": 0, "corredor": 1},   # Corredor se salta las aceleraciones
    "calidad_escalera": {
        "base": ["aceleraciones", "fartlek", "tempo_z3", "tempo_z3"],
        "velocidad": ["aceleraciones", "fartlek", "tempo_z3", "intervalos"],
        "carrera": ["aceleraciones", "fartlek", "tempo_z3", "threshold"],
    },
    "calidad_tope_nivel": {"base": 0.10, "corredor": 0.15},   # % de la semana en Z3+ (§3.9: ≤ 10 % N2, ≤ 20 % N3)
    "calidad_menos_un_renglon": True,   # con 3+ días intensos el tope baja un renglón (§3.4)
    # Carrera (§3.7). taper: fracción del pico por semana; la última es la semana de la carrera (sin larga)
    "taper": {5: [0.60], 10: [0.80, 0.55], 21: [0.75, 0.50], 42: [0.80, 0.60, 0.45]},
    "carrera_semanas_cortas": 4,      # carrera a menos semanas que esto: aviso «plan muy corto» (se permite igual)
    "semanas_minimas": {   # desde cada nivel; None = no se recomienda
        5: {"empezando": 9, "base_corta": 6, "base": 4, "corredor": 4},
        10: {"empezando": 16, "base_corta": 10, "base": 8, "corredor": 6},
        21: {"empezando": None, "base_corta": 16, "base": 12, "corredor": 10},
        42: {"empezando": None, "base_corta": None, "base": 18, "corredor": 16},
    },
    "ajuste_piso": PISO_NIVEL,   # piso duro por nivel (3 × 15' para Empezando); lo usa la generación del plan
}

# Calidad: zona, tope de Z3+ como % de la semana, mínimos para que valga la pena, estructura. Las claves de tipo las entiende el sitio.
CALIDAD_TIPOS = {
    "fartlek": {"zona": "Z3", "tope_pct": 0.05, "min_trabajo": 3, "max_picos": 6, "pico_min": 1, "rec_min": 2},
    "tempo_z3": {"zona": "Z3", "tope_pct": 0.10, "min_trabajo": 10, "reps": 2, "bloque_max": 12, "bloque_min": 5, "rec_min": 3},
    "threshold": {"zona": "Z4", "tope_pct": 0.15, "min_trabajo": 12, "reps": 3, "bloque_max": 5, "bloque_min": 4, "rec_min": 2},
    "intervalos": {"zona": "Z4", "tope_pct": 0.15, "min_trabajo": 10, "reps_max": 6, "reps_min": 5, "bloque_min": 2, "bloque_max": 2, "rec_min": 2},
}
CALENTAR_MIN = 10
ETIQUETA_CALIDAD = {"fartlek": "Fartlek", "tempo_z3": "Tempo Z3", "threshold": "Threshold", "intervalos": "Intervalos"}
NOTA_RELLENO = "suave hasta completar"
NOTA_ACELERACIONES = "al final, 4 a 6 aceleraciones de 15 s: sueltas, sin forzar"
LETRAS = "abcdefgh"


def _u(clave):
    return UMBRALES[clave]


# ───────────────────────────── entrada ─────────────────────────────

def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _meta(e: dict) -> dict:
    """Normaliza la meta: {"tipo": ninguna|base|velocidad|carrera, "km", "fecha", "semanas_hasta"}."""
    m = e.get("meta")
    if isinstance(m, str) or m is None:
        return {"tipo": m or "ninguna"}
    tipo = m.get("tipo") or ("carrera" if (m.get("km") or m.get("distancia_km")) else "ninguna")
    return {"tipo": tipo, "km": m.get("km") or m.get("distancia_km"), "fecha": m.get("fecha"), "semanas_hasta": m.get("semanas_hasta")}


def _calidad_desde(v):
    """`calidad_desde`: "auto" (falta: la regla de desbloqueo de siempre), None (la persona no quiere calidad) o la semana (>= 2) donde empieza."""
    if v == "auto":
        return "auto"
    if v is None or v is False:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError("calidad_desde debe ser una semana (2 o más) o None") from None
    if n < 2:
        raise ValueError("la calidad no puede empezar antes de la semana 2")
    return n


def normalizar_entrada(entrada: dict) -> dict:
    """Entrada con todos sus valores por defecto (una clave que falte nunca rompe) y validada."""
    u, e = UMBRALES, dict(entrada)
    nivel = e.get("nivel") or "base"
    if nivel not in NIVELES:
        raise ValueError(f"nivel '{nivel}' no existe; hay: {', '.join(NIVELES)}")
    ev = dict(e.get("evidencia") or {})
    meta = _meta(e)
    if meta["tipo"] == "carrera" and int(meta.get("km") or 0) not in u["taper"]:
        raise ValueError("la carrera debe ser de 5, 10, 21 o 42 km")
    objetivo = e.get("objetivo") or {"velocidad": "velocidad", "carrera": "carrera"}.get(meta["tipo"], "base")
    if objetivo not in OBJETIVOS:
        raise ValueError(f"objetivo '{objetivo}' no existe; hay: {', '.join(OBJETIVOS)}")
    inicio = str(e.get("inicio") or date.today().isoformat())
    if date.fromisoformat(inicio).weekday() != 0:
        inicio = _lunes(date.fromisoformat(inicio)).isoformat()
    return {
        "nivel": nivel, "dias": int(e.get("dias") or u["dias_defecto"]), "dias_intensos": list(e.get("dias_intensos", ev.get("dias_intensos", []))),
        "meta": meta, "objetivo": objetivo, "inicio": inicio, "evidencia": ev, "permitir_mas": bool(e.get("permitir_mas", False)),
        "zonas": e.get("zonas"), "edad": int(e.get("edad") or 35), "semanas": int(e.get("semanas") or u["semanas_defecto"]),
        "inicio_minutos": e.get("inicio_minutos"),
        "calidad_desde": _calidad_desde(e.get("calidad_desde", "auto")),
    }


# ───────────────────────────── reglas (una función chica cada una) ─────────────────────────────

def calidad_desbloqueada(nivel: str, ev: dict) -> bool:
    """§3.4: calidad solo para quien ya tiene base. Nivel Corredor, o Base con ≥ 6 semanas consistentes seguidas, ≥ 30'
    de trote seguido y ≥ 90'/semana (promedio de 4 semanas). Empezando nunca. (Sin lesión ni opt-in: eso lo pregunta la web.)"""
    u = UMBRALES
    if nivel == "corredor":
        return ev.get("trote_continuo_min", u["calidad_corredor_continuo_min"]) >= u["calidad_corredor_continuo_min"]
    if nivel != "base":
        return False
    return (ev.get("semanas_consistentes", 0) >= u["calidad_base_semanas"]
            and ev.get("trote_continuo_min", 0) >= u["calidad_base_continuo_min"]
            and ev.get("minutos_sem_prom", 0) >= u["calidad_base_volumen_min"])


def ciclo_descarga(edad: int, dias_intensos: list) -> int:
    """§3.5: descarga cada 4 semanas (3:1); cada 3 (2:1) con 50+ años o 3+ días intensos por semana."""
    u = UMBRALES
    return u["ciclo_mayor"] if edad >= u["mayor_edad"] or len(dias_intensos) >= u["intensos_dias"] else u["ciclo"]


def dias_efectivos(nivel: str, dias: int, calidad: bool) -> tuple:
    """(días, aviso o None). §3.2: Empezando máx. 3; Base sin calidad desbloqueada máx. 4; el resto 2–5."""
    u = UMBRALES
    pedidos = min(max(dias, u["dias_min"]), u["dias_max"])
    tope = u["dias_max_empezando"] if nivel == "empezando" else (u["dias_max_base_sin_calidad"] if nivel == "base" and not calidad else u["dias_max"])
    if pedidos > tope:
        return tope, {"clave": "dias_limitados", "pedidos": pedidos, "dias": tope,
                      "texto": f"Con tu nivel actual lo más seguro son {tope} días por semana; empezamos con {tope}."}
    return pedidos, None


def escalon_de_entrada(trote_continuo_min: float) -> int:
    """§3.6: escalón (0 = 1/2 … 6 = 12/1, 7 = continuo) según el trote seguido más largo."""
    entrada = 0
    for c, esc in UMBRALES["escalera_entrada"]:
        if trote_continuo_min > 0 and trote_continuo_min >= c:
            entrada = esc
    return entrada


def escalon_en(n: int, tipos: list, e0: int, dias: int) -> int:
    """Escalón de la semana n: sube uno cada `ceil(3 / días)` semanas de carga; en descarga y carrera se queda donde está (§3.6)."""
    por = max(1, math.ceil(UMBRALES["sesiones_por_escalon"] / max(dias, 1)))
    hechas = sum(1 for k in tipos[:n - 1] if k == "carga")
    if tipos[n - 1] != "carga":   # descarga o carrera: el mismo escalón de la última semana de carga
        hechas = max(hechas - 1, 0)
    return min(e0 + hechas // por, len(UMBRALES["escalera"]) - 1)


def esqueleto(n_semanas: int, ciclo: int, semanas_taper: int) -> list:
    """Tipo de cada semana: carga | descarga | taper | carrera. Descarga tras `ciclo − 1` semanas de carga seguidas (§3.5);
    al final de un plan de carrera, las `semanas_taper` últimas son taper y la última es la carrera (§3.7)."""
    semanas_taper = min(semanas_taper, n_semanas)
    cuerpo, tipos, seguidas = n_semanas - semanas_taper, [], 0
    for _ in range(cuerpo):
        if seguidas == ciclo - 1:
            tipos.append("descarga")
            seguidas = 0
        else:
            tipos.append("carga")
            seguidas += 1
    return tipos + ["taper"] * (semanas_taper - 1) + (["carrera"] if semanas_taper else [])


def volumen_carga(ultima_carga: int, tras_descarga: bool, tope: int, pct: float) -> int:
    """§3.9: cada semana de carga ≤ +pct sobre la última de carga; tras una descarga se vuelve al volumen de antes, no más."""
    return min(tope, ultima_carga if tras_descarga else int(ultima_carga * (1 + pct)))


def volumen_descarga(ultima_carga: int, pct: float) -> int:
    """§3.5: la descarga baja `1 − pct` de la última semana de carga (misma frecuencia, sin calidad)."""
    return int(ultima_carga * pct)


def tope_sesion(maximos_previos: list, historial_max: float, n: int) -> int | None:
    """§3.9: ninguna sesión > 110 % de la mayor de las últimas 4 semanas. Las primeras 4 semanas cuenta también el historial real."""
    v = _u("ventana_semanas")
    ventana = list(maximos_previos[-v:]) + ([historial_max] if n <= v else [])
    mayor = max(ventana, default=0)
    return int(mayor * (1 + _u("sesion_pct"))) if mayor > 0 else None


def tope_larga(nivel: str, carrera: dict | None, calidad: bool, ev: dict) -> int:
    """Tope de la larga: la del nivel (§3.3), la objetivo de la carrera (§3.7), y Base sin calidad ≤ trote continuo + 10' (mín. 35')."""
    u = UMBRALES
    if carrera:
        tope = u["tope_larga_carrera"][carrera["km"]]
    else:
        tope = u["tope_larga_min"][nivel]
    if nivel == "base" and not calidad:
        tope = min(tope, max(u["tope_larga_base_sin_calidad_min"], int(ev.get("trote_continuo_min", 0)) + u["tope_larga_base_sin_calidad"]))
    return tope


def repartir(total: int, dias: int, tope_ses: int | None, tope_lg: int) -> list:
    """Minutos [larga, fácil, fácil…] (la suma puede quedar < `total` si los topes no dejan más). §3.9: la larga ≤ 40 % (3 días), 33 % (4),
    30 % (5) de la semana y ≤ 2× una fácil; ninguna sesión pasa de `tope_ses` (110 % de la mayor de 30 días); la larga no pasa de `tope_lg`."""
    u = UMBRALES
    if dias == 1:
        return [min(total, tope_ses or total, tope_lg)]
    pct, vs, cap, n_f = u["larga_tope_pct"][dias], u["larga_vs_facil"], tope_ses or total, dias - 1

    def facil(lg):
        return max(1, min((total - lg) // n_f, cap, lg))
    larga = min(int(u["larga_reparto"][dias] * total), tope_lg, cap)
    while larga > 1:
        f = facil(larga)
        if larga <= pct * (larga + f * n_f) + 1e-9 and larga <= vs * f + 1e-9:
            break
        larga -= 1
    faciles = [facil(larga)] * n_f
    resto, i = total - larga - sum(faciles), 0
    while resto > 0 and any(x < min(cap, larga) for x in faciles):   # minutos sueltos: de uno en uno a las fáciles que aún caben
        if faciles[i % n_f] < min(cap, larga):
            faciles[i % n_f] += 1
            resto -= 1
        i += 1
    while larga > 1 and larga > pct * (larga + sum(faciles)) + 1e-9:
        larga -= 1
    return [larga] + sorted(faciles)


# ───────────────────────────── pasos de cada sesión ─────────────────────────────

NOTA_FACIL = "Z2 o un ritmo en el que puedas platicar"   # las sesiones fáciles del v6 (con su traducción en motor.nota.facil)


def pasos_continuo(minutos: int, larga: bool) -> list:
    return [ps.paso(minutos, "Z2", ps.NOTA_LARGA if larga else NOTA_FACIL)]


def pasos_tc(minutos: int, trote: int, camina: int) -> list:
    """Trote/caminata (§3.6): `n` repeticiones de trote/caminata y el sobrante (trote primero). Suma exactamente `minutos`."""
    n, resto = divmod(minutos, trote + camina)
    par = [ps.paso(trote), ps.paso(camina, "Z1", kind="walk")]
    pasos = par if n == 1 else ([{"kind": "repeat", "times": n, "steps": par}] if n else [])
    if resto:
        pasos.append(ps.paso(min(resto, trote)))
        if resto > trote:
            pasos.append(ps.paso(resto - trote, "Z1", kind="walk"))
    return pasos


def pasos_facil(minutos: int, escalon: tuple | None, larga: bool) -> list:
    return pasos_continuo(minutos, larga) if escalon is None else pasos_tc(minutos, *escalon)


def _sesion(id_: str, tipo: str, nombre: str, minutos: int, pasos: list, escalon: tuple | None = None, **extra) -> dict:
    """La sesión con el esquema de plan; su versión suave repite el escalón con menos minutos."""
    s = ps.sesion(id_, tipo, nombre, minutos, pasos, **extra)
    if escalon is not None:
        sm = min(minutos, ps.suave(minutos))
        s["easy"] = {"name": "Suave", "minutes": sm, "steps": pasos_tc(sm, *escalon)}
    return s


def pasos_calidad(tipo: str, minutos: int, trabajo: int):
    """(pasos, minutos de trabajo en Z3+) de una sesión de calidad de `minutos` con a lo más `trabajo` minutos de trabajo, o None si no cabe.
    Estructura §3.4: 10' Z2 · trabajo con recuperaciones · Z2 suave hasta completar. Sin calentar/enfriar aparte (el sitio los dibuja)."""
    c = CALIDAD_TIPOS[tipo]
    calen = ps.paso(CALENTAR_MIN, "Z2", "suave")
    if tipo == "fartlek":   # picos de 1' en Z3 con 2' fáciles; el último pico no lleva recuperación
        n = min(c["max_picos"], trabajo, (minutos - CALENTAR_MIN + c["rec_min"]) // (c["pico_min"] + c["rec_min"]))
        if n < c["min_trabajo"]:
            return None
        pasos = [calen]
        for i in range(n):
            pasos.append(ps.paso(c["pico_min"], c["zona"]))
            if i < n - 1:
                pasos.append(ps.paso(c["rec_min"], "Z2", "suave"))
        usado, z3 = CALENTAR_MIN + n * c["pico_min"] + (n - 1) * c["rec_min"], n * c["pico_min"]
    else:
        reps = c.get("reps") or min(c["reps_max"], trabajo // c["bloque_min"])
        bloque = min(c["bloque_max"], trabajo // max(reps, 1))
        while reps and CALENTAR_MIN + reps * (bloque + c["rec_min"]) > minutos:
            if "reps_max" in c:
                reps -= 1
            else:
                bloque -= 1
        if not reps or bloque < c["bloque_min"] or reps * bloque < c["min_trabajo"] or ("reps_max" in c and reps < c["reps_min"]):
            return None
        pasos = [calen, {"kind": "repeat", "times": reps,
                         "steps": [ps.paso(bloque, c["zona"]), ps.paso(c["rec_min"], "Z2", "suave")]}]
        usado, z3 = CALENTAR_MIN + reps * (bloque + c["rec_min"]), reps * bloque
    if minutos > usado:
        pasos.append(ps.paso(minutos - usado, "Z2", NOTA_RELLENO))
    return pasos, z3


def sesion_calidad(tipo: str, minutos: int, trabajo: int, id_: str = "calidad"):
    """Sesión de calidad `tipo` o None si no cabe. Con `calidad_tipo` y `objetivo`."""
    r = pasos_calidad(tipo, minutos, trabajo)
    if r is None:
        return None
    pasos, z3 = r
    s = ps.sesion(id_, "calidad", f"Calidad · {ETIQUETA_CALIDAD[tipo]}", minutos, pasos,
                        calidad_tipo=tipo, objetivo={"zona": CALIDAD_TIPOS[tipo]["zona"], "minutos": z3})
    s["easy"]["steps"] = [ps.paso(s["easy"]["minutes"])]
    return s


def calidad_de_la_semana(n: int, ciclo: int, e: dict, minutos: int, semana_total: int, intensos_altos: bool, n0: int = 1):
    """Elige la calidad de la semana n (§3.4): escalera según `objetivo`, un peldaño nuevo por bloque; con 3+ días intensos baja un renglón;
    el trabajo en Z3+ no pasa del tope del tipo ni del nivel. Si el tipo no cabe en la sesión baja al anterior; lo último son aceleraciones
    (Z2, sin Z3). `n0` = semana donde arrancó la escalera (1 sin `calidad_desde`). Devuelve (tipo, sesión o None); None = aceleraciones."""
    u = UMBRALES
    escalera = u["calidad_escalera"][e["objetivo"]]
    etapa = u["calidad_etapa_inicial"][e["nivel"]] + (n - n0) // ciclo
    if intensos_altos and u["calidad_menos_un_renglon"]:
        etapa -= 1
    etapa = min(max(etapa, 0), len(escalera) - 1)
    while etapa > 0:
        tipo = escalera[etapa]
        tope = int(min(CALIDAD_TIPOS[tipo]["tope_pct"], u["calidad_tope_nivel"][e["nivel"]]) * semana_total)
        s = sesion_calidad(tipo, minutos, tope)
        if s:
            return tipo, s
        etapa -= 1
    return "aceleraciones", None


def sesion_aceleraciones(id_: str, nombre: str, minutos: int) -> dict:
    """Etapa 1 de la calidad (§3.4): Z2 con 4–6 aceleraciones de 15 s al final. No cuentan como Z3, por eso todo va en Z2."""
    cola = min(5, minutos)
    pasos = ([ps.paso(minutos - cola, "Z2", NOTA_FACIL)] if minutos > cola else []) + [ps.paso(cola, "Z2", NOTA_ACELERACIONES)]
    return ps.sesion(id_, "z2", nombre, minutos, pasos, nota=NOTA_ACELERACIONES)


# ───────────────────────────── foco de la semana y verificación ─────────────────────────────

def _escalon_de_pasos(pasos: list):
    """(trote, caminata) del patrón trote/caminata de unos pasos, o None si son continuos."""
    for p in pasos:
        if p["kind"] == "repeat":
            hijos = p["steps"]
            if len(hijos) >= 2 and hijos[1]["kind"] == "walk":
                return hijos[0]["minutes"], hijos[1]["minutes"]
    for a, b in zip(pasos, pasos[1:]):
        if a["kind"] == "run" and b["kind"] == "walk":
            return a["minutes"], b["minutes"]
    return None


def foco(kind: str, sesiones: list, evento: str = "", carrera: str = "") -> str:
    """Resumen de la semana en el formato del sitio («Larga 40' · calidad: Fartlek · trote 3'/camina 1'»), para que el sitio lo traduzca."""
    if evento == "carrera":
        return f"Semana de carrera · {carrera}"
    if evento == "descarga_carrera":
        return "Descarga previa a la carrera"
    larga = next((s for s in sesiones if s["tipo"] == "larga"), None)
    partes = ["Descarga" if kind == "descarga" else (f"Larga {larga['minutes']}'" if larga else "Carga")]
    cal = next((s for s in sesiones if s["tipo"] == "calidad"), None)
    if cal:
        partes.append(f"calidad: {ETIQUETA_CALIDAD[cal['calidad_tipo']]}")
    elif any(s.get("nota") == NOTA_ACELERACIONES for s in sesiones):
        partes.append("aceleraciones")
    esc = next((e for s in sesiones if (e := _escalon_de_pasos(s["steps"]))), None)
    if esc:
        partes.append(f"trote {esc[0]}'/camina {esc[1]}'")
    return " · ".join(partes)


def minutos_semana(w: dict) -> int:
    return sum(s["minutes"] for s in w["sessions"])


def verificar(plan: dict) -> None:
    """Pasos que suman, suave sin Z3+, la larga sin Z3+, a lo más una sesión con Z3+ por semana, ids únicos, Empezando sin Z3+,
    calidad solo en semanas de carga y nunca en la semana 1, y la larga dentro de su tope."""
    assert plan.get("meta", {}).get("motor") == "v6", "falta meta.motor"
    u = UMBRALES
    empezando = plan["meta"]["nivel"] == "empezando"
    for w in plan["weeks"]:
        ses = w["sessions"]
        assert ses, (w["n"], "semana sin sesiones")
        assert len({s["id"] for s in ses}) == len(ses), (w["n"], "ids repetidos")
        assert all(s["minutes"] >= 1 for s in ses), (w["n"], "sesión vacía")
        con_z3 = 0
        for s in ses:
            assert ps.suma(s["steps"]) == s["minutes"], (w["n"], s["id"])
            assert ps.suma(s["easy"]["steps"]) == s["easy"]["minutes"], (w["n"], s["id"], "suave")
            assert not ps.zonas_de(s["easy"]["steps"]) & ZONAS_ALTAS, (w["n"], s["id"], "suave con Z3+")
            if s["tipo"] == "larga":
                assert not ps.zonas_de(s["steps"]) & ZONAS_ALTAS, (w["n"], "larga con Z3+")
            if empezando:
                assert not ps.zonas_de(s["steps"]) & ZONAS_ALTAS, (w["n"], s["id"], "Empezando con Z3+")
            if s["tipo"] == "calidad":
                assert w["kind"] == "carga" and w["n"] > 1, (w["n"], "calidad fuera de una semana de carga o en la semana 1")
            con_z3 += bool(ps.zonas_de(s["steps"]) & ZONAS_ALTAS)
        assert con_z3 <= 1, (w["n"], "más de una sesión con Z3+")
        if w["kind"] == "descarga":
            assert not any(s["tipo"] == "calidad" for s in ses), (w["n"], "descarga con calidad")
        if len(ses) > 1:
            larga = next((s for s in ses if s["tipo"] == "larga"), None)
            if larga:
                assert larga["minutes"] <= u["larga_tope_pct"][min(len(ses), 5)] * minutos_semana(w) + 1e-9, (w["n"], "la larga pasa de su tope")


# ───────────────────────────── generar ─────────────────────────────

def _carrera(e: dict, semanas_hasta: int | None) -> dict | None:
    m = e["meta"]
    if m["tipo"] != "carrera":
        return None
    km = int(m["km"])
    dia = date.fromisoformat(str(m["fecha"])).weekday() if m.get("fecha") else None
    return {"km": km, "semanas": semanas_hasta, "dia": dia, "nombre": f"{km}K"}


def _semanas_hasta_carrera(e: dict) -> int | None:
    m = e["meta"]
    if m["tipo"] != "carrera":
        return None
    if m.get("semanas_hasta"):
        return int(m["semanas_hasta"])
    if m.get("fecha"):
        n = (date.fromisoformat(str(m["fecha"])) - date.fromisoformat(e["inicio"])).days // 7 + 1
        if n < 1:
            raise ValueError("la fecha de la carrera es antes del inicio del plan")
        return n
    raise ValueError("la carrera necesita fecha o semanas_hasta")


def avisos_de(e: dict, calidad: bool, n_semanas: int, carrera: dict | None, dias_aviso: dict | None) -> list:
    """Avisos de la vista previa: días limitados, carrera sin tiempo suficiente (§3.7), pausa. Cada uno: {clave, texto (es), …datos}."""
    avisos = [dias_aviso] if dias_aviso else []
    if carrera:
        clave_nivel = "base" if e["nivel"] == "base" and calidad else ("base_corta" if e["nivel"] == "base" else e["nivel"])
        minimas = UMBRALES["semanas_minimas"][carrera["km"]][clave_nivel]
        if minimas is None:
            avisos.append({"clave": "carrera_no_recomendada", "km": carrera["km"], "texto":
                           f"Un {carrera['km']}K desde tu nivel actual no es lo más seguro: te sugerimos una distancia menor o llegar con trote y caminata."})
        elif n_semanas < minimas:
            avisos.append({"clave": "carrera_poco_tiempo", "km": carrera["km"], "semanas": n_semanas, "minimas": minimas, "texto":
                           f"Para un {carrera['km']}K desde tu nivel se recomiendan al menos {minimas} semanas y tienes {n_semanas}: "
                           "puedes elegir otra distancia o llegar con trote y caminata. Si sigues, el plan va lo más suave posible."})
    if carrera and n_semanas < UMBRALES["carrera_semanas_cortas"]:
        avisos.append({"clave": "carrera_cerca", "semanas": n_semanas, "texto":
                       f"Tu carrera es en {n_semanas} semana(s): el plan es muy corto. Puedes elegir otra distancia, llegar con trote y caminata, "
                       "o seguir con este plan corto, que va lo más suave posible."})
    if e["evidencia"].get("desentrenamiento"):
        avisos.append({"clave": "pausa", "texto": "Llevas varios días sin correr: empezamos más despacio."})
    return avisos


def porques_de(e: dict, inicio: int, ciclo: int, calidad: bool, carrera: dict | None, n_semanas: int) -> list:
    """Las líneas de «por qué así» de la vista previa: [{clave, texto (es), params}]."""
    pct = 100 * (UMBRALES["progresion_mas_pct"] if e["permitir_mas"] else UMBRALES["progresion_pct"])
    prom = e["evidencia"].get("minutos_sem_prom")
    out = [{"clave": "inicio", "params": {"min": inicio, "promedio": prom},
            "texto": f"Empiezas con {inicio} min porque tu promedio reciente es {prom:g} min." if prom else f"Empiezas con {inicio} min: un arranque suave."},
           {"clave": "sube", "params": {"pct": pct}, "texto": f"Sube como máximo {pct:g} % por semana."},
           {"clave": "descarga", "params": {"ciclo": ciclo}, "texto": f"Cada {ciclo} semanas hay una de descarga para que el cuerpo asimile."},
           {"clave": "calidad_si" if calidad else "calidad_no", "params": {}, "texto":
            "Ya tienes base: se suman partes más rápidas, poco a poco." if calidad else "Por ahora todo suave: así se construye la base."}]
    if e["nivel"] == "empezando":
        out.append({"clave": "escalera", "params": {}, "texto": "Alternas trote y caminata; el trote crece cuando te sientes bien."})
    if carrera:
        out.append({"clave": "carrera", "params": {"km": carrera["km"], "semanas": n_semanas},
                    "texto": f"La última semana se reduce para llegar descansado a tu {carrera['nombre']}."})
    return out


def generar_v6(entrada: dict) -> dict:
    """Plan v6. `entrada`: nivel (empezando|base|corredor), dias (2–5), dias_intensos (lunes = 0), meta (None|"ninguna"|"base"|"velocidad"|
    {"km", "fecha" | "semanas_hasta"}), objetivo (base|velocidad|carrera; define la calidad), inicio (lunes ISO), evidencia (la de nivel.py),
    inicio_minutos (semana 1), calidad_desde (semana >= 2 donde empieza la calidad, o None = sin calidad; si falta rige `calidad_desbloqueada`), permitir_mas, zonas (no se usa: las zonas las pone el sitio con las de Garmin), edad, semanas (sin carrera)."""
    e = normalizar_entrada(entrada)
    u, ev, nivel = UMBRALES, e["evidencia"], e["nivel"]
    hasta = _semanas_hasta_carrera(e)
    carrera = _carrera(e, hasta)
    n_semanas = hasta if carrera else e["semanas"]
    cd = e["calidad_desde"]
    if cd == "auto":
        base = calidad_desbloqueada(nivel, ev)            # ¿tiene base para la calidad?
        calidad = base and not ev.get("desentrenamiento")   # y no viene de una pausa
        n0 = 1
    else:   # la persona decide: Empezando nunca; Base/Corredor desde la semana elegida (la semana 1 nunca), ni siquiera tras una pausa
        base = calidad = cd is not None and nivel != "empezando"
        n0 = None
    dias, dias_aviso = dias_efectivos(nivel, e["dias"], base)
    ciclo = ciclo_descarga(e["edad"], e["dias_intensos"])
    intensos_altos = len(e["dias_intensos"]) >= u["intensos_dias"]
    taper = u["taper"][carrera["km"]] if carrera else []
    tipos = esqueleto(n_semanas, ciclo, len(taper))
    if n0 is None:   # primera semana de carga desde `calidad_desde`; si no hay ninguna, no hay calidad
        n0 = next((k for k, t in enumerate(tipos, 1) if k >= (cd or 2) and t == "carga"), None) if calidad else None
        calidad = n0 is not None
    pct_sube = u["progresion_mas_pct"] if e["permitir_mas"] else u["progresion_pct"]
    pct_descarga = u["descarga_pct_mayor"] if ciclo == u["ciclo_mayor"] else u["descarga_pct"]
    prom = ev.get("minutos_sem_prom")
    inicio = int(e["inicio_minutos"] if e["inicio_minutos"] is not None else
                 (prom * (1 + u["sesion_pct"]) if prom else u["inicio_sin_historial"]))
    inicio = max(inicio, u["ajuste_piso"][nivel])   # la semana 1 nunca baja del piso del nivel (promedio diminuto = sin datos)
    tope_vol = max(u["tope_semana_min"][nivel], inicio)
    tope_lg = tope_larga(nivel, carrera, base, ev)
    e0 = escalon_de_entrada(float(ev.get("trote_continuo_min", 0))) if nivel == "empezando" else None
    hist_max = float(ev.get("sesion_max_30d", 0))

    semanas, maximos, totales, ultima_carga, tope_alcanzado = [], [], [], inicio, False
    for n, kind in enumerate(tipos, 1):
        if kind == "carga":
            T = inicio if n == 1 else volumen_carga(ultima_carga, tipos[n - 2] == "descarga", tope_vol, pct_sube)
            if n > 1 and tipos[n - 2] != "descarga" and int(ultima_carga * (1 + pct_sube)) > tope_vol:
                tope_alcanzado = True   # esta semana quedó limitada por el máximo del nivel
        elif kind == "descarga":
            T = volumen_descarga(ultima_carga, pct_descarga)
        else:   # taper / carrera: fracción del pico (la semana más alta hasta 2 semanas antes de la carrera, como mide el simulador)
            pico = max(totales[:max(n_semanas - 2, 1)], default=inicio)
            T = int(taper[n - (n_semanas - len(taper)) - 1] * pico)
        ts = tope_sesion(maximos, hist_max, n)
        if ts and kind == "carga":
            ts = max(ts, -(-min(T, u["ajuste_piso"][nivel]) // dias))   # el piso repartido en los días se puede cumplir (como `sesion_110`)
        if nivel == "empezando":
            ts = min(ts or u["tope_larga_min"]["empezando"], u["tope_larga_min"]["empezando"])
        d = max(1, min(dias - (kind == "carrera"), T // u["sesion_min"]))
        if ts:   # si las sesiones de `sesion_min` no caben en el tope de sesión, se reparte en más sesiones (nunca más que los días)
            d = min(dias - (kind == "carrera"), max(d, math.ceil(T / ts)))
        minutos = _carrera_semana(T, d, ts) if kind == "carrera" else repartir(T, d, ts, tope_lg)
        esc = u["escalera"][escalon_en(n, tipos, e0, dias)] if nivel == "empezando" else None
        sesiones = _armar_semana(n, kind, minutos, esc, e, calidad, ciclo, intensos_altos, carrera, T, n0 or 1)
        w = {"n": n, "block": (n - 1) // u["ciclo"] + 1, "kind": "carga" if kind == "carga" else "descarga", "focus": "", "sessions": sesiones}
        if kind in ("carrera", "taper"):
            w["evento"] = "carrera" if kind == "carrera" else "descarga_carrera"
            w["taper"] = taper[n - (n_semanas - len(taper)) - 1]   # fracción del pico
        w["focus"] = foco(w["kind"], sesiones, w.get("evento", ""), carrera["nombre"] if carrera else "")
        semanas.append(w)
        totales.append(minutos_semana(w))
        maximos.append(max(s["minutes"] for s in sesiones))
        if kind == "carga":
            ultima_carga = totales[-1]
    meta = {"motor": "v6", "nivel": nivel, "dias": dias, "objetivo": e["objetivo"], "ciclo": ciclo, "calidad": calidad,
            "tope_alcanzado": tope_alcanzado, "semanas": n_semanas, "inicio_minutos": inicio, "avisos": avisos_de(e, base, n_semanas, carrera, dias_aviso),
            "porque": porques_de(e, inicio, ciclo, calidad, carrera, n_semanas),
            "entrada": e}   # la entrada ya normalizada: con ella `con_carrera` rehace la cola del plan al agregar o quitar una carrera
    if carrera:
        meta["carrera"] = {"km": carrera["km"], "semanas": n_semanas}
    plan = {"start": e["inicio"], "weeks": semanas, "meta": meta}
    verificar(plan)
    return plan


def _carrera_semana(T: int, d: int, ts: int | None) -> list:
    """Semana de la carrera: sin larga, `d` sesiones cortas casi iguales (la carrera misma no va en el plan)."""
    base, resto = divmod(min(T, (ts or T) * d), d)
    return [base + (1 if i < resto else 0) for i in range(d)]


def _armar_semana(n, kind, minutos, escalon, e, calidad, ciclo, intensos_altos, carrera, T, n0=1) -> list:
    """Sesiones de la semana: fáciles, la calidad (solo en carga, desde la semana 2, con 3+ días) y la larga. `minutos` = [larga, fáciles…]
    (la semana de la carrera no lleva larga). La calidad ocupa el lugar de la segunda fácil; si toca la etapa de aceleraciones, esa fácil lleva la nota."""
    racing = kind == "carrera"
    larga = None if racing else minutos[0]
    faciles = list(minutos if racing else minutos[1:])
    pos_cal = min(1, len(faciles) - 1) if (kind == "carga" and calidad and n > 1 and n >= n0 and len(minutos) >= 3) else None
    cal = None
    if pos_cal is not None:
        _, cal = calidad_de_la_semana(n, ciclo, e, faciles[pos_cal], T, intensos_altos, n0)   # None = aceleraciones
    sesiones, roles, letras, z2 = [], [], iter(LETRAS), 0
    for i, m in enumerate(faciles):
        if cal is not None and i == pos_cal:
            sesiones.append(cal)
            roles.append("calidad")
            continue
        z2 += 1
        id_, nombre = f"z2{next(letras)}", f"Z2 #{z2}"
        if i == pos_cal:   # aceleraciones
            sesiones.append(sesion_aceleraciones(id_, nombre, m))
        else:
            sesiones.append(_sesion(id_, "z2", nombre, m, pasos_facil(m, escalon, False), escalon))
        roles.append("facil")
    if larga is not None:
        sesiones.append(_sesion("larga", "larga", "Larga", larga, pasos_facil(larga, escalon, True), escalon))
        roles.append("larga")
    return sesiones


def con_carrera(plan: dict, desde: int, carrera: dict | None, semanas: int | None = None) -> dict:
    """El plan v6 con una carrera (`carrera` = {km, fecha, semanas_hasta}) o sin la que tenía (None), rehecho de la semana `desde` en adelante;
    las anteriores quedan tal cual. Sin carrera el plan dura `semanas` (por defecto las que ya tenía). ValueError si no se puede (sin entrada
    guardada, la carrera cae antes de `desde`, o el plan resultante no pasa la verificación)."""
    meta = plan.get("meta") or {}
    ent = dict(meta.get("entrada") or {})
    if not ent:
        raise ValueError("este plan no guarda su entrada")
    ent["inicio"] = plan["start"]
    if carrera:
        ent["meta"], ent["objetivo"] = {"tipo": "carrera", **carrera}, "carrera"
    else:
        ent["meta"] = {"tipo": "base"}
        ent["objetivo"] = "base" if ent.get("objetivo") == "carrera" else ent.get("objetivo", "base")
        ent["semanas"] = max(semanas or len(plan["weeks"]), desde)
    try:
        nuevo = generar_v6(ent)
    except AssertionError as ex:
        raise ValueError(f"el plan con carrera no pasa la verificación: {ex}") from None
    if desde > len(nuevo["weeks"]):
        raise ValueError("la carrera queda antes de la semana en curso")
    nuevo["weeks"] = [w for w in plan["weeks"] if w["n"] < desde] + [w for w in nuevo["weeks"] if w["n"] >= desde]
    nuevo["meta"].update({k: meta[k] for k in ("nivel_calculado", "dolor", "tiempo_carrera", "ajuste_pct") if k in meta})
    try:
        verificar(nuevo)
    except AssertionError as ex:
        raise ValueError(f"el plan con carrera no pasa la verificación: {ex}") from None
    return nuevo


def es_v6(plan: dict) -> bool:
    """¿El plan lo hizo este motor? (los planes viejos no traen `meta`)."""
    return (plan.get("meta") or {}).get("motor") == "v6"
