"""Conexión C6a: guía nueva (estado de pasos), /api/conexion/*, liga por correo."""
import pytest

from web.modelos import Cambio, Sincronizacion, Usuario
from ayudas import conectada, empezar, sesion, token_guia as token, volver


@pytest.fixture
def gh(gh_con_secretos):
    return gh_con_secretos


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


def test_cada_pantalla_rinde_con_sus_botones(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.uso, u.sin_plan = "completo", True
        db.commit()
    esperado = {0: ["/bienvenida?paso=1", "/bienvenida/liga"], 1: ["github.com/signup", "paso=2"],
                2: ["template_name=", "paso=3"], 3: ["/conectar/github?para=guia"]}
    for n, ligas in esperado.items():
        r = cl.get(f"/bienvenida?paso={n}")
        assert r.status_code == 200 and "bv.g" not in r.text and 'id="guia-celular"' in r.text
        for liga in ligas:
            assert liga in r.text, (n, liga)
    assert "error=" not in cl.get("/bienvenida?paso=3").text
    assert "Elige solo tu copia" in cl.get("/bienvenida?paso=3&error=repos").text
    volver(cl, empezar(cl))
    r = cl.get("/bienvenida")
    for x in ("PERSONAL_API_KEY", "/settings/secrets/actions/new", "guia-estado", "/api/conexion/comprobar", "Add secret"):
        assert x in r.text, x
    assert r.text.index("secrets/actions/new") < r.text.index("personalApiToken")   # nombre en GitHub antes que la key


def test_sin_subida_buena_ya_esta_completo(ctx, gh):
    """E1: completo = nombre + apellido + aviso vigente; la conexión a medias ya no impide entrar a «/»."""
    from web import onboarding
    cl, uid = conectada(ctx, gh)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert onboarding.completo(db, u)
    assert cl.get("/", follow_redirects=False).status_code == 200


def test_dibujos_de_github_en_pantallas_2_3_4(ctx, gh):
    import re
    from pathlib import Path
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.uso, u.sin_plan = "completo", True
        db.commit()
    for n, clave in ((2, "Create repository"), (3, "Install &amp; Authorize")):
        r = cl.get(f"/bienvenida?paso={n}")
        assert 'class="dibujo-gh"' in r.text and 'role="img"' in r.text and clave in r.text, n
    volver(cl, empezar(cl))
    r = cl.get("/bienvenida")
    assert 'class="dibujo-gh"' in r.text and "New secret" in r.text
    for n in (2, 3, 4):
        src = Path(f"web/plantillas/_dibujo_paso{n}.html").read_text()
        assert not re.search(r"#[0-9a-fA-F]{3,8}\b", src) and "rgb(" not in src, n
        assert 'aria-label="' in src and "var(--" in src
