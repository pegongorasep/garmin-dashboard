"""El paquete que sube cada repo a la web: los archivos de data/ reducidos a una lista blanca por campo.

Lo arma el repo de cada persona (scripts/subir.py) y lo valida otra vez la web antes de guardarlo. Nunca lleva
el perfil de Garmin, IDs de Garmin, nombres de actividades ni GPS.

Campos que sobreviven (solo los que lee el motor; búscalos con grep en dashboard/ y plan/):
- daily: daily_summaries {calendarDate, heartRate.restingValue}; sleep {calendarDate, sleepTimeSeconds};
  hrv {calendarDate, lastNightAvg, status, baseline.{lowUpper, balancedLow, balancedUpper}}.
- activities: {id, es_carrera, startTimeLocal, activityType.typeKey, eventType.typeKey, averageHR, maxHR,
  averageRunningCadenceInStepsPerMinute, distance, duration, elevationGain, hrTimeInZone_1..5, fastestSplit_*}.
  `id` = 16 hex de sha256(salt:activityId); `es_carrera` se calcula aquí con el nombre y el nombre no sube.
- activity_details (llave = `id` opaco): {rpe, splits [{tipo, seg, m, fc, n}], ritmos_km, serie [[seg, m, fc]]}.
  `serie` (FC por segundo, sin GPS) puede subir a la web pero nunca sale en un data.json.
- hr_zones: {sport, trainingMethod, maxHeartRateUsed, restingHeartRateUsed, lactateThresholdHeartRateUsed,
  zone1Floor..zone5Floor}: solo números (y el método como palabra en mayúsculas); nada más del perfil de zonas.
- historial_corridas: {startTimeLocal, activityType.typeKey, distance, duration, eventType.typeKey, fastestSplit_*}.
- meta: {pulled_at, pulled_at_utc}.
"""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from dashboard import ajustes
from dashboard import metrics
from dashboard import validar as validar_json

ESQUEMA = 1
ARCHIVOS = ("daily", "activities", "activity_details", "hr_zones", "historial_corridas", "meta")
MAX_BYTES = 10 * 1024 * 1024
ROOT = Path(__file__).parent.parent
# `serie` y `splits` (tramos de trote/caminata, sin GPS) solo pueden aparecer dentro de activity_details; el resto de
# la lista de privacidad, en ningún lado.
EN_DETALLE = {"serie", "splits"}
PROHIBIDAS = validar_json.PROHIBIDAS


def id_opaco(salt: str, activity_id) -> str:
    """Id estable pero no reversible de una actividad de Garmin: 16 hex de sha256(salt:activityId)."""
    return hashlib.sha256(f"{salt}:{activity_id}".encode()).hexdigest()[:16]


def _leer(ruta: Path, defecto):
    return json.loads(ruta.read_text()) if ruta.exists() else defecto


def _campos(d, claves) -> dict:
    """Solo `claves` de `d` (las que existen). Una clave puede ser (nombre, sub-claves) para un dict anidado."""
    out = {}
    for k in claves:
        if isinstance(k, tuple):
            nombre, sub = k
            if isinstance(d.get(nombre), dict):
                out[nombre] = _campos(d[nombre], sub)
        elif k in d:
            out[k] = d[k]
    return out


def _con_prefijo(d: dict, prefijo: str) -> dict:
    return {k: v for k, v in d.items() if k.startswith(prefijo)}


def _daily(d: dict) -> dict:
    return {
        "daily_summaries": [_campos(x, ["calendarDate", ("heartRate", ["restingValue"])])
                            for x in d.get("daily_summaries") or []],
        "sleep": [_campos(x, ["calendarDate", "sleepTimeSeconds"]) for x in d.get("sleep") or []],
        "hrv": [_campos(x, ["calendarDate", "lastNightAvg", "status",
                            ("baseline", ["lowUpper", "balancedLow", "balancedUpper"])]) for x in d.get("hrv") or []],
    }


_ACTIVIDAD = ["startTimeLocal", ("activityType", ["typeKey"]), ("eventType", ["typeKey"]), "averageHR", "maxHR",
              "averageRunningCadenceInStepsPerMinute", "distance", "duration", "elevationGain", "movingDuration", "calories",
              "aerobicTrainingEffect", "anaerobicTrainingEffect", "trainingEffectLabel",
              "hrTimeInZone_1", "hrTimeInZone_2", "hrTimeInZone_3", "hrTimeInZone_4", "hrTimeInZone_5"]


def _actividades(lista: list, salt: str) -> list:
    config = ajustes.config_por_defecto()
    out = []
    for a in lista or []:
        item = {"id": id_opaco(salt, a["activityId"]), "es_carrera": bool(metrics.es_carrera(a, config)),
                **_campos(a, _ACTIVIDAD), **_con_prefijo(a, "fastestSplit_")}
        out.append(item)
    return out


def _detalles(d: dict, salt: str) -> dict:
    out = {}
    for llave, e in (d or {}).items():
        item = _campos(e, ["rpe", "ritmos_km", "serie", "pulso"])
        if "splits" in e:
            item["splits"] = [_campos(s, ["tipo", "seg", "m", "fc", "n"]) for s in e["splits"] or []]
        out[id_opaco(salt, llave)] = item
    return out


ZONAS_NUM = ("maxHeartRateUsed", "restingHeartRateUsed", "lactateThresholdHeartRateUsed",
             "zone1Floor", "zone2Floor", "zone3Floor", "zone4Floor", "zone5Floor")
ZONAS_CLAVES = {"sport", "trainingMethod", *ZONAS_NUM}
_PALABRA = re.compile(r"[A-Za-z_]{1,30}")


def _zonas_hr(p) -> dict:
    """Un perfil de zonas de FC de Garmin reducido a lo numérico: `sport` y `trainingMethod` solo si son una palabra
    corta; los demás campos, solo si son números (o None). Nunca seriales, IDs ni nombres."""
    p = p if isinstance(p, dict) else {}
    out = {k: p[k] for k in ("sport", "trainingMethod") if isinstance(p.get(k), str) and _PALABRA.fullmatch(p[k])}
    for k in ZONAS_NUM:
        v = p.get(k)
        if isinstance(v, (int, float)) and not isinstance(v, bool) or (k in p and v is None):
            out[k] = v
    return out


def _historial(lista: list) -> list:
    return [{**_campos(a, ["startTimeLocal", ("activityType", ["typeKey"]), "distance", "duration",
                           ("eventType", ["typeKey"])]), **_con_prefijo(a, "fastestSplit_")} for a in lista or []]


def _motor() -> str:
    """Versión del motor que armó el paquete: MOTOR_SHA, o el commit de este código, o "local"."""
    if os.environ.get("MOTOR_SHA"):
        return os.environ["MOTOR_SHA"]
    try:
        r = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else "local"
    except (OSError, subprocess.SubprocessError):
        return "local"


def armar(data_dir, salt: str) -> dict:
    """Lee data/ y devuelve el paquete (ver la docstring del módulo). No toca `profile.json`."""
    d = Path(data_dir)
    hr = _leer(d / "hr_zones.json", [])
    hr = hr if isinstance(hr, list) else [hr or {}]
    return {
        "esquema": ESQUEMA,
        "motor": _motor(),
        "archivos": {
            "daily": _daily(_leer(d / "daily.json", {})),
            "activities": _actividades(_leer(d / "activities.json", []), salt),
            "activity_details": _detalles(_leer(d / "activity_details.json", {}), salt),
            "hr_zones": [_zonas_hr(p) for p in hr if isinstance(p, dict)],
            "historial_corridas": _historial(_leer(d / "historial_corridas.json", [])),
            "meta": _campos(_leer(d / "meta.json", {}), ["pulled_at", "pulled_at_utc"]),
        },
    }


def a_archivos(paquete: dict) -> dict:
    """El paquete como el contenido de los archivos de data/ que lee `build.load_data` (dict nombre -> JSON)."""
    return dict(paquete["archivos"])


def validar(paquete) -> list:
    """Problemas del paquete (lista vacía = bueno): esquema, archivos conocidos, claves prohibidas, tamaño."""
    if not isinstance(paquete, dict):
        return ["el paquete no es un objeto"]
    out = []
    if paquete.get("esquema") != ESQUEMA:
        out.append(f"esquema {paquete.get('esquema')!r} no soportado (se espera {ESQUEMA})")
    archivos = paquete.get("archivos")
    if not isinstance(archivos, dict):
        return out + ["falta `archivos`"]
    desconocidos = set(archivos) - set(ARCHIVOS)
    if desconocidos:
        out.append(f"archivos desconocidos: {', '.join(sorted(map(str, desconocidos)))}")
    if set(paquete) - {"esquema", "motor", "archivos", "personales"}:
        out.append("claves desconocidas en el paquete")
    if not isinstance(paquete.get("motor"), str):
        out.append("falta `motor`")

    def recorrer(o, ruta, en_detalle):
        if isinstance(o, dict):
            for k, v in o.items():
                if k in PROHIBIDAS and not (k in EN_DETALLE and en_detalle):
                    out.append(f"clave prohibida: {ruta}/{k}")
                recorrer(v, f"{ruta}/{k}", en_detalle)
        elif isinstance(o, list):
            for i, v in enumerate(o):
                recorrer(v, f"{ruta}[{i}]", en_detalle)
    for p in archivos.get("hr_zones") or []:
        if not isinstance(p, dict) or _zonas_hr(p) != p:
            out.append("hr_zones: solo se aceptan los campos numéricos de zonas")
            break
    for nombre, contenido in archivos.items():
        recorrer(contenido, nombre, nombre == "activity_details")
    pers = paquete.get("personales")
    if pers is not None:
        if not isinstance(pers, dict) or set(pers) - {"config", "plan", "inbody"} or not all(isinstance(v, dict) for v in pers.values()):
            out.append("`personales` no válido")
        else:
            recorrer(pers, "personales", False)
    if len(json.dumps(paquete, separators=(",", ":"))) >= MAX_BYTES:
        out.append("el paquete pesa 10 MB o más")
    return out


def personales(carpeta) -> dict:
    """Los archivos personales opcionales del repo ({config, plan, inbody}; solo los que existen) para la primera subida.
    La web los importa solo si esa persona aún no tiene ajustes. Nunca revienta: lo que no se pueda leer se salta."""
    c = Path(carpeta)
    out = {}
    try:
        if (c / "config.yaml").exists():
            out["config"] = json.loads(json.dumps(ajustes.leer_config_yaml(c / "config.yaml"), default=str))
        for clave, ruta in (("plan", c / "plan" / "plan.json"), ("inbody", c / "plan" / "inbody.json")):
            if ruta.exists():
                v = json.loads(ruta.read_text())
                if isinstance(v, dict):
                    out[clave] = v
    except Exception:   # noqa: BLE001  (un archivo roto no tumba la subida)
        pass
    return {k: v for k, v in out.items() if isinstance(v, dict)}
