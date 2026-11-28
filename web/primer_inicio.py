"""Primer inicio (parte 2, E3): lo que Hoy ofrece a quien llega sin nada. Python decide; el sitio solo pinta `ui.primer_inicio`.

{garmin: {conectar, liga, ocultar} | None, registrar: url | None, pasos: [{id, url}]}
También `ui.vacios` (los estados vacíos de las pestañas, ver `vacios`).
Va fuera de la caché de calcular (depende de grupos y avisos, no de la huella)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .modelos import Ajustes, AvisoOculto, InBody, MiembroGrupo, Usuario

AVISO_GARMIN = "garmin"


def tiene_plan(db: Session, u: Usuario) -> bool:
    return db.get(Ajustes, u.id) is not None and not u.sin_plan


def vacios(db: Session, u: Usuario, sin_plan: bool, pref: str = "", editable: bool = True) -> dict:
    """`ui.vacios`: lo que ofrecen las pestañas fijas cuando están vacías. `pref` = "/a/<id>" cuando un coach ve a su atleta.
    plan: None con plan; si no, {estado: "sin_plan" | "esperando" (falta el historial), armar: url | None (sin botón)}.
    grupos: None al coach (sin pestaña); si no, {crear, invitar}. Que venga es lo que pone la pestaña Grupos, aun sin ningún grupo."""
    plan = None
    if sin_plan:
        plan = {"estado": "esperando" if u.repo_id and u.historial_pendiente else "sin_plan",
                "armar": f"{pref}/plan/nuevo" if editable else None}
    grupos = None
    if not pref:
        ids = db.scalars(select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == u.id).limit(2)).all()
        grupos = {"crear": "/grupos/nuevo", "invitar": f"/grupos/{ids[0]}" if len(ids) == 1 else "/grupos"}   # la liga se crea en la página del grupo
    return {"plan": plan, "grupos": grupos}


def de(db: Session, u: Usuario, pref: str = "", editable: bool = True) -> dict:
    """`pref` = "/a/<id>" cuando un coach ve a su atleta (sin tarjeta de Garmin ni grupos; solo si puede editar)."""
    if pref and not editable:
        return {"garmin": None, "registrar": None, "pasos": []}
    garmin = None
    if not pref and not u.repo_id and db.get(AvisoOculto, (u.id, AVISO_GARMIN)) is None:
        garmin = {"conectar": "/bienvenida", "liga": "/bienvenida/liga", "ocultar": "/avisos/ocultar"}
    pasos = []
    if not tiene_plan(db, u):
        pasos.append({"id": "plan", "url": f"{pref}/plan/nuevo"})
    if not pref and not db.scalar(select(func.count()).select_from(MiembroGrupo).where(MiembroGrupo.usuario_id == u.id)):
        pasos.append({"id": "grupo", "url": "/grupos"})
    if not db.scalar(select(func.count()).select_from(InBody).where(InBody.usuario_id == u.id)):
        pasos.append({"id": "inbody", "url": f"{pref}/cuerpo"})
    return {"garmin": garmin, "registrar": f"{pref}/actividad/nueva", "pasos": pasos}
