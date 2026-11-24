"""Convierte data/ + plan + config en site/data.json (solo campos de una lista blanca).

Uso: python dashboard/build.py [--day YYYY-MM-DD] [--plan-start YYYY-MM-DD] [--out data.json]
Es el único lugar con reloj: "hoy" se calcula en la zona horaria del config.
"""
import argparse
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import metrics as m
import tipos
from ajustes import USER_DIR, cargar_config

ROOT = Path(__file__).parent.parent  # el motor (aquí vive site/)
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def load_data() -> dict:
    d = USER_DIR / "data"
    daily = load(d / "daily.json", {})
    return {
        "daily_summaries": daily.get("daily_summaries", []),
        "sleep": daily.get("sleep", []),
        "hrv": daily.get("hrv", []),
        "activities": load(d / "activities.json", []),
        "details": load(d / "activity_details.json", {}),
        "hr_zones": load(d / "hr_zones.json", []),
        "meta": load(d / "meta.json", {}),
        "historial": load(d / "historial_corridas.json"),
        "inbody": load(USER_DIR / "plan" / "inbody.json"),
    }


def load_plan() -> dict:
    plan = USER_DIR / "plan" / "plan.json"
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


ETIQUETA_CALIDAD = {"tempo_z3": "tempo Z3", "threshold": "threshold", "intervalos": "intervalos",
                    "progresivo": "progresivo", "fartlek": "fartlek"}


def estructura_calidad(s: dict) -> str:
    """"10' Z2 · 4×5' threshold (2' suave) · 5' suave" a partir de los pasos de una sesión de calidad."""
    extras = s["steps"]
    calen = next(p for p in extras if p["kind"] == "warmup")
    enfria = next(p for p in extras if p["kind"] == "cooldown")
    if s.get("calidad_tipo") == "progresivo":
        medio = [p for p in extras if p["kind"] not in ("warmup", "cooldown")]
        return (f"{calen['minutes']}' {calen['zone']} · " + " · ".join(f"{p['minutes']}' {p['zone']}" for p in medio)
                + f" progresivo · {enfria['minutes']}' suave")
    if s.get("calidad_tipo") == "fartlek":
        trabajo = [p["minutes"] for p in extras if p["kind"] == "run" and p["zone"] == "Z3"]
        return (f"{calen['minutes']}' {calen['zone']} · fartlek {'-'.join(str(t) for t in trabajo)}' en Z3 "
                f"(con pausas de 2' suave) · {enfria['minutes']}' suave")
    rep = next(p for p in extras if p["kind"] == "repeat")
    trabajo, rec = rep["steps"][0], rep["steps"][1]
    return (f"{calen['minutes']}' {calen['zone']} · {rep['times']}×{trabajo['minutes']}' "
            f"{ETIQUETA_CALIDAD.get(s.get('calidad_tipo'), 'calidad')} ({rec['minutes']}' suave) · {enfria['minutes']}' suave")


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    extra = {k: s[k] for k in ("nota", "calidad_tipo", "variada_tipo") if k in s}
    if "objetivo" in s:
        extra["objetivo"] = {**s["objetivo"], "lpm": lpm_range(s["objetivo"]["zona"], zonas)}
        extra["estructura"] = estructura_calidad(s)
    return {"id": s["id"], "tipo": s.get("tipo"), "name": s["name"], "minutes": s["minutes"], **extra,
            "forma": tipos.forma_de(s), "silueta": tipos.silueta_de(s["steps"]),
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": easy["name"], "minutes": easy["minutes"],
                     "silueta": tipos.silueta_de(easy["steps"]),
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
    for c in config["categorias"]:
        if c["id"] in tipos:
            return c["id"]
    if "run" in tipos:
        return "corrida"
    if day > hoy:
        return "futuro"
    return "descanso" if day < hoy else "hoy"


def week_runs(week_start: date, hasta: date, data: dict, config: dict) -> list:
    """Corridas de la semana (lun–dom) hasta `hasta`, en orden, con minutos y la luz de su día."""
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run"
                   and week_start <= m.day_of(a) <= hasta), key=lambda a: a["startTimeLocal"])
    return [{"fecha": m.day_of(a).isoformat(), "minutos": a["duration"] / 60, "zonas": m.zone_minutes(a),
             "luz": light_on(m.day_of(a), data, config)["color"]} for a in runs]


def week_assignment(day: date, data: dict, config: dict, plan: dict, hasta=None):
    """(semana del plan, asignación de sus sesiones) para la semana que contiene `day`; (None, []) si no hay."""
    n = m.week_index(day, date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []), config.get("plan_semanas", 12))
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
    n = m.week_index(hoy, date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []), config.get("plan_semanas", 12))
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
            "caminadora": a["activityType"]["typeKey"] == "treadmill_running", "carrera": m.es_carrera(a, config),
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


def otras_del_dia(d: date, data: dict, config: dict) -> list:
    """Actividades no-corrida del día, una entrada por categoría: TE aeróbico máx, RPE máx y minutos sumados."""
    out = []
    for c in config["categorias"]:
        acts = [a for a in data["activities"] if m.classify(a, config) == c["id"] and m.day_of(a) == d]
        if not acts:
            continue
        tes = [a["aerobicTrainingEffect"] for a in acts if a.get("aerobicTrainingEffect") is not None]
        rpes = [r for a in acts if (r := (data["details"].get(str(a["activityId"])) or {}).get("rpe")) is not None]
        out.append({"cat": c["id"], "icono": c.get("icono", "punto"), "te": r1(max(tes)) if tes else None, "rpe": max(rpes) if rpes else None,
                    "minutos": r1(sum(a["duration"] for a in acts) / 60)})
    return out


def dia_de_semana(d: date, hoy: date, runs: list, sesiones: list, data: dict, config: dict) -> dict:
    """Un día del calendario: corrida más larga (con su sesión) y otras actividades registradas (futuro: vacío)."""
    del_dia = [a for a in runs if m.day_of(a) == d]
    corrida = None
    if del_dia:
        a = max(del_dia, key=lambda a: a["duration"])
        e = next((e for e in sesiones if e["fecha"] == d.isoformat() and e["minutos"] == a["duration"] / 60), None)
        corrida = {"minutos": r1(a["duration"] / 60), "sesion_nombre": e["name"] if e else "Extra",
                   "estado": e["estado"] if e else "extra", "carrera": m.es_carrera(a, config)}
        corrida["icono"] = "medalla" if corrida["carrera"] else "correr"
    otras = otras_del_dia(d, data, config)
    return {"fecha": d.isoformat(), "dia_semana": DIAS[d.weekday()],
            "luz": light_on(d, data, config)["color"] if d <= hoy else None,
            "corrida": corrida, "corridas_n": len(del_dia), "otras": otras}


def intensidad_semana(acts: list, ini: date) -> dict:
    """Minutos por zona (Z1–Z5, Z0 fuera) de corridas + actividades de la semana y % bajo / limbo / alto: la cuenta de 80/20."""
    d = m.week_distribution(acts, ini)
    return {"minutos": {z: r1(v) for z, v in d["minutos"].items()}, "bajo": r1(d["bajo"]), "limbo": r1(d["limbo"]),
            "alto": r1(d["alto"])}


def build_semana(ini: date, hoy: date, data: dict, config: dict, plan: dict) -> dict:
    """Una semana calendario (lun–dom) de la vista Hoy: stats de todas las corridas, calendario, sesiones y extras."""
    fin = ini + timedelta(days=6)
    hasta = min(fin, hoy)
    repetidas = config.get("semanas_repetidas", [])
    n = m.week_index(ini, date.fromisoformat(config["plan_start"]), repetidas, config.get("plan_semanas", 12))
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
            "dias": dias, "sesiones": sesiones, "extras": extras,
            "intensidad": intensidad_semana(data["activities"], ini)}


def build_semanas(hoy: date, data: dict, config: dict, plan: dict):
    """(semanas_hoy, índice de la semana de hoy): las del plan (con repetidas) y, si hoy cae fuera, la de hoy."""
    inicio = monday(date.fromisoformat(config["plan_start"]))
    total = len(plan["weeks"]) + len(config.get("semanas_repetidas", []))
    inicios = {inicio + timedelta(weeks=i) for i in range(total)} | {monday(hoy)}
    inicios = sorted(inicios)
    # Antes de que empiece el plan se muestra la semana 1 como vista previa.
    mostrar = inicio if hoy < date.fromisoformat(config["plan_start"]) else monday(hoy)
    return [build_semana(i, hoy, data, config, plan) for i in inicios], inicios.index(mostrar)


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
    return [{"fecha": f["fecha"], "sesion": nombres.get((f["fecha"], f["minutos"])), "carrera": m.es_carrera(a, config),
             "icono": "medalla" if m.es_carrera(a, config) else "correr",
             "minutos": r1(f["minutos"]), "km": r2(f["km"]), "fc_prom": r1(f["fc_prom"]),
             "pct_z1z2": r1(f["pct_z1z2"]), "caminadora": f["caminadora"],
             **(rw_json(f) or dict.fromkeys(m.RW_CLAVES))}
            for a, f in zip(acts, m.run_rows(acts, data["details"], config))]


def historial_corridas(data: dict, config: dict) -> list:
    """Corridas de toda la cuenta (historial_corridas.json); si aún no existe, las actividades que ya se bajaron."""
    if data.get("historial") is not None:
        return data["historial"]
    return [a for a in data["activities"] if m.classify(a, config) == "run"]


def build_carreras(hoy: date, data: dict, config: dict) -> list:
    """Carreras (de la más nueva a la más vieja) con sus stats y la comparación con la anterior parecida.
    Las de las actividades recientes traen todo; las más viejas, del historial, solo distancia, tiempo y ritmo."""
    recientes = {a["startTimeLocal"]: a for a in data["activities"] if m.classify(a, config) == "run"}
    todas = {**{h["startTimeLocal"]: h for h in historial_corridas(data, config)}, **recientes}
    stats = [m.stats_carrera(a, data["details"], config) for _, a in sorted(todas.items()) if m.es_carrera(a, config)]
    out = []
    for i, s in enumerate(stats):
        dias = (hoy - date.fromisoformat(s["fecha"])).days
        out.append({**s, "icono": "medalla", "comparacion": m.comparar_carrera(s, stats[:i]), "hace_dias": dias,
                    "reciente": 0 <= dias <= 7})
    return out[::-1]


def build_weeks(hoy: date, data: dict, config: dict, plan: dict) -> list:
    """12 semanas: minutos, km y trote/caminata de las corridas, y los minutos del plan."""
    filas = m.run_rows(data["activities"], data["details"], config)
    inicio_plan = date.fromisoformat(config["plan_start"])
    out = []
    for i in range(11, -1, -1):
        ini = monday(hoy) - timedelta(weeks=i)
        fs = [f for f in filas if ini <= date.fromisoformat(f["fecha"]) < ini + timedelta(days=7)]
        n = m.week_index(ini, inicio_plan, config.get("semanas_repetidas", []), config.get("plan_semanas", 12))
        semana = next((w for w in plan["weeks"] if w["n"] == n), None)
        out.append({"inicio": ini.isoformat(), "minutos": r1(sum(f["minutos"] for f in fs)),
                    "km": r1(sum(f["km"] for f in fs)),
                    "min_trote": r1(sum(f["trote_min"] or 0 for f in fs)),
                    "min_camina": r1(sum(f["camina_min"] or 0 for f in fs)),
                    "plan_min": sum(s["minutes"] for s in semana["sessions"]) if semana else None})
    return out


def con_ritmo_z2(filas: list, zonas: list) -> list:
    """Agrega `ritmo_z2_s` a cada fila: ritmo (s/km) de las corridas al aire libre cuya FC promedio cayó en Z2.
    Misma fuente que la gráfica de ritmo de Progreso (ritmo trotando); si Garmin no dio tramos, el ritmo total."""
    _, lo, hi = zonas[1]
    out = []
    for f in filas:
        ritmo = f["ritmo_trote_s"] or (f["minutos"] * 60 / f["km"] if f["km"] else None)
        en_z2 = not f["caminadora"] and f["fc_prom"] is not None and lo <= f["fc_prom"] <= hi
        out.append({**f, "ritmo_z2_s": ritmo if en_z2 else None})
    return out


def iconos_semana(ini: date, data, config) -> list:
    """Un ícono por entreno registrado en la semana: primero las corridas (medalla si fue carrera), luego las demás
    actividades con el ícono de su categoría; cada grupo en orden de fecha."""
    if data is None or config is None:
        return []
    iconos = {c["id"]: c["icono"] for c in config["categorias"]}
    out = []
    for a in sorted(data["activities"], key=lambda a: a["startTimeLocal"]):
        c = m.classify(a, config)
        if not c or not ini <= m.day_of(a) < ini + timedelta(days=7):
            continue
        out.append((c != "run", ("medalla" if m.es_carrera(a, config) else "correr") if c == "run" else iconos.get(c, "punto")))
    return [ic for _, ic in sorted(out, key=lambda x: x[0])]


def build_mejora(hoy: date, filas: list, semanas: list, zonas: list, data=None, config=None) -> dict:
    """Cómo vas mejorando: frase, minutos de las últimas 8 semanas (con plan) y, según haya caminatas o no,
    % trote (modo "trote") o ritmo en Z2 (modo "ritmo") de las últimas 12 corridas."""
    desde = monday(hoy) - timedelta(weeks=4)
    recientes = [f for f in filas if date.fromisoformat(f["fecha"]) >= desde]
    modo = "ritmo" if recientes and not any((f["caminatas"] or 0) > 0 for f in recientes) else "trote"
    filas = con_ritmo_z2(filas, zonas)
    otras, frase_otras = [], []
    if data is not None and config is not None:
        acts, lunes = data["activities"], monday(hoy)
        otras = [{"semana": s["inicio"], "conteos": m.conteos_otras(acts, config, date.fromisoformat(s["inicio"]),
                                                                    date.fromisoformat(s["inicio"]) + timedelta(days=7))}
                 for s in semanas[-8:]]
        ahora = m.conteos_otras(acts, config, lunes - timedelta(weeks=4), lunes)
        antes = m.conteos_otras(acts, config, lunes - timedelta(weeks=8), lunes - timedelta(weeks=4))
        frase_otras = [{"nombre": c["nombre"], "ahora": ahora.get(c["id"], 0) / 4, "antes": antes.get(c["id"], 0) / 4}
                       for c in config["categorias"]]
    out = {"frase": m.mejora_frase(filas, hoy, modo, frase_otras), "modo": modo, "otras": otras,
           "semanas": [{"inicio": s["inicio"], "minutos": s["minutos"], "plan_min": s["plan_min"],
                        "iconos": iconos_semana(date.fromisoformat(s["inicio"]), data, config)} for s in semanas[-8:]],
           "corridas": [{"fecha": f["fecha"], "pct_trote": r1(f["pct_trote"])} for f in filas[-12:]]}
    if modo == "ritmo":
        out["ritmo"] = [{"fecha": f["fecha"], "ritmo_s": round(f["ritmo_z2_s"])} for f in filas if f["ritmo_z2_s"]][-12:]
    return out


def build_numeros(hoy: date, filas: list, modo: str) -> dict:
    """Fila de números de Progreso por periodo (4, 8 o 12 semanas): corridas, minutos y km por semana y ritmo en Z2
    (modo "ritmo") o % trote (modo "trote"), con el valor del periodo anterior y el cambio. `filas` ya trae `ritmo_z2_s`."""
    def periodo(k, fin):
        g = [f for f in filas if fin - timedelta(weeks=k) < date.fromisoformat(f["fecha"]) <= fin]
        if not g:
            return None
        clave = "ritmo_z2_s" if modo == "ritmo" else "pct_trote"
        return {"corridas": len(g) / k, "minutos": sum(f["minutos"] for f in g) / k, "km": sum(f["km"] for f in g) / k,
                "extra": m.promedio([f[clave] for f in g])}
    campos = [("corridas", "corridas"), ("minutos", "minutos"), ("km", "km"), ("extra", "ritmo_z2" if modo == "ritmo" else "pct_trote")]
    out = {}
    for k in (4, 8, 12):
        ahora, antes = periodo(k, hoy), periodo(k, hoy - timedelta(weeks=k))
        items = []
        for campo, id_ in campos:
            v = None if ahora is None else ahora[campo]
            a = None if antes is None else antes[campo]
            delta = None if v is None or a is None else v - a
            if id_ == "ritmo_z2":
                v, a, delta = (None if x is None else round(x) for x in (v, a, delta))
            else:
                v, a, delta = (None if x is None else round(x, 1) for x in (v, a, delta))
            mejor = None if not delta else (delta < 0 if id_ == "ritmo_z2" else delta > 0)
            items.append({"id": id_, "valor": v, "anterior": a, "delta": delta, "bueno": mejor})
        out[str(k)] = items
    caminatas = {str(k): any((f["caminatas"] or 0) > 0 and hoy - timedelta(weeks=k) < date.fromisoformat(f["fecha"]) <= hoy
                             for f in filas) for k in (4, 8, 12)}
    return {"modo": modo, "periodos": out, "caminatas": caminatas}


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
        semanas.append({"inicio": s.isoformat(),
                        "cargas": {k["id"]: r1(c[k["id"]]) for k in config["categorias"]},
                        "carga_corrida": r1(c["run"]), "sin_rpe": c["sin_rpe"]})
    return {
        "distribucion": {"minutos": {z: r1(v) for z, v in dist["minutos"].items()},
                         "bajo": r1(dist["bajo"]), "limbo": r1(dist["limbo"]), "alto": r1(dist["alto"])},
        "carga": carga(ini), "carga_anterior": carga(ini - timedelta(days=7)), "carga_semanas": semanas,
        "fc_max": {**fc_max, "config": config["max_hr"], "fuente": "reloj" if reloj else "respaldo"},
        "umbrales": {k: config[k] for k in ("rhr_tolerance_bpm", "sleep_min_hours", "rpe_heavy",
                                            "max_hr", "max_hr_floor", "max_hr_review_above", "zone_pcts",
                                            "ceiling_tolerance_min", "done_ratio")},
    }


def texto_inicio_plan(inicio: date) -> str:
    return f"Tu plan empieza el {DIAS[inicio.weekday()]} {inicio.day} {MESES[inicio.month - 1]}"


def lista_es(items: list) -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else ""


DIAS_LARGO = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def build_ui(config: dict, plan: dict) -> dict:
    """Todo lo que el sitio necesita de la config: título, categorías y textos ya armados."""
    cats = config["categorias"]
    nombre = m.nombre_intensa(config)
    sesiones = [("Calidad" if s.get("tipo") == "calidad" else s["name"]) for s in plan["weeks"][0]["sessions"]] if plan.get("weeks") else []
    partes = []
    if sesiones:
        partes.append("Cada semana: " + (", ".join(sesiones[:-1]) + " y la " + sesiones[-1] if len(sesiones) > 1 else sesiones[0])
                      + " (sábado o domingo)")
    if config["dias_pierna"]:
        partes.append("Día de pierna: " + lista_es([DIAS_LARGO[d] for d in config["dias_pierna"]]))
    repo = os.environ.get("GITHUB_REPOSITORY")
    return {
        "titulo": config["titulo"],
        "categorias": [{k: c[k] for k in ("id", "nombre", "letra", "clase", "icono")} for c in cats],
        "nombre_intensa": nombre,
        "acciones_url": f"https://github.com/{repo}/actions/workflows/deploy.yml" if repo else None,
        "textos": {
            "semana": ". ".join(partes) + ".",
            "rpe_ayer": f"RPE del {nombre} de ayer" if nombre else "RPE de tu sesión intensa de ayer",
            "incluye": f"Incluye {lista_es([c['nombre'] for c in cats] + ['corridas'])}.",
            "fcmax_vacia": (f"Aún no hay clases de {nombre} medidas con correa. Con 2 semanas de mediciones se calcula la FC máx definitiva."
                            if nombre else "Aún no hay sesiones intensas medidas con correa. Con 2 semanas de mediciones se calcula la FC máx definitiva.")
            if config["fc_max_correa_desde"] else
            "Sin fecha de correa en la configuración: la FC máx sale del reloj. Si usas correa en tus sesiones intensas, agrega la fecha (fc_max_correa_desde) en config.yaml.",
        },
    }


def build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    # La FC máx viene del reloj; config["max_hr"] es solo respaldo si Garmin no la da.
    reloj = m.watch_max_hr(data["hr_zones"])
    config = {**config, "max_hr": reloj or config["max_hr"]}
    # La FC en reposo solo cuenta si esa noche hubo sueño registrado (señal, promedio 7 días, zonas y gráfica).
    data = {**data, "daily_summaries": m.rhr_con_sueno(data["daily_summaries"], data["sleep"])}
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
    sin_datos = not any(data[k] for k in ("activities", "daily_summaries", "sleep", "hrv"))
    inicio_plan = date.fromisoformat(config["plan_start"])
    if sin_datos:   # primera sincronización: Garmin tarda en mandar el historial
        texto = "Primera sincronización lista. Garmin tarda en mandar el historial; regresa en unas horas"
        if hoy < inicio_plan:
            texto += f". {texto_inicio_plan(inicio_plan)}"
        tarjeta = {**tarjeta, "tipo": "primera_sync", "texto": texto, "version": None, "sesion_id": None}
    elif tarjeta["tipo"] == "sin_plan" and hoy < inicio_plan:
        tarjeta = {**tarjeta, "texto": texto_inicio_plan(inicio_plan)}
    tarjeta["motivo"] = m.motivo(sigs, config) if tarjeta["version"] in ("suave", "descanso") else None

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    filas = m.run_rows(data["activities"], data["details"], config)
    semanas_hoy, semana_hoy_idx = build_semanas(hoy, data, config, plan)
    semanas_12 = build_weeks(hoy, data, config, plan)
    mejora = build_mejora(hoy, filas, semanas_12, zonas, data, config)
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
        "carreras": build_carreras(hoy, data, config),
        "mejores_marcas": m.mejores_marcas(historial_corridas(data, config), hoy, config),
        "progreso": {"resumen": {str(k): m.progress_summary(filas, hoy, k) for k in (4, 8, 12)},
                     "corridas": build_runs(data, config, plan),
                     "semanas": semanas_12,
                     "mejora": mejora,
                     "intensidad_semanas": [{"inicio": (monday(hoy) - timedelta(weeks=i)).isoformat(),
                                             **intensidad_semana(data["activities"], monday(hoy) - timedelta(weeks=i))}
                                            for i in range(11, -1, -1)],
                     "numeros": build_numeros(hoy, con_ritmo_z2(filas, zonas), mejora["modo"]),
                     "dias": build_days(hoy, data)},
        "composicion": m.composicion(data.get("inbody") if config.get("inbody", True) else None),
        "ui": build_ui(config, plan),
        "tipos": tipos.catalogo_json({tipos.forma_de(x) for w in plan["weeks"] for x in w["sessions"]}),
        "detalles": build_details(hoy, data, config, fc_max, reloj),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="fecha local YYYY-MM-DD (para pruebas)")
    ap.add_argument("--out", help="archivo de salida (por defecto <motor>/site/data.json)")
    ap.add_argument("--plan-start", help="inicio del plan YYYY-MM-DD (solo pruebas visuales)")
    args = ap.parse_args()
    config = cargar_config()
    tz = ZoneInfo(config["timezone"])
    ahora = datetime.now(tz)
    if args.day:
        ahora = datetime.combine(date.fromisoformat(args.day), ahora.time(), tzinfo=tz)
    plan = load_plan()
    if args.plan_start:
        config = {**config, "plan_start": args.plan_start}
        plan = {**plan, "start": args.plan_start}
    out = build(load_data(), plan, config, ahora)
    destino = Path(args.out) if args.out else ROOT / "site" / "data.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"OK: {destino} ({destino.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
