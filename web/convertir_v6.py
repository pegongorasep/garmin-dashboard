"""Motor v6 G2: convierte los planes existentes (sin `meta.motor == "v6"`) a v6. Lo corre `python -m web.cli convertir-v6`
(en producción, como Cloud Run Job). Sin `aplicar` es un ensayo: no escribe nada. Idempotente: un plan que ya es v6 se salta.
Lo que se imprime por persona es solo el id y números (minutos de la semana, carreras); nunca nombres, correos ni datos de Garmin.
Una persona que falla no detiene a las demás: se imprime su error y se sigue."""
import copy
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import motor_v6
from ajustes import normalizar_config
from nivel import nivel_desde_datos

from . import cambios, datos
from .modelos import Ajustes, Plan, Usuario

SEMANAS_MIN, SEMANAS_MAX = 1, 52


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _minutos_viejo(plan: dict, lunes: date) -> int | None:
    """Minutos de la semana en curso del plan viejo (None si el plan no llega a esa semana)."""
    try:
        i = (lunes - _lunes(date.fromisoformat(plan["start"]))).days // 7
        return motor_v6.minutos_semana(plan["weeks"][i]) if 0 <= i < len(plan["weeks"]) else None
    except (KeyError, ValueError, TypeError, IndexError):
        return None


def _dias_viejo(plan: dict, lunes: date) -> int:
    """Corridas por semana del plan viejo: las de la semana en curso (o la última del plan), de 2 a 5."""
    semanas = plan.get("weeks") or []
    try:
        i = (lunes - _lunes(date.fromisoformat(plan["start"]))).days // 7
    except (KeyError, ValueError, TypeError):
        i = 0
    w = semanas[min(max(i, 0), len(semanas) - 1)] if semanas else {}
    return max(2, min(5, len(w.get("sessions") or []) or 3))


def _entrada(cfg: dict, calculado: dict, dias: int, lunes: date, carrera: dict | None) -> dict:
    return {"nivel": calculado["nivel"], "dias": dias, "dias_intensos": list(cfg.get("dias_pierna") or []),
            "meta": {"km": int(carrera["distancia_km"]), "fecha": carrera["fecha"]} if carrera else "base",
            "inicio": lunes.isoformat(), "evidencia": calculado["evidencia"], "inicio_minutos": calculado["inicio_minutos"],
            "edad": int((cfg.get("perfil") or {}).get("edad") or 35)}


def _primera_carrera(metas: list, lunes: date) -> dict | None:
    """La primera carrera futura que cabe en un plan v6 (5/10/21/42 km, de 1 a 52 semanas de aquí)."""
    for x in sorted(metas, key=lambda m: m["fecha"]):
        f = date.fromisoformat(x["fecha"])
        if f < lunes or not x.get("distancia_km") or int(float(x["distancia_km"])) not in motor_v6.UMBRALES["taper"]:
            continue
        if SEMANAS_MIN <= (f - lunes).days // 7 + 1 <= SEMANAS_MAX:
            return x
    return None


def convertir(db, atleta: Usuario, plan_viejo: dict, ahora: datetime, aplicar: bool) -> dict:
    """Convierte a una persona. Devuelve {antes, despues, carreras, en_plan}; truena si algo no cuadra (nada se guarda en ese caso)."""
    fila = db.get(Ajustes, atleta.id)
    crudo = copy.deepcopy(fila.config)
    tz = (crudo.get("perfil") or {}).get("zona_horaria") or "America/Merida"
    hoy = ahora.astimezone(ZoneInfo(tz)).date()
    lunes = _lunes(hoy)
    base = normalizar_config({**crudo, "modo": "web"})
    d = datos.leer_archivos(db, atleta.id)
    calculado = nivel_desde_datos(d["activities"], hoy, base, d["details"])
    dias = _dias_viejo(plan_viejo, lunes)
    carrera = _primera_carrera(base["metas"], lunes)
    try:
        plan = motor_v6.generar_v6(_entrada(base, calculado, dias, lunes, carrera))
    except ValueError:
        if carrera is None:
            raise
        carrera = None   # la carrera no cabe en el plan: sigue como meta normal y el plan va sin ella
        plan = motor_v6.generar_v6(_entrada(base, calculado, dias, lunes, None))
    nuevo = copy.deepcopy(crudo)
    corrida = nuevo.setdefault("corrida", {})
    corrida.update({"inicio": plan["start"], "semanas": len(plan["weeks"])})
    corrida.pop("semanas_repetidas", None)
    corrida["metas"] = [{**x, "en_plan": bool(carrera and x["id"] == carrera["id"])} for x in base["metas"]]
    normalizar_config(nuevo)   # ConfigError si algo no cuadra
    res = {"antes": _minutos_viejo(plan_viejo, lunes), "despues": motor_v6.minutos_semana(plan["weeks"][0]),
           "carreras": len(base["metas"]), "en_plan": carrera is not None}
    if aplicar:
        cambios.aplicar_cambio(db, atleta, None, "sistema", "Plan convertido al motor v6 (misma fecha de carrera, inicio esta semana)",
                               {"ajustes": nuevo, "plan": plan})
    return res


def correr(db, ahora: datetime, aplicar: bool = False, correo: str | None = None, salida=print) -> int:
    """Recorre a las personas con plan que no es v6. Devuelve cuántas fallaron (0 = todo bien)."""
    from sqlalchemy import select
    consulta = select(Usuario).where(Usuario.borrado.is_(None)).order_by(Usuario.id)
    if correo:
        consulta = consulta.where(Usuario.correo == correo)
    ids = [u.id for u in db.scalars(consulta)]
    salida(f"convertir-v6: {'APLICANDO' if aplicar else 'ensayo (no se escribe nada)'}; {len(ids)} cuenta(s)")
    hechos = saltados = errores = 0
    for uid in ids:
        try:
            u = db.get(Usuario, uid)
            fila = db.get(Plan, uid)
            if fila is None or db.get(Ajustes, uid) is None or u.sin_plan:
                saltados += 1
                continue
            if motor_v6.es_v6(fila.plan):
                salida(f"id={uid} ya es v6: sin cambio")
                saltados += 1
                continue
            r = convertir(db, u, copy.deepcopy(fila.plan), ahora, aplicar)
            ant = "-" if r["antes"] is None else r["antes"]
            salida(f"id={uid} {'convertido' if aplicar else 'convertiría'}: semana actual antes={ant} min, después={r['despues']} min; "
                   f"carreras conservadas={r['carreras']} (en el plan: {'sí' if r['en_plan'] else 'no'})")
            hechos += 1
        except Exception as ex:   # una persona que falla no detiene a las demás
            db.rollback()
            errores += 1
            salida(f"id={uid} ERROR {type(ex).__name__}: {str(ex)[:200]}")
    salida(f"convertir-v6: {hechos} {'convertidas' if aplicar else 'por convertir'}, {saltados} sin cambio, {errores} con error")
    return errores
