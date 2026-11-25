"""Arma el `data.json` de una persona con el motor (dashboard/build.py) a partir de lo guardado en la base."""
import hashlib
import json
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import build
import validar
from ajustes import normalizar_config

from . import cambios, datos, plan_vivo, tubo
from .modelos import Ajustes, CacheData, DatoGarmin, InBody, Plan, Usuario, ahora

log = logging.getLogger("web.calculo")
MINUTOS_CACHE = 30
MENU = [{"texto": "Ajustes", "url": "/ajustes"}, {"texto": "Cuerpo", "url": "/cuerpo"},
        {"texto": "Historial", "url": "/historial"}, {"texto": "Privacidad", "url": "/privacidad"},
        {"texto": "Salir", "url": "/salir"}]   # lo que pinta el JS junto al ?; crece con cada fase


class SinConfig(Exception):
    """La persona todavía no tiene ajustes (no terminó el onboarding)."""


class DataInvalido(Exception):
    """El data.json calculado no pasó la lista blanca: no se sirve."""


def acciones_url(usuario: Usuario) -> str | None:
    return f"https://github.com/{usuario.repo}/actions/workflows/deploy.yml" if usuario.repo else None


def config_de(db: Session, usuario: Usuario, menu: list | None = None) -> dict:
    aj = db.get(Ajustes, usuario.id)
    if aj is None:
        raise SinConfig()
    crudo = {**aj.config, "modo": "web", "menu": MENU if menu is None else menu}
    if not (crudo.get("perfil") or {}).get("sensor"):   # el sensor vive en los ajustes; el onboarding lo dejó en el usuario
        crudo["perfil"] = {**(crudo.get("perfil") or {}), "sensor": usuario.sensor or "banda"}
    if acciones_url(usuario):
        crudo["acciones_url"] = acciones_url(usuario)
    return normalizar_config(crudo)


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
    d["inbody"] = inbody_de(db, usuario.id, crudo if crudo is not None else (db.get(Ajustes, usuario.id).config))
    return d


def plan_de(db: Session, usuario: Usuario) -> dict:
    p = db.get(Plan, usuario.id)
    return p.plan if p else build.load(build.ROOT / "plan" / "plan.example.json")


def huella(db: Session, usuario: Usuario, hoy_local: str) -> str:
    n, ultimo = db.execute(select(func.count(DatoGarmin.id), func.max(DatoGarmin.actualizado))
                           .where(DatoGarmin.usuario_id == usuario.id)).one()
    aj, pl = db.get(Ajustes, usuario.id), db.get(Plan, usuario.id)
    ib = db.execute(select(func.count(InBody.id), func.max(InBody.actualizado)).where(InBody.usuario_id == usuario.id)).one()
    partes = [hoy_local, json.dumps(MENU), n, str(ultimo), aj.version if aj else 0, str(aj.actualizado) if aj else "",
              pl.version if pl else 0, str(pl.actualizado) if pl else "", tuple(map(str, ib)),
              usuario.repo, usuario.sensor]
    return hashlib.sha256(json.dumps(partes, default=str).encode()).hexdigest()


HORAS_SIN_SUBIR = 24
LIGA_KEY = "https://connect.garmin.com/app/settings/personalApiToken"


def estado_repo(db: Session, usuario: Usuario, ahora_utc: datetime) -> dict | None:
    """Aviso para quien tiene repo vinculado y lleva más de 24 h sin subir (o nunca ha subido). Nada si no está vinculado."""
    if not usuario.repo_id:
        return None
    ultima = tubo.ultima_subida(db, usuario.id)
    if ultima and ahora_utc - ultima < timedelta(hours=HORAS_SIN_SUBIR):
        return None
    cuando = "todavía no ha mandado datos" if ultima is None else f"no manda datos desde hace {int((ahora_utc - ultima).total_seconds() // 3600)} h"
    return {"texto": f"Tu repo {cuando}: revisa que Actions esté activo o renueva tu key de Garmin.",
            "ligas": [{"texto": "Abrir Actions", "url": f"https://github.com/{usuario.repo}/actions"},
                      {"texto": "Renovar mi key de Garmin", "url": LIGA_KEY}]}


def calcular(db: Session, usuario: Usuario, ahora_utc: datetime | None = None) -> dict:
    """data.json de la persona (con el aviso de repo atrasado, que no se guarda en la caché porque depende de la hora).
    Truena con SinConfig o DataInvalido."""
    base = _calcular_cacheado(db, usuario, ahora_utc)
    ahora_naive = ahora_utc or ahora()
    salida = {**base, "ui": {**base["ui"], "repo_estado": estado_repo(db, usuario, ahora_naive)}}
    avisos = cambios.avisos_de(db, usuario.id)   # también fuera de la caché: se van al marcarlos vistos
    if avisos:
        salida["avisos"] = avisos
    problemas = validar.problemas(salida)
    if problemas:
        log.error("data.json de usuario %s no cumple la lista blanca: %s", usuario.id, problemas)
        raise DataInvalido(problemas)
    return salida


def _calcular_cacheado(db: Session, usuario: Usuario, ahora_utc: datetime | None = None) -> dict:
    """De la caché si la huella no cambió y tiene menos de 30 min; si no, recalcula."""
    cfg = config_de(db, usuario)
    tz = ZoneInfo(cfg["timezone"])
    local = (ahora_utc.replace(tzinfo=ZoneInfo("UTC")) if ahora_utc else datetime.now(ZoneInfo("UTC"))).astimezone(tz)
    h = huella(db, usuario, local.date().isoformat())
    cache = db.get(CacheData, usuario.id)
    if cache and cache.huella == h and ahora() - cache.calculado < timedelta(minutes=MINUTOS_CACHE):
        return cache.contenido
    crudo = db.get(Ajustes, usuario.id).config
    cfg = plan_vivo.con_pausas(cfg, local.date())
    plan = plan_vivo.plan_efectivo(plan_de(db, usuario), cfg)
    salida = build.build(datos_de(db, usuario, crudo), plan, cfg, local)
    problemas = validar.problemas(salida)
    if problemas:
        log.error("data.json de usuario %s no cumple la lista blanca: %s", usuario.id, problemas)
        raise DataInvalido(problemas)
    if cache is None:
        db.add(CacheData(usuario_id=usuario.id, contenido=salida, huella=h))
    else:
        cache.contenido, cache.huella, cache.calculado = salida, h, ahora()
    db.commit()
    return salida
