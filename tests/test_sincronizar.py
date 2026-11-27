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
