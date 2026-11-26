"""G2: grupos (crear, unirse, salir, quitar, pausar) y foto para quienes comparten grupo."""
import re

from test_web_cuentas import csrf_de, entrar, crear_usuario
from test_web_perfil import con_exif_gps
from web import perfil
from web.modelos import FotoPerfil, Grupo, InvitacionGrupo, MiembroGrupo, Usuario


def sesion(ctx, correo):
    crear_usuario(ctx, correo)
    return entrar(ctx, ctx.cliente(), correo)


def post(cl, url, **campos):
    return cl.post(url, data={"csrf": csrf_de(cl.get("/grupos/nuevo").text), **campos})


def crear(cl, nombre="Los Fieras"):
    r = post(cl, "/grupos/nuevo", nombre=nombre)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def liga(cl, gid):
    t = post(cl, f"/grupos/{gid}/invitar").text
    return re.search(r"/grupos/unirse/([\w-]+)", t).group(1)


def test_crear_y_unirse(web_ctx):
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    assert "Los Fieras" in a.get(f"/grupos/{gid}").text
    tk = liga(a, gid)
    assert b.get(f"/grupos/{gid}").status_code == 404           # aún no es miembro
    assert "Los Fieras" in b.get(f"/grupos/unirse/{tk}").text    # GET no une
    assert b.get(f"/grupos/{gid}").status_code == 404
    assert post(b, f"/grupos/unirse/{tk}").headers["location"] == f"/grupos/{gid}"
    assert b.get(f"/grupos/{gid}").status_code == 200
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).filter_by(grupo_id=gid).count() == 2
        assert tk not in {i.token_hash for i in db.query(InvitacionGrupo)}   # solo hash


def test_unirse_requiere_sesion_y_liga_valida(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    tk = liga(a, gid)
    anon = web_ctx.cliente()
    assert anon.get(f"/grupos/unirse/{tk}").status_code == 401
    assert anon.get("/grupos").headers["location"] == "/entrar"
    b = sesion(web_ctx, "b@x.com")
    assert b.get("/grupos/unirse/malo").status_code == 404
    assert post(b, "/grupos/unirse/malo").status_code == 404


def test_solo_cuerpo_no_puede_unirse(web_ctx):
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    with web_ctx.sesiones() as db:
        db.query(Usuario).filter_by(correo="b@x.com").one().uso = "cuerpo"
        db.commit()
    gid = crear(a)
    tk = liga(a, gid)
    assert post(b, f"/grupos/unirse/{tk}").status_code == 403
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).filter_by(grupo_id=gid).count() == 1


def test_no_miembro_recibe_404_en_todo(web_ctx):
    a, c = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "c@x.com")
    gid = crear(a)
    assert c.get(f"/grupos/{gid}").status_code == 404
    for ruta in ("invitar", "pausar", "salir"):
        assert post(c, f"/grupos/{gid}/{ruta}").status_code == 404
    assert post(c, f"/grupos/{gid}/quitar/1").status_code == 404
    assert "Los Fieras" not in c.get("/grupos").text


def test_post_sin_csrf_es_403(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    assert a.post("/grupos/nuevo", data={"nombre": "X"}).status_code == 403


def test_quitar_y_salir(web_ctx):
    a, b, c = (sesion(web_ctx, f"{x}@x.com") for x in "abc")
    gid = crear(a)
    tk = liga(a, gid)
    post(b, f"/grupos/unirse/{tk}"), post(c, f"/grupos/unirse/{tk}")
    with web_ctx.sesiones() as db:
        ub = db.query(Usuario).filter_by(correo="b@x.com").one().id
    assert post(b, f"/grupos/{gid}/quitar/{ub}").status_code == 403   # no es admin
    assert post(a, f"/grupos/{gid}/quitar/{ub}").status_code == 303
    assert b.get(f"/grupos/{gid}").status_code == 404
    # la admin sale: c (la más antigua que queda) pasa a admin
    assert post(a, f"/grupos/{gid}/salir").headers["location"] == "/grupos"
    with web_ctx.sesiones() as db:
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid).one()
        assert m.rol == "admin"
    post(c, f"/grupos/{gid}/salir")
    with web_ctx.sesiones() as db:
        assert db.get(Grupo, gid) is None and db.query(InvitacionGrupo).count() == 0


def test_pausar(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    post(a, f"/grupos/{gid}/pausar", pausado="1")
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().pausado is True
    assert "grupo" in a.get(f"/grupos/{gid}").text.lower()
    post(a, f"/grupos/{gid}/pausar", pausado="0")
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().pausado is False


def test_foto_la_ven_quienes_comparten_grupo(web_ctx):
    a, b, c = (sesion(web_ctx, f"{x}@x.com") for x in "abc")
    with web_ctx.sesiones() as db:
        ua = db.query(Usuario).filter_by(correo="a@x.com").one().id
        perfil.guardar_foto(db, ua, perfil.procesar_foto(con_exif_gps()))
        db.commit()
    assert b.get(f"/perfil/foto/{ua}").status_code == 404
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    assert b.get(f"/perfil/foto/{ua}").status_code == 200
    assert c.get(f"/perfil/foto/{ua}").status_code == 404
    assert f"/perfil/foto/{ua}" in b.get(f"/grupos/{gid}").text


def test_borrar_cuenta_limpia_grupos(web_ctx):
    from web import cuenta
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        cuenta.borrar_cuenta(db, db.query(Usuario).filter_by(correo="a@x.com").one())
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().rol == "admin"
        assert db.get(Grupo, gid).creado_por is None
    assert b.get(f"/grupos/{gid}").status_code == 200


def test_tarjetas_pausa_y_sin_plan_solo_campos_permitidos(web_ctx):
    from web import grupos_resumen
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    pag = a.get(f"/grupos/{gid}").text
    assert pag.count("Sin plan todavía") == 2
    post(b, f"/grupos/{gid}/pausar", pausado="1")
    pag = a.get(f"/grupos/{gid}").text
    assert "En pausa" in pag and pag.count("Sin plan todavía") == 1
    with web_ctx.sesiones() as db:
        ms = [(m, db.get(Usuario, m.usuario_id)) for m in db.query(MiembroGrupo).filter_by(grupo_id=gid)]
        for c in grupos_resumen.tarjetas(db, ms).values():
            assert set(c) == grupos_resumen.CAMPOS
            if c["estado"] != "ok":
                assert c["meta"] is None and c["adherencia"] is None and c["dias"] == [] and c["ultima"] is None


def test_tarjeta_con_plan_solo_campos_permitidos(web_ctx, monkeypatch):
    from web import grupos_resumen
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    data = {"generado": "2026-11-26T08:00", "semana_hoy_idx": 0, "ultima_corrida": {"fecha": "2026-11-24", "fc_prom": 150},
            "plan": {"eventos": [{"tipo": "carrera", "desde": "2027-01-10", "nombre": "10K"}]},
            "semanas_hoy": [{"estado": "actual", "n": 5, "plan": {"total": 3, "hechas": 2},
                             "dias": [{"fecha": f"2026-11-{23 + i}", "corrida": {"minutos": 30} if i in (1, 3) else None} for i in range(7)]}]}
    monkeypatch.setattr(grupos_resumen.calculo, "calcular", lambda db, u: data)
    with web_ctx.sesiones() as db:
        from web.modelos import Ajustes, Plan
        u = db.query(Usuario).filter_by(correo="a@x.com").one()
        db.add(Ajustes(usuario_id=u.id, config={})); db.add(Plan(usuario_id=u.id, plan={"weeks": []})); db.commit()
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid).one()
        c = grupos_resumen.tarjeta_de(db, u, m)
    assert set(c) == grupos_resumen.CAMPOS and c["estado"] == "ok"
    assert c["meta"] == "10K" and c["etapa_n"] == 5 and c["ultima"] == "2026-11-24"
    assert c["dias"][1] == "hecha" and c["dias"][2] == "libre" and c["dias"][4] == "futuro"
    pag = a.get(f"/grupos/{gid}").text
    assert "10K" in pag and "Semana 5" in pag and "Adherencia 67%" in pag and "2026-11-24" in pag
    assert "150" not in pag   # la FC no sale


def test_reacciones(web_ctx):
    from web import cuenta
    from web.modelos import Reaccion
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        ua = db.query(Usuario).filter_by(correo="a@x.com").one().id
        ub = db.query(Usuario).filter_by(correo="b@x.com").one().id
    assert post(a, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥").status_code == 400   # a sí misma
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="x").status_code == 400
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥").status_code == 303
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 1
    assert "🔥 1" in b.get(f"/grupos/{gid}").text
    assert "te reaccionaron" in a.get(f"/grupos/{gid}").text
    post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥")                              # toggle
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 0
    post(a, f"/grupos/{gid}/pausar", pausado="1")                                     # pausada: no recibe
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏").status_code == 400
    post(a, f"/grupos/{gid}/pausar", pausado="0")
    post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏")
    post(a, f"/grupos/{gid}/reaccionar/{ub}", emoji="💪")
    c = sesion(web_ctx, "c@x.com")
    assert post(c, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏").status_code == 404
    with web_ctx.sesiones() as db:
        cuenta.borrar_cuenta(db, db.query(Usuario).filter_by(correo="a@x.com").one())
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 0
