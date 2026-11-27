"""Convierte un plan del motor anterior (`plan/plan.json`: start + weeks) al formato del motor v6 (con `meta`), sin tocar
semanas, sesiones ni minutos. Así el plan viejo de Pedro vive en la web con todo lo de v6 (nivel, km_est, editar/ajustar, largo, Juntos).
La carrera NO entra al plan (sus semanas siguen siendo las viejas): va como meta con fecha en los ajustes (`ajustes_con_carrera`)."""
import copy
import secrets
from datetime import date

import motor_v6

NIVEL_DEFECTO = "base"   # supuesto: base aeróbica (Z2 + picos Z3 opcionales, 3 días por semana); Empezando no admite Z3


def convertir(viejo: dict, nivel: str = NIVEL_DEFECTO, edad: int = 35) -> dict:
    """Plan v6 con las mismas semanas del viejo. ValueError si el plan viejo no tiene el formato esperado."""
    if not viejo.get("weeks") or not viejo.get("start"):
        raise ValueError("el plan viejo necesita `start` y `weeks`")
    inicio = date.fromisoformat(str(viejo["start"]))
    if inicio.weekday() != 0:
        raise ValueError("el plan debe empezar en lunes")
    semanas = copy.deepcopy(viejo["weeks"])
    dias = max(len(w["sessions"]) for w in semanas)
    inicio_min = motor_v6.minutos_semana(semanas[0])
    entrada = motor_v6.normalizar_entrada({"nivel": nivel, "dias": dias, "meta": "base", "objetivo": "base", "inicio": inicio.isoformat(),
                                           "semanas": len(semanas), "inicio_minutos": inicio_min, "edad": edad})
    descargas = [w["n"] for w in semanas if w.get("kind") == "descarga"]
    ciclo = descargas[0] if descargas else motor_v6.UMBRALES["ciclo"]
    meta = {"motor": "v6", "nivel": nivel, "dias": dias, "objetivo": "base", "ciclo": ciclo, "calidad": False, "semanas": len(semanas),
            "inicio_minutos": inicio_min, "avisos": [], "porque": [], "entrada": entrada, "convertido_de": "plan_viejo"}
    return {"start": inicio.isoformat(), "weeks": semanas, "meta": meta}


def ajustes_con_carrera(crudo: dict, plan: dict, fecha: str, km: int = 10, nombre: str | None = None) -> dict:
    """Copia de los ajustes (`crudo`) con inicio y semanas del plan, la carrera como meta con fecha (sin `en_plan`: el plan no trae su taper)
    y sin metas viejas de la misma fecha ni las que armó el plan de 7 semanas (`en_plan`)."""
    nuevo = copy.deepcopy(crudo)
    corrida = nuevo.setdefault("corrida", {})
    corrida.update({"inicio": plan["start"], "semanas": len(plan["weeks"])})
    corrida.pop("semanas_repetidas", None)
    metas = [m for m in corrida.get("metas") or [] if not m.get("en_plan") and str(m.get("fecha")) != fecha]
    metas.append({"id": secrets.token_hex(4), "tipo": "carrera", "fecha": fecha, "distancia_km": km, "nombre": nombre or f"{km}K"})
    corrida["metas"] = metas
    return nuevo


def resumen(plan: dict) -> list:
    """Líneas para imprimir: semanas con sus minutos, inicio y total."""
    lineas = [f"Inicio {plan['start']} · {len(plan['weeks'])} semanas · nivel {plan['meta']['nivel']} · {plan['meta']['dias']} días"]
    for w in plan["weeks"]:
        lineas.append(f"  S{w['n']:>2} {w['kind']:<8} {motor_v6.minutos_semana(w):>3} min  {w['focus']}")
    return lineas
