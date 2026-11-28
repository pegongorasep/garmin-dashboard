import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).parent.parent

from dashboard import ajustes
from dashboard import build
from dashboard import paquete
from dashboard import validar

HAY_DATOS = (ROOT / "data" / "activities.json").exists() and (ROOT / "config.yaml").exists()


def escribir_paquete(pq: dict, destino: Path) -> Path:
    """Deja el paquete como archivos de data/ (lo mismo que hace la web al leer lo guardado)."""
    (destino / "data").mkdir(parents=True)
    a = paquete.a_archivos(pq)
    for nombre, contenido in a.items():
        (destino / "data" / f"{nombre}.json").write_text(json.dumps(contenido))
    return destino


def sin_menu(d: dict) -> dict:
    """ui.menu es nuevo en v5 (lista vacía fuera de la web)."""
    d = json.loads(json.dumps(d))
    d["ui"].pop("menu", None)
    return d


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales en data/")
@pytest.mark.parametrize("dia", ["2026-11-25", "2026-11-10", "2026-10-20", "2026-12-30"])
def test_regla_de_oro_build_crudo_igual_a_build_con_paquete(tmp_path, dia):
    cfg = ajustes.cargar_config(ROOT)
    ahora = datetime.fromisoformat(dia + "T12:00:00").replace(tzinfo=ZoneInfo(cfg["timezone"]))
    plan = build.load_plan(ROOT)
    crudo = build.load_data(ROOT)
    pq = paquete.armar(ROOT / "data", salt="123456")
    assert paquete.validar(pq) == []
    user = escribir_paquete(pq, tmp_path)
    (user / "plan").mkdir()
    web = build.load_data(user)
    web["inbody"] = crudo["inbody"]   # el InBody lo guarda la web aparte
    a = json.dumps(build.build(crudo, plan, cfg, ahora), sort_keys=True, ensure_ascii=False)
    b = json.dumps(build.build(web, plan, cfg, ahora), sort_keys=True, ensure_ascii=False)
    assert a == b


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales en data/")
def test_paquete_de_pedro_sin_claves_prohibidas_ni_perfil():
    pq = paquete.armar(ROOT / "data", salt="s")
    texto = json.dumps(pq)
    for k in validar.PROHIBIDAS - {"serie", "splits"}:
        assert f'"{k}"' not in texto
    assert "profile" not in pq["archivos"] and "displayName" not in texto
    assert paquete.validar(pq) == []
    # los ids son opacos y nunca el activityId original
    reales = {str(a["activityId"]) for a in json.loads((ROOT / "data" / "activities.json").read_text())}
    assert not (reales & {a["id"] for a in pq["archivos"]["activities"]})
    assert not (reales & set(pq["archivos"]["activity_details"]))


def datos_falsos(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "activities.json").write_text(json.dumps([{
        "activityId": 99, "activityName": "Carrera de la Calle Secreta", "activityUUID": "u", "ownerDisplayName": "Yo",
        "startLatitude": 1.0, "locationName": "Casa", "startTimeLocal": "2026-11-01 07:00:00", "distance": 5000.0,
        "duration": 1800.0, "averageHR": 150, "activityType": {"typeKey": "running", "typeId": 1},
        "eventType": {"typeKey": "uncategorized"}, "fastestSplit_1000": 300.0, "calories": 300.0,
        "movingDuration": 1700.0, "aerobicTrainingEffect": 2.5, "anaerobicTrainingEffect": 0.1,
        "trainingEffectLabel": "TEMPO", "aerobicTrainingEffectMessage": "MENSAJE_GARMIN"}]))
    (d / "activity_details.json").write_text(json.dumps({"99": {
        "rpe": 5.0, "feel": 50, "serie": [[0, 0, 100]], "splits": [{"tipo": "RWD_RUN", "seg": 1, "m": 2, "fc": 3, "n": 1, "x": 1}]}}))
    (d / "profile.json").write_text(json.dumps({"displayName": "Pedro"}))
    return d


def test_armar_suelta_nombres_ids_y_gps(tmp_path):
    pq = paquete.armar(datos_falsos(tmp_path), salt="s")
    a = pq["archivos"]["activities"][0]
    assert a["es_carrera"] is True and "activityName" not in a and "activityId" not in a and "startLatitude" not in a
    assert a["id"] == paquete.id_opaco("s", 99) and len(a["id"]) == 16
    assert a["calories"] == 300.0 and a["trainingEffectLabel"] == "TEMPO" and "aerobicTrainingEffectMessage" not in a   # detalle de la actividad en la web
    assert list(pq["archivos"]["activity_details"]) == [a["id"]]
    det = pq["archivos"]["activity_details"][a["id"]]
    assert "feel" not in det and det["serie"] == [[0, 0, 100]] and "x" not in det["splits"][0]
    assert "Secreta" not in json.dumps(pq) and paquete.validar(pq) == []


def test_validar_detecta_problemas(tmp_path):
    pq = paquete.armar(datos_falsos(tmp_path), salt="s")
    malo = json.loads(json.dumps(pq))
    malo["archivos"]["activities"][0]["activityName"] = "x"
    assert any("activityName" in p for p in paquete.validar(malo))
    malo = json.loads(json.dumps(pq))
    malo["archivos"]["activities"][0]["serie"] = []   # serie solo vale dentro de activity_details
    assert any("serie" in p for p in paquete.validar(malo))
    assert paquete.validar({**pq, "esquema": 2})
    assert paquete.validar({**pq, "archivos": {**pq["archivos"], "profile": {}}})
    assert paquete.validar([])
    grande = json.loads(json.dumps(pq))
    grande["archivos"]["activity_details"]["z"] = {"serie": [[1, 2, 3]] * 1_500_000}
    assert any("10 MB" in p for p in paquete.validar(grande))


def test_es_carrera_del_paquete_manda_sobre_el_nombre():
    from dashboard import metrics
    cfg = ajustes.config_por_defecto()
    base = {"activityType": {"typeKey": "running"}, "startTimeLocal": "2026-11-01 07:00:00"}
    assert metrics.es_carrera({**base, "es_carrera": True}, cfg)
    assert not metrics.es_carrera({**base, "es_carrera": False, "activityName": "Carrera 5K"}, cfg)
    assert metrics.es_carrera({**base, "activityName": "Carrera 5K"}, cfg)
    assert metrics.id_de({"id": "ab", "activityId": 1}) == "ab" and metrics.id_de({"activityId": 7}) == 7


def test_paquete_detalles_solo_pulso_derivado():
    e = {"rpe": 5, "pulso": "banda", "metadataDTO": {"sensors": [{"serialNumber": 9, "sku": "x"}]}, "serialNumber": 9}
    out = paquete._detalles({"123": e}, "sal")
    assert list(out.values()) == [{"rpe": 5, "pulso": "banda"}]
