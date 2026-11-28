"""Zonas de FC, perfil de zonas Garmin, minutos por zona y FC máxima."""

from datetime import date, timedelta

from dashboard.i18n import tt
from dashboard.metricas.comun import ZONAS, categorias_intensas, classify, day_of, id_de


def zones(max_hr: float, rhr: float, pcts: list) -> list:
    """Zonas Karvonen: [(zona, piso, techo)]. El techo es el piso de la zona siguiente."""
    pisos = [round(rhr + p / 100 * (max_hr - rhr)) for p in pcts]
    techos = pisos[1:] + [round(max_hr)]
    return [(f"Z{i + 1}", pisos[i], techos[i]) for i in range(len(pcts))]


PCTS_DEFECTO_GARMIN = (50, 60, 70, 80, 90)   # los pisos de fábrica de Garmin (% de FC máx o de la reserva)


TOLERANCIA_DEFECTO_LPM = 2                  # cuánto puede diferir un piso del de fábrica y aun parecerlo (redondeos)


def perfil_zonas_garmin(hr_zones):
    """Perfil de zonas de FC que manda Garmin para correr (sport RUNNING; si no, DEFAULT) o None si falta o está
    incompleto: necesita FC máx y los 5 pisos numéricos, crecientes y bajo la máxima."""
    perfiles = [p for p in (hr_zones if isinstance(hr_zones, list) else [hr_zones or {}]) if isinstance(p, dict)]
    for sport in ("RUNNING", "DEFAULT"):
        for p in perfiles:
            if p.get("sport") != sport:
                continue
            pisos = [p.get(f"zone{i}Floor") for i in range(1, 6)]
            mx = p.get("maxHeartRateUsed")
            nums = pisos + [mx]
            if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in nums) \
                    and all(a < b for a, b in zip(pisos, pisos[1:])) and pisos[-1] < mx:
                return p
    return None


def zonas_garmin(hr_zones):
    """Zonas [(zona, piso, techo)] de Garmin, con la forma de `zones`; None si no hay perfil usable."""
    p = perfil_zonas_garmin(hr_zones)
    if p is None:
        return None
    pisos = [round(p[f"zone{i}Floor"]) for i in range(1, 6)]
    techos = pisos[1:] + [round(p["maxHeartRateUsed"])]
    return [(f"Z{i + 1}", pisos[i], techos[i]) for i in range(5)]


def zonas_de_fabrica(hr_zones) -> bool:
    """True si los pisos de Garmin parecen los de fábrica (50/60/70/80/90 % de la FC máx o de la reserva, ±2 lpm):
    la persona no ha configurado sus zonas en Garmin Connect."""
    p = perfil_zonas_garmin(hr_zones)
    if p is None:
        return False
    mx, rest = p["maxHeartRateUsed"], p.get("restingHeartRateUsed")
    pisos = [p[f"zone{i}Floor"] for i in range(1, 6)]
    bases = [(0, mx)] + ([(rest, mx)] if isinstance(rest, (int, float)) and not isinstance(rest, bool) else [])
    return any(all(abs(piso - (b0 + pct / 100 * (b1 - b0))) <= TOLERANCIA_DEFECTO_LPM
                   for piso, pct in zip(pisos, PCTS_DEFECTO_GARMIN)) for b0, b1 in bases)


def zone_minutes(activity: dict) -> dict:
    """Minutos en Z1..Z5. Z0 (duración − suma) no se devuelve."""
    return {z: (activity.get(f"hrTimeInZone_{i + 1}") or 0) / 60 for i, z in enumerate(ZONAS)}


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


def zonas_de(config: dict) -> list:
    """Zonas del dashboard (las que build deja en config["zonas"]); si no, Karvonen con FC reposo 60 (solo pruebas)."""
    return config.get("zonas") or zones(config["max_hr"], 60, config.get("zone_pcts", [50, 60, 70, 80, 90]))


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
