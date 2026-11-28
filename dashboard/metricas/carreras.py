"""Pruebas, carreras y mejores marcas."""

import re
import unicodedata
from datetime import date

from dashboard.i18n import tt
from dashboard.metricas.carga import esfuerzo_de, rpe_de
from dashboard.metricas.comun import day_of, id_de
from dashboard.metricas.zonas import zone_minutes


# --- prueba al terminar el plan ---

def distancia_en_tiempo(serie: list, seg: float):
    """Metros recorridos en los primeros `seg` segundos de una serie [seg, metros, fc] (interpola); None si no llega."""
    if not serie or serie[-1][0] < seg:
        return None
    for (t0, d0, _), (t1, d1, _) in zip(serie, serie[1:]):
        if t0 <= seg <= t1:
            return d0 if t1 == t0 else d0 + (d1 - d0) * (seg - t0) / (t1 - t0)
    return None


def tiempo_en_distancia(serie: list, metros: float):
    """Segundos en llegar a `metros` de una serie [seg, metros, fc] (interpola); None si no llega."""
    if not serie or serie[-1][1] < metros:
        return None
    for (t0, d0, _), (t1, d1, _) in zip(serie, serie[1:]):
        if d0 <= metros <= d1:
            return t0 if d1 == d0 else t0 + (t1 - t0) * (metros - d0) / (d1 - d0)
    return None


PRUEBA_FC_FIJA_S = 1800


PRUEBA_SEGUIDO_PCT = 95   # % de trote desde el cual cuenta como 30' seguidos


def valor_prueba(tipo: str, serie: list, pct_trote=None):
    """Lo que mide cada prueba. `fc_fija`: ritmo (s/km) de los primeros 30'; `trote_continuo`: % de trote; `5k`: segundos
    de los 5 km. Devuelve {"valor", "km"} o None si la serie no alcanza."""
    if tipo == "fc_fija":
        metros = distancia_en_tiempo(serie, PRUEBA_FC_FIJA_S)
        return {"valor": round(PRUEBA_FC_FIJA_S / (metros / 1000)), "km": round(metros / 1000, 2)} if metros else None
    if tipo == "trote_continuo":   # si ya trota los 30' seguidos, también los km (para pasar a la prueba a FC fija)
        if pct_trote is None:
            return None
        metros = distancia_en_tiempo(serie, PRUEBA_FC_FIJA_S) if pct_trote >= PRUEBA_SEGUIDO_PCT else None
        return {"valor": round(pct_trote, 1), "km": round(metros / 1000, 2) if metros else None,
                "seguido": pct_trote >= PRUEBA_SEGUIDO_PCT}
    t = tiempo_en_distancia(serie, 5000)
    return None if t is None else {"valor": round(t), "km": 5.0}


def comparar_prueba(tipo: str, valor: float, base):
    """Contra la base {"fuente", "fecha", "valor"}: {"dif", "mejor"} (dif = ahora − antes; en ritmo y tiempo menos es
    mejor, en % de trote más es mejor). None si no hay base."""
    if base is None:
        return None
    dif = round(valor - base["valor"], 1)
    return {"dif": dif, "mejor": None if dif == 0 else (dif > 0 if tipo == "trote_continuo" else dif < 0)}


# --- carreras y mejores marcas ---

_NOMBRE_CARRERA = re.compile(r"carrera|\brace|(?<![0-9])(?:5|10|21|42)\s?k\b|maraton|marathon")


def _sin_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn").lower()


def es_carrera(activity: dict, config: dict) -> bool:
    """¿Es carrera una corrida? Si Garmin la marcó (eventType race), si su nombre lo dice (sin importar
    mayúsculas ni acentos) o si su fecha está en `corrida.carreras`. El nombre nunca se publica."""
    tipo = (activity.get("activityType") or {}).get("typeKey")
    if tipo not in config.get("run_types", []):
        return False
    if (activity.get("eventType") or {}).get("typeKey") == "race":
        return True
    if activity.get("es_carrera") or (   # el paquete de la web trae `es_carrera` calculado y no el nombre
            "es_carrera" not in activity and _NOMBRE_CARRERA.search(_sin_acentos(activity.get("activityName") or ""))):
        return True
    return activity["startTimeLocal"][:10] in config.get("carreras", [])


def stats_carrera(activity: dict, details: dict, config: dict) -> dict:
    """Números de una carrera, sin nombre, ID ni GPS. `km` (ritmo de cada km, s) solo si Garmin dio los datos."""
    km = (activity.get("distance") or 0) / 1000
    seg = activity.get("duration") or 0
    zm = zone_minutes(activity)
    det = details.get(str(id_de(activity))) or {}
    rapido = activity.get("fastestSplit_1000")
    out = {"fecha": day_of(activity).isoformat(), "distancia_km": round(km, 2), "tiempo_s": round(seg),
           "ritmo_s": round(seg / km) if km else None,
           "fc_prom": activity.get("averageHR"), "fc_max": activity.get("maxHR"),
           "zonas_min": {z: round(v, 1) for z, v in zm.items()} if any(zm.values()) else None,
           "km_mas_rapido_s": round(rapido) if rapido else None,
           "cadencia": round(activity["averageRunningCadenceInStepsPerMinute"])
           if activity.get("averageRunningCadenceInStepsPerMinute") else None,
           "desnivel_m": round(activity["elevationGain"]) if activity.get("elevationGain") is not None else None,
           "caminadora": activity["activityType"]["typeKey"] == "treadmill_running",
           "esfuerzo": esfuerzo_de(activity, details, config), "rpe": rpe_de(activity, details),
           "km": det.get("ritmos_km") or None}
    return out


def comparar_carrera(carrera: dict, anteriores: list):
    """Contra la carrera más reciente de distancia parecida (±10 %) entre `anteriores`; None si no hay.
    Las diferencias son esta menos la anterior: negativo = más rápido / menos FC."""
    parecidas = [a for a in anteriores if a["fecha"] < carrera["fecha"] and a["distancia_km"]
                 and abs(a["distancia_km"] - carrera["distancia_km"]) <= 0.1 * a["distancia_km"]]
    if not parecidas:
        return None
    a = max(parecidas, key=lambda x: x["fecha"])
    dif = lambda k: None if carrera.get(k) is None or a.get(k) is None else round(carrera[k] - a[k], 1)  # noqa: E731
    return {"fecha": a["fecha"], "distancia_km": a["distancia_km"], "tiempo_s": a["tiempo_s"], "ritmo_s": a["ritmo_s"],
            "fc_prom": a["fc_prom"], "dif_tiempo_s": dif("tiempo_s"), "dif_ritmo_s": dif("ritmo_s"), "dif_fc": dif("fc_prom")}


# (clave, nombre, metros del tramo más rápido)
MARCAS = [("1k", "1 km", 1000), ("1mi", "1 milla", 1609), ("5k", "5K", 5000), ("10k", "10K", 10000),
          ("21k", "Medio maratón", 21098), ("42k", "Maratón", 42195)]


def mejores_marcas(historial: list, hoy=None, config=None) -> list:
    """Mejores marcas como las de Garmin, solo las que ya hizo: el menor `fastestSplit_<m>` de cada distancia
    y la corrida más larga. `nuevo` = el récord es de los últimos 30 días (si se da `hoy`)."""
    def marca(clave, nombre, a, tiempo, metros):
        fecha = a["startTimeLocal"][:10]
        return {"clave": clave, "nombre": nombre, "tiempo_s": round(tiempo), "ritmo_s": round(tiempo / (metros / 1000)),
                "fecha": fecha, "distancia_km": round(metros / 1000, 2),
                "nuevo": bool(hoy and 0 <= (hoy - date.fromisoformat(fecha)).days <= 30),
                "icono": "medalla" if config and es_carrera(a, config) else None}
    out = []
    for clave, nombre, metros in MARCAS:
        con = [a for a in historial if a.get(f"fastestSplit_{metros}")]
        if con:
            a = min(con, key=lambda x: (x[f"fastestSplit_{metros}"], x["startTimeLocal"]))
            out.append(marca(clave, tt(f"motor.marca.{clave}"), a, a[f"fastestSplit_{metros}"], metros))
    largas = [a for a in historial if a.get("distance")]
    if largas:
        a = max(largas, key=lambda x: (x["distance"], x["startTimeLocal"]))
        out.append(marca("larga", tt("motor.marca.larga"), a, a["duration"], a["distance"]))
    return out
