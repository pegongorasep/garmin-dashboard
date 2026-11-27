import json
import time
from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from web.config import Settings, desde_entorno
from web.github_app import GitHubApp, GitHubError

_k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = _k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                       serialization.NoEncryption()).decode()
PUB = _k.public_key()


def _s(**kw):
    d = dict(github_app_id="123", github_app_slug="mi-app", github_app_client_id="cid",
             github_app_client_secret="sec", github_app_private_key=PEM)
    d.update(kw)
    return Settings(**d)


def _app(handler):
    return GitHubApp(_s(), transport=httpx.MockTransport(handler))


def _exp(min_):
    return (datetime.now(timezone.utc) + timedelta(minutes=min_)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_jwt_app():
    t = GitHubApp(_s()).jwt_app()
    d = jwt.decode(t, PUB, algorithms=["RS256"], options={"verify_iat": False})
    assert d["iss"] == "123"
    assert abs(d["iat"] - (time.time() - 60)) < 5 and abs(d["exp"] - (time.time() + 540)) < 5


def test_token_instalacion_cache_y_renueva():
    llamadas = []

    def h(req):
        llamadas.append(req)
        assert req.url.path == "/app/installations/7/access_tokens"
        assert req.headers["authorization"].startswith("Bearer ")
        assert req.headers["x-github-api-version"] == "2022-11-28"
        return httpx.Response(201, json={"token": f"t{len(llamadas)}", "expires_at": _exp(60)})
    app = _app(h)
    assert app.token_instalacion(7) == "t1" and app.token_instalacion(7) == "t1"
    assert len(llamadas) == 1
    app._tokens[7] = ("viejo", time.time() + 100)   # vence en <5 min: se renueva
    assert app.token_instalacion(7) == "t2"


def _con_token(rutas):
    def h(req):
        if req.url.path.endswith("/access_tokens"):
            return httpx.Response(201, json={"token": "TK", "expires_at": _exp(60)})
        assert req.headers["authorization"] == "token TK"
        return rutas(req)
    return _app(h)


def test_url_instalar():
    assert GitHubApp(_s()).url_instalar("a b") == "https://github.com/apps/mi-app/installations/new?state=a%20b"


def test_token_y_instalaciones_de_usuario():
    def h(req):
        if req.url.host == "github.com":
            assert req.url.path == "/login/oauth/access_token"
            assert req.headers["accept"] == "application/json"
            assert b"code=C1" in req.content and b"client_id=cid" in req.content
            return httpx.Response(200, json={"access_token": "U"})
        assert req.url.path == "/user/installations" and req.headers["authorization"] == "Bearer U"
        return httpx.Response(200, json={"installations": [{"id": 5}, {"id": 9}]})
    app = _app(h)
    assert app.instalaciones_del_usuario(app.token_de_usuario("C1")) == [5, 9]


def test_token_de_usuario_malo():
    app = _app(lambda r: httpx.Response(200, json={"error": "bad_verification_code"}))
    with pytest.raises(GitHubError):
        app.token_de_usuario("x")


def test_repos_secretos():
    def r(req):
        if req.url.path == "/installation/repositories":
            return httpx.Response(200, json={"repositories": [
                {"id": 1, "full_name": "a/b", "private": True, "default_branch": "main", "x": 1}]})
        assert req.url.path == "/repos/a/b/actions/secrets"
        return httpx.Response(200, json={"secrets": [{"name": "PERSONAL_API_KEY", "updated_at": "2026-01-01T00:00:00Z",
                                                      "created_at": "z"}]})
    app = _con_token(r)
    assert app.repos_de_instalacion(7) == [{"id": 1, "full_name": "a/b", "private": True, "default_branch": "main"}]
    assert app.secretos(7, "a/b") == [{"name": "PERSONAL_API_KEY", "updated_at": "2026-01-01T00:00:00Z"}]


def test_disparar_corridas_jobs():
    def r(req):
        p = req.url.path
        if p.endswith("/dispatches"):
            assert req.method == "POST" and json.loads(req.content) == {"ref": "main"}
            assert p == "/repos/a/b/actions/workflows/deploy.yml/dispatches"
            return httpx.Response(204)
        if p.endswith("/runs"):
            assert req.url.params["created"] == ">=2026-01-01T00:00:00Z"
            return httpx.Response(200, json={"workflow_runs": [
                {"id": 3, "status": "queued", "conclusion": None, "event": "workflow_dispatch",
                 "created_at": "t", "otro": 1}]})
        assert p == "/repos/a/b/actions/runs/3/jobs"
        return httpx.Response(200, json={"jobs": [{"id": 8, "name": "j", "status": "completed", "conclusion": "success",
                                                   "steps": [{"name": "s", "status": "completed",
                                                              "conclusion": "success", "number": 1}]}]})
    app = _con_token(r)
    assert app.disparar(7, "a/b", "main") is True
    assert app.corridas(7, "a/b", desde="2026-01-01T00:00:00Z")[0] == {
        "id": 3, "status": "queued", "conclusion": None, "event": "workflow_dispatch", "created_at": "t"}
    assert app.jobs(7, "a/b", 3)[0]["steps"] == [{"name": "s", "status": "completed", "conclusion": "success"}]


@pytest.mark.parametrize("codigo", [403, 404])
def test_errores_distinguibles(codigo):
    app = _con_token(lambda req: httpx.Response(codigo, json={"message": "no"}))
    with pytest.raises(GitHubError) as e:
        app.secretos(7, "a/b")
    assert e.value.status == codigo


def test_app_github(monkeypatch):
    assert _s().app_github
    assert not _s(github_app_slug="").app_github
    assert not Settings().app_github
    for k in ("ID", "SLUG", "CLIENT_ID", "CLIENT_SECRET", "PRIVATE_KEY"):
        monkeypatch.delenv(f"GITHUB_APP_{k}", raising=False)
    assert not desde_entorno().app_github
    monkeypatch.setenv("GITHUB_APP_ID", "1")
    monkeypatch.setenv("GITHUB_APP_SLUG", "s")
    monkeypatch.setenv("GITHUB_APP_CLIENT_ID", "c")
    monkeypatch.setenv("GITHUB_APP_CLIENT_SECRET", "x")
    monkeypatch.setenv("GITHUB_APP_PRIVATE_KEY", "-----BEGIN-----\\nabc\\n-----END-----")
    s = desde_entorno()
    assert s.app_github and s.github_app_private_key == "-----BEGIN-----\nabc\n-----END-----"
