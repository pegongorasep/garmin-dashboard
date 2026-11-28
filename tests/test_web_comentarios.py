"""Social S4: comentarios por actividad (visibilidad, CSRF, borrado, límites, XSS) y punto de «nuevo»."""
import sqlite3
from datetime import timedelta

from alembic import command
from alembic.config import Config

from web import feed
from web.modelos import Comentario, DatoGarmin, Usuario, ahora
from ayudas import (
    act,
    crear,
    csrf_de,
    falso_calcular,
    ids_feed,
    liga,
    post_grupos as post,
    ROOT,
    sesion_grupos as sesion,
    tres,
    uid_de,
)


def comentar(cl, uid, clave, texto="Buenísimo", csrf=True):
    datos = {"dueno": uid, "clave": clave, "texto": texto}
    if csrf:
        datos["csrf"] = csrf_de(cl.get("/grupos/nuevo").text)
    return cl.post("/api/juntos/comentar", data=datos)


def borrar(cl, cid, csrf=True):
    datos = {"id": cid}
    if csrf:
        datos["csrf"] = csrf_de(cl.get("/grupos/nuevo").text)
    return cl.post("/api/juntos/comentario/borrar", data=datos)


def preparar(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua, ub = uid_de(web_ctx, "a@x.com"), uid_de(web_ctx, "b@x.com")
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, act())], ub: [(2, act())]}))
    clave = next(x["clave"] for x in ids_feed(a)["items"] if x["usuario_id"] == ua)
    return a, b, c, gid, ua, ub, clave


def test_comentar_lista_y_conteo(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    r = comentar(b, ua, clave, "  Qué rico  ")
    assert r.status_code == 200 and r.json()["n"] == 1
    c0 = r.json()["comentarios"][0]
    assert c0["texto"] == "Qué rico" and c0["mia"] is True and c0["puede_borrar"] is True and c0["nombre"] == "Ana Prueba"
    lista = a.get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave}).json()
    assert lista["comentarios"][0]["mia"] is False and lista["comentarios"][0]["puede_borrar"] is True   # la dueña puede borrar
    assert [x["comentarios"] for x in ids_feed(a)["items"] if x["usuario_id"] == ua] == [1]
    assert [x["comentarios"] for x in ids_feed(a)["items"] if x["usuario_id"] == ub] == [0]


def test_comentarios_visibilidad_404(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    assert c.get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave}).status_code == 404
    assert comentar(c, ua, clave).status_code == 404
    assert comentar(b, ua, "x" * 24).status_code == 404
    assert comentar(b, 9999, clave).status_code == 404
    assert b.get("/api/juntos/comentarios", params={"dueno": ua, "clave": "x" * 24}).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.query(Comentario).count() == 0
        db.get(Usuario, ua).compartir_actividades = False
        db.commit()
    assert comentar(b, ua, clave).status_code == 404                  # interruptor apagado: ya no la ve
    assert b.get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave}).status_code == 404
    assert web_ctx.cliente().get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave}).status_code in (401, 403)


def test_comentar_exige_csrf(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    assert comentar(b, ua, clave, csrf=False).status_code == 403
    assert b.post("/api/juntos/comentar", data={"csrf": "malo", "dueno": ua, "clave": clave, "texto": "x"}).status_code == 403
    assert b.post("/api/juntos/visto", data={}).status_code == 403
    assert comentar(b, ua, clave).status_code == 200
    cid = a.get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave}).json()["comentarios"][0]["id"]
    assert borrar(a, cid, csrf=False).status_code == 403
    with web_ctx.sesiones() as db:
        assert db.query(Comentario).count() == 1


def test_largo_y_vacio(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    assert comentar(b, ua, clave, "   ").status_code == 400
    assert comentar(b, ua, clave, "").status_code == 400
    assert comentar(b, ua, clave, "x" * 281).status_code == 400
    assert comentar(b, ua, clave, "  " + "x" * 280 + "  ").status_code == 200     # recortado queda en 280
    assert comentar(b, ua, clave, "ñ" * 280).status_code == 200                    # caracteres, no bytes
    with web_ctx.sesiones() as db:
        assert db.query(Comentario).count() == 2


def test_limite_de_ritmo(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    for i in range(feed.MAX_COMENTARIOS_VENTANA):
        assert comentar(b, ua, clave, f"c{i}").status_code == 200
    assert comentar(b, ua, clave, "uno más").status_code == 429
    assert comentar(a, ua, clave, "ella sí puede").status_code == 200              # el límite es por persona
    with web_ctx.sesiones() as db:                                                  # pasada la ventana, vuelve a poder
        for x in db.query(Comentario).filter_by(autor_id=uid_de(web_ctx, "b@x.com")):
            x.creado = ahora() - timedelta(minutes=11)
        db.commit()
    assert comentar(b, ua, clave, "ya").status_code == 200


def test_xss_se_guarda_como_texto_y_sale_igual(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    malo = '<script>alert(1)</script><img src=x onerror=alert(2)>'
    assert comentar(b, ua, clave, malo).status_code == 200
    r = a.get("/api/juntos/comentarios", params={"dueno": ua, "clave": clave})
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["comentarios"][0]["texto"] == malo        # texto plano: el JS lo pinta con textContent, nunca innerHTML
    js = (ROOT / "site" / "vista_grupo.js").read_text()
    tramo = js[js.index("function feedComentarios"):js.index("function feedFila")]
    assert "innerHTML" not in tramo and "insertAdjacentHTML" not in tramo


def test_borrar_matriz_de_permisos(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)       # grupo: a (admin), b
    d, x = sesion(web_ctx, "d@x.com"), sesion(web_ctx, "x@x.com")
    post(d, f"/grupos/unirse/{liga(a, gid)}")
    gx = crear(x, "Otro")                                               # x administra otro grupo
    post(b, f"/grupos/unirse/{liga(x, gx)}")                            # que contiene a b pero no a d
    ud = uid_de(web_ctx, "d@x.com")
    claveb = next(i["clave"] for i in ids_feed(b)["items"] if i["usuario_id"] == ub)

    def nuevo(autor, dueno_id, k):
        cid = comentar(autor, dueno_id, k).json()["comentarios"][-1]["id"]
        return cid
    # actividad de b, comenta d: a es admin de un grupo con b y d → puede; x (admin solo con b) → 403; c → 404
    cid = nuevo(d, ub, claveb)
    assert borrar(x, cid).status_code == 403
    assert borrar(c, cid).status_code == 404
    assert borrar(a, cid).status_code == 200
    cid = nuevo(d, ub, claveb)
    assert borrar(d, cid).status_code == 200                            # el autor
    cid = nuevo(d, ub, claveb)
    assert borrar(b, cid).status_code == 200                            # la dueña de la actividad
    # actividad de a, comenta d: b es miembro raso, ni dueño ni autor → 403
    cid = nuevo(d, ua, clave)
    assert borrar(b, cid).status_code == 403
    assert borrar(a, cid).status_code == 200
    assert borrar(a, 99999).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.query(Comentario).count() == 0
    assert ud


def test_nombre_del_autor_solo_si_se_ve(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    x = sesion(web_ctx, "x@x.com")
    gx = crear(x, "Otro")
    post(b, f"/grupos/unirse/{liga(x, gx)}")                            # x y a no comparten grupo, pero x ve a b
    claveb = next(i["clave"] for i in ids_feed(b)["items"] if i["usuario_id"] == ub)
    comentar(a, ub, claveb, "de a")
    c0 = x.get("/api/juntos/comentarios", params={"dueno": ub, "clave": claveb}).json()["comentarios"][0]
    assert c0["nombre"] == "" and c0["usuario_id"] is None
    assert b.get("/api/juntos/comentarios", params={"dueno": ub, "clave": claveb}).json()["comentarios"][0]["nombre"] == "Ana Prueba"


def test_punto_de_nuevo(web_ctx, monkeypatch):
    a, b, c, gid, ua, ub, clave = preparar(web_ctx, monkeypatch)
    nuevo = lambda cl: cl.get("/api/juntos/nuevo").json()["nuevo"]  # noqa: E731
    with web_ctx.sesiones() as db:
        for u in db.query(Usuario):
            u.juntos_visto = ahora() - timedelta(hours=2)
        db.commit()
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(0, act())], ub: [(0, act())]}))
    clave = next(i["clave"] for i in ids_feed(a)["items"] if i["usuario_id"] == ua)
    assert nuevo(a) is False and nuevo(b) is False                     # sin subidas ni comentarios
    # b sube actividad (su última subida es posterior a la visita de a)
    with web_ctx.sesiones() as db:
        db.add(DatoGarmin(usuario_id=ub, tipo="actividad", clave="1", contenido={}, actualizado=ahora() - timedelta(hours=1)))
        db.commit()
    assert nuevo(a) is True                                            # actividad de otro, nueva para a
    assert nuevo(c) is False                                           # c no ve a nadie
    assert nuevo(b) is False                                           # lo propio no cuenta
    assert a.post("/api/juntos/visto", data={"csrf": csrf_de(a.get("/grupos/nuevo").text)}).status_code == 200
    assert nuevo(a) is False                                           # abrir Juntos lo apaga
    # un comentario de otro en MIS actividades enciende el punto; uno mío o en actividad ajena, no
    comentar(b, ua, clave, "hola")
    assert nuevo(a) is True and nuevo(b) is False
    comentar(a, ub, next(i["clave"] for i in ids_feed(a)["items"] if i["usuario_id"] == ub), "mío")
    assert nuevo(b) is True
    # actividad vieja (anterior a la visita) no enciende aunque la subida sea nueva
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(30, act())], ub: [(30, act())]}))
    assert b.post("/api/juntos/visto", data={"csrf": csrf_de(b.get("/grupos/nuevo").text)}).status_code == 200
    with web_ctx.sesiones() as db:
        db.query(DatoGarmin).update({"actualizado": ahora() + timedelta(seconds=5)})
        db.commit()
    assert nuevo(b) is False   # sus actividades de hace 30 días no son nuevas aunque haya subida reciente


def test_migracion_comentarios_sube_y_baja(tmp_path):
    db = tmp_path / "m.db"
    cfg = Config(str(ROOT / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    con = lambda q: [r[0] for r in sqlite3.connect(db).execute(q)]  # noqa: E731
    command.upgrade(cfg, "0015")
    assert "comentarios_actividad" not in con("select name from sqlite_master where type='table'")
    command.upgrade(cfg, "head")
    assert "comentarios_actividad" in con("select name from sqlite_master where type='table'")
    assert "juntos_visto" in con("select name from pragma_table_info('usuarios')")
    command.downgrade(cfg, "0015")
    assert "comentarios_actividad" not in con("select name from sqlite_master where type='table'")
    assert "juntos_visto" not in con("select name from pragma_table_info('usuarios')")
    command.upgrade(cfg, "head")
