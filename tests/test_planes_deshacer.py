"""P4: repetir / retomar solo se deshace durante la misma semana; los demás cambios, igual que siempre."""
from datetime import datetime, timezone

from web import cambios
from web.modelos import Cambio
from ayudas import CONFIG, crudo, HOY, listo, tok

LUNES_SIG = datetime(2026, 11, 30, 18, 0, tzinfo=timezone.utc)   # lunes de la semana siguiente (HOY es miércoles 25)


def _fijar_fecha(ctx):
    """Los cambios se fechan con el reloj real: se alinean con el reloj de la prueba."""
    with ctx.sesiones() as db:
        for c in db.query(Cambio):
            c.fecha = HOY.replace(tzinfo=None)
        db.commit()


def _intentar(ctx, uid, cl, cid):
    cl.post(f"/historial/{cid}/deshacer", data={"csrf": tok(cl)})
    return crudo(ctx, uid)


def _botones(cl):
    return cl.get("/historial").text.count("/deshacer")


def test_retomar_se_deshace_la_misma_semana(web_ctx):
    uid, cl = listo(web_ctx)
    assert cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "2"}).status_code == 303
    _fijar_fecha(web_ctx)
    assert _botones(cl) >= 1
    with web_ctx.sesiones() as db:
        cid = db.query(Cambio).one().id
    assert _intentar(web_ctx, uid, cl, cid) == CONFIG


def test_retomar_no_se_deshace_en_la_semana_siguiente(web_ctx):
    uid, cl = listo(web_ctx)
    cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "2"})
    _fijar_fecha(web_ctx)
    with web_ctx.sesiones() as db:
        cid = db.query(Cambio).one().id
    web_ctx.app.state.reloj = lambda: LUNES_SIG
    antes = crudo(web_ctx, uid)
    assert _botones(cl) == 0
    r = cl.post(f"/historial/{cid}/deshacer", data={"csrf": tok(cl)})
    assert "solo durante la misma semana" in r.text
    assert crudo(web_ctx, uid) == antes


def test_repetir_igual(web_ctx):
    uid, cl = listo(web_ctx)
    r = cl.post("/plan/repetir", data={"csrf": tok(cl)})
    assert r.status_code == 303 and crudo(web_ctx, uid)["corrida"].get("saltos")
    _fijar_fecha(web_ctx)
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
        cid = c.id
        assert cambios.puede_deshacer(c, crudo(web_ctx, uid), HOY.date())
        assert not cambios.puede_deshacer(c, crudo(web_ctx, uid), LUNES_SIG.date())
    web_ctx.app.state.reloj = lambda: LUNES_SIG
    antes = crudo(web_ctx, uid)
    assert _intentar(web_ctx, uid, cl, cid) == antes


def test_viaje_viejo_cuyo_antes_borraria_un_salto_fijo_no_se_deshace(web_ctx):
    uid, cl = listo(web_ctx)
    cl.post("/plan/viaje", data={"csrf": tok(cl), "desde": "2026-12-14", "hasta": "2026-12-16", "correr": "si"})
    cl.post("/plan/retomar", data={"csrf": tok(cl), "semana": "2"})
    _fijar_fecha(web_ctx)
    with web_ctx.sesiones() as db:
        viaje = db.query(Cambio).order_by(Cambio.id).first().id
    web_ctx.app.state.reloj = lambda: LUNES_SIG
    antes = crudo(web_ctx, uid)
    assert _intentar(web_ctx, uid, cl, viaje) == antes   # su `antes` no traía el salto


def test_viaje_de_esta_semana_sin_tocar_saltos_si_se_deshace(web_ctx):
    uid, cl = listo(web_ctx)
    cl.post("/plan/viaje", data={"csrf": tok(cl), "desde": "2026-12-14", "hasta": "2026-12-16", "correr": "si"})
    _fijar_fecha(web_ctx)
    with web_ctx.sesiones() as db:
        cid = db.query(Cambio).one().id
    web_ctx.app.state.reloj = lambda: LUNES_SIG   # otra semana, pero no hay saltos de por medio
    assert _intentar(web_ctx, uid, cl, cid) == CONFIG
