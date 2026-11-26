import sys
from pathlib import Path

import pytest

import web  # noqa: F401,E402  (pone dashboard/ y plan/ en sys.path)

import i18n  # noqa: E402

i18n.ESTRICTO = True   # en pruebas, una clave que falta lanza error

ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


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
