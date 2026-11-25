"""Carga los archivos personales de una carpeta (config.yaml, plan/plan.json, plan/inbody.json, data/) a la base."""
import json
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

import paquete
from ajustes import leer_config_yaml, normalizar_config

from . import datos
from .modelos import Ajustes, InBody, Plan, Usuario, ahora


def _json_puro(o):
    """Los YAML traen fechas (date): a texto, que es lo que `normalizar_config` acepta."""
    return json.loads(json.dumps(o, default=str))


def guardar_ajustes(db: Session, usuario_id: int, crudo: dict) -> None:
    crudo = _json_puro(crudo)
    fila = db.get(Ajustes, usuario_id)
    if fila is None:
        db.add(Ajustes(usuario_id=usuario_id, config=crudo))
    else:
        fila.config, fila.version, fila.actualizado = crudo, fila.version + 1, ahora()
    db.commit()


def guardar_plan(db: Session, usuario_id: int, plan: dict) -> None:
    fila = db.get(Plan, usuario_id)
    if fila is None:
        db.add(Plan(usuario_id=usuario_id, plan=plan))
    else:
        fila.plan, fila.version, fila.actualizado = plan, fila.version + 1, ahora()
    db.commit()


def importar_carpeta(db: Session, usuario: Usuario, carpeta, salt: str = "importar") -> dict:
    """config.yaml -> `ajustes` (crudo), plan.json -> `planes`, inbody.json -> `inbody`, data/ -> paquete -> `datos_garmin`.
    Lo que falte en la carpeta se salta. `salt` debe ser el de su repo (GITHUB_REPOSITORY_ID) para que los ids de las
    actividades coincidan con los de las subidas futuras."""
    c = Path(carpeta)
    hecho = {}
    if (c / "config.yaml").exists():
        crudo = leer_config_yaml(c / "config.yaml")
        inbody = None
        if (c / "plan" / "inbody.json").exists():
            inbody = json.loads((c / "plan" / "inbody.json").read_text())
            crudo = {**crudo, **({"inbody_prime": inbody["prime"]} if inbody.get("prime") else {}),
                     **({"inbody_nota": inbody["nota"]} if inbody.get("nota") else {})}
        normalizar_config(crudo)   # que truene aquí si el config no vale
        guardar_ajustes(db, usuario.id, crudo)
        hecho["ajustes"] = True
        if inbody:
            db.execute(delete(InBody).where(InBody.usuario_id == usuario.id))
            for med in inbody.get("mediciones") or []:
                db.add(InBody(usuario_id=usuario.id, fecha=med["fecha"], valores=med))
            db.commit()
            hecho["inbody"] = len(inbody.get("mediciones") or [])
    if (c / "plan" / "plan.json").exists():
        guardar_plan(db, usuario.id, json.loads((c / "plan" / "plan.json").read_text()))
        hecho["plan"] = True
    if (c / "data").exists():
        pq = paquete.armar(c / "data", salt)
        problemas = paquete.validar(pq)
        if problemas:
            raise ValueError("el paquete no es válido: " + "; ".join(problemas))
        hecho["datos"] = datos.guardar_paquete(db, usuario.id, pq)
    return hecho
