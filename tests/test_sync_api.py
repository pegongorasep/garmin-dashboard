"""Conexión C8: POST/GET /api/sync."""
from datetime import timedelta

import pytest

from web import sincronizar, sync_web
from web.modelos import Sincronizacion, ahora
from ayudas import conectada, sesion, token_guia as token


@pytest.fixture
def gh(gh_con_secretos):
    return gh_con_secretos


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
        assert "365" in sync_web.texto(x, lambda k, **v: __import__("dashboard.i18n", fromlist=["t"]).t(k, "es", **v))
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
    from ayudas import crear_usuario, entrar
    crear_usuario(ctx, "otro@x.com")
    otro = ctx.cliente()
    entrar(ctx, otro, "otro@x.com")
    assert otro.get("/api/sync").json()["sinc"] is None


def _desinstalada(gh, donde):
    from web.github_app import InstalacionPerdida

    def boom(*a, **k):
        raise InstalacionPerdida(404, "Not Found")
    setattr(gh, donde, boom)


@pytest.mark.parametrize("donde", ["secretos", "disparar", "repos_de_instalacion"])
def test_desinstalada_suelta_la_instalacion(ctx, gh, donde):
    from web.modelos import Cambio, Usuario
    cl, uid, tk = listo(ctx, gh)
    _desinstalada(gh, donde)
    r = cl.post("/api/sync", data={"csrf": tk})
    assert r.status_code == 409 and r.json() == {"error": "sin_app", "url": "/conectar/github?para=conectado"}
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert u.gh_instalacion is None
        assert db.query(Cambio).filter(Cambio.atleta_id == uid, Cambio.via == "sistema",
                                       Cambio.descripcion.like("GitHub App desinstalada%")).count() == 1
        assert db.query(Sincronizacion).filter(Sincronizacion.estado.in_(("esperando", "corriendo"))).count() == 0
        assert db.query(Sincronizacion).filter(Sincronizacion.estado == "error").count() == 0   # sin error visible
        assert sync_web.sync_ui(ctx.settings, u)["puede"] is False
    assert cl.get("/api/sync").json() == {"sinc": None}
    assert cl.post("/api/sync", data={"csrf": tk}).status_code == 409


def test_desinstalada_detectada_al_consultar_la_corrida(ctx, gh):
    from web.modelos import Usuario
    cl, uid, tk = listo(ctx, gh)
    cl.post("/api/sync", data={"csrf": tk})
    _desinstalada(gh, "corridas")
    with ctx.sesiones() as db:
        s = db.query(Sincronizacion).one()
        s.actualizada = ahora() - timedelta(seconds=30)
        db.commit()
    assert cl.get("/api/sync").json() == {"sinc": None}
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).gh_instalacion is None


def test_5xx_de_github_sigue_siendo_otra(ctx, gh):
    from web.modelos import Usuario
    cl, uid, tk = listo(ctx, gh)
    gh.falla_disparo = True
    j = cl.post("/api/sync", data={"csrf": tk}).json()["sinc"]
    assert j["error"] == "otra"
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).gh_instalacion == 55


def test_cliente_github_distingue_instalacion_perdida():
    import httpx
    from web.github_app import GitHubApp, GitHubError, InstalacionPerdida

    class S:
        github_app_id, github_app_slug, github_app_private_key = "1", "x", "k"

    def app(codigo_token, codigo, msg=""):
        def h(req):
            if req.url.path.endswith("/access_tokens"):
                return httpx.Response(codigo_token, json={"token": "t", "expires_at": "2099-01-01T00:00:00Z"})
            return httpx.Response(codigo, json={"message": msg})
        g = GitHubApp(S(), transport=httpx.MockTransport(h))
        g.jwt_app = lambda: "jwt"
        return g

    for c in (401, 403, 404):
        with pytest.raises(InstalacionPerdida):
            app(201, c).secretos(7, "a/b")
    with pytest.raises(InstalacionPerdida):
        app(404, 200).secretos(7, "a/b")
    for g in (app(201, 500), app(201, 403, "API rate limit exceeded"), app(500, 200)):
        with pytest.raises(GitHubError) as e:
            g.secretos(7, "a/b")
        assert not isinstance(e.value, InstalacionPerdida)
