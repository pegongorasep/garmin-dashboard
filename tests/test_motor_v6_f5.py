"""Motor v6 F5: carreras construidas dentro del plan (`en_plan`), eventos sobre planes v6 y ajuste semanal en build."""
import copy
from datetime import date, timedelta

import build
import motor_v6
import semanal
from ajustes import normalizar_config
from web import plan_vivo

INICIO = date(2026, 11, 30)   # lunes
EV = {"minutos_sem_prom": 60, "trote_continuo_min": 30, "semanas_consistentes": 2, "sesion_max_30d": 30}


def plan_v6(**extra):
    return motor_v6.generar_v6({"nivel": "base", "dias": 3, "meta": "base", "inicio": INICIO.isoformat(), "evidencia": EV,
                                "inicio_minutos": 60, "semanas": 12, **extra})


def crudo_de(plan, **corrida):
    return {"perfil": {"edad": 35, "zona_horaria": "America/Merida"}, "corrida": {"inicio": plan["start"], "semanas": len(plan["weeks"]), **corrida}}


def cfg_de(crudo, hoy):
    return plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), hoy)


def test_meta_en_plan_no_se_aplica_dos_veces():
    plan = plan_v6(meta={"km": 10, "fecha": (INICIO + timedelta(weeks=9, days=5)).isoformat()})
    crudo = crudo_de(plan, metas=[{"id": "a", "tipo": "carrera", "fecha": (INICIO + timedelta(weeks=9, days=5)).isoformat(), "distancia_km": 10, "en_plan": True}])
    cfg = cfg_de(crudo, INICIO)
    assert cfg["metas"][0]["en_plan"] is True
    assert plan_vivo.plan_efectivo(plan, cfg) is plan
    crudo["corrida"]["metas"][0].pop("en_plan")
    assert normalizar_config(crudo)["metas"][0]["en_plan"] is False   # por defecto: false


def test_carrera_agregada_despues_rehace_el_plan_desde_la_semana_en_curso():
    plan = plan_v6()
    hoy = INICIO + timedelta(weeks=2, days=1)
    fecha = (INICIO + timedelta(weeks=9, days=5)).isoformat()
    crudo = crudo_de(plan)
    nuevo, plan_n = plan_vivo.agregar_carrera_en_plan(crudo, plan, cfg_de(crudo, hoy), fecha, "10", "Mi 10K", hoy)
    assert plan_n is not None and len(plan_n["weeks"]) == 10 and plan_n["weeks"][-1].get("evento") == "carrera"
    assert nuevo["corrida"]["metas"][-1]["en_plan"] is True and nuevo["corrida"]["semanas"] == 10
    assert plan_n["weeks"][:2] == plan["weeks"][:2]   # las ya pasadas no cambian
    cfg = cfg_de(nuevo, hoy)
    assert plan_vivo.plan_efectivo(plan_n, cfg) is plan_n
    # quitarla rehace la cola sin carrera
    mid = nuevo["corrida"]["metas"][-1]["id"]
    sin, plan_s = plan_vivo.quitar_meta_en_plan(nuevo, plan_n, cfg, mid, hoy)
    assert not sin["corrida"]["metas"] and plan_s is not None and not plan_s["meta"].get("carrera")
    assert all(w.get("evento") != "carrera" for w in plan_s["weeks"])


def test_carrera_en_plan_viejo_o_con_otra_distancia_usa_la_superposicion():
    plan = plan_v6()
    hoy = INICIO + timedelta(days=1)
    crudo = crudo_de(plan)
    fecha = (INICIO + timedelta(weeks=5, days=5)).isoformat()
    nuevo, plan_n = plan_vivo.agregar_carrera_en_plan(crudo, plan, cfg_de(crudo, hoy), fecha, "15", "15K", hoy)
    assert plan_n is None and not nuevo["corrida"]["metas"][-1].get("en_plan")
    viejo = {k: v for k, v in plan.items() if k != "meta"}
    assert plan_vivo.agregar_carrera_en_plan(crudo, viejo, cfg_de(crudo, hoy), fecha, "10", "x", hoy)[1] is None


def test_viaje_sobre_plan_v6_sigue_funcionando():
    plan = plan_v6()
    hoy = INICIO + timedelta(days=1)
    crudo = crudo_de(plan)
    crudo = plan_vivo.agregar_evento(crudo, "viaje", (INICIO + timedelta(weeks=1)).isoformat(), (INICIO + timedelta(weeks=1, days=3)).isoformat(), modo="menos")
    ef = plan_vivo.plan_efectivo(plan, cfg_de(crudo, hoy))
    assert ef["weeks"][1]["evento"] == "viaje" and ef["weeks"][1]["kind"] == "descarga" and ef["weeks"][0] == plan["weeks"][0]
    crudo = plan_vivo.agregar_evento(crudo_de(plan), "enfermedad", (INICIO + timedelta(weeks=1)).isoformat(), None)
    assert cfg_de(crudo, INICIO + timedelta(weeks=1, days=2))["pausas"]


def _acts(minutos_por_semana: dict):
    out = []
    for i, mins in minutos_por_semana.items():
        for k in range(3):
            f = INICIO + timedelta(weeks=i, days=2 * k)
            out.append({"startTimeLocal": f"{f} 07:00:00", "duration": mins / 3 * 60, "activityType": {"typeKey": "running"}})
    return out


def _cfg(plan):
    return {"plan_start": plan["start"], "semanas_repetidas": [], "pausas": [], "plan_semanas": len(plan["weeks"]),
            **{k: v for k, v in normalizar_config(crudo_de(plan)).items()}}


def test_ajuste_semanal_baja_la_semana_en_curso_y_solo_esa():
    plan = plan_v6()
    cfg = _cfg(plan)
    hoy = INICIO + timedelta(weeks=1, days=2)
    sube = semanal.ajustar_plan(plan, {"activities": _acts({0: 60})}, cfg, hoy)
    poco = semanal.ajustar_plan(plan, {"activities": _acts({0: 20})}, cfg, hoy)
    assert sum(s["minutes"] for s in poco["weeks"][1]["sessions"]) < sum(s["minutes"] for s in plan["weeks"][1]["sessions"])
    assert poco["weeks"][1]["ajuste_texto"] and poco["weeks"][0] == plan["weeks"][0] and poco["weeks"][2] == plan["weeks"][2]
    assert semanal.ajustar_plan(plan, {"activities": _acts({0: 20})}, cfg, hoy) == poco   # determinista
    assert sube["weeks"][1].get("ajuste_texto") in (None, "") or "ajustada" in sube["weeks"][1]["ajuste_texto"]
    # plan viejo (sin meta v6) y sin actividades: sin cambios
    viejo = {k: v for k, v in plan.items() if k != "meta"}
    assert semanal.ajustar_plan(viejo, {"activities": _acts({0: 20})}, cfg, hoy) is viejo
    assert semanal.ajustar_plan(plan, {"activities": []}, cfg, hoy) is plan


def test_sesiones_faciles_dicen_z2_o_platicar():
    plan = plan_v6()
    notas = {p["note"] for w in plan["weeks"] for s in w["sessions"] if s["tipo"] == "z2" for p in s["steps"]}
    assert "Z2 o un ritmo en el que puedas platicar" in notas
