"""Motor v6 F5: carreras construidas dentro del plan (`en_plan`), eventos sobre planes v6 y plan fijo en build (sin ajuste semanal)."""
from datetime import timedelta

from dashboard import build
from plan import motor_v6
from dashboard.ajustes import normalizar_config
from web import plan_vivo
from ayudas import _acts, _cfg, crudo_de, INICIO, plan_v6


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


def test_quitar_una_meta_vieja_en_plan_rehace_la_cola():
    """Las metas viejas con `en_plan` (carrera construida dentro del plan) se quitan como antes; las de paso no rehacen nada (test_planes_carrera_paso)."""
    plan = plan_v6()
    hoy = INICIO + timedelta(weeks=2, days=1)
    fecha = (INICIO + timedelta(weeks=9, days=5)).isoformat()
    plan_n = motor_v6.con_carrera(plan, 3, {"km": 10, "fecha": fecha, "semanas_hasta": 10})
    nuevo = crudo_de(plan_n, metas=[{"id": "a", "tipo": "carrera", "fecha": fecha, "distancia_km": 10, "en_plan": True}])
    assert len(plan_n["weeks"]) == 10 and plan_n["weeks"][-1].get("evento") == "carrera"
    assert plan_n["weeks"][:2] == plan["weeks"][:2]   # las ya pasadas no cambian
    cfg = cfg_de(nuevo, hoy)
    assert plan_vivo.plan_efectivo(plan_n, cfg) is plan_n
    sin, plan_s = plan_vivo.quitar_meta_en_plan(nuevo, plan_n, cfg, "a", hoy)
    assert not sin["corrida"]["metas"] and plan_s is not None and not plan_s["meta"].get("carrera")
    assert all(w.get("evento") != "carrera" for w in plan_s["weeks"])


def test_viaje_sobre_plan_v6_sigue_funcionando():
    plan = plan_v6()
    hoy = INICIO + timedelta(days=1)
    crudo = crudo_de(plan)
    crudo = plan_vivo.agregar_evento(crudo, "viaje", (INICIO + timedelta(weeks=1)).isoformat(), (INICIO + timedelta(weeks=1, days=3)).isoformat(), modo="menos")
    ef = plan_vivo.plan_efectivo(plan, cfg_de(crudo, hoy))
    assert ef["weeks"][1]["evento"] == "viaje" and ef["weeks"][1]["kind"] == "descarga" and ef["weeks"][0] == plan["weeks"][0]
    crudo = plan_vivo.agregar_evento(crudo_de(plan), "enfermedad", (INICIO + timedelta(weeks=1)).isoformat(), None)
    assert cfg_de(crudo, INICIO + timedelta(weeks=1, days=2))["pausas"]


def test_plan_fijo_la_semana_en_curso_sale_igual_aunque_la_anterior_se_corriera_poco():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from ayudas import fixture
    plan = plan_v6()
    cfg = {**_cfg(plan), "modo": "web"}
    ahora = datetime.combine(INICIO + timedelta(weeks=1, days=2), datetime.min.time(), tzinfo=ZoneInfo("America/Merida")).replace(hour=12)
    datos = fixture()

    def minutos_sem2(acts):
        out = build.build({**datos, "activities": acts}, plan, cfg, ahora)
        return [[s["minutes"] for s in w["sessions"]] for w in out["plan"]["semanas"] if w["n"] == 2]
    guardado = [[s["minutes"] for s in plan["weeks"][1]["sessions"]]]
    assert minutos_sem2([]) == minutos_sem2(_acts({0: 5})) == minutos_sem2(_acts({0: 200})) == guardado


def test_sesiones_faciles_dicen_z2_o_platicar():
    plan = plan_v6()
    notas = {p["note"] for w in plan["weeks"] for s in w["sessions"] if s["tipo"] == "z2" for p in s["steps"]}
    assert "Z2 o un ritmo en el que puedas platicar" in notas
