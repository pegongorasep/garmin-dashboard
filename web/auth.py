"""Invitaciones, liga de entrada por correo, sesiones y CSRF. Todos los tokens se guardan solo como hash (SHA-256)."""
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .modelos import Invitacion, LigaLogin, Sesion, Usuario, ahora

COOKIE_SESION = "sesion"
COOKIE_CSRF = "csrf"
DIAS_INVITACION = 14
MIN_LIGA = 15
DIAS_SESION = 60
LIGAS_POR_HORA = 5
MENSAJE_LIGA = "Si tu correo está registrado, te llegó una liga."


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def nuevo_token() -> str:
    return secrets.token_urlsafe(32)


def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower()


def correo_valido(correo: str) -> bool:
    c = normalizar_correo(correo)
    return len(c) <= 320 and c.count("@") == 1 and "." in c.split("@")[1] and " " not in c and not c.startswith("@")


# --- invitaciones ---

def crear_invitacion(db: Session, creada_por: int | None, nota: str | None = None) -> str:
    """Devuelve el token en claro (solo se ve aquí); en la base queda su hash."""
    token = nuevo_token()
    db.add(Invitacion(token_hash=hash_token(token), creada_por=creada_por, nota=nota,
                      expira=ahora() + timedelta(days=DIAS_INVITACION)))
    db.commit()
    return token


def invitacion_vigente(db: Session, token: str) -> Invitacion | None:
    inv = db.get(Invitacion, hash_token(token))
    if inv is None or inv.usada_en is not None or inv.expira < ahora():
        return None
    return inv


def aceptar_invitacion(db: Session, token: str, correo: str) -> Usuario | None:
    """Crea la cuenta y gasta la invitación. None si la invitación no vale o el correo ya tiene cuenta
    (en ese caso la invitación NO se gasta)."""
    inv = invitacion_vigente(db, token)
    correo = normalizar_correo(correo)
    if inv is None or not correo_valido(correo) or buscar_por_correo(db, correo):
        return None
    usuario = Usuario(correo=correo)
    db.add(usuario)
    db.flush()
    inv.usada_por, inv.usada_en = usuario.id, ahora()
    db.commit()
    return usuario


def buscar_por_correo(db: Session, correo: str) -> Usuario | None:
    return db.scalar(select(Usuario).where(Usuario.correo == normalizar_correo(correo), Usuario.borrado.is_(None)))


def crear_admin(db: Session, correo: str) -> Usuario:
    correo = normalizar_correo(correo)
    u = db.scalar(select(Usuario).where(Usuario.correo == correo))
    if u is None:
        u = Usuario(correo=correo)
        db.add(u)
    u.es_admin, u.borrado = True, None
    db.commit()
    return u


# --- liga de entrada ---

def crear_liga(db: Session, usuario: Usuario) -> str | None:
    """Token de liga (15 min, un uso). None si ya pidió 5 en la última hora."""
    pedidas = db.scalar(select(func.count()).select_from(LigaLogin).where(
        LigaLogin.usuario_id == usuario.id, LigaLogin.creada > ahora() - timedelta(hours=1)))
    if pedidas >= LIGAS_POR_HORA:
        return None
    token = nuevo_token()
    db.add(LigaLogin(token_hash=hash_token(token), usuario_id=usuario.id, expira=ahora() + timedelta(minutes=MIN_LIGA)))
    db.commit()
    return token


def liga_vigente(db: Session, token: str) -> LigaLogin | None:
    liga = db.get(LigaLogin, hash_token(token))
    if liga is None or liga.usada_en is not None or liga.expira < ahora():
        return None
    return liga


def gastar_liga(db: Session, token: str) -> Usuario | None:
    """Marca la liga como usada y devuelve su usuario (None si no vale). Un solo uso, aun con dos clics a la vez."""
    liga = liga_vigente(db, token)
    if liga is None:
        return None
    r = db.execute(LigaLogin.__table__.update().where(
        LigaLogin.token_hash == liga.token_hash, LigaLogin.usada_en.is_(None)).values(usada_en=ahora()))
    db.commit()
    if r.rowcount != 1:
        return None
    u = db.get(Usuario, liga.usuario_id)
    return u if u and u.borrado is None else None


# --- sesiones ---

def crear_sesion(db: Session, usuario: Usuario) -> str:
    """Valor para la cookie (en claro); en la base solo su hash."""
    valor = nuevo_token()
    db.add(Sesion(id=hash_token(valor), usuario_id=usuario.id, expira=ahora() + timedelta(days=DIAS_SESION)))
    db.commit()
    return valor


def usuario_de_sesion(db: Session, valor: str | None) -> Usuario | None:
    """Usuario de la cookie; renueva la sesión (60 días desde el último uso, anotado a lo más cada hora)."""
    if not valor:
        return None
    s = db.get(Sesion, hash_token(valor))
    if s is None or s.expira < ahora():
        return None
    u = db.get(Usuario, s.usuario_id)
    if u is None or u.borrado is not None:
        return None
    if ahora() - s.ultima_vez > timedelta(hours=1):
        s.ultima_vez, s.expira = ahora(), ahora() + timedelta(days=DIAS_SESION)
        db.commit()
    return u


def cerrar_sesion(db: Session, valor: str | None) -> None:
    if valor:
        s = db.get(Sesion, hash_token(valor))
        if s:
            db.delete(s)
            db.commit()


def cerrar_sesiones_de(db: Session, usuario_id: int) -> None:
    db.execute(Sesion.__table__.delete().where(Sesion.usuario_id == usuario_id))
    db.commit()


# --- CSRF (cookie aleatoria + campo = HMAC de la cookie con la SECRET_KEY) ---

def campo_csrf(secret_key: str, cookie: str) -> str:
    return hmac.new(secret_key.encode(), cookie.encode(), hashlib.sha256).hexdigest()


def csrf_valido(secret_key: str, cookie: str | None, campo: str | None) -> bool:
    return bool(cookie and campo) and hmac.compare_digest(campo_csrf(secret_key, cookie), campo)
