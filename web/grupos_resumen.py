"""Tarjetas de avance de los miembros de un grupo: solo campos de lista blanca, calculados del data.json de cada quien
(el mismo que usa Hoy: `calculo.calcular`, así «hecha» y «no hecha» salen de la misma lógica)."""
import logging

from sqlalchemy.orm import Session

from . import calculo
from .modelos import Ajustes, MiembroGrupo, Plan, Usuario

log = logging.getLogger("web.grupos_resumen")

CAMPOS = {"usuario_id", "estado", "meta", "etapa_n", "adherencia", "dias", "ultima"}   # lo único que sale de una tarjeta
SEMANAS_ADHERENCIA = 4


def _adherencia(semanas: list) -> int | None:
    """% de sesiones hechas en las últimas semanas pasadas con plan (o en la actual si aún no hay pasadas)."""
    con_plan = [s for s in semanas if s.get("plan")]
    base = [s for s in con_plan if s["estado"] == "pasada"][-SEMANAS_ADHERENCIA:] or [s for s in con_plan if s["estado"] == "actual"]
    total = sum(s["plan"]["total"] for s in base)
    return round(100 * sum(s["plan"]["hechas"] for s in base) / total) if total else None


def tarjeta_de(db: Session, usuario: Usuario, miembro: MiembroGrupo) -> dict:
    base = {"usuario_id": usuario.id, "estado": "ok", "meta": None, "etapa_n": None, "adherencia": None, "dias": [], "ultima": None}
    if miembro.pausado:
        return {**base, "estado": "pausa"}
    sin_plan = {**base, "estado": "sin_plan"}
    if db.get(Ajustes, usuario.id) is None or db.get(Plan, usuario.id) is None:
        return sin_plan
    try:
        data = calculo.calcular(db, usuario)
    except Exception:   # SinConfig, DataInvalido o lo que sea: la tarjeta no tumba la página del grupo
        log.warning("tarjeta de usuario %s sin datos", usuario.id, exc_info=True)
        return sin_plan
    semanas = data.get("semanas_hoy") or []
    actual = semanas[data.get("semana_hoy_idx") or 0] if semanas else None
    if not actual or not actual.get("plan"):
        return sin_plan
    hoy = (data.get("generado") or "")[:10]
    dias = ["hecha" if d.get("corrida") else "futuro" if d["fecha"] > hoy else "libre" for d in actual["dias"]]
    carreras = [e for e in (data.get("plan") or {}).get("eventos", []) if e["tipo"] == "carrera" and e["desde"] >= hoy]
    return {**base, "meta": carreras[0]["nombre"] if carreras else None, "etapa_n": actual.get("n"),
            "adherencia": _adherencia(semanas), "dias": dias, "ultima": ((data.get("ultima_corrida") or {}).get("fecha"))}


def tarjetas(db: Session, miembros: list[tuple[MiembroGrupo, Usuario]]) -> dict[int, dict]:
    return {u.id: tarjeta_de(db, u, m) for m, u in miembros}
