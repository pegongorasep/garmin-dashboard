"""Quién puede ver o editar a quién. TODA consulta de datos de una persona pasa por estas dos funciones."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import Coach, MiembroGrupo, Usuario


def _es_coach(db: Session, actor: Usuario, atleta_id: int) -> bool:
    return db.scalar(select(Coach.id).where(Coach.atleta_id == atleta_id, Coach.coach_id == actor.id)) is not None


def puede_ver(db: Session, actor: Usuario | None, atleta_id: int) -> bool:
    """Dueño o coach vigente. El admin NO ve dashboards ajenos si no es su coach."""
    if actor is None or actor.borrado is not None:
        return False
    return actor.id == atleta_id or _es_coach(db, actor, atleta_id)


def puede_editar(db: Session, actor: Usuario | None, atleta_id: int) -> bool:
    """Un solo nivel de coach: ver y editar. Hoy es lo mismo que ver."""
    return puede_ver(db, actor, atleta_id)


def es_miembro(db: Session, actor: Usuario | None, grupo_id: int) -> bool:
    if actor is None or actor.borrado is not None:
        return False
    return db.scalar(select(MiembroGrupo.id).where(MiembroGrupo.grupo_id == grupo_id,
                                                   MiembroGrupo.usuario_id == actor.id)) is not None


def mismo_grupo(db: Session, actor: Usuario | None, otro_id: int) -> bool:
    """G2: comparten al menos un grupo (solo para nombre y foto; el avance depende además de `pausado`)."""
    if actor is None or actor.borrado is not None:
        return False
    if actor.id == otro_id:
        return True
    mios = select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == actor.id)
    return db.scalar(select(MiembroGrupo.id).where(MiembroGrupo.usuario_id == otro_id,
                                                   MiembroGrupo.grupo_id.in_(mios)).limit(1)) is not None
