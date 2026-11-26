"""Convierte data/ + plan + config en site/data.json (solo campos de una lista blanca).

Uso: python dashboard/build.py [--day YYYY-MM-DD] [--plan-start YYYY-MM-DD] [--out data.json]
Es el único lugar con reloj: "hoy" se calcula en la zona horaria del config.
"""
import argparse
import hashlib
import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import i18n
import metrics as m
import plan_i18n
import tipos
from i18n import tt
from ajustes import USER_DIR, cargar_config
from ayuda import armar_ayuda

ROOT = Path(__file__).parent.parent  # el motor (aquí vive site/)
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]   # español (referencia); lo que sale usa i18n.csv("motor.dias_cortos")


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def load_data(user_dir=None) -> dict:
    user_dir = Path(user_dir) if user_dir else USER_DIR
    d = user_dir / "data"
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
        "inbody": load(user_dir / "plan" / "inbody.json"),
    }


def load_plan(user_dir=None) -> dict:
    plan = (Path(user_dir) if user_dir else USER_DIR) / "plan" / "plan.json"
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
                        "lpm": lpm_range(zona, zonas), "note": plan_i18n.nota(s.get("note", "")),
                        "optional": s.get("optional", False),
                        **({"nota_id": plan_i18n.nota_id(s.get("note", ""))} if plan_i18n.nota_id(s.get("note", "")) else {})})
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
    suave = tt("motor.suave")
    fin = f" · {enfria['minutes']}' {suave}" if enfria else ""
    if s.get("calidad_tipo") == "progresivo":
        medio = [p for p in extras[1:] if p["kind"] != "cooldown"]
        return (f"{calen['minutes']}' {calen['zone']} · " + " · ".join(f"{p['minutes']}' {tipos.zona_unica(p)}" for p in medio)
                + f" {tt('motor.estructura.progresivo')}{fin}")
    if s.get("calidad_tipo") == "fartlek":
        trabajo = [p["minutes"] for p in extras if p["kind"] == "run" and p["zone"] == "Z3"]
        return f"{calen['minutes']}' {calen['zone']} · " + tt("motor.estructura.fartlek", t="-".join(str(t) for t in trabajo)) + fin
    rep = next(p for p in extras if p["kind"] == "repeat")
    trabajo, rec = rep["steps"][0], rep["steps"][1]
    return (f"{calen['minutes']}' {calen['zone']} · {rep['times']}×{trabajo['minutes']}' "
            f"{tt('motor.estructura.' + s['calidad_tipo']) if s.get('calidad_tipo') in ETIQUETA_CALIDAD else tt('motor.calidad_min')} ({rec['minutes']}' {suave}){fin}")


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    extra = {k: s[k] for k in ("nota", "calidad_tipo", "variada_tipo") if k in s}
    if "nota" in extra:
        extra["nota"] = plan_i18n.nota(extra["nota"])
    if "objetivo" in s:
        extra["objetivo"] = {**s["objetivo"], "lpm": lpm_range(s["objetivo"]["zona"], zonas)}
        extra["estructura"] = estructura_calidad(s)
    forma, sil, sil_easy = tipos.forma_de(s), tipos.silueta_de(s["steps"]), tipos.silueta_de(easy["steps"])
    return {"id": s["id"], "tipo": s.get("tipo"), "name": plan_i18n.nombre(s["name"]), "minutes": s["minutes"], **extra,
            "forma": forma, "silueta": sil, "titulo": tipos.titulo_de(forma, tipos.silueta_de(s["steps"], False)), "rachas": rachas_de(s["steps"], zonas), **rampas_de(s["steps"]),
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": plan_i18n.nombre(easy["name"]), "minutes": easy["minutes"],
                     "silueta": sil_easy, "titulo": tipos.titulo_de(tipos.forma_de({"steps": easy["steps"]}), tipos.silueta_de(easy["steps"], False)),
                     "rachas": rachas_de(easy["steps"], zonas), **rampas_de(easy["steps"]),
                     "steps": convert_steps(easy["steps"], zonas)}}


def convert_week(w: dict, zonas: list) -> dict:
    extra = {"evento": w["evento"]} if w.get("evento") else {}   # semana que un viaje o una carrera cambió (solo la web)
    return {"n": w["n"], "block": w["block"], "kind": w["kind"], "etiqueta": w["kind"] if w["kind"] == "descarga" else "carga",
            "focus": plan_i18n.focus(w["focus"]), **extra,
            "sessions": [convert_session(s, zonas) for s in w["sessions"]]}


MARCAS_SEMANA = ("carrera", "viaje", "enfermedad", "prueba")   # por prioridad: la primera que aplica es el ícono de la esquina


def marca_semana(w: dict, ini: date | None, config: dict):
    """La marca principal de la semana (la de mayor prioridad) o None; ver `marcas_semana`."""
    return next(iter(marcas_semana(w, ini, config)), None)


def marcas_semana(w: dict, ini: date | None, config: dict) -> list:
    """Evento de una semana del plan para el ícono del cuadrito (carrera, viaje, enfermedad, prueba) o None. Sale de
    las fechas de `config` (metas, eventos) contra la semana `ini` (lunes), de `w["evento"]` (plan vivo) y de una sesión de prueba."""
    hay = {"carrera" if w.get("evento") == "carrera" else "", "viaje" if w.get("evento") in ("viaje", "viaje_igual") else "",
           "prueba" if any(s.get("tipo") == "prueba" for s in w["sessions"]) else ""}
    if ini is not None:
        fin = ini + timedelta(days=6)
        cae = lambda desde, hasta: date.fromisoformat(str(desde)) <= fin and date.fromisoformat(str(hasta or desde)) >= ini
        hay |= {"carrera" for x in config.get("metas") or [] if cae(x["fecha"], x["fecha"])}
        hay |= {e["tipo"] if e["tipo"] != "lesion" else "enfermedad" for e in config.get("eventos") or []
                if e["tipo"] in ("viaje", "enfermedad", "lesion") and cae(e["desde"], e["hasta"])}
    return [x for x in MARCAS_SEMANA if x in hay]


def detalle_marcas(w: dict, ini: date | None, config: dict, marcas: list) -> dict:
    """Para la burbuja de cada ícono: {tipo: {"d": desde, "h": hasta}} (ISO; `n` = nombre de la sesión de prueba). Solo fechas
    de la config o de la semana: nada de nombres de actividades de Garmin."""
    fin = ini + timedelta(days=6) if ini else None
    out = {}
    for tipo in marcas:
        d, h = (ini.isoformat(), fin.isoformat()) if ini else (None, None)
        if ini:
            cae = lambda a, b: date.fromisoformat(str(a)) <= fin and date.fromisoformat(str(b or a)) >= ini
            if tipo == "carrera":
                f = next((str(x["fecha"]) for x in config.get("metas") or [] if cae(x["fecha"], x["fecha"])), None)
                d, h = (f, f) if f else (d, h)
            elif tipo in ("viaje", "enfermedad"):
                ev = next((e for e in config.get("eventos") or [] if (e["tipo"] if e["tipo"] != "lesion" else "enfermedad") == tipo
                           and cae(e["desde"], e["hasta"])), None)
                d, h = (str(ev["desde"]), str(ev["hasta"] or ev["desde"])) if ev else (d, h)
        item = {"d": d, "h": h} if d else {}
        if tipo == "prueba":
            nombre = next((s.get("name") for s in w["sessions"] if s.get("tipo") == "prueba"), None)
            if nombre:
                item["n"] = plan_i18n.nombre(nombre)
        out[tipo] = item
    return out


def cumplimiento_semana(hechas: int, total: int):
    """Semana pasada: "completa" (todas), "casi" (al menos 2/3) o "baja" (el resto; la página la muestra neutra). None sin sesiones."""
    if total <= 0:
        return None
    return "completa" if hechas >= total else "casi" if 3 * hechas >= 2 * total else "baja"


def semanas_plan(plan: dict, zonas: list, hoy: date, data: dict, config: dict) -> list:
    """Las semanas del plan para el Plan: `etiqueta` (carga/descarga), `marca` (evento del ícono) y `progreso`
    {hechas, total} de las pasadas y la actual (lo que dice estado_sesiones; las futuras no traen la clave) y `cumplimiento`
    (solo las pasadas: completa, casi o baja) y `estados` [{id, estado, ajustada}] de cada sesión (pasadas: hecha/incompleta/no_hecha;
    futuras: pendiente; la semana actual usa plan.estado_sesiones)."""
    inicio = date.fromisoformat(config["plan_start"])
    sec = m.secuencia_semanas(inicio, config.get("semanas_repetidas", []), config.get("plan_semanas", 12), config.get("pausas", []))
    lunes = {}
    for i, n in enumerate(sec):
        if n is not None and (n not in lunes or monday(inicio) + timedelta(weeks=i) <= monday(hoy)):
            lunes[n] = monday(inicio) + timedelta(weeks=i)   # una semana repetida: la última que ya empezó
    out = []
    for w in plan["weeks"]:
        ini, cw = lunes.get(w["n"]), convert_week(w, zonas)
        marca = marca_semana(w, ini, config)
        if marca:
            cw["marca"] = marca
            todas = marcas_semana(w, ini, config)
            cw["marcas_det"] = detalle_marcas(w, ini, config, todas)   # fechas para la burbuja de cada ícono
            if len(todas) > 1:
                cw["marcas"] = todas   # dos eventos en la semana: la página muestra los dos íconos, en este orden
        if ini is not None and ini <= monday(hoy):
            _, estado = week_assignment(ini, data, config, plan, hasta=min(ini + timedelta(days=6), hoy))
            cw["progreso"] = {"hechas": sum(1 for e in estado if e["estado"] == "hecha"), "total": len(w["sessions"])}
            if ini < monday(hoy):
                cw["cumplimiento"] = cumplimiento_semana(cw["progreso"]["hechas"], cw["progreso"]["total"])
                # pasada: lo que no se hizo es «no_hecha» (la actual lleva el suyo en plan.estado_sesiones)
                cw["estados"] = [{"id": e["id"], "estado": "no_hecha" if e["estado"] == "pendiente" else e["estado"],
                                  "ajustada": e["ajustada"]} for e in estado]
        if "estados" not in cw and (ini is None or ini > monday(hoy)):
            cw["estados"] = [{"id": s["id"], "estado": "pendiente", "ajustada": False} for s in w["sessions"]]   # futura
        out.append(cw)
    return out


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
    n = m.semana_del_plan(day, config)
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
        dias.append({"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[i],
                     "tipo": day_type(d, hoy, acts, config), "luz": luz})
    filas = _semana_corridas(ini, hoy, acts, data["details"], config)
    previas = _semana_corridas(ini - timedelta(days=7), ini - timedelta(days=1), acts, data["details"], config)
    n = m.semana_del_plan(hoy, config)
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
        sesion = {"id": plan_ses["id"], "name": plan_i18n.nombre(plan_ses["name"]), "version": "suave" if suave else "normal",
                  "minutes_plan": plan_ses["easy"]["minutes"] if suave else plan_ses["minutes"]}
    return {"fecha": dia.isoformat(), "fc_prom": r1(a.get("averageHR")), "sesion": sesion,
            **corrida_json(a, plan_ses, data, config)}


def registro_esfuerzo(a: dict, details: dict, config: dict) -> dict:
    """Esfuerzo calculado con la FC y el RPE manual (si lo hay) de una actividad: se publican los dos."""
    return {"esfuerzo": m.esfuerzo_de(a, details, config), "rpe": (details.get(str(m.id_de(a))) or {}).get("rpe")}


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
        rpes = [r for a in acts if (r := (data["details"].get(str(m.id_de(a))) or {}).get("rpe")) is not None]
        out.append({"cat": c["id"], "icono": c.get("icono", "punto"), "esfuerzo": max(esf) if esf else None,
                    "rpe": max(rpes) if rpes else None, "minutos": r1(sum(a["duration"] for a in acts) / 60)})
    return out


def dia_de_semana(d: date, hoy: date, runs: list, sesiones: list, data: dict, config: dict, acts=None) -> dict:
    """Un día del calendario: corrida más larga (con su sesión) y otras actividades registradas (futuro: vacío)."""
    del_dia = [a for a in runs if m.day_of(a) == d]
    corrida = None
    if del_dia:
        a = max(del_dia, key=lambda a: a["duration"])
        e = next((e for e in sesiones if e["fecha"] == d.isoformat() and e["minutos"] == a["duration"] / 60), None)
        corrida = {"minutos": r1(a["duration"] / 60), "sesion_nombre": e["name"] if e else tt("motor.extra"),
                   "estado": e["estado"] if e else "extra", "carrera": m.es_carrera(a, config)}
        corrida["icono"] = "medalla" if corrida["carrera"] else "correr"
    otras = otras_del_dia(d, data, config)
    return {"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[d.weekday()],
            "luz": light_on(d, data, config)["color"] if d <= hoy else None,
            "corrida": corrida, "corridas_n": len(del_dia), "otras": otras,
            "actividades": actividades_del_dia(d, acts or [], config, sesiones, data["details"])}


def marcar_planeados(dias: list, sesiones: list, hoy: date, pasada: bool) -> None:
    """Pone `planeado: True` en los días de hoy en adelante de la semana en curso donde toca correr una sesión
    pendiente. El plan no fija día, así que: la Larga al primer fin de semana libre y las demás en los primeros
    días libres. Semanas pasadas y futuras no marcan nada."""
    if pasada or not any(d["fecha"] <= hoy.isoformat() for d in dias):
        return
    pendientes = [s for s in sesiones if s["estado"] == "pendiente"]
    for d in dias:
        d["plan_ses"] = ""   # semana en curso: "" = el plan no pone sesión ese día (descanso)
    libres = [d for d in dias if d["fecha"] >= hoy.isoformat() and d["corrida"] is None]
    for s in sorted(pendientes, key=lambda s: s.get("tipo") not in ("larga", "prueba")):
        if not libres:
            return
        if s.get("tipo") in ("larga", "prueba"):
            d = next((d for d in libres if date.fromisoformat(d["fecha"]).weekday() >= 5), None)
            if d is None:
                continue
        else:
            d = next((d for d in libres if date.fromisoformat(d["fecha"]).weekday() < 5), libres[0])
        d["planeado"] = True
        d["plan_ses"] = s["name"]
        libres.remove(d)


def intensidad_semana(acts: list, ini: date) -> dict:
    """Minutos por zona (Z1–Z5, Z0 fuera) de corridas + actividades de la semana y % bajo / limbo / alto: la cuenta de 80/20."""
    d = m.week_distribution(acts, ini)
    return {"minutos": {z: r1(v) for z, v in d["minutos"].items()}, "bajo": r1(d["bajo"]), "limbo": r1(d["limbo"]),
            "alto": r1(d["alto"])}


TE_ETIQUETAS = ("aerobic_base", "tempo", "recovery", "anaerobic_capacity", "vo2max", "speed", "lactate_threshold")
CURVA_PUNTOS = 120


def curva_fc(serie, n: int = CURVA_PUNTOS):
    """FC de una actividad bajada a ≤ n puntos (promedio por tramo de tiempo igual): {"seg": duración, "fc": [lpm]}.
    `serie` es [[seg, m, fc]] (sin GPS que salga de aquí). None si no hay FC suficiente."""
    pts = [(p[0], p[2]) for p in serie or [] if len(p) >= 3 and p[2]]
    if len(pts) < 2 or pts[-1][0] <= 0:
        return None
    total = pts[-1][0]
    cubos = [[] for _ in range(min(n, len(pts)))]
    for seg, fc in pts:
        cubos[min(int(seg / total * len(cubos)), len(cubos) - 1)].append(fc)
    medias = [round(sum(c) / len(c)) for c in cubos if c]
    return {"seg": round(total), "fc": medias}


def detalle_actividad(a: dict, details: dict, config: dict) -> dict:
    """Lo que se ve al abrir una actividad: tiempos, distancia, ritmo o velocidad, FC, calorías, desnivel, tiempo por zona,
    efecto de entrenamiento (números y etiqueta del catálogo), y en corridas cadencia y ritmo por km. Todo calculado aquí;
    nunca nombres, IDs, GPS ni textos de Garmin. Cada dato que falte va como None."""
    det = details.get(str(m.id_de(a))) or {}
    corrida = m.classify(a, config) == "run"
    km = (a.get("distance") or 0) / 1000
    seg = a.get("movingDuration") or a["duration"]
    zm = m.zone_minutes(a)
    total = sum(zm.values())
    bajo, limbo, alto = (sum(zm[z] for z in zs) for zs in (("Z1", "Z2"), ("Z3",), ("Z4", "Z5")))
    zonas = ({"minutos": {z: r1(v) for z, v in zm.items()}, "bajo": r1(bajo / total * 100), "limbo": r1(limbo / total * 100),
              "alto": r1(alto / total * 100)} if total > 0 else None)
    etiqueta = str(a.get("trainingEffectLabel") or "").lower()
    ae, an = a.get("aerobicTrainingEffect"), a.get("anaerobicTrainingEffect")
    ritmos = det.get("ritmos_km") if corrida else None
    return {"duracion_min": r1(a["duration"] / 60), "km": r2(km) if km >= 0.05 else None,
            "ritmo_s": round(seg / km) if corrida and km >= 0.1 else None,
            "vel_kmh": r1(km / (seg / 3600)) if not corrida and km >= 0.1 and seg else None,
            "fc_prom": round(a["averageHR"]) if a.get("averageHR") else None, "fc_max": round(a["maxHR"]) if a.get("maxHR") else None,
            "kcal": round(a["calories"]) if a.get("calories") else None,
            "desnivel_m": round(a["elevationGain"]) if a.get("elevationGain") else None,
            "zonas": zonas,
            "te_aerobico": r1(ae) if ae else None, "te_anaerobico": r1(an) if an else None,
            "te_etiqueta": tt(f"motor.te.{etiqueta}") if etiqueta in TE_ETIQUETAS else None,
            "cadencia": round(a["averageRunningCadenceInStepsPerMinute"]) if corrida and a.get("averageRunningCadenceInStepsPerMinute") else None,
            "ritmos_km": [round(x) for x in ritmos] if ritmos else None,
            "pulso": m.pulso_de(a, details, config),
            "curva_fc": curva_fc(det.get("serie"))}


def actividades_del_dia(d: date, acts: list, config: dict, sesiones=None, details=None) -> list:
    """Todo lo que se hizo un día, una fila por actividad: tipo (texto del catálogo), minutos, km, FC prom. y, en
    corridas, la sesión del plan que cumplió. `acts` ya viene sin repetidas. Nunca nombres, IDs ni GPS."""
    nombres = {"run": (tt("motor.entreno.run"), "correr"), "carrera": (tt("motor.entreno.carrera"), "medalla"),
               **{c["id"]: (c["nombre"], c.get("icono", "punto")) for c in config["categorias"]}}
    out = []
    for a in sorted((x for x in acts if m.day_of(x) == d and m.classify(x, config)), key=lambda x: x["startTimeLocal"]):
        c = m.classify(a, config)
        carrera = c == "run" and m.es_carrera(a, config)
        k = ("carrera" if carrera else "run") if c == "run" else c
        e = next((e for e in sesiones or [] if c == "run" and e["fecha"] == d.isoformat()
                  and e["minutos"] == a["duration"] / 60), None)
        km = (a.get("distance") or 0) / 1000
        out.append({"cat": c, "nombre": nombres[k][0], "icono": nombres[k][1], "minutos": round(a["duration"] / 60),
                    "km": r2(km) if km >= 0.05 else None, "fc_prom": round(a["averageHR"]) if a.get("averageHR") else None,
                    "carrera": carrera, "sesion": {"nombre": e["name"], "estado": e["estado"]} if e else None,
                    "detalle": detalle_actividad(a, details or {}, config)})
    return out


def build_semana_libre(hoy: date, data: dict, config: dict) -> dict:
    """«Tu semana» (modo sin plan): actividades por día, minutos y km contra el promedio de las 4 semanas anteriores,
    zonas, recuperación y racha de semanas activas. Nunca nombres, IDs ni GPS: solo tipo y minutos."""
    ini = monday(hoy)
    acts = m.sin_repetidas(data["activities"], config)

    def de_semana(i):
        a, b = i, i + timedelta(days=7)
        return [x for x in acts if m.classify(x, config) and a <= m.day_of(x) < b]

    def totales(lista):
        return (r1(sum(x["duration"] for x in lista) / 60),
                r1(sum((x.get("distance") or 0) for x in lista if m.classify(x, config) == "run") / 1000))
    esta = de_semana(ini)
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        items = actividades_del_dia(d, esta, config, details=data["details"])
        dias.append({"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[i], "hoy": d == hoy,
                     "futuro": d > hoy, "actividades": items})
    prev = [totales(de_semana(ini - timedelta(weeks=k))) for k in range(1, 5)]
    min_s, km_s = totales(esta)
    rec = next(iter(reversed(build_days(hoy, data))), {})
    recuperacion = {k: rec.get(k) for k in ("hrv_7d", "rhr_7d", "sueño_7d") if rec.get(k) is not None}
    racha, k = 0, 0 if esta else 1
    while k < 52 and de_semana(ini - timedelta(weeks=k)):
        racha, k = racha + 1, k + 1
    return {"dias": dias, "actividades": len(esta), "minutos": min_s, "km": km_s,
            "promedio_minutos": r1(sum(p[0] for p in prev) / 4), "promedio_km": r1(sum(p[1] for p in prev) / 4),
            "intensidad": intensidad_semana(data["activities"], ini) if esta else None,
            "recuperacion": recuperacion or None, "racha_semanas": racha}


def build_semana(ini: date, hoy: date, data: dict, config: dict, plan: dict) -> dict:
    """Una semana calendario (lun–dom) de la vista Hoy: stats de todas las corridas, calendario, sesiones y extras."""
    fin = ini + timedelta(days=6)
    hasta = min(fin, hoy)
    repetidas = config.get("semanas_repetidas", [])
    n = m.semana_del_plan(ini, config)
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
    acts = m.sin_repetidas(data["activities"], config)
    dias = [dia_de_semana(ini + timedelta(days=i), hoy, runs, sesiones, data, config, acts) for i in range(7)]
    marcar_planeados(dias, sesiones, hoy, pasada)
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


def _total_semanas(config: dict, plan: dict) -> int:
    """Semanas del calendario del plan: las del plan + repetidas + pausas (viaje sin correr, enfermedad)."""
    inicio = date.fromisoformat(config["plan_start"])
    n = len(plan["weeks"]) + len(config.get("semanas_repetidas", []))
    for i in sorted({(date.fromisoformat(p) - inicio).days // 7 for p in config.get("pausas", [])}):
        if 0 <= i <= n:
            n += 1
    return n


def ultima_semana(config: dict, plan: dict) -> date:
    """Lunes de la última semana del plan (cuenta las semanas repetidas)."""
    return monday(date.fromisoformat(config["plan_start"])) + timedelta(weeks=_total_semanas(config, plan) - 1)


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
    serie = (data["details"].get(str(m.id_de(a))) or {}).get("serie") or []
    medido = m.valor_prueba(ses["prueba"], serie, fila["pct_trote"])
    km = (data["details"].get(str(m.id_de(a))) or {}).get("ritmos_km") or []
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
    """Resumen de la semana pasada (lun–dom antes de la de hoy) para Hoy, sin Claude: sesiones hechas, las mismas stats
    que Esta semana (corridas, minutos, km, % trote), la intensidad y una sugerencia por reglas. None si esa semana no tuvo corridas ni plan."""
    ini = monday(hoy) - timedelta(days=7)
    s = build_semana(ini, hoy, data, config, plan)
    if not s["stats"]["corridas"] and not s["plan"]:
        return None
    rojos = [light_on(ini + timedelta(days=i), data, config)["color"] for i in range(7)].count("rojo")
    acts, det = data["activities"], data["details"]
    carga, previa = (m.week_load(acts, det, i, config)["total"] for i in (ini, ini - timedelta(days=7)))
    plan_s = s["plan"]
    return {"inicio": s["inicio"], "fin": s["fin"], "n": s["n"],
            "sesiones_hechas": plan_s["hechas"] if plan_s else None, "sesiones_total": plan_s["total"] if plan_s else None,
            "stats": s["stats"], "intensidad": s["intensidad"],
            "sugerencia": m.sugerencia_semana(plan_s["hechas"] if plan_s else 0, plan_s["total"] if plan_s else None,
                                              rojos, carga, previa, config)}


SEMANAS_ANTES_PLAN = 13


def build_semanas(hoy: date, data: dict, config: dict, plan: dict):
    """(semanas_hoy, índice de la semana de hoy): las del plan (con repetidas) y, si hoy cae fuera, la de hoy."""
    inicio = monday(date.fromisoformat(config["plan_start"]))
    total = _total_semanas(config, plan)
    # Hasta 13 semanas previas al plan, desde la primera con alguna actividad (solo calendario real, sin plan).
    previas = [monday(m.day_of(a)) for a in data["activities"]]
    previas = [x for x in previas if inicio - timedelta(weeks=SEMANAS_ANTES_PLAN) <= x < inicio]
    antes = {min(previas) + timedelta(weeks=i) for i in range((inicio - min(previas)).days // 7)} if previas else set()
    inicios = sorted({inicio + timedelta(weeks=i) for i in range(total)} | {monday(hoy)} | antes)
    # Antes de que empiece el plan se muestra la semana 1 como vista previa.
    mostrar = inicio if hoy < date.fromisoformat(config["plan_start"]) else monday(hoy)
    semanas = [{**build_semana(i, hoy, data, config, plan), **({"antes_plan": True} if i in antes else {})} for i in inicios]
    return semanas, inicios.index(mostrar)


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
        n = m.semana_del_plan(ini, config)
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
    tipos = [("run", "correr", tt("motor.entreno.run")), ("carrera", "medalla", tt("motor.entreno.carrera"))] + \
        [(c["id"], c["icono"], c["nombre"]) for c in config["categorias"]]
    return [{"icono": ic, "nombre": nombre, "n": cuenta[k]} for k, ic, nombre in tipos if cuenta.get(k)]


def _tiempo(seg: float) -> str:
    """mm:ss, o h:mm:ss si pasa de una hora."""
    t = round(seg)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else m._mmss(t)


def texto_prueba(p: dict) -> dict:
    """Textos ya armados de la prueba para los cuadritos: valor, comparación y si mejoró (None = igual o sin base)."""
    tipo, v, base = p["tipo"], p["valor"], p.get("base")
    nombre = tt(f"motor.prueba.{tipo}")
    fmt = (lambda x: (tt("motor.prueba.seguidos", x=f"{x:.0f}") if x >= m.PRUEBA_SEGUIDO_PCT else tt("motor.prueba.pct_trote", x=f"{x:.0f}")) if tipo == "trote_continuo"
           else _tiempo(x) if tipo == "5k" else f"{m._mmss(x)} /km")
    out = {"nombre": nombre, "valor": None if v is None else fmt(v), "cambio": None, "mejor": p.get("mejor")}
    if v is None:
        out["cambio"] = tt("motor.cuadro.sin_resultado")
    elif base is None or p.get("dif") is None:
        out["cambio"] = tt("motor.cuadro.sin_base")
    else:
        donde = tt({"prueba": "motor.cuadro.donde_prueba", "mejor_5k": "motor.cuadro.donde_mejor_5k"}.get(base["fuente"], "motor.cuadro.donde_inicio"))
        mag = (tt("motor.cuadro.puntos", n=f"{abs(p['dif']):.0f}") if tipo == "trote_continuo" else _tiempo(abs(p["dif"])) if tipo == "5k" else f"{abs(p['dif']):.0f} s/km")
        if p["mejor"] is None:
            out["cambio"] = tt("motor.cuadro.igual", donde=donde)
        else:
            out["cambio"] = tt("motor.cuadro.vs", flecha="▲" if p["dif"] > 0 else "▼", mag=mag, donde=donde,
                              res=tt("motor.cuadro.mejor" if p["mejor"] else "motor.cuadro.peor"))
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
        ritmo["motivo"] = tt("motor.mejora.sin_aire", ref=ref)
    else:
        ritmo.update(actual_s=round(actual), valor=f"{m._mmss(actual)} /km",
                     motivo=tt("motor.mejora.promedio", n=len(ult4)) if len(ult4) > 1 else tt("motor.mejora.ultima"))
        if inicio is None:
            ritmo["cambio"] = None
            ritmo["motivo"] += tt("motor.mejora.sin_inicio")
        else:
            dif = round(actual) - round(inicio)
            ritmo.update(inicio_s=round(inicio), dif_s=dif, mejora=None if dif == 0 else dif < 0,
                         cambio=tt("motor.mejora.igual_inicio") if dif == 0 else tt("motor.mejora.vs_inicio", flecha="▲" if dif > 0 else "▼", n=abs(dif)))
    der = next((f for f in reversed(filas) if f["deriva_pct"] is not None), None)
    deriva = {"valor": None, "fecha": None, "ok": None, "motivo": None}
    if der is None and (config.get("sensor") == "muñeca" or any(f.get("pulso") == "muñeca" for f in filas)):
        deriva["motivo"] = tt("motor.mejora.deriva_muneca")
    elif der is None:
        deriva["motivo"] = tt("motor.mejora.deriva_sin")
    else:
        deriva.update(valor=f"{der['deriva_pct']:.1f} %", fecha=der["fecha"], ok=der["deriva_ok"],
                      motivo=tt("motor.mejora.deriva_ok"))
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
    return tt("motor.inicio_plan", dia=i18n.csv("motor.dias_cortos")[inicio.weekday()], n=inicio.day,
              mes=i18n.csv("motor.meses_cortos")[inicio.month - 1])


lista_es = i18n.lista   # "a, b y c" / "a, b and c" según el idioma en curso


def build_ui(config: dict, plan: dict) -> dict:
    """Todo lo que el sitio necesita de la config: título, categorías y textos ya armados."""
    cats = config["categorias"]
    nombre = m.nombre_intensa(config)
    sesiones = [(tt("motor.nombre.calidad") if s.get("tipo") == "calidad" else plan_i18n.nombre(s["name"])) for s in plan["weeks"][0]["sessions"]] if plan.get("weeks") else []
    partes = []
    if sesiones:
        lista = (tt("motor.ui.cada_semana_y", ini=", ".join(sesiones[:-1]), ult=sesiones[-1]) if len(sesiones) > 1 else sesiones[0])
        partes.append(tt("motor.ui.cada_semana", lista=lista))
    if config["dias_pierna"]:
        partes.append(tt("motor.ui.pierna", dias=lista_es([i18n.csv("motor.dias_largos")[d] for d in config["dias_pierna"]])))
    repo = os.environ.get("GITHUB_REPOSITORY") if config.get("modo") != "web" else None   # en la web la liga la pone quien llama
    acciones = config.get("acciones_url") or (f"https://github.com/{repo}/actions/workflows/deploy.yml" if repo else None)
    return {
        "titulo": i18n.tt("sitio.titulo_defecto") if config["titulo"] == "Mi entreno" else config["titulo"],   # el título de fábrica, traducido
        "categorias": [{k: c[k] for k in ("id", "nombre", "letra", "clase", "icono")} for c in cats],
        "nombre_intensa": nombre,
        "acciones_url": acciones,
        "sin_plan": bool(config.get("sin_plan", False)),
        "plan_acciones": list(config.get("plan_acciones") or []),   # solo en la web: [{texto, url}] sobre el plan
        "liga_ajustar_plan": config.get("liga_ajustar_plan") or None,   # solo en la web: url de «Ajustar mi plan»; null = sin botón
        "cuerpo_nuevo": config.get("cuerpo_nuevo") or None,   # solo en la web: url de «Agregar medición»; null = sin botón
        "grupos": int(config.get("grupos") or 0),   # solo en la web: en cuántos grupos está la persona (0 = sin pestaña Grupo)
        "editar_urls": {str(k): str(v) for k, v in (config.get("editar_urls") or {}).items()},   # solo en la web: {"<n>/<id>": url} de las sesiones editables
        "menu": [{"texto": i["texto"], "url": i["url"]} for i in config.get("menu") or []],   # solo en la web: [{texto, url relativa}]
        "textos": {
            "semana": ". ".join(partes) + ".",
            "descarga": tt("motor.ui.descarga" if config["caminatas"] else "motor.ui.descarga_cont"),
            "incluye": tt("motor.ui.incluye", lista=lista_es([c["nombre"] for c in cats] + [tt("motor.ui.corridas")])),
            "fcmax_vacia": (tt("motor.ui.fcmax_vacia_n", nombre=nombre) if nombre else tt("motor.ui.fcmax_vacia"))
            if config["fc_max_correa_desde"] else
            tt("motor.ui.fcmax_sin_fecha", donde=tt("motor.ui.donde_web" if config.get("modo") == "web" else "motor.ui.donde_yaml")),
        },
    }


def eventos_plan(config: dict) -> dict:
    """`plan.eventos` (viajes, enfermedades, carreras con fecha) para el calendario del Plan. Sin eventos ni metas la
    clave no existe (así el data.json de quien no los usa queda idéntico)."""
    out = [{"tipo": e["tipo"], "desde": e["desde"], "hasta": e["hasta"], "correr": e["correr"], "modo": e["modo"]}
           for e in config.get("eventos") or []]
    out += [{"tipo": "carrera", "desde": x["fecha"], "hasta": x["fecha"], "nombre": x["nombre"],
             "distancia_km": x["distancia_km"]} for x in config.get("metas") or []]
    return {"eventos": sorted(out, key=lambda e: e["desde"])} if out else {}


def huella(contenido) -> str:
    """Huella corta y estable de lo que dice un aviso: quien lo dio por entendido lo ve de nuevo solo si ella cambia."""
    return hashlib.sha1(str(contenido).encode("utf-8")).hexdigest()[:10]


def huellas_avisos(tarjeta: dict, aviso_zonas, fc_max: dict, semaforo: dict, semana_n, sugerencia=None, semana_inicio=None) -> dict:
    """{id: huella} de los avisos que hoy están activos (los que el sitio puede cerrar con «Entendido»). Sin aviso, sin clave."""
    out = {}
    if tarjeta.get("aviso"):
        out["hoy"] = huella(tarjeta["aviso"])
    if aviso_zonas:
        out["zonas"] = huella(aviso_zonas)
    if fc_max.get("revisar"):
        out["fcmax"] = huella(round(fc_max["estimacion"]))
    if semaforo.get("repetir_semana"):
        out["repetir"] = huella(semana_n)
    if sugerencia and sugerencia.get("tipo") != "sigue":   # «sigue así» no es aviso: no se cierra
        out["sugerencia"] = huella(f"{sugerencia['tipo']}|{semana_inicio}")   # tipo + semana, no el texto: en la web y en el sitio el texto cambia de forma
    return out


def etiqueta_sesion(ses: dict, suave: bool = False) -> str:
    """«Z2 #1 · 20 min», «Larga suave · Z2 · 15 min»: nombre, zona (si el nombre no la dice) y minutos."""
    base = ses["easy"] if suave and ses.get("easy") else ses
    nombre = plan_i18n.nombre(ses["name"]) + (f" {tt('motor.version.suave')}" if suave and ses.get("easy") else "")
    zona = None if suave else (ses.get("objetivo") or {}).get("zona")
    if not zona:
        por_zona: dict = {}
        for minutos, z, *_ in tipos.silueta_de(base["steps"]):
            por_zona[z] = por_zona.get(z, 0) + minutos
        zona = max(por_zona, key=por_zona.get) if por_zona else None
    partes = [nombre] + ([zona] if zona and zona not in nombre else []) + [tt("motor.titular.min", n=f"{base['minutes']:g}")]
    return " · ".join(partes)


def titular_hoy(tarjeta: dict, sesiones: list, manana_id: str | None = None) -> str | None:
    """Línea 2 de Hoy: la sesión completa (nombre, zona, minutos) y, si ya está planeada, la de mañana.
    `sesiones` = sesiones del plan de esta semana. None = el sitio la deja vacía (plan terminado)."""
    tipo = tarjeta.get("tipo")
    por_id = {s["id"]: s for s in sesiones or []}
    sig = por_id.get(manana_id)
    manana = lambda base: f"{base} · " + tt("motor.titular.manana", sesion=etiqueta_sesion(sig)) if sig else base   # noqa: E731
    if tipo == "sesion":
        if tarjeta.get("version") == "descanso":
            return manana(tt("motor.titular.descanso"))
        ses = por_id.get(tarjeta.get("sesion_id"))
        return tt("motor.titular.toca", sesion=etiqueta_sesion(ses, tarjeta.get("version") == "suave")) if ses else None
    if tipo == "hecha_hoy":
        return manana(tt("motor.titular.hecha"))
    if tipo == "otra":
        return manana(tt("motor.titular.otra", cat=tarjeta.get("categoria")))
    if tipo == "completa":
        return tt("motor.titular.completa")
    if tipo in ("sin_plan", "primera_sync", "pausa"):
        return tarjeta.get("texto")
    return None


def build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    """data.json de una persona. Los textos que arma el motor salen en `config["idioma"]` (es si no lo trae)."""
    with i18n.usar(config.get("idioma")):
        return _build(data, plan, config, ahora)


def _build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    # La FC máx viene del reloj; config["max_hr"] es solo respaldo si Garmin no la da.
    reloj = m.watch_max_hr(data["hr_zones"])
    config = {**config, "max_hr": reloj or config["max_hr"]}
    # La FC en reposo solo cuenta si esa noche hubo sueño registrado (señal, promedio 7 días, zonas y gráfica).
    data = {**data, "daily_summaries": m.rhr_con_sueno(data["daily_summaries"], data["sleep"])}
    fc_max = m.max_hr_progress(data["activities"], config, data["details"])
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
        texto = tt("motor.build.primera")
        if hoy < inicio_plan:
            texto += f". {texto_inicio_plan(inicio_plan)}"
        tarjeta = {**tarjeta, "tipo": "primera_sync", "texto": texto, "version": None, "sesion_id": None}
    elif tarjeta["tipo"] == "sin_plan" and hoy < inicio_plan:
        tarjeta = {**tarjeta, "texto": texto_inicio_plan(inicio_plan)}
    elif plan_terminado(hoy, config, plan):   # pasó la última semana: resultado de la prueba y a pedir el siguiente bloque
        tarjeta = {**tarjeta, "tipo": "plan_terminado", "texto": "Plan terminado", "version": None, "sesion_id": None,
                   "prueba": prueba_resultado(data, config, plan),
                   "siguiente": ("Ve a Ajustes para el siguiente bloque" if config.get("modo") == "web"
                                 else "Corre /ajustar para el siguiente bloque"),
                   **({"siguiente_url": "/plan/acciones#siguiente"} if config.get("modo") == "web" else {})}
    elif m.en_pausa(hoy, config):   # semana de viaje sin correr o de enfermedad: el plan espera
        tarjeta = {**tarjeta, "tipo": "pausa", "texto": tt("motor.build.pausa"),
                   "version": None, "sesion_id": None}
    ayer_dato = m.ayer_duro(hoy, data["activities"], data["details"], config)
    tarjeta["motivo"] = m.motivo(sigs, config, ayer_dato) if tarjeta["version"] in ("suave", "descanso") else None
    tarjeta["opciones"] = m.opciones_hoy(tarjeta["version"], tarjeta.get("sesion"))
    tarjeta["recomendada"] = tarjeta["version"] if tarjeta["opciones"] else None
    manana_id = tarjeta.get("proxima_id") or ((m._elegir_pendiente(hoy + timedelta(days=1), estado)[0] or {}).get("id")
                                              if estado and tarjeta["version"] == "descanso" else None)

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    filas = m.run_rows(data["activities"], data["details"], config)
    semanas_hoy, semana_hoy_idx = build_semanas(hoy, data, config, plan)
    semanas_12 = build_weeks(hoy, data, config, plan)
    mejora = build_mejora(hoy, filas, zonas, data, config, plan)
    sem_pasada = resumen_semana_pasada(hoy, data, config, plan)
    return {
        "generado": ahora.isoformat(timespec="minutes"),
        "datos_al": datos_al,
        "zonas": [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in zonas],
        "rhr_promedio_7d": r1(rhr),
        "aviso_zonas": m.max_hr_above_watch(fc_max["estimacion"], reloj, fc_max.get("pulso_pico") or "banda", fc_max.get("pico")),
        "hoy": {"semaforo": luz, "señales": signals_list(sigs), "ayer": ayer_dato, "tarjeta": tarjeta,
                "titular": titular_hoy(tarjeta, (semana_plan or {}).get("sessions"), manana_id),
                "semana_pasada": sem_pasada},
        "ultima_corrida": last_run(data, config, plan),
        "semana": build_week(hoy, data, config, estado, plan),
        "semanas_hoy": semanas_hoy, "semana_hoy_idx": semana_hoy_idx,
        **({"semana_libre": build_semana_libre(hoy, data, config)} if config.get("sin_plan") else {}),
        "plan": {"inicio": plan["start"], "semana_actual": n, "semanas_repetidas": repetidas,
                 **eventos_plan(config),
                 "semanas": semanas_plan(plan, zonas, hoy, data, config),
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
        "ui": {**build_ui(config, plan), "avisos": huellas_avisos(
            tarjeta, m.max_hr_above_watch(fc_max["estimacion"], reloj, fc_max.get("pulso_pico") or "banda", fc_max.get("pico")),
            fc_max, luz, n, (sem_pasada or {}).get("sugerencia"), (sem_pasada or {}).get("inicio"))},
        "idioma": i18n.actual(),   # el sitio pinta en el mismo idioma que los textos del motor
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
    i18n.escribir_json(destino.parent / "i18n")   # los textos del sitio (es.json, en.json) junto al data.json
    print(f"OK: {destino} ({destino.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
