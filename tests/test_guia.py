"""Conexión C6a: guía nueva (estado de pasos), /api/conexion/*, liga por correo."""
import pytest

from test_conexion import Falsa, empezar, sesion, volver
from test_conexion import gh as _gh   # noqa: F401
from test_web_cuentas import csrf_de
from test_web_tubo import ctx   # noqa: F401
from web.modelos import Cambio, Sincronizacion, Usuario


class ConSecretos(Falsa):
    def __init__(self):
        super().__init__()
        self.secs = []
        self.falla_secretos = False

    def secretos(self, inst, repo):
        if self.falla_secretos:
            from web.github_app import GitHubError
            raise GitHubError(500, "x")
        return [{"name": n, "updated_at": None} for n in self.secs]


@pytest.fixture
def gh(_gh, ctx):
    f = ConSecretos()
    ctx.app.state.github_app = f
    return f


def conectada(ctx, gh):
    cl, uid = sesion(ctx)
    volver(cl, empezar(cl))
    return cl, uid


def token(cl):
    return csrf_de(cl.get("/bienvenida").text)


def test_pantallas_con_app_encendida(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.uso, u.sin_plan = "completo", True
        db.commit()
    for n in range(4):
        r = cl.get(f"/bienvenida?paso={n}")
        assert r.status_code == 200 and "bv.g" not in r.text
        assert "/bienvenida/liga" in r.text
    # sin instalación no se salta a la pantalla 4; la cookie recuerda la pantalla
    assert "Pon tu key" not in cl.get("/bienvenida?paso=4").text
    cl.get("/bienvenida?paso=2")
    assert "Crea tu copia" in cl.get("/bienvenida").text
    volver(cl, empezar(cl))
    r = cl.get("/bienvenida")   # con instalación y repo vinculado: pantalla 4, sin redirigir a /
    assert r.status_code == 200 and "Pon tu key" in r.text


def test_guia_vieja_con_app_apagada(ctx):
    cl, uid = sesion(ctx)
    r = cl.get("/bienvenida")
    assert r.status_code == 200 and "/bienvenida/liga" not in r.text


@pytest.mark.parametrize("secs,esperado,nombre", [
    ([], "falta", None), (["PERSONAL_API_KEY"], "listo", None), (["personal api key"], "nombre_mal", "personal api key"),
    (["Personal-API-Key", "OTRO"], "nombre_mal", "Personal-API-Key"), (["XYZ"], "nombre_mal", "XYZ"),
    (["A", "B"], "falta", None)])
def test_estado_secreto(ctx, gh, secs, esperado, nombre):
    cl, _ = conectada(ctx, gh)
    gh.secs = secs
    j = cl.get("/api/conexion/estado").json()
    assert (j["secreto"], j["nombre"], j["conectado"]) == (esperado, nombre, True)
    assert j["sinc"] is None and j["viva"] is False


def test_estado_sin_conexion_y_sin_sesion(ctx, gh):
    assert ctx.cliente().get("/api/conexion/estado").status_code == 401
    cl, _ = sesion(ctx)
    assert cl.get("/api/conexion/estado").json()["secreto"] is None
    volver(cl, empezar(cl))
    gh.falla_secretos = True
    assert cl.get("/api/conexion/estado").json()["error"] == "otra"


def test_comprobar_dispara_una_vez_y_pide_csrf(ctx, gh):
    cl, uid = conectada(ctx, gh)
    assert cl.post("/api/conexion/comprobar").status_code == 403
    tk = token(cl)
    assert cl.post("/api/conexion/comprobar", data={"csrf": tk}).status_code == 409   # falta el secreto
    gh.secs = ["PERSONAL_API_KEY"]
    j = cl.post("/api/conexion/comprobar", data={"csrf": tk}).json()
    assert j["nueva"] is True and j["sinc"]["tipo"] == "comprobacion" and j["sinc"]["estado"] == "esperando"
    j2 = cl.post("/api/conexion/comprobar", data={"csrf": tk}).json()
    assert j2["nueva"] is False
    assert len(gh.disparos) == 1
    with ctx.sesiones() as db:
        assert db.query(Sincronizacion).filter_by(usuario_id=uid).count() == 1
    assert cl.get("/api/conexion/estado").json()["viva"] is True


def test_comprobar_ya_comprobada_no_repite(ctx, gh):
    cl, uid = conectada(ctx, gh)
    gh.secs = ["PERSONAL_API_KEY"]
    tk = token(cl)
    cl.post("/api/conexion/comprobar", data={"csrf": tk})
    with ctx.sesiones() as db:
        from web import sincronizar
        sincronizar.terminar(db, db.query(Sincronizacion).one(), ok=True, nuevas=1)
    j = cl.post("/api/conexion/comprobar", data={"csrf": tk}).json()
    assert j["nueva"] is False and j["sinc"]["estado"] == "ok" and len(gh.disparos) == 1


def test_comprobar_falla_de_github_es_otra(ctx, gh):
    cl, _ = conectada(ctx, gh)
    gh.secs = ["PERSONAL_API_KEY"]
    gh.falla_disparo = True
    j = cl.post("/api/conexion/comprobar", data={"csrf": token(cl)}).json()
    assert j["sinc"]["estado"] == "error" and j["sinc"]["error"] == "otra"


def test_liga_por_correo_con_limite(ctx, gh):
    enviados = []
    ctx.app.state.enviar = lambda settings, para, asunto, texto: enviados.append((para, texto))
    cl, uid = sesion(ctx)
    assert cl.post("/bienvenida/liga").status_code == 403
    tk = token(cl)
    for _ in range(3):
        r = cl.post("/bienvenida/liga", data={"csrf": tk})
        assert r.headers["location"] == "/bienvenida?liga=ok"
    assert cl.post("/bienvenida/liga", data={"csrf": tk}).headers["location"] == "/bienvenida?liga=limite"
    assert len(enviados) == 3 and enviados[0][0] == "ana@x.com" and "/bienvenida" in enviados[0][1]
    with ctx.sesiones() as db:
        assert db.query(Cambio).filter_by(atleta_id=uid).count() == 3
