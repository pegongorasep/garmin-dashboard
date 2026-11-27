"""Conexión C8: POST/GET /api/sync."""
from datetime import timedelta

import pytest

from test_conexion import sesion
from test_conexion import gh as _gh   # noqa: F401
from test_guia import conectada, gh, token   # noqa: F401
from test_web_tubo import ctx   # noqa: F401
from web import sincronizar, sync_web
from web.modelos import Sincronizacion, ahora


def listo(ctx, gh):
    cl, uid = conectada(ctx, gh)
    gh.secs = ["PERSONAL_API_KEY"]
    return cl, uid, token(cl)


def test_csrf_sin_app_y_sin_sesion(ctx, gh):
    assert ctx.cliente().get("/api/sync").status_code == 401
    cl, _ = sesion(ctx)
    assert cl.post("/api/sync").status_code == 403
    r = cl.post("/api/sync", data={"csrf": token(cl)})
    assert r.status_code == 409 and r.json() == {"error": "sin_app", "url": "/conectar/github?para=conectado"}


def test_dispara_una_vez_y_no_duplica(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    j = cl.post("/api/sync", data={"csrf": tk}).json()
    assert j["nueva"] is True and j["sinc"]["tipo"] == "normal" and j["sinc"]["texto"] == "Despertando tu sincronización…"
    assert cl.post("/api/sync", data={"csrf": tk}).json()["nueva"] is False
    assert len(gh.disparos) == 1


def test_tipos(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    assert cl.post("/api/sync", data={"csrf": tk, "tipo": "historial"}).json()["sinc"]["tipo"] == "normal"
    with ctx.sesiones() as db:
        sincronizar.terminar(db, db.query(Sincronizacion).one(), ok=True, nuevas=0)
    assert cl.post("/api/sync", data={"csrf": tk, "tipo": "treinta"}).json()["sinc"]["tipo"] == "treinta"


def test_secreto_falta_y_nombre_mal(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    gh.secs = []
    j = cl.post("/api/sync", data={"csrf": tk}).json()["sinc"]
    assert j["estado"] == "error" and j["error"] == "sin_key" and j["accion"]["url"] == "/bienvenida?paso=4"
    gh.secs = ["personal api key"]
    j = cl.post("/api/sync", data={"csrf": tk}).json()["sinc"]
    assert j["error"] == "nombre_mal"
    assert gh.disparos == []


def test_falla_github_y_limite(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    gh.falla_disparo = True
    j = cl.post("/api/sync", data={"csrf": tk}).json()["sinc"]
    assert j["error"] == "otra" and j["accion"]["post"]["url"] == "/api/sync" and j["texto"] == "No pudimos bajar tus datos"
    for _ in range(5):
        assert cl.post("/api/sync", data={"csrf": tk}).status_code == 200
    r = cl.post("/api/sync", data={"csrf": tk})
    assert r.status_code == 429 and r.json()["error"] == "limite"


@pytest.mark.parametrize("paso,hechos,total,pct,txt", [
    (None, None, None, 5, "Despertando"), ("prepara", None, None, 15, "Calentando"), ("busca", None, None, 25, "Buscando"),
    ("encuentra", None, 12, 30, "Encontramos 12 actividades"), ("detalles", 5, 12, 49, "Bajando tus kilómetros · 5 de 12"),
    ("detalles", 12, 12, 75, "12 de 12"), ("salud", None, None, 80, "sueño"), ("sube", None, None, 90, "Haciendo cuentas")])
def test_texto_y_porcentaje_por_paso(ctx, gh, paso, hechos, total, pct, txt):
    cl, uid, tk = listo(ctx, gh)
    cl.post("/api/sync", data={"csrf": tk})
    with ctx.sesiones() as db:
        s = db.query(Sincronizacion).one()
        if paso:
            sincronizar.avanzar(db, s, paso, hechos, total)
    s = cl.get("/api/sync").json()["sinc"]
    assert s["porcentaje"] == pct and txt in s["texto"]


def test_listo_y_ventana_de_60s(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    cl.post("/api/sync", data={"csrf": tk})
    with ctx.sesiones() as db:
        sincronizar.terminar(db, db.query(Sincronizacion).one(), ok=True, nuevas=3)
    s = cl.get("/api/sync").json()["sinc"]
    assert s["texto"] == "✓ ¡Listo! 3 actividades nuevas" and s["porcentaje"] == 100 and s["terminada_hace_s"] < 5
    with ctx.sesiones() as db:
        x = db.query(Sincronizacion).one()
        x.terminada = ahora() - timedelta(seconds=90)
        x.nuevas = 0
        db.commit()
    assert cl.get("/api/sync").json()["sinc"] is None


def test_historial_dice_365_y_reintentar(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    with ctx.sesiones() as db:
        from web.modelos import Usuario
        db.get(Usuario, uid).historial_pendiente = True
        db.commit()
    s = cl.post("/api/sync", data={"csrf": tk, "tipo": "historial"}).json()["sinc"]
    assert s["tipo"] == "historial"
    with ctx.sesiones() as db:
        x = db.query(Sincronizacion).one()
        sincronizar.avanzar(db, x, "busca")
        assert "365" in sync_web.texto(x, lambda k, **v: __import__("i18n").t(k, "es", **v))
        sincronizar.terminar(db, x, ok=False, error="otra")
    s = cl.get("/api/sync").json()["sinc"]
    assert s["texto"] == "Falta tu historial" and s["accion"]["post"]["tipo"] == "historial"


def test_programadas_invisibles(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    with ctx.sesiones() as db:
        db.add(Sincronizacion(usuario_id=uid, tipo="programada", estado="corriendo", paso="busca"))
        db.commit()
    assert cl.get("/api/sync").json()["sinc"] is None
    j = cl.post("/api/sync", data={"csrf": tk}).json()
    assert j["nueva"] is True and j["sinc"]["tipo"] == "normal"


def test_corrida_fallida_detectada_y_cache(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    llamadas = []
    gh.corridas = lambda inst, repo, workflow="deploy.yml", desde=None: (
        llamadas.append(1) or [{"id": 9, "status": "completed", "conclusion": "failure", "event": "workflow_dispatch",
                                "created_at": (ahora() + timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")}])
    cl.post("/api/sync", data={"csrf": tk})
    assert cl.get("/api/sync").json()["sinc"]["estado"] == "esperando"   # recién avisada: no se consulta
    assert llamadas == []
    with ctx.sesiones() as db:
        s = db.query(Sincronizacion).one()
        s.actualizada = ahora() - timedelta(seconds=30)
        db.commit()
    j = cl.get("/api/sync").json()["sinc"]
    assert j["estado"] == "error" and j["error"] == "otra" and len(llamadas) == 1
    cl.get("/api/sync")
    assert len(llamadas) == 1


def test_usuario_ajeno_no_ve_nada(ctx, gh):
    cl, uid, tk = listo(ctx, gh)
    cl.post("/api/sync", data={"csrf": tk})
    from test_web_cuentas import crear_usuario, entrar
    crear_usuario(ctx, "otro@x.com")
    otro = ctx.cliente()
    entrar(ctx, otro, "otro@x.com")
    assert otro.get("/api/sync").json()["sinc"] is None
