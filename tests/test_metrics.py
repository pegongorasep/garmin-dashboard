import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
import metrics as m  # noqa: E402

CFG = {
    "max_hr": 190, "max_hr_floor": 183, "max_hr_review_above": 200,
    "fc_max_correa_desde": "2026-10-26", "rhr_tolerance_bpm": 4,
    "sleep_min_hours": 6.5, "rpe_heavy": 8,
    "run_types": ["running", "treadmill_running"],
    "categorias": [{"id": "crossfit", "nombre": "CrossFit", "letra": "CF", "tipos": ["hiit", "strength_training"],
                    "intensa": True, "clase": "azul"}],
    "dias_pierna": [], "done_ratio": 0.7, "ceiling_tolerance_min": 2,
}


def act(id, dia, tipo="hiit", dur=3600, z=(0, 0, 0, 0, 0), **extra):
    a = {"activityId": id, "startTimeLocal": f"{dia} 18:00:00", "duration": dur,
         "activityType": {"typeKey": tipo}}
    for i, s in enumerate(z):
        a[f"hrTimeInZone_{i + 1}"] = s
    return {**a, **extra}


def test_zones_karvonen():
    z = m.zones(190, 60, [50, 60, 70, 80, 90])
    assert len(z) == 5
    assert z[1] == ("Z2", 138, 151)
    assert z[4] == ("Z5", 177, 190)


def test_rhr_7d_con_huecos():
    ds = [{"calendarDate": f"2026-10-{d:02d}", "heartRate": {"restingValue": v}}
          for d, v in [(10, 60), (11, 62), (12, None), (14, 64), (16, 999)]]
    ds.append({"calendarDate": "2026-10-13"})  # sin heartRate
    # día 16: la ventana es 9..15, el 999 del día 16 queda fuera
    assert m.rhr_7d(ds, date(2026, 10, 16)) == 62
    assert m.rhr_7d(ds, date(2026, 10, 1)) is None


def test_rhr_solo_con_noche_de_sueno():
    ds = [{"calendarDate": "2026-11-12", "heartRate": {"minValue": 60, "restingValue": 61}},
          {"calendarDate": "2026-11-14", "heartRate": {"minValue": 69, "restingValue": 69}}]
    sleep = [{"calendarDate": "2026-11-12", "sleepTimeSeconds": 24720},
             {"calendarDate": None, "sleepTimeSeconds": None}]
    out = m.rhr_con_sueno(ds, sleep)
    assert out[0]["heartRate"]["restingValue"] == 61
    assert out[1]["heartRate"] == {"minValue": 69, "restingValue": None}
    assert ds[1]["heartRate"]["restingValue"] == 69  # no muta la entrada


def test_classify():
    assert m.classify(act(1, "2026-10-01", "running"), CFG) == "run"
    assert m.classify(act(1, "2026-10-01", "treadmill_running"), CFG) == "run"
    assert m.classify(act(1, "2026-10-01", "hiit"), CFG) == "crossfit"
    assert m.classify(act(1, "2026-10-01", "indoor_cycling"), CFG) is None


def test_zone_minutes_sin_z0():
    zm = m.zone_minutes(act(1, "2026-10-01", dur=3600, z=(60, 120, 180, 0, 0)))
    assert zm == {"Z1": 1, "Z2": 2, "Z3": 3, "Z4": 0, "Z5": 0}
    assert "Z0" not in zm


def test_week_distribution_80_10_10():
    lun = date(2026, 10, 26)
    acts = [act(1, "2026-10-26", z=(0, 4800, 600, 600, 0)),   # 80 / 10 / 10 min
            act(2, "2026-10-25", z=(0, 6000, 0, 0, 0)),       # domingo anterior: fuera
            act(3, "2026-11-02", z=(0, 0, 6000, 0, 0))]       # lunes siguiente: fuera
    d = m.week_distribution(acts, lun)
    assert round(d["bajo"]) == 80 and round(d["limbo"]) == 10 and round(d["alto"]) == 10
    assert m.week_distribution([], lun)["bajo"] == 0.0


def test_esfuerzo_casos_de_la_especificacion():
    assert m.esfuerzo({"Z2": 28}) == 3.0                                            # Z2 continuo
    hiit = {"Z0": 5, "Z1": 15, "Z4": 15, "Z5": 5}                                   # 15' Z4 + 5' Z5 + 20' suave
    assert m.esfuerzo(hiit) == 8.0
    assert m.esfuerzo({"Z1": 30, "Z3": 10, "Z0": 20}) == 3.2                        # mitad dura = 10' Z3 + 20' Z1
    assert m.esfuerzo({}) is None and m.esfuerzo({"Z2": 0.0}) is None


def test_esfuerzo_los_descansos_no_lo_bajan():
    solo_trabajo = {"Z4": 10}
    con_descansos = {"Z4": 10, "Z1": 6, "Z0": 4}
    assert m.esfuerzo(solo_trabajo) == m.esfuerzo(con_descansos) == 7.5
    assert m.esfuerzo({"Z4": 4, "Z2": 30}) == 4.1    # un pico corto en una sesión larga pesa poco


def test_session_and_week_load():
    lun = date(2026, 10, 26)
    cfg = {**CFG, "zonas": ZONAS_T}
    acts = [act(1, "2026-10-26", dur=3600, z=(0, 0, 0, 3600, 0)),     # 60' en Z4 -> esfuerzo 7.5
            act(2, "2026-10-27", "running", dur=1800, z=(0, 1800, 0, 0, 0)),   # 30' en Z2 -> 3.0
            {"activityId": 3, "startTimeLocal": "2026-10-28 18:00:00", "duration": 3600,
             "activityType": {"typeKey": "hiit"}},                    # sin zonas del reloj: sin carga
            act(4, "2026-10-29", "indoor_cycling")]
    assert m.session_load(acts[0], {}, cfg) == 450
    assert m.session_load(acts[2], {}, cfg) is None
    assert m.week_load(acts, {}, lun, cfg) == {"crossfit": 450, "run": 90, "total": 540}


def test_ayer_duro_toma_el_esfuerzo_mas_alto():
    cfg = {**CFG, "zonas": ZONAS_T}
    d = date(2026, 10, 24)
    acts = [act(1, "2026-10-23", dur=3600, z=(0, 3600, 0, 0, 0)),
            act(2, "2026-10-23", "strength_training", dur=1800, z=(0, 0, 0, 1800, 0)),
            act(3, "2026-10-22", dur=3600, z=(0, 0, 0, 0, 3600)),        # anteayer: no cuenta
            act(4, "2026-10-23", "running", dur=1800, z=(0, 0, 0, 1800, 0))]   # corrida: no cuenta
    r = m.ayer_duro(d, acts, {"2": {"rpe": 7.0}}, cfg)
    assert r == {"categoria": "CrossFit", "esfuerzo": 7.5, "rpe": 7.0}
    assert m.ayer_duro(d, [acts[2]], {}, cfg) is None
    assert m.ayer_duro(d, [], {}, cfg) is None


HRV_OK = {"calendarDate": "2026-10-24", "lastNightAvg": 34, "status": "BALANCED",
          "baseline": {"lowUpper": 28, "balancedLow": 30, "balancedUpper": 38}}


def test_signal_hrv():
    d = date(2026, 10, 24)
    assert m.signal_hrv(d, [HRV_OK])["estado"] == "ok"
    fuera = m.signal_hrv(d, [{**HRV_OK, "lastNightAvg": 29}])
    assert fuera["estado"] == "fuera" and fuera["hrv_baja"] is False
    assert m.signal_hrv(d, [{**HRV_OK, "lastNightAvg": 27}])["hrv_baja"] is True
    assert m.signal_hrv(d, [{**HRV_OK, "status": "LOW"}])["hrv_baja"] is True
    assert m.signal_hrv(d, [])["estado"] == "sin_dato"


def test_signal_rhr():
    ds = [{"calendarDate": f"2026-10-{d}", "heartRate": {"restingValue": 60}} for d in range(10, 17)]
    d = date(2026, 10, 17)
    hoy = lambda v: ds + [{"calendarDate": "2026-10-17", "heartRate": {"restingValue": v}}]  # noqa: E731
    assert m.signal_rhr(d, hoy(64), CFG)["estado"] == "ok"      # igual a promedio + 4
    assert m.signal_rhr(d, hoy(65), CFG)["estado"] == "fuera"
    assert m.signal_rhr(d, ds, CFG)["estado"] == "sin_dato"     # sin dato de hoy


def test_signal_sleep():
    d = date(2026, 10, 24)
    assert m.signal_sleep(d, [{"calendarDate": "2026-10-24", "sleepTimeSeconds": 23400}], CFG)["estado"] == "ok"
    assert m.signal_sleep(d, [{"calendarDate": "2026-10-24", "sleepTimeSeconds": 23399}], CFG)["estado"] == "fuera"
    assert m.signal_sleep(d, [{"calendarDate": "2026-10-23", "sleepTimeSeconds": 30000}], CFG)["estado"] == "sin_dato"


def test_signal_sleep_texto_hmin():
    d = date(2026, 10, 24)
    s = m.signal_sleep(d, [{"calendarDate": "2026-10-24", "sleepTimeSeconds": 23340}], CFG)
    assert s["texto"] == "Sueño 6 h 29 min, mínimo 6 h 30 min"
    assert s["estado"] == "fuera" and round(s["valor"], 2) == 6.48


def test_signals_completo():
    data = {"hrv": [HRV_OK], "daily_summaries": [], "sleep": [], "activities": [], "details": {}}
    s = m.signals(date(2026, 10, 24), data, CFG)
    assert set(s) == {"hrv", "rhr", "sueno"}
    assert s["hrv"]["estado"] == "ok" and s["rhr"]["estado"] == "sin_dato"


def _sigs(hrv="ok", rhr="ok", sueno="ok", baja=False):
    mk = lambda e, **k: {"estado": e, **k}  # noqa: E731
    return {"hrv": mk(hrv, hrv_baja=baja), "rhr": mk(rhr), "sueno": mk(sueno)}


def test_traffic_light_tabla():
    casos = [
        (_sigs(), None, "verde", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato"), None, "verde", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato", sueno="sin_dato"), None, "sin_datos", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato", sueno="sin_dato"), "rojo", "sin_datos", False),
        (_sigs(sueno="fuera"), None, "amarillo", False),
        (_sigs(sueno="fuera", rhr="fuera"), None, "rojo", False),
        (_sigs(hrv="fuera", baja=True), None, "rojo", False),
        (_sigs(hrv="fuera"), None, "amarillo", False),
        (_sigs(sueno="fuera", rhr="fuera"), "rojo", "rojo", True),
        (_sigs(sueno="fuera", rhr="fuera"), "amarillo", "rojo", False),
        (_sigs(), "rojo", "verde", False),
    ]
    for sigs, prev, color, repetir in casos:
        r = m.traffic_light(sigs, prev)
        assert (r["color"], r["repetir_semana"]) == (color, repetir)


def test_week_index_bordes():
    ini = date(2026, 10, 26)
    assert m.week_index(date(2026, 10, 25), ini) is None
    assert m.week_index(ini, ini) == 1
    assert m.week_index(date(2026, 11, 2), ini) == 2
    assert m.week_index(date(2027, 1, 17), ini) == 12
    assert m.week_index(date(2027, 1, 18), ini) is None


def test_week_index_con_repetidas():
    ini = date(2026, 10, 26)
    sem = lambda n: ini + timedelta(weeks=n - 1)  # noqa: E731  (semana calendario n)
    rep = [3]
    assert [m.week_index(sem(n), ini, rep) for n in (1, 2, 3, 4, 5)] == [1, 2, 3, 3, 4]
    assert m.week_index(sem(13), ini, rep) == 12
    assert m.week_index(sem(14), ini, rep) is None
    assert m.week_index(sem(14), ini, []) is None
    assert m.week_index(sem(13), ini, []) is None
    # una semana repetida dos veces
    assert [m.week_index(sem(n), ini, [3, 3]) for n in (3, 4, 5, 6)] == [3, 3, 3, 4]
    assert m.week_index(ini - timedelta(days=1), ini, rep) is None


def sesion(id_, tipo, name, minutos, suave):
    return {"id": id_, "tipo": tipo, "name": name, "minutes": minutos,
            "steps": [{"kind": "run", "minutes": minutos, "zone": "Z1-Z2"}],
            "easy": {"name": "Suave", "minutes": suave, "steps": []}}


WEEK = {"sessions": [sesion("z2a", "z2", "Z2 #1", 20, 15), sesion("z2b", "z2", "Z2 #2", 20, 15),
                     sesion("larga", "larga", "Larga", 40, 30)]}
# 2026-11-16 es lunes: mié 18, vie 20, sáb 21, dom 22
MIE, VIE, SAB, DOM = "2026-11-18", "2026-11-20", "2026-11-21", "2026-11-22"


def corr(fecha, minutos, luz="verde"):
    return {"fecha": fecha, "minutos": minutos, "luz": luz}


def estados(runs):
    return [(s["id"], s["estado"], s["fecha"]) for s in m.assign_sessions(WEEK, runs, CFG)]


def test_assign_semana_completa():
    r = m.assign_sessions(WEEK, [corr(MIE, 21), corr(VIE, 20), corr(DOM, 41)], CFG)
    assert [s["estado"] for s in r] == ["hecha"] * 3
    assert r[2]["fecha"] == DOM and r[2]["minutos"] == 41 and r[2]["name"] == "Larga"


def test_assign_sabado_corto_no_es_larga():
    r = estados([corr(SAB, 25)])          # 25 + 0.5 < 28
    assert r[0] == ("z2a", "hecha", SAB) and r[2] == ("larga", "pendiente", None)


def test_assign_larga_justo_en_el_umbral():
    r = m.assign_sessions(WEEK, [corr(DOM, 27.6)], CFG)
    assert r[2]["estado"] == "hecha" and r[0]["estado"] == "pendiente"


def test_assign_z2_incompleta():
    r = m.assign_sessions(WEEK, [corr(MIE, 12)], CFG)
    assert r[0]["estado"] == "incompleta" and r[0]["ajustada"] is False


def test_assign_dia_amarillo_ajustada():
    r = m.assign_sessions(WEEK, [corr(MIE, 20, "amarillo")], CFG)
    assert r[0]["estado"] == "hecha" and r[0]["ajustada"] is True
    # 11' en día amarillo: 11.5 >= 0.7 * 15 = 10.5 -> hecha; 9' no
    assert m.assign_sessions(WEEK, [corr(MIE, 11, "rojo")], CFG)[0]["estado"] == "hecha"
    assert m.assign_sessions(WEEK, [corr(MIE, 9, "amarillo")], CFG)[0]["estado"] == "incompleta"


def test_assign_sin_datos_cuenta_como_verde():
    r = m.assign_sessions(WEEK, [corr(MIE, 12, "sin_datos")], CFG)
    assert r[0]["estado"] == "incompleta" and r[0]["ajustada"] is False


def test_assign_sobrante_y_larga_mas_larga():
    r = estados([corr(MIE, 20), corr(VIE, 20), corr(SAB, 30), corr(DOM, 45)])
    # la más larga del fin de semana (dom 45) es la Larga; sáb 30 llena z2a... pero z2a ya tiene mié
    assert r == [("z2a", "hecha", MIE), ("z2b", "hecha", VIE), ("larga", "hecha", DOM)]


def test_assign_cuatro_corridas_sin_larga():
    r = estados([corr(MIE, 20), corr(VIE, 20), corr("2026-11-19", 20), corr(SAB, 20)])
    assert [x[1:] for x in r] == [("hecha", MIE), ("hecha", VIE), ("pendiente", None)]


def test_assign_sin_corridas():
    assert [s["estado"] for s in m.assign_sessions(WEEK, [], CFG)] == ["pendiente"] * 3


def ses(id_, tipo, estado="pendiente"):
    return {"id": id_, "tipo": tipo, "estado": estado}


VERDE = {"color": "verde", "repetir_semana": False}


def test_today_card_ramas():
    pend = [ses("z2a", "z2"), ses("z2b", "z2"), ses("larga", "larga")]
    hecha = [ses("z2a", "z2", "hecha"), ses("z2b", "z2"), ses("larga", "larga")]
    todas = [ses("z2a", "z2", "hecha"), ses("z2b", "z2", "hecha"), ses("larga", "larga", "hecha")]
    lun, mie, vie, dom = date(2026, 11, 16), date(2026, 11, 18), date(2026, 11, 20), date(2026, 11, 22)
    assert m.today_card(lun, VERDE, pend, [], CFG)["tipo"] == "sesion"   # nunca se adivina CrossFit por el día
    assert m.today_card(mie, VERDE, pend, [act(1, "2026-11-18")], CFG)["tipo"] == "otra"
    assert m.today_card(lun, VERDE, hecha, [act(2, "2026-11-16", "running")], CFG)["tipo"] == "hecha_hoy"
    assert m.today_card(mie, VERDE, hecha, [act(2, "2026-11-18", "running"), act(3, "2026-11-18")], CFG)["tipo"] == "otra"
    assert m.today_card(mie, VERDE, hecha, [], CFG)["sesion_id"] == "z2b"
    t = m.today_card(mie, VERDE, pend, [], CFG)
    assert t["version"] == "normal" and t["sesion_id"] == "z2a" and t["aviso"] is None
    assert m.today_card(mie, {**VERDE, "color": "amarillo"}, pend, [], CFG)["version"] == "suave"
    assert m.today_card(mie, {**VERDE, "color": "rojo"}, pend, [], CFG)["version"] == "descanso"
    assert m.today_card(mie, VERDE, todas, [], CFG)["texto"] == "Semana completa"
    assert m.today_card(mie, VERDE, todas, [], CFG)["tipo"] == "completa"
    assert m.today_card(mie, VERDE, [], [], CFG)["tipo"] == "sin_plan"
    rojo2 = {"color": "rojo", "repetir_semana": True}
    assert m.today_card(mie, rojo2, pend, [], CFG)["aviso"] == "Repetir la semana"
    # fin de semana: la Larga primero; si ya no está pendiente, la primera Z2
    assert m.today_card(dom, VERDE, hecha, [], CFG)["sesion_id"] == "larga"
    solo_z2 = [ses("z2a", "z2"), ses("z2b", "z2", "hecha"), ses("larga", "larga", "hecha")]
    assert m.today_card(dom, VERDE, solo_z2, [], CFG)["sesion_id"] == "z2a"
    # entre semana, si solo falta la Larga: aviso
    solo_larga = [ses("z2a", "z2", "hecha"), ses("z2b", "z2", "incompleta"), ses("larga", "larga")]
    t = m.today_card(vie, VERDE, solo_larga, [], CFG)
    assert t["tipo"] == "sesion" and t["sesion_id"] == "larga" and "sábado o domingo" in t["aviso"]
    # incompleta no es pendiente
    inc = [ses("z2a", "z2", "incompleta"), ses("z2b", "z2", "hecha"), ses("larga", "larga", "hecha")]
    assert m.today_card(vie, VERDE, inc, [], CFG)["tipo"] == "completa"


def test_today_card_sin_datos():
    pend = [ses("z2a", "z2"), ses("larga", "larga")]
    mie = date(2026, 11, 18)
    t = m.today_card(mie, {"color": "sin_datos", "fuera": 0, "repetir_semana": False}, pend, [], CFG)
    assert t["version"] == "normal" and t["aviso"] == "Sin datos de anoche: decide por cómo te sientes"
    rojo = {"color": "sin_datos", "fuera": 0, "repetir_semana": True}
    assert m.today_card(mie, rojo, pend, [], CFG)["aviso"].startswith("Repetir la semana · Sin datos")


TRAMOS_12NOV = [{"tipo": "RWD_WALK", "seg": 657.949, "m": 892.64, "fc": 129.0, "n": 9},
                {"tipo": "RWD_RUN", "seg": 1645.999, "m": 3466.89, "fc": 140.0, "n": 9},
                {"tipo": "RWD_STAND", "seg": 30, "m": 0, "fc": 100.0, "n": 1}]


def test_run_walk_caso_12_nov():
    a = act(7, "2026-11-12", "running")
    rw = m.run_walk(a, {"7": {"rpe": 2, "splits": TRAMOS_12NOV}})
    assert round(rw["trote_min"], 1) == 27.4 and round(rw["camina_min"], 1) == 11.0
    assert round(rw["pct_trote"], 1) == 71.4 and rw["caminatas"] == 9
    assert round(rw["patron_trote_min"], 2) == 3.05 and round(rw["patron_camina_min"], 2) == 1.22
    assert round(rw["ritmo_trote_s"]) == 475 and rw["fc_trote"] == 140.0
    assert round(rw["km_trote"], 2) == 3.47


def test_run_walk_sin_caminata_sin_tramos_y_respaldo():
    solo = {"7": {"splits": [{"tipo": "RWD_RUN", "seg": 1200, "m": 3000, "fc": 141, "n": 1}]}}
    rw = m.run_walk(act(7, "2026-11-12", "running"), solo)
    assert rw["caminatas"] == 0 and rw["pct_trote"] == 100 and rw["patron_camina_min"] is None
    assert m.run_walk(act(7, "2026-11-12", "running"), {}) is None
    assert m.run_walk(act(7, "2026-11-12", "running"), {"7": {"splits": []}}) is None
    resp = act(7, "2026-11-12", "running", splitSummaries=[
        {"splitType": "RWD_RUN", "duration": 600, "distance": 1500, "noOfSplits": 2},
        {"splitType": "RWD_WALK", "duration": 300, "distance": 400, "noOfSplits": 2}])
    rw = m.run_walk(resp, {"7": {"rpe": None}})
    assert rw["fc_trote"] is None and round(rw["pct_trote"], 1) == 66.7 and rw["ritmo_trote_s"] == 400


def test_run_check():
    a = act(1, "2026-11-12", "running", z=(0, 0, 90, 30, 0))           # 2.0' sobre el techo
    assert m.run_check(a, None) == {"min_sobre_techo": 2.0, "tolerancia_min": 2, "techo_ok": True}
    b = act(1, "2026-11-12", "running", z=(0, 0, 360, 0, 0))           # 6'
    assert m.run_check(b, None)["techo_ok"] is False
    con_picos = {"steps": [{"kind": "run"}, {"kind": "run", "optional": True}]}
    r = m.run_check(b, con_picos)
    assert r["tolerancia_min"] == 4 and r["techo_ok"] is False
    assert m.run_check(act(1, "2026-11-12", "running", z=(0, 0, 240, 0, 0)), con_picos)["techo_ok"] is True
    anidado = {"steps": [{"kind": "repeat", "steps": [{"kind": "run", "optional": True}]}]}
    assert m.run_check(a, anidado)["tolerancia_min"] == 4


def test_rolling_mean_con_huecos():
    v = [10, None, 20, 30, None, None, None, None, None, 40]
    r = m.rolling_mean(v)
    assert r[0] is None and r[1] is None          # menos de 3 valores
    assert r[3] == 20                             # 10, 20, 30
    assert r[6] == 20
    assert r[8] is None                           # ventana 2..8: solo 20 y 30
    assert r[9] is None                           # ventana 3..9: 30 y 40
    assert m.rolling_mean([1, 2, 3, 4], ventana=2, minimo=2) == [None, 1.5, 2.5, 3.5]
    assert m.rolling_mean([]) == []


def test_run_rows():
    acts = [act(2, "2026-10-22", "treadmill_running", dur=1800, averageHR=140.0, distance=2500.0),
            act(1, "2026-10-21", "running", dur=1800, z=(300, 900, 300, 300, 0),
                averageHR=140.0, distance=4000.0, splitSummaries=[
                    {"splitType": "RWD_RUN", "duration": 1200, "distance": 3000, "noOfSplits": 3}]),
            act(3, "2026-10-23", "hiit")]
    filas = m.run_rows(acts, {}, CFG)
    assert [f["fecha"] for f in filas] == ["2026-10-21", "2026-10-22"]
    assert "eficiencia" not in filas[0]
    assert filas[0]["minutos"] == 30 and filas[0]["km"] == 4 and round(filas[0]["pct_z1z2"]) == 67
    assert filas[0]["caminadora"] is False and filas[0]["pct_trote"] == 100
    assert filas[1]["caminadora"] is True and filas[1]["pct_z1z2"] is None
    assert filas[1]["pct_trote"] is None and filas[1]["ritmo_trote_s"] is None


def fila(fecha, pct, ritmo_ref):
    return {"fecha": fecha, "pct_trote": pct, "ritmo_ref_s": ritmo_ref}


def test_progress_summary():
    hoy = date(2026, 12, 14)
    filas = [fila("2026-11-02", 58, 460), fila("2026-11-10", 58, 460),   # antes: 19 oct – 16 nov; ahora: 16 nov – 14 dic
             fila("2026-10-25", 58, 460), fila("2026-10-30", 58, 460),
             fila("2026-12-01", 70, 445), fila("2026-12-10", 66, 445)]
    assert m.progress_summary(filas, hoy, 4, 144) == "Trotas 68 % del tiempo (antes 58 %) · a 144 lpm: 7:40 → 7:25 /km"
    assert m.progress_summary([], hoy, 4) == "Aún no hay corridas suficientes para comparar"
    sin_ritmo = [fila("2026-12-01", 70, None), fila("2026-10-25", 58, 460)]
    assert m.progress_summary(sin_ritmo, hoy, 4, 144) == (
        "Trotas 70 % del tiempo (antes 58 %) · sin corridas en Z2 en las últimas 4 semanas para comparar el ritmo")


def test_progress_summary_dice_cual_periodo_falta():
    hoy = date(2026, 12, 14)
    solo_ahora = [fila("2026-12-01", 70, 445), fila("2026-12-05", None, 450)]
    assert m.progress_summary(solo_ahora, hoy, 8, 144) == "Sin corridas en Z2 en las 8 semanas anteriores para comparar el ritmo"


def test_periodo_filas_es_un_solo_conjunto():
    hoy = date(2026, 12, 14)
    filas = [fila("2026-11-16", 1, 1), fila("2026-11-17", 2, 2), fila("2026-12-14", 3, 3), fila("2026-11-10", 4, 4)]
    assert [f["pct_trote"] for f in m.periodo_filas(filas, hoy, 4)] == [2, 3]          # (16 nov, 14 dic]
    assert [f["pct_trote"] for f in m.periodo_filas(filas, hoy, 4, 1)] == [1, 4]


FILA_RITMO = {"caminadora": False, "carrera": False, "ritmo_trote_s": 480.0, "fc_trote": 148.0,
              "minutos": 40, "km": 5.0, "fc_prom": 140}


def test_ritmo_fc_ref_lleva_el_ritmo_a_la_mitad_de_z2():
    zonas = m.zones(190, 60, [50, 60, 70, 80, 90])        # Z2 138–151, ref 144 (o 145 al redondear)
    ref = m.fc_referencia(zonas)
    assert round(m.ritmo_fc_ref(FILA_RITMO, zonas), 1) == round(480 * 148 / ref, 1)
    assert m.ritmo_fc_ref({**FILA_RITMO, "fc_trote": ref}, zonas) == 480.0          # a la FC ref, el mismo ritmo
    assert m.ritmo_fc_ref({**FILA_RITMO, "fc_trote": 137}, zonas) is None            # trote fuera de Z2 (debajo)
    assert m.ritmo_fc_ref({**FILA_RITMO, "fc_trote": 152}, zonas) is None            # fuera de Z2 (arriba)
    assert m.ritmo_fc_ref({**FILA_RITMO, "caminadora": True}, zonas) is None
    assert m.ritmo_fc_ref({**FILA_RITMO, "carrera": True}, zonas) is None


def test_ritmo_fc_ref_sin_tramos_usa_ritmo_y_fc_promedio():
    zonas = m.zones(190, 60, [50, 60, 70, 80, 90])
    f = {**FILA_RITMO, "ritmo_trote_s": None, "fc_trote": None, "fc_prom": 144}
    assert m.ritmo_fc_ref(f, zonas) == 480.0 * 144 / m.fc_referencia(zonas)          # 40 min / 5 km = 480 s/km
    assert m.ritmo_fc_ref({**f, "fc_prom": 160}, zonas) is None
    assert m.ritmo_fc_ref({**f, "fc_prom": None}, zonas) is None


def test_max_hr_progress():
    acts = [act(1, "2026-10-20", maxHR=199),   # antes de la correa: no cuenta
            act(2, "2026-10-27", maxHR=180), act(3, "2026-10-29", maxHR=181)]
    p = m.max_hr_progress(acts, CFG)
    assert (p["pico"], p["estimacion"], p["semanas_medidas"], p["listo"]) == (181, 184, 1, False)
    acts.append(act(4, "2026-11-03", maxHR=203))
    p = m.max_hr_progress(acts, CFG)
    assert p["estimacion"] == 206 and p["revisar"] and p["listo"]
    bajo = m.max_hr_progress([act(5, "2026-10-27", maxHR=170)], CFG)
    assert bajo["estimacion"] == 183 and not bajo["revisar"]
    assert m.max_hr_progress([], CFG)["estimacion"] is None


def test_watch_max_hr():
    assert m.watch_max_hr([{"sport": "RUNNING", "maxHeartRateUsed": 195},
                           {"sport": "DEFAULT", "maxHeartRateUsed": 189}]) == 189
    assert m.watch_max_hr([]) is None


def test_max_hr_above_watch():
    assert m.max_hr_above_watch(189, 189) is None
    assert m.max_hr_above_watch(None, 189) is None
    assert "192" in m.max_hr_above_watch(192, 189)
    assert "Garmin Connect" in m.max_hr_above_watch(None, None) and "220" in m.max_hr_above_watch(192, None)


def test_motivo():
    assert m.motivo(_sigs()) is None
    assert m.motivo(_sigs(rhr="fuera")) == "FC en reposo alta"
    assert m.motivo(_sigs(sueno="fuera", rhr="fuera")) == "FC en reposo alta · Dormiste poco"
    assert m.motivo(_sigs(baja=True)) == "HRV baja"
    assert m.motivo(_sigs(hrv="fuera", baja=True)) == "HRV baja"


def test_motivo_despues_de_un_dia_duro():
    duro = {"categoria": "CrossFit", "esfuerzo": 8.7, "rpe": 7.0}
    assert m.motivo(_sigs(hrv="fuera"), CFG, duro) == "HRV baja después de un día duro"
    assert m.motivo(_sigs(hrv="fuera"), {**CFG, "esfuerzo_duro": 9}, duro) == "HRV baja"          # umbral de la config
    assert m.motivo(_sigs(hrv="fuera"), CFG, {**duro, "esfuerzo": 7.9}) == "HRV baja"
    assert m.motivo(_sigs(), CFG, duro) is None                                                    # sin señal fuera no hay motivo
    assert m.motivo(_sigs(hrv="fuera"), CFG, {**duro, "esfuerzo": None}) == "HRV baja"


def test_today_card_proxima_id():
    pend = [ses("z2a", "z2"), ses("z2b", "z2"), ses("larga", "larga")]
    z2_hechas = [ses("z2a", "z2", "hecha"), ses("z2b", "z2", "hecha"), ses("larga", "larga")]
    mar, vie, mie = date(2026, 11, 17), date(2026, 11, 20), date(2026, 11, 18)
    assert m.today_card(mar, VERDE, pend, [act(1, "2026-11-17")], CFG)["proxima_id"] == "z2a"   # CrossFit registrado hoy
    jue = date(2026, 11, 19)
    assert m.today_card(jue, VERDE, z2_hechas, [act(1, "2026-11-19")], CFG)["proxima_id"] == "larga"   # mañana viernes
    run_hoy = [act(2, "2026-11-20", "running")]
    assert m.today_card(vie, VERDE, z2_hechas, run_hoy, CFG)["proxima_id"] == "larga"  # mañana sábado
    assert m.today_card(mie, VERDE, pend, [], CFG)["proxima_id"] is None   # tipo sesion
    assert m.today_card(mar, VERDE, [], [], CFG)["proxima_id"] is None


# --- v3.2 F2: mejora y composición corporal ---

HOY = date(2026, 11, 14)   # lunes de esa semana: 9 nov; ventanas 12 oct–8 nov y 14 sep–11 oct





INBODY = {"prime": "2024-05-25", "mediciones": [
    {"fecha": "2026-11-13", "hora": "08:29", "peso_kg": 93.8, "mme_kg": 39.1, "pgc": 27.1,
     "masa_grasa_kg": 25.5, "puntuacion": 75, "grasa_visceral": 10, "grasa_visceral_rango": [1, 9], "nota": "x"},
    {"fecha": "2024-05-25", "hora": "08:34", "peso_kg": 86.2, "mme_kg": 38.4, "pgc": 22.3},
    {"fecha": "2026-10-08", "peso_kg": 94.8, "mme_kg": 38.0, "pgc": 30.1}]}


def test_composicion_deltas_y_meta():
    c = m.composicion(INBODY)
    assert [x["fecha"] for x in c["mediciones"]] == ["2024-05-25", "2026-10-08", "2026-11-13"]
    u = c["ultima"]
    assert (u["delta_pgc"], u["delta_mme"], u["delta_peso"]) == (-3.0, 1.1, -1.0)
    assert c["meta"] == {"faltan_pgc": 4.8, "mme_ok": True, "faltan_mme": 0.0}
    assert c["prime"]["fecha"] == "2024-05-25" and c["visceral_rango"] == [1, 9]
    texto = str(c)
    assert "nota" not in texto and "hora" not in texto


def test_composicion_masa_grasa_calculada_y_sin_prime():
    c = m.composicion({"mediciones": INBODY["mediciones"][1:]})
    assert c["mediciones"][0]["masa_grasa_kg"] == 19.2          # 86.2 × 22.3 %
    assert c["prime"]["fecha"] == "2024-05-25"                  # sin `prime`: la de menor % de grasa
    una = m.composicion({"mediciones": INBODY["mediciones"][1:2]})
    assert una["ultima"]["delta_pgc"] is None and una["meta"]["faltan_pgc"] == 0
    assert m.composicion(None) is None and m.composicion({"mediciones": []}) is None


# --- v4 F1: categorías genéricas ---

CFG3 = {**CFG, "categorias": [
    {"id": "fuerza", "nombre": "Fuerza", "letra": "F", "tipos": ["strength_training"], "intensa": False, "clase": "azul"},
    {"id": "hiit", "nombre": "HIIT", "letra": "H", "tipos": ["hiit"], "intensa": True, "clase": "aqua"},
    {"id": "cardio", "nombre": "Cardio", "letra": "B", "tipos": ["cycling"], "intensa": False, "clase": "violeta"}],
    "dias_pierna": [0]}


def test_classify_categorias():
    assert m.classify(act(1, "2026-10-01", "strength_training"), CFG3) == "fuerza"
    assert m.classify(act(1, "2026-10-01", "cycling"), CFG3) == "cardio"
    assert m.classify(act(1, "2026-10-01", "walking"), CFG3) is None


def test_week_load_por_categoria():
    lun = date(2026, 10, 19)
    cfg = {**CFG3, "zonas": ZONAS_T}
    acts = [act(1, "2026-10-19", "strength_training", dur=3600, z=(0, 3600, 0, 0, 0)),
            act(2, "2026-10-20", "hiit", dur=1800, z=(0, 0, 0, 1800, 0)),
            act(3, "2026-10-21", "running", dur=1800, z=(0, 1800, 0, 0, 0)), act(4, "2026-10-22", "walking")]
    c = m.week_load(acts, {}, lun, cfg)
    assert c == {"fuerza": 180.0, "hiit": 225.0, "cardio": 0.0, "run": 90.0, "total": 495.0}


def test_today_card_otra_con_nombre_de_categoria():
    lun = date(2026, 11, 16)
    t = m.today_card(lun, VERDE, [ses("z2a", "z2")], [], CFG3)
    assert t["tipo"] == "sesion" and "categoria" not in t and "CrossFit" not in t["texto"]   # sin actividad hoy
    t = m.today_card(lun, VERDE, [ses("z2a", "z2")], [act(1, "2026-11-16", "hiit")], CFG3)
    assert (t["tipo"], t["categoria"], t["texto"]) == ("otra", "HIIT", "Hoy: HIIT ✓")
    # una categoría no intensa hecha no tapa la corrida
    mar = date(2026, 11, 17)
    t = m.today_card(mar, VERDE, [ses("z2a", "z2")], [act(1, "2026-11-17", "strength_training")], CFG3)
    assert t["tipo"] == "sesion"


def test_aviso_dia_de_pierna():
    mar = date(2026, 11, 17)   # ayer lunes = pierna
    solo_larga = [ses("z2a", "z2", "hecha"), ses("z2b", "z2", "hecha"), ses("larga", "larga")]
    ayer = [act(1, "2026-11-16", "strength_training")]
    t = m.today_card(mar, VERDE, solo_larga, ayer, CFG3)
    assert t["sesion_id"] == "larga" and "Ayer pierna: hoy mejor la Z2 y deja la Larga para mañana" in t["aviso"]
    cal = [ses("z2a", "z2", "hecha"), ses("cal", "calidad")]
    assert "deja la calidad para mañana" in m.today_card(mar, VERDE, cal, ayer, CFG3)["aviso"]
    # Garmin no registró nada ayer: sin aviso (solo cuenta lo registrado)
    assert "Ayer pierna" not in m.today_card(mar, VERDE, solo_larga, [], CFG3)["aviso"]
    # una Z2 pendiente no lleva aviso, y otro día tampoco
    assert m.today_card(mar, VERDE, [ses("z2a", "z2")], [], CFG3)["aviso"] is None
    assert m.today_card(date(2026, 11, 19), VERDE, solo_larga, [], CFG3)["aviso"] == "La larga va el sábado o domingo"


def test_max_hr_progress_sin_correa_configurada():
    p = m.max_hr_progress([act(1, "2026-10-27", maxHR=180)], {**CFG, "fc_max_correa_desde": None})
    assert p["configurada"] is False and p["estimacion"] is None and p["sesiones"] == []


# --- carreras y mejores marcas ---

CFG_CARRERA = {"run_types": ["running", "treadmill_running"], "carreras": ["2026-11-21"], "max_hr": 190}


def _corrida(nombre=None, fecha="2026-11-07", evento=None, tipo="running", **kw):
    a = {"activityType": {"typeKey": tipo}, "startTimeLocal": f"{fecha} 07:00:00", "distance": 5000.0, "duration": 2400.0, **kw}
    if nombre is not None:
        a["activityName"] = nombre
    if evento:
        a["eventType"] = {"typeKey": evento}
    return a


def test_es_carrera_por_evento_nombre_y_fecha():
    assert m.es_carrera(_corrida(evento="race"), CFG_CARRERA)
    assert m.es_carrera(_corrida("Mérida CARRERA del Pavo"), CFG_CARRERA)
    assert m.es_carrera(_corrida("Medio Maratón de Mérida"), CFG_CARRERA)
    assert m.es_carrera(_corrida("Mi 10K"), CFG_CARRERA) and m.es_carrera(_corrida("Race day"), CFG_CARRERA)
    assert m.es_carrera(_corrida("Corrida matutina", fecha="2026-11-21"), CFG_CARRERA)
    assert m.es_carrera(_corrida("Maratón", tipo="treadmill_running"), CFG_CARRERA)


def test_es_carrera_negativos():
    assert not m.es_carrera(_corrida("Corrida matutina", evento="uncategorized"), CFG_CARRERA)
    assert not m.es_carrera(_corrida("Trote de 15K pasos"), CFG_CARRERA) and not m.es_carrera(_corrida(), CFG_CARRERA)
    assert not m.es_carrera(_corrida("Carrera", tipo="cycling"), CFG_CARRERA)
    assert not m.es_carrera(_corrida("Embrace the pace"), CFG_CARRERA)


def test_stats_carrera():
    a = _corrida(distance=5049.8, duration=2457.3, averageHR=145.0, maxHR=176.0, fastestSplit_1000=409.3,
                 hrTimeInZone_2=1700, hrTimeInZone_3=240, averageRunningCadenceInStepsPerMinute=151.2, elevationGain=8.4,
                 activityId=7)
    s = m.stats_carrera(a, {"7": {"ritmos_km": [501, 527]}}, CFG_CARRERA)
    assert s["distancia_km"] == 5.05 and s["tiempo_s"] == 2457 and s["ritmo_s"] == 487
    assert s["fc_prom"] == 145 and s["fc_max"] == 176 and s["zonas_min"]["Z2"] == 28.3 and s["zonas_min"]["Z3"] == 4
    assert s["km_mas_rapido_s"] == 409 and s["cadencia"] == 151 and s["desnivel_m"] == 8 and s["km"] == [501, 527]
    vacia = m.stats_carrera(_corrida(), {}, CFG_CARRERA)
    assert vacia["km"] is None and vacia["zonas_min"] is None and vacia["fc_prom"] is None and vacia["km_mas_rapido_s"] is None


def test_ritmos_por_km_interpola():
    # 2.5 km a ritmo constante de 300 s/km, con puntos cada 500 m
    pts = [(i * 500.0, i * 150.0) for i in range(6)]
    assert m.ritmos_por_km(pts) == [300, 300]
    assert m.ritmos_por_km([(0, 0)]) == [] and m.ritmos_por_km([(0, 0), (900, 300)]) == []


def test_comparar_carrera():
    ant = {"fecha": "2026-05-02", "distancia_km": 5.1, "tiempo_s": 2600, "ritmo_s": 510, "fc_prom": 150.0}
    vieja = {"fecha": "2025-01-01", "distancia_km": 5.0, "tiempo_s": 2900, "ritmo_s": 580, "fc_prom": 155.0}
    lejana = {"fecha": "2026-08-01", "distancia_km": 10.0, "tiempo_s": 5000, "ritmo_s": 500, "fc_prom": 160.0}
    hoy = {"fecha": "2026-11-21", "distancia_km": 5.05, "tiempo_s": 2457, "ritmo_s": 487, "fc_prom": 145.0}
    c = m.comparar_carrera(hoy, [vieja, ant, lejana])
    assert c["fecha"] == "2026-05-02" and c["dif_tiempo_s"] == -143 and c["dif_ritmo_s"] == -23 and c["dif_fc"] == -5.0
    assert m.comparar_carrera(hoy, [lejana]) is None and m.comparar_carrera(hoy, []) is None


def test_mejores_marcas():
    h = [_corrida(fecha="2026-06-13", fastestSplit_1000=393.0, fastestSplit_1609=649.0, distance=3000.0),
         _corrida(fecha="2026-11-21", fastestSplit_1000=409.0, fastestSplit_5000=2422.0, distance=5050.0),
         _corrida(fecha="2025-09-28", distance=5510.0, duration=2778.0)]
    out = {x["clave"]: x for x in m.mejores_marcas(h, date(2026, 11, 24))}
    assert list(out) == ["1k", "1mi", "5k", "larga"]
    assert out["1k"]["tiempo_s"] == 393 and out["1k"]["fecha"] == "2026-06-13" and out["1k"]["nuevo"] is False
    assert out["5k"]["tiempo_s"] == 2422 and out["5k"]["ritmo_s"] == 484 and out["5k"]["nuevo"] is True
    assert out["larga"]["distancia_km"] == 5.51 and out["larga"]["tiempo_s"] == 2778 and out["larga"]["fecha"] == "2025-09-28"
    assert m.mejores_marcas([]) == []


# --- hoja InBody ---

def _inbody_pedro():
    import json
    return json.loads((Path(__file__).parent.parent / "plan" / "inbody.json").read_text())


def test_pos_escala_por_tramos():
    escala = [40, 60, 80, 100, 160, 220, 280, 340, 400, 460, 520]   # no lineal: cada tick mide lo mismo
    assert m.pos_escala(40, escala) == 0 and m.pos_escala(10, escala) == 0 and m.pos_escala(600, escala) == 1
    assert m.pos_escala(100, escala) == 0.3 and m.pos_escala(130, escala) == 0.35
    assert 0.5 < m.pos_escala(240, escala) < 0.6   # entre 220 y 280


def test_composicion_hoja_inbody_de_pedro():
    c = m.composicion(_inbody_pedro())
    filas = {f["id"]: f for f in c["hoja"]["musculo_grasa"]}
    assert list(filas) == ["peso", "mme", "masa_grasa"]
    peso = filas["peso"]
    assert peso["zona"] == "alto" and peso["valor"] == 93.8 and peso["pct"] == 133
    assert 0.5 < peso["pos"] < 0.55 and peso["normal_pos"] == [0.2, 0.4]       # 133 % entre 130 y 145
    assert filas["mme"]["estimado"] is True and "estimado" not in peso and 0.45 < filas["mme"]["pos"] < 0.5
    assert 0.52 < filas["masa_grasa"]["pos"] < 0.54 and filas["masa_grasa"]["zona"] == "alto"   # 240 % entre 220 y 280
    obes = {f["id"]: f for f in c["hoja"]["obesidad"]}
    assert obes["imc"]["zona"] == "alto" and obes["pgc"]["valor"] == 27.1 and 0.5 < obes["pgc"]["pos"] < 0.6
    assert c["hoja"]["control_peso"]["peso_ideal_kg"] == 80.4 and c["hoja"]["segmental_grasa"]["tronco"] == [14.0, 314.4]
    assert c["hoja"]["investigacion"]["tmb_kcal"][0] == 1846 and c["hoja"]["composicion_corporal"]["agua_l"][0] == 49.9


def test_composicion_historial_puntuacion_visceral():
    c = m.composicion(_inbody_pedro())
    assert [h["fecha"] for h in c["historial"]][0] == "2024-05-25" and len(c["historial"]) == 4
    assert [h["es_prime"] for h in c["historial"]] == [True, False, False, False]
    # puntuación: desde la primera con puntos; la del 25 oct 2025 (sin hoja) queda como hueco
    assert [(x["fecha"], x["puntos"]) for x in c["puntuacion"]] == [("2024-05-25", 80), ("2025-10-25", None), ("2026-10-08", 69), ("2026-11-13", 75)]
    assert c["puntuacion"][1]["delta"] is None and c["puntuacion"][2]["delta"] == -11   # sin puntos: hueco; el delta salta al anterior con dato
    assert c["puntuacion"][-1]["delta"] == 6
    assert c["visceral"]["valor"] == 10 and c["visceral"]["rango"] == [1, 9] and c["visceral"]["zona"] == "alto"


def test_composicion_puntuacion_con_dos_mediciones_y_sin_hoja():
    inb = {"mediciones": [{"fecha": "2026-01-01", "peso_kg": 90, "mme_kg": 38, "pgc": 30, "puntuacion": 70},
                          {"fecha": "2026-02-01", "peso_kg": 89, "mme_kg": 38.5, "pgc": 29, "puntuacion": 74}]}
    c = m.composicion(inb)
    assert [p["delta"] for p in c["puntuacion"]] == [None, 4]
    assert "hoja" not in c and "visceral" not in c and len(c["historial"]) == 2


def test_hoja_rangos_con_zona():
    r = {x["nombre"]: x for x in m.composicion(_inbody_pedro())["hoja"]["rangos"]}
    assert r["TMB"]["zona"] == "bajo" and r["TMB"]["min"] == 1919 and r["TMB"]["valor"] == 1846
    assert r["Agua corporal"]["zona"] == "alto" and r["Relación cintura-cadera"]["zona"] == "alto"
    assert r["Grado de obesidad"]["grupo"] == "Parámetros de investigación" and r["Peso"]["grupo"] == "Composición corporal"


def test_run_check_variada_suma_su_z3_planeado_a_la_tolerancia():
    ses = {"tipo": "variada", "steps": [{"kind": "run", "minutes": 5, "zone": "Z1"},
                                        {"kind": "repeat", "times": 2, "steps": [{"kind": "run", "minutes": 2, "zone": "Z3"}]}]}
    a = act(1, "2026-11-18", "running", dur=1800, z=(300, 900, 240, 0, 0))   # 4' en Z3
    assert m.run_check(a, ses, CFG)["tolerancia_min"] == CFG["ceiling_tolerance_min"] + 4
    assert m.run_check(a, ses, CFG)["techo_ok"] is True
    assert m.run_check(a, {**ses, "tipo": "z2"}, CFG)["techo_ok"] is False


# --- v4.2 F6: otros entrenos y 80/20 ---


# --- v4.3 F1: serie de FC y minutos por zona ---

ZONAS_T = m.zones(190, 60, [50, 60, 70, 80, 90])   # Z1 125, Z2 138, Z3 151, Z4 164, Z5 177


def detalle_t(filas):
    claves = ["sumDuration", "sumDistance", "directHeartRate", "directLatitude"]
    return {"metricDescriptors": [{"key": k, "metricsIndex": i} for i, k in enumerate(claves)],
            "activityDetailMetrics": [{"metrics": [s, d, fc, 20.9]} for s, d, fc in filas]}


def test_serie_de_detalle_cada_5s_sin_gps():
    filas = [(t, t * 3.0, 140 + t % 3) for t in range(0, 31)]     # una muestra por segundo
    serie = m.serie_de_detalle(detalle_t(filas))
    assert [x[0] for x in serie] == [0, 5, 10, 15, 20, 25, 30]
    assert all(len(x) == 3 for x in serie)                           # solo [seg, metros, fc]
    assert serie[1] == [5, 15, 142]


def test_serie_de_detalle_sin_descriptor_es_vacia():
    d = detalle_t([(0, 0, 140), (5, 10, 141)])
    d["metricDescriptors"] = [x for x in d["metricDescriptors"] if x["key"] != "directHeartRate"]
    assert m.serie_de_detalle(d) == []
    assert m.serie_de_detalle({}) == []


def test_serie_de_detalle_muestras_gruesas_no_se_repiten():
    serie = m.serie_de_detalle(detalle_t([(0, 0, 100), (12, 30, 120), (13, 33, 121), (30, 80, 130)]))
    assert [x[0] for x in serie] == [0, 12, 30]


def test_ritmos_km_de_detalle():
    d = detalle_t([(0, 0, 140), (300, 1000, 140), (620, 2000, 140)])
    assert m.ritmos_km_de_detalle(d) == [300, 320]
    assert m.ritmos_km_de_detalle({}) == []


def test_zona_de_fc_limites():
    assert m.zona_de_fc(100, ZONAS_T) == "Z0"
    assert m.zona_de_fc(125, ZONAS_T) == "Z1"
    assert m.zona_de_fc(137, ZONAS_T) == "Z1"
    assert m.zona_de_fc(138, ZONAS_T) == "Z2"
    assert m.zona_de_fc(195, ZONAS_T) == "Z5"


def test_minutos_zona_serie_pesa_por_tiempo_y_no_cuenta_pausas():
    serie = [[0, 0, 100], [60, 0, 140], [120, 0, 155], [125, 0, 155], [400, 0, 140], [405, 0, 140]]
    mz = m.minutos_zona_serie(serie, ZONAS_T)
    assert mz["Z0"] == 10 / 60                       # 0→60 se topa en 10 s (hueco máx.)
    assert round(mz["Z2"], 3) == round(20 / 60, 3)
    assert round(mz["Z3"], 3) == round(15 / 60, 3)
    assert mz["Z5"] == 0


def test_minutos_zona_serie_ignora_muestras_sin_fc():
    mz = m.minutos_zona_serie([[0, 0, None], [5, 0, 140], [10, 0, 140]], ZONAS_T)
    assert round(sum(mz.values()) * 60) == 10


def test_zona_minutos_usa_la_serie_y_si_no_el_reloj():
    a = act(7, "2026-11-10", "running", dur=1800, z=(300, 900, 0, 0, 0))
    serie = [[t, 0, 145] for t in range(0, 300, 5)]
    de_serie = m.zona_minutos(a, {"7": {"serie": serie}}, ZONAS_T)
    assert round(de_serie["Z2"], 1) == 5.0 and de_serie["Z1"] == 0
    del_reloj = m.zona_minutos(a, {}, ZONAS_T)
    assert del_reloj["Z1"] == 5 and del_reloj["Z2"] == 15 and del_reloj["Z0"] == 10   # 30 − 20
    assert m.zona_minutos({"activityId": 8, "duration": 600}, {}, ZONAS_T) is None


def test_fc_referencia_es_la_mitad_de_z2():
    assert m.fc_referencia(ZONAS_T) == round((138 + 151) / 2)


def test_detalle_vigente():
    completa = {"rpe": 5, "splits": [], "serie": [[0, 0, 100]], "pulso": "banda"}
    assert m.detalle_vigente(completa, True)
    assert not m.detalle_vigente({k: v for k, v in completa.items() if k != "pulso"}, True)   # detalle viejo: se repide
    assert not m.detalle_vigente({"rpe": 5, "splits": []}, True)                 # falta la serie
    assert not m.detalle_vigente(None, False)
    assert not m.detalle_vigente({"rpe": 5, "splits": [], "serie": [[0, 0, 1]]}, True, es_carrera=True)
    assert m.detalle_vigente({"rpe": None, "pulso": "banda"}, False)                               # no-corrida vieja sin RPE: no se repide
    assert not m.detalle_vigente({"rpe": None, "pulso": "banda"}, False, reciente=True)            # reciente sin RPE: Pedro puede ponerlo
    assert m.detalle_vigente({**completa, "rpe": None}, True, reciente=False)



# --- v4.3 F3: deriva cardiaca ---

def serie_parejo(min_total=50, ritmo=360, fc=lambda t: 140, paso=5):
    """Serie [seg, metros, fc] a ritmo constante `ritmo` s/km."""
    return [[t, round(t / ritmo * 1000), fc(t)] for t in range(0, min_total * 60 + 1, paso)]


def test_deriva_cero_si_la_fc_no_sube():
    d = m.deriva(serie_parejo(), {"minutos": 50, "pct_trote": 100})
    assert d["pct"] == 0.0 and d["ok"] is True


def test_deriva_mide_la_caida_de_eficiencia():
    # a ritmo constante la FC sube de 140 a 150 en la segunda mitad: EF cae ~ 6.7 %
    serie = serie_parejo(fc=lambda t: 140 if t < 1800 else 150)
    d = m.deriva(serie, {"minutos": 50, "pct_trote": None})
    assert 6 < d["pct"] < 7 and d["ok"] is False
    suave = m.deriva(serie_parejo(fc=lambda t: 140 if t < 1800 else 144), {"minutos": 50, "pct_trote": 95})
    assert 0 < suave["pct"] < 5 and suave["ok"] is True


def test_deriva_exige_40_min_y_casi_sin_caminar():
    assert m.deriva(serie_parejo(30), {"minutos": 30, "pct_trote": 100})["motivo"] == "corta"
    assert m.deriva(serie_parejo(), {"minutos": 50, "pct_trote": 80})["motivo"] == "con caminatas"
    assert m.deriva([], {"minutos": 50, "pct_trote": 100})["motivo"] == "sin serie"


def test_deriva_no_pareja_si_un_km_se_sale_de_15_pct():
    serie, extra, t = [], 0, 0
    for seg in range(0, 3001, 5):
        ritmo = 360 if not (1500 <= seg < 1900) else 270     # un tramo rápido (-25 %) después de los 10 min
        serie.append([seg, round(extra), 140])
        extra += 5 / ritmo * 1000
    d = m.deriva(serie, {"minutos": 50, "pct_trote": 100})
    assert d["pct"] is None and d["motivo"] == "no pareja"


def test_deriva_ignora_los_primeros_10_min_y_las_pausas():
    # los primeros 10 min con FC alta (calentamiento) no cuentan
    serie = serie_parejo(fc=lambda t: 170 if t < 600 else 140)
    assert m.deriva(serie, {"minutos": 50, "pct_trote": 100})["pct"] == 0.0
    # una pausa de 60 s (semáforo) a mitad: sin muestras en el hueco, no cambia nada
    con_pausa = [x for x in serie_parejo() if not 1500 < x[0] < 1560]
    assert abs(m.deriva(con_pausa, {"minutos": 50, "pct_trote": 100})["pct"]) < 0.5


# --- v4.3 F5: sugerencia de la semana pasada ---

def test_sugerencia_semana_reglas_en_orden():
    cfg = {"resumen_min_sesiones": 2, "resumen_dias_rojos": 2, "resumen_carga_alta": 1.3}
    sug = lambda *a: (m.sugerencia_semana(*a, cfg) or {}).get("tipo")  # noqa: E731
    assert sug(1, 3, 0, 100, 100) == "repetir"           # menos de 2 sesiones hechas
    assert sug(3, 3, 2, 100, 100) == "repetir"           # dos días rojos, aunque todo hecho
    assert sug(3, 3, 0, 131, 100) == "pesada"            # carga > 1.3 ×
    assert sug(3, 3, 0, 130, 100) == "sigue"             # justo en el umbral no es pesada
    assert sug(2, 3, 1, 100, 100) is None                # 2 de 3 y un rojo: sin sugerencia
    assert sug(3, 3, 0, 100, None) == "sigue"            # sin semana anterior no hay "pesada"
    assert sug(0, None, 0, 100, 100) is None             # sin plan no se pide mínimo de sesiones
    assert sug(0, None, 2, 100, 100) == "repetir"
    assert m.sugerencia_semana(3, 3, 0, 100, 100, cfg)["texto"] == "Sigue el plan"


# --- v4.3 F6: prueba ---

def test_valor_prueba_por_tipo():
    serie = [[t, round(t / 400 * 1000), 144] for t in range(0, 2401, 5)]        # 400 s/km durante 40 min
    assert m.valor_prueba("fc_fija", serie) == {"valor": 400, "km": 4.5}           # solo cuentan los primeros 30'
    assert m.valor_prueba("fc_fija", serie[:100]) is None                          # menos de 30': no hay prueba
    assert m.valor_prueba("5k", serie) == {"valor": 2000, "km": 5.0}
    assert m.valor_prueba("5k", serie[:300]) is None                               # no llegó a 5 km
    assert m.valor_prueba("trote_continuo", [], 93.44) == {"valor": 93.4, "km": None, "seguido": False}
    assert m.valor_prueba("trote_continuo", serie, 98) == {"valor": 98, "km": 4.5, "seguido": True}   # 30' seguidos
    assert m.valor_prueba("trote_continuo", [], None) is None


def test_comparar_prueba_mejor_segun_el_tipo():
    base = {"fuente": "inicio", "fecha": None, "valor": 450}
    assert m.comparar_prueba("fc_fija", 420, base) == {"dif": -30, "mejor": True}
    assert m.comparar_prueba("5k", 1600, {**base, "valor": 1500}) == {"dif": 100, "mejor": False}
    assert m.comparar_prueba("trote_continuo", 95, {**base, "valor": 80}) == {"dif": 15, "mejor": True}
    assert m.comparar_prueba("fc_fija", 450, base) == {"dif": 0, "mejor": None}
    assert m.comparar_prueba("fc_fija", 450, None) is None


def test_la_prueba_se_asigna_en_cualquier_dia():
    semana = {"sessions": [{"id": "z2a", "tipo": "z2", "name": "Z2 #1", "minutes": 20, "easy": {"minutes": 15}},
                           {"id": "prueba", "tipo": "prueba", "name": "Prueba", "minutes": 30, "easy": {"minutes": 30}}]}
    runs = [{"fecha": "2026-11-17", "minutos": 31, "luz": "verde"}, {"fecha": "2026-11-18", "minutos": 18, "luz": "verde"}]   # mar y mié
    est = {e["id"]: e for e in m.assign_sessions(semana, runs, CFG)}
    assert est["prueba"]["estado"] == "hecha" and est["prueba"]["fecha"] == "2026-11-17"
    assert est["z2a"]["fecha"] == "2026-11-18"


def test_run_check_5k_no_exige_el_techo():
    ses = {"tipo": "prueba", "prueba": "5k", "steps": [{"kind": "run", "minutes": 35, "zone": "Z4", "note": ""}],
           "easy": {"steps": []}}
    a = act(1, "2026-11-18", "running", dur=1500, z=(0, 2, 5, 10, 8))
    r = m.run_check(a, ses, CFG, {"Z0": 0, "Z1": 0, "Z2": 2, "Z3": 5, "Z4": 10, "Z5": 8})
    assert r["techo_ok"] is True and "plan_vs_real" not in r


def test_plan_vs_real_avisa_si_pasaste_mucho_arriba_de_la_zona_alta():
    pasos = [{"kind": "run", "minutes": 10, "zone": "Z2"}, {"kind": "run", "minutes": 20, "zone": "Z3"}]
    bien = m.plan_vs_real(pasos, {"Z2": 10, "Z3": 19, "Z4": 2})
    assert bien[0]["zona"] == "Z3" and bien[0]["mucho_arriba"] is False
    arriba = m.plan_vs_real(pasos, {"Z2": 10, "Z3": 8, "Z4": 12})
    assert arriba[0]["ok"] is True and arriba[0]["arriba_min"] == 12 and arriba[0]["mucho_arriba"] is True
    assert "mucho_arriba" not in m.plan_vs_real([{"kind": "run", "minutes": 20, "zone": "Z2"}], {"Z2": 20})[0]


def test_run_check_calidad_tolera_su_z3_y_usa_las_zonas_del_dashboard():
    ses = {"tipo": "calidad", "steps": [{"kind": "run", "minutes": 10, "zone": "Z2"},
                                        {"kind": "run", "minutes": 20, "zone": "Z3"}]}
    a = act(1, "2026-11-12", "running", z=(0, 0, 0, 0, 1800))     # el reloj dice todo en Z5
    r = m.run_check(a, ses, None, {"Z0": 0, "Z1": 0, "Z2": 10, "Z3": 20, "Z4": 0, "Z5": 0})
    assert r["min_sobre_techo"] == 20 and r["tolerancia_min"] == 22 and r["techo_ok"] is True


def test_deriva_solo_si_casi_todo_el_trote_va_en_z2():
    zonas = [("Z1", 125, 138), ("Z2", 138, 151), ("Z3", 151, 164)]
    assert m.deriva(serie_parejo(), {"minutos": 50, "pct_trote": 100}, zonas)["pct"] is not None
    carrera = serie_parejo(fc=lambda t: 160)
    assert m.deriva(carrera, {"minutos": 50, "pct_trote": 100}, zonas)["motivo"] == "fuera de Z2"


def test_opciones_hoy_por_color():
    ses = {"easy": {"minutes": 35}}
    assert m.opciones_hoy("normal", ses) == ["suave", "normal"]
    assert m.opciones_hoy("suave", ses) == ["suave", "normal"]
    assert m.opciones_hoy("descanso", ses) == ["descanso", "suave", "normal"]
    assert m.opciones_hoy("normal", {}) == []
    assert m.opciones_hoy(None, ses) == []


def test_pulso_de_detalle_y_por_actividad():
    con = {"metadataDTO": {"sensors": [{"antplusDeviceType": "HEART_RATE", "serialNumber": 1, "sku": "x"}]}}
    sin = {"metadataDTO": {"sensors": []}}
    assert m.pulso_de_detalle(con) == "banda" and m.pulso_de_detalle(sin) == "muñeca"
    assert m.pulso_de_detalle({}) is None and m.pulso_de_detalle(None) is None
    a = act(7, "2026-10-27", maxHR=170)
    k = str(m.id_de(a))
    assert m.pulso_de(a, {k: {"pulso": "muñeca"}}, CFG) == "muñeca"
    assert m.pulso_de(a, {}, CFG) == "banda"                                        # sin detalle: config (default banda)
    assert m.pulso_de(a, {}, {**CFG, "sensor": "muñeca"}) == "muñeca"


def test_max_hr_prefiere_banda_y_aviso_por_pulso():
    b, w = act(8, "2026-10-27", maxHR=180), act(9, "2026-10-29", maxHR=195)
    det = {str(m.id_de(b)): {"pulso": "banda"}, str(m.id_de(w)): {"pulso": "muñeca"}}
    p = m.max_hr_progress([b, w], CFG, det)
    assert (p["pico"], p["pulso_pico"]) == (180, "banda")                          # el pico de muñeca no manda
    p = m.max_hr_progress([w], CFG, det)
    assert (p["pico"], p["pulso_pico"]) == (195, "muñeca")
    assert "medido con banda" in m.max_hr_above_watch(193, 189, "banda")
    cauto = m.max_hr_above_watch(198, 189, "muñeca", 195)
    assert "195" in cauto and "muñeca" in cauto and "medido con banda" not in cauto
    assert "banda cardiaca" in m.max_hr_above_watch(None, None)
    assert m.max_hr_above_watch(180, 189, "muñeca") is None


def test_deriva_solo_con_banda(monkeypatch):
    monkeypatch.setattr(m, "deriva_de", lambda *_: {"pct": 3.0, "ok": True})
    a = act(10, "2026-10-27", "running", dur=2700, distance=5000)
    for pulso, hay in (("banda", True), ("muñeca", False)):
        det = {str(m.id_de(a)): {"pulso": pulso}}
        fila = m.run_rows([a], det, CFG)[0]
        assert fila["pulso"] == pulso
        assert (fila["deriva_pct"] is not None) == hay
