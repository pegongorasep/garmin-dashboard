"""Redondeos y fechas sueltas que usan varios módulos."""
from dashboard import metrics as m
from datetime import date, timedelta

from dashboard.fechas import lunes as monday  # noqa: F401


def r1(x):
    return None if x is None else round(x, 1)


def light_on(day: date, data: dict, config: dict, prev=None) -> dict:
    return m.traffic_light(m.signals(day, data, config), prev)


def week_runs(week_start: date, hasta: date, data: dict, config: dict) -> list:
    """Corridas de la semana (lun–dom) hasta `hasta`, en orden, con minutos y la luz de su día."""
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run"
                   and week_start <= m.day_of(a) <= hasta), key=lambda a: a["startTimeLocal"])
    return [{"fecha": m.day_of(a).isoformat(), "minutos": a["duration"] / 60, "zonas": m.zone_minutes(a),
             "luz": light_on(m.day_of(a), data, config)["color"]} for a in runs]


def week_assignment(day: date, data: dict, config: dict, plan: dict, hasta=None):
    """(semana del plan, asignación de sus sesiones) para la semana que contiene `day`; (None, []) si no hay."""
    n = m.semana_del_plan(day, config)
    semana = next((w for w in plan["weeks"] if w["n"] == n), None)
    if semana is None:
        return None, []
    ini = monday(day)
    return semana, m.assign_sessions(semana, week_runs(ini, hasta or day, data, config), config)


def rw_json(rw) -> dict:
    """Trote/caminata redondeado para el JSON (None si no hay tramos). Acepta una fila de run_rows."""
    if rw is None or rw["trote_min"] is None:
        return None
    return {"trote_min": r1(rw["trote_min"]), "camina_min": r1(rw["camina_min"]),
            "pct_trote": r1(rw["pct_trote"]), "caminatas": rw["caminatas"],
            "patron_trote_min": r2(rw["patron_trote_min"]), "patron_camina_min": r2(rw["patron_camina_min"]),
            "km_trote": r2(rw["km_trote"]), "ritmo_trote_s": None if rw["ritmo_trote_s"] is None else round(rw["ritmo_trote_s"]),
            "fc_trote": r1(rw["fc_trote"])}


def r2(x):
    return None if x is None else round(x, 2)


def _total_semanas(config: dict, plan: dict) -> int:
    """Semanas del calendario del plan: las de la secuencia (repetidas, saltos y pausas). Sin plan_semanas en la config, las del plan."""
    return len(m.secuencia_de({**config, "plan_semanas": len(plan["weeks"])}))


def ultima_semana(config: dict, plan: dict) -> date:
    """Lunes de la última semana del plan (cuenta las semanas repetidas)."""
    return monday(date.fromisoformat(config["plan_start"])) + timedelta(weeks=_total_semanas(config, plan) - 1)


def plan_terminado(hoy: date, config: dict, plan: dict) -> bool:
    return bool(plan.get("weeks")) and hoy >= ultima_semana(config, plan) + timedelta(days=7)
