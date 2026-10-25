"""Funciones puras del dashboard: zonas, carga, semáforo y plan. Sin I/O ni reloj.

Convenciones: `day` y `week_start` son objetos date; las fechas de Garmin
(`calendarDate`, `startTimeLocal`) ya vienen en hora local de Mérida.
Semáforo: "verde" | "amarillo" | "rojo".
"""
from datetime import date, timedelta

ZONAS = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def day_of(activity: dict) -> date:
    return date.fromisoformat(activity["startTimeLocal"][:10])


def zones(max_hr: float, rhr: float, pcts: list) -> list:
    """Zonas Karvonen: [(zona, piso, techo)]. El techo es el piso de la zona siguiente."""
    pisos = [round(rhr + p / 100 * (max_hr - rhr)) for p in pcts]
    techos = pisos[1:] + [round(max_hr)]
    return [(f"Z{i + 1}", pisos[i], techos[i]) for i in range(len(pcts))]


def rhr_7d(daily_summaries: list, day: date):
    """Promedio de la FC en reposo de los 7 días anteriores a `day`, ignorando vacíos."""
    desde, valores = day - timedelta(days=7), []
    for d in daily_summaries:
        fecha = date.fromisoformat(d["calendarDate"])
        v = (d.get("heartRate") or {}).get("restingValue")
        if desde <= fecha < day and v is not None:
            valores.append(v)
    return sum(valores) / len(valores) if valores else None


def classify(activity: dict, config: dict) -> str:
    tipo = activity["activityType"]["typeKey"]
    if tipo in config["run_types"]:
        return "run"
    if tipo in config["crossfit_types"]:
        return "crossfit"
    return "other"


def zone_minutes(activity: dict) -> dict:
    """Minutos en Z1..Z5. Z0 (duración − suma) no se devuelve."""
    return {z: (activity.get(f"hrTimeInZone_{i + 1}") or 0) / 60 for i, z in enumerate(ZONAS)}


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


def session_load(activity: dict, details: dict):
    """RPE × minutos; None si no hay RPE."""
    rpe = (details.get(str(activity["activityId"])) or {}).get("rpe")
    if rpe is None:
        return None
    return rpe * activity["duration"] / 60


def week_load(activities: list, details: dict, week_start: date, config: dict) -> dict:
    """Carga de la semana: {crossfit, run, total, sin_rpe}."""
    fin = week_start + timedelta(days=7)
    out = {"crossfit": 0.0, "run": 0.0, "sin_rpe": 0}
    for a in activities:
        tipo = classify(a, config)
        if tipo == "other" or not (week_start <= day_of(a) < fin):
            continue
        carga = session_load(a, details)
        if carga is None:
            out["sin_rpe"] += 1
        else:
            out[tipo] += carga
    out["total"] = out["crossfit"] + out["run"]
    return out


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
        return _senal("sin_dato", None, None, "Sin HRV de anoche", hrv_baja=False)
    v, base = r["lastNightAvg"], r.get("baseline") or {}
    bajo, alto, low_upper = base.get("balancedLow"), base.get("balancedUpper"), base.get("lowUpper")
    ref = f"{bajo}–{alto}"
    baja = r.get("status") == "LOW" or (low_upper is not None and v < low_upper)
    fuera = bajo is not None and v < bajo
    texto = f"HRV {v} ms, rango base {ref}"
    return _senal("fuera" if fuera else "ok", v, ref, texto, hrv_baja=baja)


def signal_rhr(day: date, daily_summaries: list, config: dict) -> dict:
    hoy = _por_fecha(daily_summaries, day)
    v = ((hoy or {}).get("heartRate") or {}).get("restingValue")
    prom = rhr_7d(daily_summaries, day)
    if v is None or prom is None:
        return _senal("sin_dato", v, prom, "Sin FC en reposo")
    limite = prom + config["rhr_tolerance_bpm"]
    texto = f"FC reposo {v} lpm, promedio 7 días {prom:.0f}"
    return _senal("fuera" if v > limite else "ok", v, round(prom, 1), texto)


def _hmin(horas: float) -> str:
    """Horas decimales -> '6 h 29 min' (trunca los segundos)."""
    minutos = int(horas * 60 + 1e-6)
    return f"{minutos // 60} h {minutos % 60:02d} min"


def signal_sleep(day: date, sleep: list, config: dict) -> dict:
    r = _por_fecha(sleep, day)
    if not r or r.get("sleepTimeSeconds") is None:
        return _senal("sin_dato", None, config["sleep_min_hours"], "Sin dato de sueño")
    horas = r["sleepTimeSeconds"] / 3600
    minimo = config["sleep_min_hours"]
    texto = f"Sueño {_hmin(horas)}, mínimo {_hmin(minimo)}"
    return _senal("fuera" if horas < minimo else "ok", round(horas, 2), minimo, texto)


def signal_rpe(day: date, activities: list, details: dict, config: dict) -> dict:
    ayer = day - timedelta(days=1)
    cf = [a for a in activities if classify(a, config) == "crossfit" and day_of(a) == ayer]
    if not cf:
        return _senal("ok", None, config["rpe_heavy"], "sin CrossFit ayer")
    rpes = [r for a in cf if (r := (details.get(str(a["activityId"])) or {}).get("rpe")) is not None]
    if not rpes:
        return _senal("sin_dato", None, config["rpe_heavy"], "CrossFit de ayer sin RPE")
    v = max(rpes)
    texto = f"RPE de CrossFit de ayer {v:g}, pesado desde {config['rpe_heavy']}"
    return _senal("fuera" if v >= config["rpe_heavy"] else "ok", v, config["rpe_heavy"], texto)


def signals(day: date, data: dict, config: dict) -> dict:
    """Las 4 señales de anoche y ayer. data: daily_summaries, sleep, hrv, activities, details."""
    return {
        "hrv": signal_hrv(day, data.get("hrv", [])),
        "rhr": signal_rhr(day, data.get("daily_summaries", []), config),
        "sueno": signal_sleep(day, data.get("sleep", []), config),
        "rpe": signal_rpe(day, data.get("activities", []), data.get("details", {}), config),
    }


def traffic_light(sigs: dict, prev_light) -> dict:
    """Semáforo del día. `sin_dato` no cuenta como fuera. prev_light: color de ayer o None."""
    fuera = sum(1 for s in sigs.values() if s["estado"] == "fuera")
    if sigs["hrv"].get("hrv_baja") or fuera >= 2:
        color = "rojo"
    elif fuera == 1:
        color = "amarillo"
    else:
        color = "verde"
    return {"color": color, "fuera": fuera,
            "repetir_semana": color == "rojo" and prev_light == "rojo"}


def week_index(day: date, plan_start: date, repetidas=()):
    """Semana del plan (1–12) que toca en `day`, o None si está fuera.

    `repetidas`: números de semana del plan que se repitieron (una semana puede
    aparecer más de una vez). Cada repetición empuja el resto una semana.
    """
    secuencia = []
    for n in range(1, 13):
        secuencia += [n] * (1 + list(repetidas).count(n))
    i = (day - plan_start).days // 7
    return secuencia[i] if 0 <= i < len(secuencia) else None


def plan_status(week: dict, runs_this_week: list) -> list:
    """Asigna las corridas hechas, en orden, a las sesiones de la semana.

    runs_this_week: [{"fecha": "YYYY-MM-DD", "luz": "verde"|"amarillo"|"rojo"|None}] en orden.
    Devuelve [{"id", "estado": "hecha"|"pendiente", "ajustada": bool, "fecha"}].
    """
    out = []
    for i, s in enumerate(week["sessions"]):
        run = runs_this_week[i] if i < len(runs_this_week) else None
        out.append({"id": s["id"], "estado": "hecha" if run else "pendiente",
                    "ajustada": bool(run) and run.get("luz") in ("amarillo", "rojo"),
                    "fecha": run["fecha"] if run else None})
    return out


def today_card(day: date, light: dict, status: list, activities: list, config: dict) -> dict:
    """Qué mostrar hoy. light = resultado de traffic_light; status = plan_status."""
    hoy = [a for a in activities if day_of(a) == day]
    hay_cf = any(classify(a, config) == "crossfit" for a in hoy)
    hay_run = any(classify(a, config) == "run" for a in hoy)
    aviso = "Repetir la semana" if light.get("repetir_semana") else None
    if hay_cf or (day.weekday() in (0, 1, 3) and not hay_run):
        return {"tipo": "crossfit", "texto": "Hoy es CrossFit", "version": None,
                "sesion_id": None, "aviso": aviso}
    if hay_run:
        return {"tipo": "hecha_hoy", "texto": "Corrida de hoy hecha", "version": None,
                "sesion_id": None, "aviso": aviso}
    if not status:
        return {"tipo": "sin_plan", "texto": "Hoy no hay semana de plan activa", "version": None,
                "sesion_id": None, "aviso": aviso}
    pendientes = [s for s in status if s["estado"] == "pendiente"]
    if not pendientes:
        return {"tipo": "completa", "texto": "Semana completa, descansa", "version": None,
                "sesion_id": None, "aviso": aviso}
    version = {"verde": "normal", "amarillo": "suave", "rojo": "descanso"}[light["color"]]
    return {"tipo": "sesion", "texto": f"Siguiente sesión: versión {version}",
            "version": version, "sesion_id": pendientes[0]["id"], "aviso": aviso}


def run_rows(activities: list, config: dict) -> list:
    """Una fila por corrida: fecha, minutos, FC promedio, % en Z1–Z2 y eficiencia aeróbica."""
    filas = []
    for a in activities:
        if classify(a, config) != "run":
            continue
        zm = zone_minutes(a)
        total = sum(zm.values())
        hr, vel = a.get("averageHR"), a.get("averageSpeed")
        eficiencia = None
        if a["activityType"]["typeKey"] == "running" and hr and vel:
            eficiencia = vel * 60 / hr
        filas.append({"fecha": day_of(a).isoformat(), "minutos": a["duration"] / 60,
                      "fc_prom": hr, "pct_z1z2": (zm["Z1"] + zm["Z2"]) / total * 100 if total else None,
                      "eficiencia": eficiencia})
    return sorted(filas, key=lambda f: f["fecha"])


def max_hr_progress(activities: list, config: dict) -> dict:
    """Progreso de la medición de FC máx con correa en CrossFit."""
    desde = date.fromisoformat(config["strap_in_crossfit_since"])
    ses = [a for a in activities if classify(a, config) == "crossfit"
           and day_of(a) >= desde and a.get("maxHR")]
    sesiones = sorted(({"fecha": day_of(a).isoformat(), "max_hr": a["maxHR"]} for a in ses),
                      key=lambda s: s["fecha"])
    pico = max((s["max_hr"] for s in sesiones), default=None)
    estimacion = max(pico + 3, config["max_hr_floor"]) if pico is not None else None
    semanas = {day_of(a) - timedelta(days=day_of(a).weekday()) for a in ses}
    return {"sesiones": sesiones, "pico": pico, "estimacion": estimacion,
            "revisar": estimacion is not None and estimacion > config["max_hr_review_above"],
            "semanas_medidas": len(semanas), "listo": len(semanas) >= 2}


def watch_zone_mismatch(hr_zones, config: dict):
    """Aviso si la FC máx del reloj difiere de la del config; None si coincide o no hay dato."""
    perfiles = hr_zones if isinstance(hr_zones, list) else [hr_zones or {}]
    perfil = next((p for p in perfiles if p.get("sport") == "DEFAULT"), perfiles[0] if perfiles else {})
    reloj = perfil.get("maxHeartRateUsed")
    if reloj is None or reloj == config["max_hr"]:
        return None
    return (f"El reloj usa FC máx {reloj} y el dashboard {config['max_hr']}: "
            "las zonas por actividad no coinciden. Corrígelo en Garmin Connect.")
