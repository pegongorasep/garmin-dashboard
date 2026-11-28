"""C11: key de Garmin rechazada: un correo por incidente, aviso, /garmin/key y detección por updated_at."""
from datetime import timedelta

import pytest

from web.modelos import Usuario, ahora
from ayudas import _instr, auth_tubo as auth, csrf_de, Falsa, paquete_chico, sesion, subir, token_tubo as token, V2


class ConSecretos(Falsa):
    def __init__(self):
        super().__init__()
        self.updated = None

    def secretos(self, inst, repo):
        return [{"name": "PERSONAL_API_KEY", "updated_at": self.updated}]


@pytest.fixture
def gh(gh, ctx):
    f = ConSecretos()
    ctx.app.state.github_app = f
    return f


def rechazar(ctx, run="9"):
    cl = ctx.cliente()
    _instr(ctx, V2, run_id=run)
    return cl.post("/api/tubo/avance", json={"paso": "arranca", "error": "key_rechazada"}, headers=auth(token(ctx, run_id=run)))


def desde(ctx, uid):
    with ctx.sesiones() as db:
        return db.get(Usuario, uid).key_rechazada_desde


def test_un_solo_correo_por_incidente_y_subida_buena_limpia(ctx):
    from ayudas import usuario_amigo
    uid = usuario_amigo(ctx, repo_id=777)
    assert rechazar(ctx, "1").status_code == 200
    assert desde(ctx, uid) is not None
    assert len(ctx.enviados) == 1
    para, asunto, texto = ctx.enviados[0]
    assert para == "amigo@x.com" and asunto == "Tu key de Garmin dejó de funcionar" and "/garmin/key" in texto
    rechazar(ctx, "2")                       # la programada vuelve a fallar: mismo incidente
    assert len(ctx.enviados) == 1
    assert subir(ctx.cliente(), token(ctx), paquete_chico()).status_code == 200
    assert desde(ctx, uid) is None
    rechazar(ctx, "3")                       # incidente nuevo: otro correo
    assert len(ctx.enviados) == 2


def test_aviso_en_data_json_aparece_y_se_va(ctx, gh):
    from ayudas import con_ajustes
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    with ctx.sesiones() as db:
        db.get(Usuario, uid).gh_instalacion = 55
        db.commit()
    assert cl.get("/data.json").json()["ui"]["sync"]["key_rechazada"] is False
    with ctx.sesiones() as db:
        db.get(Usuario, uid).key_rechazada_desde = ahora()
        db.commit()
    assert cl.get("/data.json").json()["ui"]["sync"]["key_rechazada"] is True
    with ctx.sesiones() as db:
        db.get(Usuario, uid).key_rechazada_desde = None
        db.commit()
    assert cl.get("/data.json").json()["ui"]["sync"]["key_rechazada"] is False


def conectada(ctx, gh):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.repo, u.repo_id, u.gh_instalacion = "ana/ahilallevas-datos", 900, 55
        u.key_rechazada_desde = ahora() - timedelta(hours=1)
        db.commit()
    return cl, uid


def test_pagina_guia_y_deteccion_por_updated_at(ctx, gh):
    cl, uid = conectada(ctx, gh)
    h = cl.get("/garmin/key").text
    assert "PERSONAL_API_KEY" in h and "Update" in h and "github.com/ana/ahilallevas-datos/settings/secrets/actions" in h
    t = csrf_de(h)
    gh.updated = (ahora() - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")     # sigue la vieja
    assert cl.get("/api/garmin/key").json()["cambiada"] is False
    assert cl.post("/api/garmin/key/comprobar", data={"csrf": t}).status_code == 409
    gh.updated = (ahora() + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")   # cambió
    assert cl.get("/api/garmin/key").json()["cambiada"] is True
    r = cl.post("/api/garmin/key/comprobar", data={"csrf": t}).json()
    assert r["nueva"] is True
    assert gh.disparos and gh.disparos[0][1] == "ana/ahilallevas-datos"
    # sigue una subida buena: resuelta
    with ctx.sesiones() as db:
        db.get(Usuario, uid).key_rechazada_desde = None
        db.commit()
    assert cl.get("/api/garmin/key").json()["resuelta"] is True
    assert "Tu key está bien" in cl.get("/garmin/key").text


def test_ya_la_cambie_fuerza_y_exige_csrf(ctx, gh):
    cl, _ = conectada(ctx, gh)
    gh.updated = None
    assert cl.post("/api/garmin/key/comprobar", data={"csrf": "x"}).status_code == 403
    t = csrf_de(cl.get("/garmin/key").text)
    assert cl.post("/api/garmin/key/comprobar", data={"csrf": t, "forzar": "1"}).json()["nueva"] is True


def test_sin_app_explica_a_mano(ctx):
    cl, uid = sesion(ctx)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.repo, u.repo_id = "ana/ahilallevas-datos", 900
        u.key_rechazada_desde = ahora()
        db.commit()
    h = cl.get("/garmin/key").text
    assert "PERSONAL_API_KEY" in h and "gh secret set" not in h and "a mano" in h and "guia-estado" not in h
    assert ctx.cliente().get("/garmin/key", follow_redirects=False).status_code == 303
