from datetime import date, timedelta

from test_web_cuentas import crear_usuario
from web import sincronizar as sz
from web.modelos import Subida, Usuario, ahora


def _u(ctx, db):
    return db.get(Usuario, crear_usuario(ctx))


def test_pedir_no_duplica_y_programada_no_cuenta(web_ctx):
    with web_ctx.sesiones() as db:
        u = _u(web_ctx, db)
        p, nueva = sz.pedir(db, u, "programada")
        assert nueva and sz.actual(db, u.id) is None and sz.actual(db, u.id, True).id == p.id
        s, nueva = sz.pedir(db, u, "normal")
        assert nueva and s.estado == "esperando"
        s2, nueva = sz.pedir(db, u, "treinta")
        assert not nueva and s2.id == s.id


def test_viva_vieja_pasa_a_error(web_ctx):
    with web_ctx.sesiones() as db:
        u = _u(web_ctx, db)
        s, _ = sz.pedir(db, u, "normal")
        s.actualizada = ahora() - timedelta(minutes=sz.VIVA_MIN + 1)
        db.commit()
        assert sz.actual(db, u.id) is None
        assert (s.estado, s.error) == ("error", "otra")
        assert sz.ultima_terminada(db, u.id).id == s.id


def test_avanzar_y_terminar(web_ctx):
    with web_ctx.sesiones() as db:
        u = _u(web_ctx, db)
        s, _ = sz.pedir(db, u, "comprobacion")
        sz.avanzar(db, s, "detalles", hechos=3, total=10)
        assert (s.estado, s.paso, s.hechos, s.total) == ("corriendo", "detalles", 3, 10)
        sz.terminar(db, s, True, nuevas=2)
        assert s.estado == "ok" and s.nuevas == 2 and u.historial_pendiente is True
        h, _ = sz.pedir(db, u, "historial")
        sz.terminar(db, h, True)
        assert u.historial_pendiente is False
        e, _ = sz.pedir(db, u, "normal")
        sz.terminar(db, e, False, "key_rechazada")
        assert (e.estado, e.error) == ("error", "key_rechazada")
        assert sz.ultima_terminada(db, u.id).id == e.id


def test_dias_y_rango(web_ctx):
    with web_ctx.sesiones() as db:
        u = _u(web_ctx, db)
        assert sz.dias_a_pedir(db, u) == 365
        assert sz.rango("comprobacion", db, u) == (1, 1)
        assert sz.rango("historial", db, u) == (365, 16)
        assert sz.rango("treinta", db, u) == (30, 5)
        hoy = date(2026, 6, 20)
        db.add(Subida(usuario_id=u.id, ok=True, fecha=ahora().replace(year=2026, month=6, day=18)))
        db.commit()
        assert sz.dias_a_pedir(db, u, hoy) == 9
        db.add(Subida(usuario_id=u.id, ok=True, fecha=ahora().replace(year=2026, month=6, day=20)))
        db.commit()
        assert sz.dias_a_pedir(db, u, hoy) == 7
        assert sz.rango("normal", db, u)[1] >= 1


# --- C3: el tubo habla de sincronizaciones ---
from test_web_tubo import auth, ctx, paquete_chico, subir, token, usuario_amigo   # noqa: E402,F401
from web.modelos import Sincronizacion   # noqa: E402

V2 = {"motor_version": 2}


def _instr(ctx, cuerpo=None, **claims):
    return ctx.cliente().post("/api/tubo/instrucciones", json=cuerpo, headers=auth(token(ctx, **claims)))


def _sincs(ctx):
    with ctx.sesiones() as db:
        return [(s.tipo, s.estado, s.paso, s.run_id, s.hechos, s.total, s.error, s.nuevas)
                for s in db.query(Sincronizacion).order_by(Sincronizacion.id)]


def test_motor_viejo_recibe_lo_de_hoy(ctx):
    usuario_amigo(ctx, repo_id=777)
    r = _instr(ctx).json()
    assert set(r) == {"vinculado", "historial_desde", "dias_actividades"} and r["dias_actividades"] == 365
    assert _sincs(ctx) == []


def test_v2_normal_con_rangos_y_cabecera(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    r = _instr(ctx, V2, run_id="55", event_name="workflow_dispatch").json()
    assert (r["dias_actividades"], r["semanas_salud"]) == (365, 16)   # primera vez
    assert _sincs(ctx)[0][:4] == ("normal", "corriendo", "prepara", 55)
    with ctx.sesiones() as db:
        db.add(Subida(usuario_id=uid, ok=True, bytes=1, fecha=ahora() - timedelta(days=3)))
        s = db.query(Sincronizacion).one()
        s.estado, s.terminada = "ok", ahora()
        db.commit()
    cab = {**auth(token(ctx, run_id="56")), "X-Motor-Version": "2"}
    r = ctx.cliente().post("/api/tubo/instrucciones", headers=cab).json()
    assert (r["dias_actividades"], r["semanas_salud"]) == (10, 2)


def test_v2_programada_y_no_se_mezcla(ctx):
    usuario_amigo(ctx, repo_id=777)
    _instr(ctx, V2, run_id="1", event_name="schedule")
    _instr(ctx, V2, run_id="2", event_name="workflow_dispatch")
    assert [x[:2] + x[3:4] for x in _sincs(ctx)] == [("programada", "corriendo", 1), ("normal", "corriendo", 2)]
    # un avance de la corrida 2 no toca la programada
    ctx.cliente().post("/api/tubo/avance", json={"paso": "busca"}, headers=auth(token(ctx, run_id="2")))
    assert [x[2] for x in _sincs(ctx)] == ["prepara", "busca"]


def test_avance_error_y_validacion(ctx):
    usuario_amigo(ctx, repo_id=777)
    _instr(ctx, V2, run_id="9")
    h = auth(token(ctx, run_id="9"))
    cl = ctx.cliente()
    r = cl.post("/api/tubo/avance", json={"paso": "detalles", "hechos": 3, "total": 10}, headers=h)
    assert r.json() == {"ok": True} and _sincs(ctx)[0][2:6] == ("detalles", 9, 3, 10)
    for malo in ({"paso": "x"}, {"paso": "busca", "hechos": -1}, {"paso": "busca", "total": "3"},
                 {"paso": "busca", "hechos": 10**6}, {"paso": "busca", "error": 5}):
        assert cl.post("/api/tubo/avance", json=malo, headers=h).status_code == 422
    assert cl.post("/api/tubo/avance", json={"paso": "arranca", "error": "key_rechazada"}, headers=h).status_code == 200
    assert _sincs(ctx)[0][1] == "error" and _sincs(ctx)[0][6] == "key_rechazada"
    assert cl.post("/api/tubo/avance", json={"paso": "arranca"}).status_code == 401


def test_error_raro_es_otra(ctx):
    usuario_amigo(ctx, repo_id=777)
    _instr(ctx, V2, run_id="9")
    ctx.cliente().post("/api/tubo/avance", json={"paso": "arranca", "error": "lo que sea"}, headers=auth(token(ctx, run_id="9")))
    assert _sincs(ctx)[0][6] == "otra"


def test_subida_cierra_con_nuevas_y_mala_con_error(ctx):
    usuario_amigo(ctx, repo_id=777)
    _instr(ctx, V2, run_id="7")
    r = subir(ctx.cliente(), token(ctx, run_id="7"), paquete_chico())
    assert r.status_code == 200
    assert _sincs(ctx)[0][1] == "ok" and _sincs(ctx)[0][7] == 1
    _instr(ctx, V2, run_id="8")
    assert subir(ctx.cliente(), token(ctx, run_id="8"), {"esquema": 1}).status_code == 422
    assert _sincs(ctx)[1][1:] [0] == "error" and _sincs(ctx)[1][6] == "otra"


def test_comprobacion_ok_deja_historial_pendiente(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    with ctx.sesiones() as db:
        db.add(Sincronizacion(usuario_id=uid, tipo="comprobacion", estado="esperando"))
        db.commit()
    r = _instr(ctx, V2, run_id="3").json()
    assert (r["dias_actividades"], r["semanas_salud"]) == (1, 1)
    assert subir(ctx.cliente(), token(ctx, run_id="3"), paquete_chico()).status_code == 200
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).historial_pendiente is True
    r = _instr(ctx, V2, run_id="4").json()
    assert (r["dias_actividades"], r["semanas_salud"]) == (365, 16) and r["historial_desde"]
    assert _sincs(ctx)[1][0] == "historial"
