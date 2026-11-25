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
from ayuda import armar_ayuda

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
            zona = tipos.zona_unica(s)
            # planes viejos: los 10' Z2 del inicio de una calidad venían como "calentamiento"; son un tramo normal
            kind = "run" if s["kind"] == "warmup" and zona not in ("Z0", "Z1") else s["kind"]
            out.append({"kind": kind, "minutes": s["minutes"], "zone": zona,
                        "lpm": lpm_range(zona, zonas), "note": s.get("note", ""),
                        "optional": s.get("optional", False)})
    return out


def rampas_de(steps: list) -> dict:
    """El sitio dibuja 5' de calentar y 5' de enfriar (no cuentan en los minutos), salvo que el plan ya los traiga:
    calentamiento = primer paso suave (Z0/Z1) marcado como tal; enfriamiento = último paso marcado como tal."""
    def marcado(p, kind, nota):
        return p["kind"] == kind or (p["kind"] != "repeat" and p.get("note") == nota)
    return {"con_calentamiento": bool(steps) and marcado(steps[0], "warmup", "calentamiento")
            and tipos.zona_unica(steps[0]) in ("Z0", "Z1"),
            "con_enfriamiento": bool(steps) and marcado(steps[-1], "cooldown", "enfriamiento")}


def rachas_de(steps: list, zonas: list) -> list:
    """Rachas de la silueta (tramos seguidos del mismo color) con lo que va escrito encima: minutos, la zona como la
    dice el plan (una sola: "Z2"; si la racha mezcla zonas, la de la silueta) y sus lpm.
    Suman lo mismo que `silueta`."""
    planos = []
    def aplanar(pasos):
        for p in pasos:
            if p["kind"] == "repeat":
                for _ in range(p["times"]):
                    aplanar(p["steps"])
            else:
                planos.append(p)
    aplanar(steps)
    out = []
    for p, (m, zs, *_) in zip(planos, tipos.silueta_de(planos)):
        if out and out[-1]["_zs"] == zs:
            out[-1]["min"] += m
            out[-1]["_zonas"].add(tipos.zona_unica(p))
            out[-1]["opcional"] = out[-1]["opcional"] and bool(p.get("optional"))
        else:
            out.append({"min": m, "_zs": zs, "_zonas": {tipos.zona_unica(p)}, "opcional": bool(p.get("optional"))})
    for r in out:
        zona = r["_zonas"].pop() if len(r["_zonas"]) == 1 else r["_zs"]
        r.update({"zona": zona, "lpm": lpm_range(zona, zonas)})
        del r["_zs"], r["_zonas"]
    return out


ETIQUETA_CALIDAD = {"tempo_z3": "tempo Z3", "threshold": "threshold", "intervalos": "intervalos",
                    "progresivo": "progresivo", "fartlek": "fartlek"}


def estructura_calidad(s: dict) -> str:
    """"10' Z2 · 4×5' threshold (2' suave)" a partir de los pasos de una sesión de calidad. Los planes viejos traen
    además un enfriamiento al final (" · 5' suave")."""
    extras = s["steps"]
    calen = extras[0]
    enfria = next((p for p in extras if p["kind"] == "cooldown"), None)
    fin = f" · {enfria['minutes']}' suave" if enfria else ""
    if s.get("calidad_tipo") == "progresivo":
        medio = [p for p in extras[1:] if p["kind"] != "cooldown"]
        return (f"{calen['minutes']}' {calen['zone']} · " + " · ".join(f"{p['minutes']}' {tipos.zona_unica(p)}" for p in medio)
                + f" progresivo{fin}")
    if s.get("calidad_tipo") == "fartlek":
        trabajo = [p["minutes"] for p in extras if p["kind"] == "run" and p["zone"] == "Z3"]
        return f"{calen['minutes']}' {calen['zone']} · fartlek {'-'.join(str(t) for t in trabajo)}' en Z3 (con pausas de 2' suave){fin}"
    rep = next(p for p in extras if p["kind"] == "repeat")
    trabajo, rec = rep["steps"][0], rep["steps"][1]
    return (f"{calen['minutes']}' {calen['zone']} · {rep['times']}×{trabajo['minutes']}' "
            f"{ETIQUETA_CALIDAD.get(s.get('calidad_tipo'), 'calidad')} ({rec['minutes']}' suave){fin}")


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    extra = {k: s[k] for k in ("nota", "calidad_tipo", "variada_tipo") if k in s}
    if "objetivo" in s:
        extra["objetivo"] = {**s["objetivo"], "lpm": lpm_range(s["objetivo"]["zona"], zonas)}
        extra["estructura"] = estructura_calidad(s)
    forma, sil, sil_easy = tipos.forma_de(s), tipos.silueta_de(s["steps"]), tipos.silueta_de(easy["steps"])
    return {"id": s["id"], "tipo": s.get("tipo"), "name": s["name"], "minutes": s["minutes"], **extra,
            "forma": forma, "silueta": sil, "titulo": tipos.titulo_de(forma, tipos.silueta_de(s["steps"], False)), "rachas": rachas_de(s["steps"], zonas), **rampas_de(s["steps"]),
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": easy["name"], "minutes": easy["minutes"],
                     "silueta": sil_easy, "titulo": tipos.titulo_de(tipos.forma_de({"steps": easy["steps"]}), tipos.silueta_de(easy["steps"], False)),
                     "rachas": rachas_de(easy["steps"], zonas), **rampas_de(easy["steps"]),
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


def registro_esfuerzo(a: dict, details: dict, config: dict) -> dict:
    """Esfuerzo calculado con la FC y el RPE manual (si lo hay) de una actividad: se publican los dos."""
    return {"esfuerzo": m.esfuerzo_de(a, details, config), "rpe": (details.get(str(a["activityId"])) or {}).get("rpe")}


def datos_serie(a: dict, data: dict, config: dict) -> dict:
    """Lo que sale de la serie de FC de una corrida: ritmo a la FC de referencia y deriva cardiaca."""
    fila = next(iter(m.run_rows([a], data["details"], config)), None)
    if fila is None:
        return {"ritmo_ref_s": None, "deriva_pct": None, "deriva_ok": None}
    return {"ritmo_ref_s": None if fila["ritmo_ref_s"] is None else round(fila["ritmo_ref_s"]),
            "deriva_pct": fila["deriva_pct"], "deriva_ok": fila["deriva_ok"]}


def corrida_json(a: dict, plan_ses, data: dict, config: dict) -> dict:
    """Lo común de una corrida: minutos, km, caminadora, '¿lo hice bien?' y trote/caminata."""
    return {"minutos": r1(a["duration"] / 60), "km": r2((a.get("distance") or 0) / 1000),
            "caminadora": a["activityType"]["typeKey"] == "treadmill_running", "carrera": m.es_carrera(a, config),
            **m.run_check(a, plan_ses, config, m.zona_minutos(a, data["details"], m.zonas_de(config)),
                          light_on(m.day_of(a), data, config)["color"] in ("amarillo", "rojo")), "trote": rw_json(m.run_walk(a, data["details"])),
            **registro_esfuerzo(a, data["details"], config), **datos_serie(a, data, config)}


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
    """Actividades no-corrida del día, una entrada por categoría: esfuerzo máx, RPE máx y minutos sumados."""
    out = []
    for c in config["categorias"]:
        acts = [a for a in data["activities"] if m.classify(a, config) == c["id"] and m.day_of(a) == d]
        if not acts:
            continue
        esf = [e for a in acts if (e := m.esfuerzo_de(a, data["details"], config)) is not None]
        rpes = [r for a in acts if (r := (data["details"].get(str(a["activityId"])) or {}).get("rpe")) is not None]
        out.append({"cat": c["id"], "icono": c.get("icono", "punto"), "esfuerzo": max(esf) if esf else None,
                    "rpe": max(rpes) if rpes else None, "minutos": r1(sum(a["duration"] for a in acts) / 60)})
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


def ultima_semana(config: dict, plan: dict) -> date:
    """Lunes de la última semana del plan (cuenta las semanas repetidas)."""
    total = len(plan["weeks"]) + len(config.get("semanas_repetidas", []))
    return monday(date.fromisoformat(config["plan_start"])) + timedelta(weeks=total - 1)


def plan_terminado(hoy: date, config: dict, plan: dict) -> bool:
    return bool(plan.get("weeks")) and hoy >= ultima_semana(config, plan) + timedelta(days=7)


def base_prueba(tipo: str, filas: list, data: dict, config: dict):
    """Contra qué se compara la primera prueba: ritmo a FC ref (fc_fija) o % de trote (trote_continuo) promedio de las
    semanas 1–2 del plan; en 5k, la mejor marca de 5 km antes del inicio del plan. None si no hay."""
    inicio = date.fromisoformat(config["plan_start"])
    if tipo == "5k":
        previas = [(a["fastestSplit_5000"], a["startTimeLocal"][:10]) for a in historial_corridas(data, config)
                   if a.get("fastestSplit_5000") and a["startTimeLocal"][:10] < inicio.isoformat()]
        mejor = min(previas, default=None)
        return None if mejor is None else {"fuente": "mejor_5k", "fecha": mejor[1], "valor": round(mejor[0])}
    primeras = [f for f in filas if inicio <= date.fromisoformat(f["fecha"]) < inicio + timedelta(days=14)]
    v = m.promedio([f["ritmo_ref_s"] if tipo == "fc_fija" else f["pct_trote"] for f in primeras])
    return None if v is None else {"fuente": "inicio", "fecha": None, "valor": round(v, 1 if tipo == "trote_continuo" else 0)}


def prueba_resultado(data: dict, config: dict, plan: dict):
    """Resultado de la prueba de la última semana del plan y su comparación; None si el plan no trae prueba o no se hizo.
    {tipo, fecha, estado, valor, km, base, dif, mejor}. Se compara contra la última prueba del mismo tipo de
    `corrida.pruebas` y, si no hay, contra la base (semanas 1–2, o la mejor marca de 5 km)."""
    ini = ultima_semana(config, plan)
    semana, estado = week_assignment(ini, data, config, plan, hasta=ini + timedelta(days=6))
    ses = next((s for s in (semana or {}).get("sessions", []) if s.get("tipo") == "prueba"), None)
    e = next((e for e in estado if ses and e["id"] == "prueba" and e["fecha"]), None)
    if ses is None or e is None:
        return None
    a = next(a for a in data["activities"] if m.classify(a, config) == "run"
             and m.day_of(a).isoformat() == e["fecha"] and a["duration"] / 60 == e["minutos"])
    fila = m.run_rows([a], data["details"], config)[0]
    serie = (data["details"].get(str(a["activityId"])) or {}).get("serie") or []
    medido = m.valor_prueba(ses["prueba"], serie, fila["pct_trote"])
    km = (data["details"].get(str(a["activityId"])) or {}).get("ritmos_km") or []
    if medido is None and ses["prueba"] == "5k" and len(km) >= 5:   # sin serie, el ritmo por km de una carrera sirve
        medido = {"valor": sum(km[:5]), "km": 5.0}
    previas = [p for p in config.get("pruebas", []) if p["tipo"] == ses["prueba"] and p["fecha"] < e["fecha"]]
    base = ({"fuente": "prueba", "fecha": previas[-1]["fecha"], "valor": previas[-1]["valor"]} if previas
            else base_prueba(ses["prueba"], m.run_rows([a2 for a2 in data["activities"] if m.classify(a2, config) == "run"],
                                                         data["details"], config), data, config))
    out = {"tipo": ses["prueba"], "fecha": e["fecha"], "estado": e["estado"], "valor": None, "km": None,
           "base": base, "dif": None, "mejor": None}
    if medido:
        out.update(valor=medido["valor"], km=medido["km"], seguido=medido.get("seguido"), **(m.comparar_prueba(ses["prueba"], medido["valor"], base) or {}))
    return out


def resumen_semana_pasada(hoy: date, data: dict, config: dict, plan: dict):
    """Resumen de la semana pasada (lun–dom antes de la de hoy) para Hoy, sin Claude: sesiones hechas, minutos, km,
    % trote, días verdes, 80/20, carga contra la anterior, ritmo a FC ref contra la anterior, plan vs real y una
    sugerencia por reglas. None si esa semana no tuvo corridas ni plan."""
    ini = monday(hoy) - timedelta(days=7)
    s = build_semana(ini, hoy, data, config, plan)
    if not s["stats"]["corridas"] and not s["plan"]:
        return None
    luces = [light_on(ini + timedelta(days=i), data, config)["color"] for i in range(7)]
    verdes, rojos, sin_datos = (luces.count(c) for c in ("verde", "rojo", "sin_datos"))
    acts, det = data["activities"], data["details"]
    carga, previa = (m.week_load(acts, det, i, config)["total"] for i in (ini, ini - timedelta(days=7)))
    ritmo = lambda i: m.promedio([f["ritmo_ref_s"] for f in _semana_corridas(i, i + timedelta(days=6), acts, det, config)])  # noqa: E731
    ahora_r, antes_r = ritmo(ini), ritmo(ini - timedelta(days=7))
    plan_s = s["plan"]
    return {"inicio": s["inicio"], "fin": s["fin"], "n": s["n"],
            "sesiones_hechas": plan_s["hechas"] if plan_s else None, "sesiones_total": plan_s["total"] if plan_s else None,
            "minutos": s["stats"]["minutos"], "plan_min": plan_s["plan_min"] if plan_s else None,
            "km": s["stats"]["km"], "pct_trote": s["stats"]["pct_trote"],
            "dias_verdes": verdes, "dias_rojos": rojos, "dias_sin_datos": sin_datos,
            "intensidad": s["intensidad"],
            "carga": r1(carga), "carga_anterior": r1(previa),
            "ritmo_ref_s": None if ahora_r is None else round(ahora_r),
            "ritmo_ref_anterior_s": None if antes_r is None else round(antes_r),
            "plan_vs_real": [{"sesion": x["name"], "filas": x["corrida"]["plan_vs_real"]} for x in s["sesiones"]
                             if x["corrida"] and x["corrida"].get("plan_vs_real")],
            "sugerencia": m.sugerencia_semana(plan_s["hechas"] if plan_s else 0, plan_s["total"] if plan_s else None,
                                              rojos, carga, previa, config)}


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
    filas = m.run_rows(acts, data["details"], config)
    # promedio móvil de 4 del ritmo a FC ref, solo entre las corridas que lo tienen
    con = [i for i, f in enumerate(filas) if f["ritmo_ref_s"]]
    prom = dict(zip(con, m.rolling_mean([filas[i]["ritmo_ref_s"] for i in con], 4, 2)))
    return [{"fecha": f["fecha"], "sesion": nombres.get((f["fecha"], f["minutos"])), "carrera": f["carrera"],
             "icono": "medalla" if f["carrera"] else "correr",
             "minutos": r1(f["minutos"]), "km": r2(f["km"]), "fc_prom": r1(f["fc_prom"]),
             "pct_z1z2": r1(f["pct_z1z2"]), "caminadora": f["caminadora"],
             "ritmo_ref_s": None if f["ritmo_ref_s"] is None else round(f["ritmo_ref_s"]),
             "ritmo_ref_prom_s": None if prom.get(i) is None else round(prom[i]),
             "deriva_pct": f["deriva_pct"], "deriva_ok": f["deriva_ok"],
             **registro_esfuerzo(a, data["details"], config), **(rw_json(f) or dict.fromkeys(m.RW_CLAVES))}
            for i, (a, f) in enumerate(zip(acts, filas))]


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
    """12 semanas: minutos, km y trote/caminata de las corridas, los minutos del plan y los entrenos de la semana."""
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
                    "plan_min": sum(s["minutes"] for s in semana["sessions"]) if semana else None,
                    "entrenos": entrenos_semana(ini, data, config)})
    return out


def entrenos_semana(ini: date, data, config) -> list:
    """Entrenos registrados en la semana, uno por tipo con su cuenta: [{"icono", "nombre", "n"}]. Primero corridas y
    carreras, luego cada categoría en el orden de la config. Dos de la misma categoría a menos de 3 h cuentan como uno
    (m.sin_repetidas)."""
    if data is None or config is None:
        return []
    cuenta = {}
    for a in m.sin_repetidas(data["activities"], config):
        c = m.classify(a, config)
        if c and ini <= m.day_of(a) < ini + timedelta(days=7):
            k = ("carrera" if m.es_carrera(a, config) else "run") if c == "run" else c
            cuenta[k] = cuenta.get(k, 0) + 1
    tipos = [("run", "correr", "Corrida"), ("carrera", "medalla", "Carrera")] + \
        [(c["id"], c["icono"], c["nombre"]) for c in config["categorias"]]
    return [{"icono": ic, "nombre": nombre, "n": cuenta[k]} for k, ic, nombre in tipos if cuenta.get(k)]


def _tiempo(seg: float) -> str:
    """mm:ss, o h:mm:ss si pasa de una hora."""
    t = round(seg)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else m._mmss(t)


def texto_prueba(p: dict) -> dict:
    """Textos ya armados de la prueba para los cuadritos: valor, comparación y si mejoró (None = igual o sin base)."""
    tipo, v, base = p["tipo"], p["valor"], p.get("base")
    nombre = {"fc_fija": "30 min a FC fija", "trote_continuo": "trote continuo", "5k": "5 km a tope"}[tipo]
    fmt = (lambda x: (f"30 min seguidos ({x:.0f} % de trote)" if x >= m.PRUEBA_SEGUIDO_PCT else f"{x:.0f} % de trote") if tipo == "trote_continuo"
           else _tiempo(x) if tipo == "5k" else f"{m._mmss(x)} /km")
    out = {"nombre": nombre, "valor": None if v is None else fmt(v), "cambio": None, "mejor": p.get("mejor")}
    if v is None:
        out["cambio"] = "Sin resultado: la corrida no alcanzó para medirla"
    elif base is None or p.get("dif") is None:
        out["cambio"] = "Sin base para comparar: la próxima se comparará con esta"
    else:
        donde = {"prueba": "tu prueba anterior", "mejor_5k": "tu mejor 5 km"}.get(base["fuente"], "el inicio")
        mag = (f"{abs(p['dif']):.0f} puntos" if tipo == "trote_continuo" else _tiempo(abs(p["dif"])) if tipo == "5k" else f"{abs(p['dif']):.0f} s/km")
        if p["mejor"] is None:
            out["cambio"] = f"= igual que {donde}"
        else:
            out["cambio"] = f"{'▲' if p['dif'] > 0 else '▼'} {mag} vs {donde}, {'mejor' if p['mejor'] else 'peor'}"
    return out


def build_mejora(hoy: date, filas: list, zonas: list, data=None, config=None, plan=None) -> dict:
    """Cómo vas mejorando, ya calculado para los cuadritos: ritmo a la FC de referencia (promedio de las últimas 4 corridas
    válidas contra las semanas 1–2 del plan), última deriva válida y, si ya hay, el resultado de la prueba.
    `modo` ("ritmo" sin caminatas recientes, si no "trote") lo usa la fila de números. Cada cuadrito trae su `motivo`
    cuando no hay dato."""
    desde = monday(hoy) - timedelta(weeks=4)
    recientes = [f for f in filas if date.fromisoformat(f["fecha"]) >= desde]
    modo = "ritmo" if recientes and not any((f["caminatas"] or 0) > 0 for f in recientes) else "trote"
    ref = m.fc_referencia(zonas)
    validas = [f for f in filas if f["ritmo_ref_s"]]
    ult4 = validas[-4:]
    actual = m.promedio([f["ritmo_ref_s"] for f in ult4])
    inicio = None
    if config is not None:
        ini = date.fromisoformat(config["plan_start"])
        inicio = m.promedio([f["ritmo_ref_s"] for f in validas if ini <= date.fromisoformat(f["fecha"]) < ini + timedelta(days=14)])
    ritmo = {"fc_ref": ref, "n": len(ult4), "actual_s": None, "inicio_s": None, "dif_s": None, "mejora": None,
             "valor": None, "cambio": None, "motivo": None}
    if actual is None:
        ritmo["motivo"] = f"Aún no hay corridas al aire libre con el trote en Z2 (a {ref} lpm)"
    else:
        ritmo.update(actual_s=round(actual), valor=f"{m._mmss(actual)} /km",
                     motivo=f"Promedio de tus últimas {len(ult4)} corridas válidas" if len(ult4) > 1 else "Tu última corrida válida")
        if inicio is None:
            ritmo["cambio"] = None
            ritmo["motivo"] += "; sin corridas válidas en las semanas 1–2 del plan para comparar"
        else:
            dif = round(actual) - round(inicio)
            ritmo.update(inicio_s=round(inicio), dif_s=dif, mejora=None if dif == 0 else dif < 0,
                         cambio="= igual que al inicio" if dif == 0 else f"{'▲' if dif > 0 else '▼'} {abs(dif)} s vs inicio")
    der = next((f for f in reversed(filas) if f["deriva_pct"] is not None), None)
    deriva = {"valor": None, "fecha": None, "ok": None, "motivo": None}
    if der is None:
        deriva["motivo"] = "Aún no hay una corrida que cumpla (40' o más, casi toda en Z2)"
    else:
        deriva.update(valor=f"{der['deriva_pct']:.1f} %", fecha=der["fecha"], ok=der["deriva_ok"],
                      motivo="Menos de 5 % es buena base")
    prueba = None
    if data is not None and config is not None and plan is not None and plan.get("weeks"):
        res = prueba_resultado(data, config, plan)
        prueba = None if res is None else {**res, **texto_prueba(res)}
    return {"modo": modo, "ritmo": ritmo, "deriva": deriva, "prueba": prueba}


def build_numeros(hoy: date, filas: list, modo: str) -> dict:
    """Fila de números de Progreso por periodo (4, 8 o 12 semanas): corridas, minutos y km por semana y ritmo a la FC de
    referencia (modo "ritmo") o % trote (modo "trote"), con el valor del periodo anterior y el cambio. `filas` es run_rows;
    usa el mismo conjunto de corridas por periodo que la frase del periodo (m.periodo_filas)."""
    def periodo(k, atras):
        g = m.periodo_filas(filas, hoy, k, atras)
        if not g:
            return None
        clave = "ritmo_ref_s" if modo == "ritmo" else "pct_trote"
        return {"corridas": len(g) / k, "minutos": sum(f["minutos"] for f in g) / k, "km": sum(f["km"] for f in g) / k,
                "extra": m.promedio([f.get(clave) for f in g])}
    campos = [("corridas", "corridas"), ("minutos", "minutos"), ("km", "km"), ("extra", "ritmo_ref" if modo == "ritmo" else "pct_trote")]
    out = {}
    for k in (4, 8, 12):
        ahora, antes = periodo(k, 0), periodo(k, 1)
        items = []
        for campo, id_ in campos:
            v = None if ahora is None else ahora[campo]
            a = None if antes is None else antes[campo]
            delta = None if v is None or a is None else v - a
            if id_ == "ritmo_ref":
                v, a, delta = (None if x is None else round(x) for x in (v, a, delta))
            else:
                v, a, delta = (None if x is None else round(x, 1) for x in (v, a, delta))
            mejor = None if not delta else (delta < 0 if id_ == "ritmo_ref" else delta > 0)
            items.append({"id": id_, "valor": v, "anterior": a, "delta": delta, "bueno": mejor})
        out[str(k)] = items
    caminatas = {str(k): any((f["caminatas"] or 0) > 0 for f in m.periodo_filas(filas, hoy, k)) for k in (4, 8, 12)}
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
    carga = lambda s: {k: r1(v) for k, v in m.week_load(acts, data["details"], s, config).items()}  # noqa: E731
    dist = m.week_distribution(acts, ini)
    semanas = []
    for i in range(11, -1, -1):
        s = ini - timedelta(weeks=i)
        c = m.week_load(acts, data["details"], s, config)
        semanas.append({"inicio": s.isoformat(),
                        "cargas": {k["id"]: r1(c[k["id"]]) for k in config["categorias"]},
                        "carga_corrida": r1(c["run"])})
    return {
        "distribucion": {"minutos": {z: r1(v) for z, v in dist["minutos"].items()},
                         "bajo": r1(dist["bajo"]), "limbo": r1(dist["limbo"]), "alto": r1(dist["alto"])},
        "carga": carga(ini), "carga_anterior": carga(ini - timedelta(days=7)), "carga_semanas": semanas,
        "fc_max": {**fc_max, "config": config["max_hr"], "fuente": "reloj" if reloj else "respaldo"},
        "umbrales": {k: config[k] for k in ("rhr_tolerance_bpm", "sleep_min_hours", "esfuerzo_duro",
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
            "descarga": "Las semanas de descarga (línea punteada) bajan la carga" + ("." if config["caminatas"] else ": todo continuo en Z2."),
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
    config = {**config, "zonas": zonas}   # derivadas de este día: esfuerzo, ritmo a FC ref y plan vs real las leen de aquí

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
    elif plan_terminado(hoy, config, plan):   # pasó la última semana: resultado de la prueba y a pedir el siguiente bloque
        tarjeta = {**tarjeta, "tipo": "plan_terminado", "texto": "Plan terminado", "version": None, "sesion_id": None,
                   "prueba": prueba_resultado(data, config, plan),
                   "siguiente": "Corre /ajustar para el siguiente bloque"}
    ayer_dato = m.ayer_duro(hoy, data["activities"], data["details"], config)
    tarjeta["motivo"] = m.motivo(sigs, config, ayer_dato) if tarjeta["version"] in ("suave", "descanso") else None

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    filas = m.run_rows(data["activities"], data["details"], config)
    semanas_hoy, semana_hoy_idx = build_semanas(hoy, data, config, plan)
    semanas_12 = build_weeks(hoy, data, config, plan)
    mejora = build_mejora(hoy, filas, zonas, data, config, plan)
    return {
        "generado": ahora.isoformat(timespec="minutes"),
        "datos_al": datos_al,
        "zonas": [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in zonas],
        "rhr_promedio_7d": r1(rhr),
        "aviso_zonas": m.max_hr_above_watch(fc_max["estimacion"], config["max_hr"]),
        "hoy": {"semaforo": luz, "señales": signals_list(sigs), "ayer": ayer_dato, "tarjeta": tarjeta,
                "semana_pasada": resumen_semana_pasada(hoy, data, config, plan)},
        "ultima_corrida": last_run(data, config, plan),
        "semana": build_week(hoy, data, config, estado, plan),
        "semanas_hoy": semanas_hoy, "semana_hoy_idx": semana_hoy_idx,
        "plan": {"inicio": plan["start"], "semana_actual": n, "semanas_repetidas": repetidas,
                 "semanas": [convert_week(w, zonas) for w in plan["weeks"]],
                 "estado_sesiones": [{**e, "minutos": r1(e["minutos"]),
                                         "corrida": corrida_de_sesion(e, semana_plan, data, config)} for e in estado]},
        "carreras": build_carreras(hoy, data, config),
        "mejores_marcas": m.mejores_marcas(historial_corridas(data, config), hoy, config),
        "progreso": {"fc_ref": m.fc_referencia(zonas),
                     "resumen": {str(k): m.progress_summary(filas, hoy, k, m.fc_referencia(zonas)) for k in (4, 8, 12)},
                     "corridas": build_runs(data, config, plan),
                     "semanas": semanas_12,
                     "mejora": mejora,
                     "intensidad_semanas": [{"inicio": (monday(hoy) - timedelta(weeks=i)).isoformat(),
                                             **intensidad_semana(data["activities"], monday(hoy) - timedelta(weeks=i))}
                                            for i in range(11, -1, -1)],
                     "numeros": build_numeros(hoy, filas, mejora["modo"]),
                     "dias": build_days(hoy, data)},
        "composicion": m.composicion(data.get("inbody") if config.get("inbody", True) else None),
        "ui": build_ui(config, plan),
        "ayuda": armar_ayuda(config, plan, zonas, m.fc_referencia(zonas)),
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
