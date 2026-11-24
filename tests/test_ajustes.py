import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
import ajustes  # noqa: E402

MINIMA = """
perfil: {zona_horaria: America/Merida, edad: 30}
corrida: {inicio: 2026-11-09}
"""


def cfg(tmp_path, texto):
    (tmp_path / "config.yaml").write_text(texto)
    return ajustes.cargar_config(tmp_path)


def test_config_de_pedro_da_el_dict_plano():
    c = ajustes.cargar_config(ROOT / "tests" / "fixtures")
    assert c["timezone"] == "America/Merida" and c["max_hr"] == 189 and c["max_hr_floor"] == 183
    assert c["plan_start"] == "2026-11-09" and c["fc_max_correa_desde"] == "2026-10-26"
    assert c["zone_pcts"] == [50, 60, 70, 80, 90] and c["done_ratio"] == 0.7 and c["esfuerzo_duro"] == 8
    assert "semana_tipica" not in c   # actividades.semana vieja se tolera y se ignora
    assert c["categorias"][0]["tipos"] == ["hiit", "strength_training"]


def test_minima_usa_defaults(tmp_path):
    c = cfg(tmp_path, MINIMA)
    assert c["max_hr"] == 190 and c["max_hr_floor"] == 190 and c["fc_max_correa_desde"] is None
    assert [x["id"] for x in c["categorias"]] == ["fuerza", "hiit", "cardio", "movilidad"]
    assert c["nivel"] == "intermedio" and c["plan_semanas"] == 12 and c["base_min"] == {"z2": 20, "larga": 40}
    assert c["inbody"] is True and "walking" not in c["tipos_con_detalle"]


def test_umbrales_se_sobreescriben(tmp_path):
    c = cfg(tmp_path, MINIMA + "umbrales: {esfuerzo_duro: 7}\n")
    assert c["esfuerzo_duro"] == 7 and c["done_ratio"] == 0.7


def test_rpe_heavy_de_configs_viejas_se_tolera_y_se_ignora(tmp_path):
    c = cfg(tmp_path, MINIMA + "umbrales: {rpe_heavy: 7}\n")
    assert c["esfuerzo_duro"] == 8 and c["done_ratio"] == 0.7


@pytest.mark.parametrize("texto,frag", [
    ("perfil: {edad: 30}\ncorrida: {inicio: 2026-11-09}\n", "zona_horaria"),
    ("perfil: {zona_horaria: America/Merida}\ncorrida: {inicio: 2026-11-09}\n", "fc_max"),
    ("perfil: {zona_horaria: America/Merida, edad: 30}\ncorrida: {}\n", "inicio"),
    (MINIMA.replace("2026-11-09", "2026-11-10"), "lunes"),
    (MINIMA + "corrida: {inicio: 2026-11-09, nivel: pro}\n", "nivel"),
    ("perfil: {zona_horaria: America/Merida, edad: 30}\ncorrida: {inicio: 2026-11-09, intensidad: calidad}\n", "calidad_tipos"),
])
def test_errores_claros(tmp_path, texto, frag):
    with pytest.raises(ajustes.ConfigError, match=frag):
        cfg(tmp_path, texto.replace("corrida: {inicio: 2026-11-09}\ncorrida:", "corrida:"))


def test_sin_archivo(tmp_path):
    with pytest.raises(ajustes.ConfigError, match="/setup"):
        ajustes.cargar_config(tmp_path)


def test_maximo_cuatro_categorias(tmp_path):
    cats = "".join(f"  - {{id: c{i}, nombre: C{i}, letra: X, tipos: [yoga]}}\n" for i in range(5))
    with pytest.raises(ajustes.ConfigError, match="Máximo 4"):
        cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n" + cats)


def test_titulo_por_defecto_y_carreras(tmp_path):
    c = cfg(tmp_path, MINIMA)
    assert c["titulo"] == "Mi entreno" and c["carreras"] == []
    c = cfg(tmp_path, MINIMA.replace("{inicio: 2026-11-09}", "{inicio: 2026-11-09, carreras: [2026-11-21, 2026-05-02, 2026-11-21]}"))
    assert c["carreras"] == ["2026-05-02", "2026-11-21"]


def test_carrera_con_fecha_mala(tmp_path):
    with pytest.raises(ajustes.ConfigError):
        cfg(tmp_path, MINIMA.replace("{inicio: 2026-11-09}", "{inicio: 2026-11-09, carreras: [mañana]}"))


def test_actividades_semana_vieja_se_tolera_y_se_ignora(tmp_path):
    c = cfg(tmp_path, MINIMA + "actividades:\n  semana: {lun: nada, mar: inexistente}\n")
    assert "semana_tipica" not in c and c["categorias"]


def test_variada_default_false_y_calidad_con_variada_rota_los_5(tmp_path):
    assert cfg(tmp_path, MINIMA)["variada"] is False
    c = cfg(tmp_path, MINIMA.replace("corrida: {", "corrida: {variada: true, intensidad: calidad, "))
    assert c["variada"] is True and c["calidad_tipos"] == list(ajustes.CALIDAD_TIPOS) and len(c["calidad_tipos"]) == 5
    with pytest.raises(ajustes.ConfigError):   # sin variada, calidad sigue pidiendo tipos
        cfg(tmp_path, MINIMA.replace("corrida: {", "corrida: {intensidad: calidad, "))
    assert cfg(tmp_path, MINIMA.replace("corrida: {", "corrida: {intensidad: calidad, calidad_tipos: [fartlek], "))["calidad_tipos"] == ["fartlek"]


def test_iconos_por_tipo_de_garmin_y_de_config(tmp_path):
    for k, i in {"running": "correr", "treadmill_running": "correr", "trail_running": "correr", "strength_training": "mancuerna",
                 "hiit": "rayo", "cardio": "rayo", "cycling": "bici", "indoor_cycling": "bici", "virtual_ride": "bici",
                 "spinning": "bici", "lap_swimming": "nadar", "open_water_swimming": "nadar", "walking": "caminar",
                 "hiking": "caminar", "yoga": "yoga", "pilates": "yoga", "otra_cosa": "punto"}.items():
        assert ajustes.icono_de_tipo(k) == i
    c = cfg(tmp_path, MINIMA)
    assert {x["id"]: x["icono"] for x in c["categorias"]} == {"fuerza": "mancuerna", "hiit": "rayo", "cardio": "bici", "movilidad": "yoga"}
    c = cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: cf, nombre: CrossFit, letra: CF, tipos: [strength_training, hiit], icono: rayo}\n")
    assert c["categorias"][0]["icono"] == "rayo"
    with pytest.raises(ajustes.ConfigError):
        cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: cf, nombre: CF, letra: CF, tipos: [hiit], icono: dragon}\n")
