"""Funciones puras del dashboard: zonas, carga, semáforo y plan. Sin I/O ni reloj.

Convenciones: `day` y `week_start` son objetos date; las fechas de Garmin
(`calendarDate`, `startTimeLocal`) ya vienen en hora local de Mérida.
Semáforo: "verde" | "amarillo" | "rojo" | "sin_datos".
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


def classify(activity: dict, config: dict):
    """"run", el `id` de la categoría de actividad (config["categorias"]) o None si no se muestra."""
    tipo = activity["activityType"]["typeKey"]
    if tipo in config["run_types"]:
        return "run"
    for c in config.get("categorias", []):
        if tipo in c["tipos"]:
            return c["id"]
    return None


def categorias_intensas(config: dict) -> list:
    return [c for c in config.get("categorias", []) if c.get("intensa")]


def nombre_intensa(config: dict):
    """Nombre de la categoría intensa si hay una sola; None si hay varias o ninguna."""
    ints = categorias_intensas(config)
    return ints[0]["nombre"] if len(ints) == 1 else None


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
    """Carga de la semana: {<id de cada categoría>, run, total, sin_rpe}."""
    fin = week_start + timedelta(days=7)
    ids = [c["id"] for c in config.get("categorias", [])]
    out = {**dict.fromkeys(ids, 0.0), "run": 0.0, "sin_rpe": 0}
    for a in activities:
        tipo = classify(a, config)
        if tipo is None or not (week_start <= day_of(a) < fin):
            continue
        carga = session_load(a, details)
        if carga is None:
            out["sin_rpe"] += 1
        else:
            out[tipo] += carga
    out["total"] = sum(out[k] for k in (*ids, "run"))
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
    intensas = {c["id"] for c in categorias_intensas(config)}
    nombre = nombre_intensa(config)
    sesion = nombre or "sesión intensa"
    cf = [a for a in activities if classify(a, config) in intensas and day_of(a) == ayer]
    if not cf:
        return _senal("ok", None, config["rpe_heavy"], f"sin {sesion} ayer")
    rpes = [r for a in cf if (r := (details.get(str(a["activityId"])) or {}).get("rpe")) is not None]
    if not rpes:
        return _senal("sin_dato", None, config["rpe_heavy"], f"{nombre or 'Sesión intensa'} de ayer sin RPE")
    v = max(rpes)
    texto = f"RPE de {sesion} de ayer {v:g}, pesado desde {config['rpe_heavy']}"
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


MOTIVOS = {"hrv": "HRV baja", "rhr": "FC en reposo alta", "sueno": "Dormiste poco"}


def motivo(sigs: dict, config=None):
    """Por qué la sesión va suave o en descanso: textos de las señales `fuera`, unidos con ' · '; None si no hay."""
    nombre = nombre_intensa(config or {})
    motivos = {**MOTIVOS, "rpe": f"{nombre} pesado ayer" if nombre else "Sesión intensa pesada ayer"}
    textos = [motivos[k] for k in ("hrv", "rhr", "sueno", "rpe") if sigs[k]["estado"] == "fuera"]
    if sigs["hrv"].get("hrv_baja") and MOTIVOS["hrv"] not in textos:
        textos.insert(0, MOTIVOS["hrv"])
    return " · ".join(textos) or None


def week_index(day: date, plan_start: date, repetidas=(), total: int = 12):
    """Semana del plan (1–`total`) que toca en `day`, o None si está fuera.

    `repetidas`: números de semana del plan que se repitieron (una semana puede
    aparecer más de una vez). Cada repetición empuja el resto una semana.
    """
    secuencia = []
    for n in range(1, total + 1):
        secuencia += [n] * (1 + list(repetidas).count(n))
    i = (day - plan_start).days // 7
    return secuencia[i] if 0 <= i < len(secuencia) else None


def es_fin_de_semana(fecha) -> bool:
    return date.fromisoformat(fecha).weekday() >= 5


def _ref_minutos(sesion: dict, luz) -> int:
    """Minutos de referencia: los de la versión suave si ese día fue amarillo/rojo."""
    return sesion["easy"]["minutes"] if luz in ("amarillo", "rojo") else sesion["minutes"]


def _estado_sesion(sesion: dict, corrida, config: dict) -> dict:
    base = {"id": sesion["id"], "name": sesion["name"], "tipo": sesion.get("tipo")}
    if corrida is None:
        return {**base, "estado": "pendiente", "ajustada": False, "fecha": None, "minutos": None}
    suave = corrida.get("luz") in ("amarillo", "rojo")
    hecha = corrida["minutos"] + 0.5 >= config["done_ratio"] * _ref_minutos(sesion, corrida.get("luz"))
    return {**base, "estado": "hecha" if hecha else "incompleta", "ajustada": hecha and suave,
            "fecha": corrida["fecha"], "minutos": corrida["minutos"]}


def assign_sessions(week: dict, runs: list, config: dict) -> list:
    """Asigna las corridas de la semana a sus sesiones (sin mirar nombres).

    runs: [{"fecha", "minutos", "luz"}] en orden cronológico. Una corrida en sáb/dom con
    minutos + 0.5 ≥ done_ratio × larga → Larga (la más larga si hay varias). Las demás, en
    orden, llenan las Z2; las sobrantes son "extra" y no se asignan. `luz` "sin_datos" cuenta
    como verde. Devuelve un dict por sesión, en el orden de la semana.
    """
    sesiones = week["sessions"]
    larga = next((s for s in sesiones if s.get("tipo") == "larga"), None)
    calidad = next((s for s in sesiones if s.get("tipo") == "calidad"), None)
    elegida = None
    if larga:
        candidatas = [r for r in runs if es_fin_de_semana(r["fecha"])
                      and r["minutos"] + 0.5 >= config["done_ratio"] * larga["minutes"]]
        elegida = max(candidatas, key=lambda r: r["minutos"], default=None)
    resto = [r for r in runs if r is not elegida]
    # La calidad es la primera corrida (no Larga) con >= 50 % de los minutos objetivo en Z3 o más.
    de_calidad = None
    if calidad:
        meta = (calidad.get("objetivo") or {}).get("minutos", 0)
        de_calidad = next((r for r in resto if sum((r.get("zonas") or {}).get(z, 0) for z in ("Z3", "Z4", "Z5")) >= 0.5 * meta
                           and meta > 0), None)
        if de_calidad:
            resto = [r for r in resto if r is not de_calidad]
    asignadas = {}
    for s in sesiones:
        if s is larga:
            asignadas[s["id"]] = elegida
        elif s is calidad:
            asignadas[s["id"]] = de_calidad
        else:
            asignadas[s["id"]] = resto.pop(0) if resto else None
    return [_estado_sesion(s, asignadas[s["id"]], config) for s in sesiones]


AVISO_LARGA = "La larga va el sábado o domingo"
AVISO_SIN_DATOS = "Sin datos de anoche: decide por cómo te sientes"


def _unir_avisos(*avisos):
    unidos = " · ".join(a for a in avisos if a)
    return unidos or None


def _elegir_pendiente(day: date, status: list):
    """(sesión pendiente, aviso). Sáb/dom: la Larga primero; entre semana: una Z2, y la Larga solo si no hay."""
    pendientes = [s for s in status if s["estado"] == "pendiente"]
    larga = next((s for s in pendientes if s["tipo"] == "larga"), None)
    z2 = next((s for s in pendientes if s["tipo"] != "larga"), None)
    if day.weekday() >= 5:
        return (larga or z2), None
    if z2:
        return z2, None
    return larga, (AVISO_LARGA if larga else None)


def aviso_pierna(day: date, sesion: dict, activities: list, config: dict):
    """Si ayer fue día de pierna (planeado o real) y hoy toca la Larga o la calidad, avisa."""
    ayer = day - timedelta(days=1)
    if ayer.weekday() not in config.get("dias_pierna", []) or sesion.get("tipo") not in ("larga", "calidad"):
        return None
    hubo = ayer.weekday() in config.get("semana_tipica", {}) or any(
        classify(a, config) in {c["id"] for c in config.get("categorias", [])} for a in activities if day_of(a) == ayer)
    if not hubo:
        return None
    resto = "la Larga" if sesion["tipo"] == "larga" else "la calidad"
    return f"Ayer pierna: hoy mejor la Z2 y deja {resto} para mañana"


def today_card(day: date, light: dict, status: list, activities: list, config: dict) -> dict:
    """Qué mostrar hoy. light = resultado de traffic_light; status = assign_sessions."""
    hoy = [a for a in activities if day_of(a) == day]
    cats = {c["id"]: c for c in config.get("categorias", [])}
    hechas = [classify(a, config) for a in hoy]
    hay_run = "run" in hechas
    # Una actividad intensa hecha hoy, o el día típico de una categoría sin corrida, ocupan el día.
    intensa_hoy = next((i for i in hechas if i in cats and cats[i]["intensa"]), None)
    tipica = config.get("semana_tipica", {}).get(day.weekday())
    otra = intensa_hoy or (tipica if tipica and not hay_run else None)
    aviso = "Repetir la semana" if light.get("repetir_semana") else None
    base = {"version": None, "sesion_id": None, "aviso": aviso, "proxima_id": None}
    manana = (_elegir_pendiente(day + timedelta(days=1), status)[0] or {}).get("id") if status else None
    if otra:
        nombre = cats[otra]["nombre"]
        return {"tipo": "otra", "categoria": nombre, "texto": f"Hoy es {nombre}", **{**base, "proxima_id": manana}}
    if hay_run:
        return {"tipo": "hecha_hoy", "texto": "Corrida de hoy hecha", **{**base, "proxima_id": manana}}
    if not status:
        return {"tipo": "sin_plan", "texto": "Hoy no hay semana de plan activa", **base}
    sesion, aviso_larga = _elegir_pendiente(day, status)
    if sesion is None:
        return {"tipo": "completa", "texto": "Semana completa", **base}
    sin_datos = light["color"] == "sin_datos"
    version = "normal" if sin_datos else {"verde": "normal", "amarillo": "suave", "rojo": "descanso"}[light["color"]]
    aviso = _unir_avisos(aviso, aviso_larga, aviso_pierna(day, sesion, activities, config),
                         AVISO_SIN_DATOS if sin_datos else None)
    return {"tipo": "sesion", "texto": f"Siguiente sesión: versión {version}",
            "version": version, "sesion_id": sesion["id"], "aviso": aviso, "proxima_id": None}


# --- trote / caminata ---

def _tramos(activity: dict, details: dict) -> list:
    """Tramos RWD_* de details (con FC) o, si no hay, de splitSummaries de la lista (sin FC)."""
    guardados = (details.get(str(activity["activityId"])) or {}).get("splits")
    if guardados:
        return guardados
    return [{"tipo": t.get("splitType"), "seg": t.get("duration"), "m": t.get("distance"),
             "fc": None, "n": t.get("noOfSplits")} for t in activity.get("splitSummaries") or []]


def _suma_tramos(tramos: list, tipo: str) -> dict:
    ts = [t for t in tramos if t.get("tipo") == tipo]
    seg = sum(t.get("seg") or 0 for t in ts)
    con_fc = [t for t in ts if t.get("fc") is not None and t.get("seg")]
    peso = sum(t["seg"] for t in con_fc)
    return {"seg": seg, "m": sum(t.get("m") or 0 for t in ts), "n": sum(t.get("n") or 0 for t in ts),
            "fc": sum(t["fc"] * t["seg"] for t in con_fc) / peso if peso else None, "hay": bool(ts)}


def run_walk(activity: dict, details: dict):
    """Trote vs caminata de una corrida (RWD_RUN / RWD_WALK); None si no hay tramos."""
    tramos = _tramos(activity, details)
    run, walk = _suma_tramos(tramos, "RWD_RUN"), _suma_tramos(tramos, "RWD_WALK")
    if not (run["hay"] or walk["hay"]):
        return None
    trote, camina = run["seg"] / 60, walk["seg"] / 60
    total = trote + camina
    return {"trote_min": trote, "camina_min": camina,
            "pct_trote": trote / total * 100 if total else None,
            "caminatas": walk["n"],
            "patron_trote_min": trote / run["n"] if run["n"] else None,
            "patron_camina_min": camina / walk["n"] if walk["n"] else None,
            "km_trote": run["m"] / 1000,
            "ritmo_trote_s": run["seg"] / (run["m"] / 1000) if run["m"] else None,
            "fc_trote": run["fc"]}


RW_CLAVES = ["trote_min", "camina_min", "pct_trote", "caminatas", "patron_trote_min",
             "patron_camina_min", "km_trote", "ritmo_trote_s", "fc_trote"]


def _tiene_opcionales(pasos: list) -> bool:
    return any(p.get("optional") or _tiene_opcionales(p.get("steps", [])) for p in pasos)


def run_check(activity: dict, session, config=None) -> dict:
    """¿Lo hice bien?: minutos sobre el techo de Z2 (Z3+Z4+Z5) vs la tolerancia."""
    zm = zone_minutes(activity)
    sobre = round(zm["Z3"] + zm["Z4"] + zm["Z5"], 1)
    tolerancia = (config or {}).get("ceiling_tolerance_min", 2)
    if session and _tiene_opcionales(session.get("steps", [])):
        tolerancia += 2
    out = {"min_sobre_techo": sobre, "tolerancia_min": tolerancia, "techo_ok": sobre <= tolerancia}
    objetivo = (session or {}).get("objetivo")
    if (session or {}).get("tipo") == "calidad" and objetivo:
        out["calidad"] = calidad_check(zm, objetivo, (config or {}).get("done_ratio", 0.7))
    return out


def calidad_check(zm: dict, objetivo: dict, done_ratio: float) -> dict:
    """Sesión de calidad: minutos en la zona objetivo vs objetivo; avisa si pasó mucho por encima de esa zona."""
    zona, meta = objetivo["zona"], objetivo["minutos"]
    en_zona = zm[zona]
    arriba = sum(zm[z] for z in ZONAS[ZONAS.index(zona) + 1:])
    return {"zona": zona, "min_zona": round(en_zona, 1), "objetivo_min": meta,
            "ok": en_zona + 0.05 >= done_ratio * meta, "min_arriba": round(arriba, 1),
            "mucho_arriba": arriba > max(2.0, 0.25 * meta)}


def rolling_mean(valores: list, ventana: int = 7, minimo: int = 3) -> list:
    """Media móvil de los valores no nulos de los últimos `ventana` puntos; None si hay menos de `minimo`."""
    out = []
    for i in range(len(valores)):
        vs = [v for v in valores[max(0, i - ventana + 1):i + 1] if v is not None]
        out.append(sum(vs) / len(vs) if len(vs) >= minimo else None)
    return out


def run_rows(activities: list, details: dict, config: dict) -> list:
    """Una fila por corrida: fecha, minutos, km, FC promedio, % en Z1–Z2, caminadora y trote/caminata."""
    filas = []
    for a in sorted(activities, key=lambda a: a["startTimeLocal"]):
        if classify(a, config) != "run":
            continue
        zm = zone_minutes(a)
        total = sum(zm.values())
        rw = run_walk(a, details) or dict.fromkeys(RW_CLAVES)
        filas.append({"fecha": day_of(a).isoformat(), "minutos": a["duration"] / 60,
                      "km": (a.get("distance") or 0) / 1000, "fc_prom": a.get("averageHR"),
                      "pct_z1z2": (zm["Z1"] + zm["Z2"]) / total * 100 if total else None,
                      "caminadora": a["activityType"]["typeKey"] == "treadmill_running", **rw})
    return filas


def _promedio(valores: list):
    vs = [v for v in valores if v is not None]
    return sum(vs) / len(vs) if vs else None


def _mmss(seg: float) -> str:
    seg = round(seg)
    return f"{seg // 60}:{seg % 60:02d}"


def progress_summary(rows: list, hoy: date, semanas: int) -> str:
    """Compara las corridas al aire libre de las últimas `semanas` contra las `semanas` anteriores."""
    corte = hoy - timedelta(weeks=semanas)
    antes_corte = corte - timedelta(weeks=semanas)
    aire = [r for r in rows if not r["caminadora"] and r.get("pct_trote") is not None]
    ahora = [r for r in aire if corte < date.fromisoformat(r["fecha"]) <= hoy]
    antes = [r for r in aire if antes_corte < date.fromisoformat(r["fecha"]) <= corte]
    if not ahora or not antes:
        return "Aún no hay corridas suficientes para comparar"
    pct_a, pct_b = (_promedio([r["pct_trote"] for r in g]) for g in (ahora, antes))
    texto = f"Trotas {pct_a:.0f} % del tiempo (antes {pct_b:.0f} %)"
    rit_a, rit_b = (_promedio([r["ritmo_trote_s"] for r in g]) for g in (ahora, antes))
    if rit_a and rit_b:
        texto += f" · ritmo trotando {_mmss(rit_b)} → {_mmss(rit_a)} /km"
    return texto


def _grupo_mejora(filas: list, ini: date, fin: date, semanas: int):
    """Corridas y minutos por semana y % trote promedio de las corridas con ini <= fecha < fin; None si no hay corridas."""
    g = [f for f in filas if ini <= date.fromisoformat(f["fecha"]) < fin]
    if not g:
        return None
    return {"corridas": len(g) / semanas, "minutos": sum(f["minutos"] for f in g) / semanas,
            "pct_trote": _promedio([f.get("pct_trote") for f in g]),
            "ritmo_z2": _promedio([f.get("ritmo_z2_s") for f in g])}


def mejora_frase(filas: list, hoy: date, modo: str = "trote") -> str:
    """Compara las últimas 4 semanas calendario completas contra las 4 anteriores (filas = run_rows).

    modo "trote": agrega el % trote. modo "ritmo" (sin caminatas): agrega el cambio de ritmo en Z2
    (usa `ritmo_z2_s` de cada fila: ritmo de las corridas cuya FC promedio cayó en Z2)."""
    lunes = hoy - timedelta(days=hoy.weekday())
    ahora = _grupo_mejora(filas, lunes - timedelta(weeks=4), lunes, 4)
    antes = _grupo_mejora(filas, lunes - timedelta(weeks=8), lunes - timedelta(weeks=4), 4)
    if not ahora and not antes:
        return "Aún no hay corridas suficientes para comparar."
    if not ahora:
        return f"Últimas 4 semanas: sin corridas (antes {antes['corridas']:.1f} y {antes['minutos']:.0f} min por semana)."
    texto = f"Últimas 4 semanas: {ahora['corridas']:.1f} corridas y {ahora['minutos']:.0f} min por semana"
    if antes:
        texto += f" (antes {antes['corridas']:.1f} y {antes['minutos']:.0f})"
    if modo == "ritmo":
        if ahora["ritmo_z2"] and antes and antes["ritmo_z2"]:
            dif = antes["ritmo_z2"] - ahora["ritmo_z2"]       # positivo = más rápido ahora
            texto += ("; a la misma FC vas al mismo ritmo que hace 4 semanas" if abs(dif) < 3 else
                      f"; a la misma FC vas {_mmss(abs(dif))}/km {'más rápido' if dif > 0 else 'más lento'} que hace 4 semanas")
    elif ahora["pct_trote"] is not None:
        texto += f"; trote {ahora['pct_trote']:.0f} %"
        if antes and antes["pct_trote"] is not None:
            texto += f" (antes {antes['pct_trote']:.0f} %)"
    return texto + "."


def _medicion(x: dict) -> dict:
    """Una medición InBody para publicar (lista blanca: sin nota ni hora); masa grasa calculada si falta."""
    grasa = x.get("masa_grasa_kg")
    out = {"fecha": x["fecha"], "peso_kg": x["peso_kg"], "mme_kg": x["mme_kg"], "pgc": x["pgc"],
           "masa_grasa_kg": grasa if grasa is not None else round(x["peso_kg"] * x["pgc"] / 100, 1)}
    for k in ("puntuacion", "grasa_visceral"):
        if x.get(k) is not None:
            out[k] = x[k]
    return out


def composicion(inbody):
    """Composición corporal: mediciones por fecha, prime, última con deltas y meta de superar el prime. None sin datos."""
    if not inbody or not inbody.get("mediciones"):
        return None
    meds = sorted((_medicion(x) for x in inbody["mediciones"]), key=lambda x: x["fecha"])
    prime = next((x for x in meds if x["fecha"] == inbody.get("prime")), None) or min(meds, key=lambda x: x["pgc"])
    ultima, previa = meds[-1], (meds[-2] if len(meds) > 1 else None)
    delta = lambda k: None if previa is None else round(ultima[k] - previa[k], 1)  # noqa: E731
    rango = next((x.get("grasa_visceral_rango") for x in reversed(inbody["mediciones"]) if x.get("grasa_visceral_rango")), [1, 9])
    return {"mediciones": meds,
            "prime": {k: prime[k] for k in ("fecha", "pgc", "mme_kg", "peso_kg", "masa_grasa_kg")},
            "ultima": {**ultima, "delta_pgc": delta("pgc"), "delta_mme": delta("mme_kg"), "delta_peso": delta("peso_kg")},
            "meta": {"faltan_pgc": max(0.0, round(ultima["pgc"] - prime["pgc"], 1)),
                     "mme_ok": ultima["mme_kg"] >= prime["mme_kg"],
                     "faltan_mme": max(0.0, round(prime["mme_kg"] - ultima["mme_kg"], 1))},
            "visceral_rango": rango}


def max_hr_progress(activities: list, config: dict) -> dict:
    """Progreso de la medición de FC máx con correa en las sesiones intensas (desde `fc_max_correa_desde`)."""
    desde = config.get("fc_max_correa_desde")
    if not desde:
        return {"sesiones": [], "pico": None, "estimacion": None, "revisar": False,
                "semanas_medidas": 0, "listo": False, "configurada": False}
    desde = date.fromisoformat(desde)
    intensas = {c["id"] for c in categorias_intensas(config)}
    ses = [a for a in activities if classify(a, config) in intensas
           and day_of(a) >= desde and a.get("maxHR")]
    sesiones = sorted(({"fecha": day_of(a).isoformat(), "max_hr": a["maxHR"]} for a in ses),
                      key=lambda s: s["fecha"])
    pico = max((s["max_hr"] for s in sesiones), default=None)
    estimacion = max(pico + 3, config["max_hr_floor"]) if pico is not None else None
    semanas = {day_of(a) - timedelta(days=day_of(a).weekday()) for a in ses}
    return {"sesiones": sesiones, "pico": pico, "estimacion": estimacion,
            "revisar": estimacion is not None and estimacion > config["max_hr_review_above"],
            "semanas_medidas": len(semanas), "listo": len(semanas) >= 2, "configurada": True}


def watch_max_hr(hr_zones):
    """FC máx que usa el reloj (perfil DEFAULT); None si Garmin no la da."""
    perfiles = hr_zones if isinstance(hr_zones, list) else [hr_zones or {}]
    perfil = next((p for p in perfiles if p.get("sport") == "DEFAULT"), perfiles[0] if perfiles else {})
    return perfil.get("maxHeartRateUsed")


def max_hr_above_watch(estimacion, max_hr):
    """Aviso si la FC máx medida supera la que se usa; None si no."""
    if estimacion is None or estimacion <= max_hr:
        return None
    return (f"Tu FC máx medida ({estimacion}) es mayor que la del reloj ({max_hr}). "
            "Súbela en Garmin Connect y el dashboard la tomará sola.")
