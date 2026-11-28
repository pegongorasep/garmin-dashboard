"""web/deps.py: cada app lee su propio app.state (dos apps en un proceso no se mezclan)."""
from fastapi.testclient import TestClient

from web.app import crear_app
from web.config import Settings
from web.db import crear_motor
from web.modelos import Base


def _app(secreto):
    s = Settings(database_url="sqlite://", secret_key=secreto, base_url="https://x.test", admin_correo="a@example.com")
    motor = crear_motor(s.database_url)
    Base.metadata.create_all(motor)
    return crear_app(s, motor, enviar=lambda *a: None)


def test_dos_apps_no_se_mezclan():
    a, b = _app("secreto-a"), _app("secreto-b")
    assert a.state.settings.secret_key == "secreto-a" and b.state.settings.secret_key == "secreto-b"
    ca = TestClient(a, base_url="https://x.test", follow_redirects=False)
    cb = TestClient(b, base_url="https://x.test", follow_redirects=False)
    ca.get("/entrar")
    csrf_a = ca.cookies.get("csrf") or next(iter(ca.cookies.values()))
    # el token CSRF (cookie) de la app A no vale en la app B: sus secretos son distintos
    from web import auth
    campo_a = auth.campo_csrf("secreto-a", csrf_a)
    cb.cookies.set(auth.COOKIE_CSRF, csrf_a)
    assert cb.post("/coach/dar", data={"csrf": campo_a, "correo": "x@example.com"}).status_code == 403
    ca.cookies.set(auth.COOKIE_CSRF, csrf_a)
    assert ca.post("/coach/dar", data={"csrf": campo_a, "correo": "x@example.com"}).status_code == 303   # CSRF ok, sin sesión -> /entrar
