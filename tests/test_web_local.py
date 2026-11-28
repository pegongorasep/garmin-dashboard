"""`./run_web.sh`: sin red ni gcloud (los comandos son falsos y la «producción» es un SQLite temporal)."""
import os
import sqlite3
import subprocess

import pytest

from scripts import web_local as wl

CLAVE = "clave-supersecreta-123"
CADENA = f"postgresql://usuario:{CLAVE}@base.invalid/ahi"


@pytest.fixture
def falso(monkeypatch):
    """Sustituye gh/gcloud y el arranque del servidor; anota lo que se habría hecho."""
    class F:
        secreto, codigo, stderr = CADENA + "\n", 0, ""
        comandos, servido, entorno = [], [], {}

    f = F()
    f.comandos, f.servido, f.entorno = [], [], {}

    def run(comando, **kw):
        f.comandos.append(comando)
        salida = "mi-proyecto\n" if comando[0] == "gh" else f.secreto
        return subprocess.CompletedProcess(comando, f.codigo, stdout=salida, stderr=f.stderr)

    def servir(puerto):
        f.servido.append(puerto)
        f.entorno = dict(os.environ)

    monkeypatch.setattr(wl.subprocess, "run", run)
    monkeypatch.setattr(wl, "servir", servir)
    antes = dict(os.environ)
    for k in ("GCP_PROYECTO", "PORT"):
        os.environ.pop(k, None)
    yield f
    os.environ.clear()
    os.environ.update(antes)


def sin_clave(capsys) -> str:
    salida = capsys.readouterr()
    texto = salida.out + salida.err
    assert CLAVE not in texto and "base.invalid" not in texto
    return texto


def test_revision_distinta_aborta(falso, monkeypatch, capsys):
    monkeypatch.setattr(wl, "revision_en_base", lambda cadena: {"0001"})
    assert wl.main([]) == 1
    texto = sin_clave(capsys)
    assert "0001" in texto and "--temporal" in texto
    assert falso.servido == []
    assert all("alembic" not in c for c in falso.comandos)   # nunca migra


def test_revision_se_lee_sin_escribir(tmp_path):
    base = tmp_path / "prod.db"
    with sqlite3.connect(base) as c:
        c.execute("CREATE TABLE alembic_version (version_num TEXT)")
        c.execute("INSERT INTO alembic_version VALUES ('0003')")
    antes = base.read_bytes()
    assert wl.revision_en_base(f"sqlite:///{base}") == {"0003"}
    assert base.read_bytes() == antes
    assert len(wl.revision_local()) == 1


def test_sin_tabla_de_revision_aborta(tmp_path):
    with pytest.raises(wl.Aborta):
        wl.revision_en_base(f"sqlite:///{tmp_path / 'vacia.db'}")


@pytest.mark.parametrize("secreto", ["", "\n", "sqlite:///web/dev.db", f"basura {CLAVE}"])
def test_sin_cadena_aborta(falso, capsys, secreto):
    falso.secreto = secreto
    assert wl.main([]) == 1
    assert "No se arranca" in sin_clave(capsys)
    assert falso.servido == []


def test_gcloud_falla_no_muestra_stdout(falso, capsys):
    falso.codigo, falso.stderr = 1, f"ERROR: sin permiso\ndetalle {CADENA}"
    os.environ["GCP_PROYECTO"] = "mi-proyecto"
    assert wl.main([]) == 1
    assert "sin permiso" in sin_clave(capsys)
    assert falso.servido == []


def test_sin_gcloud_aborta(falso, monkeypatch, capsys):
    def run(comando, **kw):
        raise FileNotFoundError(comando[0])
    monkeypatch.setattr(wl.subprocess, "run", run)
    os.environ["GCP_PROYECTO"] = "mi-proyecto"
    assert wl.main([]) == 1
    assert "gcloud" in capsys.readouterr().err
    assert falso.servido == []


@pytest.mark.parametrize("cadena", [CADENA, f"postgresql://usuario:{CLAVE}@base.invalid:puerto/ahi"])
def test_error_de_la_base_no_muestra_la_cadena(falso, monkeypatch, capsys, cadena):
    import sqlalchemy

    def truena(url, **kw):
        raise ValueError(f"no se pudo con {url}")
    monkeypatch.setattr(sqlalchemy, "create_engine", truena)
    falso.secreto = cadena
    assert wl.main([]) == 1
    assert "ValueError" in sin_clave(capsys)


def test_error_inesperado_sin_traceback(falso, monkeypatch, capsys):
    monkeypatch.setattr(wl, "revision_en_base", lambda cadena: wl.revision_local())

    def truena(puerto):
        raise RuntimeError(CADENA)
    monkeypatch.setattr(wl, "servir", truena)
    assert wl.main([]) == 1
    assert "RuntimeError" in sin_clave(capsys)


def test_produccion_arranca_sin_llaves_y_sin_mostrar_la_cadena(falso, monkeypatch, capsys):
    monkeypatch.setattr(wl, "revision_en_base", lambda cadena: wl.revision_local())
    os.environ.update({"DATABASE_URL": "sqlite:///heredada.db", "BASE_URL": "https://ahilallevas.com", "PORT": "8123",
                       "RESEND_API_KEY": "x", "GITHUB_APP_ID": "1", "GITHUB_APP_PRIVATE_KEY": "x",
                       "GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "x"})
    assert wl.main([]) == 0
    texto = sin_clave(capsys)
    assert "PRODUCCIÓN" in texto and "es real" in texto and "http://localhost:8123" in texto
    assert falso.servido == [8123]
    e = falso.entorno
    assert e["DATABASE_URL"] == CADENA and e["BASE_URL"] == "http://localhost:8123"
    assert not [k for k in e if k == "RESEND_API_KEY" or k.startswith(("GITHUB_APP_", "GOOGLE_"))]
    assert all(CLAVE not in a for c in falso.comandos for a in c)
    assert falso.comandos[1][:4] == ["gcloud", "secrets", "versions", "access"]


def test_temporal_no_usa_el_database_url_heredado(falso, monkeypatch, capsys):
    migrado = {}
    monkeypatch.setattr(wl, "migrar_temporal", migrado.update)
    os.environ.update({"DATABASE_URL": CADENA, "RESEND_API_KEY": "x"})
    assert wl.main(["--temporal"]) == 0
    esperado = f"sqlite:///{wl.BASE_TEMPORAL}"
    assert migrado["DATABASE_URL"] == esperado == falso.entorno["DATABASE_URL"]
    assert "RESEND_API_KEY" not in falso.entorno
    assert falso.comandos == []   # ni gh ni gcloud
    texto = sin_clave(capsys)
    assert "TEMPORAL" in texto and "invitar" in texto


def test_en_local_no_se_usa_la_cache(web_ctx, monkeypatch):
    from web import calculo
    from web.modelos import CacheData, Usuario

    assert wl.entorno_web({}, 8000, CADENA)["AHI_SIN_CACHE"] == "1"
    monkeypatch.setenv("AHI_SIN_CACHE", "1")
    with web_ctx.sesiones() as db:
        u = Usuario(correo="local@example.com", nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        assert "ui" in calculo._calcular_cacheado(db, u)
        assert db.get(CacheData, u.id) is None   # no escribe
        db.add(CacheData(usuario_id=u.id, contenido={"viejo": 1}, huella=calculo.huella(db, u, "x")))
        db.commit()
        assert "viejo" not in calculo._calcular_cacheado(db, u)   # ni lee
        assert db.get(CacheData, u.id).contenido == {"viejo": 1}
