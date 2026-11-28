"""Leer data/, el plan y los JSON personales."""
import json
from dashboard.ajustes import USER_DIR
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent  # el motor


def load(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def load_data(user_dir=None) -> dict:
    user_dir = Path(user_dir) if user_dir else USER_DIR
    d = user_dir / "data"
    daily = load(d / "daily.json", {})
    return {
        "daily_summaries": daily.get("daily_summaries", []),
        "sleep": daily.get("sleep", []),
        "hrv": daily.get("hrv", []),
        "activities": load(d / "activities.json", []),
        "details": load(d / "activity_details.json", {}),
        "hr_zones": load(d / "hr_zones.json", []),
        "meta": load(d / "meta.json", {}),
        "historial": load(d / "historial_corridas.json"),
        "inbody": load(user_dir / "plan" / "inbody.json"),
    }


def load_plan(user_dir=None) -> dict:
    plan = (Path(user_dir) if user_dir else USER_DIR) / "plan" / "plan.json"
    return load(plan if plan.exists() else ROOT / "plan" / "plan.example.json")
