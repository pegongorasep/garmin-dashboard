"""Primer inicio: lo que Hoy ofrece a quien llega sin nada. Python decide; el sitio solo pinta `ui.primer_inicio` (ver `de`).
También `ui.vacios` (los estados vacíos de las pestañas, ver `vacios`).
Va fuera de la caché de calcular (depende de grupos y avisos, no de la huella)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .modelos import ActividadManual, Ajustes, AvisoOculto, DatoGarmin, InBody, MiembroGrupo, Usuario

AVISO_GARMIN = "garmin"
# paso que se puede saltar -> aviso (`avisos_ocultos`) con el que se da por saltado; en el orden en que se ofrecen
SALTOS = {"garmin": AVISO_GARMIN, "plan": "paso_plan", "grupo": "paso_grupo", "inbody": "paso_inbody"}


def tiene_plan(db: Session, u: Usuario) -> bool:
    return db.get(Ajustes, u.id) is not None and not u.sin_plan


def garmin_saltado(db: Session, u: Usuario) -> bool:
    """Dijo «No tengo Garmin» en Hoy."""
    return db.get(AvisoOculto, (u.id, AVISO_GARMIN)) is not None


def esperando_historial(u: Usuario) -> bool:
    return bool(u.repo_id and u.historial_pendiente)


def _progreso(db: Session, u: Usuario, pref: str, editable: bool) -> dict:
    """Lo que ofrece Progreso mientras no hay ni una corrida (con corridas el sitio no lo usa). Conectar es solo de la propia persona
    y si no lo saltó; mientras llega el historial no hay botones."""
    estado = "sin_garmin" if not u.repo_id else "esperando" if esperando_historial(u) else "sin_corridas"
    conectar = "/bienvenida" if estado == "sin_garmin" and not pref and not garmin_saltado(db, u) else None
    registrar = f"{pref}/actividad/nueva" if estado != "esperando" and editable else None
    return {"estado": estado, "conectar": conectar, "registrar": registrar}


def vacios(db: Session, u: Usuario, sin_plan: bool, pref: str = "", editable: bool = True) -> dict:
    """`ui.vacios`: lo que ofrecen las pestañas fijas cuando están vacías. `pref` = "/a/<id>" cuando un coach ve a su atleta.
    plan: None con plan; si no, {estado: "sin_plan" | "esperando" (falta el historial), armar: url | None (sin botón)}.
    grupos: None al coach (sin pestaña); si no, {crear, invitar}. Que venga es lo que pone la pestaña Grupos, aun sin ningún grupo.
    progreso: {estado: "sin_garmin" | "esperando" | "sin_corridas", conectar: url | None, registrar: url | None}."""
    plan = None
    if sin_plan:
        plan = {"estado": "esperando" if esperando_historial(u) else "sin_plan",
                "armar": f"{pref}/plan/nuevo" if editable else None}
    grupos = None
    if not pref:
        ids = db.scalars(select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == u.id).limit(2)).all()
        grupos = {"crear": "/grupos/nuevo", "invitar": f"/grupos/{ids[0]}" if len(ids) == 1 else "/grupos"}   # la liga se crea en la página del grupo
    return {"plan": plan, "grupos": grupos, "progreso": _progreso(db, u, pref, editable)}


def _hay(db: Session, columna, *donde) -> bool:
    return db.scalar(select(columna).where(*donde).limit(1)) is not None


def _cumplidos(db: Session, u: Usuario) -> dict:
    return {"garmin": bool(u.repo_id), "plan": tiene_plan(db, u),
            "grupo": _hay(db, MiembroGrupo.grupo_id, MiembroGrupo.usuario_id == u.id),
            "inbody": _hay(db, InBody.id, InBody.usuario_id == u.id)}


def _barras(db: Session, u: Usuario) -> dict:
    """Los 5 primeros pasos (las 5 barras del logo). Hecho = cumplido o saltado; la cuenta siempre lo está.
    vista: "garmin" (grande: falta Garmin) | "historial" (grande: llega el historial) | "compacta" | "completa" (5 de 5:
    el sitio solo se despide si ese teléfono la vio incompleta). `siguiente`: el paso del botón, en el orden de SALTOS.
    `lista`: los demás pendientes que enlistan las vistas grandes. El plan espera mientras falte el historial.
    `llave`: con qué recuerda el teléfono cuántas barras vio de esta cuenta."""
    saltados = set(db.scalars(select(AvisoOculto.aviso_id).where(AvisoOculto.usuario_id == u.id)))
    cumplidos, espera = _cumplidos(db, u), esperando_historial(u)
    urls = {"garmin": "/bienvenida", "plan": "/plan/nuevo", "grupo": "/grupos", "inbody": "/cuerpo"}
    pasos = [{"id": "cuenta", "hecho": True, "url": None, "saltar": None},
             *({"id": p, "hecho": cumplidos[p] or aviso in saltados, "url": urls[p], "saltar": aviso} for p, aviso in SALTOS.items())]
    hechos = sum(p["hecho"] for p in pasos)
    pendientes = [p["id"] for p in pasos if not p["hecho"] and not (espera and p["id"] == "plan")]
    vista = "completa" if hechos == len(pasos) else "historial" if espera else "garmin" if "garmin" in pendientes else "compacta"
    siguiente = pendientes[0] if vista in ("garmin", "compacta") else None
    lista = [p for p in pendientes if p != siguiente] if vista in ("garmin", "historial") else []
    return {"llave": u.id, "vista": vista, "hechos": hechos, "siguiente": siguiente, "lista": lista, "pasos": pasos,
            "liga": "/bienvenida/liga", "ocultar": "/avisos/ocultar"}


def de(db: Session, u: Usuario, pref: str = "", editable: bool = True) -> dict:
    """En la cuenta propia: {registrar, sin_actividad, barras} (ver `_barras`); `sin_actividad` = ni una actividad todavía
    (Hoy sin plan esconde sus tarjetas vacías). Con `pref` = "/a/<id>" (un coach ve a su atleta): {registrar, pasos: [{id, url}]},
    la lista de lo que falta, sin Garmin ni grupos y vacía si no puede editar."""
    if not pref:
        sin_actividad = not (_hay(db, DatoGarmin.id, DatoGarmin.usuario_id == u.id, DatoGarmin.tipo == "actividad")
                             or _hay(db, ActividadManual.id, ActividadManual.usuario_id == u.id))
        return {"registrar": "/actividad/nueva", "sin_actividad": sin_actividad, "barras": _barras(db, u)}
    if not editable:
        return {"registrar": None, "pasos": []}
    cumplidos = _cumplidos(db, u)
    pasos = [{"id": p, "url": f"{pref}{ruta}"} for p, ruta in (("plan", "/plan/nuevo"), ("inbody", "/cuerpo")) if not cumplidos[p]]
    return {"registrar": f"{pref}/actividad/nueva", "pasos": pasos}
