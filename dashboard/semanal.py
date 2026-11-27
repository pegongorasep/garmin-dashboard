"""Ajuste semanal de los planes v6 (§3.8): la semana en curso se recalcula con lo que de verdad se corrió la anterior.
Función pura sobre (plan, datos, config, hoy); la usa `build` para que Hoy y Plan lo muestren. Determinista: solo depende de las
actividades (que ya entran a la huella de la caché de la web) y de la fecha. Los planes del motor viejo salen igual."""
import sys
from datetime import date, timedelta
from pathlib import Path

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


RITMO_SEMANAS, RITMO_MIN_CORRIDAS = 6, 3   # ventana de corridas reales y mínimo para fiarse del ritmo
RITMO_LIMITES = (4.0, 16.0)                # min/km creíbles de trote o trote-caminata (amplio: el principiante va a 9–15); fuera se ignora
RITMO_MIN_CORRIDA = (0.5, 5)               # km y minutos mínimos para que una corrida cuente


_PLAN = str(Path(__file__).resolve().parent.parent / "plan")
if _PLAN not in sys.path:
    sys.path.insert(0, _PLAN)
from nivel import RITMO_NIVEL  # noqa: E402  (ritmo genérico por nivel, junto a PISO_NIVEL)


def ritmo_facil(filas: list, hoy: date, semanas: int = RITMO_SEMANAS):
    """Ritmo fácil reciente en min/km: mediana de las corridas reales (no carreras, mínimo 0.5 km y 5 min; cuentan también las de trote-caminata) de las últimas
    `semanas` semanas, descartando ritmos fuera de RITMO_LIMITES. None si hay menos de RITMO_MIN_CORRIDAS (sin datos)."""
    ritmos = []
    for f in m.periodo_filas(filas, hoy, semanas):
        if f.get("carrera") or (f.get("km") or 0) < RITMO_MIN_CORRIDA[0] or (f.get("minutos") or 0) < RITMO_MIN_CORRIDA[1]:
            continue
        r = f["minutos"] / f["km"]
        if RITMO_LIMITES[0] <= r <= RITMO_LIMITES[1]:
            ritmos.append(r)
    if len(ritmos) < RITMO_MIN_CORRIDAS:
        return None
    ritmos.sort()
    k = len(ritmos)
    return ritmos[k // 2] if k % 2 else (ritmos[k // 2 - 1] + ritmos[k // 2]) / 2


def ritmo_o_nivel(ritmo, nivel):
    """El ritmo para estimar km: el personal si lo hay; si no, el genérico del nivel (RITMO_NIVEL). Sin nivel conocido, el de Base."""
    return ritmo or RITMO_NIVEL.get(nivel) or RITMO_NIVEL["base"]


def volumen_plan(minutos, unidad: str = "min", ritmo=None):
    """El volumen PLANEADO en la unidad pedida. El plan sigue en minutos; en km es solo una estimación para mostrar:
    minutos ÷ ritmo fácil, a 0.5 km (mínimo 0.5). None si no hay ritmo (la página muestra entonces los minutos)."""
    if unidad != "km":
        return minutos
    if not minutos or not ritmo:
        return None
    return max(0.5, round(minutos / ritmo * 2) / 2)


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


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _tramo_plan(plan: dict = None, config: dict = None):
    """(lunes del inicio, lunes de la última semana, semanas) del plan; None sin plan (o en modo libre)."""
    if not (plan and plan.get("weeks")) or (config or {}).get("sin_plan"):
        return None
    ini = _lunes(date.fromisoformat(str(plan.get("start") or (config or {}).get("plan_start"))[:10]))
    n = len(plan["weeks"])
    return ini, ini + timedelta(weeks=n - 1), n


def periodos_progreso(hoy: date, plan: dict = None, config: dict = None) -> list:
    """Opciones del selector de periodo de Progreso: [{"n", "todo"}]. SIEMPRE 4, 8 y 12 (las últimas N semanas hasta la
    actual, con ceros donde no hay nada) y, con plan, «todo el plan» (su largo real, con `desde`/`hasta` = primer y último
    lunes). La página solo elige la ventana de `serie_semanas`."""
    ops = [{"n": k, "todo": False} for k in (4, 8, 12)]
    t = _tramo_plan(plan, config)
    if t:
        ops.append({"n": t[2], "todo": True, "desde": t[0].isoformat(), "hasta": t[1].isoformat()})
    return ops


def serie_semanas(hoy: date, plan: dict = None, config: dict = None) -> list:
    """Lunes (del más viejo al más nuevo) de toda serie por semanas. Cubre las últimas 12 semanas hasta la actual
    (SEMANAS_SIN_PLAN) y, con plan, también todas sus semanas (aunque empiecen antes o terminen después)."""
    ini = _lunes(hoy)
    desde, hasta = ini - timedelta(weeks=SEMANAS_SIN_PLAN - 1), ini
    t = _tramo_plan(plan, config)
    if t:
        desde, hasta = min(desde, t[0]), max(hasta, t[1])
    return [desde + timedelta(weeks=i) for i in range((hasta - desde).days // 7 + 1)]


# --- el plan que se comparte (perfil): un solo filtro sobre el plan de la persona ---

SEMANA_PUBLICA = ("n", "block", "kind", "etiqueta", "focus", "sessions", "plan_min")
SEMANA_AVANCE = ("progreso", "cumplimiento", "estados", "minutos", "km", "plan_km")   # salen de sus actividades
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
        else:   # el km estimado con el ritmo real lo delata: sin actividades se recalcula con el ritmo genérico del nivel
            ritmo = ritmo_o_nivel(None, plan.get("nivel"))
            if "plan_km" in w or any("km_est" in ses for ses in x.get("sessions", [])):
                x["plan_km"] = volumen_plan(x.get("plan_min"), "km", ritmo)
            x["sessions"] = [{**{k: v for k, v in ses.items() if k != "km_est"},
                              **({"km_est": volumen_plan(ses.get("minutes"), "km", ritmo)} if "km_est" in ses else {})}
                             for ses in x.get("sessions", [])]
        out["semanas"].append(x)
    if con_actividades:
        if plan.get("faltan"):
            out["faltan"] = plan["faltan"]
        out["estado_sesiones"] = [{"id": e["id"], "estado": e["estado"], "ajustada": e.get("ajustada", False)}
                                  for e in plan.get("estado_sesiones") or []]
    return out
