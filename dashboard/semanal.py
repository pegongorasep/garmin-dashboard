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
