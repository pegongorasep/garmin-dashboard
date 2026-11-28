"""Historial de cambios. TODA escritura a `ajustes`, `planes` o `inbody` pasa por `aplicar_cambio`: guarda quién, por qué
vía y el antes/después, y permite deshacer (el `antes` se aplica como un cambio nuevo)."""
import copy
from datetime import date, timedelta
from zoneinfo import ZoneInfo

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
            u = db.get(Usuario, atleta_id)
            if u is not None:
                u.sin_plan = False   # quien guarda ajustes de entreno tiene plan
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


def aplicar_cambio(db: Session, atleta: Usuario, autor: Usuario | None, via: str, descripcion: str, nuevo: dict,
                   nota: str | None = None) -> Cambio:
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
                    antes=antes, despues=despues, nota=(nota or "").strip() or None, visto=propio or via == "sistema")
    db.add(cambio)
    db.commit()
    return cambio


def via_de(actor: Usuario, atleta: Usuario) -> str:
    return "web" if actor.id == atleta.id else "coach"


def _saltos(ajustes) -> list:
    return ((ajustes or {}).get("corrida") or {}).get("saltos") or []


def _lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _salto_fijo(c: Cambio, actuales: dict | None, hoy: date | None) -> bool:
    """True si deshacer `c` cambiaría los saltos (repetir / retomar) y ya pasó la semana en que se hizo (lunes a domingo,
    en la zona horaria de la persona). `hoy` es la fecha local de la persona; sin ella no se limita (uso de sistema)."""
    if hoy is None or "ajustes" not in (c.antes or {}):
        return False
    if _saltos(c.antes["ajustes"]) == _saltos(actuales):
        return False
    tz = ZoneInfo(((actuales or {}).get("perfil") or {}).get("zona_horaria") or "America/Merida")
    hecho = c.fecha.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).date()
    return _lunes(hecho) != _lunes(hoy)


def _actuales(db: Session, atleta_id: int) -> dict | None:
    fila = db.get(Ajustes, atleta_id)
    return fila.config if fila else None


def deshacer(db: Session, actor: Usuario, cambio_id: int, via: str | None = None, hoy: date | None = None,
             nota: str | None = None) -> Cambio:
    """Aplica el `antes` de un cambio como un cambio nuevo y marca el original. Truena con SinPermiso (el actor no puede
    editar a ese atleta o el cambio no existe: se trata igual para no confirmar nada) o NoSeDeshace. `hoy` (fecha local de
    la persona) activa la regla de que repetir / retomar solo se deshace la misma semana."""
    c = db.get(Cambio, cambio_id)
    if c is None or not puede_editar(db, actor, c.atleta_id):
        raise SinPermiso()
    if c.deshecho_por is not None:
        raise NoSeDeshace("err.ya_deshecho")
    if _visto_de_ia(c):
        raise NoSeDeshace("err.visto")
    if not c.antes or any(v is None for v in c.antes.values()):
        raise NoSeDeshace("err.creado")
    if _salto_fijo(c, _actuales(db, c.atleta_id), hoy):
        raise NoSeDeshace("err.salto_fijo")
    if not orden_ok(c, instantanea(db, c.atleta_id, areas(c))):
        raise NoSeDeshace("err.orden_deshacer")
    atleta = db.get(Usuario, c.atleta_id)
    nuevo = aplicar_cambio(db, atleta, actor, via or via_de(actor, atleta), f"Deshacer: {c.descripcion}", c.antes, nota=nota)
    c.deshecho_por, c.visto = nuevo.id, True
    db.commit()
    return nuevo


def _visto_de_ia(c: Cambio) -> bool:
    """Un cambio de la IA o del coach que la persona ya marcó como visto («Entendido») se queda."""
    return c.via in ("ia", "coach") and bool(c.visto)


def areas(c: Cambio) -> list[str]:
    """Las áreas (plan, ajustes, inbody) que tocó un cambio: las claves de su `despues`."""
    return [k for k in CAMPOS if k in (c.despues or {})]


def _igual(area: str, a, b) -> bool:
    if area == "inbody":   # la lista se guarda ordenada por fecha; el orden en que se mandó no cuenta
        a, b = [sorted(x or [], key=lambda m: str(m.get("fecha"))) for x in (a, b)]
    return a == b


def orden_ok(c: Cambio, snaps: dict) -> bool:
    """Regla de orden para deshacer: lo guardado hoy de cada área que tocó es justo lo que dejó este cambio.
    `snaps`: `instantanea` actual del atleta (al menos de las áreas del cambio)."""
    return all(_igual(a, snaps.get(a), c.despues[a]) for a in areas(c))


def puede_deshacer(c: Cambio, actuales: dict | None = None, hoy: date | None = None, snaps: dict | None = None) -> bool:
    """`actuales`: los ajustes crudos de hoy del atleta; `hoy`: su fecha local (regla de los saltos); `snaps`: la
    instantánea actual de las tres áreas (regla de orden; sin ella no se revisa el orden)."""
    return puede_deshacer_base(c, actuales, hoy) and (snaps is None or orden_ok(c, snaps))


def puede_deshacer_base(c: Cambio, actuales: dict | None = None, hoy: date | None = None) -> bool:
    """Las reglas de deshacer que no dependen del orden."""
    return c.deshecho_por is None and not _visto_de_ia(c) and bool(c.antes) and all(v is not None for v in c.antes.values()) \
        and not c.descripcion.startswith("Deshacer:") and not _salto_fijo(c, actuales, hoy)


def pendientes_de(db: Session, atleta_id: int) -> list[Cambio]:
    """Cambios de la IA o del coach sin aceptar ni deshacer, del más viejo al más nuevo."""
    return list(db.scalars(select(Cambio).where(Cambio.atleta_id == atleta_id, Cambio.visto.is_(False),
                                                Cambio.via.in_(("coach", "ia")), Cambio.deshecho_por.is_(None))
                           .order_by(Cambio.fecha, Cambio.id)))


def es_pendiente(c: Cambio) -> bool:
    return c.via in ("ia", "coach") and not c.visto and c.deshecho_por is None


def puede_aceptar(c: Cambio, pendientes: list[Cambio]) -> bool:
    """Solo el pendiente más viejo de cada una de sus áreas. `pendientes`: de `pendientes_de`."""
    if not es_pendiente(c):
        return False
    mias = set(areas(c))
    return not any((p.fecha, p.id) < (c.fecha, c.id) and mias & set(areas(p)) for p in pendientes if p.id != c.id)


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
    """Cambios del coach o de la IA que el atleta aún no marca como vistos y siguen vigentes (para el banner del dashboard).
    `cerrable` (solo si es verdad): un cambio que solo toca InBody y se puede aceptar ya (la ✕ del banner)."""
    import i18n
    pend = pendientes_de(db, atleta_id)
    out = []
    for c in list(reversed(pend))[:MAX_AVISOS]:
        quien = "Tu IA" if c.via == "ia" and c.autor_id == atleta_id else (
            f"La IA de {nombre_de(db, c.autor_id)}" if c.via == "ia" else nombre_de(db, c.autor_id))
        que = [i18n.t(f"cambios.de_{k}", "es") for k in areas(c)]
        aviso = {"id": c.id, "texto": i18n.t("cambios.aviso", "es", quien=quien, que=" y ".join(que) or i18n.t("cambios.de_algo", "es")),
                 "fecha": c.fecha.date().isoformat(), "url": f"/historial#c{c.id}"}
        if areas(c) == ["inbody"] and puede_aceptar(c, pend):
            aviso["cerrable"] = True
        out.append(aviso)
    return out


def aceptar(db: Session, atleta_id: int, cambio_id: int) -> bool:
    """«Entendido» a un solo cambio, solo si le toca (el pendiente más viejo de sus áreas). False si no se marcó."""
    c = db.get(Cambio, cambio_id)
    if c is None or c.atleta_id != atleta_id or not puede_aceptar(c, pendientes_de(db, atleta_id)):
        return False
    c.visto = True
    db.commit()
    return True


def marcar_vistos(db: Session, atleta_id: int, cambio_id: int | None = None) -> None:
    for c in db.scalars(select(Cambio).where(Cambio.atleta_id == atleta_id, Cambio.visto.is_(False))):
        if cambio_id is None or c.id == cambio_id:
            c.visto = True
    db.commit()


# --- resumen en palabras (antes -> después) ---

MAX_LINEAS = 6
ETIQ_AJUSTE = {"perfil.titulo": "el título", "perfil.zona_horaria": "la zona horaria", "perfil.edad": "la edad",
               "perfil.fc_max": "la FC máxima", "perfil.sensor": "el sensor", "inbody": "InBody",
               "corrida.inicio": "el inicio del plan", "corrida.nivel": "el nivel", "corrida.dias": "los días de corrida"}
ETIQ_CAMPO = {"peso_kg": "peso (kg)", "mme_kg": "masa muscular (kg)", "pgc": "% de grasa", "grasa_kg": "grasa (kg)"}
NOMBRE_PASO = {"run": "trote", "walk": "caminata"}


def _pasos_texto(pasos) -> str:
    out = []
    for p in pasos or []:
        if p.get("kind") == "repeat":
            out.append(f"{p.get('times')}× ({_pasos_texto(p.get('steps'))})")
        else:
            out.append(f"{NOMBRE_PASO.get(p.get('kind'), p.get('kind'))} {p.get('minutes')}' {p.get('zone')}")
    return ", ".join(out)


def _valor(v) -> str:
    if v is None or v == "":
        return "vacío"
    if v is True:
        return "sí"
    if v is False:
        return "no"
    if isinstance(v, list):
        return f"{len(v)} elementos"
    return str(v)


def _sesiones(plan) -> dict:
    return {(w.get("n"), s.get("id")): s for w in (plan or {}).get("weeks") or [] for s in w.get("sessions") or []}


def _resumen_plan(antes, despues) -> list[str]:
    a, b = _sesiones(antes), _sesiones(despues)
    out = []
    for k in sorted(set(a) | set(b), key=lambda x: (x[0] or 0, str(x[1]))):
        sa, sb = a.get(k), b.get(k)
        pref = f"Semana {k[0]} · {(sb or sa).get('name') or 'sesión'}"
        if sa is None:
            out.append(f"{pref}: se agregó")
        elif sb is None:
            out.append(f"{pref}: se quitó")
        else:
            if sa.get("name") != sb.get("name"):
                out.append(f"Semana {k[0]} · nombre: {sa.get('name')} → {sb.get('name')}")
            if sa.get("minutes") != sb.get("minutes"):
                out.append(f"{pref}: minutos {sa.get('minutes')} → {sb.get('minutes')}")
            if sa.get("tipo") != sb.get("tipo"):
                out.append(f"{pref}: tipo {sa.get('tipo')} → {sb.get('tipo')}")
            if sa.get("distance_km") != sb.get("distance_km") and (sa.get("distance_km") or sb.get("distance_km")):
                out.append(f"{pref}: distancia {_valor(sa.get('distance_km'))} → {_valor(sb.get('distance_km'))} km")
            if sa.get("steps") != sb.get("steps"):
                out.append(f"{pref}: pasos {_pasos_texto(sa.get('steps'))} → {_pasos_texto(sb.get('steps'))}")
    return out


def _planas(d, pref="") -> dict:
    out = {}
    for k, v in (d or {}).items():
        ruta = f"{pref}.{k}" if pref else str(k)
        if isinstance(v, dict):
            out.update(_planas(v, ruta))
        else:
            out[ruta] = v
    return out


def _resumen_ajustes(antes, despues) -> list[str]:
    a, b = _planas(antes), _planas(despues)
    out = []
    for k in sorted(set(a) | set(b)):
        if a.get(k) != b.get(k):
            etiqueta = ETIQ_AJUSTE.get(k) or k.split(".")[-1].replace("_", " ")
            if isinstance(a.get(k), list) or isinstance(b.get(k), list):
                out.append(f"{etiqueta}: {len(a.get(k) or [])} → {len(b.get(k) or [])}")
            else:
                out.append(f"{etiqueta}: {_valor(a.get(k))} → {_valor(b.get(k))}")
    return out


def _resumen_inbody(antes, despues) -> list[str]:
    a = {m.get("fecha"): m for m in antes or []}
    b = {m.get("fecha"): m for m in despues or []}
    out = []
    for f in sorted(set(a) | set(b), key=str):
        if f not in a:
            out.append(f"InBody {f}: se agregó")
        elif f not in b:
            out.append(f"InBody {f}: se quitó")
        elif a[f] != b[f]:
            for k in sorted(set(a[f]) | set(b[f])):
                if a[f].get(k) != b[f].get(k) and k not in ("fecha", "hora"):
                    out.append(f"InBody {f} · {ETIQ_CAMPO.get(k, k)}: {_valor(a[f].get(k))} → {_valor(b[f].get(k))}")
    return out


def resumen(c: Cambio, tope: int | None = MAX_LINEAS) -> list[str]:
    """Líneas en palabras de lo que cambió (antes → después), hasta `tope` (MAX_LINEAS) con «y N más»; sin tope, todas.
    [] si no se puede resumir."""
    try:
        antes, despues = c.antes or {}, c.despues or {}
        lineas = []
        if "plan" in despues:
            lineas += _resumen_plan(antes.get("plan"), despues.get("plan"))
        if "ajustes" in despues:
            lineas += _resumen_ajustes(antes.get("ajustes"), despues.get("ajustes"))
        if "inbody" in despues:
            lineas += _resumen_inbody(antes.get("inbody"), despues.get("inbody"))
    except (AttributeError, TypeError, ValueError):
        return []
    if tope and len(lineas) > tope:
        resto = len(lineas) - (tope - 1)
        lineas = lineas[:tope - 1] + [f"y {resto} más"]
    return lineas
