"""F5a: dar y quitar acceso de coach."""
from test_web_ajustes import listo
from test_web_cuentas import csrf_de
from web.modelos import Cambio, Coach


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


def test_f5b_coach_ve_y_edita_a_su_atleta_con_via_coach_y_aviso(web_ctx):
    from web.modelos import Cambio
    uid_a, atleta = listo(web_ctx, "atleta@x.com")
    uid_c, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    uid_o, otro = listo(web_ctx, "otro@x.com")
    dar(atleta, "coach@x.com")
    pag = coach.get("/coach").text
    assert "Mis atletas" in pag and f"/a/{uid_a}/" in pag and "otro@x.com" not in pag
    assert coach.get(f"/a/{uid_o}/").status_code == 404 and coach.get(f"/a/{uid_o}/data.json").status_code == 404
    sitio = coach.get(f"/a/{uid_a}/")
    assert sitio.status_code == 200 and 'src="/app.js"' in sitio.text
    ui = coach.get(f"/a/{uid_a}/data.json").json()["ui"]
    assert all(a["url"].startswith(f"/a/{uid_a}/plan") for a in ui["plan_acciones"])
    assert all(v.startswith(f"/a/{uid_a}/plan/sesion/") for v in ui["editar_urls"].values())
    assert not any(m["url"] == "/coach" for m in ui["menu"])
    assert atleta.get("/data.json").json()["ui"]["plan_acciones"][0]["url"].startswith("/plan")
    r = coach.get(f"/a/{uid_a}/plan/acciones")
    assert r.status_code == 200
    r = coach.post(f"/a/{uid_a}/plan/viaje", data={"csrf": csrf_de(r.text), "desde": "2027-03-01", "hasta": "2027-03-05"})
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).filter(Cambio.atleta_id == uid_a).order_by(Cambio.id.desc()).first()
        assert c is not None and c.via == "coach" and c.autor_id == uid_c
    assert atleta.get("/data.json").json().get("avisos")


def test_a_sin_slash_redirige_y_el_coach_no_consume_avisos(web_ctx):
    uid_a, atleta = listo(web_ctx, "atleta@x.com")
    uid_c, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    dar(atleta, "coach@x.com")
    r = coach.get(f"/a/{uid_a}")
    assert r.status_code == 308 and r.headers["location"] == f"/a/{uid_a}/"
    r = coach.get(f"/a/{uid_a}/plan/acciones")
    coach.post(f"/a/{uid_a}/plan/viaje", data={"csrf": csrf_de(r.text), "desde": "2027-03-01", "hasta": "2027-03-05"})
    assert not coach.get(f"/a/{uid_a}/data.json").json().get("avisos")   # oculto al coach
    coach.post(f"/a/{uid_a}/historial/visto", data={"csrf": csrf_de(coach.get(f"/a/{uid_a}/historial").text)})
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).filter(Cambio.atleta_id == uid_a, Cambio.visto.is_(False)).count() == 1
    assert atleta.get("/data.json").json().get("avisos")   # sigue pendiente para el atleta
