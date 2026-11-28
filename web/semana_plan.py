"""Semana contra el plan, compartido por el perfil (`persona.py`) y las tarjetas del grupo (`grupos_resumen.py`): una sola lógica.
Todo estructurado (el JS arma las frases en el idioma de quien mira) y solo conteos, tipos de sesión y categorías: nunca nombres de Garmin."""
from dashboard.metrics import faltan   # la regla de «lo que falta» vive en el motor


def semana_vs_plan(actual: dict, con_plan: bool) -> dict:
    """{minutos, objetivo, faltan} de la semana actual; sin `con_plan` (interruptor apagado) solo los minutos."""
    out = {"minutos": round((actual.get("stats") or {}).get("minutos") or 0), "objetivo": None, "faltan": []}
    if con_plan and actual.get("plan"):
        out.update(objetivo=actual["plan"].get("plan_min"), faltan=faltan(actual.get("sesiones") or []))
    return out


def calendario_semana(dias: list, hoy: str) -> list[dict]:
    """Mini calendario lun-dom: [{hoy, hecha, cats}] con las categorías (run, crossfit…) de cada día hecho."""
    out = []
    for d in dias:
        cats = (["run"] if d.get("corrida") else []) + [o["cat"] for o in d.get("otras") or []]
        out.append({"hoy": d.get("fecha") == hoy, "hecha": bool(cats), "cats": cats})
    return out
