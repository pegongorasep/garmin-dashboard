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

from . import datos
from .modelos import Ajustes, CacheData, DatoGarmin, InBody, Plan, Usuario, ahora

log = logging.getLogger("web.calculo")
MINUTOS_CACHE = 30
MENU = [{"texto": "Salir", "url": "/salir"}]   # lo que pinta el JS junto al ?; crece con cada fase


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
    if acciones_url(usuario):
        crudo["acciones_url"] = acciones_url(usuario)
    return normalizar_config(crudo)


def inbody_de(db: Session, usuario_id: int, crudo: dict) -> dict | None:
    filas = list(db.scalars(select(InBody).where(InBody.usuario_id == usuario_id).order_by(InBody.fecha)))
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
    partes = [hoy_local, n, str(ultimo), aj.version if aj else 0, str(aj.actualizado) if aj else "",
              pl.version if pl else 0, str(pl.actualizado) if pl else "", tuple(map(str, ib)),
              usuario.repo, usuario.sensor]
    return hashlib.sha256(json.dumps(partes, default=str).encode()).hexdigest()


def calcular(db: Session, usuario: Usuario, ahora_utc: datetime | None = None) -> dict:
    """data.json de la persona: de la caché si la huella no cambió y tiene menos de 30 min; si no, recalcula.
    Truena con SinConfig o DataInvalido."""
    cfg = config_de(db, usuario)
    tz = ZoneInfo(cfg["timezone"])
    local = (ahora_utc.replace(tzinfo=ZoneInfo("UTC")) if ahora_utc else datetime.now(ZoneInfo("UTC"))).astimezone(tz)
    h = huella(db, usuario, local.date().isoformat())
    cache = db.get(CacheData, usuario.id)
    if cache and cache.huella == h and ahora() - cache.calculado < timedelta(minutes=MINUTOS_CACHE):
        return cache.contenido
    crudo = db.get(Ajustes, usuario.id).config
    salida = build.build(datos_de(db, usuario, crudo), plan_de(db, usuario), cfg, local)
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
