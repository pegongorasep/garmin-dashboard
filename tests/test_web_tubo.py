import gzip
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

import jwt
import pytest
import yaml

from dashboard import ajustes
from dashboard import build
from dashboard import paquete
from dashboard import validar
from web import calculo, importar, tubo
from web.modelos import Ajustes, Cambio, Consentimiento, DatoGarmin, Plan, Subida, Usuario, ahora
from web.privacidad import VERSION_AVISO
from ayudas import (
    auth_tubo as auth,
    CONFIG,
    crear_usuario,
    csrf_de,
    ENTORNO,
    entrar,
    HttpFalso,
    ISS,
    LLAVE,
    OTRA_LLAVE,
    paquete_chico,
    RespuestaFalsa,
    subir,
    token_tubo as token,
    usuario_amigo,
)

ROOT = Path(__file__).parent.parent
HAY_DATOS = (ROOT / "data" / "activities.json").exists() and (ROOT / "config.yaml").exists()


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

def test_un_repo_no_vinculado_no_se_asigna_por_el_owner(ctx):
    uid = usuario_amigo(ctx, owner="amigo")
    r = ctx.cliente().post("/api/tubo/instrucciones", headers=auth(token(ctx)))
    assert r.status_code == 403 and r.json() == {"error": "repo no vinculado"}
    with ctx.sesiones() as db:
        assert db.get(Usuario, uid).repo_id is None


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
        db.add(Usuario(correo="b@x.com", nombre="Ana", apellido="Prueba", github_owner="amigo"))
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
    assert r.status_code == 200 and r.json() == {"ok": True}
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


def test_subida_con_clave_prohibida_da_422(ctx):
    usuario_amigo(ctx, repo_id=777)
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
        ultima_subida = tubo.ultima_subida(db, uid)
    cfg = ajustes.cargar_config(ROOT)
    from zoneinfo import ZoneInfo
    local = ahora_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"]))
    esp = build.build(build.load_data(ROOT), build.load_plan(ROOT), {**cfg, "modo": "web", "menu": calculo.MENU, "plan_acciones": calculo.PLAN_ACCIONES, "editar_urls": calculo.editar_urls(build.load_plan(ROOT)), "idioma": "es", "plan_url": calculo.PLAN_URL, "cuerpo_nuevo": "/cuerpo/nuevo",
                      "acciones_url": "https://github.com/amigo/garmin-prueba/actions/workflows/deploy.yml", "garmin_conectado": True,
                      "garmin_ultima_subida": ultima_subida}, local)
    web["ui"].pop("repo_estado")   # depende de la hora de la última subida; se prueba aparte
    web["ui"].pop("primer_inicio")   # solo la web (E3); se prueba en test_web_primer_inicio
    web["ui"].pop("vacios", None)   # solo la web (Animaciones A1)
    web["ui"].pop("recordatorio_corrida")
    web["ui"].update(propuesta_url=None, plan_nuevo_url=None, retomar_url=None, retomar_opciones=[])   # solo la web, fuera de la caché (P3)
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

def test_onboarding_usuario_de_github_repetido(ctx):
    usuario_amigo(ctx, owner="ocupado")
    crear_usuario(ctx, "otro@x.com")
    cl = entrar(ctx, ctx.cliente(), "otro@x.com")
    with ctx.sesiones() as db:
        db.add(Consentimiento(usuario_id=2, version_aviso=VERSION_AVISO))
        db.commit()
    r = cl.post("/bienvenida/github", data={"csrf": csrf_de(cl.get("/bienvenida").text), "usuario": "OCUPADO"})
    assert r.status_code == 400 and "ya está ligado" in r.text


def test_privacidad_publica_con_lo_necesario(ctx):
    t = ctx.cliente().get("/privacidad").text
    for frase in ("consentimiento expreso", "datos sensibles", "Google Cloud", "Neon", "Resend", "GitHub", "Cloudflare",
                  "Garmin", "ARCO", "no es consejo médico", "Datos de Garmin", VERSION_AVISO, ctx.settings.admin_correo):
        assert frase.lower() in t.lower(), frase


def test_paso_a_paso_no_pide_la_key():
    """Ninguna plantilla tiene un campo (input) que pida la key de Garmin."""
    for f in (ROOT / "web" / "plantillas").glob("*.html"):
        texto = f.read_text().lower()
        assert not re.search(r"<input[^>]*(key|token|password)", texto), f.name
        assert "name=\"key\"" not in texto


# --- scripts/subir.py ---

from scripts import subir as sub


def _caido(url, **kw):
    raise sub.requests.ConnectionError("web caída")


def test_subir_con_la_web_caida_falla_visible(tmp_path):
    (tmp_path / "meta.json").write_text('{"pulled_at": "2026-11-01"}')
    http = HttpFalso(_caido, lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    pausas = []
    assert sub.subir(tmp_path, ENTORNO, http, pausas.append) == sub.FALLO
    assert len([c for c in http.llamadas if c[0] == "post"]) == 1 + sub.REINTENTOS and len(pausas) == sub.REINTENTOS
    assert sub.instrucciones(http, lambda s: None) == ""
    # sin token OIDC tampoco truena
    assert sub.subir(tmp_path, {}, http, lambda s: None) == sub.FALLO


def test_subir_ok(tmp_path):
    (tmp_path / "meta.json").write_text('{"pulled_at": "2026-11-01"}')
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(200, {"ok": True}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) == sub.SUBIDO
    _, url, kw = [c for c in http.llamadas if c[0] == "post"][0]
    assert url.endswith("/api/tubo/subida") and kw["headers"]["Content-Encoding"] == "gzip"
    assert json.loads(gzip.decompress(kw["data"]))["esquema"] == 1
    assert kw["timeout"] == 60 and "key" not in json.dumps(json.loads(gzip.decompress(kw["data"]))).lower()


def test_web_responde_403_no_vinculado(tmp_path):
    http = HttpFalso(lambda url, **kw: RespuestaFalsa(403, {"error": "repo no vinculado"}),
                     lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
    assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) == sub.NO_VINCULADO
    # otro 403 (workflow no autorizado) o un 422 sí son fallo
    for cod, err in ((403, "workflow no autorizado"), (422, "paquete no válido")):
        http = HttpFalso(lambda url, **kw: RespuestaFalsa(cod, {"error": err}),
                         lambda url, **kw: RespuestaFalsa(200, {"value": "jwt"}))
        assert sub.subir(tmp_path, ENTORNO, http, lambda s: None) == sub.FALLO
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


def test_main_subir_falla_sin_token_e_instrucciones_nunca(tmp_path, monkeypatch):
    monkeypatch.setenv("GARMIN_USER_DIR", str(tmp_path))
    monkeypatch.delenv("ACTIONS_ID_TOKEN_REQUEST_URL", raising=False)
    assert sub.main(["subir"]) == 1
    assert sub.main(["instrucciones"]) == 0


# --- flujo de GitHub y despliegue ---

def test_motor_yml_es_solo_tubo_de_datos():
    texto = (ROOT / ".github" / "workflows" / "motor.yml").read_text()
    wf = yaml.safe_load(texto)
    assert "subir.py instrucciones" in texto and "subir.py subir" in texto
    assert list(wf["jobs"]) == ["build"]
    assert wf["jobs"]["build"]["permissions"] == {"contents": "read", "id-token": "write"}
    for ya_no in ("pages", "Pages", "build.py"):
        assert ya_no not in texto, ya_no


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
    # la construcción misma falla si algo personal entró (así se revisa en cada deploy)
    texto = (ROOT / "Dockerfile").read_text()
    guarda = texto[texto.index("RUN for f in "):texto.index("; do")]
    assert {".env", "config.yaml", "data", "plan/plan.json", "plan/inbody.json", "site/data.json"} <= set(guarda.split())
    assert texto.index("RUN for f in ") > max(texto.rfind("\nCOPY "), 0) and "exit 1" in texto


@pytest.mark.skipif(not __import__("shutil").which("docker"), reason="no hay docker")
@pytest.mark.skipif(bool(__import__("os").environ.get("GITHUB_ACTIONS")), reason="en CI lo revisa el Dockerfile al construir")
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
