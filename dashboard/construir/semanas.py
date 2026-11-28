"""Semanas del plan y de la vista: marcas, asignación, tarjetas de semana, resumen y retomar."""
from dashboard import i18n, plan_i18n, semanal
from dashboard.metricas import carga as mt_carga, carreras as mt_carreras, comun as mt_comun, semana as mt_semana
from dashboard.i18n import tt
from datetime import date, timedelta
from dashboard.construir.actividades import actividades_del_dia, corrida_de_sesion, corrida_plana, historial_corridas, otras_del_dia
from dashboard.construir.comun import _total_semanas, light_on, monday, plan_terminado, r1, week_assignment
from dashboard.construir.progreso import build_days
from dashboard.construir.sesiones import convert_week
from dashboard.construir.ui import texto_inicio_plan


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


def semanas_plan(plan: dict, zonas: list, hoy: date, semanas_hoy: list, config: dict, ritmo=None) -> list:
    ritmo = semanal.ritmo_o_nivel(ritmo, (plan.get("meta") or {}).get("nivel"))
    """Las semanas del plan para el Plan: `etiqueta` (carga/descarga), `marca` (evento del ícono) y `progreso`
    {hechas, total} de las pasadas y la actual (lo que dice estado_sesiones; las futuras no traen la clave) y `cumplimiento`
    (solo las pasadas: completa, casi o baja) y `estados` [{id, estado, ajustada}] de cada sesión (pasadas: hecha/incompleta/no_hecha;
    futuras: pendiente; la semana actual usa plan.estado_sesiones). El avance sale de `semanas_hoy` (build_semana): un solo conteo."""
    por_inicio = {s["inicio"]: s for s in semanas_hoy}
    inicio = date.fromisoformat(config["plan_start"])
    sec = mt_semana.secuencia_de(config)
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
            sem = por_inicio[ini.isoformat()]
            cw["progreso"] = {"hechas": sem["plan"]["hechas"], "total": sem["plan"]["total"], "pct": sem["plan"]["pct"]}
            cw["minutos"], cw["km"] = sem["stats"]["minutos"], sem["stats"]["km"]   # lo hecho de la semana (volumen), en las dos unidades
            if ini < monday(hoy):
                cw["cumplimiento"] = semanal.cumplimiento(cw["progreso"]["hechas"], cw["progreso"]["total"])
                # pasada: lo que no se hizo es «no_hecha» (la actual lleva el suyo en plan.estado_sesiones)
                cw["estados"] = [{"id": e["id"], "estado": e["estado"], "ajustada": e["ajustada"]} for e in sem["sesiones"]]
        if "estados" not in cw and (ini is None or ini > monday(hoy)):
            cw["estados"] = [{"id": s["id"], "estado": "pendiente", "ajustada": False} for s in w["sessions"]]   # futura
        cw["plan_min"] = semanal.minutos_plan(w)   # el objetivo del plan solo existe en minutos
        if ini is None or ini >= monday(hoy):   # km estimados (minutos ÷ ritmo fácil, o el del nivel) de la semana actual y las futuras
            cw["plan_km"] = semanal.volumen_plan(cw["plan_min"], "km", ritmo) if ini is None or ini > monday(hoy) else None
            for ses in cw["sessions"]:
                ses["km_est"] = semanal.volumen_plan(ses.get("minutes"), "km", ritmo)
        out.append(cw)
    return out


# --- bloques del JSON ---

def signals_list(sigs: dict) -> list:
    return [{"id": k, "estado": s["estado"], "valor": s["valor"],
             "referencia": s["referencia"], "texto": s["texto"]} for k, s in sigs.items()]


def day_type(day: date, hoy: date, acts: list, config: dict) -> str:
    tipos = {mt_comun.classify(a, config) for a in acts if mt_comun.day_of(a) == day}
    for c in config["categorias"]:
        if c["id"] in tipos:
            return c["id"]
    if "run" in tipos:
        return "corrida"
    if day > hoy:
        return "futuro"
    return "descanso" if day < hoy else "hoy"


def build_week(hoy: date, data: dict, config: dict, estado: list, plan: dict) -> dict:
    ini, acts = monday(hoy), data["activities"]
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        luz = light_on(d, data, config)["color"] if d <= hoy else None
        dias.append({"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[i],
                     "tipo": day_type(d, hoy, acts, config), "luz": luz})
    r = semanal.resumen_semana(ini, hoy, data, config)
    previas = semanal.resumen_semana(ini - timedelta(days=7), ini - timedelta(days=1), data, config)
    n = mt_semana.semana_del_plan(hoy, config)
    semana = next((w for w in plan["weeks"] if w["n"] == n), None)
    c = semanal.conteo(estado)
    return {"dias": dias, "sesiones_total": c["total"], "hechas": c["hechas"], "incompletas": c["incompletas"],
            "minutos": r["minutos"], "km": r["km"], "min_trote": r["min_trote"], "min_camina": r["min_camina"],
            "pct_trote": r["pct_trote"], "plan_min": semanal.minutos_plan(semana),
            "anterior": {k: previas[k] for k in ("minutos", "km", "min_trote")}}


def dia_de_semana(d: date, hoy: date, runs: list, sesiones: list, data: dict, config: dict, acts=None) -> dict:
    """Un día del calendario: corrida más larga (con su sesión) y otras actividades registradas (futuro: vacío)."""
    del_dia = [a for a in runs if mt_comun.day_of(a) == d]
    corrida = None
    if del_dia:
        a = max(del_dia, key=lambda a: a["duration"])
        e = next((e for e in sesiones if e["fecha"] == d.isoformat() and e["minutos"] == a["duration"] / 60), None)
        corrida = {"minutos": r1(a["duration"] / 60), "sesion_nombre": e["name"] if e else tt("motor.extra"),
                   "estado": e["estado"] if e else "extra", "carrera": mt_carreras.es_carrera(a, config)}
        corrida["icono"] = "medalla" if corrida["carrera"] else "correr"
    otras = otras_del_dia(d, data, config)
    return {"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[d.weekday()],
            "luz": light_on(d, data, config)["color"] if d <= hoy else None,
            "corrida": corrida, "corridas_n": len(del_dia), "otras": otras,
            "actividades": actividades_del_dia(d, acts or [], config, sesiones, data["details"])}


def intensidad_semana(acts: list, ini: date) -> dict:
    """Minutos por zona (Z1–Z5, Z0 fuera) de corridas + actividades de la semana y % bajo / limbo / alto: la cuenta de 80/20."""
    d = mt_carga.week_distribution(acts, ini)
    return {"minutos": {z: r1(v) for z, v in d["minutos"].items()}, "bajo": r1(d["bajo"]), "limbo": r1(d["limbo"]),
            "alto": r1(d["alto"])}


def build_semana_libre(hoy: date, data: dict, config: dict) -> dict:
    """«Tu semana» (modo sin plan): actividades por día, minutos y km contra el promedio de las 4 semanas anteriores,
    zonas, recuperación y racha de semanas activas. Nunca nombres, IDs ni GPS: solo tipo y minutos."""
    ini = monday(hoy)
    acts = data["activities"]

    def de_semana(i):
        a, b = i, i + timedelta(days=7)
        return [x for x in acts if mt_comun.classify(x, config) and a <= mt_comun.day_of(x) < b]

    def totales(i):
        r = semanal.resumen_semana(i, i + timedelta(days=6), data, config, todas=True)
        return r["minutos"], r["km"]
    esta = de_semana(ini)
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        items = actividades_del_dia(d, esta, config, details=data["details"])
        dias.append({"fecha": d.isoformat(), "dia_semana": i18n.csv("motor.dias_cortos")[i], "hoy": d == hoy,
                     "futuro": d > hoy, "actividades": items})
    prev = [totales(ini - timedelta(weeks=k)) for k in range(1, 5)]
    min_s, km_s = totales(ini)
    rec = next(iter(reversed(build_days(hoy, data))), {})
    recuperacion = {k: rec.get(k) for k in ("hrv_7d", "rhr_7d", "sueño_7d") if rec.get(k) is not None}
    racha = semanal.racha_semanas([], 0, hoy, data, config, libre=True)["semanas"]
    return {"dias": dias, "actividades": len(esta), "minutos": min_s, "km": km_s,
            "promedio_minutos": r1(sum(p[0] for p in prev) / 4), "promedio_km": r1(sum(p[1] for p in prev) / 4),
            "intensidad": intensidad_semana(data["activities"], ini) if esta else None,
            "recuperacion": recuperacion or None, "racha_semanas": racha}


def build_semana(ini: date, hoy: date, data: dict, config: dict, plan: dict) -> dict:
    """Una semana calendario (lun–dom) de la vista Hoy: stats de todas las corridas, calendario, sesiones y extras."""
    fin = ini + timedelta(days=6)
    hasta = min(fin, hoy)
    n = mt_semana.semana_del_plan(ini, config)
    semana, estado = week_assignment(ini, data, config, plan, hasta=hasta)
    pasada = fin < hoy
    sesiones = [{**e, "estado": "no_hecha" if pasada and e["estado"] == "pendiente" else e["estado"],
                 "minutos": e["minutos"], "corrida": corrida_de_sesion(e, semana, data, config)} for e in estado]
    runs = sorted((a for a in data["activities"] if mt_comun.classify(a, config) == "run" and ini <= mt_comun.day_of(a) <= hasta),
                  key=lambda a: a["startTimeLocal"])
    sin_asignar = [(e["fecha"], e["minutos"]) for e in estado if e["fecha"]]
    extras = []
    for a in runs:
        clave = (mt_comun.day_of(a).isoformat(), a["duration"] / 60)
        if clave in sin_asignar:
            sin_asignar.remove(clave)
        else:
            extras.append({"fecha": clave[0], **corrida_plana(a, None, data, config)})
    acts = data["activities"]
    dias = [dia_de_semana(ini + timedelta(days=i), hoy, runs, sesiones, data, config, acts) for i in range(7)]
    for s in sesiones:
        s["minutos"] = r1(s["minutos"])
    previas = semanal.resumen_semana(ini - timedelta(days=7), ini - timedelta(days=1), data, config)
    c = semanal.conteo(sesiones)
    stats_s = semanal.resumen_semana(ini, hasta, data, config)
    return {"inicio": ini.isoformat(), "fin": fin.isoformat(), "n": n if semana else None,
            "kind": semana["kind"] if semana else None, "block": semana["block"] if semana else None,
            "estado": "pasada" if pasada else "actual" if ini <= hoy else "futura",
            "stats": stats_s,
            "plan": {"total": c["total"], "hechas": c["hechas"], "incompletas": c["incompletas"], "pct": semanal.pct(c["hechas"], c["total"]),
                     "plan_min": semanal.minutos_plan(semana),
                     "min_pct": semanal.pct(stats_s["minutos"], semanal.minutos_plan(semana)),
                     **({"faltan": mt_semana.faltan_texto(sesiones)} if not pasada and ini <= hoy and mt_semana.faltan_texto(sesiones) else {})} if semana else None,
            "anterior": {k: previas[k] for k in ("minutos", "km", "min_trote")},
            "dias": dias, "sesiones": sesiones, "extras": extras,
            "intensidad": intensidad_semana(data["activities"], ini)}


def resumen_semana_pasada(hoy: date, data: dict, config: dict, plan: dict, semanas_hoy: list = ()):
    """Resumen de la semana pasada (lun–dom antes de la de hoy) para Hoy, sin Claude: sesiones hechas, las mismas stats
    que Esta semana (corridas, minutos, km, % trote), la intensidad y una sugerencia por reglas. None si esa semana no tuvo corridas ni plan."""
    ini = monday(hoy) - timedelta(days=7)
    s = next((x for x in semanas_hoy if x["inicio"] == ini.isoformat()), None) or build_semana(ini, hoy, data, config, plan)
    if not s["stats"]["corridas"] and not s["plan"]:
        return None
    rojos = [light_on(ini + timedelta(days=i), data, config)["color"] for i in range(7)].count("rojo")
    acts, det = data["activities"], data["details"]
    carga, previa = (mt_carga.week_load(acts, det, i, config)["total"] for i in (ini, ini - timedelta(days=7)))
    plan_s = s["plan"]
    return {"inicio": s["inicio"], "fin": s["fin"], "n": s["n"],
            "sesiones_hechas": plan_s["hechas"] if plan_s else None, "sesiones_total": plan_s["total"] if plan_s else None,
            "pct": min(100, plan_s["pct"]) if plan_s and plan_s["pct"] is not None else None,
            "stats": s["stats"], "intensidad": s["intensidad"],
            "sugerencia": mt_semana.sugerencia_semana(plan_s["hechas"] if plan_s else 0, plan_s["total"] if plan_s else None,
                                              rojos, carga, previa, config)}


SEMANAS_ANTES_PLAN = 13


def build_semanas(hoy: date, data: dict, config: dict, plan: dict):
    """(semanas_hoy, índice de la semana de hoy): las del plan (con repetidas) y, si hoy cae fuera, la de hoy."""
    inicio = monday(date.fromisoformat(config["plan_start"]))
    total = _total_semanas(config, plan)
    # Hasta 13 semanas previas al plan, desde la primera con alguna actividad (solo calendario real, sin plan).
    previas = [monday(mt_comun.day_of(a)) for a in data["activities"]]
    previas = [x for x in previas if inicio - timedelta(weeks=SEMANAS_ANTES_PLAN) <= x < inicio]
    antes = {min(previas) + timedelta(weeks=i) for i in range((inicio - min(previas)).days // 7)} if previas else set()
    if monday(hoy) < inicio:
        antes.add(monday(hoy))   # la semana de hoy, aunque esté vacía, es «antes del plan»
    inicios = sorted({inicio + timedelta(weeks=i) for i in range(total)} | {monday(hoy)} | antes)
    # Siempre se abre en la semana de hoy; antes de que empiece el plan, esa semana liga a la semana 1.
    hoy_i = inicios.index(monday(hoy))
    empieza = {"plan_empieza": {"texto": texto_inicio_plan(inicio), "idx": inicios.index(inicio)}} if monday(hoy) < inicio else {}
    semanas = [{**build_semana(i, hoy, data, config, plan), **({"antes_plan": True} if i in antes else {}),
                **(empieza if i == monday(hoy) else {})} for i in inicios]
    return semanas, hoy_i


def build_weeks(hoy: date, data: dict, config: dict, plan: dict) -> list:
    """Serie de semanas (`semanal.serie_semanas`): minutos, km y trote/caminata de las corridas, los minutos del plan y los entrenos."""
    out = []
    for ini in semanal.serie_semanas(hoy, plan, config):
        r = semanal.resumen_semana(ini, ini + timedelta(days=6), data, config)
        n = mt_semana.semana_del_plan(ini, config)
        semana = next((w for w in plan["weeks"] if w["n"] == n), None)
        out.append({"inicio": ini.isoformat(), "actual": ini == monday(hoy), "minutos": r["minutos"], "km": r["km"],
                    "min_trote": r["min_trote"], "min_camina": r["min_camina"],
                    "plan_min": semanal.minutos_plan(semana),
                    "entrenos": entrenos_semana(ini, data, config)})
    return out


def entrenos_semana(ini: date, data, config) -> list:
    """Entrenos registrados en la semana, uno por tipo con su cuenta: [{"icono", "nombre", "n"}]. Primero corridas y
    carreras, luego cada categoría en el orden de la config. Las encadenadas (`metricas.corridas.unir_encadenadas`) ya son una sola."""
    if data is None or config is None:
        return []
    cuenta = {}
    for a in data["activities"]:
        c = mt_comun.classify(a, config)
        if c and ini <= mt_comun.day_of(a) < ini + timedelta(days=7):
            k = ("carrera" if mt_carreras.es_carrera(a, config) else "run") if c == "run" else c
            cuenta[k] = cuenta.get(k, 0) + 1
    tipos = [("run", "correr", tt("motor.entreno.run")), ("carrera", "medalla", tt("motor.entreno.carrera"))] + \
        [(c["id"], c["icono"], c["nombre"]) for c in config["categorias"]]
    return [{"icono": ic, "nombre": nombre, "n": cuenta[k]} for k, ic, nombre in tipos if cuenta.get(k)]


DIAS_SIN_CORRER = 14


def retomar_sugerido(hoy: date, data: dict, config: dict, plan: dict, semanas_hoy: list, n_actual, pausa: bool):
    """Hoy sugiere «Retomar desde la semana X» si hay plan en curso y pasaron ≥ 14 días sin correr (Garmin o a mano; si nunca,
    desde el inicio del plan). X = la última semana con todas sus sesiones hechas (tope: la actual − 1; si no hay, 1).
    {"semana", "dias", "accion": "retomar"|"repetir", "ultima"} o None (sin plan, en pausa, enfermedad/lesión, plan terminado)."""
    if config.get("sin_plan") or pausa or n_actual is None or plan_terminado(hoy, config, plan):
        return None
    for e in config.get("eventos") or []:
        if e["tipo"] in ("enfermedad", "lesion") and date.fromisoformat(str(e["desde"])) <= hoy <= date.fromisoformat(str(e.get("hasta") or e["desde"])):
            return None
    dias_corridos = [mt_comun.day_of(a) for a in historial_corridas(data, config) + [a for a in data["activities"] if mt_comun.classify(a, config) == "run"]]
    ultima = max((d for d in dias_corridos if d <= hoy), default=None)
    desde = ultima or date.fromisoformat(config["plan_start"])
    dias = (hoy - desde).days
    if dias < DIAS_SIN_CORRER:
        return None
    completas = [s["n"] for s in semanas_hoy if s["estado"] == "pasada" and s.get("n") and s.get("plan")
                 and s["plan"]["total"] and s["plan"]["hechas"] == s["plan"]["total"] and s["n"] <= n_actual - 1]
    x = max(completas, default=1)
    return {"semana": x, "dias": dias, "accion": "repetir" if n_actual == 1 else "retomar", "ultima": ultima.isoformat() if ultima else None}
