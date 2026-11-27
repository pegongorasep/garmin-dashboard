"""E5: formulario de actividad a mano (rutas, permisos, CSRF, validación, caché, coach)."""
import json
from datetime import date, datetime, timedelta, timezone

from test_web_ajustes import HOY as AHORA, listo
from test_web_cuentas import csrf_de
from web import calculo, manual
from web.modelos import ActividadManual, Coach, Usuario

HOY = date(2026, 11, 25)   # el reloj de `listo`


def datos(**kw):
    return {"tipo": "correr", "fecha": "2026-11-24", "distancia": "5", "tiempo": "30:00", **kw}


def enviar(cl, url, form, ir=None):
    r = cl.get(ir or url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **form}, follow_redirects=False)


def filas(web_ctx, uid):
    with web_ctx.sesiones() as db:
        return [(f.id, f.tipo, f.distancia_m, f.duracion_s, f.esfuerzo, f.fc_prom, f.nota, f.fecha)
                for f in manual.de_persona(db, uid)]


def test_crear_editar_y_borrar(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.get("/actividad/nueva")
    assert r.status_code == 200 and 'value="correr" data-unidad="km" checked' in r.text and "2026-11-25" in r.text
    r = enviar(cl, "/actividad/nueva", datos(esfuerzo="6", fc_prom="150", nota="rica"))
    assert r.status_code == 303 and r.headers["location"] == "/#hoy"
    [(aid, tipo, dist, dur, esf, fc, nota, fecha)] = filas(web_ctx, uid)
    assert (tipo, dist, dur, esf, fc, nota, fecha) == ("correr", 5000, 1800, 6, 150, "rica", date(2026, 11, 24))
    r = cl.get(f"/actividad/{aid}")
    assert r.status_code == 200 and "6:00" in r.text and 'value="30:00"' in r.text   # ritmo calculado en Python
    r = enviar(cl, f"/actividad/{aid}", datos(tipo="natacion", distancia="800", tiempo="20:00"))
    assert r.status_code == 303
    assert filas(web_ctx, uid)[0][1:4] == ("natacion", 800, 1200)
    assert "2:30" in cl.get(f"/actividad/{aid}").text   # por 100 m
    r = enviar(cl, f"/actividad/{aid}/borrar", {}, ir=f"/actividad/{aid}")
    assert r.status_code == 303 and r.headers["location"] == "/#hoy" and filas(web_ctx, uid) == []


def test_query_tipo_y_fecha_y_otra_con_lista(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.get("/actividad/nueva?tipo=caminar&fecha=2026-11-20")
    assert 'value="caminar" data-unidad="km" checked' in r.text and "2026-11-20" in r.text
    enviar(cl, "/actividad/nueva", datos(tipo="otra", otro="yoga", distancia="", tiempo="1:00:00"))
    assert filas(web_ctx, uid)[0][1:4] == ("yoga", None, 3600)
    assert 'value="otra" data-unidad="lista" checked' in cl.get(f"/actividad/{filas(web_ctx, uid)[0][0]}").text


def test_errores_400_con_valores_puestos(web_ctx):
    uid, cl = listo(web_ctx)
    for campos, clave in [({"fecha": "2026-11-26"}, "La fecha no puede ser futura"), ({"tiempo": "99:99"}, "El tiempo no es válido"),
                          ({"distancia": ""}, "Escribe la distancia")]:
        r = enviar(cl, "/actividad/nueva", datos(nota="conservada", **campos), ir="/actividad/nueva")
        assert r.status_code == 400 and clave in r.text and "conservada" in r.text
    assert filas(web_ctx, uid) == []


def test_csrf_obligatorio(web_ctx):
    uid, cl = listo(web_ctx)
    assert cl.post("/actividad/nueva", data=datos(), follow_redirects=False).status_code == 403
    assert cl.post("/actividad/nueva", data={"csrf": "malo", **datos()}, follow_redirects=False).status_code == 403
    enviar(cl, "/actividad/nueva", datos())
    aid = filas(web_ctx, uid)[0][0]
    assert cl.post(f"/actividad/{aid}/borrar", data={}, follow_redirects=False).status_code == 403
    assert cl.post(f"/actividad/{aid}", data=datos(), follow_redirects=False).status_code == 403
    assert len(filas(web_ctx, uid)) == 1


def test_otra_persona_404_y_sin_sesion_a_entrar(web_ctx):
    uid, cl = listo(web_ctx)
    enviar(cl, "/actividad/nueva", datos())
    aid = filas(web_ctx, uid)[0][0]
    uid2, cl2 = listo(web_ctx, "b@x.com")
    assert cl2.get(f"/actividad/{aid}").status_code == 404
    assert enviar(cl2, f"/actividad/{aid}", datos(), ir="/actividad/nueva").status_code == 404
    assert enviar(cl2, f"/actividad/{aid}/borrar", {}, ir="/actividad/nueva").status_code == 404
    assert cl2.get(f"/a/{uid}/actividad/nueva").status_code == 404   # sin ser su coach
    assert cl2.get("/actividad/99999").status_code == 404
    assert len(filas(web_ctx, uid)) == 1
    anonimo = web_ctx.cliente()
    assert anonimo.get("/actividad/nueva", follow_redirects=False).headers["location"] == "/entrar"


def test_coach_con_permiso_si_y_sin_permiso_no(web_ctx):
    uid_a, _ = listo(web_ctx)
    uid_c, cl_c = listo(web_ctx, "coach@x.com")
    assert cl_c.get(f"/a/{uid_a}/actividad/nueva").status_code == 404
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    r = enviar(cl_c, f"/a/{uid_a}/actividad/nueva", datos(), ir=f"/a/{uid_a}/actividad/nueva")
    assert r.status_code == 303 and r.headers["location"] == f"/a/{uid_a}/#hoy"
    [(aid, *_)] = filas(web_ctx, uid_a)
    assert filas(web_ctx, uid_c) == []
    assert enviar(cl_c, f"/a/{uid_a}/actividad/{aid}", datos(tiempo="40:00"), ir=f"/a/{uid_a}/actividad/{aid}").status_code == 303
    assert filas(web_ctx, uid_a)[0][3] == 2400
    # la actividad del atleta no se abre con el id del coach (ni al revés)
    assert cl_c.get(f"/actividad/{aid}").status_code == 404
    r = enviar(cl_c, f"/a/{uid_a}/actividad/{aid}/borrar", {}, ir=f"/a/{uid_a}/actividad/{aid}")
    assert r.status_code == 303 and filas(web_ctx, uid_a) == []


def test_guardar_invalida_la_cache_y_la_nota_no_sale(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        antes = calculo.calcular(db, db.get(Usuario, uid), AHORA)
    enviar(cl, "/actividad/nueva", datos(nota="NOTA-SECRETA-77"))
    with web_ctx.sesiones() as db:
        despues = calculo.calcular(db, db.get(Usuario, uid), AHORA)   # misma hora: solo la huella pudo cambiar el resultado
    assert antes != despues and "NOTA-SECRETA-77" not in json.dumps(despues, ensure_ascii=False)
    sem = despues["semanas_hoy"][despues["semana_hoy_idx"]]
    assert next(d for d in sem["dias"] if d["fecha"] == "2026-11-24")["corrida"]
    aid = filas(web_ctx, uid)[0][0]
    r = enviar(cl, f"/actividad/{aid}", datos(tiempo="45:00"))
    with web_ctx.sesiones() as db:
        otra = calculo.calcular(db, db.get(Usuario, uid), AHORA)
    assert otra != despues


def test_actividad_de_hoy_a_las_8_ya_cuenta(web_ctx):
    """a_actividad pone la hora a mediodía; a las 8:00 locales no debe verse como futura."""
    uid, cl = listo(web_ctx)
    madrugada = datetime(2026, 11, 25, 14, 0, tzinfo=timezone.utc)   # 8:00 en Mérida
    with web_ctx.sesiones() as db:
        db.add(ActividadManual(usuario_id=uid, fecha=date(2026, 11, 25), tipo="correr", distancia_m=5000, duracion_s=1800))
        db.commit()
        salida = calculo.calcular(db, db.get(Usuario, uid), madrugada)
        u = db.get(Usuario, uid)
        u.sin_plan, u.repo_id = True, 1   # la tarjeta del grupo («semana libre») tampoco la trata como futura
        db.commit()
        libre = calculo.calcular(db, u, madrugada)["semana_libre"]
    assert libre["km"] == 5.0 and any(d["actividades"] for d in libre["dias"] if not d["futuro"])
    sem = salida["semanas_hoy"][salida["semana_hoy_idx"]]
    hoy = next(d for d in sem["dias"] if d["fecha"] == "2026-11-25")
    assert hoy["corrida"] and hoy["corrida"]["minutos"] == 30


def _fila_del_dia(salida, fecha):
    sem = salida["semanas_hoy"][salida["semana_hoy_idx"]]
    return next(d for d in sem["dias"] if d["fecha"] == fecha)["actividades"]


def test_e6_marca_liga_y_ritmo_en_el_sitio(web_ctx):
    uid, cl = listo(web_ctx)
    enviar(cl, "/actividad/nueva", datos(nota="NOTA-SECRETA-77", esfuerzo="6"))
    aid = filas(web_ctx, uid)[0][0]
    with web_ctx.sesiones() as db:
        salida = calculo.calcular(db, db.get(Usuario, uid), AHORA)
    [fila] = _fila_del_dia(salida, "2026-11-24")
    assert fila["manual"] is True and fila["id"] == f"m{aid}" and fila["rpe"] == 6
    assert salida["ui"]["editar_manual"] == {f"m{aid}": f"/actividad/{aid}"}
    assert fila["detalle"]["ritmo_s"] == 360 and fila["detalle"]["zonas"] is None   # 30:00 en 5 km = 6:00/km
    assert "NOTA-SECRETA-77" not in json.dumps(salida, ensure_ascii=False)
    from dashboard import validar
    assert validar.problemas(salida) == []
    malo = {**salida, "ui": {**salida["ui"], "editar_manual": {"m1": "https://x.com/a"}}}
    assert any("editar_manual" in p for p in validar.problemas(malo))


def test_e6_coach_sin_permiso_no_recibe_liga_y_con_permiso_con_prefijo(web_ctx):
    uid, cl = listo(web_ctx)
    enviar(cl, "/actividad/nueva", datos())
    aid = filas(web_ctx, uid)[0][0]
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert calculo.calcular(db, u, AHORA, pref=f"/a/{uid}", editable=False)["ui"]["editar_manual"] == {}
        con = calculo.calcular(db, u, AHORA, pref=f"/a/{uid}", editable=True)["ui"]["editar_manual"]
    assert con == {f"m{aid}": f"/a/{uid}/actividad/{aid}"}


def test_e6_una_de_garmin_no_lleva_marca():
    from datetime import date as d
    from dashboard import build
    garmin = {"id": 99, "startTimeLocal": "2026-11-24T07:00:00", "duration": 1800, "distance": 5000,
              "activityType": {"typeKey": "running"}, "averageHR": 150}
    from dashboard import ajustes
    cfg = ajustes.config_por_defecto()
    filas_ = build.actividades_del_dia(d(2026, 11, 24), [garmin], cfg)
    assert filas_ and "manual" not in filas_[0] and "id" not in filas_[0]
