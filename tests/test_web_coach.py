"""F5a: dar y quitar acceso de coach."""
from test_web_ajustes import listo
from test_web_cuentas import csrf_de
from web.modelos import Coach


def dar(cl, correo):
    return cl.post("/coach/dar", data={"csrf": csrf_de(cl.get("/coach").text), "correo": correo})


def test_sin_acceso_404_dar_ve_y_quitar_corta_con_sesion_abierta(web_ctx):
    uid_a, atleta = listo(web_ctx, "atleta@x.com")
    uid_c, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    assert coach.get(f"/a/{uid_a}/ajustes").status_code == 404
    assert coach.get(f"/a/{uid_a}/data.json").status_code == 404
    r = dar(atleta, "Coach@X.com")
    assert r.status_code == 303 and r.headers["location"] == "/coach?ok=1"
    assert "coach@x.com" in atleta.get("/coach").text
    assert coach.get(f"/a/{uid_a}/ajustes").status_code == 200
    assert coach.get(f"/a/{uid_a}/data.json").status_code == 200
    with web_ctx.sesiones() as db:
        fila = db.query(Coach).one().id
    atleta.post(f"/coach/quitar/{fila}", data={"csrf": csrf_de(atleta.get("/coach").text)})
    for ruta in ("/ajustes", "/data.json", "/plan/acciones", "/historial", "/cuerpo"):   # misma sesión del coach, sin volver a entrar
        assert coach.get(f"/a/{uid_a}{ruta}").status_code == 404
    assert "coach@x.com" not in atleta.get("/coach").text


def test_no_puedes_ser_tu_propio_coach_ni_saber_si_existe_la_cuenta(web_ctx):
    uid, cl = listo(web_ctx, "yo@x.com")
    a = dar(cl, "yo@x.com")
    b = dar(cl, "nadie@x.com")
    assert a.status_code == b.status_code == 303 and a.headers["location"] == b.headers["location"] == "/coach?ok=1"
    with web_ctx.sesiones() as db:
        assert db.query(Coach).count() == 0


def test_quitar_exige_csrf_y_solo_tus_coaches(web_ctx):
    uid_a, atleta = listo(web_ctx, "a@x.com")
    uid_b, otro = listo(web_ctx, "b@x.com")
    uid_c, _ = listo(web_ctx, "c@x.com", con_plan=False)
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
        fila = db.query(Coach).one().id
    assert otro.post(f"/coach/quitar/{fila}", data={"csrf": "malo"}).status_code == 403
    otro.post(f"/coach/quitar/{fila}", data={"csrf": csrf_de(otro.get("/coach").text)})
    with web_ctx.sesiones() as db:
        assert db.query(Coach).count() == 1   # b no puede quitar el coach de a
