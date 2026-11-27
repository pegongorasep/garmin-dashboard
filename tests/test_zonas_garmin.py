"""Zonas de FC de Garmin (Motor v6 F1): lista blanca numérica del paquete, zonas que usa el motor y su origen."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT))
import build  # noqa: E402
import metrics as m  # noqa: E402
import paquete  # noqa: E402
import validar  # noqa: E402
from test_build import AHORA, CONFIG_FIXTURE, fixture  # noqa: E402

# Perfil de Garmin con zonas propias (no de fábrica) y otro con las de fábrica (60 % de reserva, etc.)
PROPIO = {"sport": "RUNNING", "trainingMethod": "HR_RESERVE", "restingHeartRateUsed": 55, "lactateThresholdHeartRateUsed": 172,
          "zone1Floor": 118, "zone2Floor": 132, "zone3Floor": 146, "zone4Floor": 160, "zone5Floor": 174, "maxHeartRateUsed": 190}
FABRICA = {"sport": "DEFAULT", "trainingMethod": "HR_RESERVE", "restingHeartRateUsed": 60, "lactateThresholdHeartRateUsed": None,
           "zone1Floor": 126, "zone2Floor": 137, "zone3Floor": 150, "zone4Floor": 164, "zone5Floor": 176, "maxHeartRateUsed": 189}


def test_paquete_deja_solo_lo_numerico_de_las_zonas(tmp_path):
    sucio = {**PROPIO, "userProfilePK": 77, "serial": "ABC123", "nombre": "Pedro", "trainingMethod": "ARCHIVO con espacios y nombre"}
    (tmp_path / "hr_zones.json").write_text(json.dumps([sucio, {"sport": "DEFAULT", "maxHeartRateUsed": 190}]))
    hr = paquete.armar(tmp_path, "s")["archivos"]["hr_zones"]
    assert hr[0] == {"sport": "RUNNING", "restingHeartRateUsed": 55, "lactateThresholdHeartRateUsed": 172, "zone1Floor": 118,
                     "zone2Floor": 132, "zone3Floor": 146, "zone4Floor": 160, "zone5Floor": 174, "maxHeartRateUsed": 190}
    assert hr[1] == {"sport": "DEFAULT", "maxHeartRateUsed": 190}     # perfil viejo: solo lo que trae
    (tmp_path / "hr_zones.json").write_text(json.dumps([FABRICA]))
    assert paquete.armar(tmp_path, "s")["archivos"]["hr_zones"] == [FABRICA]   # el umbral None se conserva


def test_validar_paquete_rechaza_campos_de_zonas_fuera_de_la_lista(tmp_path):
    (tmp_path / "hr_zones.json").write_text(json.dumps([PROPIO]))
    pq = paquete.armar(tmp_path, "s")
    assert paquete.validar(pq) == []
    pq["archivos"]["hr_zones"][0]["serial"] = "ABC"
    assert any("hr_zones" in p for p in paquete.validar(pq))
    pq["archivos"]["hr_zones"] = [{"sport": "DEFAULT", "zone1Floor": "126"}]
    assert any("hr_zones" in p for p in paquete.validar(pq))


def test_zonas_garmin_prefiere_running_y_cae_a_default():
    z = m.zonas_garmin([FABRICA, PROPIO])
    assert z[0] == ("Z1", 118, 132) and z[4] == ("Z5", 174, 190)   # RUNNING gana aunque venga después
    assert m.zonas_garmin([FABRICA])[0] == ("Z1", 126, 137)
    assert m.zonas_garmin({**FABRICA}) is not None                  # un dict suelto también vale


def test_zonas_garmin_none_si_falta_o_es_incoherente():
    assert m.zonas_garmin([]) is None and m.zonas_garmin(None) is None
    assert m.zonas_garmin([{"sport": "DEFAULT", "maxHeartRateUsed": 190}]) is None     # perfil viejo del paquete
    assert m.zonas_garmin([{**PROPIO, "zone3Floor": 100}]) is None                     # no crecen
    assert m.zonas_garmin([{**PROPIO, "zone5Floor": 195}]) is None                     # el piso pasa de la máxima
    assert m.zonas_garmin([{**PROPIO, "zone2Floor": None}]) is None


def test_zonas_de_fabrica():
    assert m.zonas_de_fabrica([FABRICA]) is True
    pct_max = {"sport": "DEFAULT", "maxHeartRateUsed": 190, "zone1Floor": 95, "zone2Floor": 114, "zone3Floor": 133,
               "zone4Floor": 152, "zone5Floor": 171}
    assert m.zonas_de_fabrica([pct_max]) is True
    assert m.zonas_de_fabrica([PROPIO]) is False and m.zonas_de_fabrica([]) is False


def _data(hr):
    return {**fixture(), "hr_zones": hr}


def _build(hr):
    plan = build.load(ROOT / "plan" / "plan.example.json")
    return build.build(_data(hr), plan, CONFIG_FIXTURE, AHORA)


def test_build_usa_las_zonas_de_garmin_y_dice_el_origen():
    out = _build([PROPIO])
    assert out["ui"]["zonas_origen"] == "garmin"
    assert [(z["piso"], z["techo"]) for z in out["zonas"]] == [(118, 132), (132, 146), (146, 160), (160, 174), (174, 190)]
    assert "zonas_garmin" not in out["ui"]["avisos"]      # zonas propias: sin aviso
    assert validar.problemas(out) == []


def test_build_sin_zonas_de_garmin_sigue_como_antes():
    for hr in ([], [{"sport": "DEFAULT", "maxHeartRateUsed": 190}]):
        out = _build(hr)
        assert out["ui"]["zonas_origen"] == "calculadas"
        assert [z["piso"] for z in out["zonas"]] != [118, 132, 146, 160, 174] and len(out["zonas"]) == 5
        if not hr:   # lo de siempre: Karvonen con la FC máx del config y la FC en reposo promedio
            assert out["zonas"] == [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in
                                    m.zones(CONFIG_FIXTURE["max_hr"], out["rhr_promedio_7d"], CONFIG_FIXTURE["zone_pcts"])]
        assert out["ui"]["avisos"]["zonas_garmin"]


def test_build_con_zonas_de_fabrica_sugiere_configurarlas():
    out = _build([FABRICA])
    assert out["ui"]["zonas_origen"] == "garmin" and out["ui"]["avisos"]["zonas_garmin"]
    assert build.huellas_avisos({}, None, {}, {}, 1) == {}      # sin el nuevo argumento, nada cambia
