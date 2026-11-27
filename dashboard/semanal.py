"""Ajuste semanal de los planes v6 (§3.8): la semana en curso se recalcula con lo que de verdad se corrió la anterior.
Función pura sobre (plan, datos, config, hoy); la usa `build` para que Hoy y Plan lo muestren. Determinista: solo depende de las
actividades (que ya entran a la huella de la caché de la web) y de la fecha. Los planes del motor viejo salen igual."""
from datetime import date, timedelta

import metrics as m
from i18n import tt

PCT = 10   # lo mismo que motor_v6.UMBRALES["ajuste_pct"], en %


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def ajustar_plan(plan: dict, data: dict, config: dict, hoy: date) -> dict:
    """El plan con la semana en curso ajustada (trae `ajuste` y `ajuste_texto`); el resto igual."""
    if (plan.get("meta") or {}).get("motor") != "v6":
        return plan
    import motor_v6
    corridas = [(m.day_of(a), a["duration"] / 60) for a in data["activities"] if m.classify(a, config) == "run"]
    if not corridas:
        return plan
    inicio = _lunes(date.fromisoformat(config["plan_start"]))
    sec = m.secuencia_semanas(inicio, config.get("semanas_repetidas", []), len(plan["weeks"]), config.get("pausas", []))
    actual = (hoy - inicio).days // 7
    if not 1 <= actual < len(sec) or sec[actual] is None or sec[actual - 1] is None:
        return plan
    real = [sum(mi for d, mi in corridas if _lunes(d) == inicio + timedelta(weeks=i)) for i in range(actual)]
    mayor = lambda i: max([mi for d, mi in corridas if _lunes(d) == inicio + timedelta(weeks=i)], default=0)
    trabajo = {"start": plan["start"], "weeks": list(plan["weeks"]), "meta": plan.get("meta")}
    por_n = {w["n"]: w for w in trabajo["weeks"]}
    actual_ajustada = None
    for j in range(1, actual + 1):
        n = sec[j]
        if n is None or sec[j - 1] is None or n == sec[j - 1] or n not in por_n or n - 1 not in por_n:
            continue   # pausa, semana repetida o sin anterior: sin ajuste
        normal = next((k for k in range(n - 1, 0, -1) if por_n[k]["kind"] != "descarga"), None)
        i_normal = max((i for i in range(j) if sec[i] == normal), default=None)
        ceros = 0
        for i in range(j - 1, -1, -1):
            if sec[i] is None or real[i] > 0:
                break
            ceros += 1
        w = motor_v6.ajustar_semana(trabajo, n, round(real[j - 1]), max_sesion_real_min=max(mayor(i) for i in range(max(0, j - 4), j)) or None,
                                    real_normal_min=round(real[i_normal]) if i_normal is not None else None, semanas_en_cero=ceros)
        por_n[n] = w
        trabajo["weeks"] = [por_n[x["n"]] for x in trabajo["weeks"]]
        if j == actual:
            actual_ajustada = w
    if actual_ajustada is None or "ajuste" not in actual_ajustada:
        return plan
    a = actual_ajustada["ajuste"]
    if a["razon"] == "sube" and not a["ajustada"]:
        texto = None
    else:
        texto = tt(f"motor.ajuste.{a['razon']}", min=a["minutos"], real=a["real_prev"], pct=PCT)
    actual_ajustada = {**actual_ajustada, "ajuste_texto": texto}
    return {**plan, "weeks": [actual_ajustada if w["n"] == actual_ajustada["n"] else w for w in plan["weeks"]]}


# --- cifras de la semana: una sola fuente (Unificar U2) ---

def resumen_corridas(filas: list) -> dict:
    """Totales de las corridas (filas de run_rows): minutos, km, trote/caminata y % trote."""
    min_trote, min_camina = (sum(f[k] or 0 for f in filas) for k in ("trote_min", "camina_min"))
    return {"corridas": len(filas), "minutos": round(sum(f["minutos"] for f in filas), 1),
            "km": round(sum(f["km"] for f in filas), 1), "min_trote": round(min_trote, 1), "min_camina": round(min_camina, 1),
            "pct_trote": round(min_trote / (min_trote + min_camina) * 100, 1) if min_trote + min_camina else None}


def resumen_semana(ini: date, hasta: date, data: dict, config: dict, todas: bool = False) -> dict:
    """Volumen de las corridas de ini..hasta (inclusive): {corridas, minutos, km, min_trote, min_camina, pct_trote}.
    Única fuente de minutos y km de una semana: Hoy, Plan, Progreso y la web leen esto.
    Con `todas=True` (modo sin plan) los minutos cuentan todas las categorías y el km solo las corridas: {actividades, minutos, km}."""
    if todas:
        lista = [a for a in data["activities"] if m.classify(a, config) and ini <= m.day_of(a) <= hasta]
        return {"actividades": len(lista), "minutos": round(sum(x["duration"] for x in lista) / 60, 1),
                "km": round(sum((x.get("distance") or 0) for x in lista if m.classify(x, config) == "run") / 1000, 1)}
    acts = [a for a in data["activities"] if ini <= m.day_of(a) <= hasta]
    return resumen_corridas(m.run_rows(acts, data["details"], config))


def volumen(resumen: dict, unidad: str = "min"):
    """El volumen en la unidad pedida ("min" o "km"); el plan solo tiene minutos, por eso no hay objetivo en km."""
    return resumen["km" if unidad == "km" else "minutos"]


def minutos_plan(semana):
    """Minutos que pide una semana del plan (None sin semana)."""
    return sum(s["minutes"] for s in semana["sessions"]) if semana else None


def conteo(estado: list) -> dict:
    """Hechas/incompletas/total de la asignación de sesiones (`estado` de week_assignment). Única fuente del avance."""
    return {"hechas": sum(1 for e in estado if e["estado"] == "hecha"),
            "incompletas": sum(1 for e in estado if e["estado"] == "incompleta"), "total": len(estado)}


def cumplimiento(hechas: int, total: int):
    """Semana pasada: "completa" (todas), "casi" (al menos 2/3) o "baja" (el resto; la página la muestra neutra). None sin sesiones."""
    if total <= 0:
        return None
    return "completa" if hechas >= total else "casi" if 3 * hechas >= 2 * total else "baja"


# --- racha, adherencia y porcentajes (Unificar U2b) ---

MAX_RACHA = 52   # semanas que se miran hacia atrás


def pct(hechas, total):
    """Porcentaje entero (0-100) de hechas sobre total; None si no hay total. Única fuente de los % de la página."""
    return round(100 * hechas / total) if total else None


def racha(cerradas: list, actual: bool = False) -> int:
    """REGLA ÚNICA de la racha: semanas seguidas que «cumplen», terminando en la última semana cerrada (la actual se suma solo si
    ya cumple). `cerradas` va de la más vieja a la más nueva. Cumplir = ✓ o ✓✓ del Plan (2/3 de las sesiones) con plan;
    sin plan = tener alguna actividad (no hay meta que medir). Con plan la semana actual no cuenta porque aún puede perderse."""
    n = 0
    for ok in reversed(cerradas[-MAX_RACHA:]):
        if not ok:
            break
        n += 1
    return n + 1 if actual else n


def racha_semanas(semanas: list, idx: int, hoy: date = None, data: dict = None, config: dict = None, libre: bool = False) -> dict:
    """Lo que sale en data.json como `racha`: {"semanas": n, "modo": "plan"|"libre"}. Grupos y perfil solo lo leen.
    Plan: sobre `semanas_hoy` (semanas pasadas con cumplimiento completa/casi). Libre: sobre las actividades de cada semana."""
    if libre:
        ini = hoy - timedelta(days=hoy.weekday())
        tiene = lambda k: any(m.classify(a, config) and ini - timedelta(weeks=k) <= m.day_of(a) < ini - timedelta(weeks=k - 1)
                              for a in data["activities"])
        return {"semanas": racha([tiene(k) for k in range(MAX_RACHA, 0, -1)], tiene(0)), "modo": "libre"}
    ok = lambda s: s.get("estado") == "pasada" and bool(s.get("plan")) and cumplimiento(s["plan"]["hechas"], s["plan"]["total"]) in ("completa", "casi")
    return {"semanas": racha([ok(s) for s in semanas[:idx]]), "modo": "plan"}


def adherencia(semanas: list, ultimas: int = 4):
    """% de sesiones hechas en las últimas semanas pasadas con plan (o en la actual si aún no hay pasadas); None sin sesiones."""
    con_plan = [s for s in semanas if s.get("plan")]
    base = [s for s in con_plan if s["estado"] == "pasada"][-ultimas:] or [s for s in con_plan if s["estado"] == "actual"]
    return pct(sum(s["plan"]["hechas"] for s in base), sum(s["plan"]["total"] for s in base))


SEMANAS_SIN_PLAN = 12


def serie_semanas(hoy: date, plan: dict = None, config: dict = None) -> list:
    """Lunes (del más viejo al de esta semana) de toda serie por semanas: tantas como semanas tiene el plan
    (8, 12, 16…) o 12 si no hay plan. Gráficas, intensidad y carga usan esta lista, así todas miden lo mismo."""
    con_plan = bool(plan and plan.get("weeks")) and not (config or {}).get("sin_plan")
    n = len(plan["weeks"]) if con_plan else SEMANAS_SIN_PLAN
    ini = hoy - timedelta(days=hoy.weekday())
    return [ini - timedelta(weeks=i) for i in range(n - 1, -1, -1)]


# --- el plan que se comparte (perfil): un solo filtro sobre el plan de la persona ---

SEMANA_PUBLICA = ("n", "block", "kind", "etiqueta", "focus", "sessions", "plan_min")
SEMANA_AVANCE = ("progreso", "cumplimiento", "estados", "minutos", "km")   # salen de sus actividades
EVENTOS_PUBLICOS = ("carrera", "prueba")   # viajes y enfermedades son privados


def plan_visible(plan: dict, con_actividades: bool) -> dict | None:
    """El `plan` de data.json tal como lo ve otra persona: el mismo objeto que usa la pestaña Plan, sin lo privado.
    Sin `con_actividades` no lleva marcas ni avance (hechas, cumplimiento, minutos y km reales, faltan). Nunca lleva
    eventos (viajes, enfermedades), ajustes ni ligas de edición (esas viven en `ui`, que no se comparte)."""
    if not plan or not plan.get("semanas"):
        return None
    out = {k: plan[k] for k in ("inicio", "semana_actual", "nivel", "largo", "bloques") if k in plan}
    out["semanas"] = []
    for w in plan["semanas"]:
        x = {k: w[k] for k in SEMANA_PUBLICA if k in w}
        marcas = [k for k in ([w.get("marca")] + list(w.get("marcas") or [])) if k in EVENTOS_PUBLICOS]
        if marcas:
            x["marca"] = marcas[0]
            if len(marcas) > 1:
                x["marcas"] = marcas
        if con_actividades:
            x.update({k: w[k] for k in SEMANA_AVANCE if k in w})
        out["semanas"].append(x)
    if con_actividades:
        if plan.get("faltan"):
            out["faltan"] = plan["faltan"]
        out["estado_sesiones"] = [{"id": e["id"], "estado": e["estado"], "ajustada": e.get("ajustada", False)}
                                  for e in plan.get("estado_sesiones") or []]
    return out
