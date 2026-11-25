"""Quién puede ver o editar a quién. TODA consulta de datos de una persona pasa por estas dos funciones."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import Coach, Usuario


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
