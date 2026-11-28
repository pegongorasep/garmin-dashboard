"""P6: dos semanas sin correr con plan en curso → Hoy sugiere retomar (Python decide); carrera de paso sin versión suave."""
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import build
import metrics as m
import planes_v6
from ajustes import normalizar_config
from test_build import CONFIG, fixture
from test_web_ajustes import CONFIG as CONFIG_WEB

PLAN = {**planes_v6.generar(normalizar_config(CONFIG_WEB)), "start": "2026-10-26"}
INI = date(2026, 10, 26)   # semana 1
CFG = {**CONFIG, "plan_start": INI.isoformat()}


def act(i, dia, tipo="running", minutos=30, **kw):
    return {"activityId": i, "startTimeLocal": f"{dia} 18:00:00", "duration": minutos * 60.0,
            "id": i, "activityType": {"typeKey": tipo}, "distance": 3000.0, "hrTimeInZone_2": 600, **kw}


def hoy_con(acts, dia, cfg=CFG):
    data = {**fixture(), "activities": acts}
    ahora = datetime.combine(dia, datetime(2026, 1, 1, 12).time(), tzinfo=ZoneInfo("America/Merida"))
    return build.build(data, PLAN, cfg, ahora)


def retomar(acts, dia, cfg=CFG):
    return hoy_con(acts, dia, cfg)["hoy"]["retomar"]


def test_13_dias_no_14_si():
    ultima = INI + timedelta(days=15)   # semana 3
    assert retomar([act(1, ultima.isoformat())], ultima + timedelta(days=13)) is None
    r = retomar([act(1, ultima.isoformat())], ultima + timedelta(days=14))
    assert r["dias"] == 14 and r["ultima"] == ultima.isoformat() and r["accion"] == "retomar"
    assert 1 <= r["semana"] <= 4   # tope: semana actual - 1


def test_x_es_la_ultima_semana_completa_y_nunca_la_actual():
    # semana 1 sin hacer nada ni correr: X = 1 (no hay completa)
    r = retomar([act(1, INI.isoformat())], INI + timedelta(days=22))   # semana 4, 21 días sin correr
    assert r["semana"] == 1 and r["accion"] == "retomar"


def test_nunca_corrio_cuenta_desde_el_inicio_del_plan():
    r = retomar([], INI + timedelta(days=14))
    assert r["dias"] == 14 and r["ultima"] is None and r["semana"] == 1 and r["accion"] == "retomar"
    assert retomar([], INI + timedelta(days=13)) is None


def test_semana_uno_ofrece_repetir():
    # primera semana del plan y 14 días sin correr: la última corrida fue antes del plan
    cfg = {**CFG, "plan_start": (INI + timedelta(days=14)).isoformat()}
    r = retomar([act(1, INI.isoformat())], INI + timedelta(days=15), cfg)
    assert r["accion"] == "repetir" and r["semana"] == 1


def test_actividad_a_mano_de_correr_cuenta_y_caminar_no():
    hoy = INI + timedelta(days=22)
    mano = act(1, (hoy - timedelta(days=3)).isoformat(), tipo="running", manual=True)
    assert retomar([mano], hoy) is None
    caminar = act(2, (hoy - timedelta(days=3)).isoformat(), tipo="walking")
    assert retomar([caminar], hoy) is not None


def test_pausa_enfermedad_sin_plan_y_plan_terminado():
    hoy = INI + timedelta(days=22)
    assert retomar([], hoy, {**CFG, "eventos": [{"tipo": "enfermedad", "desde": (hoy - timedelta(days=2)).isoformat(),
                                                  "hasta": (hoy + timedelta(days=2)).isoformat(), "correr": False, "modo": "pausa"}]}) is None
    assert retomar([], hoy, {**CFG, "sin_plan": True}) is None
    assert retomar([], INI + timedelta(weeks=40)) is None
    d = hoy_con([], hoy)
    assert build.retomar_sugerido(hoy, {**fixture(), "activities": []}, CFG, PLAN, d["semanas_hoy"], 4, True) is None


def test_huella_cambia_con_la_ultima_corrida():
    hoy = INI + timedelta(days=40)
    a = hoy_con([act(1, (INI + timedelta(days=5)).isoformat())], hoy)["ui"]["avisos"]["retomar"]
    b = hoy_con([act(1, (INI + timedelta(days=6)).isoformat())], hoy)["ui"]["avisos"]["retomar"]
    assert a != b


def test_carrera_de_paso_no_tiene_opciones_suaves():
    ses = {"easy": {"minutes": 40}, "carrera": True}
    assert m.opciones_hoy("normal", ses) == []
    assert m.opciones_hoy("normal", {"easy": {"minutes": 20}}) == ["suave", "normal"]


def test_x_toma_la_ultima_semana_con_todo_hecho_con_tope():
    def sem(n, hechas, total=3, estado="pasada"):
        return {"n": n, "estado": estado, "plan": {"hechas": hechas, "total": total}}
    semanas = [sem(1, 3), sem(2, 3), sem(3, 1), sem(4, 3, estado="actual")]
    hoy = INI + timedelta(days=30)
    data = {**fixture(), "activities": [], "historial": []}
    r = build.retomar_sugerido(hoy, data, CFG, PLAN, semanas, 4, False)
    assert r["semana"] == 2 and r["accion"] == "retomar"
    assert build.retomar_sugerido(hoy, data, CFG, PLAN, [sem(1, 3), sem(2, 3), sem(3, 3), sem(4, 3, estado="actual")], 3, False)["semana"] == 2   # tope n - 1
