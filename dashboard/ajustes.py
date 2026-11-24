"""Lee config.yaml (personal) + defaults.yaml (motor) y devuelve el dict plano que usa el código.

USER_DIR: variable de entorno GARMIN_USER_DIR si existe; si no, la raíz del repo.
De ahí salen config.yaml y plan/, y ahí se escribe data/.
"""
import os
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
USER_DIR = Path(os.environ.get("GARMIN_USER_DIR") or ROOT)
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
_DIA_IDX = {"lun": 0, "mar": 1, "mie": 2, "mié": 2, "jue": 3, "vie": 4, "sab": 5, "sáb": 5, "dom": 6}
NIVELES = ("novato", "intermedio", "corredor")
INTENSIDADES = ("solo_z2", "z2_poca_z3", "calidad")
CALIDAD_TIPOS = ("tempo_z3", "threshold", "intervalos")
MAX_CATEGORIAS = 4
CLASES = ["c1", "c2", "c3", "c4"]  # clase de color por orden de categoría


class ConfigError(ValueError):
    """Error de configuración con mensaje en español."""


def _leer_yaml(path: Path) -> dict:
    try:
        datos = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name} no es un YAML válido: {e}") from e
    return datos or {}


def _fecha(valor, campo: str) -> str:
    if isinstance(valor, date):
        return valor.isoformat()
    try:
        return date.fromisoformat(str(valor)).isoformat()
    except ValueError as e:
        raise ConfigError(f"{campo}: '{valor}' no es una fecha AAAA-MM-DD") from e


def _dia(valor, campo: str) -> int:
    clave = str(valor).strip().lower()
    if clave not in _DIA_IDX:
        raise ConfigError(f"{campo}: '{valor}' no es un día (lun, mar, mié, jue, vie, sáb, dom)")
    return _DIA_IDX[clave]


def _requerido(d: dict, clave: str, donde: str):
    if d.get(clave) in (None, ""):
        raise ConfigError(f"Falta `{clave}` en la sección `{donde}` de config.yaml")
    return d[clave]


def _categorias(brutas: list) -> list:
    if not brutas:
        raise ConfigError("`actividades.categorias` está vacía; quita la sección para usar las de por defecto")
    if len(brutas) > MAX_CATEGORIAS:
        raise ConfigError(f"Máximo {MAX_CATEGORIAS} categorías de actividad (hay {len(brutas)})")
    out, ids = [], set()
    for i, c in enumerate(brutas):
        for k in ("id", "nombre", "letra", "tipos"):
            if not c.get(k):
                raise ConfigError(f"La categoría {i + 1} no tiene `{k}`")
        if c["id"] in ids or c["id"] == "run":
            raise ConfigError(f"El id de categoría '{c['id']}' está repetido o reservado")
        ids.add(c["id"])
        out.append({"id": c["id"], "nombre": c["nombre"], "letra": c["letra"], "tipos": list(c["tipos"]),
                    "intensa": bool(c.get("intensa", False)), "clase": CLASES[i]})
    return out


def cargar_config(user_dir=None) -> dict:
    """Config plana lista para build/metrics/garmin_connect. Truena con ConfigError si falta algo."""
    user_dir = Path(user_dir) if user_dir else USER_DIR
    ruta = user_dir / "config.yaml"
    if not ruta.exists():
        raise ConfigError(f"No existe {ruta}. Corre /setup en Claude Code para crearlo "
                          "(o copia config.example.yaml como config.yaml).")
    defaults = _leer_yaml(Path(__file__).parent / "defaults.yaml")
    cfg = _leer_yaml(ruta)
    perfil, corrida = cfg.get("perfil") or {}, cfg.get("corrida") or {}
    act = cfg.get("actividades") or {}

    tz = _requerido(perfil, "zona_horaria", "perfil")
    edad, fc_max = perfil.get("edad"), perfil.get("fc_max")
    if fc_max is None and edad is None:
        raise ConfigError("Falta `fc_max` o `edad` en la sección `perfil` de config.yaml")
    max_hr = fc_max if fc_max is not None else 220 - edad
    inicio = _fecha(_requerido(corrida, "inicio", "corrida"), "corrida.inicio")
    if date.fromisoformat(inicio).weekday() != 0:
        raise ConfigError(f"corrida.inicio ({inicio}) debe ser lunes")

    nivel = corrida.get("nivel", "intermedio")
    if nivel not in NIVELES:
        raise ConfigError(f"corrida.nivel '{nivel}' no válido; usa: {', '.join(NIVELES)}")
    intensidad = corrida.get("intensidad", "z2_poca_z3")
    if intensidad not in INTENSIDADES:
        raise ConfigError(f"corrida.intensidad '{intensidad}' no válida; usa: {', '.join(INTENSIDADES)}")
    tipos_cal = list(corrida.get("calidad_tipos") or [])
    for t in tipos_cal:
        if t not in CALIDAD_TIPOS:
            raise ConfigError(f"corrida.calidad_tipos: '{t}' no válido; usa: {', '.join(CALIDAD_TIPOS)}")
    if intensidad == "calidad" and not tipos_cal:
        raise ConfigError("corrida.intensidad es `calidad` pero `calidad_tipos` está vacío")
    base = {"z2": 20, "larga": 40, **(corrida.get("base_min") or {})}

    categorias = _categorias(act.get("categorias") or defaults["categorias"])
    ids = {c["id"] for c in categorias}
    semana = {}
    for dia, cat in (act.get("semana") or {}).items():
        if cat not in ids:
            raise ConfigError(f"actividades.semana: '{cat}' no es una categoría (hay: {', '.join(sorted(ids))})")
        semana[_dia(dia, "actividades.semana")] = cat
    pierna = sorted(_dia(d, "actividades.dias_pierna") for d in act.get("dias_pierna") or [])

    umbrales = {**defaults["umbrales"], **(cfg.get("umbrales") or {})}
    desde = perfil.get("fc_max_correa_desde")
    return {
        **umbrales,
        "titulo": perfil.get("titulo") or "Base aeróbica",
        "timezone": tz, "edad": edad,
        "max_hr": max_hr, "max_hr_floor": perfil.get("fc_max_piso", max_hr),
        "fc_max_correa_desde": _fecha(desde, "perfil.fc_max_correa_desde") if desde else None,
        "plan_start": inicio, "semanas_repetidas": list(corrida.get("semanas_repetidas") or []),
        "nivel": nivel, "intensidad": intensidad, "calidad_tipos": tipos_cal,
        "caminatas": bool(corrida.get("caminatas", False)),
        "plan_semanas": int(corrida.get("semanas", 12)), "base_min": base,
        "categorias": categorias, "semana_tipica": semana, "dias_pierna": pierna,
        "inbody": bool(cfg.get("inbody", True)),
        # compatibilidad F0 (se quitan en F1)
        "crossfit_types": categorias[0]["tipos"], "strap_in_crossfit_since": desde and _fecha(desde, "x"),
        "crossfit_days": sorted(semana),
        "tipos_con_detalle": umbrales["run_types"] + [t for c in categorias for t in c["tipos"]],
    }
