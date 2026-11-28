"""Social S3: feed de actividades de Juntos (quién aparece, privacidad, paginación) y reacciones por actividad."""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from alembic import command
from alembic.config import Config

from web import feed
from web.modelos import Ajustes, Coach, DatoGarmin, ReaccionActividad, Usuario
from ayudas import (
    act,
    CONFIG,
    csrf_de,
    falso_calcular,
    ids_feed,
    liga,
    post_grupos as post,
    sesion_grupos as sesion,
    tres,
    uid_de,
)

ROOT = Path(__file__).resolve().parent.parent


def test_feed_matriz_de_visibilidad(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    d = sesion(web_ctx, "d@x.com")
    post(d, f"/grupos/unirse/{liga(a, gid)}")
    e = sesion(web_ctx, "e@x.com")                       # coach de a, sin grupo
    ua, ub, uc, ud, ue = (uid_de(web_ctx, f"{x}@x.com") for x in "abcde")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=ua, coach_id=ue))
        db.get(Usuario, ud).compartir_actividades = False   # d apaga el interruptor
        db.commit()
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({u: [(1, act())] for u in (ua, ub, uc, ud, ue)}))
    quienes = lambda cl: sorted(x["usuario_id"] for x in ids_feed(cl)["items"])   # noqa: E731
    assert quienes(a) == sorted([ua, ub])                # sí: grupo; no: d (interruptor apagado)
    assert quienes(b) == sorted([ua, ub])
    assert quienes(c) == [uc]                            # sin grupo: solo lo suyo
    assert quienes(d) == sorted([ua, ub, ud])            # d ve a los demás y se ve a sí mismo
    assert quienes(e) == [ue]                            # coach sin grupo: no es «social»
    assert web_ctx.cliente().get("/api/juntos/feed").status_code == 401


def test_feed_pausa_en_todos_los_grupos_oculta(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua, ub = uid_de(web_ctx, "a@x.com"), uid_de(web_ctx, "b@x.com")
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, act())], ub: [(1, act())]}))
    post(b, f"/grupos/{gid}/pausar", pausado="1")
    assert [x["usuario_id"] for x in ids_feed(a)["items"]] == [ua]
    assert sorted(x["usuario_id"] for x in ids_feed(b)["items"]) == sorted([ua, ub])   # pausar es lo que ella comparte, no lo que ve


def test_feed_orden_paginas_sin_duplicados_y_campos(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua, ub = uid_de(web_ctx, "a@x.com"), uid_de(web_ctx, "b@x.com")
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({
        ua: [(i, act(minutos=30 + i)) for i in range(1, 15)] + [(1, act("fuerza", 45, None))],
        ub: [(i, act(minutos=60 + i)) for i in range(1, 12)]}))
    p1 = ids_feed(a)
    assert len(p1["items"]) == 20 and p1["siguiente"]
    p2 = ids_feed(a, antes=p1["siguiente"])
    assert len(p2["items"]) == 6 and p2["siguiente"] is None
    todos = p1["items"] + p2["items"]
    claves = [x["clave"] for x in todos]
    assert len(set(claves)) == len(claves) == 26
    fechas = [x["fecha"] for x in todos]
    assert fechas == sorted(fechas, reverse=True)
    x = todos[0]
    assert {"clave", "usuario_id", "nombre", "foto", "fecha", "cat", "tipo", "emoji", "minutos", "km", "fc_prom", "esfuerzo",
            "trote", "sesion", "detalle", "reacciones", "mia"} <= set(x)
    assert any(i["cat"] == "fuerza" and i["emoji"] == "🏋️" for i in todos)   # todos los tipos
    assert ids_feed(a, antes="basura")["items"]                              # cursor inválido: desde el principio


def test_feed_sesion_del_plan_solo_si_comparte_el_plan(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua = uid_de(web_ctx, "a@x.com")
    s = {"nombre": "Fácil 1", "estado": "hecha"}
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, act(sesion=s))]}))
    assert ids_feed(b)["items"][0]["sesion"] == {"nombre": "Fácil 1", "n": 3}
    with web_ctx.sesiones() as db:
        db.get(Usuario, ua).compartir_plan = False
        db.commit()
    assert ids_feed(b)["items"][0]["sesion"] is None
    assert ids_feed(a)["items"][0]["sesion"] == {"nombre": "Fácil 1", "n": 3}   # ella sí ve lo suyo


def test_e7_actividad_manual_lleva_marca_y_conserva_reacciones_sin_nota(web_ctx, monkeypatch):
    a, b, _, _ = tres(web_ctx)
    ua = uid_de(web_ctx, "a@x.com")
    secreta = "NOTA-PRIVADA-E7"
    actividad = {**act(manual=True), "nota": secreta}
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, actividad)]}))
    item = ids_feed(b)["items"][0]
    assert item["manual"] is True and secreta not in json.dumps(item)
    assert reaccionar(b, ua, item["clave"]).status_code == 200
    js = (ROOT / "site" / "vista_grupo.js").read_text(encoding="utf-8")
    assert 'it.manual ? T("sitio.dia.a_mano")' in js


def test_feed_real_no_filtra_nombres_ni_ids_ni_gps(web_ctx):
    a, b, c, gid = tres(web_ctx)
    ua = uid_de(web_ctx, "a@x.com")
    hoy = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    with web_ctx.sesiones() as db:
        db.add(Ajustes(usuario_id=ua, config=CONFIG))
        for n, (tipo, i) in enumerate([("running", 1), ("strength_training", 2)], start=7001):
            db.add(DatoGarmin(usuario_id=ua, tipo="actividad", clave=str(n), contenido={
                "id": n, "activityId": n, "activityName": "Ruta de la Calle Secreta", "ownerDisplayName": "Ana", "userProfilePk": 55,
                "startLatitude": 20.97, "startLongitude": -89.6, "birthDate": "1990-01-01",
                "startTimeLocal": (hoy - timedelta(days=i)).isoformat(sep=" "), "duration": 2400.0, "distance": 5000.0,
                "averageHR": 140.0, "activityType": {"typeKey": tipo}}))
        db.commit()
    r = b.get("/api/juntos/feed")
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 2 and {x["cat"] for x in items} == {"run", "crossfit"}
    crudo = r.text
    for prohibido in ("Calle Secreta", "activityId", "activityName", "ownerDisplayName", "userProfilePk", "startLatitude",
                      "startLongitude", "birthDate", "1990-01-01", "7001", "7002", "20.97", "-89.6", "gps", "serie"):
        assert prohibido not in crudo, prohibido
    assert all(len(x["clave"]) == 24 and x["clave"].isalnum() for x in items)


def reaccionar(cl, uid, clave, emoji="🔥", csrf=True):
    datos = {"dueno": uid, "clave": clave, "emoji": emoji}
    if csrf:
        datos["csrf"] = csrf_de(cl.get("/grupos/nuevo").text)
    return cl.post("/api/juntos/reaccionar", data=datos)


def test_reacciones_toggle_conteo_y_404(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua, ub, uc = (uid_de(web_ctx, f"{x}@x.com") for x in "abc")
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, act())], uc: [(1, act())]}))
    clave = ids_feed(a)["items"][0]["clave"]
    r = reaccionar(b, ua, clave)
    assert r.status_code == 200 and r.json()["reacciones"] == {"🔥": {"n": 1, "quienes": ["Ana Prueba"], "mia": True}}
    it = ids_feed(a)["items"][0]
    assert it["reacciones"]["🔥"]["mia"] is False and it["reacciones"]["🔥"]["n"] == 1
    assert reaccionar(a, ua, clave, "👏").status_code == 200                      # también la dueña
    assert set(ids_feed(b)["items"][0]["reacciones"]) == {"🔥", "👏"}
    assert reaccionar(b, ua, clave).json()["reacciones"].get("🔥") is None        # toggle: la quita
    with web_ctx.sesiones() as db:
        assert db.query(ReaccionActividad).count() == 1
    # no la ve → 404, sin dejar rastro
    assert reaccionar(c, ua, clave).status_code == 404
    assert reaccionar(a, uc, ids_feed(c)["items"][0]["clave"]).status_code == 404
    assert reaccionar(b, ua, "x" * 24).status_code == 404                         # clave que no existe
    assert reaccionar(b, 9999, clave).status_code == 404
    assert reaccionar(b, ua, clave, "x").status_code == 400
    with web_ctx.sesiones() as db:
        assert db.query(ReaccionActividad).count() == 1
        db.get(Usuario, ua).compartir_actividades = False
        db.commit()
    assert reaccionar(b, ua, clave).status_code == 404                            # interruptor apagado: ya no la ve
    assert web_ctx.cliente().post("/api/juntos/reaccionar", data={"dueno": ua, "clave": clave, "emoji": "🔥"}).status_code == 403


def test_reaccion_exige_csrf(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua = uid_de(web_ctx, "a@x.com")
    monkeypatch.setattr(feed.calculo, "calcular", falso_calcular({ua: [(1, act())]}))
    clave = ids_feed(a)["items"][0]["clave"]
    assert reaccionar(b, ua, clave, csrf=False).status_code == 403
    assert b.post("/api/juntos/reaccionar", data={"csrf": "malo", "dueno": ua, "clave": clave, "emoji": "🔥"}).status_code == 403
    with web_ctx.sesiones() as db:
        assert db.query(ReaccionActividad).count() == 0


def test_clave_estable_opaca_y_distinta_por_persona():
    k = feed.clave_actividad("s", 1, "2026-11-01", "run", 40, 0)
    assert k == feed.clave_actividad("s", 1, "2026-11-01", "run", 40, 0)
    assert k != feed.clave_actividad("s", 2, "2026-11-01", "run", 40, 0) != feed.clave_actividad("s", 1, "2026-11-01", "run", 40, 1)
    assert k != feed.clave_actividad("otra", 1, "2026-11-01", "run", 40, 0)


def test_migracion_reacciones_actividad_sube_y_baja(tmp_path):
    db = tmp_path / "m.db"
    cfg = Config(str(ROOT / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    tablas = lambda: {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}  # noqa: E731
    command.upgrade(cfg, "0014")
    assert "reacciones" in tablas() and "reacciones_actividad" not in tablas()
    command.upgrade(cfg, "head")
    assert "reacciones_actividad" in tablas() and "reacciones" not in tablas()
    command.downgrade(cfg, "0014")
    assert "reacciones" in tablas() and "reacciones_actividad" not in tablas()
    command.upgrade(cfg, "head")
