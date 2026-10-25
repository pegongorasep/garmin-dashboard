import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
import metrics as m  # noqa: E402

CFG = {
    "max_hr": 190, "max_hr_floor": 183, "max_hr_review_above": 200,
    "strap_in_crossfit_since": "2026-10-26", "rhr_tolerance_bpm": 4,
    "sleep_min_hours": 6.5, "rpe_heavy": 8,
    "run_types": ["running", "treadmill_running"], "crossfit_types": ["hiit", "strength_training"],
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


def test_classify():
    assert m.classify(act(1, "2026-10-01", "running"), CFG) == "run"
    assert m.classify(act(1, "2026-10-01", "treadmill_running"), CFG) == "run"
    assert m.classify(act(1, "2026-10-01", "hiit"), CFG) == "crossfit"
    assert m.classify(act(1, "2026-10-01", "indoor_cycling"), CFG) == "other"


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


WEEK = {"sessions": [{"id": "A"}, {"id": "B"}]}


def test_plan_status():
    runs = [{"fecha": "2026-10-28", "luz": "verde"}, {"fecha": "2026-10-31", "luz": "amarillo"}]
    assert [s["estado"] for s in m.plan_status(WEEK, [])] == ["pendiente", "pendiente"]
    uno = m.plan_status(WEEK, runs[:1])
    assert [s["estado"] for s in uno] == ["hecha", "pendiente"] and not uno[0]["ajustada"]
    dos = m.plan_status(WEEK, runs)
    assert dos[1]["estado"] == "hecha" and dos[1]["ajustada"] is True


def test_today_card_ramas():
    verde = {"color": "verde", "repetir_semana": False}
    pend = [{"id": "A", "estado": "pendiente"}, {"id": "B", "estado": "pendiente"}]
    hecha = [{"id": "A", "estado": "hecha"}, {"id": "B", "estado": "pendiente"}]
    todas = [{"id": "A", "estado": "hecha"}, {"id": "B", "estado": "hecha"}]
    lun, mie = date(2026, 10, 26), date(2026, 10, 28)
    # lunes sin corrida -> CrossFit
    assert m.today_card(lun, verde, pend, [], CFG)["tipo"] == "crossfit"
    # miércoles con CrossFit registrado -> CrossFit
    assert m.today_card(mie, verde, pend, [act(1, "2026-10-28")], CFG)["tipo"] == "crossfit"
    # lunes con corrida hecha hoy y sesión pendiente -> sesión
    assert m.today_card(lun, verde, hecha, [act(2, "2026-10-26", "running")], CFG)["tipo"] == "sesion"
    # miércoles libre: versión según semáforo y siguiente pendiente
    assert m.today_card(mie, verde, hecha, [], CFG)["sesion_id"] == "B"
    assert m.today_card(mie, verde, pend, [], CFG)["version"] == "normal"
    assert m.today_card(mie, {**verde, "color": "amarillo"}, pend, [], CFG)["version"] == "suave"
    assert m.today_card(mie, {**verde, "color": "rojo"}, pend, [], CFG)["version"] == "descanso"
    # semana completa
    assert m.today_card(mie, verde, todas, [], CFG)["tipo"] == "completa"
    # aviso de repetir semana
    rojo2 = {"color": "rojo", "repetir_semana": True}
    assert m.today_card(mie, rojo2, pend, [], CFG)["aviso"] == "Repetir la semana"


def test_run_rows():
    acts = [act(1, "2026-10-21", "running", dur=1800, z=(300, 900, 300, 300, 0),
                averageHR=140.0, averageSpeed=3.0),
            act(2, "2026-10-22", "treadmill_running", dur=1800, averageHR=140.0, averageSpeed=3.0),
            act(3, "2026-10-23", "hiit")]
    filas = m.run_rows(acts, CFG)
    assert len(filas) == 2
    assert round(filas[0]["eficiencia"], 4) == round(3.0 * 60 / 140, 4)
    assert filas[0]["minutos"] == 30 and round(filas[0]["pct_z1z2"]) == 67
    assert filas[1]["eficiencia"] is None and filas[1]["pct_z1z2"] is None


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


def test_watch_zone_mismatch():
    assert m.watch_zone_mismatch([{"sport": "DEFAULT", "maxHeartRateUsed": 190}], CFG) is None
    assert "203" in m.watch_zone_mismatch([{"sport": "DEFAULT", "maxHeartRateUsed": 203}], CFG)
    assert m.watch_zone_mismatch([], CFG) is None
