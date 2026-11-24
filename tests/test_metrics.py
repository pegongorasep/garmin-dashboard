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


def test_session_and_week_load():
    lun = date(2026, 10, 26)
    acts = [act(1, "2026-10-26", dur=3600), act(2, "2026-10-27", "running", dur=1800),
            act(3, "2026-10-28", dur=3600), act(4, "2026-10-29", "indoor_cycling")]
    det = {"1": {"rpe": 7.0}, "2": {"rpe": 4.0}, "3": {"rpe": None}}
    assert m.session_load(acts[0], det) == 420
    assert m.session_load(acts[2], det) is None
    assert m.session_load(acts[0], {}) is None
    assert m.week_load(acts, det, lun, CFG) == {
        "crossfit": 420, "run": 120, "sin_rpe": 1, "total": 540}


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


def test_signal_rpe():
    d = date(2026, 10, 24)
    acts = [act(1, "2026-10-23"), act(2, "2026-10-23", "strength_training"), act(3, "2026-10-22")]
    assert m.signal_rpe(d, acts, {"1": {"rpe": 6.0}, "2": {"rpe": 8.0}}, CFG)["estado"] == "fuera"
    assert m.signal_rpe(d, acts, {"1": {"rpe": 6.0}, "2": {"rpe": 7.0}}, CFG)["valor"] == 7.0
    assert m.signal_rpe(d, acts, {"1": {"rpe": None}}, CFG)["estado"] == "sin_dato"
    sin = m.signal_rpe(d, [acts[2]], {}, CFG)
    assert sin["estado"] == "ok" and sin["texto"] == "sin CrossFit ayer"


def test_signals_completo():
    data = {"hrv": [HRV_OK], "daily_summaries": [], "sleep": [], "activities": [], "details": {}}
    s = m.signals(date(2026, 10, 24), data, CFG)
    assert set(s) == {"hrv", "rhr", "sueno", "rpe"}
    assert s["hrv"]["estado"] == "ok" and s["rhr"]["estado"] == "sin_dato"


def _sigs(hrv="ok", rhr="ok", sueno="ok", rpe="ok", baja=False):
    mk = lambda e, **k: {"estado": e, **k}  # noqa: E731
    return {"hrv": mk(hrv, hrv_baja=baja), "rhr": mk(rhr), "sueno": mk(sueno), "rpe": mk(rpe)}


def test_traffic_light_tabla():
    casos = [
        (_sigs(), None, "verde", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato"), None, "verde", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato", sueno="sin_dato"), None, "sin_datos", False),
        (_sigs(hrv="sin_dato", rhr="sin_dato", sueno="sin_dato", rpe="fuera"), "rojo", "sin_datos", False),
        (_sigs(sueno="fuera"), None, "amarillo", False),
        (_sigs(sueno="fuera", rpe="fuera"), None, "rojo", False),
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


def fila(fecha, pct, ritmo, caminadora=False):
    return {"fecha": fecha, "pct_trote": pct, "ritmo_trote_s": ritmo, "caminadora": caminadora}


def test_progress_summary():
    hoy = date(2026, 12, 14)
    filas = [fila("2026-11-02", 58, 460), fila("2026-11-10", 58, 460),   # antes: 19 oct – 16 nov; ahora: 16 nov – 14 dic
             fila("2026-10-25", 58, 460), fila("2026-10-30", 58, 460),
             fila("2026-12-01", 70, 445), fila("2026-12-10", 66, 445),
             fila("2026-12-05", 10, 300, caminadora=True)]               # caminadora: no cuenta
    assert m.progress_summary(filas, hoy, 4) == "Trotas 68 % del tiempo (antes 58 %) · ritmo trotando 7:40 → 7:25 /km"
    assert m.progress_summary(filas[:4], hoy, 4) == "Aún no hay corridas suficientes para comparar"
    assert m.progress_summary([], hoy, 4) == "Aún no hay corridas suficientes para comparar"
    sin_ritmo = [fila("2026-12-01", 70, None), fila("2026-10-25", 58, 460)]
    assert m.progress_summary(sin_ritmo, hoy, 4) == "Trotas 70 % del tiempo (antes 58 %)"


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


def test_motivo():
    assert m.motivo(_sigs()) is None
    assert m.motivo(_sigs(rhr="fuera")) == "FC en reposo alta"
    assert m.motivo(_sigs(hrv="fuera", rpe="fuera"), CFG) == "HRV baja · CrossFit pesado ayer"
    assert m.motivo(_sigs(sueno="fuera", rhr="fuera")) == "FC en reposo alta · Dormiste poco"
    assert m.motivo(_sigs(baja=True)) == "HRV baja"
    assert m.motivo(_sigs(hrv="fuera", baja=True)) == "HRV baja"


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

def c_mej(fecha, minutos, pct=None):
    return {"fecha": fecha, "minutos": minutos, "pct_trote": pct}


HOY = date(2026, 11, 14)   # lunes de esa semana: 9 nov; ventanas 12 oct–8 nov y 14 sep–11 oct


def test_mejora_frase_con_datos():
    filas = [c_mej("2026-09-20", 34, 66), c_mej("2026-10-01", 34, 66),
             c_mej("2026-10-14", 50, 70), c_mej("2026-10-21", 54, 72), c_mej("2026-10-31", 50, 70),
             c_mej("2026-11-05", 54, 72), c_mej("2026-11-09", 99, 99)]   # la de esta semana no cuenta
    assert m.mejora_frase(filas, HOY) == (
        "Últimas 4 semanas: 1.0 corridas y 52 min por semana (antes 0.5 y 17); trote 71 % (antes 66 %).")


def test_mejora_frase_sin_datos():
    assert m.mejora_frase([], HOY) == "Aún no hay corridas suficientes para comparar."
    assert m.mejora_frase([c_mej("2026-11-12", 38, 71)], HOY) == "Aún no hay corridas suficientes para comparar."


def test_mejora_frase_con_la_mitad_vacia():
    solo_ahora = [c_mej("2026-10-20", 40, 60), c_mej("2026-10-27", 40)]
    assert m.mejora_frase(solo_ahora, HOY) == "Últimas 4 semanas: 0.5 corridas y 20 min por semana; trote 60 %."
    solo_antes = [c_mej("2026-09-20", 40, 60)]
    assert m.mejora_frase(solo_antes, HOY) == "Últimas 4 semanas: sin corridas (antes 0.2 y 10 min por semana)."


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
    acts = [act(1, "2026-10-19", "strength_training", dur=3600), act(2, "2026-10-20", "hiit", dur=1800),
            act(3, "2026-10-21", "running", dur=1800), act(4, "2026-10-22", "walking")]
    c = m.week_load(acts, {"1": {"rpe": 5.0}, "2": {"rpe": 8.0}, "3": {"rpe": 4.0}}, lun, CFG3)
    assert c == {"fuerza": 300.0, "hiit": 240.0, "cardio": 0.0, "run": 120.0, "sin_rpe": 0, "total": 660.0}


def test_signal_rpe_solo_categorias_intensas():
    d = date(2026, 10, 21)
    acts = [act(1, "2026-10-20", "strength_training"), act(2, "2026-10-20", "hiit")]
    s = m.signal_rpe(d, acts, {"1": {"rpe": 9.0}, "2": {"rpe": 6.0}}, CFG3)
    assert s["valor"] == 6.0 and s["estado"] == "ok" and "HIIT" in s["texto"]


def test_signal_rpe_nombre_unico_y_varias_intensas():
    d = date(2026, 10, 21)
    sin = m.signal_rpe(d, [], {}, CFG3)
    assert sin["texto"] == "sin HIIT ayer"
    dos = {**CFG3, "categorias": [{**c, "intensa": True} for c in CFG3["categorias"]]}
    assert m.signal_rpe(d, [], {}, dos)["texto"] == "sin sesión intensa ayer"
    assert m.motivo(_sigs(rpe="fuera"), dos) == "Sesión intensa pesada ayer"


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

CFG_CARRERA = {"run_types": ["running", "treadmill_running"], "carreras": ["2026-11-21"]}


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
    # puntuación: solo las mediciones con hoja completa (25 may 2024, 8 oct 2026, 13 nov 2026)
    assert [(x["fecha"], x["puntos"]) for x in c["puntuacion"]] == [("2024-05-25", 80), ("2026-10-08", 69), ("2026-11-13", 75)]
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

def test_conteos_otras_y_frase():
    acts = [act(1, "2026-10-14"), act(2, "2026-10-21"), act(3, "2026-10-22"), act(4, "2026-11-04", "running"),
            act(5, "2026-11-05"), act(6, "2026-11-10", "strength_training"), act(7, "2026-11-11"), act(8, "2026-11-12")]
    c = m.conteos_otras(acts, CFG, date(2026, 10, 12), date(2026, 11, 9))
    assert c == {"crossfit": 4}                       # la corrida no cuenta; el 10 nov queda fuera
    assert m.frase_otras([{"nombre": "CrossFit", "ahora": 3.25, "antes": 2.5}]) == " · CrossFit 3.2 por semana (antes 2.5)"
    assert m.frase_otras([{"nombre": "A", "ahora": 0, "antes": 0}]) == ""
    tres = [{"nombre": n, "ahora": a, "antes": 1} for n, a in (("A", 1), ("B", 3), ("C", 2))]
    assert m.frase_otras(tres) == " · B 3.0 por semana (antes 1.0) · C 2.0 por semana (antes 1.0)"   # máximo 2, las de más sesiones
    filas = [c_mej("2026-09-20", 34, 66), c_mej("2026-10-14", 50, 70)]
    assert m.mejora_frase(filas, HOY, "trote", [{"nombre": "CrossFit", "ahora": 3.2, "antes": 2.5}]).endswith(
        "(antes 66 %) · CrossFit 3.2 por semana (antes 2.5).")
    assert "CrossFit" not in m.mejora_frase(filas, HOY, "trote", [])
