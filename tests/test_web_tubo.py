import gzip
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pytest
import yaml
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

import ajustes
import build
import paquete
import validar
from test_web_cuentas import CONFIG, crear_usuario, csrf_de, entrar, post
from web import calculo, importar, onboarding, tubo
from web.modelos import Ajustes, Cambio, Consentimiento, DatoGarmin, Plan, Subida, Usuario, ahora

ROOT = Path(__file__).parent.parent
HAY_DATOS = (ROOT / "data" / "activities.json").exists() and (ROOT / "config.yaml").exists()
ISS = "https://token.actions.githubusercontent.com"
WORKFLOW = "pegongorasep/garmin-dashboard/.github/workflows/motor.yml@refs/tags/stable"
LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTRA_LLAVE = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks_falso():
    jwk = json.loads(RSAAlgorithm.to_jwk(LLAVE.public_key()))
    jwk.update({"kid": "k1", "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def token(web_ctx, llave=LLAVE, **extra):
    claims = {"iss": ISS, "aud": web_ctx.settings.oidc_audience, "exp": int(time.time()) + 600,
              "repository": "amigo/garmin-prueba", "repository_id": "777", "repository_owner": "Amigo",
              "repository_owner_id": "5", "repository_visibility": "private", "job_workflow_ref": WORKFLOW, **extra}
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, llave, algorithm="RS256", headers={"kid": "k1"})


@pytest.fixture
def ctx(web_ctx):
    web_ctx.app.state.jwks_fetch = lambda url: jwks_falso()
    web_ctx.app.state.__dict__.pop("jwks_cache", None)
    return web_ctx


def usuario_amigo(ctx, owner="amigo", consentimiento=True, repo_id=None):
    with ctx.sesiones() as db:
        u = Usuario(correo="amigo@x.com", github_owner=owner, repo_id=repo_id, repo="amigo/garmin-prueba" if repo_id else None)
        db.add(u)
        db.commit()
        if consentimiento:
            db.add(Consentimiento(usuario_id=u.id, version_aviso="2026-12"))
            db.commit()
        return u.id


def auth(tok):
    return {"Authorization": f"Bearer {tok}"}


def paquete_chico(**cambios):
    pq = {"esquema": 1, "motor": "abc123", "archivos": {
        "daily": {"daily_summaries": [{"calendarDate": "2026-11-01", "heartRate": {"restingValue": 60}}], "sleep": [], "hrv": []},
        "activities": [{"id": "a1", "es_carrera": False, "startTimeLocal": "2026-11-01 07:00:00",
                        "activityType": {"typeKey": "running"}, "duration": 1200.0, "distance": 3000.0}],
        "activity_details": {"a1": {"rpe": 3.0, "serie": [[0, 0, 100]]}}, "hr_zones": [{"sport": "DEFAULT", "maxHeartRateUsed": 190}],
        "historial_corridas": [], "meta": {"pulled_at": "2026-11-01", "pulled_at_utc": "2026-11-01T12:00:00+00:00"}}}
    pq.update(cambios)
    return pq


def subir(cl, tok, pq, comprimir=True):
    cuerpo = json.dumps(pq).encode()
    cab = auth(tok)
    if comprimir:
        cuerpo, cab = gzip.compress(cuerpo), {**cab, "Content-Encoding": "gzip"}
    return cl.post("/api/tubo/subida", content=cuerpo, headers={**cab, "Content-Type": "application/json"})


# --- OIDC ---

@pytest.mark.parametrize("extra,llave,codigo", [
    ({}, LLAVE, 200),
    ({"aud": "https://otra.web"}, LLAVE, 401),
    ({"exp": int(time.time()) - 10}, LLAVE, 401),
    ({"iss": "https://evil.example"}, LLAVE, 401),
    ({"job_workflow_ref": "otro/repo/.github/workflows/motor.yml@refs/tags/stable"}, LLAVE, 403),
    ({"job_workflow_ref": "pegongorasep/garmin-dashboard/.github/workflows/otro.yml@refs/tags/stable"}, LLAVE, 403),
    ({"job_workflow_ref": "pegongorasep/garmin-dashboard/.github/workflows/motor.yml@refs/heads/dev"}, LLAVE, 403),
    ({"job_workflow_ref": "pegongorasep/garmin-dashboard/.github/workflows/motor.yml@refs/heads/main"}, LLAVE, 200),
    ({}, OTRA_LLAVE, 401),
])
def test_verificacion_del_token(ctx, extra, llave, codigo):
    usuario_amigo(ctx, repo_id=777)
    r = ctx.cliente().post("/api/tubo/instrucciones", headers=auth(token(ctx, llave, **extra)))
    assert r.status_code == codigo, r.text


def test_sin_token_o_con_basura_es_401(ctx):
    cl = ctx.cliente()
    assert cl.post("/api/tubo/instrucciones").status_code == 401
    assert cl.post("/api/tubo/instrucciones", headers=auth("basura")).status_code == 401
    assert cl.post("/api/tubo/subida", content=b"{}").status_code == 401


def test_token_sin_alg_none(ctx):
    usuario_amigo(ctx, repo_id=777)
    falso = jwt.encode({"iss": ISS, "aud": ctx.settings.oidc_audience, "exp": int(time.time()) + 60}, None, algorithm="none")
    assert ctx.cliente().post("/api/tubo/instrucciones", headers=auth(falso)).status_code == 401


# --- vinculación ---

def codigo_de_respuesta(r):
    assert r.status_code == 403 and r.json()["error"] == "repo no vinculado"
    return r.json().get("codigo")


def escribir_codigo(cl, codigo):
    return cl.post("/bienvenida/codigo", data={"csrf": csrf_de(cl.get("/bienvenida?paso=6").text), "codigo": codigo})


def test_coincidir_el_owner_no_vincula_hay_que_probar_el_codigo(ctx):
    uid = usuario_amigo(ctx, owner="AMIGO")   # sin distinguir mayúsculas
    cl = ctx.cliente()
    r = cl.post("/api/tubo/instrucciones", headers=auth(token(ctx)))
    codigo = codigo_de_respuesta(r)
    assert re.fullmatch(r"[0-9]{6}", codigo)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert u.repo_id is None and db.query(Cambio).count() == 0   # todavía nada vinculado
        p = db.query(tubo.VinculoPendiente).one()
        assert (p.repo, p.repo_id, p.owner_id) == ("amigo/garmin-prueba", 777, 5)
        assert p.codigo_hash == tubo.hash_codigo(codigo) and codigo not in str(p.__dict__)   # solo el hash
    # la subida que genera el código no se guarda; reutiliza el mismo pendiente y el mismo código
    r = subir(cl, token(ctx), paquete_chico())
    assert codigo_de_respuesta(r) == codigo
    with ctx.sesiones() as db:
        assert db.query(DatoGarmin).count() == 0 and db.query(Subida).count() == 0 and db.query(tubo.VinculoPendiente).count() == 1
    # la persona entra a la web y escribe el código
    crear_sesion = entrar(ctx, ctx.cliente(), "amigo@x.com")
    assert escribir_codigo(crear_sesion, codigo).status_code == 303
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo, u.repo_id, u.github_owner_id) == ("amigo/garmin-prueba", 777, 5)
        c = db.query(Cambio).filter_by(atleta_id=uid).one()
        assert c.via == "sistema" and "amigo/garmin-prueba" in c.descripcion
        assert db.query(tubo.VinculoPendiente).count() == 0
    # ya vinculado, la siguiente subida sí se guarda, y el paso 6 ofrece "Run workflow"
    assert subir(cl, token(ctx), paquete_chico()).status_code == 200
    assert "Run workflow en mi repo" in crear_sesion.get("/bienvenida?paso=6").text


def test_un_invitado_que_reclama_el_owner_de_otro_no_vincula_sin_el_codigo(ctx):
    victima = usuario_amigo(ctx, owner="pegongorasep")   # el invitado escribió el owner de la víctima
    cl = ctx.cliente()
    codigo = codigo_de_respuesta(cl.post("/api/tubo/instrucciones", headers=auth(token(
        ctx, repository_owner="pegongorasep", repository="pegongorasep/su-repo"))))
    # el código solo está en el resumen del repo de la víctima: el invitado no lo tiene y adivina
    cl2 = entrar(ctx, ctx.cliente(), "amigo@x.com")
    malo = "000000" if codigo != "000000" else "111111"
    r = escribir_codigo(cl2, malo)
    assert r.status_code == 400 and "no coincide" in r.text
    with ctx.sesiones() as db:
        assert db.get(Usuario, victima).repo_id is None
    assert subir(cl, token(ctx, repository_owner="pegongorasep"), paquete_chico()).status_code == 403
    with ctx.sesiones() as db:
        assert db.query(DatoGarmin).count() == 0


def test_repo_publico_o_sin_dato_de_visibilidad_nunca_se_vincula_solo(ctx):
    uid = usuario_amigo(ctx)
    cl = ctx.cliente()
    for vis in ("public", "internal", None):
        r = cl.post("/api/tubo/instrucciones", headers=auth(token(ctx, repository_visibility=vis)))
        assert r.status_code == 403 and "codigo" not in r.json()
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).repo_id is None and db.query(tubo.VinculoPendiente).count() == 0


def test_codigo_vencido_equivocado_y_limite_de_intentos(ctx):
    uid = usuario_amigo(ctx)
    cl = ctx.cliente()
    web = entrar(ctx, ctx.cliente(), "amigo@x.com")
    codigo = codigo_de_respuesta(cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))))
    malo = "000000" if codigo != "000000" else "111111"
    # equivocado, 4 veces: sigue vigente; con el correcto vincula (comparación sin espacios)
    for restantes in (4, 3, 2, 1):
        r = escribir_codigo(web, malo)
        assert r.status_code == 400 and f"({restantes} intentos más)" in r.text
    # el quinto intento equivocado invalida el pendiente
    r = escribir_codigo(web, malo)
    assert r.status_code == 400 and "Demasiados intentos" in r.text
    with ctx.sesiones() as db:
        assert db.query(tubo.VinculoPendiente).count() == 0
    assert "No hay un código vigente" in escribir_codigo(web, codigo).text   # ni el correcto sirve ya
    # la siguiente corrida genera otro (distinto, con otro nonce)
    nuevo = codigo_de_respuesta(cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))))
    with ctx.sesiones() as db:
        assert db.query(tubo.VinculoPendiente).one().intentos == 0
    # vencido: no vincula y la siguiente corrida genera otro
    with ctx.sesiones() as db:
        db.query(tubo.VinculoPendiente).one().expira = ahora() - timedelta(seconds=1)
        db.commit()
    assert "No hay un código vigente" in escribir_codigo(web, nuevo).text
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).repo_id is None
    otro = codigo_de_respuesta(cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))))
    assert re.fullmatch(r"[0-9]{6}", otro)
    assert escribir_codigo(web, " " + otro[:3] + " " + otro[3:]).status_code == 303   # con espacios también


def test_sin_consentimiento_o_owner_equivocado_no_hay_ni_codigo(ctx):
    usuario_amigo(ctx, consentimiento=False)
    cl = ctx.cliente()
    assert "codigo" not in cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()
    with ctx.sesiones() as db:
        db.add(Consentimiento(usuario_id=1, version_aviso="2026-12"))
        db.commit()
    assert "codigo" not in cl.post("/api/tubo/instrucciones", headers=auth(token(ctx, repository_owner="otro"))).json()
    assert "codigo" in cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()


def test_cli_vincular(ctx, capsys):
    from web import cli
    uid = crear_usuario(ctx, "pedro@x.com")
    args = dict(settings=ctx.settings, motor=ctx.motor)
    assert cli.main(["vincular", "nadie@x.com", "a/b", "5"], **args) == 1
    assert cli.main(["vincular", "pedro@x.com", "sin-diagonal", "5"], **args) == 1
    assert cli.main(["vincular", "pedro@x.com", "pegongorasep/garmin-dashboard", "123"], **args) == 0
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.repo, u.repo_id, u.github_owner) == ("pegongorasep/garmin-dashboard", 123, "pegongorasep")
        c = db.query(Cambio).one()
        assert c.via == "sistema" and "a mano" in c.descripcion
    # su repo es público: con repo_id ya vinculado el token público sí sube
    r = ctx.cliente().post("/api/tubo/instrucciones", headers=auth(token(ctx, repository_visibility="public", repository_id="123")))
    assert r.status_code == 200


def test_un_repo_ya_vinculado_a_otro_usuario_no_se_roba(ctx):
    usuario_amigo(ctx, owner="amigo", repo_id=777)
    with ctx.sesiones() as db:
        db.add(Usuario(correo="b@x.com", github_owner="amigo"))
        db.commit()
    # el repo 777 sigue siendo del primero; otro repo del mismo owner no se vincula a nadie (el primero ya tiene repo)
    assert ctx.cliente().post("/api/tubo/instrucciones", headers=auth(token(ctx))).status_code == 200
    r = ctx.cliente().post("/api/tubo/instrucciones", headers=auth(token(ctx, repository_id="999")))
    assert r.status_code == 403 or r.json()["vinculado"]
    with ctx.sesiones() as db:
        assert db.query(Usuario).filter_by(correo="amigo@x.com").one().repo_id == 777


def test_instrucciones_primera_corrida_y_historial_pedido(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    cl = ctx.cliente()
    d = cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()
    assert d["dias_actividades"] == 365 and d["historial_desde"] == (ahora().date() - timedelta(days=365)).isoformat()
    assert subir(cl, token(ctx), paquete_chico()).status_code == 200
    d = cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()
    assert d == {"vinculado": True, "historial_desde": None, "dias_actividades": 120}
    with ctx.sesiones() as db:
        db.get(Usuario, uid).historial_desde = "2024-01-01"
        db.commit()
    assert cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()["historial_desde"] == "2024-01-01"
    assert subir(cl, token(ctx), paquete_chico()).status_code == 200   # la subida cumple el pedido
    assert cl.post("/api/tubo/instrucciones", headers=auth(token(ctx))).json()["historial_desde"] is None


# --- subida ---

def test_subida_guarda_con_upsert_y_registra(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    cl = ctx.cliente()
    r = subir(cl, token(ctx), paquete_chico())
    assert r.status_code == 200 and r.json() == {"ok": True, "publicar_pages": True}
    n = None
    for _ in range(2):   # subir lo mismo dos veces no duplica
        subir(cl, token(ctx), paquete_chico())
        with ctx.sesiones() as db:
            filas = db.query(DatoGarmin).filter_by(usuario_id=uid).count()
        n = n or filas
        assert filas == n
    with ctx.sesiones() as db:
        s = db.query(Subida).filter_by(usuario_id=uid).first()
        assert s.ok and s.motor == "abc123" and s.bytes > 0
        db.get(Usuario, uid).migrado = True
        db.commit()
    assert subir(cl, token(ctx), paquete_chico()).json()["publicar_pages"] is False


def test_subida_con_clave_prohibida_da_422(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    pq = paquete_chico()
    pq["archivos"]["activities"][0]["activityName"] = "Carrera secreta"
    r = subir(ctx.cliente(), token(ctx), pq)
    assert r.status_code == 422 and any("activityName" in p for p in r.json()["problemas"])
    with ctx.sesiones() as db:
        assert db.query(DatoGarmin).count() == 0
        s = db.query(Subida).one()
        assert not s.ok and "activityName" in s.error


def test_subida_sin_gzip_gzip_roto_y_muy_grande(ctx):
    usuario_amigo(ctx, repo_id=777)
    cl = ctx.cliente()
    assert subir(cl, token(ctx), paquete_chico(), comprimir=False).status_code == 200
    r = cl.post("/api/tubo/subida", content=b"no es gzip", headers={**auth(token(ctx)), "Content-Encoding": "gzip"})
    assert r.status_code == 400
    r = cl.post("/api/tubo/subida", content=b"{no json", headers=auth(token(ctx)))
    assert r.status_code == 400
    bomba = gzip.compress(b"0" * (30 * 1024 * 1024))   # chiquito comprimido, enorme al abrirlo
    r = cl.post("/api/tubo/subida", content=bomba, headers={**auth(token(ctx)), "Content-Encoding": "gzip"})
    assert r.status_code == 413
    assert cl.post("/api/tubo/subida", content=b"x" * (tubo.MAX_COMPRIMIDO + 1), headers=auth(token(ctx))).status_code == 413


def test_subida_de_un_repo_no_vinculado_no_guarda_nada(ctx):
    usuario_amigo(ctx, owner="otro")
    r = subir(ctx.cliente(), token(ctx), paquete_chico())
    assert r.status_code == 403
    with ctx.sesiones() as db:
        assert db.query(DatoGarmin).count() == 0


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_regla_de_oro_por_el_tubo(ctx):
    """Los archivos de data/ -> paquete -> endpoint -> base -> data.json == build() con los archivos de data/."""
    uid = usuario_amigo(ctx, repo_id=777)
    with ctx.sesiones() as db:
        db.query(Consentimiento).delete()
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT / "tests" / "no-existe")   # no falla: carpeta vacía
        # solo ajustes, plan e InBody de Pedro; los datos entran por el tubo
        import shutil, tempfile
        with tempfile.TemporaryDirectory() as t:
            shutil.copy(ROOT / "config.yaml", t)
            shutil.copytree(ROOT / "plan", Path(t) / "plan", ignore=shutil.ignore_patterns("__pycache__"))
            importar.importar_carpeta(db, db.get(Usuario, uid), t)
    pq = paquete.armar(ROOT / "data", salt="777")
    assert subir(ctx.cliente(), token(ctx), pq).status_code == 200
    ahora_utc = datetime(2026, 11, 25, 18, 0)
    with ctx.sesiones() as db:
        web = calculo.calcular(db, db.get(Usuario, uid), ahora_utc)
    cfg = ajustes.cargar_config(ROOT)
    from zoneinfo import ZoneInfo
    local = ahora_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"]))
    esp = build.build(build.load_data(ROOT), build.load_plan(ROOT), {**cfg, "modo": "web", "menu": calculo.MENU, "plan_acciones": calculo.PLAN_ACCIONES, "editar_urls": calculo.editar_urls(build.load_plan(ROOT)), "idioma": "es",
                      "acciones_url": "https://github.com/amigo/garmin-prueba/actions/workflows/deploy.yml"}, local)
    web["ui"].pop("repo_estado")   # depende de la hora de la última subida; se prueba aparte
    assert json.dumps(web, sort_keys=True) == json.dumps(esp, sort_keys=True)
    assert validar.problemas(web) == []


# --- estado del repo ---

def test_banner_de_repo_atrasado(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert calculo.estado_repo(db, u, ahora())["texto"].startswith("Tu repo todavía no ha mandado datos")
        db.add(Subida(usuario_id=uid, fecha=ahora() - timedelta(hours=30), ok=True))
        db.commit()
        e = calculo.estado_repo(db, u, ahora())
        assert "30 h" in e["texto"] and e["ligas"][0]["url"] == "https://github.com/amigo/garmin-prueba/actions"
        d = {"ui": {"repo_estado": e}}
        assert [p for p in validar.problemas({**d, **{k: {} for k in validar.OBLIGATORIAS if k != "ui"}}) if "URL" in p] == []
        db.add(Subida(usuario_id=uid, fecha=ahora() - timedelta(hours=2), ok=True))
        db.commit()
        assert calculo.estado_repo(db, u, ahora()) is None
        u.repo_id = None
        assert calculo.estado_repo(db, u, ahora()) is None


def test_validar_no_deja_pasar_otras_urls_en_repo_estado():
    base = {k: {} for k in validar.OBLIGATORIAS}
    malo = {**base, "ui": {"repo_estado": {"ligas": [{"url": "https://evil.example/x"}]}}}
    assert any("URL" in p for p in validar.problemas(malo))
    malo = {**base, "ui": {"otra": {"url": "https://github.com/x/actions"}}}
    assert any("URL" in p for p in validar.problemas(malo))


# --- onboarding ---

def test_onboarding_completo(ctx):
    uid = crear_usuario(ctx, "nuevo@x.com")
    cl = entrar(ctx, ctx.cliente(), "nuevo@x.com")
    r = cl.get("/")
    assert r.status_code == 303 and r.headers["location"] == "/bienvenida"
    assert "acepto expresamente" in cl.get("/bienvenida").text
    # sin consentimiento no avanza (ni siquiera pidiendo el paso 4)
    assert "acepto expresamente" in cl.get("/bienvenida?paso=4").text
    assert cl.post("/bienvenida/github", data={"csrf": csrf_de(cl.get("/bienvenida").text), "usuario": "yo"}).status_code == 403
    # consentimiento: debe estar marcada la casilla
    cl.post("/bienvenida/consentimiento", data={"csrf": csrf_de(cl.get("/bienvenida").text)})
    with ctx.sesiones() as db:
        assert db.query(Consentimiento).count() == 0
    cl.post("/bienvenida/consentimiento", data={"csrf": csrf_de(cl.get("/bienvenida").text), "acepto": "on"})
    with ctx.sesiones() as db:
        c = db.query(Consentimiento).one()
        assert c.version_aviso == "2026-12" and c.fecha
    assert "¿Qué quieres usar?" in cl.get("/bienvenida").text
    cl.post("/bienvenida/uso", data={"csrf": csrf_de(cl.get("/bienvenida").text), "uso": "completo"})
    assert "usuario de GitHub" in cl.get("/bienvenida").text
    # usuario inválido
    r = cl.post("/bienvenida/github", data={"csrf": csrf_de(cl.get("/bienvenida").text), "usuario": "no válido!"})
    assert r.status_code == 400 and "Escribe tu usuario" in r.text
    r = cl.post("/bienvenida/github", data={"csrf": csrf_de(cl.get("/bienvenida").text), "usuario": "@Yo-Mismo"})
    assert r.status_code == 303
    p3 = cl.get("/bienvenida?paso=3").text
    assert "template_owner=pegongorasep" in p3 and "template_name=garmin-dashboard-template" in p3 and "visibility=private" in p3
    assert "&amp;name=ahilallevas-datos" in p3 and "Si le pusiste otro nombre, abre tu repo en GitHub y sigue igual" in p3
    p4 = cl.get("/bienvenida?paso=4").text
    assert "https://github.com/Yo-Mismo/ahilallevas-datos/settings/secrets/actions/new" in p4 and "PERSONAL_API_KEY" in p4
    assert "no la pedimos nunca" in p4 and 'type="password"' not in p4 and "<input" not in p4   # ningún campo para la key
    assert "https://github.com/Yo-Mismo/ahilallevas-datos/actions" in cl.get("/bienvenida?paso=5").text
    # todavía no hay datos: el paso 7 no se abre
    assert "Comprueba que ese repo es tuyo" in cl.get("/bienvenida?paso=7").text
    assert cl.get("/api/estado").json() == {"vinculado": False, "repo": None, "datos": False, "ultima_subida": None,
                                            "consentimiento": True, "plan": False}
    # el repo sube su primer paquete (esto vincula)
    tok = token(ctx, repository_owner="yo-mismo", repository="Yo-Mismo/ahilallevas-datos")
    r = subir(ctx.cliente(), tok, paquete_chico())
    codigo = codigo_de_respuesta(r)   # primera corrida: no guarda, da el código
    assert cl.get("/api/estado").json()["vinculado"] is False
    p6 = cl.get("/bienvenida").text   # con código pendiente cae en el paso 6
    assert "Comprueba que ese repo es tuyo" in p6 and "https://github.com/Yo-Mismo/ahilallevas-datos/actions" in p6
    assert escribir_codigo(cl, codigo).status_code == 303
    assert "Run workflow en mi repo" in cl.get("/bienvenida?paso=6").text
    assert subir(ctx.cliente(), tok, paquete_chico()).status_code == 200
    e = cl.get("/api/estado").json()
    assert e["vinculado"] and e["datos"] and e["repo"] == "Yo-Mismo/ahilallevas-datos" and e["ultima_subida"].endswith("Z")
    p7 = cl.get("/bienvenida").text   # sin paso: salta al 7
    assert "Crear mi plan" in p7
    # preguntas
    datos = {"titulo": "Mi plan", "nivel": "novato", "intensidad": "solo_z2", "caminatas": "on", "z2": "15", "larga": "30",
             "edad": "35", "fc_max": "", "cats": ["fuerza", "hiit"], "pierna": ["lun"], "inicio": "2030-01-07",
             "sensor": "muñeca", "zona": "America/Merida"}
    malos = [{**datos, "inicio": "2030-01-08"}, {**datos, "edad": "", "fc_max": ""}, {**datos, "zona": "Marte/Base"},
             {**datos, "z2": "abc"}]
    for m in malos:
        r = cl.post("/bienvenida/plan", data={"csrf": csrf_de(cl.get("/bienvenida").text), **m})
        assert r.status_code == 400 and 'role="alert"' in r.text
    r = cl.post("/bienvenida/plan", data={"csrf": csrf_de(cl.get("/bienvenida").text), **datos})
    assert r.status_code == 303 and r.headers["location"] == "/"
    with ctx.sesiones() as db:
        a, p = db.get(Ajustes, uid), db.get(Plan, uid)
        assert a.config["corrida"]["inicio"] == "2030-01-07" and a.config["perfil"]["titulo"] == "Mi plan"
        assert [c["id"] for c in a.config["actividades"]["categorias"]] == ["fuerza", "hiit"]
        assert len(p.plan["weeks"]) == 12 and p.plan["start"] == "2030-01-07"
        assert db.get(Usuario, uid).sensor == "muñeca"
    # ya con plan: el dashboard (con el pie y el aviso), y /bienvenida regresa a /
    inicio = cl.get("/")
    assert inicio.status_code == 200 and "Aviso de privacidad" in inicio.text and "no es consejo médico" in inicio.text
    assert cl.get("/bienvenida").headers["location"] == "/"
    r = cl.get("/data.json")
    assert r.status_code == 200 and validar.problemas(r.json()) == []
    assert cl.post("/bienvenida/plan", data={"csrf": csrf_de(cl.get("/salir").text), **datos}).status_code in (403, 400)


def test_onboarding_usuario_de_github_repetido(ctx):
    usuario_amigo(ctx, owner="ocupado")
    crear_usuario(ctx, "otro@x.com")
    cl = entrar(ctx, ctx.cliente(), "otro@x.com")
    with ctx.sesiones() as db:
        db.add(Consentimiento(usuario_id=2, version_aviso="2026-12"))
        db.commit()
    r = cl.post("/bienvenida/github", data={"csrf": csrf_de(cl.get("/bienvenida").text), "usuario": "OCUPADO"})
    assert r.status_code == 400 and "ya está ligado" in r.text


def test_privacidad_publica_con_lo_necesario(ctx):
    t = ctx.cliente().get("/privacidad").text
    for frase in ("consentimiento expreso", "datos sensibles", "Google Cloud", "Neon", "Resend", "GitHub", "Cloudflare",
                  "Garmin", "ARCO", "no es consejo médico", "Datos de Garmin", "2026-12", ctx.settings.admin_correo):
        assert frase.lower() in t.lower(), frase


def test_paso_a_paso_no_pide_la_key():
    """Ninguna plantilla tiene un campo (input) que pida la key de Garmin."""
    for f in (ROOT / "web" / "plantillas").glob("*.html"):
        texto = f.read_text().lower()
        assert not re.search(r"<input[^>]*(key|token|password)", texto), f.name
        assert "name=\"key\"" not in texto


# --- scripts/subir.py ---

sys.path.insert(0, str(ROOT / "scripts"))
import subir as sub  # noqa: E402


class RespuestaFalsa:
    def __init__(self, status=200, cuerpo=None):
        self.status_code, self._c = status, cuerpo or {}

    def json(self):
        return self._c

    def raise_for_status(self):
        pass


class HttpFalso:
    def __init__(self, post, get=None):
        self._post, self._get, self.llamadas = post, get, []

    def post(self, url, **kw):
        self.llamadas.append(("post", url, kw))
        return self._post(url, **kw)

    def get(self, url, **kw):
        self.llamadas.append(("get", url, kw))
        return self._get(url, **kw)


def _caido(url, **kw):
    raise sub.requests.ConnectionError("web caída")


ENTORNO = {"ACTIONS_ID_TOKEN_REQUEST_URL": "https://actions.example/t?x=1", "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "tok",
           "GITHUB_REPOSITORY_ID": "777"}


def test_subir_con_la_web_caida_no_falla_y_publica_pages(tmp_path):
    (tmp_path / "meta.json").write_text('{"pulled_at": "2026-11-01"}')
    http = HttpFalso(_caido, lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    pausas = []
    assert sub.subir(tmp_path, ENTORNO, http, pausas.append) is True
    assert len([c for c in http.llamadas if c[0] == "post"]) == 1 + sub.REINTENTOS and len(pausas) == sub.REINTENTOS
    assert sub.instrucciones(http, lambda s: None) == ""
    # sin token OIDC tampoco truena
    assert sub.subir(tmp_path, {}, http, lambda s: None) is True


def test_subir_ok_y_migrado(tmp_path):
    (tmp_path / "meta.json").write_text('{"pulled_at": "2026-11-01"}')
    for publicar in (True, False):
        http = HttpFalso(lambda url, **kw: RespuestaFalsa(200, {"ok": True, "publicar_pages": publicar}),
                         lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
        assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) is publicar
        _, url, kw = [c for c in http.llamadas if c[0] == "post"][0]
        assert url.endswith("/api/tubo/subida") and kw["headers"]["Content-Encoding"] == "gzip"
        assert json.loads(gzip.decompress(kw["data"]))["esquema"] == 1
        assert kw["timeout"] == 60 and "key" not in json.dumps(json.loads(gzip.decompress(kw["data"]))).lower()


def test_web_responde_403_no_vinculado(tmp_path):
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(403, {"error": "repo no vinculado"}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) is True
    assert sub.instrucciones(http, lambda s: None) == ""


def test_instrucciones_a_argumentos(monkeypatch):
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://actions.example/t")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "tok")
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(200, {"vinculado": True, "historial_desde": "2025-11-25", "dias_actividades": 365}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.instrucciones(http, lambda s: None) == "--dias-actividades 365 --historial-desde 2025-11-25"
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(200, {"dias_actividades": 120, "historial_desde": None}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.instrucciones(http, lambda s: None) == "--dias-actividades 120"
    # una respuesta con forma rara jamás llega al shell
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(200, {"dias_actividades": 1, "historial_desde": "2025-01-01; rm -rf /"}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.instrucciones(http, lambda s: None) == ""


def test_main_siempre_sale_con_cero_y_escribe_la_salida(tmp_path, monkeypatch):
    salida = tmp_path / "out"
    monkeypatch.setenv("GITHUB_OUTPUT", str(salida))
    monkeypatch.setenv("GARMIN_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_URL", raising=False)
    assert sub.main(["subir"]) == 0
    assert salida.read_text().strip() == "publicar_pages=true"
    assert sub.main(["instrucciones"]) == 0


# --- flujo de GitHub y despliegue ---

def test_motor_yml_pide_instrucciones_sube_y_condiciona_pages():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "motor.yml").read_text())
    pasos = wf["jobs"]["build"]["steps"]
    texto = (ROOT / ".github" / "workflows" / "motor.yml").read_text()
    assert "subir.py instrucciones" in texto and "subir.py subir" in texto
    assert wf["jobs"]["deploy"]["if"] == "needs.build.outputs.publicar == 'true'"
    por_nombre = {p.get("name") or p.get("uses"): p for p in pasos}
    for nombre in ("Construir el sitio", "Validar data.json (lista blanca de privacidad)", "actions/configure-pages@v5",
                   "actions/upload-pages-artifact@v3"):
        assert "decidir.outputs.publicar == 'true'" in por_nombre[nombre]["if"]
    assert wf["jobs"]["build"]["permissions"]["id-token"] == "write"
    assert "config.yaml" in por_nombre["Decidir si se publica Pages"]["run"]


def test_dockerignore_excluye_lo_personal():
    lineas = {l.strip() for l in (ROOT / ".dockerignore").read_text().splitlines() if l.strip() and not l.startswith("#")}
    for debe in (".env", "data/", "config.yaml", "plan/plan.json", "plan/inbody.json", "site/data.json", ".venv/", "tests/"):
        assert debe in lineas, debe


def test_dockerfile_copia_solo_lo_necesario():
    d = (ROOT / "Dockerfile").read_text()
    assert "FROM python:3.12-slim" in d and "web/requirements.txt" in d and "alembic -c web/alembic.ini upgrade head" in d
    assert "uvicorn web.app:app --host 0.0.0.0 --port ${PORT:-8080}" in d
    copias = [l.split()[1:-1] for l in d.splitlines() if l.startswith("COPY ")]
    planas = {x for c in copias for x in c}
    assert not planas & {"data/", ".env", "config.yaml", "plan/plan.json", "plan/inbody.json", "plan/", "."}
    assert {"dashboard/", "site/", "web/", "scripts/"} <= planas


@pytest.mark.skipif(not __import__("shutil").which("docker"), reason="no hay docker")
def test_imagen_no_contiene_archivos_personales():
    import subprocess
    try:
        ok = subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    if not ok:
        pytest.skip("el daemon de docker no está corriendo")
    subprocess.run(["docker", "build", "-q", "-t", "ahi-prueba", str(ROOT)], check=True, timeout=900)
    malos = ("/app/.env", "/app/config.yaml", "/app/data", "/app/plan/plan.json", "/app/plan/inbody.json",
             "/app/site/data.json")
    r = subprocess.run(["docker", "run", "--rm", "--entrypoint", "sh", "ahi-prueba", "-c",
                        "for f in " + " ".join(malos) + "; do [ -e $f ] && echo $f; done; true"],
                       capture_output=True, text=True, check=True)
    assert r.stdout.split() == [], r.stdout


def test_subir_py_escribe_el_codigo_en_el_resumen_y_no_en_el_log(tmp_path, monkeypatch, capsys):
    resumen = tmp_path / "resumen.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(resumen))
    sub._codigo_escrito.clear()
    (tmp_path / "meta.json").write_text('{"pulled_at": "2026-11-01"}')
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(403, {"error": "repo no vinculado", "codigo": "123456"}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) is True
    assert sub.instrucciones(http, lambda s: None) == ""
    t = resumen.read_text()
    assert "Tu código para Ahí la Llevas: 123456" in t and "vence en 1 h" in t and t.count("123456") == 1
    assert "123456" not in capsys.readouterr().err
    # un "código" con otra forma no se escribe
    sub._codigo_escrito.clear()
    resumen.write_text("")
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(403, {"codigo": "abc<script>"}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    sub.subir(tmp_path, ENTORNO, http, lambda s: None)
    assert resumen.read_text() == ""


# --- primera subida: config/plan/InBody del repo ---

def test_primera_subida_importa_personales_y_la_segunda_no_pisa(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    cl = ctx.cliente()
    pers = {"config": CONFIG, "plan": {"semanas": []}}
    assert subir(cl, token(ctx), paquete_chico(personales=pers)).status_code == 200
    with ctx.sesiones() as db:
        a = db.get(Ajustes, uid)
        assert a is not None and a.config["perfil"] == CONFIG["perfil"]
        assert db.get(Plan, uid) is not None
    otro = json.loads(json.dumps(CONFIG))
    otro["perfil"]["fc_max"] = 150
    assert subir(cl, token(ctx), paquete_chico(personales={"config": otro})).status_code == 200
    with ctx.sesiones() as db:
        assert db.get(Ajustes, uid).config["perfil"] == CONFIG["perfil"]


def test_subida_sin_personales_o_con_config_roto_sigue_funcionando(ctx):
    uid = usuario_amigo(ctx, repo_id=777)
    cl = ctx.cliente()
    # primero el config roto: los datos de esa misma subida no deben perderse
    assert subir(cl, token(ctx), paquete_chico(personales={"config": {"perfil": {}}})).status_code == 200
    with ctx.sesiones() as db:
        assert db.query(DatoGarmin).filter_by(usuario_id=uid).count() > 0
    assert subir(cl, token(ctx), paquete_chico()).status_code == 200
    with ctx.sesiones() as db:
        assert db.get(Ajustes, uid) is None
        assert db.query(DatoGarmin).filter_by(usuario_id=uid).count() > 0
    assert subir(cl, token(ctx), paquete_chico(personales=[1])).status_code == 422
    assert subir(cl, token(ctx), paquete_chico(personales={"config": {"fullName": "X"}})).status_code == 422


def test_paquete_personales_lee_archivos(tmp_path):
    (tmp_path / "plan").mkdir()
    (tmp_path / "config.yaml").write_text("perfil:\n  zona_horaria: America/Mexico_City\n")
    (tmp_path / "plan" / "inbody.json").write_text('{"mediciones": []}')
    assert set(paquete.personales(tmp_path)) == {"config", "inbody"}
    assert paquete.personales(tmp_path / "nada") == {}
