"""Actividades registradas a mano (parte 2, E4): tipos, validación y la forma de Garmin con que entran al motor.
La nota es privada: nunca entra a la actividad que ve el motor (ni, por tanto, a data.json, grupos o feed)."""
import re
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import ActividadManual

# clave -> typeKey con que entra al motor, unidad de la distancia («km», «m» u «oculta») y si es obligatoria.
# Categoría de cada typeKey: `metrics.CATEGORIA_MANUAL` (mapa fijo, decisión 6).
TIPOS = {
    "correr": {"type_key": "running", "unidad": "km", "obligatoria": True},
    "caminar": {"type_key": "walking", "unidad": "km", "obligatoria": True},
    "crossfit": {"type_key": "hiit", "unidad": "oculta", "obligatoria": False},
    "gimnasio": {"type_key": "strength_training", "unidad": "oculta", "obligatoria": False},
    "bicicleta": {"type_key": "cycling", "unidad": "km", "obligatoria": False},
    "natacion": {"type_key": "lap_swimming", "unidad": "m", "obligatoria": False},
    "senderismo": {"type_key": "hiking", "unidad": "km", "obligatoria": False},
    "eliptica": {"type_key": "elliptical", "unidad": "oculta", "obligatoria": False},
    "yoga": {"type_key": "yoga", "unidad": "oculta", "obligatoria": False},
    "deporte": {"type_key": "sport", "unidad": "oculta", "obligatoria": False},
    "otra": {"type_key": "other", "unidad": "km", "obligatoria": False},   # distancia opcional
}
CLAVE_DE_TYPE_KEY = {v["type_key"]: k for k, v in TIPOS.items()}
MAX_NOTA = 280
MAX_DURACION_S = 24 * 3600
MAX_DISTANCIA_M = 1_000_000


def _num(texto) -> float | None:
    """Número con coma o punto decimal; None si está vacío; ValueError si no es número."""
    t = str(texto if texto is not None else "").strip().replace(",", ".")
    if not t:
        return None
    n = float(t)
    if n != n or n in (float("inf"), float("-inf")):
        raise ValueError(t)
    return n


def _tiempo(texto) -> int | None:
    """«h:mm:ss» o «mm:ss» (también «h:mm:ss» con ceros de más) en segundos; None si está vacío; ValueError si no vale."""
    t = str(texto if texto is not None else "").strip()
    if not t:
        return None
    if not re.fullmatch(r"\d{1,3}(:\d{1,2}){1,2}", t):
        raise ValueError(t)
    partes = [int(x) for x in t.split(":")]
    if any(p >= 60 for p in partes[1:]):
        raise ValueError(t)
    s = 0
    for p in partes:
        s = s * 60 + p
    return s


def validar(form, hoy: date) -> tuple[dict | None, dict]:
    """(datos, errores). `datos` = columnas de ActividadManual (sin usuario) o None si hay errores; `errores` = {campo: clave i18n}.
    `hoy` es la fecha de hoy en la zona de la persona (no se aceptan fechas futuras)."""
    g = lambda k: (form.get(k) or "") if hasattr(form, "get") else ""   # noqa: E731
    errores: dict = {}
    tipo = str(g("tipo")).strip()
    if tipo not in TIPOS:
        errores["tipo"] = "web.manual.err.tipo"
        info = {"unidad": "oculta", "obligatoria": False}
    else:
        info = TIPOS[tipo]
    fecha = None
    try:
        fecha = date.fromisoformat(str(g("fecha")).strip())
        if fecha > hoy:
            errores["fecha"] = "web.manual.err.fecha_futura"
        elif fecha.year < 2000:
            errores["fecha"] = "web.manual.err.fecha"
    except ValueError:
        errores["fecha"] = "web.manual.err.fecha"
    distancia_m = None
    if info["unidad"] != "oculta":
        try:
            d = _num(g("distancia"))
            if d is None:
                if info["obligatoria"]:
                    errores["distancia"] = "web.manual.err.distancia_falta"
            elif d <= 0 or d * (1 if info["unidad"] == "m" else 1000) > MAX_DISTANCIA_M:
                errores["distancia"] = "web.manual.err.distancia"
            else:
                distancia_m = round(d * (1 if info["unidad"] == "m" else 1000))
        except ValueError:
            errores["distancia"] = "web.manual.err.distancia"
    duracion_s = None
    try:
        duracion_s = _tiempo(g("tiempo"))
        if duracion_s is None:
            errores["tiempo"] = "web.manual.err.tiempo_falta"
        elif not 0 < duracion_s <= MAX_DURACION_S:
            errores["tiempo"] = "web.manual.err.tiempo"
    except ValueError:
        errores["tiempo"] = "web.manual.err.tiempo"
    esfuerzo = fc_prom = None
    try:
        e = _num(g("esfuerzo"))
        if e is not None:
            if e != int(e) or not 1 <= e <= 10:
                raise ValueError
            esfuerzo = int(e)
    except ValueError:
        errores["esfuerzo"] = "web.manual.err.esfuerzo"
    try:
        f = _num(g("fc_prom"))
        if f is not None:
            if f != int(f) or not 30 <= f <= 250:
                raise ValueError
            fc_prom = int(f)
    except ValueError:
        errores["fc_prom"] = "web.manual.err.fc"
    nota = str(g("nota")).strip() or None
    if nota and len(nota) > MAX_NOTA:
        errores["nota"] = "web.manual.err.nota"
    if errores:
        return None, errores
    return {"fecha": fecha, "tipo": tipo, "distancia_m": distancia_m, "duracion_s": duracion_s,
            "esfuerzo": esfuerzo, "fc_prom": fc_prom, "nota": nota}, {}


def a_actividad(fila: ActividadManual) -> dict:
    """La fila con la forma de una actividad de Garmin para el motor. Sin la nota (es privada)."""
    info = TIPOS.get(fila.tipo) or TIPOS["otra"]
    a = {"id": f"m{fila.id}", "es_carrera": False, "manual": True,
         "startTimeLocal": f"{fila.fecha.isoformat()}T12:00:00",
         "activityType": {"typeKey": info["type_key"]},
         "distance": fila.distancia_m, "duration": fila.duracion_s}
    if fila.fc_prom is not None:
        a["averageHR"] = fila.fc_prom
    return a


def detalle_de(fila: ActividadManual) -> dict | None:
    """Lo que va en `details` de la actividad: el esfuerzo como `rpe`. None si no lo puso."""
    return {"rpe": fila.esfuerzo} if fila.esfuerzo is not None else None


def de_persona(db: Session, usuario_id: int) -> list[ActividadManual]:
    return list(db.scalars(select(ActividadManual).where(ActividadManual.usuario_id == usuario_id)
                           .order_by(ActividadManual.fecha, ActividadManual.id)))
