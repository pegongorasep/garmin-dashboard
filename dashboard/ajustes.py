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
CALIDAD_TIPOS = ("tempo_z3", "threshold", "intervalos", "progresivo", "fartlek")
MAX_CATEGORIAS = 4
# Íconos de site/iconos.js. Cada tipo de Garmin se mapea a uno; Python decide, el sitio solo pinta.
ICONOS = ("correr", "medalla", "mancuerna", "rayo", "bici", "nadar", "caminar", "yoga", "punto")
ICONO_TIPO = {
    "running": "correr", "treadmill_running": "correr", "trail_running": "correr", "track_running": "correr",
    "strength_training": "mancuerna", "hiit": "rayo", "cardio": "rayo",
    "cycling": "bici", "indoor_cycling": "bici", "virtual_ride": "bici", "spinning": "bici",
    "road_biking": "bici", "mountain_biking": "bici",
    "lap_swimming": "nadar", "open_water_swimming": "nadar", "walking": "caminar", "hiking": "caminar",
    "yoga": "yoga", "pilates": "yoga",
}


def icono_de_tipo(type_key) -> str:
    """Ícono de un typeKey de Garmin; "punto" si no tiene uno propio."""
    return ICONO_TIPO.get(type_key, "punto")
# Color de cada categoría según cuántas hay (validado con el skill dataviz, claro y oscuro: el naranja
# es de la corrida y nunca queda junto al amarillo ni al magenta en la pila de la carga semanal).
CLASES = {1: ["azul"], 2: ["azul", "aqua"], 3: ["azul", "aqua", "violeta"],
          4: ["azul", "amarillo", "violeta", "aqua"]}


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
        icono = c.get("icono") or icono_de_tipo(c["tipos"][0])
        if icono not in ICONOS:
            raise ConfigError(f"La categoría '{c['id']}' tiene icono '{icono}'; usa: {', '.join(ICONOS)}")
        out.append({"id": c["id"], "nombre": c["nombre"], "letra": c["letra"], "tipos": list(c["tipos"]),
                    "intensa": bool(c.get("intensa", False)), "clase": CLASES[len(brutas)][i], "icono": icono})
    return out


PRUEBAS_TIPOS = ("fc_fija", "trote_continuo", "5k")


def _pruebas(brutas: list) -> list:
    """Resultados de pruebas anteriores [{fecha, tipo, valor}], por fecha. `valor` es lo que publica el sitio:
    ritmo (s/km) a FC fija, % de trote continuo o segundos de los 5 km."""
    out = []
    for i, p in enumerate(brutas):
        for k in ("fecha", "tipo", "valor"):
            if p.get(k) in (None, ""):
                raise ConfigError(f"La prueba {i + 1} de `corrida.pruebas` no tiene `{k}`")
        if p["tipo"] not in PRUEBAS_TIPOS:
            raise ConfigError(f"corrida.pruebas: tipo '{p['tipo']}' no válido; usa: {', '.join(PRUEBAS_TIPOS)}")
        out.append({"fecha": _fecha(p["fecha"], "corrida.pruebas"), "tipo": p["tipo"], "valor": float(p["valor"])})
    return sorted(out, key=lambda x: x["fecha"])


def leer_config_yaml(ruta) -> dict:
    """config.yaml crudo (sin validar ni completar). `ruta` puede ser el archivo o su carpeta.
    Es el mismo formato que la web guarda en la tabla `ajustes`."""
    ruta = Path(ruta) if ruta else USER_DIR
    ruta = ruta if ruta.is_file() else ruta / "config.yaml"   # acepta el archivo o su carpeta
    if not ruta.exists():
        raise ConfigError(f"No existe {ruta}. Corre /setup en Claude Code para crearlo "
                          "(o copia config.example.yaml como config.yaml).")
    return _leer_yaml(ruta)


def normalizar_config(crudo: dict) -> dict:
    """Config plana lista para build/metrics/garmin_connect a partir del dict crudo. Truena con ConfigError.
    Clave opcional `modo` ("pages" por defecto, "web" en la web): la pone quien llama, no se escribe en config.yaml."""
    defaults = _leer_yaml(Path(__file__).parent / "defaults.yaml")
    cfg = crudo or {}
    modo = cfg.get("modo") or "pages"
    if modo not in ("pages", "web"):
        raise ConfigError(f"modo '{modo}' no válido; usa: pages, web")
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
    variada = bool(corrida.get("variada", False))
    if intensidad == "calidad" and not tipos_cal and variada:
        tipos_cal = list(CALIDAD_TIPOS)   # variada + calidad sin elegir: rotan los 5 avanzados
    if intensidad == "calidad" and not tipos_cal:
        raise ConfigError("corrida.intensidad es `calidad` pero `calidad_tipos` está vacío")
    base = {"z2": 20, "larga": 40, **(corrida.get("base_min") or {})}
    pruebas = _pruebas(corrida.get("pruebas") or [])

    categorias = _categorias(act.get("categorias") or defaults["categorias"])
    # `actividades.semana` (v4.1 y antes) se tolera y se ignora: ya no se asume ninguna semana típica.
    pierna = sorted(_dia(d, "actividades.dias_pierna") for d in act.get("dias_pierna") or [])

    umbrales = {**defaults["umbrales"], **(cfg.get("umbrales") or {})}
    desde = perfil.get("fc_max_correa_desde")
    return {
        "modo": modo,
        "menu": list(cfg.get("menu") or []),   # solo la web: [{texto, url}] para ui.menu
        "acciones_url": cfg.get("acciones_url"),
        **umbrales,
        "titulo": perfil.get("titulo") or "Mi entreno",
        "timezone": tz, "edad": edad,
        "max_hr": max_hr, "max_hr_floor": perfil.get("fc_max_piso", max_hr),
        "fc_max_correa_desde": _fecha(desde, "perfil.fc_max_correa_desde") if desde else None,
        "carreras": sorted({_fecha(f, "corrida.carreras") for f in corrida.get("carreras") or []}),
        "plan_start": inicio, "semanas_repetidas": list(corrida.get("semanas_repetidas") or []),
        "nivel": nivel, "intensidad": intensidad, "calidad_tipos": tipos_cal,
        "caminatas": bool(corrida.get("caminatas", False)), "variada": variada,
        "plan_semanas": int(corrida.get("semanas", 12)), "base_min": base, "pruebas": pruebas,
        "categorias": categorias, "dias_pierna": pierna,
        "inbody": bool(cfg.get("inbody", True)),
        "tipos_con_detalle": umbrales["run_types"] + [t for c in categorias for t in c["tipos"]],
    }


def cargar_config(user_dir=None) -> dict:
    """Config plana lista para build/metrics/garmin_connect. Truena con ConfigError si falta algo."""
    return normalizar_config(leer_config_yaml(user_dir))


def config_por_defecto() -> dict:
    """Config con solo valores por defecto, para quien no tiene config.yaml (repos nuevos que solo son tubo de datos:
    garmin_connect.py solo necesita los tipos de actividad)."""
    return normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190},
                              "corrida": {"inicio": "2026-01-05"}})


def categorias_por_defecto() -> list:
    """Las categorías de actividad de defaults.yaml (sin validar): [{id, nombre, letra, tipos, intensa}]."""
    return list(_leer_yaml(Path(__file__).parent / "defaults.yaml")["categorias"])
