"""Detalle de corridas, run/walk, ritmos, deriva, progreso y actividades encadenadas."""

from datetime import date, datetime, timedelta

from dashboard.i18n import tt
from dashboard.metricas.carreras import es_carrera
from dashboard.metricas.comun import classify, day_of, id_de
from dashboard.metricas.zonas import fc_referencia, pulso_de, zonas_de, zone_minutes


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


ENCADENADA_MIN = 30   # minutos máximos entre el fin de una actividad y el inicio de la siguiente para contarlas como una sesión


def _fin(a: dict) -> datetime:
    return datetime.fromisoformat(a["startTimeLocal"]) + timedelta(seconds=a.get("duration") or 0)


def _nombre_tipo(a: dict, respaldo: str) -> str:
    """Nombre del tipo de actividad según el catálogo (motor.tipo.*); si no está, el de su categoría. Nunca el nombre de Garmin."""
    clave = f"motor.tipo.{a['activityType']['typeKey']}"
    n = tt(clave)
    return respaldo if n == clave else n


def _unir(partes: list, config: dict) -> dict:
    """Una sola actividad con las partes de una sesión encadenada. Categoría = la más intensa (`intensa`, luego la más
    larga); minutos, distancia, calorías, desnivel y minutos por zona suman; FC prom. pesada por duración, FC máx. el máximo.
    Guarda las originales en `_partes` (no sale en el data.json) y `partes` [{cat, nombre, minutos}] con nombres del catálogo."""
    cats = {c["id"]: c for c in config.get("categorias", [])}
    gana = max(partes, key=lambda a: (bool(cats[classify(a, config)].get("intensa")), a.get("duration") or 0))
    suma = lambda k: sum(a.get(k) or 0 for a in partes)   # noqa: E731
    out = {**gana, "startTimeLocal": partes[0]["startTimeLocal"], "duration": suma("duration"), "distance": suma("distance"),
           "calories": suma("calories") or gana.get("calories"), "elevationGain": suma("elevationGain") or gana.get("elevationGain")}
    if any(a.get("movingDuration") for a in partes):
        out["movingDuration"] = sum(a.get("movingDuration") or a.get("duration") or 0 for a in partes)
    for i in range(1, 6):
        k = f"hrTimeInZone_{i}"
        out[k] = suma(k) if any(a.get(k) is not None for a in partes) else None
    con_fc = [a for a in partes if a.get("averageHR")]
    peso = sum(a.get("duration") or 0 for a in con_fc)
    out["averageHR"] = sum(a["averageHR"] * (a.get("duration") or 0) for a in con_fc) / peso if peso else gana.get("averageHR")
    out["maxHR"] = max((a["maxHR"] for a in partes if a.get("maxHR")), default=gana.get("maxHR"))
    for k in ("aerobicTrainingEffect", "anaerobicTrainingEffect"):
        out[k] = max((a[k] for a in partes if a.get(k)), default=None)
    out["_partes"] = partes
    out["partes"] = [{"cat": classify(a, config), "nombre": _nombre_tipo(a, cats[classify(a, config)]["nombre"]),
                      "minutos": round((a.get("duration") or 0) / 60)} for a in partes]
    return out


def unir_encadenadas(activities: list, config: dict, gap_min: float = ENCADENADA_MIN) -> list:
    """Las actividades no-corrida (de cualquier categoría que se muestre) donde la siguiente empieza a ≤ `gap_min`
    minutos de que acabó la anterior son UNA sesión (un CrossFit grabado como fuerza + hiit; también cadenas de 3 o más).
    Las corridas y lo que no se muestra no se tocan. Devuelve la lista ordenada con cada cadena ya unida (`_unir`)."""
    ordenadas = sorted(activities, key=lambda a: a["startTimeLocal"])
    cadenas, cadena = [], []
    for a in ordenadas:
        c = classify(a, config)
        if not c or c == "run":
            continue
        if a.get("manual"):   # lo registrado a mano nunca se junta con otra actividad (ni entre sí)
            cadenas.append([a])
            cadena = []
            continue
        if cadena and datetime.fromisoformat(a["startTimeLocal"]) - max(_fin(x) for x in cadena) <= timedelta(minutes=gap_min):
            cadena.append(a)
        else:
            cadena = [a]
            cadenas.append(cadena)
    union = {id(a): ch for ch in cadenas if len(ch) > 1 for a in ch}
    out, hechas = [], set()
    for a in ordenadas:
        ch = union.get(id(a))
        if ch is None:
            out.append(a)
        elif id(ch) not in hechas:
            hechas.add(id(ch))
            out.append(_unir(ch, config))
    return out


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
