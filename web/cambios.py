"""Historial de cambios. TODA escritura a `ajustes`, `planes` o `inbody` pasa por `aplicar_cambio`: guarda quién, por qué
vía y el antes/después, y permite deshacer (el `antes` se aplica como un cambio nuevo)."""
import copy

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .modelos import Ajustes, Cambio, InBody, Plan, Usuario, ahora
from .permisos import puede_editar

CAMPOS = ("ajustes", "plan", "inbody")
VIAS = ("web", "ia", "coach", "sistema")
MAX_AVISOS = 5


class SinPermiso(Exception):
    """El autor no puede editar a ese atleta."""


class NoSeDeshace(Exception):
    """El cambio ya se deshizo, es de otra persona o fue una creación (no hay un «antes» al que volver)."""
    def __init__(self, clave: str):
        import i18n
        self.clave, self.vars = clave, {}
        super().__init__(i18n.t(clave, "es"))


def instantanea(db: Session, atleta_id: int, claves) -> dict:
    """Lo guardado hoy de `claves` (ajustes: dict crudo; plan: dict; inbody: lista de mediciones por fecha). None si no hay."""
    out = {}
    if "ajustes" in claves:
        fila = db.get(Ajustes, atleta_id)
        out["ajustes"] = copy.deepcopy(fila.config) if fila else None
    if "plan" in claves:
        fila = db.get(Plan, atleta_id)
        out["plan"] = copy.deepcopy(fila.plan) if fila else None
    if "inbody" in claves:
        filas = db.scalars(select(InBody).where(InBody.usuario_id == atleta_id).order_by(InBody.fecha, InBody.id))
        out["inbody"] = [copy.deepcopy(f.valores) for f in filas]
    return out


def _escribir(db: Session, atleta_id: int, campo: str, valor) -> None:
    if campo == "ajustes":
        fila = db.get(Ajustes, atleta_id)
        if fila is None:
            db.add(Ajustes(usuario_id=atleta_id, config=valor))
        else:
            fila.config, fila.version, fila.actualizado = valor, fila.version + 1, ahora()
    elif campo == "plan":
        fila = db.get(Plan, atleta_id)
        if fila is None:
            db.add(Plan(usuario_id=atleta_id, plan=valor))
        else:
            fila.plan, fila.version, fila.actualizado = valor, fila.version + 1, ahora()
    else:   # inbody: se reemplaza la lista completa (son pocas filas)
        db.execute(delete(InBody).where(InBody.usuario_id == atleta_id))
        for med in valor or []:
            db.add(InBody(usuario_id=atleta_id, fecha=med["fecha"], valores=med))


def aplicar_cambio(db: Session, atleta: Usuario, autor: Usuario | None, via: str, descripcion: str, nuevo: dict) -> Cambio:
    """Escribe `nuevo` ({"ajustes"?, "plan"?, "inbody"?}) y registra el cambio. `autor` None solo con via "sistema".
    Truena con SinPermiso si el autor no puede editar al atleta. Hace commit."""
    if via not in VIAS:
        raise ValueError(f"vía '{via}' desconocida")
    if autor is None and via != "sistema":
        raise SinPermiso()
    if autor is not None and not puede_editar(db, autor, atleta.id):
        raise SinPermiso()
    claves = [c for c in CAMPOS if c in nuevo]
    if not claves:
        raise ValueError("el cambio no trae nada que guardar")
    antes = instantanea(db, atleta.id, claves)
    despues = {c: copy.deepcopy(nuevo[c]) for c in claves}
    for c in claves:
        _escribir(db, atleta.id, c, despues[c])
    propio = autor is not None and autor.id == atleta.id and via == "web"
    cambio = Cambio(atleta_id=atleta.id, autor_id=autor.id if autor else None, via=via, descripcion=descripcion,
                    antes=antes, despues=despues, visto=propio or via == "sistema")
    db.add(cambio)
    db.commit()
    return cambio


def via_de(actor: Usuario, atleta: Usuario) -> str:
    return "web" if actor.id == atleta.id else "coach"


def deshacer(db: Session, actor: Usuario, cambio_id: int, via: str | None = None) -> Cambio:
    """Aplica el `antes` de un cambio como un cambio nuevo y marca el original. Truena con SinPermiso (el actor no puede
    editar a ese atleta o el cambio no existe: se trata igual para no confirmar nada) o NoSeDeshace."""
    c = db.get(Cambio, cambio_id)
    if c is None or not puede_editar(db, actor, c.atleta_id):
        raise SinPermiso()
    if c.deshecho_por is not None:
        raise NoSeDeshace("err.ya_deshecho")
    if not c.antes or any(v is None for v in c.antes.values()):
        raise NoSeDeshace("err.creado")
    atleta = db.get(Usuario, c.atleta_id)
    nuevo = aplicar_cambio(db, atleta, actor, via or via_de(actor, atleta), f"Deshacer: {c.descripcion}", c.antes)
    c.deshecho_por, c.visto = nuevo.id, True
    db.commit()
    return nuevo


def puede_deshacer(c: Cambio) -> bool:
    return c.deshecho_por is None and bool(c.antes) and all(v is not None for v in c.antes.values()) \
        and not c.descripcion.startswith("Deshacer:")


def historial(db: Session, atleta_id: int, limite: int = 100) -> list[Cambio]:
    return list(db.scalars(select(Cambio).where(Cambio.atleta_id == atleta_id)
                           .order_by(Cambio.fecha.desc(), Cambio.id.desc()).limit(limite)))


def nombre_de(db: Session, usuario_id: int | None) -> str:
    if usuario_id is None:
        return "El sistema"
    u = db.get(Usuario, usuario_id)
    return (u.apodo or u.correo.split("@")[0]) if u else "Alguien"


def autor_texto(db: Session, c: Cambio) -> str:
    if c.via == "sistema":
        return "Sistema"
    if c.via == "ia":
        return "Tu IA" if c.autor_id == c.atleta_id else f"La IA de {nombre_de(db, c.autor_id)}"
    return "Tú" if c.autor_id == c.atleta_id else nombre_de(db, c.autor_id)


def avisos_de(db: Session, atleta_id: int) -> list[dict]:
    """Cambios del coach o de la IA que el atleta aún no marca como vistos y siguen vigentes (para el banner del dashboard)."""
    filas = db.scalars(select(Cambio).where(Cambio.atleta_id == atleta_id, Cambio.visto.is_(False),
                                            Cambio.via.in_(("coach", "ia")), Cambio.deshecho_por.is_(None))
                       .order_by(Cambio.fecha.desc(), Cambio.id.desc()).limit(MAX_AVISOS))
    out = []
    for c in filas:
        quien = "Tu IA" if c.via == "ia" and c.autor_id == atleta_id else (
            f"La IA de {nombre_de(db, c.autor_id)}" if c.via == "ia" else nombre_de(db, c.autor_id))
        out.append({"id": c.id, "texto": f"{quien} cambió: {c.descripcion}", "fecha": c.fecha.date().isoformat(),
                    "url": "/historial"})
    return out


def marcar_vistos(db: Session, atleta_id: int, cambio_id: int | None = None) -> None:
    for c in db.scalars(select(Cambio).where(Cambio.atleta_id == atleta_id, Cambio.visto.is_(False))):
        if cambio_id is None or c.id == cambio_id:
            c.visto = True
    db.commit()
