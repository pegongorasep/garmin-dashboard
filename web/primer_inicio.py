"""Primer inicio (parte 2, E3): lo que Hoy ofrece a quien llega sin nada. Python decide; el sitio solo pinta `ui.primer_inicio`.

{garmin: {conectar, liga, ocultar} | None, registrar: url | None, pasos: [{id, url}]}
Va fuera de la caché de calcular (depende de grupos y avisos, no de la huella)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .modelos import Ajustes, AvisoOculto, InBody, MiembroGrupo, Usuario

AVISO_GARMIN = "garmin"


def tiene_plan(db: Session, u: Usuario) -> bool:
    return db.get(Ajustes, u.id) is not None and not u.sin_plan


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
