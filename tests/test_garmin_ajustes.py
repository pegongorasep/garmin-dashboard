"""C10: sección Garmin en /ajustes (tres estados), desconectar y reconectar."""
import copy

from test_conexion import empezar, gh, sesion, volver   # noqa: F401
from test_web_ajustes import CONFIG
from test_web_cuentas import csrf_de
from test_web_tubo import ctx   # noqa: F401
from web.modelos import Ajustes, Cambio, DatoGarmin, Subida, Usuario


def con_ajustes(ctx, uid):
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.repo, u.repo_id = "ana/ahilallevas-datos", 900
        db.add(Ajustes(usuario_id=uid, config=copy.deepcopy(CONFIG)))
        db.add(DatoGarmin(usuario_id=uid, tipo="dia", clave="2026-11-24", contenido={"calendarDate": "2026-11-24"}))
        db.commit()


def desconectar(cl, **extra):
    t = csrf_de(cl.get("/ajustes").text)
    return cl.post("/ajustes/garmin/desconectar", data={"csrf": t, **extra})


def test_estado_sin_conectar(ctx, gh):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.repo = u.repo_id = None
        db.commit()
    h = cl.get("/ajustes").text
    assert "Conectar Garmin" in h and 'href="/bienvenida"' in h and "Desconectar Garmin" not in h


def test_estado_con_app_y_sin_app(ctx, gh):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        db.add(Subida(usuario_id=uid, ok=True))
        db.commit()
    h = cl.get("/ajustes").text          # conectado con el código viejo: sin instalación
    assert "Autoriza una vez" in h and "/conectar/github?para=conectado" in h and "Desconectar Garmin" not in h
    assert "última descarga hace un momento" in h
    with ctx.sesiones() as db:
        db.get(Usuario, uid).gh_instalacion = 55
        db.commit()
    h = cl.get("/ajustes").text
    assert "Desconectar Garmin" in h and "Volver a traer los últimos 30 días" in h and "Sí, desconectar" in h
    assert "Autoriza una vez" not in h


def test_sin_variables_de_la_app_no_hay_botones(ctx):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    h = cl.get("/ajustes").text
    assert "Autoriza una vez" not in h and "Desconectar Garmin" not in h and "Conectado" in h


def test_desconectar_deja_datos_y_registro(ctx, gh):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.gh_instalacion, u.historial_pendiente = 55, True
        db.commit()
    r = cl.post("/ajustes/garmin/desconectar", data={"csrf": "mal"})
    assert r.status_code == 403
    r = desconectar(cl)
    assert r.status_code == 303 and r.headers["location"] == "/ajustes?garmin=desconectado"
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo, u.repo_id, u.gh_instalacion, u.historial_pendiente) == (None, None, None, False)
        assert db.query(DatoGarmin).filter_by(usuario_id=uid).count() == 1
        assert db.get(Ajustes, uid) is not None
        c = db.query(Cambio).filter_by(atleta_id=uid, descripcion="Garmin desconectado").one()
        assert c.via == "sistema" and c.antes["repo_id"] is not None
    h = cl.get("/ajustes?garmin=desconectado").text
    assert "github.com/settings/installations" in h and "Conectar Garmin" in h


def test_reconectar_con_otra_copia(ctx, gh):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.gh_instalacion = 55
        db.commit()
    desconectar(cl)
    gh.repos = [{"id": 901, "full_name": "ana/otra-copia", "private": True, "default_branch": "main"}]
    r = volver(cl, empezar(cl))
    assert "error" not in r.headers["location"]
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo, u.repo_id, u.gh_instalacion) == ("ana/otra-copia", 901, 55)


def test_el_coach_no_ve_ni_desconecta(ctx, gh):
    from web.modelos import Coach
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.gh_instalacion = 55
        coach = Usuario(correo="coach@x.com")
        db.add(coach)
        db.commit()
        db.add(Coach(atleta_id=uid, coach_id=coach.id))
        db.commit()
    from test_web_cuentas import entrar
    cc = entrar(ctx, ctx.cliente(), "coach@x.com")
    assert "Desconectar Garmin" not in cc.get(f"/a/{uid}/ajustes").text
    t = csrf_de(cc.get("/ajustes").text) if cc.get("/ajustes").status_code == 200 else "x"
    cc.post("/ajustes/garmin/desconectar", data={"csrf": t})   # actúa sobre la cuenta del coach, nunca sobre la del atleta
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).gh_instalacion == 55
