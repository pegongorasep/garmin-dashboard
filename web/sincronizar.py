"""Conexión C2: sincronizaciones (una corrida del workflow de la persona). Lógica pura, sin HTTP."""
import math
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tubo
from .modelos import Sincronizacion, Usuario, ahora

VIVA_MIN = 15
VIVAS = ("esperando", "corriendo")
TIPOS = ("comprobacion", "historial", "normal", "treinta", "programada")


def _vivas(db: Session, usuario_id: int, incluir_programadas: bool) -> list[Sincronizacion]:
    q = select(Sincronizacion).where(Sincronizacion.usuario_id == usuario_id, Sincronizacion.estado.in_(VIVAS))
    if not incluir_programadas:
        q = q.where(Sincronizacion.tipo != "programada")
    return list(db.scalars(q.order_by(Sincronizacion.id.desc())))


def actual(db: Session, usuario_id: int, incluir_programadas: bool = False) -> Sincronizacion | None:
    """La sincronización viva más reciente. Una viva sin noticias en VIVA_MIN minutos pasa a error `otra`."""
    limite = ahora() - timedelta(minutes=VIVA_MIN)
    viva = None
    for s in _vivas(db, usuario_id, incluir_programadas):
        if s.actualizada < limite:
            s.estado, s.error, s.terminada = "error", "otra", ahora()
            db.commit()
        elif viva is None:
            viva = s
    return viva


def ultima_terminada(db: Session, usuario_id: int) -> Sincronizacion | None:
    return db.scalar(select(Sincronizacion).where(Sincronizacion.usuario_id == usuario_id,
                                                  Sincronizacion.estado.in_(("ok", "error")))
                     .order_by(Sincronizacion.terminada.desc(), Sincronizacion.id.desc()).limit(1))


def pedir(db: Session, u: Usuario, tipo: str) -> tuple[Sincronizacion, bool]:
    """Crea una sincronización `esperando`, o regresa la viva (no programada) si ya hay una. No dispara nada."""
    viva = actual(db, u.id)
    if viva is not None:
        return viva, False
    s = Sincronizacion(usuario_id=u.id, tipo=tipo, estado="esperando")
    db.add(s)
    db.commit()
    return s, True


def dias_a_pedir(db: Session, u: Usuario, hoy: date | None = None) -> int:
    """Días desde la última subida buena + 7 (mín. 7, máx. 365); sin subida buena, 365."""
    ultima = tubo.ultima_subida(db, u.id)
    if ultima is None:
        return 365
    hoy = hoy or ahora().date()
    ult = ultima.date() if isinstance(ultima, datetime) else ultima
    return max(7, min(365, (hoy - ult).days + 7))


def rango(tipo: str, db: Session, u: Usuario) -> tuple[int, int]:
    """(días de actividades, semanas de salud) de cada tipo."""
    if tipo == "comprobacion":
        return 1, 1
    if tipo == "historial":
        return 365, 16
    if tipo == "treinta":
        return 30, 5
    dias = dias_a_pedir(db, u)
    return dias, max(1, min(16, math.ceil(dias / 7)))


def avanzar(db: Session, sinc: Sincronizacion, paso: str, hechos: int | None = None, total: int | None = None) -> None:
    sinc.paso = paso
    if sinc.estado == "esperando":
        sinc.estado = "corriendo"
    if hechos is not None:
        sinc.hechos = hechos
    if total is not None:
        sinc.total = total
    sinc.actualizada = ahora()
    db.commit()


def marcar_key_rechazada(u: Usuario) -> bool:
    """Marca el incidente (sin commit). True si es nuevo: ahí va el correo, uno por incidente."""
    nuevo = u.key_rechazada_desde is None
    u.key_rechazada_desde = ahora()   # si ya había incidente, se renueva: la key cambiada que falló otra vez cuenta como cambio nuevo
    return nuevo


def terminar(db: Session, sinc: Sincronizacion, ok: bool, error: str | None = None, nuevas: int | None = None) -> None:
    sinc.estado = "ok" if ok else "error"
    sinc.error = None if ok else (error or "otra")
    if nuevas is not None:
        sinc.nuevas = nuevas
    sinc.actualizada = sinc.terminada = ahora()
    if error == "key_rechazada" and not ok:
        u = db.get(Usuario, sinc.usuario_id)
        if u is not None:
            marcar_key_rechazada(u)
    if ok and sinc.tipo in ("comprobacion", "historial"):
        u = db.get(Usuario, sinc.usuario_id)
        if u is not None:
            u.historial_pendiente = sinc.tipo == "comprobacion"
    db.commit()
