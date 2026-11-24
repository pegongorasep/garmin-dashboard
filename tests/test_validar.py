import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import validar  # noqa: E402

BUENO = {k: {} for k in validar.OBLIGATORIAS}


def test_valido():
    assert validar.problemas(BUENO) == []


def test_faltan_sobran_y_prohibidas():
    assert any("faltan" in p for p in validar.problemas({"generado": "x"}))
    assert any("lista blanca" in p for p in validar.problemas({**BUENO, "extra": 1}))
    malo = {**BUENO, "hoy": {"a": [{"activityName": "Corrida de X"}]}}
    assert validar.problemas(malo) == ["clave prohibida: /hoy/a[0]/activityName"]


def test_urls_solo_la_de_acciones():
    ok = {**BUENO, "ui": {"acciones_url": "https://github.com/a/b/actions/workflows/deploy.yml"}}
    assert validar.problemas(ok) == []
    assert validar.problemas({**BUENO, "hoy": {"x": "https://ejemplo.com"}}) == ["URL en el JSON: /hoy/x"]


def test_cli(tmp_path):
    f = tmp_path / "data.json"
    f.write_text(json.dumps(BUENO))
    py = [sys.executable, str(ROOT / "dashboard" / "validar.py")]
    assert subprocess.run([*py, str(f)], capture_output=True).returncode == 0
    f.write_text("{no es json")
    assert subprocess.run([*py, str(f)], capture_output=True).returncode == 1
    assert subprocess.run([*py, str(tmp_path / "nada.json")], capture_output=True).returncode == 1
