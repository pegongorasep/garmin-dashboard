"""Señales de recuperación (FC en reposo, HRV, sueño), semáforo y motivos."""

from datetime import date, timedelta

from dashboard.i18n import tt
from dashboard.metricas.carga import esfuerzo_de, rpe_de
from dashboard.metricas.comun import classify, day_of


def rhr_con_sueno(daily_summaries: list, sleep: list) -> list:
    """Quita la FC en reposo de los días sin noche de sueño registrada: sin reloj de noche, Garmin
    la saca de unos minutos despierto y sale inflada."""
    noches = {s.get("calendarDate") for s in sleep if (s.get("sleepTimeSeconds") or 0) > 0}
    return [d if d.get("calendarDate") in noches
            else {**d, "heartRate": {**(d.get("heartRate") or {}), "restingValue": None}}
            for d in daily_summaries]


def rhr_7d(daily_summaries: list, day: date):
    """Promedio de la FC en reposo de los 7 días anteriores a `day`, ignorando vacíos."""
    desde, valores = day - timedelta(days=7), []
    for d in daily_summaries:
        fecha = date.fromisoformat(d["calendarDate"])
        v = (d.get("heartRate") or {}).get("restingValue")
        if desde <= fecha < day and v is not None:
            valores.append(v)
    return sum(valores) / len(valores) if valores else None


def _por_fecha(registros: list, day: date):
    for r in registros:
        if r.get("calendarDate") == day.isoformat():
            return r
    return None


def _senal(estado, valor, referencia, texto, **extra):
    return {"estado": estado, "valor": valor, "referencia": referencia, "texto": texto, **extra}


def signal_hrv(day: date, hrv: list) -> dict:
    r = _por_fecha(hrv, day)
    if not r or r.get("lastNightAvg") is None:
        return _senal("sin_dato", None, None, tt("motor.senal.hrv_sin"), hrv_baja=False)
    v, base = r["lastNightAvg"], r.get("baseline") or {}
    bajo, alto, low_upper = base.get("balancedLow"), base.get("balancedUpper"), base.get("lowUpper")
    ref = f"{bajo}–{alto}"
    baja = r.get("status") == "LOW" or (low_upper is not None and v < low_upper)
    fuera = bajo is not None and v < bajo
    texto = tt("motor.senal.hrv", v=v, ref=ref)
    return _senal("fuera" if fuera else "ok", v, ref, texto, hrv_baja=baja)


def signal_rhr(day: date, daily_summaries: list, config: dict) -> dict:
    hoy = _por_fecha(daily_summaries, day)
    v = ((hoy or {}).get("heartRate") or {}).get("restingValue")
    prom = rhr_7d(daily_summaries, day)
    if v is None or prom is None:
        return _senal("sin_dato", v, prom, tt("motor.senal.rhr_sin"))
    limite = prom + config["rhr_tolerance_bpm"]
    texto = tt("motor.senal.rhr", v=v, prom=f"{prom:.0f}")
    return _senal("fuera" if v > limite else "ok", v, round(prom, 1), texto)


def _hmin(horas: float) -> str:
    """Horas decimales -> '6 h 29 min' (trunca los segundos)."""
    minutos = int(horas * 60 + 1e-6)
    return tt("motor.hmin", h=minutos // 60, m=f"{minutos % 60:02d}")


def signal_sleep(day: date, sleep: list, config: dict) -> dict:
    r = _por_fecha(sleep, day)
    if not r or r.get("sleepTimeSeconds") is None:
        return _senal("sin_dato", None, config["sleep_min_hours"], tt("motor.senal.sueno_sin"))
    horas = r["sleepTimeSeconds"] / 3600
    minimo = config["sleep_min_hours"]
    texto = tt("motor.senal.sueno", h=_hmin(horas), min=_hmin(minimo))
    return _senal("fuera" if horas < minimo else "ok", round(horas, 2), minimo, texto)


def signals(day: date, data: dict, config: dict) -> dict:
    """Las 3 señales de anoche: HRV, FC en reposo y sueño. data: daily_summaries, sleep, hrv."""
    return {
        "hrv": signal_hrv(day, data.get("hrv", [])),
        "rhr": signal_rhr(day, data.get("daily_summaries", []), config),
        "sueno": signal_sleep(day, data.get("sleep", []), config),
    }


def traffic_light(sigs: dict, prev_light) -> dict:
    """Semáforo del día. `sin_dato` no cuenta como fuera. prev_light: color de ayer o None.

    Si HRV, FC en reposo y sueño están los tres sin dato, el color es "sin_datos" (no verde).
    """
    if all(sigs[k]["estado"] == "sin_dato" for k in ("hrv", "rhr", "sueno")):
        return {"color": "sin_datos", "fuera": 0, "repetir_semana": False}
    fuera = sum(1 for s in sigs.values() if s["estado"] == "fuera")
    if sigs["hrv"].get("hrv_baja") or fuera >= 2:
        color = "rojo"
    elif fuera == 1:
        color = "amarillo"
    else:
        color = "verde"
    return {"color": color, "fuera": fuera,
            "repetir_semana": color == "rojo" and prev_light == "rojo"}


def ayer_duro(day: date, activities: list, details: dict, config: dict):
    """La actividad no-corrida de ayer con más esfuerzo: {categoria, esfuerzo, rpe}; None si no hubo.
    Varias del mismo día: gana el esfuerzo más alto (una sin esfuerzo solo cuenta si no hay otra)."""
    nombres = {c["id"]: c["nombre"] for c in config.get("categorias", [])}
    ayer = day - timedelta(days=1)
    cands = [(a, c) for a in activities if day_of(a) == ayer and (c := classify(a, config)) in nombres]
    if not cands:
        return None
    a, c = max(cands, key=lambda x: esfuerzo_de(x[0], details, config) or 0)
    return {"categoria": nombres[c], "esfuerzo": esfuerzo_de(a, details, config),
            "rpe": rpe_de(a, details)}


def _motivos() -> dict:
    return {k: tt(f"motor.motivo.{k}") for k in ("hrv", "rhr", "sueno")}


def motivo(sigs: dict, config=None, ayer=None):
    """Por qué la sesión va suave o en descanso: textos de las señales `fuera`, unidos con ' · '; None si no hay.
    Si ayer fue un día duro (esfuerzo ≥ `esfuerzo_duro`), lo dice al final."""
    MOTIVOS = _motivos()
    textos = [MOTIVOS[k] for k in ("hrv", "rhr", "sueno") if sigs[k]["estado"] == "fuera"]
    if sigs["hrv"].get("hrv_baja") and MOTIVOS["hrv"] not in textos:
        textos.insert(0, MOTIVOS["hrv"])
    if not textos:
        return None
    texto = " · ".join(textos)
    if ayer and ayer.get("esfuerzo") is not None and ayer["esfuerzo"] >= (config or {}).get("esfuerzo_duro", 8):
        texto += tt("motor.motivo.dia_duro")
    return texto
