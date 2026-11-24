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
    assert c["zone_pcts"] == [50, 60, 70, 80, 90] and c["done_ratio"] == 0.7 and c["rpe_heavy"] == 8
    assert "semana_tipica" not in c   # actividades.semana vieja se tolera y se ignora
    assert c["categorias"][0]["tipos"] == ["hiit", "strength_training"]


def test_minima_usa_defaults(tmp_path):
    c = cfg(tmp_path, MINIMA)
    assert c["max_hr"] == 190 and c["max_hr_floor"] == 190 and c["fc_max_correa_desde"] is None
    assert [x["id"] for x in c["categorias"]] == ["fuerza", "hiit", "cardio", "movilidad"]
    assert c["nivel"] == "intermedio" and c["plan_semanas"] == 12 and c["base_min"] == {"z2": 20, "larga": 40}
    assert c["inbody"] is True and "walking" not in c["tipos_con_detalle"]


def test_umbrales_se_sobreescriben(tmp_path):
    c = cfg(tmp_path, MINIMA + "umbrales: {rpe_heavy: 7}\n")
    assert c["rpe_heavy"] == 7 and c["done_ratio"] == 0.7


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
