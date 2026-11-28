"""F7b: panel de admin."""
from datetime import timedelta


from web.modelos import Invitacion, Subida, Usuario, ahora
from ayudas import csrf_de, listo


def admin_listo(ctx):
    a, cl = listo(ctx, "pedro@example.com")   # ADMIN_CORREO de la prueba
    return a, cl


def test_no_admin_recibe_404(web_ctx):
    _, cl = listo(web_ctx, "a@x.com")
    assert cl.get("/admin").status_code == 404
    assert web_ctx.cliente().get("/admin").status_code == 404
    assert cl.get("/privacidad/mis-datos").status_code == 200
    assert 'href="/admin"' not in cl.get("/privacidad/mis-datos").text
    csrf = csrf_de(cl.get("/privacidad/mis-datos").text)
    assert cl.post("/admin/invitar", data={"csrf": csrf, "nota": "x"}).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.query(Invitacion).count() == 0


def test_admin_crea_y_revoca_invitacion(web_ctx):
    _, cl = admin_listo(web_ctx)
    assert 'href="/admin"' in cl.get("/privacidad/mis-datos").text
    html = cl.get("/admin").text
    r = cl.post("/admin/invitar", data={"csrf": csrf_de(html), "nota": "para Luis"})
    assert r.status_code == 200 and "https://ahilallevas.test/invitacion/" in r.text
    r2 = cl.get("/admin")
    assert "para Luis" in r2.text and "Revocar" in r2.text
    with web_ctx.sesiones() as db:
        inv = db.query(Invitacion).one()
        h = inv.token_hash
    r3 = cl.post("/admin/revocar", data={"csrf": csrf_de(r2.text), "id": h})
    assert "Invitación revocada" in r3.text
    with web_ctx.sesiones() as db:
        assert db.query(Invitacion).count() == 0
    assert "https://ahilallevas.test/invitacion/" not in cl.get("/admin").text   # el token no queda a la vista


def test_lista_solo_columnas_y_atrasados(web_ctx):
    _, cl = admin_listo(web_ctx)
    b, _ = listo(web_ctx, "b@x.com")
    c, _ = listo(web_ctx, "c@x.com")
    with web_ctx.sesiones() as db:
        db.add(Subida(usuario_id=b, motor="abc123", fecha=ahora() - timedelta(days=5)))
        db.add(Subida(usuario_id=c, motor="abc123", fecha=ahora()))
        ub = db.get(Usuario, b)
        ub.apodo, ub.repo = "Beto", "beto/garmin"
        db.commit()
    t = cl.get("/admin").text
    assert "b@x.com" in t and "Beto" in t and "beto/garmin" in t and "abc123" in t
    assert t.count("<strong>atrasado</strong>") == 1
    assert "/a/" not in t   # no es coach de nadie: ninguna liga a dashboards ajenos
    for secreto in ("restingValue", "calendarDate", "z2_min"):
        assert secreto not in t
