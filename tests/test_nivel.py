"""Nivel desde Garmin (plan/nivel.py) con actividades sintéticas."""
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent
from plan import nivel as nv

HOY = datetime(2026, 11, 30)


def corrida(dias_atras, minutos, continuo=None, tipo="running"):
    a = {"startTimeLocal": (HOY - timedelta(days=dias_atras, hours=-7)).isoformat(sep=" "),
         "duration": minutos * 60.0, "activityType": {"typeKey": tipo}}
    if continuo and continuo < minutos:
        n = max(1, round(minutos / (continuo + 1)))
        a["splitSummaries"] = [{"splitType": "RWD_RUN", "duration": n * continuo * 60, "noOfSplits": n},
                               {"splitType": "RWD_WALK", "duration": n * 60, "noOfSplits": n}]
    return a


def semanas(n_sem, sesiones, desde=1, continuo=None):
    """`sesiones` minutos por semana, repartidas (3 días de separación aprox.), de la semana `desde` a `desde+n_sem-1`."""
    return [corrida(7 * (s - 1) + 2 + 2 * j, m, continuo)
            for s in range(desde, desde + n_sem) for j, m in enumerate(sesiones)]


def test_sin_datos_es_empezando_con_escalera():
    r = nv.nivel_desde_datos([], HOY)
    assert r["nivel"] == "empezando"
    assert r["inicio_minutos"] == nv.UMBRALES["inicio_sin_historial_min"]
    assert r["evidencia"]["dias_desde_ultima"] is None and r["evidencia"]["semanas_activas"] == 0


def test_trota_camina_es_empezando_y_arranca_cerca_de_lo_real():
    r = nv.nivel_desde_datos(semanas(8, [15, 15], continuo=2), HOY)
    assert r["nivel"] == "empezando"
    assert r["evidencia"]["trote_continuo_min"] == 2.0
    assert r["inicio_minutos"] == nv.PISO_NIVEL["empezando"]   # 30' de promedio < piso (45'): arranca en el piso, nunca debajo


def test_base_y_evidencia():
    r = nv.nivel_desde_datos(semanas(8, [30, 30, 35]), HOY)
    e = r["evidencia"]
    assert r["nivel"] == "base"
    assert e["corridas_sem_4"] == 3 and e["corridas_sem_8"] == 3
    assert e["minutos_sem_prom"] == 95 and e["minutos_sem_mediana"] == 95
    assert e["trote_continuo_min"] == 35 and e["semanas_activas"] == 8 and e["semanas_consistentes"] == 8
    assert e["sesion_max_30d"] == 35 and e["intensos_sem"] == 0
    assert r["inicio_minutos"] == 100   # 95 × 1.10 = 104.5 → múltiplo de 5 hacia abajo


def test_corredor():
    r = nv.nivel_desde_datos(semanas(8, [45, 45, 45, 60]), HOY)
    assert r["nivel"] == "corredor" and r["inicio_minutos"] <= 195 * 1.10


def test_pocas_semanas_activas_no_es_corredor():
    assert nv.nivel_desde_datos(semanas(5, [45, 45, 45, 60]), HOY)["nivel"] == "base"


def test_pausa_larga_baja_un_nivel():
    base = nv.nivel_desde_datos(semanas(8, [30, 30, 35], desde=5), HOY)   # corrió hasta hace ~4 semanas
    e = base["evidencia"]
    assert e["dias_desde_ultima"] > nv.UMBRALES["pausa_baja_nivel_dias"]
    assert e["desentrenamiento"] == "baja_nivel" and e["nivel_sin_pausa"] == "base" and base["nivel"] == "empezando"
    assert [nv._bajar(n) for n in nv.NIVELES] == ["empezando", "empezando", "base"]


def test_pausa_leve_recorta_el_arranque():
    r = nv.nivel_desde_datos(semanas(8, [30, 30, 35], desde=3), HOY)   # última corrida hace ~15 días
    assert r["evidencia"]["desentrenamiento"] == "leve" and r["nivel"] == "base"
    assert r["inicio_minutos"] < 105 * 0.8 + 1


def test_sin_corridas_en_8_semanas_es_empezando():
    assert nv.nivel_desde_datos([corrida(80, 40)], HOY)["nivel"] == "empezando"


def test_dias_intensos_unidos_y_habituales():
    act = semanas(8, [30, 30, 35])
    for s in range(8):   # CrossFit lun y jue: fuerza + hiit pegados = un solo día intenso
        for d in (0, 3):
            ini = HOY - timedelta(days=7 * (s + 1)) + timedelta(days=d, hours=18)
            act.append({"startTimeLocal": ini.isoformat(sep=" "), "duration": 1800.0, "activityType": {"typeKey": "strength_training"}})
            act.append({"startTimeLocal": (ini + timedelta(minutes=35)).isoformat(sep=" "), "duration": 900.0, "activityType": {"typeKey": "hiit"}})
    e = nv.nivel_desde_datos(act, HOY)["evidencia"]
    assert e["intensos_sem"] == 2 and e["dias_intensos"] == [0, 3]


def test_actividades_futuras_se_ignoran():
    r = nv.nivel_desde_datos([corrida(-3, 60)], HOY)
    assert r["evidencia"]["semanas_activas"] == 0


def test_personas_del_simulador_tienen_nivel():
    from plan import simulador as sim
    niveles = {p["id"]: p["nivel"]["nivel"] for p in sim.cargar_personas()}
    assert niveles["novata_sin_datos"] == "empezando" and niveles["novata_trota_camina"] == "empezando"
    assert niveles["corredor_velocidad"] == "corredor" and niveles["pedro_like"] == "base"
    assert sim.simular(sim.persona_por_id("pedro_like"))["nivel"]["nivel"] == "base"
