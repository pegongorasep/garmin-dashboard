"""Funciones puras del dashboard: zonas, carga, semáforo y plan. Sin I/O ni reloj.

Convenciones: `day` y `week_start` son objetos date; las fechas de Garmin
(`calendarDate`, `startTimeLocal`) ya vienen en hora local de Mérida.
Semáforo: "verde" | "amarillo" | "rojo" | "sin_datos".
"""
import re
import unicodedata
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
    """Si ayer fue día de pierna (y Garmin registró una actividad) y hoy toca la Larga o la calidad, avisa."""
    ayer = day - timedelta(days=1)
    if ayer.weekday() not in config.get("dias_pierna", []) or sesion.get("tipo") not in ("larga", "calidad"):
        return None
    ids = {c["id"] for c in config.get("categorias", [])}
    if not any(classify(a, config) in ids for a in activities if day_of(a) == ayer):   # solo lo que Garmin registró
        return None
    resto = "la Larga" if sesion["tipo"] == "larga" else "la calidad"
    return f"Ayer pierna: hoy mejor la Z2 y deja {resto} para mañana"


def today_card(day: date, light: dict, status: list, activities: list, config: dict) -> dict:
    """Qué mostrar hoy. light = resultado de traffic_light; status = assign_sessions."""
    hoy = [a for a in activities if day_of(a) == day]
    cats = {c["id"]: c for c in config.get("categorias", [])}
    hechas = [classify(a, config) for a in hoy]
    hay_run = "run" in hechas
    # Solo una actividad intensa que Garmin ya registró hoy ocupa el día; nunca se adivina por el día de la semana.
    otra = next((i for i in hechas if i in cats and cats[i]["intensa"]), None)
    aviso = "Repetir la semana" if light.get("repetir_semana") else None
    base = {"version": None, "sesion_id": None, "aviso": aviso, "proxima_id": None}
    manana = (_elegir_pendiente(day + timedelta(days=1), status)[0] or {}).get("id") if status else None
    if otra:
        nombre = cats[otra]["nombre"]
        return {"tipo": "otra", "categoria": nombre, "texto": f"Hoy: {nombre} ✓", **{**base, "proxima_id": manana}}
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


def _min_z3_planeados(pasos: list) -> int:
    return sum(p["times"] * _min_z3_planeados(p["steps"]) if p["kind"] == "repeat"
               else p["minutes"] if p["zone"] in ("Z3", "Z4", "Z5") else 0 for p in pasos)


def run_check(activity: dict, session, config=None) -> dict:
    """¿Lo hice bien?: minutos sobre el techo de Z2 (Z3+Z4+Z5) vs la tolerancia."""
    zm = zone_minutes(activity)
    sobre = round(zm["Z3"] + zm["Z4"] + zm["Z5"], 1)
    tolerancia = (config or {}).get("ceiling_tolerance_min", 2)
    if session and _tiene_opcionales(session.get("steps", [])):
        tolerancia += 2
    if (session or {}).get("tipo") == "variada":   # su Z3 corto es parte del plan
        tolerancia += _min_z3_planeados(session.get("steps", []))
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


def promedio(valores: list):
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
    pct_a, pct_b = (promedio([r["pct_trote"] for r in g]) for g in (ahora, antes))
    texto = f"Trotas {pct_a:.0f} % del tiempo (antes {pct_b:.0f} %)"
    rit_a, rit_b = (promedio([r["ritmo_trote_s"] for r in g]) for g in (ahora, antes))
    if rit_a and rit_b:
        texto += f" · ritmo trotando {_mmss(rit_b)} → {_mmss(rit_a)} /km"
    return texto


def _grupo_mejora(filas: list, ini: date, fin: date, semanas: int):
    """Corridas y minutos por semana y % trote promedio de las corridas con ini <= fecha < fin; None si no hay corridas."""
    g = [f for f in filas if ini <= date.fromisoformat(f["fecha"]) < fin]
    if not g:
        return None
    return {"corridas": len(g) / semanas, "minutos": sum(f["minutos"] for f in g) / semanas,
            "pct_trote": promedio([f.get("pct_trote") for f in g]),
            "ritmo_z2": promedio([f.get("ritmo_z2_s") for f in g])}


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
    if _NOMBRE_CARRERA.search(_sin_acentos(activity.get("activityName") or "")):
        return True
    return activity["startTimeLocal"][:10] in config.get("carreras", [])


def ritmos_por_km(puntos: list) -> list:
    """Segundos de cada kilómetro completo a partir de puntos [(metros acumulados, segundos acumulados)] (interpola)."""
    pts = [(d, s) for d, s in puntos if d is not None and s is not None]
    if len(pts) < 2:
        return []

    def tiempo_en(metros):
        for (d0, s0), (d1, s1) in zip(pts, pts[1:]):
            if d0 <= metros <= d1:
                return s0 if d1 == d0 else s0 + (s1 - s0) * (metros - d0) / (d1 - d0)
        return None

    out, k = [], 1
    while k * 1000 <= pts[-1][0] + 1e-6:
        a, b = tiempo_en((k - 1) * 1000), tiempo_en(k * 1000)
        if a is None or b is None:
            break
        out.append(round(b - a))
        k += 1
    return out


def stats_carrera(activity: dict, details: dict, config: dict) -> dict:
    """Números de una carrera, sin nombre, ID ni GPS. `km` (ritmo de cada km, s) solo si Garmin dio los datos."""
    km = (activity.get("distance") or 0) / 1000
    seg = activity.get("duration") or 0
    zm = zone_minutes(activity)
    det = details.get(str(activity.get("activityId"))) or {}
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
            out.append(marca(clave, nombre, a, a[f"fastestSplit_{metros}"], metros))
    largas = [a for a in historial if a.get("distance")]
    if largas:
        a = max(largas, key=lambda x: (x["distance"], x["startTimeLocal"]))
        out.append(marca("larga", "Corrida más larga", a, a["duration"], a["distance"]))
    return out


def _medicion(x: dict) -> dict:
    """Una medición InBody para publicar (lista blanca: sin nota ni hora); masa grasa calculada si falta."""
    grasa = x.get("masa_grasa_kg")
    out = {"fecha": x["fecha"], "peso_kg": x["peso_kg"], "mme_kg": x["mme_kg"], "pgc": x["pgc"],
           "masa_grasa_kg": grasa if grasa is not None else round(x["peso_kg"] * x["pgc"] / 100, 1)}
    for k in ("puntuacion", "grasa_visceral"):
        if x.get(k) is not None:
            out[k] = x[k]
    return out


def pos_escala(valor: float, escala: list) -> float:
    """Dónde cae `valor` en una escala de la hoja InBody, de 0 a 1. Los ticks ocupan el mismo ancho (la escala de
    grasa no es lineal) y dentro de cada tramo se interpola; fuera de la escala se recorta a los extremos."""
    n = len(escala) - 1
    if valor <= escala[0]:
        return 0.0
    if valor >= escala[-1]:
        return 1.0
    i = max(k for k in range(n) if escala[k] <= valor)
    return round((i + (valor - escala[i]) / (escala[i + 1] - escala[i])) / n, 4)


def zona_rango(valor: float, normal: list) -> str:
    """"bajo", "normal" o "alto" según el rango normal [min, max] (los bordes cuentan como normal)."""
    return "bajo" if valor < normal[0] else "alto" if valor > normal[1] else "normal"


def _barra_inbody(id_: str, nombre: str, unidad: str, d: dict, valor_pos: float, valor_txt: float) -> dict:
    out = {"id": id_, "nombre": nombre, "unidad": unidad, "valor": valor_txt, "escala": d["escala"], "normal": d["normal"],
           "normal_pos": [pos_escala(d["normal"][0], d["escala"]), pos_escala(d["normal"][1], d["escala"])],
           "pos": pos_escala(valor_pos, d["escala"]), "zona": zona_rango(valor_pos, d["normal"])}
    if d.get("pct") is not None:
        out["pct"] = d["pct"]
    if d.get("pct_estimado"):
        out["estimado"] = True
    return out


def hoja_inbody(med: dict) -> dict:
    """Lo que pinta la hoja InBody de una medición completa (todo precalculado): análisis músculo-grasa,
    obesidad, control de peso, investigación, composición y segmental. Cada parte se omite si la hoja no la trae."""
    out = {"fecha": med["fecha"]}
    mg = med.get("musculo_grasa")
    if mg:
        filas = [("peso", "Peso", "kg"), ("mme", "MME", "kg"), ("masa_grasa", "Masa grasa", "kg")]
        out["musculo_grasa"] = [_barra_inbody(i, n, u, mg[i], mg[i]["pct"], mg[i]["valor"]) for i, n, u in filas if i in mg]
    ob = med.get("obesidad")
    if ob:
        out["obesidad"] = [_barra_inbody(i, n, u, ob[i], ob[i]["valor"], ob[i]["valor"])
                           for i, n, u in (("imc", "IMC", "kg/m²"), ("pgc", "PGC", "%")) if i in ob]
    rangos = []
    for grupo, clave, filas in (("Parámetros de investigación", "investigacion",
                                 (("tmb_kcal", "TMB", "kcal"), ("cintura_cadera", "Relación cintura-cadera", ""),
                                  ("grado_obesidad_pct", "Grado de obesidad", "%"))),
                                ("Composición corporal", "composicion",
                                 (("agua_l", "Agua corporal", "L"), ("proteinas_kg", "Proteínas", "kg"),
                                  ("minerales_kg", "Minerales", "kg"), ("masa_grasa_kg", "Masa grasa", "kg"),
                                  ("peso_kg", "Peso", "kg")))):
        for k, nombre, unidad in filas:
            v = (med.get(clave) or {}).get(k)
            if v:
                rangos.append({"grupo": grupo, "nombre": nombre, "unidad": unidad, "valor": v[0], "min": v[1], "max": v[2],
                               "zona": zona_rango(v[0], [v[1], v[2]])})
    if rangos:
        out["rangos"] = rangos
    for k in ("control_peso", "investigacion", "composicion", "segmental_magra", "segmental_grasa"):
        if med.get(k):
            out["composicion_corporal" if k == "composicion" else k] = med[k]
    return out


def composicion(inbody):
    """Composición corporal: mediciones por fecha, prime, última con deltas y meta de superar el prime, más lo de la
    hoja InBody (barras, historial, puntuación, visceral y secciones extra). None sin datos."""
    if not inbody or not inbody.get("mediciones"):
        return None
    crudas = sorted(inbody["mediciones"], key=lambda x: x["fecha"])
    meds = sorted((_medicion(x) for x in inbody["mediciones"]), key=lambda x: x["fecha"])
    prime = next((x for x in meds if x["fecha"] == inbody.get("prime")), None) or min(meds, key=lambda x: x["pgc"])
    ultima, previa = meds[-1], (meds[-2] if len(meds) > 1 else None)
    delta = lambda k: None if previa is None else round(ultima[k] - previa[k], 1)  # noqa: E731
    rango = next((x.get("grasa_visceral_rango") for x in reversed(crudas) if x.get("grasa_visceral_rango")), [1, 9])
    out = {"mediciones": meds,
           "prime": {k: prime[k] for k in ("fecha", "pgc", "mme_kg", "peso_kg", "masa_grasa_kg")},
           "ultima": {**ultima, "delta_pgc": delta("pgc"), "delta_mme": delta("mme_kg"), "delta_peso": delta("peso_kg")},
           "meta": {"faltan_pgc": max(0.0, round(ultima["pgc"] - prime["pgc"], 1)),
                    "mme_ok": ultima["mme_kg"] >= prime["mme_kg"],
                    "faltan_mme": max(0.0, round(prime["mme_kg"] - ultima["mme_kg"], 1))},
           "visceral_rango": rango,
           "historial": [{"fecha": x["fecha"], "peso_kg": x["peso_kg"], "mme_kg": x["mme_kg"], "pgc": x["pgc"],
                          "es_prime": x["fecha"] == prime["fecha"]} for x in meds]}
    puntos = [x for x in meds if x.get("puntuacion") is not None]
    if puntos:
        out["puntuacion"] = [{"fecha": x["fecha"], "puntos": x["puntuacion"],
                              "delta": None if i == 0 else x["puntuacion"] - puntos[i - 1]["puntuacion"]}
                             for i, x in enumerate(puntos)]
    visc = next((x for x in reversed(meds) if x.get("grasa_visceral") is not None), None)
    if visc:
        out["visceral"] = {"fecha": visc["fecha"], "valor": visc["grasa_visceral"], "rango": rango,
                           "zona": zona_rango(visc["grasa_visceral"], rango)}
    hoja = next((x for x in reversed(crudas) if x.get("musculo_grasa")), None)
    if hoja:
        out["hoja"] = hoja_inbody(hoja)
    return out


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
    return (f"Tu FC máx medida ({round(estimacion)}) es mayor que la del reloj ({max_hr}). "
            "Súbela en Garmin Connect y el dashboard la tomará sola.")
