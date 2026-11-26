"""Funciones puras del dashboard: zonas, carga, semáforo y plan. Sin I/O ni reloj.

Convenciones: `day` y `week_start` son objetos date; las fechas de Garmin
(`calendarDate`, `startTimeLocal`) ya vienen en hora local de Mérida.
Semáforo: "verde" | "amarillo" | "rojo" | "sin_datos".
"""
import re
import unicodedata
from datetime import date, datetime, timedelta

import plan_i18n
import tipos
from i18n import tt

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


def _indices_detalle(d: dict) -> dict:
    return {x["key"]: x["metricsIndex"] for x in d.get("metricDescriptors") or []}


def ritmos_km_de_detalle(d: dict) -> list:
    """Segundos de cada kilómetro completo del `/details` de una actividad (no se guarda GPS)."""
    idx = _indices_detalle(d)
    if "sumDistance" not in idx or "sumDuration" not in idx:
        return []
    return ritmos_por_km([(r["metrics"][idx["sumDistance"]], r["metrics"][idx["sumDuration"]])
                          for r in d.get("activityDetailMetrics") or []])


def serie_de_detalle(d: dict, paso: int = 5) -> list:
    """Serie [seg, metros, fc] (enteros) de un `/details`, una muestra cada `paso` segundos. Sin lat/lon ni nada más.
    Si falta tiempo, distancia o FC en los descriptores, devuelve []."""
    idx = _indices_detalle(d)
    if not {"sumDuration", "sumDistance", "directHeartRate"} <= set(idx):
        return []
    out, siguiente = [], 0
    for r in d.get("activityDetailMetrics") or []:
        mt = r["metrics"]
        seg, metros, fc = (mt[idx[k]] for k in ("sumDuration", "sumDistance", "directHeartRate"))
        if seg is None or seg < siguiente:
            continue
        out.append([round(seg), round(metros or 0), None if fc is None else round(fc)])
        siguiente = (int(seg) // paso + 1) * paso
    return out


def id_de(a: dict):
    """Id de una actividad: el `id` opaco del paquete (web) o el `activityId` de Garmin (datos locales)."""
    return a.get("id") or a.get("activityId")


def pulso_de_detalle(detalle: dict):
    """Sensor de pulso de una actividad según el detalle de Garmin: "banda" si hay un sensor de FC externo
    (ANT+ HEART_RATE o BLE), "muñeca" si hay metadatos sin sensor; None si el detalle no trae metadatos.
    Solo el tipo derivado: nunca serie, sku, fabricante ni versión."""
    meta = (detalle or {}).get("metadataDTO")
    if not isinstance(meta, dict) or "sensors" not in meta:
        return None
    for s in meta.get("sensors") or []:
        tipo = str(s.get("antplusDeviceType") or "").upper()
        if tipo == "HEART_RATE" or (str(s.get("sourceType") or "").upper() == "BLUETOOTH_LE" and "HEART" in tipo):
            return "banda"
    return "muñeca"


def pulso_de(activity: dict, details: dict, config: dict) -> str:
    """"banda" o "muñeca" de una actividad: el detectado en su detalle; sin detalle, `config.sensor` (default banda)."""
    p = (details.get(str(id_de(activity))) or {}).get("pulso")
    return p if p in ("banda", "muñeca") else (config.get("sensor") or "banda")


def detalle_vigente(entrada, es_corrida: bool, es_carrera: bool = False, reciente: bool = False) -> bool:
    """¿Se reusa lo ya guardado de una actividad? Sí si ya existe y, en corridas, trae tramos y serie (y en carreras
    el ritmo por km). Sin RPE solo se vuelve a pedir en los últimos 7 días (`reciente`): Pedro puede ponerlo después."""
    if not entrada:
        return False
    if entrada.get("rpe") is None and reciente:
        return False
    if "pulso" not in entrada:      # detalle viejo, sin el sensor de pulso: se vuelve a pedir una vez
        return False
    return (not es_corrida or ("splits" in entrada and "serie" in entrada)) and (not es_carrera or "ritmos_km" in entrada)


def zona_de_fc(fc: float, zonas: list) -> str:
    """Zona de una FC con las zonas del dashboard (piso incluido): debajo del piso de Z1 es Z0; del piso de Z5 para arriba, Z5."""
    zona = "Z0"
    for z, piso, _ in zonas:
        if fc >= piso:
            zona = z
    return zona


def minutos_zona_serie(serie: list, zonas: list, max_hueco: int = 10) -> dict:
    """Minutos en Z0..Z5 de una serie [seg, metros, fc] con las zonas del dashboard. Cada muestra pesa lo que falta
    para la siguiente (máx. `max_hueco` s: una pausa no cuenta) y la última pesa lo mismo que la anterior. Sin FC no cuenta."""
    minutos = dict.fromkeys(["Z0", *ZONAS], 0.0)
    for i, (seg, _, fc) in enumerate(serie):
        if fc is None:
            continue
        if i + 1 < len(serie):
            peso = min(serie[i + 1][0] - seg, max_hueco)
        else:
            peso = min(seg - serie[i - 1][0], max_hueco) if i else 0
        minutos[zona_de_fc(fc, zonas)] += max(peso, 0) / 60
    return minutos


def zona_minutos(activity: dict, details: dict, zonas: list):
    """Minutos en Z0..Z5 de una actividad: de la serie de FC si existe; si no, de las zonas del reloj
    (`hrTimeInZone_*`, con Z0 = duración − suma). None si no hay ni uno ni otro. Fuente del esfuerzo, la carga y el plan vs real."""
    serie = (details.get(str(id_de(activity))) or {}).get("serie")
    if serie:
        return minutos_zona_serie(serie, zonas)
    if activity.get("hrTimeInZone_1") is None:
        return None
    zm = zone_minutes(activity)
    return {"Z0": max(0.0, (activity.get("duration") or 0) / 60 - sum(zm.values())), **zm}


def fc_referencia(zonas: list) -> int:
    """FC de referencia para comparar ritmos: la mitad de Z2."""
    _, piso, techo = zonas[1]
    return round((piso + techo) / 2)


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


# Valor de cada zona para el esfuerzo (1–10): lo que cuesta un minuto en esa zona.
ESFUERZO = {"Z0": 1, "Z1": 2, "Z2": 3, "Z3": 5.5, "Z4": 7.5, "Z5": 9.5}
ORDEN_ZONAS = ["Z0", *ZONAS]


def zonas_de(config: dict) -> list:
    """Zonas del dashboard (las que build deja en config["zonas"]); si no, Karvonen con FC reposo 60 (solo pruebas)."""
    return config.get("zonas") or zones(config["max_hr"], 60, config.get("zone_pcts", [50, 60, 70, 80, 90]))


def esfuerzo(minutos: dict):
    """Esfuerzo 1–10 de una sesión: promedio ponderado de ESFUERZO en la mitad más dura (de Z5 hacia Z0), para que
    los descansos no lo bajen. 1 decimal; None sin minutos."""
    total = sum(minutos.values())
    if total <= 0:
        return None
    mitad = resto = total / 2
    suma = 0.0
    for z in reversed(ORDEN_ZONAS):
        tomo = min(minutos.get(z, 0.0), resto)
        suma += tomo * ESFUERZO[z]
        resto -= tomo
        if resto <= 1e-9:
            break
    return round(suma / mitad, 1)


def esfuerzo_de(activity: dict, details: dict, config: dict):
    """Esfuerzo de una actividad, de su serie de FC o de las zonas del reloj; None si no hay."""
    zm = zona_minutos(activity, details, zonas_de(config))
    return None if zm is None else esfuerzo(zm)


def session_load(activity: dict, details: dict, config: dict):
    """Carga = esfuerzo × minutos de la actividad; None si no hay esfuerzo."""
    e = esfuerzo_de(activity, details, config)
    return None if e is None else e * activity["duration"] / 60


def week_load(activities: list, details: dict, week_start: date, config: dict) -> dict:
    """Carga de la semana: {<id de cada categoría>, run, total}."""
    fin = week_start + timedelta(days=7)
    ids = [c["id"] for c in config.get("categorias", [])]
    out = {**dict.fromkeys(ids, 0.0), "run": 0.0}
    for a in activities:
        tipo = classify(a, config)
        if tipo is None or not (week_start <= day_of(a) < fin):
            continue
        out[tipo] += session_load(a, details, config) or 0.0
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
            "rpe": (details.get(str(id_de(a))) or {}).get("rpe")}


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


def secuencia_semanas(plan_start: date, repetidas=(), total: int = 12, pausas=()) -> list:
    """Semanas del calendario desde `plan_start`: el número de semana del plan que toca en cada una (o None si esa
    semana está en pausa). `repetidas` repite semanas del plan; `pausas` son lunes (AAAA-MM-DD) que no gastan semana
    del plan (viaje sin correr, enfermedad): el plan se reanuda donde iba."""
    secuencia = []
    for n in range(1, total + 1):
        secuencia += [n] * (1 + list(repetidas).count(n))
    for i in sorted({(date.fromisoformat(str(p)) - plan_start).days // 7 for p in pausas}):
        if 0 <= i <= len(secuencia):
            secuencia.insert(i, None)
    return secuencia


def week_index(day: date, plan_start: date, repetidas=(), total: int = 12, pausas=()):
    """Semana del plan (1–`total`) que toca en `day`, o None si está fuera (o en pausa).

    `repetidas`: números de semana del plan que se repitieron (una semana puede
    aparecer más de una vez). Cada repetición empuja el resto una semana. `pausas`: ver `secuencia_semanas`.
    """
    secuencia = secuencia_semanas(plan_start, repetidas, total, pausas)
    i = (day - plan_start).days // 7
    return secuencia[i] if 0 <= i < len(secuencia) else None


def semana_del_plan(day: date, config: dict):
    """`week_index` con lo que dice la config (inicio, semanas repetidas, total y pausas)."""
    return week_index(day, date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []),
                      config.get("plan_semanas", 12), config.get("pausas", []))


def en_pausa(day: date, config: dict) -> bool:
    """Hoy cae en una semana de pausa del plan (viaje sin correr o enfermedad)."""
    inicio = date.fromisoformat(config["plan_start"])
    i = (day - inicio).days // 7
    sec = secuencia_semanas(inicio, config.get("semanas_repetidas", []), config.get("plan_semanas", 12), config.get("pausas", []))
    return 0 <= i < len(sec) and sec[i] is None


def es_fin_de_semana(fecha) -> bool:
    return date.fromisoformat(fecha).weekday() >= 5


def _ref_minutos(sesion: dict, luz) -> int:
    """Minutos de referencia: los de la versión suave si ese día fue amarillo/rojo."""
    return sesion["easy"]["minutes"] if luz in ("amarillo", "rojo") else sesion["minutes"]


def _estado_sesion(sesion: dict, corrida, config: dict) -> dict:
    base = {"id": sesion["id"], "name": plan_i18n.nombre(sesion["name"]), "tipo": sesion.get("tipo")}
    if corrida is None:
        return {**base, "estado": "pendiente", "ajustada": False, "fecha": None, "minutos": None}
    suave = corrida.get("luz") in ("amarillo", "rojo")
    hecha = corrida["minutos"] + 0.5 >= config["done_ratio"] * _ref_minutos(sesion, corrida.get("luz"))
    return {**base, "estado": "hecha" if hecha else "incompleta", "ajustada": hecha and suave,
            "fecha": corrida["fecha"], "minutos": corrida["minutos"]}


def assign_sessions(week: dict, runs: list, config: dict) -> list:
    """Asigna las corridas de la semana a sus sesiones (sin mirar nombres).

    runs: [{"fecha", "minutos", "luz"}] en orden cronológico. Una corrida en sáb/dom con
    minutos + 0.5 ≥ done_ratio × larga → Larga (la más larga si hay varias); la prueba de la última semana se asigna
    igual pero en cualquier día. Las demás, en
    orden, llenan las Z2; las sobrantes son "extra" y no se asignan. `luz` "sin_datos" cuenta
    como verde. Devuelve un dict por sesión, en el orden de la semana.
    """
    sesiones = week["sessions"]
    larga = next((s for s in sesiones if s.get("tipo") in ("larga", "prueba")), None)   # la prueba ocupa su lugar
    calidad = next((s for s in sesiones if s.get("tipo") == "calidad"), None)
    elegida = None
    if larga:
        candidatas = [r for r in runs if (es_fin_de_semana(r["fecha"]) or larga["tipo"] == "prueba")
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
    return larga, (tt("motor.aviso.larga") if larga else None)


def aviso_pierna(day: date, sesion: dict, activities: list, config: dict):
    """Si ayer fue día de pierna (y Garmin registró una actividad) y hoy toca la Larga o la calidad, avisa."""
    ayer = day - timedelta(days=1)
    if ayer.weekday() not in config.get("dias_pierna", []) or sesion.get("tipo") not in ("larga", "calidad"):
        return None
    ids = {c["id"] for c in config.get("categorias", [])}
    if not any(classify(a, config) in ids for a in activities if day_of(a) == ayer):   # solo lo que Garmin registró
        return None
    resto = tt("motor.aviso.resto_larga") if sesion["tipo"] == "larga" else tt("motor.aviso.resto_calidad")
    return tt("motor.aviso.pierna", resto=resto)


def today_card(day: date, light: dict, status: list, activities: list, config: dict) -> dict:
    """Qué mostrar hoy. light = resultado de traffic_light; status = assign_sessions."""
    hoy = [a for a in activities if day_of(a) == day]
    cats = {c["id"]: c for c in config.get("categorias", [])}
    hechas = [classify(a, config) for a in hoy]
    hay_run = "run" in hechas
    # Solo una actividad intensa que Garmin ya registró hoy ocupa el día; nunca se adivina por el día de la semana.
    otra = next((i for i in hechas if i in cats and cats[i]["intensa"]), None)
    aviso = tt("motor.aviso.repetir") if light.get("repetir_semana") else None
    base = {"version": None, "sesion_id": None, "aviso": aviso, "proxima_id": None}
    manana = (_elegir_pendiente(day + timedelta(days=1), status)[0] or {}).get("id") if status else None
    if otra:
        nombre = cats[otra]["nombre"]
        return {"tipo": "otra", "categoria": nombre, "texto": tt("motor.hoy.otra", nombre=nombre), **{**base, "proxima_id": manana}}
    if hay_run:
        return {"tipo": "hecha_hoy", "texto": tt("motor.hoy.hecha"), **{**base, "proxima_id": manana}}
    if not status:
        return {"tipo": "sin_plan", "texto": tt("motor.hoy.sin_plan"), **base}
    sesion, aviso_larga = _elegir_pendiente(day, status)
    if sesion is None:
        return {"tipo": "completa", "texto": tt("motor.hoy.completa"), **base}
    sin_datos = light["color"] == "sin_datos"
    version = "normal" if sin_datos else {"verde": "normal", "amarillo": "suave", "rojo": "descanso"}[light["color"]]
    aviso = _unir_avisos(aviso, aviso_larga, aviso_pierna(day, sesion, activities, config),
                         tt("motor.aviso.sin_datos") if sin_datos else None)
    return {"tipo": "sesion", "texto": tt("motor.hoy.siguiente", version=tt(f"motor.version.{version}")),
            "version": version, "sesion_id": sesion["id"], "aviso": aviso, "proxima_id": None}


def opciones_hoy(version: str | None, sesion: dict | None) -> list[str]:
    """Versiones que se pueden elegir hoy, en orden. Sin versión suave en el plan no hay nada que elegir."""
    if version not in ("normal", "suave", "descanso") or not sesion or not sesion.get("easy"):
        return []
    return ["descanso", "suave", "normal"] if version == "descanso" else ["suave", "normal"]


# --- trote / caminata ---

def _tramos(activity: dict, details: dict) -> list:
    """Tramos RWD_* de details (con FC) o, si no hay, de splitSummaries de la lista (sin FC)."""
    guardados = (details.get(str(id_de(activity))) or {}).get("splits")
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


def minutos_planeados(pasos: list) -> dict:
    """Minutos por zona de los pasos de una sesión (con `repeat`; una sola zona por paso: zona_unica). Los pasos
    opcionales no cuentan: si los haces, suman a lo hecho pero no los exige el plan."""
    out = {}
    for p in pasos:
        if p["kind"] == "repeat":
            for z, mi in minutos_planeados(p["steps"]).items():
                out[z] = out.get(z, 0) + p["times"] * mi
        elif not p.get("optional"):
            z = tipos.zona_unica(p)
            out[z] = out.get(z, 0) + p["minutes"]
    return out


def plan_vs_real(pasos: list, minutos_z: dict, done_ratio: float = 0.7) -> list:
    """Plan vs real por zona. Para cada zona planeada Z ≥ Z2, lo planeado en Z o más contra lo hecho en Z o más (lo que
    haces en una zona más alta cuenta para la de abajo). `ok` = hecho ≥ done_ratio × plan (la FC tarda en subir).
    [{zona, plan_min, hecho_min, pct, ok}] de la zona más alta a la más baja."""
    plan = minutos_planeados(pasos)
    out = []
    for z in reversed(ZONAS[1:]):
        if not plan.get(z):
            continue
        arriba = ZONAS[ZONAS.index(z):]
        plan_acum = sum(plan.get(k, 0) for k in arriba)
        hecho = sum(minutos_z.get(k, 0.0) for k in arriba)
        out.append({"zona": z, "plan_min": round(plan_acum, 1), "hecho_min": round(hecho, 1),
                    "pct": round(hecho / plan_acum * 100), "ok": hecho + 0.05 >= done_ratio * plan_acum})
    if out and out[0]["zona"] in ("Z3", "Z4"):   # zona alta planeada: avisa si pasaste mucho por encima de ella
        tope = out[0]
        arriba = sum(minutos_z.get(k, 0.0) for k in ZONAS[ZONAS.index(tope["zona"]) + 1:])
        tope["arriba_min"] = round(arriba, 1)
        tope["mucho_arriba"] = arriba > max(2.0, 0.25 * tope["plan_min"])
    return out


def run_check(activity: dict, session, config=None, minutos_z=None, suave: bool = False) -> dict:
    """¿Lo hice bien?: minutos sobre el techo de Z2 (Z3+Z4+Z5) vs la tolerancia, y el plan vs real por zona
    (si la corrida tiene sesión y minutos por zona; con `suave`, contra la versión suave)."""
    zm = minutos_z if minutos_z is not None else zone_minutes(activity)
    sobre = round(zm["Z3"] + zm["Z4"] + zm["Z5"], 1)
    tolerancia = (config or {}).get("ceiling_tolerance_min", 2)
    if session and _tiene_opcionales(session.get("steps", [])):
        tolerancia += 2
    if (session or {}).get("tipo") in ("variada", "calidad"):   # su Z3+ es parte del plan
        tolerancia += _min_z3_planeados(session.get("steps", []))
    es_5k = (session or {}).get("prueba") == "5k"
    if es_5k:   # 5 km a tope: pasarse de Z2 es la idea
        tolerancia = activity["duration"] / 60
    out = {"min_sobre_techo": sobre, "tolerancia_min": round(tolerancia, 1), "techo_ok": sobre <= tolerancia}
    if session and minutos_z is not None and not es_5k:
        pasos = session["easy"]["steps"] if suave else session["steps"]
        out["plan_vs_real"] = plan_vs_real(pasos, minutos_z, (config or {}).get("done_ratio", 0.7))
    return out


def sugerencia_semana(hechas, total, dias_rojos: int, carga, carga_anterior, config: dict):
    """Sugerencia por reglas conservadoras del resumen de la semana pasada: {"tipo", "texto"} o None. En orden:
    pocas sesiones hechas (con plan) o muchos días rojos → repetir; carga muy por encima de la anterior → semana pesada;
    todo hecho y sin rojos → seguir el plan. Solo sugiere: repetir la semana sigue siendo con /ajustar (o desde Ajustes en la web)."""
    pocas = total is not None and hechas < config.get("resumen_min_sesiones", 2)
    if pocas or dias_rojos >= config.get("resumen_dias_rojos", 2):
        tipo = "repetir"
    elif carga_anterior and carga > config.get("resumen_carga_alta", 1.3) * carga_anterior:
        tipo = "pesada"
    elif total and hechas >= total and dias_rojos == 0:
        tipo = "sigue"
    else:
        return None
    texto = tt("motor.sugerencia.repetir_web" if tipo == "repetir" and config.get("modo") == "web" else f"motor.sugerencia.{tipo}")
    return {"tipo": tipo, "texto": texto}


def rolling_mean(valores: list, ventana: int = 7, minimo: int = 3) -> list:
    """Media móvil de los valores no nulos de los últimos `ventana` puntos; None si hay menos de `minimo`."""
    out = []
    for i in range(len(valores)):
        vs = [v for v in valores[max(0, i - ventana + 1):i + 1] if v is not None]
        out.append(sum(vs) / len(vs) if len(vs) >= minimo else None)
    return out


def ritmo_fc_ref(fila: dict, zonas: list):
    """Ritmo (s/km) llevado a la FC de referencia (mitad de Z2): ritmo × FC ÷ FC ref, o sea la eficiencia aeróbica.
    Solo corridas al aire libre, no carreras, cuyo trote cayó en Z2; si no, None. Sin tramos de trote/caminata
    (todo trote) usa el ritmo y la FC promedio de la actividad. `fila` es una fila de run_rows."""
    if fila.get("caminadora") or fila.get("carrera"):
        return None
    ritmo, fc = fila.get("ritmo_trote_s"), fila.get("fc_trote")
    if ritmo is None:
        ritmo = fila["minutos"] * 60 / fila["km"] if fila.get("km") else None
        fc = fila.get("fc_prom")
    _, piso, techo = zonas[1]
    if not ritmo or fc is None or not piso <= fc <= techo:
        return None
    return ritmo * fc / fc_referencia(zonas)


DERIVA_MIN = 40          # minutos mínimos de la corrida
DERIVA_TROTE_PCT = 90    # % mínimo de trote (casi sin caminar)
DERIVA_CALENTAR_S = 600  # los primeros 10 min no cuentan
DERIVA_PAREJO = 0.15     # cada km a ±15 % del ritmo mediano
DERIVA_BUENA = 5.0       # < 5 % = buena base
DERIVA_Z2_PCT = 80       # % mínimo del trote (después de los 10 min) con la FC en Z2


def _mediana(valores: list):
    v = sorted(valores)
    n = len(v)
    return None if not n else v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2


def _km_con_inicio(serie: list) -> list:
    """[(segundo en que empieza, segundos que tardó)] de cada km completo de una serie [seg, metros, fc]."""
    pts = [(d, t) for t, d, _ in serie]
    out, k = [], 1

    def tiempo_en(metros):
        for (d0, t0), (d1, t1) in zip(pts, pts[1:]):
            if d0 <= metros <= d1:
                return t0 if d1 == d0 else t0 + (t1 - t0) * (metros - d0) / (d1 - d0)
        return None
    while pts and k * 1000 <= pts[-1][0]:
        a, b = tiempo_en((k - 1) * 1000), tiempo_en(k * 1000)
        if a is None or b is None:
            break
        out.append((a, b - a))
        k += 1
    return out


def deriva(serie: list, fila: dict, zonas=None) -> dict:
    """Deriva cardiaca: cuánto cae la eficiencia (velocidad ÷ FC) de la primera mitad a la segunda.
    Solo corridas de ≥ 40 min casi sin caminar (≥ 90 % trote o sin tramos) y a ritmo parejo (después de los primeros
    10 min, cada km dentro de ±15 % del ritmo mediano) y, con `zonas`, casi todo en Z2 (≥ 80 % del trote después de
    los 10 min; una carrera a tope no cuenta). Sin los primeros 10 min ni los tramos de caminata (velocidad
    < 70 % de la mediana). Devuelve {"pct", "ok"} (ok = pct < 5) o {"pct": None, "motivo"} con motivo "corta",
    "con caminatas", "sin serie", "no pareja" o "fuera de Z2"."""
    no = lambda motivo: {"pct": None, "ok": None, "motivo": motivo}  # noqa: E731
    if fila.get("minutos", 0) < DERIVA_MIN:
        return no("corta")
    if fila.get("pct_trote") is not None and fila["pct_trote"] < DERIVA_TROTE_PCT:
        return no("con caminatas")
    if len(serie or []) < 3:
        return no("sin serie")
    kms = [p for t, p in _km_con_inicio(serie) if t >= DERIVA_CALENTAR_S]
    mediano = _mediana(kms)
    if len(kms) < 2 or any(abs(p - mediano) > DERIVA_PAREJO * mediano for p in kms):
        return no("no pareja")
    # tramos entre muestras: (inicio, segundos, metros, fc) después de los 10 min, sin pausas ni huecos
    tramos = [(a[0], b[0] - a[0], b[1] - a[1], a[2]) for a, b in zip(serie, serie[1:])
              if a[0] >= DERIVA_CALENTAR_S and 0 < b[0] - a[0] <= 15 and a[2] is not None]
    vel = _mediana([m_ / dt for _, dt, m_, _ in tramos])
    tramos = [t for t in tramos if vel and t[2] / t[1] >= 0.7 * vel]
    if len(tramos) < 4:
        return no("sin serie")
    if zonas:
        _, piso, techo = zonas[1]
        en_z2 = sum(t[1] for t in tramos if piso <= t[3] <= techo)
        if en_z2 < DERIVA_Z2_PCT / 100 * sum(t[1] for t in tramos):
            return no("fuera de Z2")
    corte = (DERIVA_CALENTAR_S + serie[-1][0]) / 2
    ef = []
    for mitad in ([t for t in tramos if t[0] < corte], [t for t in tramos if t[0] >= corte]):
        dt = sum(t[1] for t in mitad)
        if not dt or not sum(t[3] * t[1] for t in mitad):
            return no("sin serie")
        ef.append((sum(t[2] for t in mitad) / dt) / (sum(t[3] * t[1] for t in mitad) / dt))
    pct = round((ef[0] - ef[1]) / ef[0] * 100, 1)
    return {"pct": pct, "ok": pct < DERIVA_BUENA, "motivo": None}


def deriva_de(activity: dict, details: dict, zonas=None) -> dict:
    """deriva() de una actividad, con su serie guardada y el % de trote de sus tramos."""
    rw = run_walk(activity, details) or {}
    return deriva((details.get(str(id_de(activity))) or {}).get("serie") or [],
                  {"minutos": (activity.get("duration") or 0) / 60, "pct_trote": rw.get("pct_trote")}, zonas)


def run_rows(activities: list, details: dict, config: dict) -> list:
    """Una fila por corrida: fecha, minutos, km, FC promedio, % en Z1–Z2, caminadora, carrera, trote/caminata,
    ritmo a FC ref y deriva."""
    filas, zonas = [], zonas_de(config)
    for a in sorted(activities, key=lambda a: a["startTimeLocal"]):
        if classify(a, config) != "run":
            continue
        zm = zone_minutes(a)
        total = sum(zm.values())
        rw = run_walk(a, details) or dict.fromkeys(RW_CLAVES)
        fila = {"fecha": day_of(a).isoformat(), "minutos": a["duration"] / 60,
                "km": (a.get("distance") or 0) / 1000, "fc_prom": a.get("averageHR"),
                "pct_z1z2": (zm["Z1"] + zm["Z2"]) / total * 100 if total else None,
                "caminadora": a["activityType"]["typeKey"] == "treadmill_running", "carrera": es_carrera(a, config), **rw}
        # con pulso de muñeca la deriva no es confiable (pide banda de pecho): no se calcula
        pulso = pulso_de(a, details, config)
        d = {"pct": None, "ok": None} if pulso == "muñeca" else deriva_de(a, details, zonas)
        filas.append({**fila, "ritmo_ref_s": ritmo_fc_ref(fila, zonas), "deriva_pct": d["pct"], "deriva_ok": d["ok"], "pulso": pulso})
    return filas


def promedio(valores: list):
    vs = [v for v in valores if v is not None]
    return sum(vs) / len(vs) if vs else None


def _mmss(seg: float) -> str:
    seg = round(seg)
    return f"{seg // 60}:{seg % 60:02d}"


def periodo_filas(filas: list, hoy: date, semanas: int, atras: int = 0) -> list:
    """Filas de las `semanas` semanas que terminan en `hoy` (o `atras` periodos antes): (fin − semanas, fin]. Los
    recuadros de números y la frase del periodo usan este mismo conjunto."""
    fin = hoy - timedelta(weeks=semanas * atras)
    return [f for f in filas if fin - timedelta(weeks=semanas) < date.fromisoformat(f["fecha"]) <= fin]


def frase_ritmo(ahora, antes, fc_ref, cuando_ahora: str, cuando_antes: str):
    """"a 144 lpm: 7:48 → 7:35 /km" (promedio de cada periodo, antes → ahora). Si a un periodo le faltan corridas en Z2,
    dice cuál falta. None si no hubo en ninguno."""
    if ahora and antes:
        return tt("motor.ritmo.a_fc", fc=fc_ref, antes=_mmss(antes), ahora=_mmss(ahora))
    if not ahora and not antes:
        return None
    return tt("motor.ritmo.sin_z2", cuando=cuando_ahora if not ahora else cuando_antes)


def progress_summary(rows: list, hoy: date, semanas: int, fc_ref: int = None) -> str:
    """Compara las últimas `semanas` semanas contra las `semanas` anteriores: % trote y ritmo a la FC de referencia."""
    ahora, antes = periodo_filas(rows, hoy, semanas), periodo_filas(rows, hoy, semanas, 1)
    if not ahora and not antes:
        return tt("motor.progreso.sin_corridas")
    partes = []
    pct_a, pct_b = (promedio([r["pct_trote"] for r in g]) for g in (ahora, antes))
    if pct_a is not None and pct_b is not None:
        partes.append(tt("motor.progreso.trotas", a=f"{pct_a:.0f}", b=f"{pct_b:.0f}"))
    rit = frase_ritmo(*(promedio([r.get("ritmo_ref_s") for r in g]) for g in (ahora, antes)), fc_ref or tt("motor.fc_ref"),
                      tt("motor.progreso.ultimas", n=semanas), tt("motor.progreso.anteriores", n=semanas))
    if rit:
        partes.append(rit)
    if not partes:
        return tt("motor.progreso.sin_corridas")
    return (" · ".join(partes))[0].upper() + (" · ".join(partes))[1:]


def _grupo_mejora(filas: list, ini: date, fin: date, semanas: int):
    """Corridas y minutos por semana y % trote promedio de las corridas con ini <= fecha < fin; None si no hay corridas."""
    g = [f for f in filas if ini <= date.fromisoformat(f["fecha"]) < fin]
    if not g:
        return None
    return {"corridas": len(g) / semanas, "minutos": sum(f["minutos"] for f in g) / semanas,
            "pct_trote": promedio([f.get("pct_trote") for f in g]),
            "ritmo_ref": promedio([f.get("ritmo_ref_s") for f in g])}


def sin_repetidas(activities: list, config: dict, horas: float = 3) -> list:
    """Quita las actividades no-corrida que empiezan a menos de `horas` de la anterior que se quedó de su misma categoría
    (p. ej. un CrossFit grabado en dos partes cuenta como una sola sesión). Las corridas no se tocan."""
    out, ultima = [], {}
    for a in sorted(activities, key=lambda a: a["startTimeLocal"]):
        c = classify(a, config)
        if c and c != "run":
            t = datetime.fromisoformat(a["startTimeLocal"])
            if c in ultima and t - ultima[c] < timedelta(hours=horas):
                continue
            ultima[c] = t
        out.append(a)
    return out





# --- prueba al terminar el plan ---

def distancia_en_tiempo(serie: list, seg: float):
    """Metros recorridos en los primeros `seg` segundos de una serie [seg, metros, fc] (interpola); None si no llega."""
    if not serie or serie[-1][0] < seg:
        return None
    for (t0, d0, _), (t1, d1, _) in zip(serie, serie[1:]):
        if t0 <= seg <= t1:
            return d0 if t1 == t0 else d0 + (d1 - d0) * (seg - t0) / (t1 - t0)
    return None


def tiempo_en_distancia(serie: list, metros: float):
    """Segundos en llegar a `metros` de una serie [seg, metros, fc] (interpola); None si no llega."""
    if not serie or serie[-1][1] < metros:
        return None
    for (t0, d0, _), (t1, d1, _) in zip(serie, serie[1:]):
        if d0 <= metros <= d1:
            return t0 if d1 == d0 else t0 + (t1 - t0) * (metros - d0) / (d1 - d0)
    return None


PRUEBA_FC_FIJA_S = 1800
PRUEBA_SEGUIDO_PCT = 95   # % de trote desde el cual cuenta como 30' seguidos


def valor_prueba(tipo: str, serie: list, pct_trote=None):
    """Lo que mide cada prueba. `fc_fija`: ritmo (s/km) de los primeros 30'; `trote_continuo`: % de trote; `5k`: segundos
    de los 5 km. Devuelve {"valor", "km"} o None si la serie no alcanza."""
    if tipo == "fc_fija":
        metros = distancia_en_tiempo(serie, PRUEBA_FC_FIJA_S)
        return {"valor": round(PRUEBA_FC_FIJA_S / (metros / 1000)), "km": round(metros / 1000, 2)} if metros else None
    if tipo == "trote_continuo":   # si ya trota los 30' seguidos, también los km (para pasar a la prueba a FC fija)
        if pct_trote is None:
            return None
        metros = distancia_en_tiempo(serie, PRUEBA_FC_FIJA_S) if pct_trote >= PRUEBA_SEGUIDO_PCT else None
        return {"valor": round(pct_trote, 1), "km": round(metros / 1000, 2) if metros else None,
                "seguido": pct_trote >= PRUEBA_SEGUIDO_PCT}
    t = tiempo_en_distancia(serie, 5000)
    return None if t is None else {"valor": round(t), "km": 5.0}


def comparar_prueba(tipo: str, valor: float, base):
    """Contra la base {"fuente", "fecha", "valor"}: {"dif", "mejor"} (dif = ahora − antes; en ritmo y tiempo menos es
    mejor, en % de trote más es mejor). None si no hay base."""
    if base is None:
        return None
    dif = round(valor - base["valor"], 1)
    return {"dif": dif, "mejor": None if dif == 0 else (dif > 0 if tipo == "trote_continuo" else dif < 0)}


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
    if activity.get("es_carrera") or (   # el paquete de la web trae `es_carrera` calculado y no el nombre
            "es_carrera" not in activity and _NOMBRE_CARRERA.search(_sin_acentos(activity.get("activityName") or ""))):
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
    det = details.get(str(id_de(activity))) or {}
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
           "esfuerzo": esfuerzo_de(activity, details, config), "rpe": det.get("rpe"),
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
            out.append(marca(clave, tt(f"motor.marca.{clave}"), a, a[f"fastestSplit_{metros}"], metros))
    largas = [a for a in historial if a.get("distance")]
    if largas:
        a = max(largas, key=lambda x: (x["distance"], x["startTimeLocal"]))
        out.append(marca("larga", tt("motor.marca.larga"), a, a["duration"], a["distance"]))
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
        filas = [("peso", tt("motor.ib.peso"), "kg"), ("mme", tt("motor.ib.mme"), "kg"), ("masa_grasa", tt("motor.ib.masa_grasa"), "kg")]
        out["musculo_grasa"] = [_barra_inbody(i, n, u, mg[i], mg[i]["pct"], mg[i]["valor"]) for i, n, u in filas if i in mg]
    ob = med.get("obesidad")
    if ob:
        out["obesidad"] = [_barra_inbody(i, n, u, ob[i], ob[i]["valor"], ob[i]["valor"])
                           for i, n, u in (("imc", tt("motor.ib.imc"), "kg/m²"), ("pgc", tt("motor.ib.pgc"), "%")) if i in ob]
    rangos = []
    for grupo, clave, filas in ((tt("motor.ib.g_investigacion"), "investigacion",
                                 (("tmb_kcal", tt("motor.ib.tmb"), "kcal"), ("cintura_cadera", tt("motor.ib.cintura_cadera"), ""),
                                  ("grado_obesidad_pct", tt("motor.ib.grado_obesidad"), "%"))),
                                (tt("motor.ib.g_composicion"), "composicion",
                                 (("agua_l", tt("motor.ib.agua"), "L"), ("proteinas_kg", tt("motor.ib.proteinas"), "kg"),
                                  ("minerales_kg", tt("motor.ib.minerales"), "kg"), ("masa_grasa_kg", tt("motor.ib.masa_grasa"), "kg"),
                                  ("peso_kg", tt("motor.ib.peso"), "kg")))):
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
    # puntuación: todas las mediciones desde la primera con puntos; las que no la tienen van con puntos None (hueco)
    con = [i for i, x in enumerate(meds) if x.get("puntuacion") is not None]
    if con:
        out["puntuacion"], previo = [], None
        for x in meds[con[0]:]:
            p = x.get("puntuacion")
            out["puntuacion"].append({"fecha": x["fecha"], "puntos": p,
                                      "delta": p - previo if p is not None and previo is not None else None})
            previo = p if p is not None else previo
    visc = next((x for x in reversed(meds) if x.get("grasa_visceral") is not None), None)
    if visc:
        out["visceral"] = {"fecha": visc["fecha"], "valor": visc["grasa_visceral"], "rango": rango,
                           "zona": zona_rango(visc["grasa_visceral"], rango)}
    hoja = next((x for x in reversed(crudas) if x.get("musculo_grasa")), None)
    if hoja:
        out["hoja"] = hoja_inbody(hoja)
    return out


def max_hr_progress(activities: list, config: dict, details: dict = None) -> dict:
    """Progreso de la medición de FC máx con correa en las sesiones intensas (desde `fc_max_correa_desde`)."""
    desde = config.get("fc_max_correa_desde")
    if not desde:
        return {"sesiones": [], "pico": None, "estimacion": None, "revisar": False, "pulso_pico": None,
                "semanas_medidas": 0, "listo": False, "configurada": False}
    desde = date.fromisoformat(desde)
    intensas = {c["id"] for c in categorias_intensas(config)}
    ses = [a for a in activities if classify(a, config) in intensas
           and day_of(a) >= desde and a.get("maxHR")]
    sesiones = sorted(({"fecha": day_of(a).isoformat(), "max_hr": a["maxHR"]} for a in ses),
                      key=lambda s: s["fecha"])
    # el pico sale de las sesiones con banda; solo si no hay ninguna, de las de muñeca (menos confiables)
    con_banda = [a["maxHR"] for a in ses if pulso_de(a, details or {}, config) == "banda"]
    pico = max(con_banda) if con_banda else max((s["max_hr"] for s in sesiones), default=None)
    pulso_pico = None if pico is None else "banda" if con_banda else "muñeca"
    estimacion = max(pico + 3, config["max_hr_floor"]) if pico is not None else None
    semanas = {day_of(a) - timedelta(days=day_of(a).weekday()) for a in ses}
    return {"sesiones": sesiones, "pico": pico, "estimacion": estimacion,
            "revisar": estimacion is not None and estimacion > config["max_hr_review_above"],
            "pulso_pico": pulso_pico, "semanas_medidas": len(semanas), "listo": len(semanas) >= 2, "configurada": True}


def watch_max_hr(hr_zones):
    """FC máx que usa el reloj (perfil DEFAULT); None si Garmin no la da."""
    perfiles = hr_zones if isinstance(hr_zones, list) else [hr_zones or {}]
    perfil = next((p for p in perfiles if p.get("sport") == "DEFAULT"), perfiles[0] if perfiles else {})
    return perfil.get("maxHeartRateUsed")


def max_hr_above_watch(estimacion, reloj, pulso: str = "banda", pico=None):
    """Aviso de FC máx: sin valor de Garmin, cómo sacarla (más el consejo de la banda); con valor y estimación mayor,
    que la cambie en Garmin (seguro si el pico salió de banda, con cautela si fue de muñeca); si no, None."""
    if reloj is None:
        return tt("motor.aviso.fcmax_sin") + " " + tt("motor.aviso.banda_consejo")
    if estimacion is None or estimacion <= reloj:
        return None
    if pulso == "muñeca":
        return tt("motor.aviso.fcmax_muneca", pico=round(pico if pico is not None else estimacion - 3))
    return tt("motor.aviso.fcmax", est=round(estimacion))