"""Piezas compartidas: clasificación de actividades y utilidades de fecha/id."""

from datetime import date


ZONAS = ["Z1", "Z2", "Z3", "Z4", "Z5"]


def day_of(activity: dict) -> date:
    return date.fromisoformat(activity["startTimeLocal"][:10])


# Las actividades registradas a mano (`manual: true`) se clasifican por su tipo con este mapa fijo, sin depender de la
# config de cada persona (decisión 6 de PLAN_ENTRADA). Lo que no esté aquí es «otra».
CATEGORIA_MANUAL = {"running": "run", "walking": "caminar", "hiit": "hiit", "strength_training": "fuerza",
                    "cycling": "cardio", "lap_swimming": "cardio", "elliptical": "cardio", "yoga": "movilidad"}


def classify(activity: dict, config: dict):
    """"run", el `id` de la categoría de actividad (config["categorias"]) o None si no se muestra."""
    tipo = activity["activityType"]["typeKey"]
    if activity.get("manual"):
        cat = CATEGORIA_MANUAL.get(tipo, "otra")
        ids = {c["id"] for c in config.get("categorias", [])}
        if cat == "run" or cat in ids:
            return cat
        # una categoría propia se quedó con ese id: se usa la que cubre el tipo, o «otra»
        return next((c["id"] for c in config.get("categorias", []) if tipo in c["tipos"]), "otra" if "otra" in ids else None)
    if tipo in config["run_types"]:
        return "run"
    for c in config.get("categorias", []):
        if tipo in c["tipos"]:
            return c["id"]
    return None


def categorias_intensas(config: dict) -> list:
    return [c for c in config.get("categorias", []) if c.get("intensa")]


def nombre_intensa(config: dict):
    """Nombre de la categoría intensa si hay una sola; None si hay varias o ninguna."""
    ints = categorias_intensas(config)
    return ints[0]["nombre"] if len(ints) == 1 else None


def id_de(a: dict):
    """Id de una actividad: el `id` opaco del paquete (web) o el `activityId` de Garmin (datos locales)."""
    return a.get("id") or a.get("activityId")
