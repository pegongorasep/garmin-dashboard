import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from alembic import command
from alembic.config import Config

import ajustes
import build
import validar
from web import calculo, cli, datos, importar
from web.modelos import Ajustes, Base, Consentimiento, CacheData, DatoGarmin, Usuario
from web.privacidad import VERSION_AVISO

ROOT = Path(__file__).parent.parent
HAY_DATOS = (ROOT / "data" / "activities.json").exists() and (ROOT / "config.yaml").exists()
AHORA_UTC = datetime(2026, 11, 25, 18, 0)   # 12:00 en Mérida


def usuario_pedro(ctx):
    with ctx.sesiones() as db:
        u = Usuario(correo="pedro@example.com", nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        return u.id


def esperado(modo_web: bool):
    cfg = ajustes.cargar_config(ROOT)
    if modo_web:
        cfg = {**cfg, "modo": "web", "menu": calculo.MENU,
               "plan_acciones": calculo.PLAN_ACCIONES, "editar_urls": calculo.editar_urls(build.load_plan(ROOT)), "idioma": "es",
               "plan_url": calculo.PLAN_URL, "cuerpo_nuevo": "/cuerpo/nuevo"}
    ahora = AHORA_UTC.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(cfg["timezone"]))
    return build.build(build.load_data(ROOT), build.load_plan(ROOT), cfg, ahora)


def norm(d, a_pages=False):
    texto = json.dumps(d, sort_keys=True, ensure_ascii=False)
    if a_pages:   # los textos que cambian en modo web (el plan los nombra)
        texto = texto.replace("(desde Ajustes)", "(con /ajustar)").replace("vayas a Ajustes", "corras /ajustar") \
                     .replace("Ve a Ajustes para", "Corre /ajustar para")
    return json.loads(texto)


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_dashboard_de_pedro_importado_igual_al_de_build(web_ctx):
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT, salt="42")
        web = calculo.calcular(db, db.get(Usuario, uid), AHORA_UTC)
        assert validar.problemas(web) == []
        assert "serie" not in json.dumps(web)
    # diferencias permitidas: ui.menu (lista de la web), ui.repo_estado (None si no hay repo) y los textos de /ajustar
    assert web["ui"].pop("repo_estado") is None
    esp = norm(esperado(modo_web=True))
    assert norm(web) == esp
    pages, web_n = norm(esperado(modo_web=False)), norm(web, a_pages=True)
    # las dos mandan "idioma" siempre
    for d in (pages, web_n):
        for k in ("menu", "plan_acciones", "editar_urls", "plan_url", "repetir_url", "cuerpo_nuevo"):
            d["ui"].pop(k)
    assert pages == web_n


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_el_orden_de_las_filas_guardadas_no_cambia_el_resultado(web_ctx):
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT, salt="42")
        u = db.get(Usuario, uid)
        antes = norm(calculo.calcular(db, u, AHORA_UTC))
        cache = db.get(CacheData, uid)
        db.delete(cache)
        filas = db.query(DatoGarmin).all()
        contenidos = [(f.tipo, f.clave, f.contenido) for f in filas]
        random.Random(1).shuffle(contenidos)
        for f in filas:
            db.delete(f)
        db.commit()
        for tipo, clave, c in contenidos:
            db.add(DatoGarmin(usuario_id=uid, tipo=tipo, clave=clave, contenido=c))
        db.commit()
        assert norm(calculo.calcular(db, u, AHORA_UTC)) == antes


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_cache_se_reusa_y_se_invalida(web_ctx):
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT, salt="42")
        u = db.get(Usuario, uid)
        calculo.calcular(db, u, AHORA_UTC)
        h1 = db.get(CacheData, uid).huella
        calculo.calcular(db, u, AHORA_UTC)
        assert db.get(CacheData, uid).huella == h1
        # cambia el día local -> otra huella
        calculo.calcular(db, u, datetime(2026, 11, 26, 18, 0))
        assert db.get(CacheData, uid).huella != h1
        # una subida nueva -> otra huella
        h2 = db.get(CacheData, uid).huella
        d = db.query(DatoGarmin).filter_by(usuario_id=uid, tipo="meta").one()
        d.contenido = {**d.contenido, "pulled_at": "2030-01-01"}
        d.actualizado = datetime(2030, 1, 1)
        db.commit()
        calculo.calcular(db, u, datetime(2026, 11, 26, 18, 0))
        assert db.get(CacheData, uid).huella != h2


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_ruta_data_json_de_la_web_sirve_el_del_usuario(web_ctx):
    from test_web_cuentas import csrf_de, liga_de  # noqa: F401
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT, salt="42")
        db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.commit()
    from test_web_cuentas import entrar
    cl = entrar(web_ctx, web_ctx.cliente(), "pedro@example.com")
    assert "<title>" in cl.get("/").text
    r = cl.get("/data.json")
    assert r.status_code == 200 and validar.problemas(r.json()) == []
    assert r.json()["ui"]["menu"] == calculo.MENU


def test_data_con_claves_prohibidas_no_se_sirve(web_ctx, monkeypatch):
    from test_web_cuentas import CONFIG, entrar
    with web_ctx.sesiones() as db:
        u = Usuario(correo="a@x.com", nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        db.add(Ajustes(usuario_id=u.id, config=CONFIG))
        db.commit()
    monkeypatch.setattr(build, "build", lambda *a, **k: {**norm(esperado_vacio()), "activityName": "x"})
    cl = entrar(web_ctx, web_ctx.cliente(), "a@x.com")
    r = cl.get("/data.json")
    assert r.status_code == 500 and "activityName" not in r.text


def esperado_vacio():
    return {}


def test_guardar_paquete_es_upsert_y_no_borra(web_ctx):
    pq = {"esquema": 1, "motor": "x", "archivos": {
        "daily": {"daily_summaries": [{"calendarDate": "2026-11-01", "heartRate": {"restingValue": 60}}],
                  "sleep": [], "hrv": []},
        "activities": [{"id": "a1", "startTimeLocal": "2026-11-01 07:00:00", "activityType": {"typeKey": "running"}}],
        "activity_details": {"a1": {"rpe": 3.0}}, "hr_zones": [], "historial_corridas": [], "meta": {}}}
    with web_ctx.sesiones() as db:
        u = Usuario(correo="a@x.com", nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        r1 = datos.guardar_paquete(db, u.id, pq)
        assert r1["actividad"] == {"nuevos": 1, "cambiados": 0}
        r2 = datos.guardar_paquete(db, u.id, pq)
        assert r2["actividad"] == {"nuevos": 0, "cambiados": 0} and db.query(DatoGarmin).count() == 3
        pq["archivos"]["activity_details"]["a1"]["rpe"] = 5.0
        pq["archivos"]["activities"] = []   # un paquete sin esa actividad no la borra
        assert datos.guardar_paquete(db, u.id, pq)["detalle"]["cambiados"] == 1
        assert db.query(DatoGarmin).filter_by(tipo="actividad").count() == 1
        assert datos.leer_archivos(db, u.id)["details"]["a1"]["rpe"] == 5.0


def test_cli_invitar_crear_admin_importar(web_ctx, capsys, tmp_path):
    args = dict(settings=web_ctx.settings, motor=web_ctx.motor)
    assert cli.main(["crear-admin", "Pedro@Example.com"], **args) == 0
    assert cli.main(["invitar", "--nota", "Adrián"], **args) == 0
    liga = capsys.readouterr().out.strip().splitlines()[-1]
    assert liga.startswith("https://ahilallevas.test/invitacion/")
    assert "Adrián" in web_ctx.cliente().get(liga.removeprefix("https://ahilallevas.test")).text
    with web_ctx.sesiones() as db:
        assert db.query(Usuario).filter_by(correo="pedro@example.com", es_admin=True).count() == 1
    assert cli.main(["importar", "nadie@x.com", str(tmp_path)], **args) == 1
    (tmp_path / "config.yaml").write_text((ROOT / "tests" / "fixtures" / "config.yaml").read_text())
    assert cli.main(["importar", "pedro@example.com", str(tmp_path)], **args) == 0
    with web_ctx.sesiones() as db:
        assert db.query(Ajustes).count() == 1


def test_migracion_inicial_crea_las_mismas_tablas_que_los_modelos(tmp_path):
    db = tmp_path / "m.db"
    cfg = Config(str(ROOT / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    command.upgrade(cfg, "head")
    tablas = {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}
    assert set(Base.metadata.tables) <= tablas


def test_migracion_avisos_ocultos_sube_y_baja(tmp_path):
    db = tmp_path / "m.db"
    cfg = Config(str(ROOT / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    tablas = lambda: {r[0] for r in sqlite3.connect(db).execute("select name from sqlite_master where type='table'")}  # noqa: E731
    command.upgrade(cfg, "head")
    assert "avisos_ocultos" in tablas()
    command.downgrade(cfg, "0012")
    assert "avisos_ocultos" not in tablas()
    command.upgrade(cfg, "head")
    assert "avisos_ocultos" in tablas()


def test_settings_exigen_secret_key_fuera_de_localhost_y_arreglan_la_url_de_postgres():
    from web.config import Settings
    with pytest.raises(RuntimeError):
        Settings(base_url="https://ahilallevas.com")
    s = Settings(base_url="http://localhost:8000", database_url="postgres://u:p@h/db")
    assert s.database_url.startswith("postgresql+psycopg://") and not s.cookie_segura
    assert Settings(base_url="https://ahilallevas.com/", secret_key="x").cookie_segura
    assert s.oidc_audience == "http://localhost:8000"


@pytest.mark.skipif(not HAY_DATOS, reason="no hay datos personales")
def test_semanas_del_plan_web_y_build_traen_las_mismas_claves(web_ctx):
    """Las palomitas del Plan salen de plan.semanas[]: la web debe traer las mismas claves que build."""
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        importar.importar_carpeta(db, db.get(Usuario, uid), ROOT, salt="42")
        web = calculo.calcular(db, db.get(Usuario, uid), AHORA_UTC)
    esp = esperado(modo_web=True)["plan"]["semanas"]
    assert [sorted(w) for w in web["plan"]["semanas"]] == [sorted(w) for w in esp]
    assert any("cumplimiento" in w for w in web["plan"]["semanas"]) and all("estados" in w for w in web["plan"]["semanas"] if "progreso" not in w or "cumplimiento" in w)


def test_la_huella_del_cache_incluye_el_codigo_del_motor(web_ctx, monkeypatch):
    """Tras un deploy el data.json en caché (calculado con el código viejo) no debe servirse: la huella cambia con el código."""
    uid = usuario_pedro(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        h1 = calculo.huella(db, u, "2026-11-26")
        monkeypatch.setattr(calculo, "CODIGO", "otro")
        assert calculo.huella(db, u, "2026-11-26") != h1


def test_plan_url_con_prefijo_del_coach():
    from web import calculo
    s = {"ui": {"menu": [], "plan_acciones": [], "plan_url": calculo.PLAN_URL, "editar_urls": {}}}
    assert calculo.con_prefijo(s, "/a/7")["ui"]["plan_url"] == "/a/7/plan"
    assert calculo.con_prefijo(s, "")["ui"]["plan_url"] == "/plan"


def test_migracion_compartir_sube_y_baja_y_los_usuarios_quedan_en_si(tmp_path):
    db = tmp_path / "m.db"
    cfg = Config(str(ROOT / "web" / "alembic.ini"))
    cfg.cmd_opts = type("O", (), {"x": [f"url=sqlite:///{db}"]})()
    cols = lambda: {r[1] for r in sqlite3.connect(db).execute("pragma table_info(usuarios)")}  # noqa: E731
    command.upgrade(cfg, "0013")
    con = sqlite3.connect(db)
    con.execute("insert into usuarios (correo, es_admin, creado, migrado, sensor, sin_plan) values ('v@x.com', 0, '2026-01-01', 0, 'banda', 0)")
    con.commit()
    con.close()
    command.upgrade(cfg, "head")
    assert {"compartir_actividades", "compartir_plan"} <= cols()
    assert sqlite3.connect(db).execute("select compartir_actividades, compartir_plan from usuarios").fetchone() == (1, 1)
    command.downgrade(cfg, "0013")
    assert not {"compartir_actividades", "compartir_plan"} & cols()
    command.upgrade(cfg, "head")
    assert "compartir_plan" in cols()
