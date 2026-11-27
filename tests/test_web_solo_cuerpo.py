from test_web_cuentas import csrf_de, entrar, post, crear_usuario
from sqlalchemy import text
from web.modelos import Consentimiento, InBody, Usuario
from web.privacidad import VERSION_AVISO


def nuevo(ctx, correo="c@x.com", uso=None, consentido=True):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        if consentido:
            db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.get(Usuario, uid).uso = uso
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def token(cl, url="/bienvenida"):
    return csrf_de(cl.get(url).text)


def test_cuenta_vieja_con_repo_no_ve_la_pregunta(web_ctx):
    uid, cl = nuevo(web_ctx)
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid).github_owner = "pepe"
        db.commit()
    assert "¿Qué quieres usar?" not in cl.get("/bienvenida").text


def test_ajustes_uso_ya_no_existe(web_ctx):
    uid, cl = nuevo(web_ctx)
    assert cl.post("/ajustes/uso", data={"csrf": token(cl)}).status_code in (404, 405)


def test_persona_solo_cuerpo_migrada_conserva_mediciones_y_ve_todo(web_ctx):
    """La migración 0019 deja uso NULL y sin_plan; sus mediciones se quedan y el data.json trae todo (no el mínimo de antes)."""
    from dashboard import validar
    uid, cl = nuevo(web_ctx, uso="cuerpo")
    with web_ctx.sesiones() as db:
        db.add(InBody(usuario_id=uid, fecha="2026-11-20", valores={"fecha": "2026-11-20", "peso_kg": 80.0, "mme_kg": 35.0, "pgc": 20.0, "masa_grasa_kg": 16.0}))
        db.commit()
        db.execute(text("UPDATE usuarios SET uso = NULL, sin_plan = true WHERE uso = 'cuerpo'"))   # lo que hace 0019
        db.commit()
        assert db.query(InBody).count() == 1 and db.get(Usuario, uid).uso is None and db.get(Usuario, uid).sin_plan
    d = cl.get("/data.json").json()
    assert validar.problemas(d) == []
    assert not d["ui"].get("solo_cuerpo") and d["ui"]["sin_plan"] is True
    assert len(d["composicion"]["mediciones"]) == 1
    assert {m["url"] for m in d["ui"]["menu"]} >= {"/ajustes", "/historial", "/cuerpo", "/coach", "/privacidad", "/salir"}
    assert cl.get("/ajustes").status_code == 200 and cl.get("/cuerpo").status_code == 200


def test_sin_copia_ni_ajustes_tiene_config_de_fabrica_sin_plan(web_ctx):
    from web.calculo import config_de
    uid, cl = nuevo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert not u.repo_id and not u.sin_plan
        cfg = config_de(db, u)
        assert cfg["sin_plan"] is True
    d = cl.get("/data.json").json()
    assert d["ui"]["sin_plan"] is True


def test_cuerpo_nuevo_segun_inbody_activo(web_ctx):
    from web.calculo import config_de
    uid, cl = nuevo(web_ctx)
    with web_ctx.sesiones() as db:
        assert config_de(db, db.get(Usuario, uid))["cuerpo_nuevo"] == "/cuerpo/nuevo"
    assert cl.get("/data.json").json()["ui"]["cuerpo_nuevo"] == "/cuerpo/nuevo"


def test_cuerpo_nuevo_sin_inbody_no_hay_boton(web_ctx):
    import copy
    from test_web_ajustes import CONFIG
    from web.calculo import config_de
    from web.modelos import Ajustes
    uid, cl = nuevo(web_ctx, uso="completo")
    with web_ctx.sesiones() as db:
        db.add(Ajustes(usuario_id=uid, config={**copy.deepcopy(CONFIG), "inbody": False}))
        db.commit()
        assert config_de(db, db.get(Usuario, uid)).get("cuerpo_nuevo") is None


def test_migracion_0019_pasa_solo_cuerpo_a_sin_plan(tmp_path):
    import sqlite3
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    db = tmp_path / "m.db"
    cfg = Config(str(Path(__file__).parent.parent / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    command.upgrade(cfg, "0018")
    con = sqlite3.connect(db)
    cols = [r[1] for r in con.execute("pragma table_info(usuarios)") if r[3] and r[4] is None and not r[5]]   # NOT NULL sin valor por defecto
    assert "correo" in cols
    for i, uso in enumerate(("cuerpo", "completo", None)):
        valores = {c: "2026-01-01" if c == "creado" else f"u{i}@x.com" if c == "correo" else 0 for c in cols}
        con.execute(f"INSERT INTO usuarios ({','.join(valores)}, uso, sin_plan) VALUES ({','.join('?' * len(valores))}, ?, 0)", (*valores.values(), uso))
    con.commit()
    con.close()
    command.upgrade(cfg, "head")
    filas = sqlite3.connect(db).execute("select correo, uso, sin_plan from usuarios order by id").fetchall()
    assert filas == [("u0@x.com", None, 1), ("u1@x.com", "completo", 0), ("u2@x.com", None, 0)]
    command.downgrade(cfg, "0018")
    command.upgrade(cfg, "head")
