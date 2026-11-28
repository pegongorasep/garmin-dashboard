"""Arma el `data.json` de una persona con el motor (dashboard/build.py) a partir de lo guardado en la base."""
import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from dashboard import build
from dashboard import i18n
from dashboard import validar
from dashboard.ajustes import normalizar_config

from . import cambios, datos, manual, plan_vivo, primer_inicio, tubo
from .modelos import ActividadManual, Ajustes, CacheData, DatoGarmin, InBody, MiembroGrupo, Plan, Usuario, ahora

log = logging.getLogger("web.calculo")
MINUTOS_CACHE = 30


def menu_de(idioma: str = "es") -> list[dict]:
    """Lo que pinta el JS junto al ?; el plan vive en la pestaña Plan."""
    return [{"texto": i18n.t(f"web.menu.{k}", idioma), "url": u} for k, u in
            (("ajustes", "/ajustes"), ("historial", "/historial"), ("inbody", "/cuerpo"),
             ("coach", "/coach"), ("aprende", "/aprende"), ("privacidad", "/privacidad"), ("salir", "/salir"))]


def plan_acciones(idioma: str = "es") -> list[dict]:
    """Botones de la pestaña Plan (ui.plan_acciones): llevan a los formularios del plan vivo."""
    return [{"texto": i18n.t(f"web.accion.{k}", idioma), "url": u} for k, u in
            (("viaje", "/plan/acciones#viaje"), ("enfermo", "/plan/acciones#enfermo"),
             ("carrera", "/plan/acciones#carrera"), ("repetir", "/plan/acciones"))]


PLAN_URL = "/plan"   # la página del plan (ajustes en el camino, eventos, rehacer): botón «Ajustar mi plan»
MENU = menu_de("es")
PLAN_ACCIONES = plan_acciones("es")


class SinConfig(Exception):
    """La persona todavía no tiene ajustes (no terminó el onboarding)."""


class DataInvalido(Exception):
    """El data.json calculado no pasó la lista blanca: no se sirve."""


def acciones_url(usuario: Usuario) -> str | None:
    return f"https://github.com/{usuario.repo}/actions/workflows/deploy.yml" if usuario.repo else None


def config_de(db: Session, usuario: Usuario, menu: list | None = None, idioma: str | None = None, crudo_nuevo: dict | None = None) -> dict:
    """Config de la persona; `crudo_nuevo` (una propuesta) sustituye a los ajustes guardados."""
    aj = db.get(Ajustes, usuario.id)
    idioma = idioma or usuario.idioma or "es"
    # sin ajustes (nadie los tiene al registrarse): el motor usa los de fábrica y la persona queda sin plan, con o sin copia
    base = crudo_nuevo if crudo_nuevo is not None else aj.config if aj else {"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}}   # los de fábrica (config_por_defecto)
    crudo = {**base, "menu": menu_de(idioma) if menu is None else menu,
             "plan_acciones": plan_acciones(idioma), "idioma": idioma}
    if aj is not None and not usuario.sin_plan:
        crudo["plan_url"] = PLAN_URL
    if crudo.get("inbody", True):   # InBody activo: botón «Agregar medición» en Progreso > Cuerpo
        crudo["cuerpo_nuevo"] = "/cuerpo/nuevo"
    if not (crudo.get("perfil") or {}).get("sensor"):   # el sensor vive en los ajustes; el onboarding lo dejó en el usuario
        crudo["perfil"] = {**(crudo.get("perfil") or {}), "sensor": usuario.sensor or "banda"}
    if acciones_url(usuario):
        crudo["acciones_url"] = acciones_url(usuario)
    crudo["sin_plan"] = bool(usuario.sin_plan) or aj is None
    return normalizar_config(crudo)


def editar_urls(plan: dict) -> dict:
    """{"<n>/<id>": url} de las sesiones que el editor acepta (el que ve su data.json puede editar: puede_editar == puede_ver)."""
    return {f"{w['n']}/{s['id']}": f"/plan/sesion/{w['n']}/{s['id']}"
            for w in plan.get("weeks", []) for s in w.get("sessions", []) if s.get("tipo") in plan_vivo.TIPOS_EDITABLES}


def inbody_de(db: Session, usuario_id: int, crudo: dict) -> dict | None:
    filas = list(db.scalars(select(InBody).where(InBody.usuario_id == usuario_id).order_by(InBody.fecha)))
    # el motor necesita peso, músculo y % de grasa: una medición que solo trae el peso se guarda pero aún no se muestra
    filas = [f for f in filas if all(f.valores.get(k) is not None for k in ("peso_kg", "mme_kg", "pgc"))]
    if not filas:
        return None
    # `prime` (la mejor medición) puede guardarse en los ajustes crudos; si no, el motor toma la de menor % de grasa
    return {"nota": crudo.get("inbody_nota"), "prime": crudo.get("inbody_prime"),
            "mediciones": [f.valores for f in filas]}


def datos_de(db: Session, usuario: Usuario, crudo: dict | None = None) -> dict:
    """El mismo dict que `build.load_data`, desde `datos_garmin` + `inbody`."""
    d = datos.leer_archivos(db, usuario.id)
    a_mano = manual.de_persona(db, usuario.id)
    if a_mano:   # a mano: entran con la forma de Garmin (sin la nota); el esfuerzo va como `rpe` en sus detalles
        d["activities"] = sorted([*d["activities"], *(manual.a_actividad(f) for f in a_mano)],
                                 key=lambda a: (a.get("startTimeLocal") or "", str(a.get("id") or "")), reverse=True)
        d["details"] = {**d["details"], **{f"m{f.id}": x for f in a_mano if (x := manual.detalle_de(f))}}
    d["inbody"] = inbody_de(db, usuario.id, crudo if crudo is not None else (db.get(Ajustes, usuario.id).config))
    return d


def plan_de(db: Session, usuario: Usuario) -> dict:
    p = db.get(Plan, usuario.id)
    return p.plan if p else build.load(build.ROOT / "plan" / "plan.example.json")


def _huella_codigo() -> str:
    """Huella del código del motor: si cambia (un deploy), el data.json guardado en caché deja de valer."""
    h = hashlib.sha256()
    for carpeta in ("dashboard", "plan", "i18n"):
        for f in sorted((build.ROOT / carpeta).glob("*")):
            if f.is_file() and f.suffix in (".py", ".csv", ".yaml", ".json"):
                h.update(f.name.encode() + f.read_bytes())
    return h.hexdigest()[:16]


CODIGO = _huella_codigo()


def huella(db: Session, usuario: Usuario, hoy_local: str, idioma: str = "es") -> str:
    n, ultimo = db.execute(select(func.count(DatoGarmin.id), func.max(DatoGarmin.actualizado))
                           .where(DatoGarmin.usuario_id == usuario.id)).one()
    man = db.execute(select(func.count(ActividadManual.id), func.max(ActividadManual.actualizada))
                     .where(ActividadManual.usuario_id == usuario.id)).one()
    aj, pl = db.get(Ajustes, usuario.id), db.get(Plan, usuario.id)
    ib = db.execute(select(func.count(InBody.id), func.max(InBody.actualizado)).where(InBody.usuario_id == usuario.id)).one()
    partes = [hoy_local, idioma, json.dumps([menu_de(idioma), plan_acciones(idioma), PLAN_URL]), n, str(ultimo), aj.version if aj else 0, str(aj.actualizado) if aj else "",
              pl.version if pl else 0, str(pl.actualizado) if pl else "", tuple(map(str, ib)),
              usuario.repo, usuario.repo_id, usuario.historial_pendiente, str(tubo.ultima_subida(db, usuario.id)), usuario.sensor, bool(usuario.sin_plan), CODIGO, tuple(map(str, man))]
    return hashlib.sha256(json.dumps(partes, default=str).encode()).hexdigest()


HORAS_SIN_SUBIR = 24
LIGA_KEY = "https://connect.garmin.com/app/settings/personalApiToken"


def estado_repo(db: Session, usuario: Usuario, ahora_utc: datetime, idioma: str = "es") -> dict | None:
    """Aviso para quien tiene repo vinculado y lleva más de 24 h sin subir (o nunca ha subido). Nada si no está vinculado."""
    if not usuario.repo_id:
        return None
    ultima = tubo.ultima_subida(db, usuario.id)
    if ultima and ahora_utc - ultima < timedelta(hours=HORAS_SIN_SUBIR):
        return None
    cuando = (i18n.t("web.repo.nunca", idioma) if ultima is None else
              i18n.t("web.repo.hace", idioma, h=int((ahora_utc - ultima).total_seconds() // 3600)))
    return {"texto": i18n.t("web.repo.aviso", idioma, cuando=cuando),
            "ligas": [{"texto": i18n.t("web.repo.actions", idioma), "url": f"https://github.com/{usuario.repo}/actions"},
                      {"texto": i18n.t("web.repo.key", idioma), "url": LIGA_KEY}]}


PREFIJABLES = ("/ajustes", "/historial", "/cuerpo", "/plan")   # rutas que existen también bajo /a/<id>


def con_prefijo(salida: dict, pref: str) -> dict:
    """Cuando el coach ve a su atleta: las ligas de edición, el menú y los avisos llevan /a/<id>. Sin Coach en el menú."""
    def f(url):
        return pref + url if isinstance(url, str) and url.startswith(PREFIJABLES) else url
    ui = salida["ui"]
    ui = {**ui, "menu": [{**m, "url": f(m["url"])} for m in ui.get("menu") or [] if m["url"] != "/coach"],
          "plan_acciones": [{**a, "url": f(a["url"])} for a in ui.get("plan_acciones") or []],
          "plan_url": f(ui.get("plan_url")), "repetir_url": f(ui.get("repetir_url")),
          "propuesta_url": f(ui.get("propuesta_url")), "plan_nuevo_url": f(ui.get("plan_nuevo_url")), "retomar_url": f(ui.get("retomar_url")),
          "editar_urls": {k: f(v) for k, v in (ui.get("editar_urls") or {}).items()}}
    if ui.get("cuerpo_nuevo"):
        ui["cuerpo_nuevo"] = f(ui["cuerpo_nuevo"])
    out = {**salida, "ui": ui}
    if out.get("avisos"):
        out["avisos"] = [{**a, "url": f(a.get("url"))} for a in out["avisos"]]
    return out


def editar_manual(db: Session, usuario: Usuario, pref: str = "", editable: bool = True) -> dict:
    """{"m<id>": ruta} para editar cada actividad a mano; vacío si quien mira no puede editar (un coach sin permiso). Sin la nota."""
    if pref and not editable:
        return {}
    return {f"m{f.id}": f"{pref}/actividad/{f.id}" for f in manual.de_persona(db, usuario.id)}


def contar_grupos(db: Session, usuario: Usuario, pref: str = "") -> int:
    """Cuántos grupos tiene la persona; 0 cuando un coach ve a su atleta (no se le muestra)."""
    if pref:
        return 0
    return db.scalar(select(func.count()).select_from(MiembroGrupo).where(MiembroGrupo.usuario_id == usuario.id)) or 0


def calcular(db: Session, usuario: Usuario, ahora_utc: datetime | None = None, pref: str = "", idioma: str | None = None,
             sync: dict | None = None, editable: bool = True) -> dict:
    """data.json de la persona (con el aviso de repo atrasado, que no se guarda en la caché porque depende de la hora).
    Truena con SinConfig o DataInvalido."""
    base = _calcular_cacheado(db, usuario, ahora_utc, idioma)
    ahora_naive = ahora_utc or ahora()
    # `grupos` también va fuera de la caché: la huella no cuenta las membresías. Al coach que ve a su atleta no se le muestra.
    n_grupos = contar_grupos(db, usuario, pref)
    # `coach`: solo cuando un coach ve a su atleta, con el mismo nombre que le muestra su página de atletas (nada más).
    coach = {"nombre": usuario.apodo or usuario.correo, "volver": "/coach"} if pref else None
    salida = {**base, "ui": {**base["ui"], "repo_estado": estado_repo(db, usuario, ahora_naive, base.get("idioma") or "es"),
                             "grupos": n_grupos, "coach": coach, "editar_manual": editar_manual(db, usuario, pref, editable), "primer_inicio": primer_inicio.de(db, usuario, pref, editable),
                             **({"sync": sync} if sync is not None and not pref else {})}}
    recordatorio = None
    if editable and not usuario.repo_id:
        cfg = config_de(db, usuario, idioma=idioma)
        fecha = ahora_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"])).date().isoformat()
        recordatorio = {"fecha": fecha, "url": f"{pref}/actividad/nueva?tipo=correr&fecha={fecha}"}
    salida["ui"]["recordatorio_corrida"] = recordatorio
    salida["ui"].update(_ui_saltos(db, usuario, salida["ui"], ahora_naive, idioma, editable))
    # También fuera de la caché: se van al marcarlos vistos. El coach no los ve: son del atleta y siguen pendientes.
    avisos = [] if pref else cambios.avisos_de(db, usuario.id)
    if avisos:
        salida["avisos"] = avisos
    problemas = validar.problemas(salida)
    if problemas:
        log.error("data.json de usuario %s no cumple la lista blanca: %s", usuario.id, problemas)
        raise DataInvalido(problemas)
    return con_prefijo(salida, pref) if pref else salida


def _ui_saltos(db: Session, usuario: Usuario, ui: dict, ahora_naive: datetime, idioma: str | None, editable: bool) -> dict:
    """«Repetir o retomar»: las ligas y las semanas 1..N-1 con sus fechas (según la secuencia actual). Vacío sin semana en curso,
    sin plan o si quien mira no puede editar. Va fuera de la caché: depende de hoy y de quién mira."""
    vacio = {"propuesta_url": None, "plan_nuevo_url": None, "retomar_url": None, "retomar_opciones": []}
    if not editable or not ui.get("repetir_url"):
        return vacio
    cfg = config_de(db, usuario, idioma=idioma)
    hoy = ahora_naive.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"])).date()
    cfg = plan_vivo.con_pausas(cfg, hoy)
    inicio = date.fromisoformat(cfg["plan_start"])
    sec = build.m.secuencia_de(cfg)
    i = (hoy - inicio).days // 7
    n = sec[i] if 0 <= i < len(sec) else None
    if n is None:
        return vacio
    ligas = {"propuesta_url": "/plan/propuesta.json", "plan_nuevo_url": "/plan/nuevo", "retomar_url": "/plan/retomar"}
    opciones = []
    for x in range(1, n):
        j = next((k for k in range(i) if sec[k] == x), None)
        if j is not None:
            d = inicio + timedelta(weeks=j)
            opciones.append({"semana": x, "desde": d.isoformat(), "hasta": (d + timedelta(days=6)).isoformat()})
    return {**ligas, "retomar_opciones": opciones}


def _calcular_cacheado(db: Session, usuario: Usuario, ahora_utc: datetime | None = None, idioma: str | None = None) -> dict:
    """De la caché si la huella no cambió y tiene menos de 30 min; si no, recalcula.
    Con AHI_SIN_CACHE (la web local, `./run_web.sh`) ni la lee ni la escribe: la huella no cubre web/, así que verías datos
    viejos y producción podría servir los calculados con código a medias."""
    cfg = config_de(db, usuario, idioma=idioma)
    idioma = cfg["idioma"]   # el de la petición, o el de la cuenta, o es: la caché lo lleva en su huella
    tz = ZoneInfo(cfg["timezone"])
    local = (ahora_utc.replace(tzinfo=ZoneInfo("UTC")) if ahora_utc else datetime.now(ZoneInfo("UTC"))).astimezone(tz)
    if os.environ.get("AHI_SIN_CACHE"):
        aj = db.get(Ajustes, usuario.id)
        return _armar(db, usuario, aj.config if aj else {}, cfg, local, bool(aj))
    h = huella(db, usuario, local.date().isoformat(), idioma)
    cache = db.get(CacheData, usuario.id)
    if cache and cache.huella == h and ahora() - cache.calculado < timedelta(minutes=MINUTOS_CACHE):
        return cache.contenido
    aj = db.get(Ajustes, usuario.id)
    salida = _armar(db, usuario, aj.config if aj else {}, cfg, local, bool(aj))
    if cache is None:
        db.add(CacheData(usuario_id=usuario.id, contenido=salida, huella=h))
    else:
        cache.contenido, cache.huella, cache.calculado = salida, h, ahora()
    db.commit()
    return salida


def calcular_propuesta(db: Session, usuario: Usuario, crudo_nuevo: dict, ahora_utc: datetime | None = None, idioma: str | None = None,
                       plan: dict | None = None, editable: bool = True) -> dict:
    """data.json que tendría la persona con `crudo_nuevo` en lugar de sus ajustes: no lee ni escribe la caché ni la base.
    Con `plan` (uno propuesto, sin guardar) se usa ese en vez del guardado y la persona cuenta como con plan; `editable=False` quita las ligas de editar."""
    cfg = config_de(db, usuario, idioma=idioma, crudo_nuevo=crudo_nuevo)
    if plan is not None:
        cfg = {**cfg, "sin_plan": False}
    local = (ahora_utc.replace(tzinfo=ZoneInfo("UTC")) if ahora_utc else datetime.now(ZoneInfo("UTC"))).astimezone(ZoneInfo(cfg["timezone"]))
    return _armar(db, usuario, crudo_nuevo, cfg, local, editable, plan)


def _armar(db: Session, usuario: Usuario, crudo: dict, cfg: dict, local: datetime, con_ajustes: bool, plan_propuesto: dict | None = None) -> dict:
    """El motor con la config y el plan (más los datos) de la persona; pasa por la lista blanca. Compartido por la caché y la propuesta."""
    cfg = plan_vivo.con_pausas(cfg, local.date())
    if cfg["sin_plan"]:   # sin plan: el motor corre con un plan vacío (nadie edita sesiones que no hay)
        plan = {"start": cfg["plan_start"], "weeks": []}
    else:
        plan = plan_vivo.plan_efectivo(plan_propuesto if plan_propuesto is not None else plan_de(db, usuario), cfg)
    ultima = tubo.ultima_subida(db, usuario.id)
    cfg = {**cfg, "editar_urls": editar_urls(plan) if con_ajustes else {},
           "garmin_conectado": bool(usuario.repo_id), "garmin_ultima_subida": ultima if usuario.repo_id else None,
           "garmin_historial_pendiente": bool(usuario.historial_pendiente)}
    salida = build.build(datos_de(db, usuario, crudo), plan, cfg, local)
    problemas = validar.problemas(salida)
    if problemas:
        log.error("data.json de usuario %s no cumple la lista blanca: %s", usuario.id, problemas)
        raise DataInvalido(problemas)
    return salida
