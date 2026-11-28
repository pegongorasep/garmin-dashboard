"""Plan viejo -> plan v6 (`plan/convertir_viejo.py`) y el comando `web.cli cargar-plan-viejo`."""
import json
from datetime import datetime
from pathlib import Path

import pytest

from plan import convertir_viejo as cv
from plan import motor_v6
from dashboard import validar
from web import calculo, cli
from web.modelos import Ajustes, CacheData, Cambio, Plan
from ayudas import crear_usuario

ROOT = Path(__file__).parent.parent
VIEJO = json.loads((ROOT / "plan" / "plan.json").read_text()) if (ROOT / "plan" / "plan.json").exists() else None
pytestmark = pytest.mark.skipif(VIEJO is None, reason="plan/plan.json es personal y no está en este checkout")


def test_convertir_conserva_semanas_sesiones_y_minutos():
    v6 = cv.convertir(VIEJO)
    assert motor_v6.es_v6(v6) and v6["start"] == VIEJO["start"] == "2026-11-09" and len(v6["weeks"]) == 12
    assert v6["meta"]["nivel"] == "base" and v6["meta"]["dias"] == 3 and v6["meta"]["semanas"] == 12
    assert v6["weeks"] == VIEJO["weeks"]   # ni una sesión cambia
    assert [motor_v6.minutos_semana(w) for w in v6["weeks"]] == [motor_v6.minutos_semana(w) for w in VIEJO["weeks"]]
    assert "carrera" not in v6["meta"] and not any(w.get("evento") for w in v6["weeks"])   # la carrera va como meta con fecha


def test_convertir_no_toca_el_original_y_valida_la_entrada():
    antes = json.dumps(VIEJO, sort_keys=True)
    cv.convertir(VIEJO)
    assert json.dumps(VIEJO, sort_keys=True) == antes
    with pytest.raises(ValueError):
        cv.convertir({"weeks": []})
    with pytest.raises(ValueError):
        cv.convertir({**VIEJO, "start": "2026-11-10"})   # no es lunes


def test_ajustes_con_carrera_quita_la_de_7_semanas():
    crudo = {"corrida": {"inicio": "2026-11-16", "semanas": 7, "semanas_repetidas": [3],
                         "metas": [{"id": "a", "tipo": "carrera", "fecha": "2027-01-10", "distancia_km": 10, "nombre": "10K", "en_plan": True}]}}
    nuevo = cv.ajustes_con_carrera(crudo, cv.convertir(VIEJO), "2027-01-10")
    c = nuevo["corrida"]
    assert c["inicio"] == "2026-11-09" and c["semanas"] == 12 and "semanas_repetidas" not in c
    assert [(m["fecha"], m["distancia_km"], m.get("en_plan")) for m in c["metas"]] == [("2027-01-10", 10, None)]
    assert crudo["corrida"]["semanas"] == 7   # no muta


def _cuenta(ctx):
    uid = crear_usuario(ctx, "pedro@example.com", con_ajustes=True)
    siete = motor_v6.generar_v6({"nivel": "base", "dias": 3, "inicio": "2026-11-16", "semanas": 7, "inicio_minutos": 100})
    with ctx.sesiones() as db:
        db.add(Plan(usuario_id=uid, plan=siete))
        db.commit()
    return uid, siete


def _con_historial_viejo(ctx, uid, donde="antes"):
    """Siembra un cambio cuyo `antes` (o `despues`) trae el plan viejo, como si lo hubiera reemplazado un plan v6."""
    with ctx.sesiones() as db:
        db.add(Cambio(atleta_id=uid, via="sistema", descripcion="plan v6", antes={"plan": VIEJO} if donde == "antes" else None,
                      despues={"plan": VIEJO} if donde == "despues" else {"plan": {"x": 1}}))
        db.commit()


@pytest.mark.parametrize("donde", ["antes", "despues"])
def test_cli_busca_el_plan_viejo_en_el_historial(web_ctx, capsys, donde):
    uid, siete = _cuenta(web_ctx)
    _con_historial_viejo(web_ctx, uid, donde)
    assert cli.main(["cargar-plan-viejo", "pedro@example.com"], web_ctx.settings, web_ctx.motor) == 0
    out = capsys.readouterr().out
    assert "tomado de: historial de la cuenta" in out and f"«{donde}»" in out and "12 semanas" in out
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == siete   # en seco


def test_cli_sin_plan_viejo_en_el_historial_avisa(web_ctx, capsys):
    _cuenta(web_ctx)
    assert cli.main(["cargar-plan-viejo", "pedro@example.com"], web_ctx.settings, web_ctx.motor) == 1
    assert "No encuentro un plan viejo" in capsys.readouterr().err


def test_cli_en_seco_no_escribe(web_ctx, capsys):
    uid, siete = _cuenta(web_ctx)
    assert cli.main(["cargar-plan-viejo", "pedro@example.com", "--archivo", str(ROOT / "plan" / "plan.json")], web_ctx.settings, web_ctx.motor) == 0
    out = capsys.readouterr().out
    assert "12 semanas" in out and "2026-11-09" in out and "2027-01-10" in out and "en seco" in out
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == siete and db.query(Cambio).count() == 0


def test_cli_si_reemplaza_guarda_el_anterior_y_se_deshace(web_ctx, capsys):
    uid, siete = _cuenta(web_ctx)
    _con_historial_viejo(web_ctx, uid)
    with web_ctx.sesiones() as db:
        db.add(CacheData(usuario_id=uid, contenido={"x": 1}, huella="h"))
        db.commit()
    assert cli.main(["cargar-plan-viejo", "pedro@example.com", "--si"], web_ctx.settings, web_ctx.motor) == 0
    assert "deshacer" in capsys.readouterr().out.lower()
    with web_ctx.sesiones() as db:
        p = db.get(Plan, uid).plan
        assert len(p["weeks"]) == 12 and p["start"] == "2026-11-09" and motor_v6.es_v6(p)
        assert db.get(CacheData, uid) is None   # caché invalidada
        c = db.query(Cambio).order_by(Cambio.id.desc()).first()
        assert c.antes["plan"] == siete   # el plan de 7 semanas queda en el historial
        metas = db.get(Ajustes, uid).config["corrida"]["metas"]
        assert any(m["fecha"] == "2027-01-10" and m["distancia_km"] == 10 for m in metas)
        cid = c.id
    assert cli.main(["deshacer-cambio", str(cid)], web_ctx.settings, web_ctx.motor) == 0
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid).plan == siete


def test_round_trip_el_sitio_muestra_las_mismas_semanas(web_ctx):
    uid, _ = _cuenta(web_ctx)
    _con_historial_viejo(web_ctx, uid)
    cli.main(["cargar-plan-viejo", "pedro@example.com", "--si"], web_ctx.settings, web_ctx.motor)
    with web_ctx.sesiones() as db:
        from web.modelos import Usuario
        salida = calculo._calcular_cacheado(db, db.get(Usuario, uid), datetime(2026, 11, 27, 15, 0))
    assert validar.problemas(salida) == []
    semanas = salida["plan"]["semanas"]
    assert len(semanas) == 12 and salida["plan"]["inicio"] == "2026-11-09" and salida["plan"]["largo"] == 12
    assert salida["plan"]["semana_actual"] == 3
    assert [s["n"] for s in semanas] == list(range(1, 13))
    for s, w in zip(semanas, VIEJO["weeks"]):
        if s["n"] == salida["plan"]["semana_actual"]:
            assert s["plan_min"] <= sum(x["minutes"] for x in w["sessions"])
            continue  # la semana actual se ajusta según lo realmente registrado
        assert [x["minutes"] for x in s["sessions"]] == [x["minutes"] for x in w["sessions"]] and s["plan_min"] == sum(x["minutes"] for x in w["sessions"])
        assert [x["id"] for x in s["sessions"]] == [x["id"] for x in w["sessions"]]
    assert all("km_est" in x for s in semanas[2:] for x in s["sessions"])   # la actual (3) y las futuras
    assert semanas[8].get("marca") == "carrera"   # la carrera del 10 de enero cae en la semana 9
