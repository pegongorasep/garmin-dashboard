"""Convierte data/ + plan + config en site/data.json (solo campos de una lista blanca).

Uso: python dashboard/build.py [--day YYYY-MM-DD]
Es el único lugar con reloj: "hoy" se calcula en la zona horaria del config.
"""
import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import metrics as m

ROOT = Path(__file__).parent.parent
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def load_data() -> dict:
    d = ROOT / "data"
    daily = load(d / "daily.json", {})
    return {
        "daily_summaries": daily.get("daily_summaries", []),
        "sleep": daily.get("sleep", []),
        "hrv": daily.get("hrv", []),
        "activities": load(d / "activities.json", []),
        "details": load(d / "activity_details.json", {}),
        "hr_zones": load(d / "hr_zones.json", []),
        "meta": load(d / "meta.json", {}),
    }


def load_plan() -> dict:
    plan = ROOT / "plan" / "plan.json"
    return load(plan if plan.exists() else ROOT / "plan" / "plan.example.json")


def r1(x):
    return None if x is None else round(x, 1)


def monday(day: date) -> date:
    return day - timedelta(days=day.weekday())


def light_on(day: date, data: dict, config: dict, prev=None) -> dict:
    return m.traffic_light(m.signals(day, data, config), prev)


# --- plan: zonas por nombre -> lpm ---

def lpm_range(zone: str, zonas: list):
    """'Z2' -> [piso, techo]; 'Z1-Z2' -> piso de Z1 a techo de Z2."""
    por_nombre = {z: (lo, hi) for z, lo, hi in zonas}
    try:
        a, b = zone.split("-")[0], zone.split("-")[-1]
        return [por_nombre[a][0], por_nombre[b][1]]
    except KeyError:
        return None


def convert_steps(steps: list, zonas: list) -> list:
    out = []
    for s in steps:
        if s["kind"] == "repeat":
            out.append({"kind": "repeat", "times": s["times"], "steps": convert_steps(s["steps"], zonas)})
        else:
            out.append({"kind": s["kind"], "minutes": s["minutes"], "zone": s["zone"],
                        "lpm": lpm_range(s["zone"], zonas), "note": s.get("note", "")})
    return out


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    return {"id": s["id"], "name": s["name"], "minutes": s["minutes"],
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": easy["name"], "minutes": easy["minutes"],
                     "steps": convert_steps(easy["steps"], zonas)}}


def convert_week(w: dict, zonas: list) -> dict:
    return {"n": w["n"], "block": w["block"], "kind": w["kind"], "focus": w["focus"],
            "sessions": [convert_session(s, zonas) for s in w["sessions"]]}


# --- bloques del JSON ---

def signals_list(sigs: dict) -> list:
    return [{"id": k, "estado": s["estado"], "valor": s["valor"],
             "referencia": s["referencia"], "texto": s["texto"]} for k, s in sigs.items()]


def day_type(day: date, hoy: date, acts: list, config: dict) -> str:
    tipos = {m.classify(a, config) for a in acts if m.day_of(a) == day}
    if "crossfit" in tipos:
        return "crossfit"
    if "run" in tipos:
        return "corrida"
    if day > hoy:
        return "futuro"
    return "descanso" if day < hoy else "hoy"


def build_week(hoy: date, data: dict, config: dict) -> dict:
    ini, acts = monday(hoy), data["activities"]
    dias = []
    for i in range(7):
        d = ini + timedelta(days=i)
        luz = light_on(d, data, config)["color"] if d <= hoy else None
        dias.append({"fecha": d.isoformat(), "dia_semana": DIAS[i],
                     "tipo": day_type(d, hoy, acts, config), "luz": luz})
    carga = lambda s: {k: r1(v) if k != "sin_rpe" else v  # noqa: E731
                       for k, v in m.week_load(acts, data["details"], s, config).items()}
    dist = m.week_distribution(acts, ini)
    return {
        "dias": dias,
        "corridas_hechas": sum(1 for d in dias if d["tipo"] == "corrida"),
        "carga": carga(ini),
        "carga_anterior": carga(ini - timedelta(days=7)),
        "distribucion": {"minutos": {z: r1(v) for z, v in dist["minutos"].items()},
                         "bajo": r1(dist["bajo"]), "limbo": r1(dist["limbo"]), "alto": r1(dist["alto"])},
    }


def week_runs(hoy: date, data: dict, config: dict) -> list:
    """Corridas de la semana en orden, con la luz del día en que se hicieron."""
    ini = monday(hoy)
    runs = sorted((a for a in data["activities"] if m.classify(a, config) == "run"
                   and ini <= m.day_of(a) <= hoy), key=lambda a: a["startTimeLocal"])
    return [{"fecha": m.day_of(a).isoformat(),
             "luz": light_on(m.day_of(a), data, config)["color"]} for a in runs]


def build_trends(hoy: date, data: dict, config: dict) -> dict:
    hrv = {r["calendarDate"]: r for r in data["hrv"]}
    daily = {r["calendarDate"]: r for r in data["daily_summaries"]}
    sleep = {r["calendarDate"]: r for r in data["sleep"]}
    dias = []
    for i in range(83, -1, -1):
        d = (hoy - timedelta(days=i)).isoformat()
        h, base = hrv.get(d, {}), hrv.get(d, {}).get("baseline") or {}
        seg = (sleep.get(d) or {}).get("sleepTimeSeconds")
        dias.append({"fecha": d, "hrv": h.get("lastNightAvg"),
                     "hrv_base_baja": base.get("balancedLow"), "hrv_base_alta": base.get("balancedUpper"),
                     "rhr": ((daily.get(d) or {}).get("heartRate") or {}).get("restingValue"),
                     "sueño_h": None if seg is None else round(seg / 3600, 2)})
    semanas = []
    for i in range(11, -1, -1):
        s = monday(hoy) - timedelta(weeks=i)
        c = m.week_load(data["activities"], data["details"], s, config)
        semanas.append({"inicio": s.isoformat(), "carga_crossfit": r1(c["crossfit"]),
                        "carga_corrida": r1(c["run"]), "sin_rpe": c["sin_rpe"]})
    return {"dias": dias, "semanas": semanas}


def build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)
    rhr = m.rhr_7d(data["daily_summaries"], hoy) or 60
    zonas = m.zones(config["max_hr"], rhr, config["zone_pcts"])

    sigs = m.signals(hoy, data, config)
    prev = light_on(ayer, data, config)["color"]
    luz = m.traffic_light(sigs, prev)

    repetidas = config.get("semanas_repetidas", [])
    n = m.week_index(hoy, date.fromisoformat(config["plan_start"]), repetidas)
    semanas = {w["n"]: w for w in plan["weeks"]}
    semana_plan = semanas.get(n)
    estado = m.plan_status(semana_plan, week_runs(hoy, data, config)) if semana_plan else []

    tarjeta = m.today_card(hoy, luz, estado, data["activities"], config)
    if tarjeta["sesion_id"] and semana_plan:
        ses = next(s for s in semana_plan["sessions"] if s["id"] == tarjeta["sesion_id"])
        tarjeta["sesion"] = convert_session(ses, zonas)

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    return {
        "generado": ahora.isoformat(timespec="minutes"),
        "datos_al": datos_al,
        "zonas": [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in zonas],
        "rhr_promedio_7d": r1(rhr),
        "aviso_zonas": m.watch_zone_mismatch(data["hr_zones"], config),
        "hoy": {"semaforo": luz, "señales": signals_list(sigs), "tarjeta": tarjeta},
        "semana": build_week(hoy, data, config),
        "plan": {"inicio": plan["start"], "semana_actual": n, "semanas_repetidas": repetidas,
                 "semanas": [convert_week(w, zonas) for w in plan["weeks"]],
                 "estado_sesiones": estado},
        "tendencias": build_trends(hoy, data, config),
        "corridas": [{**f, "minutos": r1(f["minutos"]), "pct_z1z2": r1(f["pct_z1z2"]),
                      "eficiencia": None if f["eficiencia"] is None else round(f["eficiencia"], 3)}
                     for f in m.run_rows(data["activities"], config)],
        "fc_max": {**m.max_hr_progress(data["activities"], config), "config": config["max_hr"]},
        "umbrales": {k: config[k] for k in ("rhr_tolerance_bpm", "sleep_min_hours", "rpe_heavy",
                                            "max_hr", "max_hr_floor", "zone_pcts")},
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="fecha local YYYY-MM-DD (para pruebas)")
    args = ap.parse_args()
    config = load(Path(__file__).parent / "config.json")
    tz = ZoneInfo(config["timezone"])
    ahora = datetime.now(tz)
    if args.day:
        ahora = datetime.combine(date.fromisoformat(args.day), ahora.time(), tzinfo=tz)
    out = build(load_data(), load_plan(), config, ahora)
    destino = ROOT / "site" / "data.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"OK: {destino} ({destino.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
