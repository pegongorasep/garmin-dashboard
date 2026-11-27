"""Motor v6 G2: `web.cli convertir-v6` (ensayo, aplicar, idempotencia, carreras, errores por persona). Solo SQLite."""
import copy
from datetime import date, datetime, timedelta, timezone

import gen_plan
import motor_v6
from test_web_cuentas import CONFIG, crear_usuario
from web import cli, convertir_v6
from web.modelos import Ajustes, Cambio, DatoGarmin, Plan

AHORA = datetime(2026, 11, 25, 15, 0, tzinfo=timezone.utc)   # miércoles
LUNES = date(2026, 11, 23)


def crudo_con(metas=None):
    c = copy.deepcopy(CONFIG)
    c.setdefault("corrida", {})["inicio"] = (LUNES - timedelta(days=14)).isoformat()
    c["corrida"]["metas"] = metas or []
    return c


def sembrar_persona(ctx, correo, metas=None, con_corridas=True):
    uid = crear_usuario(ctx, correo, con_ajustes=True)
    crudo = crudo_con(metas)
    with ctx.sesiones() as db:
        db.get(Ajustes, uid).config = crudo
        db.add(Plan(usuario_id=uid, plan=gen_plan.generar(__import__("ajustes").normalizar_config(crudo))))
        if con_corridas:
            for i in range(10):
                f = datetime(2026, 11, 24) - timedelta(days=2 * i + 1)
                db.add(DatoGarmin(usuario_id=uid, tipo="actividad", clave=str(i), contenido={
                    "id": i, "startTimeLocal": f.isoformat(sep=" "), "duration": 2400.0, "activityType": {"typeKey": "running"}}))
        db.commit()
    return uid


def correr(ctx, **kw):
    salida = []
    with ctx.sesiones() as db:
        errores = convertir_v6.correr(db, AHORA, salida=salida.append, **kw)
    return errores, salida


def test_ensayo_no_escribe_y_aplicar_convierte(web_ctx):
    uid = sembrar_persona(web_ctx, "a@x.com")
    errores, salida = correr(web_ctx)
    assert errores == 0 and any(f"id={uid} convertiría" in s and "antes=" in s and "después=" in s for s in salida)
    with web_ctx.sesiones() as db:
        assert not motor_v6.es_v6(db.get(Plan, uid).plan) and db.query(Cambio).count() == 0
    errores, salida = correr(web_ctx, aplicar=True)
    assert errores == 0
    with web_ctx.sesiones() as db:
        plan = db.get(Plan, uid).plan
        assert motor_v6.es_v6(plan) and plan["start"] == LUNES.isoformat()
        assert db.get(Ajustes, uid).config["corrida"]["inicio"] == LUNES.isoformat()
        c = db.query(Cambio).one()
        assert c.via == "sistema" and c.antes["plan"] is not None   # queda en el historial: se puede deshacer


def test_idempotente(web_ctx):
    sembrar_persona(web_ctx, "a@x.com")
    correr(web_ctx, aplicar=True)
    errores, salida = correr(web_ctx, aplicar=True)
    assert errores == 0 and any("ya es v6" in s for s in salida)
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).count() == 1


def test_primera_carrera_futura_entra_al_plan_y_las_otras_quedan_metas(web_ctx):
    metas = [{"id": "pasada", "tipo": "carrera", "fecha": "2026-10-01", "distancia_km": 10, "nombre": "vieja"},
             {"id": "uno", "tipo": "carrera", "fecha": "2027-01-10", "distancia_km": 10, "nombre": "10K"},
             {"id": "dos", "tipo": "carrera", "fecha": "2027-03-14", "distancia_km": 21, "nombre": "21K"}]
    uid = sembrar_persona(web_ctx, "a@x.com", metas)
    errores, salida = correr(web_ctx, aplicar=True)
    assert errores == 0 and any("carreras conservadas=3 (en el plan: sí)" in s for s in salida)
    with web_ctx.sesiones() as db:
        plan, metas_n = db.get(Plan, uid).plan, db.get(Ajustes, uid).config["corrida"]["metas"]
        assert plan["meta"]["carrera"]["km"] == 10
        assert {m["id"]: m["en_plan"] for m in metas_n} == {"pasada": False, "uno": True, "dos": False}


def test_nada_personal_en_la_salida_y_filtro_por_correo(web_ctx):
    uid = sembrar_persona(web_ctx, "a@x.com")
    otro = sembrar_persona(web_ctx, "b@x.com")
    _, salida = correr(web_ctx, aplicar=True, correo="b@x.com")
    texto = "\n".join(salida)
    assert "a@x.com" not in texto and "b@x.com" not in texto and "Ana" not in texto and f"id={otro}" in texto and f"id={uid}" not in texto
    with web_ctx.sesiones() as db:
        assert not motor_v6.es_v6(db.get(Plan, uid).plan) and motor_v6.es_v6(db.get(Plan, otro).plan)


def test_un_error_no_detiene_a_los_demas(web_ctx, monkeypatch):
    malo = sembrar_persona(web_ctx, "a@x.com")
    bueno = sembrar_persona(web_ctx, "b@x.com")
    real = convertir_v6.motor_v6.generar_v6

    def falla_al_primero(entrada):
        if falla_al_primero.n == 0:
            falla_al_primero.n += 1
            raise ValueError("no cuadra")
        return real(entrada)
    falla_al_primero.n = 0
    monkeypatch.setattr(convertir_v6.motor_v6, "generar_v6", falla_al_primero)
    errores, salida = correr(web_ctx, aplicar=True)
    assert errores == 1 and any(f"id={malo} ERROR ValueError" in s for s in salida)
    with web_ctx.sesiones() as db:
        assert not motor_v6.es_v6(db.get(Plan, malo).plan) and motor_v6.es_v6(db.get(Plan, bueno).plan)


def test_sin_plan_o_sin_ajustes_se_saltan_y_cli(web_ctx, capsys):
    crear_usuario(web_ctx, "a@x.com")                       # sin ajustes ni plan
    uid = sembrar_persona(web_ctx, "b@x.com")
    assert cli.main(["convertir-v6"], settings=web_ctx.settings, motor=web_ctx.motor) == 0
    assert f"id={uid} convertiría" in capsys.readouterr().out
    with web_ctx.sesiones() as db:
        assert not motor_v6.es_v6(db.get(Plan, uid).plan)
    assert cli.main(["convertir-v6", "--aplicar"], settings=web_ctx.settings, motor=web_ctx.motor) == 0
    with web_ctx.sesiones() as db:
        assert motor_v6.es_v6(db.get(Plan, uid).plan)


def test_una_corrida_de_5_min_no_deja_la_semana_1_bajo_el_piso(web_ctx):
    uid = sembrar_persona(web_ctx, "a@x.com", con_corridas=False)
    with web_ctx.sesiones() as db:
        db.add(DatoGarmin(usuario_id=uid, tipo="actividad", clave="1", contenido={
            "id": 1, "startTimeLocal": "2026-11-10 07:00:00", "duration": 300.0, "activityType": {"typeKey": "running"}}))
        db.commit()
    errores, salida = correr(web_ctx, aplicar=True)
    assert errores == 0
    with web_ctx.sesiones() as db:
        plan = db.get(Plan, uid).plan
    assert motor_v6.minutos_semana(plan["weeks"][0]) >= motor_v6.UMBRALES["ajuste_piso"][plan["meta"]["nivel"]]


def test_el_piso_es_una_sola_constante():
    import nivel
    assert motor_v6.UMBRALES["ajuste_piso"] is nivel.PISO_NIVEL
    r = nivel.nivel_desde_datos([], date(2026, 11, 25))
    assert r["inicio_minutos"] >= nivel.PISO_NIVEL[r["nivel"]]
