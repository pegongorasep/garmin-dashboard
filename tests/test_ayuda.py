"""Ayuda personalizada (v4.5 F4): se arma con la config y el plan de cada persona."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
from dashboard import ayuda
import planes_v6
from dashboard.ajustes import cargar_config

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
    return ayuda.armar_ayuda(cfg, planes_v6.generar(cfg), ZONAS, 144), cfg


def test_ayuda_de_un_plan_v6_nombra_sus_sesiones_y_no_las_que_no_tiene(tmp_path):
    t = texto(ayuda_de(tmp_path)[0])
    assert "Z2 #1, Z2 #2 y Larga" in t
    assert "Variada" not in t and "Picos de Z3" not in t and "30 min a FC fija" not in t and "5 km a tope" not in t


def test_sesiones_salen_del_plan_y_zonas_con_lpm(tmp_path):
    b, cfg = ayuda_de(tmp_path)
    plan = planes_v6.generar(cfg)
    assert f"Tu plan tiene {len(plan['weeks'][0]['sessions'])} sesiones por semana" in texto(b)
    # un plan con 2 sesiones por semana lo dice
    plan2 = {**plan, "weeks": [{**w, "sessions": w["sessions"][:2]} for w in plan["weeks"]]}
    assert "Tu plan tiene 2 sesiones por semana" in texto(ayuda.armar_ayuda(cfg, plan2, ZONAS, 144))
    t = texto(b)
    assert "Z2 138–150 lpm" in t and "Ritmo a 144 lpm" in t and "Z2 (138–150 lpm)" in t


def test_umbrales_de_la_config(tmp_path):
    cfg = {**config_de(tmp_path), "rhr_tolerance_bpm": 6, "sleep_min_hours": 7}
    t = texto(ayuda.armar_ayuda(cfg, planes_v6.generar(cfg), ZONAS, 144))
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
