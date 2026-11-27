import re
from urllib.parse import parse_qs, urlparse

import pytest

from test_sincronizar import V2, _instr, _sincs
from test_web_cuentas import crear_usuario, entrar
from test_web_tubo import ctx, paquete_chico, subir, token, usuario_amigo   # noqa: F401
from web.github_app import GitHubError
from web.modelos import Cambio, Sincronizacion, Usuario, VinculoPendiente, ahora


class Falsa:
    def __init__(self):
        self.instalaciones = [55]
        self.repos = [{"id": 900, "full_name": "ana/ahilallevas-datos", "private": True, "default_branch": "main"}]
        self.falla_disparo = False
        self.disparos = []

    def url_instalar(self, state):
        return f"https://github.com/apps/x/installations/new?state={state}"

    def token_de_usuario(self, code):
        if code == "mala":
            raise GitHubError(400, "bad_verification_code")
        return "TOKEN-SECRETO-USUARIO"

    def instalaciones_del_usuario(self, token):
        return self.instalaciones

    def repos_de_instalacion(self, inst):
        return self.repos

    def disparar(self, inst, repo, rama, workflow="deploy.yml"):
        if self.falla_disparo:
            raise GitHubError(500, "x")
        self.disparos.append((inst, repo, rama))
        return True


@pytest.fixture
def gh(ctx):
    ctx.settings.github_app_id = ctx.settings.github_app_slug = ctx.settings.github_app_client_id = "x"
    ctx.settings.github_app_client_secret = ctx.settings.github_app_private_key = "x"
    f = Falsa()
    ctx.app.state.github_app = f
    return f


def sesion(ctx, correo="ana@x.com"):
    uid = usuario_amigo(ctx, owner="ana", consentimiento=True)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).correo = correo
        db.commit()
    cl = ctx.cliente()
    entrar(ctx, cl, correo)
    return cl, uid


def empezar(cl, para=None):
    r = cl.get("/conectar/github" + (f"?para={para}" if para else ""))
    assert r.status_code == 303
    return parse_qs(urlparse(r.headers["location"]).query)["state"][0]


def volver(cl, state, code="bueno", inst="55"):
    return cl.get("/conectar/github/vuelta", params={"state": state, "code": code, "installation_id": inst,
                                                     "setup_action": "install"})


def test_apagada_da_404(ctx):
    cl, _ = sesion(ctx)
    assert cl.get("/conectar/github").status_code == 404
    assert cl.get("/conectar/github/vuelta").status_code == 404


def test_exige_sesion_y_consentimiento(ctx, gh):
    assert ctx.cliente().get("/conectar/github").headers["location"] == "/entrar"
    uid = usuario_amigo(ctx, consentimiento=False)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).correo = "s@x.com"
        db.commit()
    cl = ctx.cliente()
    entrar(ctx, cl, "s@x.com")
    assert cl.get("/conectar/github").headers["location"] == "/bienvenida"


def test_exito_vincula_guarda_instalacion_y_no_filtra_token(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        db.add(VinculoPendiente(usuario_id=uid, repo="ana/x", repo_id=900, nonce="n", codigo_hash="h",
                                expira=ahora().replace(year=2099)))
        db.commit()
    r = volver(cl, empezar(cl))
    assert r.headers["location"] == "/bienvenida?paso=4"
    assert "TOKEN-SECRETO" not in r.text and "TOKEN-SECRETO" not in str(r.headers)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo, u.repo_id, u.gh_instalacion) == ("ana/ahilallevas-datos", 900, 55)
        assert db.get(VinculoPendiente, uid) is None
        c = db.query(Cambio).filter(Cambio.atleta_id == uid).one()
        assert c.descripcion.startswith("Repo vinculado con la app de GitHub")
        for t in db.query(Usuario).all():
            assert "TOKEN-SECRETO" not in str([getattr(t, k.name) for k in Usuario.__table__.columns])


def test_ya_conectado_mismo_repo_y_destino_conexiones(ctx, gh):
    cl, uid = sesion(ctx)
    volver(cl, empezar(cl))
    gh.instalaciones = [56]
    r = volver(cl, empezar(cl, "conectado"), inst="56")
    assert r.headers["location"] == "/"
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).gh_instalacion == 56
        assert db.query(Cambio).filter(Cambio.atleta_id == uid).count() == 1


@pytest.mark.parametrize("caso,codigo", [("cancelado", "cancelado"), ("falsa", "instalacion"), ("cero", "repos"),
                                         ("dos", "repos"), ("publica", "publica"), ("github", "github")])
def test_errores(ctx, gh, caso, codigo):
    cl, uid = sesion(ctx)
    st = empezar(cl)
    kw = {}
    if caso == "cancelado":
        kw["code"] = ""
    if caso == "falsa":
        kw["inst"] = "99"
    if caso == "cero":
        gh.repos = []
    if caso == "dos":
        gh.repos = gh.repos * 2
    if caso == "publica":
        gh.repos = [{**gh.repos[0], "private": False}]
    if caso == "github":
        kw["code"] = "mala"
    r = volver(cl, st, **kw)
    assert r.headers["location"] == f"/bienvenida?paso=3&error={codigo}"
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).gh_instalacion is None and db.get(Usuario, uid).repo_id is None


def test_mensaje_de_error_se_muestra(ctx, gh):
    cl, _ = sesion(ctx)
    assert "Elige solo tu copia ahilallevas-datos" in cl.get("/bienvenida?paso=3&error=repos").text
    assert "Elige solo tu copia" in cl.get("/conexiones?error=repos").text


def test_otra_copia_y_ajena(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).repo_id, db.get(Usuario, uid).repo = 111, "ana/otra"
        db.commit()
    assert volver(cl, empezar(cl)).headers["location"].endswith("error=otra_copia")
    with ctx.sesiones() as db:
        db.get(Usuario, uid).repo_id = None
        db.add(Usuario(correo="b@x.com", repo_id=900, repo="b/r"))
        db.commit()
    assert volver(cl, empezar(cl)).headers["location"].endswith("error=ajena")


def test_state_ausente_robado_o_de_otra_persona(ctx, gh):
    cl, uid = sesion(ctx)
    st = empezar(cl)
    assert volver(cl, "otro").headers["location"].endswith("error=estado")
    cl2 = ctx.cliente()
    assert volver(cl2, st).headers["location"] == "/entrar"   # sin sesión
    cl4 = ctx.cliente()
    with ctx.sesiones() as db:
        db.add(Usuario(correo="c@x.com", nombre="C", apellido="D"))
        db.commit()
    entrar(ctx, cl4, "c@x.com")
    assert volver(cl4, st).headers["location"].endswith("error=estado")   # sin su cookie de state
    cl4.cookies.set("gh_estado", cl.cookies.get("gh_estado"), path="/conectar/github")
    assert volver(cl4, st).headers["location"].endswith("error=estado")   # cookie ligada a otro usuario


# --- correcciones de C3 ---
def test_schedule_con_historial_pendiente_pide_historial(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).historial_pendiente = True
        db.commit()
    r = _instr(ctx, V2, run_id="9", event_name="schedule").json()
    assert (r["dias_actividades"], r["semanas_salud"]) == (365, 16)
    assert _sincs(ctx)[0][0] == "historial"


def _tras_comprobacion(ctx, gh):
    uid = usuario_amigo(ctx, repo_id=777)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).gh_instalacion = 55
        db.add(Sincronizacion(usuario_id=uid, tipo="comprobacion", estado="esperando"))
        db.commit()
    _instr(ctx, V2, run_id="3")
    return subir(ctx.cliente(), token(ctx, run_id="3"), paquete_chico())


def test_comprobacion_ok_dispara_historial(ctx, gh):
    assert _tras_comprobacion(ctx, gh).status_code == 200
    assert gh.disparos == [(55, "amigo/garmin-prueba", "main")]
    s = _sincs(ctx)
    assert s[0][:2] == ("comprobacion", "ok") and s[1][:2] == ("historial", "esperando")


def test_si_github_falla_el_historial_queda_en_error_y_la_subida_sigue(ctx, gh):
    gh.falla_disparo = True
    assert _tras_comprobacion(ctx, gh).status_code == 200
    s = _sincs(ctx)
    assert s[1][0] == "historial" and s[1][1] == "error" and s[1][6] == "otra"


def test_sin_app_no_dispara(ctx):
    assert _tras_comprobacion(ctx, Falsa()).status_code == 200
    assert len(_sincs(ctx)) == 1


def test_migrar_vuelta_misma_copia_va_a_hoy_o_a_ajustes(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:   # conectado a la manera vieja: copia sin instalación
        u = db.get(Usuario, uid)
        u.repo, u.repo_id, u.gh_instalacion = "ana/ahilallevas-datos", 900, None
        db.commit()
    assert volver(cl, empezar(cl, "conectado")).headers["location"] == "/"
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo_id, u.gh_instalacion) == (900, 55)
        u.gh_instalacion = None
        db.commit()
    assert volver(cl, empezar(cl, "ajustes")).headers["location"] == "/ajustes"
