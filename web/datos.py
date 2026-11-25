"""Guardar y leer los datos de Garmin de una persona (tabla `datos_garmin`). Subir es siempre upsert: nunca borra."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import DatoGarmin, ahora

TIPOS = ("actividad", "detalle", "dia", "sueno", "hrv", "zonas", "historial", "meta")


def _upsert(db: Session, usuario_id: int, tipo: str, items: list) -> tuple[int, int]:
    """items = [(clave, contenido)]. Devuelve (nuevos, cambiados)."""
    existentes = {d.clave: d for d in db.scalars(
        select(DatoGarmin).where(DatoGarmin.usuario_id == usuario_id, DatoGarmin.tipo == tipo))}
    nuevos = cambiados = 0
    for clave, contenido in items:
        clave = str(clave)
        fila = existentes.get(clave)
        if fila is None:
            fila = DatoGarmin(usuario_id=usuario_id, tipo=tipo, clave=clave, contenido=contenido)
            db.add(fila)
            existentes[clave] = fila   # una clave repetida dentro del mismo paquete no choca
            nuevos += 1
        elif fila.contenido != contenido:
            fila.contenido, fila.actualizado = contenido, ahora()
            cambiados += 1
    return nuevos, cambiados


def guardar_paquete(db: Session, usuario_id: int, paquete: dict) -> dict:
    """Upsert por (tipo, clave): actividades y detalles por `id`, días/sueño/hrv por fecha, historial por fecha de la
    corrida, zonas y meta completas. El paquete ya pasó `paquete.validar`. Hace commit."""
    a = paquete["archivos"]
    daily = a.get("daily") or {}
    cuentas = {
        "actividad": _upsert(db, usuario_id, "actividad", [(x["id"], x) for x in a.get("activities") or []]),
        "detalle": _upsert(db, usuario_id, "detalle", list((a.get("activity_details") or {}).items())),
        "dia": _upsert(db, usuario_id, "dia", [(x["calendarDate"], x) for x in daily.get("daily_summaries") or []
                                               if x.get("calendarDate")]),
        "sueno": _upsert(db, usuario_id, "sueno", [(x["calendarDate"], x) for x in daily.get("sleep") or []
                                                   if x.get("calendarDate")]),
        "hrv": _upsert(db, usuario_id, "hrv", [(x["calendarDate"], x) for x in daily.get("hrv") or []
                                               if x.get("calendarDate")]),
        "historial": _upsert(db, usuario_id, "historial", [(x["startTimeLocal"], x)
                                                          for x in a.get("historial_corridas") or []]),
    }
    if a.get("hr_zones"):
        cuentas["zonas"] = _upsert(db, usuario_id, "zonas", [("actual", a["hr_zones"])])
    if a.get("meta"):
        cuentas["meta"] = _upsert(db, usuario_id, "meta", [("meta", a["meta"])])
    db.commit()
    return {k: {"nuevos": n, "cambiados": c} for k, (n, c) in cuentas.items()}


def leer_archivos(db: Session, usuario_id: int) -> dict:
    """Lo guardado, con la forma que lee `build.load_data` (menos `inbody`). Actividades de la más nueva a la más vieja."""
    por_tipo: dict = {t: [] for t in TIPOS}
    for d in db.scalars(select(DatoGarmin).where(DatoGarmin.usuario_id == usuario_id).order_by(DatoGarmin.id)):
        por_tipo[d.tipo].append(d)
    una = lambda tipo, defecto: por_tipo[tipo][0].contenido if por_tipo[tipo] else defecto   # noqa: E731
    return {
        "daily_summaries": [d.contenido for d in por_tipo["dia"]],
        "sleep": [d.contenido for d in por_tipo["sueno"]],
        "hrv": [d.contenido for d in por_tipo["hrv"]],
        # el motor depende del orden de las actividades: las más recientes primero, como las entrega Garmin
        "activities": sorted((d.contenido for d in por_tipo["actividad"]),
                             key=lambda a: (a.get("startTimeLocal") or "", a.get("id") or ""), reverse=True),
        "details": {d.clave: d.contenido for d in por_tipo["detalle"]},
        "hr_zones": una("zonas", []),
        "meta": una("meta", {}),
        "historial": [d.contenido for d in por_tipo["historial"]] or None,
    }
