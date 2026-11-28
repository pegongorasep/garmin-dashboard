"""Esfuerzo, RPE y carga de sesión y de semana; distribución por zona."""

from datetime import date, timedelta

from dashboard.metricas.comun import ZONAS, classify, day_of, id_de
from dashboard.metricas.zonas import zona_minutos, zonas_de, zone_minutes


def week_distribution(activities: list, week_start: date) -> dict:
    """Minutos por zona de la semana (lun–dom) y % bajo/limbo/alto sobre Z1–Z5."""
    fin = week_start + timedelta(days=7)
    minutos = dict.fromkeys(ZONAS, 0.0)
    for a in activities:
        if week_start <= day_of(a) < fin:
            for z, m in zone_minutes(a).items():
                minutos[z] += m
    total = sum(minutos.values())
    grupos = {"bajo": minutos["Z1"] + minutos["Z2"], "limbo": minutos["Z3"],
              "alto": minutos["Z4"] + minutos["Z5"]}
    pct = {k: (v / total * 100 if total else 0.0) for k, v in grupos.items()}
    return {"minutos": minutos, **pct}


# Valor de cada zona para el esfuerzo (1–10): lo que cuesta un minuto en esa zona.
ESFUERZO = {"Z0": 1, "Z1": 2, "Z2": 3, "Z3": 5.5, "Z4": 7.5, "Z5": 9.5}


ORDEN_ZONAS = ["Z0", *ZONAS]


def esfuerzo(minutos: dict):
    """Esfuerzo 1–10 de una sesión: promedio ponderado de ESFUERZO en la mitad más dura (de Z5 hacia Z0), para que
    los descansos no lo bajen. 1 decimal; None sin minutos."""
    total = sum(minutos.values())
    if total <= 0:
        return None
    mitad = resto = total / 2
    suma = 0.0
    for z in reversed(ORDEN_ZONAS):
        tomo = min(minutos.get(z, 0.0), resto)
        suma += tomo * ESFUERZO[z]
        resto -= tomo
        if resto <= 1e-9:
            break
    return round(suma / mitad, 1)


def esfuerzo_de(activity: dict, details: dict, config: dict):
    """Esfuerzo de una actividad, de su serie de FC o de las zonas del reloj; None si no hay.
    En una sesión encadenada (ver `unir_encadenadas`) es el máximo de sus partes."""
    if activity.get("_partes"):
        es = [e for p in activity["_partes"] if (e := esfuerzo_de(p, details, config)) is not None]
        return max(es) if es else None
    zm = zona_minutos(activity, details, zonas_de(config))
    if zm is None and activity.get("manual"):   # a mano no hay zonas: vale el esfuerzo (1–10) que la persona puso
        rpe = rpe_de(activity, details)
        return None if rpe is None else float(rpe)
    return None if zm is None else esfuerzo(zm)


def rpe_de(activity: dict, details: dict):
    """RPE de una actividad (el máximo de sus partes si es una sesión encadenada); None si no hay."""
    partes = activity.get("_partes") or [activity]
    rs = [r for p in partes if (r := (details.get(str(id_de(p))) or {}).get("rpe")) is not None]
    return max(rs) if rs else None


def session_load(activity: dict, details: dict, config: dict):
    """Carga = esfuerzo × minutos de la actividad; None si no hay esfuerzo. Encadenada: suma de la carga de sus partes."""
    if activity.get("_partes"):
        cs = [c for p in activity["_partes"] if (c := session_load(p, details, config)) is not None]
        return sum(cs) if cs else None
    e = esfuerzo_de(activity, details, config)
    return None if e is None else e * activity["duration"] / 60


def week_load(activities: list, details: dict, week_start: date, config: dict) -> dict:
    """Carga de la semana: {<id de cada categoría>, run, total}."""
    fin = week_start + timedelta(days=7)
    ids = [c["id"] for c in config.get("categorias", [])]
    out = {**dict.fromkeys(ids, 0.0), "run": 0.0}
    for a in activities:
        tipo = classify(a, config)
        if tipo is None or not (week_start <= day_of(a) < fin):
            continue
        out[tipo] += session_load(a, details, config) or 0.0
    out["total"] = sum(out[k] for k in (*ids, "run"))
    return out
