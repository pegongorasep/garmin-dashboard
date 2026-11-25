"""Carga los archivos personales de una carpeta (config.yaml, plan/plan.json, plan/inbody.json, data/) a la base."""
import json
from pathlib import Path

from sqlalchemy.orm import Session

import paquete
from ajustes import leer_config_yaml, normalizar_config

from . import cambios, datos
from .modelos import Usuario


def _json_puro(o):
    """Los YAML traen fechas (date): a texto, que es lo que `normalizar_config` acepta."""
    return json.loads(json.dumps(o, default=str))


def importar_carpeta(db: Session, usuario: Usuario, carpeta, salt: str = "importar") -> dict:
    """config.yaml -> `ajustes` (crudo), plan.json -> `planes`, inbody.json -> `inbody`, data/ -> paquete -> `datos_garmin`.
    Lo que falte en la carpeta se salta. `salt` debe ser el de su repo (GITHUB_REPOSITORY_ID) para que los ids de las
    actividades coincidan con los de las subidas futuras."""
    c = Path(carpeta)
    hecho, nuevo = {}, {}
    if (c / "config.yaml").exists():
        crudo = leer_config_yaml(c / "config.yaml")
        inbody = None
        if (c / "plan" / "inbody.json").exists():
            inbody = json.loads((c / "plan" / "inbody.json").read_text())
            crudo = {**crudo, **({"inbody_prime": inbody["prime"]} if inbody.get("prime") else {}),
                     **({"inbody_nota": inbody["nota"]} if inbody.get("nota") else {})}
        normalizar_config(crudo)   # que truene aquí si el config no vale
        nuevo["ajustes"] = _json_puro(crudo)
        hecho["ajustes"] = True
        if inbody:
            nuevo["inbody"] = list(inbody.get("mediciones") or [])
            hecho["inbody"] = len(nuevo["inbody"])
    if (c / "plan" / "plan.json").exists():
        nuevo["plan"] = json.loads((c / "plan" / "plan.json").read_text())
        hecho["plan"] = True
    if nuevo:   # como todo lo que escribe ajustes, plan o InBody: con historial
        cambios.aplicar_cambio(db, usuario, None, "sistema", "Importado desde los archivos personales", nuevo)
    if (c / "data").exists():
        pq = paquete.armar(c / "data", salt)
        problemas = paquete.validar(pq)
        if problemas:
            raise ValueError("el paquete no es válido: " + "; ".join(problemas))
        hecho["datos"] = datos.guardar_paquete(db, usuario.id, pq)
    return hecho
