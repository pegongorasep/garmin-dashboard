from pathlib import Path

import pytest


from ayudas import Falsa, ConSecretos, jwks_falso
from dashboard import i18n

i18n.ESTRICTO = True   # en pruebas, una clave que falta lanza error

ROOT = Path(__file__).parent.parent


@pytest.fixture
def web_ctx():
    """App de la web con SQLite en memoria, correo falso (lista `enviados`) y cliente HTTPS."""
    from fastapi.testclient import TestClient

    from web.app import crear_app
    from web.config import Settings
    from web.db import crear_motor, crear_sesiones
    from web.modelos import Base

    class Ctx:
        pass

    c = Ctx()
    c.settings = Settings(database_url="sqlite://", secret_key="prueba-secreta", base_url="https://ahilallevas.test",
                          admin_correo="pedro@example.com")
    c.motor = crear_motor(c.settings.database_url)
    Base.metadata.create_all(c.motor)
    c.sesiones = crear_sesiones(c.motor)
    c.enviados = []
    c.app = crear_app(c.settings, c.motor, enviar=lambda s, para, asunto, texto: c.enviados.append((para, asunto, texto)))

    def cliente():
        return TestClient(c.app, base_url="https://ahilallevas.test", follow_redirects=False)
    c.cliente = cliente
    return c


@pytest.fixture
def ctx(web_ctx):
    """web_ctx con las llaves públicas de GitHub (JWKS) falsas, para el token OIDC del tubo."""
    web_ctx.app.state.jwks_fetch = lambda url: jwks_falso()
    web_ctx.app.state.__dict__.pop("jwks_cache", None)
    return web_ctx


@pytest.fixture
def gh(ctx):
    """App de GitHub falsa (`Falsa`) ya instalada en la web."""
    ctx.settings.github_app_id = ctx.settings.github_app_slug = ctx.settings.github_app_client_id = "x"
    ctx.settings.github_app_client_secret = ctx.settings.github_app_private_key = "x"
    f = Falsa()
    ctx.app.state.github_app = f
    return f


@pytest.fixture
def gh_con_secretos(gh, ctx):
    f = ConSecretos()
    ctx.app.state.github_app = f
    return f
