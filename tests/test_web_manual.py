"""E4: actividades a mano (modelo, validación, motor, cuenta). Sin pantallas todavía."""
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

import metrics
import semanal
import validar
from ajustes import normalizar_config
from test_motor_v6_f5 import INICIO, _cfg, _acts, plan_v6
from test_web_ajustes import listo
from web import calculo, cuenta, grupos_resumen, manual
from web.modelos import ActividadManual, MiembroGrupo, Usuario

HOY = date(2026, 11, 25)
AHORA_UTC = datetime(2026, 11, 25, 18, 0)   # 12:00 en Mérida; miércoles


def form(**kw):
    return {"tipo": "correr", "fecha": "2026-11-24", "distancia": "5", "tiempo": "30:00", **kw}


def fila(db, uid, **kw):
    f = ActividadManual(usuario_id=uid, **{"fecha": date(2026, 11, 24), "tipo": "correr", "distancia_m": 5000,
                                           "duracion_s": 1800, **kw})
    db.add(f)
    db.commit()
    return f


# --- validación ---

def test_validar_correr_y_unidades():
    d, e = manual.validar(form(distancia="5,25", tiempo="1:02:03", esfuerzo="7", fc_prom="150", nota="  ok  "), HOY)
    assert e == {} and d == {"fecha": date(2026, 11, 24), "tipo": "correr", "distancia_m": 5250, "duracion_s": 3723,
                             "esfuerzo": 7, "fc_prom": 150, "nota": "ok"}
    d, e = manual.validar(form(tipo="natacion", distancia="800"), HOY)
    assert d["distancia_m"] == 800
    d, e = manual.validar(form(tipo="crossfit", distancia="99"), HOY)   # oculta: se ignora
    assert e == {} and d["distancia_m"] is None
    d, e = manual.validar(form(tipo="bicicleta", distancia=""), HOY)   # opcional
    assert e == {} and d["distancia_m"] is None


@pytest.mark.parametrize("campos,campo", [
    ({"tipo": "x"}, "tipo"), ({"fecha": "2026-11-26"}, "fecha_futura"), ({"fecha": "mañana"}, "fecha"),
    ({"distancia": ""}, "distancia"), ({"tipo": "caminar", "distancia": "0"}, "distancia"),
    ({"tiempo": ""}, "tiempo"), ({"tiempo": "70:99"}, "tiempo"), ({"tiempo": "0:00"}, "tiempo"),
    ({"esfuerzo": "11"}, "esfuerzo"), ({"fc_prom": "20"}, "fc_prom"), ({"nota": "x" * 281}, "nota")])
def test_validar_errores(campos, campo):
    d, e = manual.validar(form(**campos), HOY)
    assert d is None and e
    if campo == "fecha_futura":
        assert e == {"fecha": "web.manual.err.fecha_futura"}
    else:
        assert campo.split("_")[0] in e or campo in e


def test_a_actividad_forma_de_garmin_sin_nota(web_ctx):
    uid, _ = listo(web_ctx)
    with web_ctx.sesiones() as db:
        f = fila(db, uid, tipo="caminar", fc_prom=110, esfuerzo=4, nota="secreta")
        a = manual.a_actividad(f)
        assert a == {"id": f"m{f.id}", "es_carrera": False, "manual": True, "startTimeLocal": "2026-11-24T12:00:00",
                     "activityType": {"typeKey": "walking"}, "distance": 5000, "duration": 1800, "averageHR": 110}
        assert manual.detalle_de(f) == {"rpe": 4}
        assert "secreta" not in json.dumps(a)


# --- clasificación ---

def test_classify_mapa_fijo_de_las_manuales_y_walking_de_garmin():
    cfg = normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}})
    esperado = {"running": "run", "walking": "caminar", "hiit": "hiit", "strength_training": "fuerza", "cycling": "cardio",
                "lap_swimming": "cardio", "elliptical": "cardio", "yoga": "movilidad", "hiking": "otra", "sport": "otra", "other": "otra"}
    for tk, cat in esperado.items():
        assert metrics.classify({"manual": True, "activityType": {"typeKey": tk}}, cfg) == cat
    assert metrics.classify({"activityType": {"typeKey": "walking"}}, cfg) == "caminar"   # Garmin, sin umbral de duración
    assert metrics.classify({"activityType": {"typeKey": "hiking"}}, cfg) is None


def test_categoria_propia_que_se_queda_con_el_tipo_no_rompe_la_manual():
    cfg = normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"},
                             "actividades": {"categorias": [{"id": "cf", "nombre": "CF", "letra": "CF", "tipos": ["hiit", "strength_training"]}]}})
    assert "caminar" in {c["id"] for c in cfg["categorias"]} and "otra" in {c["id"] for c in cfg["categorias"]}
    assert metrics.classify({"manual": True, "activityType": {"typeKey": "hiit"}}, cfg) == "cf"


def test_unir_encadenadas_no_junta_las_manuales():
    cfg = normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}})
    g = {"id": "g1", "startTimeLocal": "2026-11-24T12:00:00", "duration": 3600, "activityType": {"typeKey": "strength_training"}}
    m1 = {"id": "m1", "manual": True, "startTimeLocal": "2026-11-24T12:00:00", "duration": 1800, "activityType": {"typeKey": "hiit"}}
    m2 = {"id": "m2", "manual": True, "startTimeLocal": "2026-11-24T12:00:00", "duration": 1800, "activityType": {"typeKey": "yoga"}}
    assert len(metrics.unir_encadenadas([g, m1, m2], cfg)) == 3
    g2 = {**g, "id": "g2", "startTimeLocal": "2026-11-24T13:00:00", "activityType": {"typeKey": "hiit"}}
    assert len(metrics.unir_encadenadas([g, g2], cfg)) == 1   # dos de Garmin pegadas siguen juntándose


# --- el motor las ve ---

def test_datos_de_las_agrega_y_la_huella_cambia(web_ctx):
    uid, _ = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        h0 = calculo.huella(db, u, "2026-11-25")
        f = fila(db, uid, esfuerzo=6, nota="privada")
        d = calculo.datos_de(db, u)
        assert [a["id"] for a in d["activities"]] == [f"m{f.id}"] and d["details"][f"m{f.id}"] == {"rpe": 6}
        h1 = calculo.huella(db, u, "2026-11-25")
        assert h1 != h0
        f.actualizada = f.actualizada + timedelta(seconds=5)
        db.commit()
        assert calculo.huella(db, u, "2026-11-25") != h1


def test_una_a_mano_cuenta_en_la_semana_y_la_nota_no_sale(web_ctx):
    uid, _ = listo(web_ctx)
    with web_ctx.sesiones() as db:
        fila(db, uid, nota="NOTA-PRIVADA-123", tipo="crossfit", distancia_m=None, esfuerzo=8)
        fila(db, uid, tipo="correr", fecha=date(2026, 11, 23))
        salida = calculo.calcular(db, db.get(Usuario, uid), AHORA_UTC)
    assert validar.problemas(salida) == []
    assert "NOTA-PRIVADA-123" not in json.dumps(salida, ensure_ascii=False)
    sem = salida["semanas_hoy"][salida["semana_hoy_idx"]]
    lun = next(d for d in sem["dias"] if d["fecha"] == "2026-11-23")
    mar = next(d for d in sem["dias"] if d["fecha"] == "2026-11-24")
    assert lun["corrida"] and lun["corrida"]["minutos"] == 30
    assert [o["cat"] for o in mar["otras"]] == ["crossfit"]   # la config del fixture trae su categoría crossfit para hiit


def test_garmin_y_a_mano_el_mismo_dia_no_se_juntan(web_ctx):
    uid, _ = listo(web_ctx)
    from web.modelos import DatoGarmin
    with web_ctx.sesiones() as db:
        db.add(DatoGarmin(usuario_id=uid, tipo="actividad", clave="g1", contenido={
            "id": "g1", "startTimeLocal": "2026-11-24 12:30:00", "duration": 1800.0, "distance": 0,
            "activityType": {"typeKey": "hiit"}}))
        db.commit()
        fila(db, uid, tipo="gimnasio", distancia_m=None)
        d = calculo.datos_de(db, db.get(Usuario, uid))
        cfg = calculo.config_de(db, db.get(Usuario, uid))
        assert len(metrics.unir_encadenadas(d["activities"], cfg)) == 2


def test_cuenta_en_ajustar_semana_real_prev():
    plan = plan_v6()
    cfg = _cfg(plan)
    hoy = INICIO + timedelta(weeks=1, days=2)
    garmin = _acts({0: 60})
    a_mano = [{"id": f"m{k}", "manual": True, "startTimeLocal": f"{INICIO + timedelta(days=2 * k)}T12:00:00", "duration": 20 * 60,
               "activityType": {"typeKey": "running"}} for k in range(3)]
    con = semanal.ajustar_plan(plan, {"activities": a_mano}, cfg, hoy)
    ref = semanal.ajustar_plan(plan, {"activities": garmin}, cfg, hoy)
    assert con["weeks"][1]["ajuste"]["real_prev"] == ref["weeks"][1]["ajuste"]["real_prev"] == 60
    assert semanal.ajustar_plan(plan, {"activities": []}, cfg, hoy) is plan


def test_tarjeta_del_grupo_cuenta_la_manual(web_ctx, monkeypatch):
    original = calculo.calcular   # reloj fijo: la tarjeta calcula «ahora» con el miércoles de AHORA_UTC
    monkeypatch.setattr(calculo, "calcular", lambda db, u, ahora_utc=None, *a, **k: original(db, u, AHORA_UTC, *a, **k))
    uid, cl = listo(web_ctx, con_plan=False)   # el reloj de `listo` es el miércoles 2026-11-25
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.sin_plan, u.repo_id = True, 1
        db.commit()
        fila(db, uid, fecha=HOY - timedelta(days=HOY.weekday()), tipo="correr", nota="NOTA-PRIVADA-9")
        t, _ = grupos_resumen._tarjeta_cruda(db, u, MiembroGrupo(usuario_id=uid, pausado=False))
    assert t["estado"] == "libre" and t["semana"]["minutos"] == 30 and t["semana"]["km"] == 5.0
    assert "NOTA-PRIVADA-9" not in json.dumps(t)


# --- cuenta ---

def test_mis_datos_incluye_con_nota_y_borrar_las_borra(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        fila(db, uid, nota="mi nota")
        z = cuenta.datos_de(db, db.get(Usuario, uid))
        assert z["actividades_manuales.json"][0]["nota"] == "mi nota"
        cuenta.borrar_cuenta(db, db.get(Usuario, uid))
        assert db.query(ActividadManual).count() == 0
