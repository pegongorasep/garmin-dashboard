"""Convierte data/ + plan + config en site/data.json (solo campos de una lista blanca).

Uso: python dashboard/build.py [--day YYYY-MM-DD] [--plan-start YYYY-MM-DD]
Es el único lugar con reloj: "hoy" se calcula en la zona horaria del config.
"""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import metrics as m

ROOT = Path(__file__).parent.parent
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def load_data() -> dict:
    d = ROOT / "data"
    daily = load(d / "daily.json", {})
    return {
        "daily_summaries": daily.get("daily_summaries", []),
        "sleep": daily.get("sleep", []),
        "hrv": daily.get("hrv", []),
        "activities": load(d / "activities.json", []),
        "details": load(d / "activity_details.json", {}),
        "hr_zones": load(d / "hr_zones.json", []),
        "meta": load(d / "meta.json", {}),
        "inbody": load(ROOT / "plan" / "inbody.json"),
    }


def load_plan() -> dict:
    plan = ROOT / "plan" / "plan.json"
    return load(plan if plan.exists() else ROOT / "plan" / "plan.example.json")


def r1(x):
    return None if x is None else round(x, 1)


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def light_on(day: date, data: dict, config: dict, prev=None) -> dict:
    return m.traffic_light(m.signals(day, data, config), prev)


# --- plan: zonas por nombre -> lpm ---

def lpm_range(zone: str, zonas: list):
    """'Z2' -> [piso, techo]; 'Z1-Z2' -> piso de Z1 a techo de Z2."""
    por_nombre = {z: (lo, hi) for z, lo, hi in zonas}
    try:
        a, b = zone.split("-")[0], zone.split("-")[-1]
        return [por_nombre[a][0], por_nombre[b][1]]
    except KeyError:
        return None


def convert_steps(steps: list, zonas: list) -> list:
    out = []
    for s in steps:
        if s["kind"] == "repeat":
            out.append({"kind": "repeat", "times": s["times"], "steps": convert_steps(s["steps"], zonas)})
        else:
            out.append({"kind": s["kind"], "minutes": s["minutes"], "zone": s["zone"],
                        "lpm": lpm_range(s["zone"], zonas), "note": s.get("note", ""),
                        "optional": s.get("optional", False)})
    return out


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    return {"id": s["id"], "tipo": s.get("tipo"), "name": s["name"], "minutes": s["minutes"],
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": easy["name"], "minutes": easy["minutes"],
                     "steps": convert_steps(easy["steps"], zonas)}}


def convert_week(w: dict, zonas: list) -> dict:
    return {"n": w["n"], "block": w["block"], "kind": w["kind"], "focus": w["focus"],
            "sessions": [convert_session(s, zonas) for s in w["sessions"]]}


# --- bloques del JSON ---

def signals_list(sigs: dict) -> list:
    return [{"id": k, "estado": s["estado"], "valor": s["valor"],
             "referencia": s["referencia"], "texto": s["texto"]} for k, s in sigs.items()]


def day_type(day: date, hoy: date, acts: list, config: dict) -> str:
    tipos = {m.classify(a, config) for a in acts if m.day_of(a) == day}
    if "crossfit" in tipos:
        return "crossfit"
    if "run" in tipos:
        return "corrida"
    if day > hoy:
        return "futuro"
    return "descanso" if day < hoy else "hoy"


def week_runs(week_start: date, hasta: date, data: dict, config: dict) -> list:
    """Corridas de la semana (lun–dom) hasta `hasta`, en orden, con minutos y la luz de su día."""
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run"
                   and week_start <= m.day_of(a) <= hasta), key=lambda a: a["startTimeLocal"])
    return [{"fecha": m.day_of(a).isoformat(), "minutos": a["duration"] / 60,
             "luz": light_on(m.day_of(a), data, config)["color"]} for a in runs]


def week_assignment(day: date, data: dict, config: dict, plan: dict, hasta=None):
    """(semana del plan, asignación de sus sesiones) para la semana que contiene `day`; (None, []) si no hay."""
    n = m.week_index(day, date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []))
    semana = next((w for w in plan["weeks"] if w["n"] == n), None)
    if semana is None:
        return None, []
    ini = monday(day)
    return semana, m.assign_sessions(semana, week_runs(ini, hasta or day, data, config), config)


def _semana_corridas(ini: date, hasta: date, acts: list, details: dict, config: dict) -> list:
    return m.run_rows([a for a in acts if ini <= m.day_of(a) <= hasta], details, config)


def resumen_corridas(filas: list) -> dict:
    """Totales de las corridas de una semana (filas de run_rows): minutos, km, trote/caminata y % trote."""
    min_trote, min_camina = (sum(f[k] or 0 for f in filas) for k in ("trote_min", "camina_min"))
    return {"corridas": len(filas), "minutos": r1(sum(f["minutos"] for f in filas)),
            "km": r1(sum(f["km"] for f in filas)), "min_trote": r1(min_trote), "min_camina": r1(min_camina),
            "pct_trote": r1(min_trote / (min_trote + min_camina) * 100) if min_trote + min_camina else None}


def build_week(hoy: date, data: dict, config: dict, estado: list, plan: dict) -> dict:
    ini, acts = monday(hoy), data["activities"]
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        luz = light_on(d, data, config)["color"] if d <= hoy else None
        dias.append({"fecha": d.isoformat(), "dia_semana": DIAS[i],
                     "tipo": day_type(d, hoy, acts, config), "luz": luz})
    filas = _semana_corridas(ini, hoy, acts, data["details"], config)
    previas = _semana_corridas(ini - timedelta(days=7), ini - timedelta(days=1), acts, data["details"], config)
    n = m.week_index(hoy, date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []))
    semana = next((w for w in plan["weeks"] if w["n"] == n), None)
    r = resumen_corridas(filas)
    return {"dias": dias, "sesiones_total": len(estado),
            "hechas": sum(1 for e in estado if e["estado"] == "hecha"),
            "incompletas": sum(1 for e in estado if e["estado"] == "incompleta"),
            "minutos": r["minutos"], "km": r["km"], "min_trote": r["min_trote"], "min_camina": r["min_camina"],
            "pct_trote": r["pct_trote"],
            "plan_min": sum(x["minutes"] for x in semana["sessions"]) if semana else None,
            "anterior": {"minutos": r1(sum(f["minutos"] for f in previas)),
                         "km": r1(sum(f["km"] for f in previas)),
                         "min_trote": r1(sum(f["trote_min"] or 0 for f in previas))}}


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


def last_run(data: dict, config: dict, plan: dict):
    """La corrida más reciente con su sesión del plan (de SU semana), '¿lo hice bien?' y trote/caminata."""
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run"),
                  key=lambda a: a["startTimeLocal"])
    if not runs:
        return None
    a = runs[-1]
    dia = m.day_of(a)
    semana, estado = week_assignment(dia, data, config, plan, hasta=monday(dia) + timedelta(days=6))
    minutos = a["duration"] / 60
    asignada = next((e for e in estado if e["fecha"] == dia.isoformat() and e["minutos"] == minutos), None)
    sesion, plan_ses = None, None
    if asignada:
        plan_ses = next(s for s in semana["sessions"] if s["id"] == asignada["id"])
        suave = light_on(dia, data, config)["color"] in ("amarillo", "rojo")
        sesion = {"id": plan_ses["id"], "name": plan_ses["name"], "version": "suave" if suave else "normal",
                  "minutes_plan": plan_ses["easy"]["minutes"] if suave else plan_ses["minutes"]}
    return {"fecha": dia.isoformat(), "fc_prom": r1(a.get("averageHR")), "sesion": sesion,
            **corrida_json(a, plan_ses, data, config)}


def corrida_json(a: dict, plan_ses, data: dict, config: dict) -> dict:
    """Lo común de una corrida: minutos, km, caminadora, '¿lo hice bien?' y trote/caminata."""
    return {"minutos": r1(a["duration"] / 60), "km": r2((a.get("distance") or 0) / 1000),
            "caminadora": a["activityType"]["typeKey"] == "treadmill_running",
            **m.run_check(a, plan_ses, config), "trote": rw_json(m.run_walk(a, data["details"]))}


def corrida_plana(a: dict, plan_ses, data: dict, config: dict) -> dict:
    """corrida_json con el trote/caminata aplanado (lo que pinta el frontend en cada fila de corrida)."""
    c = corrida_json(a, plan_ses, data, config)
    tr = c.pop("trote") or dict.fromkeys(m.RW_CLAVES)
    return {**c, "pct_trote": tr["pct_trote"], "ritmo_trote_s": tr["ritmo_trote_s"], "fc_trote": tr["fc_trote"],
            "caminatas": tr["caminatas"], "patron_trote_min": tr["patron_trote_min"],
            "patron_camina_min": tr["patron_camina_min"], "trote_min": tr["trote_min"],
            "camina_min": tr["camina_min"]}


def corrida_de_sesion(e: dict, semana: dict, data: dict, config: dict):
    """Corrida asignada a la sesión `e` de estado_sesiones, en plano; None si no tiene (pendiente / no hecha)."""
    if e["fecha"] is None:
        return None
    a = next(a for a in data["activities"] if m.classify(a, config) == "run"
             and m.day_of(a).isoformat() == e["fecha"] and a["duration"] / 60 == e["minutos"])
    plan_ses = next(s for s in semana["sessions"] if s["id"] == e["id"])
    return corrida_plana(a, plan_ses, data, config)


def crossfit_del_dia(d: date, data: dict, config: dict):
    """CrossFit del día: TE aeróbico máximo, RPE máximo y minutos sumados; None si no hubo."""
    cf = [a for a in data["activities"] if m.classify(a, config) == "crossfit" and m.day_of(a) == d]
    if not cf:
        return None
    tes = [a["aerobicTrainingEffect"] for a in cf if a.get("aerobicTrainingEffect") is not None]
    rpes = [r for a in cf if (r := (data["details"].get(str(a["activityId"])) or {}).get("rpe")) is not None]
    return {"te": r1(max(tes)) if tes else None, "rpe": max(rpes) if rpes else None,
            "minutos": r1(sum(a["duration"] for a in cf) / 60)}


def dia_de_semana(d: date, hoy: date, runs: list, sesiones: list, data: dict, config: dict) -> dict:
    """Un día del calendario: corrida más larga (con su sesión), CrossFit y lo planeado si es futuro."""
    del_dia = [a for a in runs if m.day_of(a) == d]
    corrida = None
    if del_dia:
        a = max(del_dia, key=lambda a: a["duration"])
        e = next((e for e in sesiones if e["fecha"] == d.isoformat() and e["minutos"] == a["duration"] / 60), None)
        corrida = {"minutos": r1(a["duration"] / 60), "sesion_nombre": e["name"] if e else "Extra",
                   "estado": e["estado"] if e else "extra"}
    cf = crossfit_del_dia(d, data, config)
    planeado = None
    if d > hoy and not corrida and not cf:
        larga_pendiente = any(e["tipo"] == "larga" and e["estado"] == "pendiente" for e in sesiones)
        if d.weekday() in config["crossfit_days"]:
            planeado = "cf"
        elif d.weekday() >= 5 and larga_pendiente:
            planeado = "larga"
    return {"fecha": d.isoformat(), "dia_semana": DIAS[d.weekday()],
            "luz": light_on(d, data, config)["color"] if d <= hoy else None,
            "corrida": corrida, "corridas_n": len(del_dia), "crossfit": cf, "planeado": planeado}


def build_semana(ini: date, hoy: date, data: dict, config: dict, plan: dict) -> dict:
    """Una semana calendario (lun–dom) de la vista Hoy: stats de todas las corridas, calendario, sesiones y extras."""
    fin = ini + timedelta(days=6)
    hasta = min(fin, hoy)
    repetidas = config.get("semanas_repetidas", [])
    n = m.week_index(ini, date.fromisoformat(config["plan_start"]), repetidas)
    semana, estado = week_assignment(ini, data, config, plan, hasta=hasta)
    pasada = fin < hoy
    sesiones = [{**e, "estado": "no_hecha" if pasada and e["estado"] == "pendiente" else e["estado"],
                 "minutos": e["minutos"], "corrida": corrida_de_sesion(e, semana, data, config)} for e in estado]
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run" and ini <= m.day_of(a) <= hasta),
                  key=lambda a: a["startTimeLocal"])
    sin_asignar = [(e["fecha"], e["minutos"]) for e in estado if e["fecha"]]
    extras = []
    for a in runs:
        clave = (m.day_of(a).isoformat(), a["duration"] / 60)
        if clave in sin_asignar:
            sin_asignar.remove(clave)
        else:
            extras.append({"fecha": clave[0], **corrida_plana(a, None, data, config)})
    dias = [dia_de_semana(ini + timedelta(days=i), hoy, runs, sesiones, data, config) for i in range(7)]
    for s in sesiones:
        s["minutos"] = r1(s["minutos"])
    filas = _semana_corridas(ini, hasta, data["activities"], data["details"], config)
    previas = _semana_corridas(ini - timedelta(days=7), ini - timedelta(days=1), data["activities"], data["details"], config)
    return {"inicio": ini.isoformat(), "fin": fin.isoformat(), "n": n if semana else None,
            "kind": semana["kind"] if semana else None, "block": semana["block"] if semana else None,
            "estado": "pasada" if pasada else "actual" if ini <= hoy else "futura",
            "stats": resumen_corridas(filas),
            "plan": {"total": len(estado), "hechas": sum(1 for e in sesiones if e["estado"] == "hecha"),
                     "incompletas": sum(1 for e in sesiones if e["estado"] == "incompleta"),
                     "plan_min": sum(x["minutes"] for x in semana["sessions"])} if semana else None,
            "anterior": {k: v for k, v in resumen_corridas(previas).items() if k in ("minutos", "km", "min_trote")},
            "dias": dias, "sesiones": sesiones, "extras": extras}


def build_semanas(hoy: date, data: dict, config: dict, plan: dict):
    """(semanas_hoy, índice de la semana de hoy): las del plan (con repetidas) y, si hoy cae fuera, la de hoy."""
    inicio = monday(date.fromisoformat(config["plan_start"]))
    total = len(plan["weeks"]) + len(config.get("semanas_repetidas", []))
    inicios = {inicio + timedelta(weeks=i) for i in range(total)} | {monday(hoy)}
    inicios = sorted(inicios)
    return [build_semana(i, hoy, data, config, plan) for i in inicios], inicios.index(monday(hoy))


def session_names(rows_acts: list, data: dict, config: dict, plan: dict) -> dict:
    """{(fecha, minutos): nombre de la sesión} de todas las corridas que caen en una semana del plan."""
    out, vistas = {}, set()
    for a in rows_acts:
        ini = monday(m.day_of(a))
        if ini in vistas:
            continue
        vistas.add(ini)
        _, estado = week_assignment(ini, data, config, plan, hasta=ini + timedelta(days=6))
        out.update({(e["fecha"], e["minutos"]): e["name"] for e in estado if e["fecha"]})
    return out


def build_runs(data: dict, config: dict, plan: dict) -> list:
    acts = sorted((a for a in data["activities"] if m.classify(a, config) == "run"),
                  key=lambda a: a["startTimeLocal"])
    nombres = session_names(acts, data, config, plan)
    return [{"fecha": f["fecha"], "sesion": nombres.get((f["fecha"], f["minutos"])),
             "minutos": r1(f["minutos"]), "km": r2(f["km"]), "fc_prom": r1(f["fc_prom"]),
             "pct_z1z2": r1(f["pct_z1z2"]), "caminadora": f["caminadora"],
             **(rw_json(f) or dict.fromkeys(m.RW_CLAVES))}
            for f in m.run_rows(acts, data["details"], config)]


def build_weeks(hoy: date, data: dict, config: dict, plan: dict) -> list:
    """12 semanas: minutos, km y trote/caminata de las corridas, y los minutos del plan."""
    filas = m.run_rows(data["activities"], data["details"], config)
    inicio_plan = date.fromisoformat(config["plan_start"])
    out = []
    for i in range(11, -1, -1):
        ini = monday(hoy) - timedelta(weeks=i)
        fs = [f for f in filas if ini <= date.fromisoformat(f["fecha"]) < ini + timedelta(days=7)]
        n = m.week_index(ini, inicio_plan, config.get("semanas_repetidas", []))
        semana = next((w for w in plan["weeks"] if w["n"] == n), None)
        out.append({"inicio": ini.isoformat(), "minutos": r1(sum(f["minutos"] for f in fs)),
                    "km": r1(sum(f["km"] for f in fs)),
                    "min_trote": r1(sum(f["trote_min"] or 0 for f in fs)),
                    "min_camina": r1(sum(f["camina_min"] or 0 for f in fs)),
                    "plan_min": sum(s["minutes"] for s in semana["sessions"]) if semana else None})
    return out


def build_mejora(hoy: date, filas: list, semanas: list) -> dict:
    """Cómo vas mejorando: frase, minutos de las últimas 8 semanas (con plan) y % trote de las últimas 12 corridas."""
    return {"frase": m.mejora_frase(filas, hoy),
            "semanas": [{"inicio": s["inicio"], "minutos": s["minutos"], "plan_min": s["plan_min"]} for s in semanas[-8:]],
            "corridas": [{"fecha": f["fecha"], "pct_trote": r1(f["pct_trote"])} for f in filas[-12:]]}


def build_days(hoy: date, data: dict) -> list:
    """84 días de recuperación con promedios de 7 días (se calculan con 6 días extra antes)."""
    hrv = {r["calendarDate"]: r for r in data["hrv"]}
    daily = {r["calendarDate"]: r for r in data["daily_summaries"]}
    sleep = {r["calendarDate"]: r for r in data["sleep"]}
    fechas = [(hoy - timedelta(days=i)).isoformat() for i in range(89, -1, -1)]
    horas = lambda f: None if (seg := (sleep.get(f) or {}).get("sleepTimeSeconds")) is None else round(seg / 3600, 2)  # noqa: E731
    v_hrv = [hrv.get(f, {}).get("lastNightAvg") for f in fechas]
    v_rhr = [((daily.get(f) or {}).get("heartRate") or {}).get("restingValue") for f in fechas]
    v_sue = [horas(f) for f in fechas]
    p_hrv, p_rhr, p_sue = (m.rolling_mean(v) for v in (v_hrv, v_rhr, v_sue))
    dias = []
    for i in range(6, 90):
        base = hrv.get(fechas[i], {}).get("baseline") or {}
        dias.append({"fecha": fechas[i], "hrv": v_hrv[i], "hrv_7d": r1(p_hrv[i]),
                     "hrv_base_baja": base.get("balancedLow"), "hrv_base_alta": base.get("balancedUpper"),
                     "rhr": v_rhr[i], "rhr_7d": r1(p_rhr[i]), "sueño_h": v_sue[i], "sueño_7d": r2(p_sue[i])})
    return dias


def build_details(hoy: date, data: dict, config: dict, fc_max: dict, reloj) -> dict:
    ini, acts = monday(hoy), data["activities"]
    carga = lambda s: {k: r1(v) if k != "sin_rpe" else v  # noqa: E731
                       for k, v in m.week_load(acts, data["details"], s, config).items()}
    dist = m.week_distribution(acts, ini)
    semanas = []
    for i in range(11, -1, -1):
        s = ini - timedelta(weeks=i)
        c = m.week_load(acts, data["details"], s, config)
        semanas.append({"inicio": s.isoformat(), "carga_crossfit": r1(c["crossfit"]),
                        "carga_corrida": r1(c["run"]), "sin_rpe": c["sin_rpe"]})
    return {
        "distribucion": {"minutos": {z: r1(v) for z, v in dist["minutos"].items()},
                         "bajo": r1(dist["bajo"]), "limbo": r1(dist["limbo"]), "alto": r1(dist["alto"])},
        "carga": carga(ini), "carga_anterior": carga(ini - timedelta(days=7)), "carga_semanas": semanas,
        "fc_max": {**fc_max, "config": config["max_hr"], "fuente": "reloj" if reloj else "respaldo"},
        "umbrales": {k: config[k] for k in ("rhr_tolerance_bpm", "sleep_min_hours", "rpe_heavy",
                                            "max_hr", "max_hr_floor", "zone_pcts",
                                            "ceiling_tolerance_min", "done_ratio")},
    }


def build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    # La FC máx viene del reloj; config["max_hr"] es solo respaldo si Garmin no la da.
    reloj = m.watch_max_hr(data["hr_zones"])
    config = {**config, "max_hr": reloj or config["max_hr"]}
    fc_max = m.max_hr_progress(data["activities"], config)
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)
    rhr = m.rhr_7d(data["daily_summaries"], hoy) or 60
    zonas = m.zones(config["max_hr"], rhr, config["zone_pcts"])

    sigs = m.signals(hoy, data, config)
    prev = light_on(ayer, data, config)["color"]
    luz = m.traffic_light(sigs, prev)

    repetidas = config.get("semanas_repetidas", [])
    semana_plan, estado = week_assignment(hoy, data, config, plan)
    n = semana_plan["n"] if semana_plan else None

    tarjeta = m.today_card(hoy, luz, estado, data["activities"], config)
    if tarjeta["sesion_id"] and semana_plan:
        ses = next(s for s in semana_plan["sessions"] if s["id"] == tarjeta["sesion_id"])
        tarjeta["sesion"] = convert_session(ses, zonas)
    tarjeta["motivo"] = m.motivo(sigs) if tarjeta["version"] in ("suave", "descanso") else None

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    filas = m.run_rows(data["activities"], data["details"], config)
    semanas_hoy, semana_hoy_idx = build_semanas(hoy, data, config, plan)
    semanas_12 = build_weeks(hoy, data, config, plan)
    return {
        "generado": ahora.isoformat(timespec="minutes"),
        "datos_al": datos_al,
        "zonas": [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in zonas],
        "rhr_promedio_7d": r1(rhr),
        "aviso_zonas": m.max_hr_above_watch(fc_max["estimacion"], config["max_hr"]),
        "hoy": {"semaforo": luz, "señales": signals_list(sigs), "tarjeta": tarjeta},
        "ultima_corrida": last_run(data, config, plan),
        "semana": build_week(hoy, data, config, estado, plan),
        "semanas_hoy": semanas_hoy, "semana_hoy_idx": semana_hoy_idx,
        "plan": {"inicio": plan["start"], "semana_actual": n, "semanas_repetidas": repetidas,
                 "semanas": [convert_week(w, zonas) for w in plan["weeks"]],
                 "estado_sesiones": [{**e, "minutos": r1(e["minutos"]),
                                         "corrida": corrida_de_sesion(e, semana_plan, data, config)} for e in estado]},
        "progreso": {"resumen": {str(k): m.progress_summary(filas, hoy, k) for k in (4, 8, 12)},
                     "corridas": build_runs(data, config, plan),
                     "semanas": semanas_12,
                     "mejora": build_mejora(hoy, filas, semanas_12),
                     "dias": build_days(hoy, data)},
        "composicion": m.composicion(data.get("inbody")),
        "detalles": build_details(hoy, data, config, fc_max, reloj),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="fecha local YYYY-MM-DD (para pruebas)")
    ap.add_argument("--plan-start", help="inicio del plan YYYY-MM-DD (solo pruebas visuales)")
    args = ap.parse_args()
    config = load(Path(__file__).parent / "config.json")
    tz = ZoneInfo(config["timezone"])
    ahora = datetime.now(tz)
    if args.day:
        ahora = datetime.combine(date.fromisoformat(args.day), ahora.time(), tzinfo=tz)
    plan = load_plan()
    if args.plan_start:
        config = {**config, "plan_start": args.plan_start}
        plan = {**plan, "start": args.plan_start}
    out = build(load_data(), plan, config, ahora)
    destino = ROOT / "site" / "data.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"OK: {destino} ({destino.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
