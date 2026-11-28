from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
from dashboard import ajustes

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
    assert [x["id"] for x in c["categorias"]] == ["fuerza", "hiit", "cardio", "movilidad", "caminar", "otra"]
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
])
def test_errores_claros(tmp_path, texto, frag):
    with pytest.raises(ajustes.ConfigError, match=frag):
        cfg(tmp_path, texto.replace("corrida: {inicio: 2026-11-09}\ncorrida:", "corrida:"))


def test_sin_archivo(tmp_path):
    with pytest.raises(ajustes.ConfigError, match="/setup"):
        ajustes.cargar_config(tmp_path)


def test_categorias_propias_se_suman_a_las_de_defecto(tmp_path):
    c = cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: cf, nombre: CrossFit, letra: CF, tipos: [hiit, strength_training], intensa: true}\n")
    # la propia va primero; fuerza y hiit quedan cubiertas por ella y se omiten; cardio y movilidad se suman
    assert [x["id"] for x in c["categorias"]] == ["cf", "cardio", "movilidad", "caminar", "otra"]
    c = cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: pesas, nombre: Pesas, letra: P, tipos: [strength_training]}\n")
    assert [x["id"] for x in c["categorias"]] == ["pesas", "hiit", "cardio", "movilidad", "caminar", "otra"]


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


def test_claves_del_motor_anterior_se_ignoran_sin_error(tmp_path):
    """Nivel, intensidad, calidad o escalón raros o viejos caen al valor por defecto: nunca rompen una config vieja."""
    c = cfg(tmp_path, MINIMA.replace("corrida: {", "corrida: {nivel: pro, intensidad: calidad, calidad_tipos: [x], escalon: 9/9, "))
    assert (c["nivel"], c["intensidad"], c["calidad_tipos"], c["escalon"], c["variada"]) == ("intermedio", "calidad", [], None, False)


def test_iconos_por_tipo_de_garmin_y_de_config(tmp_path):
    for k, i in {"running": "correr", "treadmill_running": "correr", "trail_running": "correr", "strength_training": "mancuerna",
                 "hiit": "rayo", "cardio": "rayo", "cycling": "bici", "indoor_cycling": "bici", "virtual_ride": "bici",
                 "spinning": "bici", "lap_swimming": "nadar", "open_water_swimming": "nadar", "walking": "caminar",
                 "hiking": "caminar", "yoga": "yoga", "pilates": "yoga", "otra_cosa": "punto"}.items():
        assert ajustes.icono_de_tipo(k) == i
    c = cfg(tmp_path, MINIMA)
    assert {x["id"]: x["icono"] for x in c["categorias"]} == {"fuerza": "mancuerna", "hiit": "rayo", "cardio": "bici", "movilidad": "yoga", "caminar": "caminar", "otra": "punto"}
    c = cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: cf, nombre: CrossFit, letra: CF, tipos: [strength_training, hiit], icono: rayo}\n")
    assert c["categorias"][0]["icono"] == "rayo"
    with pytest.raises(ajustes.ConfigError):
        cfg(tmp_path, MINIMA + "actividades:\n  categorias:\n    - {id: cf, nombre: CF, letra: CF, tipos: [hiit], icono: dragon}\n")


PRUEBAS_CFG = "perfil: {zona_horaria: America/Merida, edad: 30}\ncorrida:\n  inicio: 2026-11-09\n  pruebas: %s\n"


def test_pruebas_de_la_config(tmp_path):
    assert cfg(tmp_path, MINIMA)["pruebas"] == []
    c = cfg(tmp_path, PRUEBAS_CFG % "[{fecha: 2027-02-01, tipo: 5k, valor: 1500}, {fecha: 2026-08-01, tipo: fc_fija, valor: 430}]")
    assert [p["fecha"] for p in c["pruebas"]] == ["2026-08-01", "2027-02-01"] and c["pruebas"][1]["valor"] == 1500.0


def test_pruebas_invalidas(tmp_path):
    with pytest.raises(ajustes.ConfigError, match="tipo"):
        cfg(tmp_path, PRUEBAS_CFG % "[{fecha: 2027-02-01, tipo: 10k, valor: 1}]")
    with pytest.raises(ajustes.ConfigError, match="valor"):
        cfg(tmp_path, PRUEBAS_CFG % "[{fecha: 2027-02-01, tipo: 5k}]")
