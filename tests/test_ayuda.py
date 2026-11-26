"""Ayuda personalizada (v4.5 F4): se arma con la config y el plan de cada persona."""
import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))
sys.path.insert(0, str(ROOT / "plan"))
import ayuda  # noqa: E402
import gen_plan  # noqa: E402
from ajustes import cargar_config  # noqa: E402

ZONAS = [("Z1", 125, 138), ("Z2", 138, 150), ("Z3", 150, 163), ("Z4", 163, 176), ("Z5", 176, 189)]


def config_de(tmp_path, **corrida):
    """Config de tests/fixtures/config_ejemplo.yaml con cambios en `corrida`, cargada con el motor."""
    c = yaml.safe_load((ROOT / "tests" / "fixtures" / "config_ejemplo.yaml").read_text())
    c["corrida"].update({"inicio": "2026-11-09", **corrida})
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(c, allow_unicode=True))
    return cargar_config(tmp_path)


def texto(bloques) -> str:
    return "\n".join(" ".join([b["titulo"], *b["parrafos"], *(f"{i['t'] or ''} {i['x']}" for i in b["lista"])]) for b in bloques)


def ayuda_de(tmp_path, **corrida):
    cfg = config_de(tmp_path, **corrida)
    return ayuda.armar_ayuda(cfg, gen_plan.generar(cfg), ZONAS, 144), cfg


def test_novato_con_caminatas_no_habla_de_calidad_ni_variada(tmp_path):
    b, _ = ayuda_de(tmp_path, nivel="novato", intensidad="solo_z2", caminatas=True, variada=False, base_min={"z2": 15, "larga": 20})
    t = texto(b)
    assert "Calidad" not in t and "Variada" not in t and "Picos de Z3" not in t
    assert "trote 3'/camina 1'" in t and "trote 8'/camina 1'" in t and "% de trote" in t
    assert "trotando sin caminar" in t and "5 km a tope" not in t and "30 min a FC fija" not in t
    assert "Tu plan tiene 3 sesiones por semana: Z2 #1, Z2 #2 y Larga." in t


def test_corredor_nombra_sus_tipos_de_calidad_y_su_prueba(tmp_path):
    b, _ = ayuda_de(tmp_path, nivel="corredor", intensidad="calidad", calidad_tipos=["tempo_z3", "intervalos"], variada=False)
    t = texto(b)
    assert "Tempo Z3 y Intervalos" in t and "Z2 #1, Calidad y Larga" in t
    assert "Threshold" not in t and "Fartlek" not in t
    assert "5 km a tope" in t and "trotando sin caminar" not in t and "30 min a FC fija" not in t
    assert "ni las sesiones de calidad" in t and "% de trote" not in t


def test_variada_solo_si_el_plan_la_tiene(tmp_path):
    con, _ = ayuda_de(tmp_path, variada=True)
    sin, _ = ayuda_de(tmp_path, variada=False)
    assert "Variada" in texto(con) and "Espiga" in texto(con)
    assert "Variada" not in texto(sin)


def test_picos_z3_solo_con_z2_poca_z3(tmp_path):
    con, _ = ayuda_de(tmp_path, intensidad="z2_poca_z3", variada=False)
    sin, _ = ayuda_de(tmp_path, intensidad="solo_z2", variada=False)
    assert "Picos de Z3" in texto(con) and "Picos de Z3" not in texto(sin)


def test_solo_su_tipo_de_prueba(tmp_path):
    por_tipo = {"fc_fija": "30 min a FC fija", "trote_continuo": "trotando sin caminar", "5k": "5 km a tope"}
    for corrida, tipo in (({}, "fc_fija"), ({"nivel": "novato", "intensidad": "solo_z2", "caminatas": True}, "trote_continuo"),
                          ({"nivel": "corredor", "intensidad": "calidad", "calidad_tipos": ["tempo_z3"]}, "5k")):
        b, _ = ayuda_de(tmp_path, **corrida)
        t = texto(b)
        assert por_tipo[tipo] in t and all(v not in t for k, v in por_tipo.items() if k != tipo), tipo


def test_sesiones_salen_del_plan_y_zonas_con_lpm(tmp_path):
    b, cfg = ayuda_de(tmp_path)
    plan = gen_plan.generar(cfg)
    assert f"Tu plan tiene {len(plan['weeks'][0]['sessions'])} sesiones por semana" in texto(b)
    # un plan con 2 sesiones por semana lo dice
    plan2 = {**plan, "weeks": [{**w, "sessions": w["sessions"][:2]} for w in plan["weeks"]]}
    assert "Tu plan tiene 2 sesiones por semana" in texto(ayuda.armar_ayuda(cfg, plan2, ZONAS, 144))
    t = texto(b)
    assert "Z2 138–150 lpm" in t and "Ritmo a 144 lpm" in t and "Z2 (138–150 lpm)" in t


def test_umbrales_de_la_config(tmp_path):
    cfg = {**config_de(tmp_path), "rhr_tolerance_bpm": 6, "sleep_min_hours": 7}
    t = texto(ayuda.armar_ayuda(cfg, gen_plan.generar(cfg), ZONAS, 144))
    assert "+ 6 lpm" in t and "menos de 7 h" in t


def test_sin_plan_no_truena(tmp_path):
    cfg = config_de(tmp_path)
    b = ayuda.armar_ayuda(cfg, {}, ZONAS, 144)
    assert [x["titulo"] for x in b][0] == "El semáforo de cada mañana" and "Tus sesiones" not in texto(b)


def test_pedro_ayuda_en_el_json():
    cfg = cargar_config(ROOT)
    plan = json.loads((ROOT / "plan" / "plan.json").read_text())
    t = texto(ayuda.armar_ayuda(cfg, plan, ZONAS, 144))
    assert "Calidad" not in t and "Variada" not in t and "% de trote" not in t and "CrossFit" in t
