"""Lógica pura de reloj.py (sin red ni `garminconnect`): arma los entrenamientos del plan en el formato de Garmin.

Solo de Pedro: no la usa el workflow ni la plantilla. Los IDs de Garmin nunca pasan por aquí hacia el sitio.
"""
import re
from datetime import date

import metrics as m

DESCRIPCION = "Plan del dashboard"   # marca para reconocer lo que mandó el plan

# IDs de Garmin (iguales a los de garminconnect.workout, verificados en la versión 0.3.20)
DEPORTE_CORRER = {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1}
TIPO_PASO = {"run": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
             "walk": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4}}
TIPO_REPETIR = {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6}
FIN_TIEMPO = {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2, "displayable": True}
FIN_VECES = {"conditionTypeId": 7, "conditionTypeKey": "iterations", "displayOrder": 7, "displayable": False}
SIN_OBJETIVO = {"workoutTargetTypeId": 1, "workoutTargetTypeKey": "no.target", "displayOrder": 1}
OBJETIVO_ZONA_FC = {"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone", "displayOrder": 1}


def semana_actual(hoy: date, config: dict, plan: dict):
    """Semana del plan (cuenta `semanas_repetidas`) que toca hoy, o None si no hay."""
    n = m.semana_del_plan(hoy, config)
    return n if n is not None and any(w["n"] == n for w in plan["weeks"]) else None


def numero_zona(zona):
    """'Z2' -> 2; 'Z1-Z2' -> 1 (la primera); sin zona -> None."""
    hallado = re.search(r"Z(\d)", zona or "")
    return int(hallado.group(1)) if hallado else None


def _paso(p: dict, orden: int, hijo=None) -> dict:
    zona = numero_zona(p.get("zone"))
    paso = {"type": "ExecutableStepDTO", "stepOrder": orden,
            "stepType": TIPO_PASO["walk" if p["kind"] == "walk" else "run"],
            "endCondition": FIN_TIEMPO, "endConditionValue": float(p["minutes"] * 60),
            "targetType": OBJETIVO_ZONA_FC if zona else SIN_OBJETIVO}
    if zona:
        paso["zoneNumber"] = zona
    if p.get("note"):
        paso["description"] = p["note"]
    if hijo:
        paso["childStepId"] = hijo
    return paso


def pasos_garmin(pasos: list) -> list:
    """Pasos del plan -> pasos de Garmin, mismo orden. `repeat` es un grupo de repetición."""
    cuenta = {"orden": 0, "grupos": 0}

    def convertir(lista, hijo=None):
        out = []
        for p in lista:
            cuenta["orden"] += 1
            if p["kind"] == "repeat":
                cuenta["grupos"] += 1
                grupo = {"type": "RepeatGroupDTO", "stepOrder": cuenta["orden"], "stepType": TIPO_REPETIR,
                         "numberOfIterations": p["times"], "endCondition": FIN_VECES,
                         "endConditionValue": float(p["times"]), "smartRepeat": False}
                grupo["workoutSteps"] = convertir(p["steps"], cuenta["grupos"])
                out.append(grupo)
            else:
                out.append(_paso(p, cuenta["orden"], hijo))
        return out
    return convertir(pasos)


def minutos_pasos(pasos: list) -> int:
    return sum(p["times"] * minutos_pasos(p["steps"]) if p["kind"] == "repeat" else p["minutes"] for p in pasos)


def nombre_entrenamiento(sesion: dict, n: int) -> str:
    return f"S{n} · {sesion['name']} · {sesion['minutes']}'"


def entrenamiento(sesion: dict, n: int) -> dict:
    """Entrenamiento de correr listo para `upload_workout` (versión normal de la sesión, no la suave)."""
    return {"workoutName": nombre_entrenamiento(sesion, n), "description": DESCRIPCION,
            "sportType": DEPORTE_CORRER,
            "estimatedDurationInSecs": minutos_pasos(sesion["steps"]) * 60,
            "workoutSegments": [{"segmentOrder": 1, "sportType": DEPORTE_CORRER,
                                 "workoutSteps": pasos_garmin(sesion["steps"])}]}


def resumen_pasos(pasos: list) -> str:
    """"10' Z2 · 1' Z3 · 3× (4' Z2 + 1' Z1 caminar)" para mostrar qué se va a subir."""
    partes = []
    for p in pasos:
        if p["kind"] == "repeat":
            partes.append(f"{p['times']}× ({' + '.join(resumen_pasos([q]) for q in p['steps'])})")
        else:
            partes.append(f"{p['minutes']}' {p.get('zone') or 'sin zona'}" + (" caminar" if p["kind"] == "walk" else ""))
    return " · ".join(partes)


def clasificar(enviados: list, estado: list):
    """(borrar_sin_preguntar, pendientes). `estado`: lista de m.assign_sessions de la semana de esos enviados.
    Una sesión `hecha` se borra sin preguntar; `pendiente` (o que ya no existe en el plan) se pregunta."""
    por_id = {e["id"]: e["estado"] for e in estado}
    borrar, pendientes = [], []
    for e in enviados:
        (borrar if por_id.get(e["sesion"]) == "hecha" else pendientes).append(e)
    return borrar, pendientes
