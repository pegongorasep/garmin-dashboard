"""Descarga historial de la Garmin Connect Personal API a data/.

Auth: POST con 'Authorization: ApiKey <key>' devuelve un JWT en texto plano
(vive 24h, sin refresh); el resto de llamadas usan 'Authorization: Bearer <jwt>'.
"""
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_URL = f"{BASE_URL}/personalapitoken-service/personal-api/personal-api-key/token"
DATA_DIR = Path(__file__).parent / "data"
CONFIG = json.loads((Path(__file__).parent / "dashboard" / "config.json").read_text())
RUN_TYPES = CONFIG["run_types"]
CROSSFIT_TYPES = CONFIG["crossfit_types"]


def get_access_token() -> str:
    resp = requests.post(
        TOKEN_URL, headers={"Authorization": f"ApiKey {os.environ['PERSONAL_API_KEY']}"}
    )
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def pull_activity_details(c: Client, activities: list) -> dict:
    """Pide RPE y sensación de las corridas y CrossFit; reusa las que ya tienen RPE."""
    tipos = RUN_TYPES + CROSSFIT_TYPES
    path = DATA_DIR / "activity_details.json"
    cache = load_json(path)
    out = {}
    for a in activities:
        if a["activityType"]["typeKey"] not in tipos:
            continue
        key = str(a["activityId"])
        if cache.get(key, {}).get("rpe") is not None:
            out[key] = cache[key]
            continue
        s = (c.get(f"/activity-service/activity/{key}") or {}).get("summaryDTO", {})
        rpe = s.get("directWorkoutRpe")
        out[key] = {"rpe": rpe / 10 if rpe is not None else None,
                    "feel": s.get("directWorkoutFeel")}
    path.write_text(json.dumps(out, indent=2))
    return out


def main() -> None:
    health_weeks = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    activity_days = int(sys.argv[2]) if len(sys.argv) > 2 else 120

    today = date.today()
    c = Client(get_access_token())
    DATA_DIR.mkdir(exist_ok=True)

    activities = pull_activities(c, today - timedelta(days=activity_days))
    details = pull_activity_details(c, activities)
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
          f"{len(details)} detalles, "
          f"{len(datasets['daily']['daily_summaries'])} días de salud -> {DATA_DIR}")


if __name__ == "__main__":
    main()
