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
