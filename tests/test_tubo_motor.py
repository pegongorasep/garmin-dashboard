"""C4: el motor avisa su avance (garmin_connect.py + scripts/subir.py)."""
import json
from datetime import date
from pathlib import Path

import pytest
from ayudas import ENTORNO, HttpFalso, RespuestaFalsa

ROOT = Path(__file__).parent.parent
import garmin_connect as gc
from scripts import subir as sub


class ClienteFalso:
    def __init__(self, n=3):
        hoy = date.today().isoformat()
        self.acts = [{"activityId": i, "startTimeLocal": f"{hoy} 07:00:00", "activityType": {"typeKey": "running"}}
                     for i in range(n)]

    def get(self, path, params=None):
        if path.endswith("search/activities"):
            return self.acts if (params or {}).get("start", 0) == 0 else []
        if "/activity/" in path:
            return {"summaryDTO": {}}
        return None


@pytest.fixture
def aislado(tmp_path, monkeypatch):
    monkeypatch.setattr(gc, "DATA_DIR", tmp_path)
    return tmp_path


def test_garmin_con_y_sin_avance(aislado):
    gc.main([], cliente=ClienteFalso())   # sin callable: igual que siempre
    avisos = []
    gc.main(["--semanas-salud", "4"], cliente=ClienteFalso(), avance=lambda p, hechos=None, total=None: avisos.append((p, hechos, total)))
    pasos = [a[0] for a in avisos]
    assert pasos[0] == "busca" and ("encuentra", None, 3) in avisos and "detalles" in pasos and pasos[-1] == "salud"
    assert pasos.index("encuentra") < pasos.index("detalles") < pasos.index("salud")


def test_semanas_salud_opcion_gana(aislado, monkeypatch):
    vistas = []
    monkeypatch.setattr(gc, "pull_daily", lambda c, a, b: vistas.append((b - a).days) or
                        {"daily_summaries": [], "sleep": [], "hrv": [], "body_battery": [], "stress": []})
    gc.main(["8", "--semanas-salud", "3"], cliente=ClienteFalso(0))
    gc.main(["8"], cliente=ClienteFalso(0))
    assert vistas == [21, 56]
    with pytest.raises(SystemExit):
        gc.main(["--semanas-salud", "53"], cliente=ClienteFalso(0))


def _http(estado=200, cuerpo=None):
    return HttpFalso(lambda url, **kw: RespuestaFalsa(estado, cuerpo or {}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))


def test_instrucciones_manda_version_y_arma_args(monkeypatch):
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://actions.example/t")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "tok")
    http = _http(200, {"vinculado": True, "historial_desde": "2025-11-25", "dias_actividades": 365, "semanas_salud": 26})
    assert sub.instrucciones(http, lambda s: None) == "--dias-actividades 365 --historial-desde 2025-11-25 --semanas-salud 26"
    _, _, kw = [c for c in http.llamadas if c[0] == "post"][0]
    assert json.loads(kw["data"]) == {"motor_version": 2} and kw["headers"]["X-Motor-Version"] == "2"
    viejo = _http(200, {"vinculado": True, "dias_actividades": 30})   # web vieja: sin semanas_salud
    assert sub.instrucciones(viejo, lambda s: None) == "--dias-actividades 30"
    assert sub.ARGS_OK.match("") and sub.ARGS_OK.match("--semanas-salud 4") and sub.ARGS_OK.match("--dias-actividades 9 --semanas-salud 4") and not sub.ARGS_OK.match("--dias-actividades 9--semanas-salud 4;") and not sub.ARGS_OK.match("--semanas-salud 4; ls")


def test_avance_ignora_404_y_caidas():
    assert sub.avisar("busca", entorno=ENTORNO, http=_http(404)) is False
    assert sub.avisar("busca", entorno=ENTORNO, http=_http(200)) is True
    caido = HttpFalso(lambda u, **kw: (_ for _ in ()).throw(sub.requests.ConnectionError()), lambda u, **kw: RespuestaFalsa(200, {"value": "j"}))
    assert sub.avisar("busca", entorno=ENTORNO, http=caido) is False
    assert sub.main(["avance", "busca"]) == 0   # sin token OIDC: no truena


def _cuerpos(http):
    return [json.loads(kw["data"]) for m, u, kw in http.llamadas if m == "post" and u.endswith("/avance")]


def test_bajar_mapea_errores(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    env = {**ENTORNO, "PERSONAL_API_KEY": "x"}
    http = _http()
    assert sub.bajar([], lambda a, avance=None: avance("busca"), env, http) == 0
    assert _cuerpos(http) == [{"paso": "busca"}]

    http = _http()
    def rechazada(a, avance=None):
        raise gc.KeyRechazada("ERROR: Garmin rechazó la key (401)")
    assert sub.bajar([], rechazada, env, http) == 1 and _cuerpos(http)[-1]["error"] == "key_rechazada"

    class E401(Exception):
        response = type("R", (), {"status_code": 401})()
    http = _http()
    def f(a, avance=None):
        raise E401()
    assert sub.bajar([], f, env, http) == 1 and _cuerpos(http)[-1]["error"] == "key_rechazada"

    http = _http()
    def g(a, avance=None):
        raise ValueError("x")
    assert sub.bajar([], g, env, http) == 1 and _cuerpos(http)[-1]["error"] == "otra"

    http = _http()
    assert sub.bajar([], g, ENTORNO, http) == 1 and _cuerpos(http)[-1]["error"] == "sin_key"


def test_fallo_no_duplica(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path))
    http = _http()
    sub.fallo(ENTORNO, http)
    sub.fallo(ENTORNO, http)
    assert [c["error"] for c in _cuerpos(http)] == ["otra"]
    # ya hubo un error avisado por bajar -> fallo no manda otro
    (tmp_path / "ahi-error-avisado").unlink()
    http = _http()
    sub.bajar([], lambda a, avance=None: 1 / 0, {**ENTORNO, "PERSONAL_API_KEY": "x"}, http)
    sub.fallo(ENTORNO, http)
    assert len(_cuerpos(http)) == 1
