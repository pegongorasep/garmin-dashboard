"""Descarga historial de la Garmin Connect Personal API a data/.

Auth: POST con 'Authorization: ApiKey <key>' devuelve un JWT en texto plano
(vive 24h, sin refresh); el resto de llamadas usan 'Authorization: Bearer <jwt>'.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent / "dashboard"))
import metrics  # noqa: E402
from ajustes import USER_DIR, ConfigError, cargar_config, config_por_defecto  # noqa: E402

load_dotenv(USER_DIR / ".env")
load_dotenv(Path(__file__).parent / ".env")

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_URL = f"{BASE_URL}/personalapitoken-service/personal-api/personal-api-key/token"
DATA_DIR = USER_DIR / "data"
try:
    CONFIG = cargar_config()
except ConfigError:
    if (USER_DIR / "config.yaml").exists():   # existe pero está mal: que truene como siempre
        raise
    CONFIG = config_por_defecto()   # repo nuevo que solo es tubo de datos: no hay config.yaml
RUN_TYPES = CONFIG["run_types"]
CROSSFIT_TYPES = [t for t in CONFIG["tipos_con_detalle"] if t not in RUN_TYPES]


def get_access_token() -> str:
    resp = requests.post(
        TOKEN_URL, headers={"Authorization": f"ApiKey {os.environ['PERSONAL_API_KEY']}"}
    )
    if resp.status_code in (400, 401, 403):
        # Mensaje para quien lee el log del workflow (casi siempre: la key expiró o se borró).
        sys.exit(f"ERROR: Garmin rechazó la key ({resp.status_code}). Probablemente expiró: crea una nueva en "
                 "https://connect.garmin.com/app/settings/personalApiToken y guárdala con "
                 "`gh secret set PERSONAL_API_KEY`.")
    resp.raise_for_status()
    return resp.text.strip()


class Client:
    def __init__(self, token: str):
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {token}"

    def get(self, path: str, params: dict | None = None):
        resp = self.session.get(f"{BASE_URL}{path}", params=params or {}, timeout=60)
        if resp.status_code == 204:
            return None
        resp.raise_for_status()
        return resp.json()


def date_chunks(start: date, end: date, max_days: int):
    cur = start
    while cur <= end:
        chunk_end = min(cur + timedelta(days=max_days - 1), end)
        yield cur, chunk_end
        cur = chunk_end + timedelta(days=1)


def pull_daily(c: Client, start: date, end: date) -> dict:
    out = {"daily_summaries": [], "sleep": [], "hrv": [], "body_battery": [], "stress": []}
    for s, e in date_chunks(start, end, 28):
        a, b = s.isoformat(), e.isoformat()
        out["daily_summaries"] += (
            c.get("/usersummary-service/v2/dailysummaries", {"startDate": a, "endDate": b})
            or {}
        ).get("data", [])
        out["sleep"] += c.get(
            "/sleep-service/sleep/dailySleepSummariesByDate", {"startDate": a, "endDate": b}
        ) or []
        out["hrv"] += (c.get(f"/hrv-service/hrv/daily/{a}/{b}") or {}).get("hrvSummaries", [])
        out["body_battery"] += c.get(
            "/wellness-service/wellness/bodyBattery/reports/daily",
            {"startDate": a, "endDate": b},
        ) or []
        out["stress"] += c.get(f"/usersummary-service/stats/stress/daily/{a}/{b}") or []
    return out


def pull_activities(c: Client, since: date) -> list:
    activities, start, page = [], 0, 100
    while True:
        batch = c.get(
            "/activitylist-service/activities/search/activities",
            {"start": start, "limit": page},
        ) or []
        activities += batch
        if len(batch) < page or batch[-1]["startTimeLocal"][:10] < since.isoformat():
            break
        start += page
    return [a for a in activities if a["startTimeLocal"][:10] >= since.isoformat()]


def pull_historial(c: Client, desde: str | None = None) -> list:
    """Corridas de la cuenta (todas, o las de `desde` AAAA-MM-DD en adelante), solo con lo necesario para las mejores
    marcas. Sin nombres, IDs ni GPS. Pagina la lista de actividades hasta el final (o hasta pasar de `desde`)."""
    corridas, start, page = [], 0, 100
    while True:
        batch = c.get("/activitylist-service/activities/search/activities", {"start": start, "limit": page}) or []
        for a in batch:
            tipo = (a.get("activityType") or {}).get("typeKey")
            if tipo not in RUN_TYPES or (desde and a["startTimeLocal"][:10] < desde):
                continue
            corridas.append({"startTimeLocal": a["startTimeLocal"], "activityType": {"typeKey": tipo},
                             "distance": a.get("distance"), "duration": a.get("duration"),
                             "eventType": {"typeKey": (a.get("eventType") or {}).get("typeKey")},
                             **{k: v for k, v in a.items() if k.startswith("fastestSplit_")}})
        if len(batch) < page or (desde and batch and batch[-1]["startTimeLocal"][:10] < desde):
            return corridas
        start += page


def detalle_serie(c: Client, key: str) -> dict:
    """Serie de la actividad (`/details`, una sola llamada): ritmo de cada km (para carreras) y [seg, metros, fc]
    cada 5 s. No se guarda GPS: solo tiempo, distancia y FC."""
    # maxChartSize alto: sin él Garmin entrega ~250 puntos sin importar la duración; así llega 1 muestra por segundo
    d = c.get(f"/activity-service/activity/{key}/details", {"maxChartSize": 5000, "maxPolylineSize": 0}) or {}
    return {"ritmos_km": metrics.ritmos_km_de_detalle(d), "serie": metrics.serie_de_detalle(d)}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def tramos(summary: dict) -> list:
    """Tramos de trote/caminata (RWD_*) del detalle: solo tiempos, distancias y FC, sin GPS."""
    return [{"tipo": t.get("splitType"), "seg": t.get("duration"), "m": t.get("distance"),
             "fc": t.get("averageHR"), "n": t.get("noOfSplits")}
            for t in summary.get("splitSummaries") or []]


def pull_activity_details(c: Client, activities: list) -> dict:
    """Pide RPE y sensación (y tramos de trote/caminata y serie de FC en corridas); reusa lo ya completo.
    Una actividad de los últimos 7 días sin RPE se vuelve a pedir (Pedro puede ponerlo después)."""
    tipos = RUN_TYPES + CROSSFIT_TYPES
    path = DATA_DIR / "activity_details.json"
    cache = load_json(path)
    out = {}
    hoy = date.today()
    for a in activities:
        tipo = a["activityType"]["typeKey"]
        if tipo not in tipos:
            continue
        key, es_corrida = str(a["activityId"]), tipo in RUN_TYPES
        carrera = es_corrida and metrics.es_carrera(a, CONFIG)
        reciente = (hoy - date.fromisoformat(a["startTimeLocal"][:10])).days <= 7
        if metrics.detalle_vigente(cache.get(key), es_corrida, carrera, reciente):
            out[key] = cache[key]
            continue
        detalle = c.get(f"/activity-service/activity/{key}") or {}
        s = detalle.get("summaryDTO", {})
        rpe = s.get("directWorkoutRpe")
        out[key] = {"rpe": rpe / 10 if rpe is not None else None,
                    "feel": s.get("directWorkoutFeel"),
                    "pulso": metrics.pulso_de_detalle(detalle)}   # solo "banda"/"muñeca": nada del dispositivo
        if es_corrida:
            out[key]["splits"] = tramos(detalle)
            extra = detalle_serie(c, key)
            out[key]["serie"] = extra["serie"]
            if carrera:
                out[key]["ritmos_km"] = extra["ritmos_km"]
    path.write_text(json.dumps(out, separators=(",", ":")))   # compacto: la serie de FC es larga
    return out


def main(argv=None, cliente=None) -> None:
    ap = argparse.ArgumentParser(description="Baja los datos de Garmin a data/")
    ap.add_argument("semanas_salud", nargs="?", type=int, default=16, help="semanas de salud (por defecto 16)")
    ap.add_argument("dias_posicional", nargs="?", type=int, help="días de actividades (igual que --dias-actividades)")
    ap.add_argument("--dias-actividades", type=int, help="días de actividades (por defecto 120)")
    ap.add_argument("--historial-desde", metavar="AAAA-MM-DD", help="solo las corridas del historial desde esta fecha")
    args = ap.parse_args(argv)
    health_weeks = args.semanas_salud
    activity_days = args.dias_actividades or args.dias_posicional or 120
    if args.historial_desde:
        date.fromisoformat(args.historial_desde)   # falla claro si no es fecha

    today = date.today()
    c = cliente or Client(get_access_token())
    DATA_DIR.mkdir(exist_ok=True)

    activities = pull_activities(c, today - timedelta(days=activity_days))
    details = pull_activity_details(c, activities)
    historial = pull_historial(c, args.historial_desde)
    (DATA_DIR / "historial_corridas.json").write_text(json.dumps(historial, indent=1))
    datasets = {
        "daily": pull_daily(c, today - timedelta(weeks=health_weeks), today),
        "activities": activities,
        "hr_zones": c.get("/biometric-service/heartRateZones/v2"),
        "profile": c.get("/userprofile-service/userprofile/settings"),
    }
    for name, payload in datasets.items():
        (DATA_DIR / f"{name}.json").write_text(json.dumps(payload, indent=2, default=str))

    (DATA_DIR / "meta.json").write_text(json.dumps({
        "pulled_at": today.isoformat(),
        "pulled_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }))
    print(f"OK: {len(datasets['activities'])} actividades, "
          f"{len(details)} detalles, {len(historial)} corridas en el historial, "
          f"{len(datasets['daily']['daily_summaries'])} días de salud -> {DATA_DIR}")


if __name__ == "__main__":
    main()
