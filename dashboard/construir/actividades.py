"""Corridas y actividades: detalle, curva de FC, actividades del día, historial y carreras."""
from dashboard import plan_i18n
from dashboard.metricas import carga, carreras as mt_carreras, comun as mt_comun, corridas as mt_corridas, semana as mt_semana, zonas as mt_zonas
from dashboard.i18n import tt
from datetime import date, timedelta
from dashboard.construir.comun import light_on, monday, r1, r2, rw_json, week_assignment


def last_run(data: dict, config: dict, plan: dict):
    """La corrida más reciente con su sesión del plan (de SU semana), '¿lo hice bien?' y trote/caminata."""
    runs = sorted((a for a in data["activities"] if mt_comun.classify(a, config) == "run"),
                  key=lambda a: a["startTimeLocal"])
    if not runs:
        return None
    a = runs[-1]
    dia = mt_comun.day_of(a)
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
    return {"esfuerzo": carga.esfuerzo_de(a, details, config), "rpe": carga.rpe_de(a, details)}


def datos_serie(a: dict, data: dict, config: dict) -> dict:
    """Lo que sale de la serie de FC de una corrida: ritmo a la FC de referencia y deriva cardiaca."""
    fila = next(iter(mt_corridas.run_rows([a], data["details"], config)), None)
    if fila is None:
        return {"ritmo_ref_s": None, "deriva_pct": None, "deriva_ok": None}
    return {"ritmo_ref_s": None if fila["ritmo_ref_s"] is None else round(fila["ritmo_ref_s"]),
            "deriva_pct": fila["deriva_pct"], "deriva_ok": fila["deriva_ok"]}


def corrida_json(a: dict, plan_ses, data: dict, config: dict) -> dict:
    """Lo común de una corrida: minutos, km, caminadora, '¿lo hice bien?' y trote/caminata."""
    return {"minutos": r1(a["duration"] / 60), "km": r2((a.get("distance") or 0) / 1000),
            "caminadora": a["activityType"]["typeKey"] == "treadmill_running", "carrera": mt_carreras.es_carrera(a, config),
            **mt_semana.run_check(a, plan_ses, config, mt_zonas.zona_minutos(a, data["details"], mt_zonas.zonas_de(config)),
                          light_on(mt_comun.day_of(a), data, config)["color"] in ("amarillo", "rojo")), "trote": rw_json(mt_corridas.run_walk(a, data["details"])),
            **registro_esfuerzo(a, data["details"], config), **datos_serie(a, data, config)}


def corrida_plana(a: dict, plan_ses, data: dict, config: dict) -> dict:
    """corrida_json con el trote/caminata aplanado (lo que pinta el frontend en cada fila de corrida)."""
    c = corrida_json(a, plan_ses, data, config)
    tr = c.pop("trote") or dict.fromkeys(mt_corridas.RW_CLAVES)
    return {**c, "pct_trote": tr["pct_trote"], "ritmo_trote_s": tr["ritmo_trote_s"], "fc_trote": tr["fc_trote"],
            "caminatas": tr["caminatas"], "patron_trote_min": tr["patron_trote_min"],
            "patron_camina_min": tr["patron_camina_min"], "trote_min": tr["trote_min"],
            "camina_min": tr["camina_min"]}


def corrida_de_sesion(e: dict, semana: dict, data: dict, config: dict):
    """Corrida asignada a la sesión `e` de estado_sesiones, en plano; None si no tiene (pendiente / no hecha)."""
    if e["fecha"] is None:
        return None
    a = next(a for a in data["activities"] if mt_comun.classify(a, config) == "run"
             and mt_comun.day_of(a).isoformat() == e["fecha"] and a["duration"] / 60 == e["minutos"])
    plan_ses = next(s for s in semana["sessions"] if s["id"] == e["id"])
    return corrida_plana(a, plan_ses, data, config)


def otras_del_dia(d: date, data: dict, config: dict) -> list:
    """Actividades no-corrida del día, UNA ENTRADA POR SESIÓN (en orden de hora; `data["activities"]` ya trae las
    encadenadas unidas): categoría, esfuerzo, RPE y minutos. Una sesión unida lleva `partes` ([{nombre, minutos}])."""
    iconos = {c["id"]: c.get("icono", "punto") for c in config["categorias"]}
    out = []
    for a in sorted(data["activities"], key=lambda a: a["startTimeLocal"]):
        c = mt_comun.classify(a, config)
        if c not in iconos or mt_comun.day_of(a) != d:
            continue
        e = {"cat": c, "icono": iconos[c], "esfuerzo": carga.esfuerzo_de(a, data["details"], config),
             "rpe": carga.rpe_de(a, data["details"]), "minutos": r1(a["duration"] / 60)}
        if a.get("partes"):
            e["partes"] = [{"nombre": p["nombre"], "minutos": p["minutos"]} for p in a["partes"]]
        out.append(e)
    return out


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
    det = details.get(str(mt_comun.id_de(a))) or {}
    corrida = mt_comun.classify(a, config) == "run"
    km = (a.get("distance") or 0) / 1000
    seg = a.get("movingDuration") or a["duration"]
    zm = mt_zonas.zone_minutes(a)
    total = sum(zm.values())
    bajo, limbo, alto = (sum(zm[z] for z in zs) for zs in (("Z1", "Z2"), ("Z3",), ("Z4", "Z5")))
    zonas = ({"minutos": {z: r1(v) for z, v in zm.items()}, "bajo": r1(bajo / total * 100), "limbo": r1(limbo / total * 100),
              "alto": r1(alto / total * 100)} if total > 0 else None)
    etiqueta = str(a.get("trainingEffectLabel") or "").lower()
    ae, an = a.get("aerobicTrainingEffect"), a.get("anaerobicTrainingEffect")
    ritmos = det.get("ritmos_km") if corrida else None
    # a mano: el ritmo (por km, o por 100 m en natación) sale de la distancia y el tiempo que la persona anotó, sea cual sea el tipo
    mano = bool(a.get("manual")) and km >= 0.05 and seg
    nado = mano and (a.get("activityType") or {}).get("typeKey") == "lap_swimming"
    ritmo_s = (round(seg / (km * 10)) if nado else round(seg / km)) if mano else (round(seg / km) if corrida and km >= 0.1 else None)
    return {"duracion_min": r1(a["duration"] / 60), "km": r2(km) if km >= 0.05 else None,
            "ritmo_s": ritmo_s, "ritmo_unidad": "100 m" if nado else "km",
            "vel_kmh": r1(km / (seg / 3600)) if not corrida and not mano and km >= 0.1 and seg else None,
            "fc_prom": round(a["averageHR"]) if a.get("averageHR") else None, "fc_max": round(a["maxHR"]) if a.get("maxHR") else None,
            "kcal": round(a["calories"]) if a.get("calories") else None,
            "desnivel_m": round(a["elevationGain"]) if a.get("elevationGain") else None,
            "zonas": zonas,
            "te_aerobico": r1(ae) if ae else None, "te_anaerobico": r1(an) if an else None,
            "te_etiqueta": tt(f"motor.te.{etiqueta}") if etiqueta in TE_ETIQUETAS else None,
            "cadencia": round(a["averageRunningCadenceInStepsPerMinute"]) if corrida and a.get("averageRunningCadenceInStepsPerMinute") else None,
            "ritmos_km": [round(x) for x in ritmos] if ritmos else None,
            "pulso": mt_zonas.pulso_de(a, details, config),
            "curva_fc": None if a.get("_partes") else curva_fc(det.get("serie"))}


def _trote_corto(a: dict, details: dict):
    """Trote/caminata de una corrida para la fila de actividad: {pct_trote, trote_min, camina_min}; None sin tramos."""
    rw = rw_json(mt_corridas.run_walk(a, details))
    return {k: rw[k] for k in ("pct_trote", "trote_min", "camina_min")} if rw else None


def actividades_del_dia(d: date, acts: list, config: dict, sesiones=None, details=None) -> list:
    """Todo lo que se hizo un día, una fila por actividad: tipo (texto del catálogo), minutos, km, FC prom. y, en
    corridas, la sesión del plan que cumplió. `acts` ya viene con las encadenadas unidas (`mt_corridas.unir_encadenadas`). Nunca nombres, IDs ni GPS."""
    nombres = {"run": (tt("motor.entreno.run"), "correr"), "carrera": (tt("motor.entreno.carrera"), "medalla"),
               **{c["id"]: (c["nombre"], c.get("icono", "punto")) for c in config["categorias"]}}
    out = []
    for a in sorted((x for x in acts if mt_comun.day_of(x) == d and mt_comun.classify(x, config)), key=lambda x: x["startTimeLocal"]):
        c = mt_comun.classify(a, config)
        carrera = c == "run" and mt_carreras.es_carrera(a, config)
        k = ("carrera" if carrera else "run") if c == "run" else c
        e = next((e for e in sesiones or [] if c == "run" and e["fecha"] == d.isoformat()
                  and e["minutos"] == a["duration"] / 60), None)
        km = (a.get("distance") or 0) / 1000
        a_mano = {"manual": True, "id": str(a["id"])} if a.get("manual") else {}   # las de a mano llevan la marca y su id (la liga de editar la pone la web)
        out.append({**a_mano, "cat": c, "nombre": nombres[k][0], "icono": nombres[k][1], "minutos": round(a["duration"] / 60),
                    "km": r2(km) if km >= 0.05 else None, "fc_prom": round(a["averageHR"]) if a.get("averageHR") else None,
                    "carrera": carrera, "sesion": {"nombre": e["name"], "estado": e["estado"]} if e else None,
                    **registro_esfuerzo(a, details or {}, config),
                    "trote": _trote_corto(a, details or {}) if c == "run" else None,
                    "partes": [{"nombre": p["nombre"], "minutos": p["minutos"]} for p in a.get("partes") or []],
                    "detalle": detalle_actividad(a, details or {}, config)})
    return out


def session_names(rows_acts: list, data: dict, config: dict, plan: dict) -> dict:
    """{(fecha, minutos): nombre de la sesión} de todas las corridas que caen en una semana del plan."""
    out, vistas = {}, set()
    for a in rows_acts:
        ini = monday(mt_comun.day_of(a))
        if ini in vistas:
            continue
        vistas.add(ini)
        _, estado = week_assignment(ini, data, config, plan, hasta=ini + timedelta(days=6))
        out.update({(e["fecha"], e["minutos"]): e["name"] for e in estado if e["fecha"]})
    return out


def build_runs(data: dict, config: dict, plan: dict) -> list:
    acts = sorted((a for a in data["activities"] if mt_comun.classify(a, config) == "run"),
                  key=lambda a: a["startTimeLocal"])
    nombres = session_names(acts, data, config, plan)
    filas = mt_corridas.run_rows(acts, data["details"], config)
    # promedio móvil de 4 del ritmo a FC ref, solo entre las corridas que lo tienen
    con = [i for i, f in enumerate(filas) if f["ritmo_ref_s"]]
    prom = dict(zip(con, mt_corridas.rolling_mean([filas[i]["ritmo_ref_s"] for i in con], 4, 2)))
    return [{"fecha": f["fecha"], "sesion": nombres.get((f["fecha"], f["minutos"])), "carrera": f["carrera"],
             "icono": "medalla" if f["carrera"] else "correr",
             "minutos": r1(f["minutos"]), "km": r2(f["km"]), "fc_prom": r1(f["fc_prom"]),
             "pct_z1z2": r1(f["pct_z1z2"]), "caminadora": f["caminadora"],
             "ritmo_ref_s": None if f["ritmo_ref_s"] is None else round(f["ritmo_ref_s"]),
             "ritmo_ref_prom_s": None if prom.get(i) is None else round(prom[i]),
             "deriva_pct": f["deriva_pct"], "deriva_ok": f["deriva_ok"],
             **registro_esfuerzo(a, data["details"], config), **(rw_json(f) or dict.fromkeys(mt_corridas.RW_CLAVES))}
            for i, (a, f) in enumerate(zip(acts, filas))]


def historial_corridas(data: dict, config: dict) -> list:
    """Corridas de toda la cuenta (historial_corridas.json); si aún no existe, las actividades que ya se bajaron."""
    if data.get("historial") is not None:
        return data["historial"]
    return [a for a in data["activities"] if mt_comun.classify(a, config) == "run"]


def build_carreras(hoy: date, data: dict, config: dict) -> list:
    """Carreras (de la más nueva a la más vieja) con sus stats y la comparación con la anterior parecida.
    Las de las actividades recientes traen todo; las más viejas, del historial, solo distancia, tiempo y ritmo."""
    recientes = {a["startTimeLocal"]: a for a in data["activities"] if mt_comun.classify(a, config) == "run"}
    todas = {**{h["startTimeLocal"]: h for h in historial_corridas(data, config)}, **recientes}
    stats = [mt_carreras.stats_carrera(a, data["details"], config) for _, a in sorted(todas.items()) if mt_carreras.es_carrera(a, config)]
    out = []
    for i, s in enumerate(stats):
        dias = (hoy - date.fromisoformat(s["fecha"])).days
        out.append({**s, "icono": "medalla", "comparacion": mt_carreras.comparar_carrera(s, stats[:i]), "hace_dias": dias,
                    "reciente": 0 <= dias <= 7})
    return out[::-1]
