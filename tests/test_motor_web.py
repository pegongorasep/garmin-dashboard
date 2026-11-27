"""F0 de v5: el motor se puede llamar con datos en memoria y sin config.yaml."""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "plan"))

import ajustes  # noqa: E402
import build  # noqa: E402
import metrics as m  # noqa: E402

FIX = ROOT / "tests" / "fixtures"


def test_cargar_config_es_leer_mas_normalizar():
    crudo = ajustes.leer_config_yaml(FIX / "config.yaml")
    assert isinstance(crudo, dict) and "perfil" in crudo
    assert ajustes.normalizar_config(crudo) == ajustes.cargar_config(FIX)
    assert ajustes.cargar_config(FIX)["modo"] == "pages"
    assert ajustes.normalizar_config({**crudo, "modo": "web"})["modo"] == "web"
    with pytest.raises(ajustes.ConfigError):
        ajustes.normalizar_config({**crudo, "modo": "otro"})


def test_normalizar_no_modifica_el_crudo():
    crudo = ajustes.leer_config_yaml(FIX / "config.yaml")
    copia = json.loads(json.dumps(crudo, default=str))
    ajustes.normalizar_config(crudo)
    assert json.loads(json.dumps(crudo, default=str)) == copia


@pytest.mark.skipif(not (ROOT / "config.yaml").exists(), reason="no hay config.yaml de Pedro")
def test_el_plan_de_pedro_en_formato_anterior_se_sigue_pintando():
    """Su plan.json no trae `meta` (lo hizo el motor anterior): build.build lo renderiza sin pedir nada nuevo."""
    cfg = ajustes.normalizar_config(ajustes.leer_config_yaml(ROOT / "config.yaml"))
    plan = json.loads((ROOT / "plan" / "plan.json").read_text())
    datos = {"daily_summaries": [], "sleep": [], "hrv": [], "activities": [], "details": {}, "hr_zones": [], "meta": {},
             "historial": None, "inbody": None}
    d = build.build(datos, plan, cfg, datetime(2026, 11, 25, 12, 0, tzinfo=ZoneInfo(cfg["timezone"])))
    assert d["plan"]["semanas"] and "meta" not in plan


def test_config_por_defecto_sirve_sin_config_yaml():
    c = ajustes.config_por_defecto()
    assert "running" in c["run_types"] and c["modo"] == "pages"


def test_load_data_y_load_plan_aceptan_carpeta(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "meta.json").write_text('{"pulled_at": "2026-01-01"}')
    assert build.load_data(tmp_path)["meta"] == {"pulled_at": "2026-01-01"}
    assert build.load_data(tmp_path)["activities"] == []
    assert build.load_plan(tmp_path) == build.load(ROOT / "plan" / "plan.example.json")


def _salida(modo):
    cfg = {**ajustes.cargar_config(FIX), "modo": modo}
    vacio = {"daily_summaries": [{"calendarDate": "2029-12-30", "heartRate": {"restingValue": 60}}], "sleep": [], "hrv": [], "activities": [], "details": {}, "hr_zones": [],
             "meta": {}, "historial": None, "inbody": None}
    plan = build.load(ROOT / "plan" / "plan.example.json")
    ahora = datetime(2030, 1, 7, 12, tzinfo=ZoneInfo(cfg["timezone"]))   # el plan ya terminó
    return build.build(vacio, plan, cfg, ahora)


def test_modo_web_cambia_los_textos_de_ajustar():
    web, pages = _salida("web"), _salida("pages")
    assert "/ajustar" in pages["hoy"]["tarjeta"]["siguiente"]
    assert web["hoy"]["tarjeta"]["siguiente"] == "Ve a Ajustes para el siguiente bloque"
    assert "/ajustar" not in json.dumps(web, ensure_ascii=False)
    assert "config.yaml" not in json.dumps(web, ensure_ascii=False)
    assert web["ui"]["acciones_url"] is None and web["ui"]["menu"] == []


def test_menu_y_acciones_url_los_pone_quien_llama():
    cfg = {**ajustes.cargar_config(FIX), "modo": "web", "acciones_url": "https://github.com/x/y/actions",
           "menu": [{"texto": "Ajustes", "url": "ajustes"}]}
    ui = build.build_ui(cfg, build.load(ROOT / "plan" / "plan.example.json"))
    assert ui["acciones_url"] == "https://github.com/x/y/actions"
    assert ui["menu"] == [{"texto": "Ajustes", "url": "ajustes"}]


def test_sugerencia_repetir_en_modo_web():
    cfg = {**ajustes.cargar_config(FIX), "modo": "web"}
    assert m.sugerencia_semana(0, 3, 0, 10, 10, cfg)["texto"] == "Considera repetir la semana (desde Ajustes)"


class ClienteFalso:
    """Sin red: responde lo mínimo que pide garmin_connect."""
    def get(self, path, params=None):
        if "dailysummaries" in path:
            return {"data": [{"calendarDate": "2026-11-01", "heartRate": {"restingValue": 60}}]}
        if path.endswith("activities/search/activities"):
            return [{"activityId": 7, "activityName": "Carrera X", "startTimeLocal": "2026-11-20 07:00:00",
                     "activityType": {"typeKey": "running"}, "eventType": {"typeKey": "uncategorized"},
                     "distance": 3000.0, "duration": 1200.0}]
        if path.endswith("/details"):
            return {}
        if "/activity-service/activity/" in path:
            return {"summaryDTO": {"directWorkoutRpe": 50, "directWorkoutFeel": 50}}
        if "heartRateZones" in path:
            return [{"sport": "DEFAULT", "maxHeartRateUsed": 190}]
        return [] if "sleep" in path or "bodyBattery" in path or "stress" in path else {}


def test_garmin_connect_sin_config_yaml(tmp_path):
    codigo = (
        "import sys; sys.path.insert(0, %r)\n"
        "import garmin_connect as gc\n"
        "from test_motor_web import ClienteFalso\n"
        "gc.main(['4', '--dias-actividades', '30', '--historial-desde', '2026-01-01'], cliente=ClienteFalso())\n"
        % str(ROOT))
    env = {**os.environ, "GARMIN_USER_DIR": str(tmp_path), "PYTHONPATH": str(ROOT / "tests")}
    r = subprocess.run([sys.executable, "-c", codigo], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "config.yaml").exists()
    datos = tmp_path / "data"
    assert {p.name for p in datos.iterdir()} >= {"activities.json", "daily.json", "historial_corridas.json", "meta.json"}
    assert json.loads((datos / "activity_details.json").read_text())["7"]["rpe"] == 5.0
    assert len(json.loads((datos / "historial_corridas.json").read_text())) == 1
