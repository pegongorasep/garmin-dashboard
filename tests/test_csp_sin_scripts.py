"""La CSP es `script-src 'self'`: ninguna plantilla ni página de site/ lleva scripts con código ni manejadores en línea."""
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
PAGINAS = sorted((RAIZ / "web" / "plantillas").glob("*.html")) + sorted((RAIZ / "site").glob("*.html"))
SCRIPT = re.compile(r"<script\b([^>]*)>(.*?)</script>", re.S | re.I)
MANEJADOR = re.compile(r"""<[a-z][^<>]*\son[a-z]+\s*=""", re.I)


def test_sin_scripts_en_linea():
    malos = []
    for p in PAGINAS:
        for m in SCRIPT.finditer(p.read_text(encoding="utf-8")):
            attrs = m.group(1)
            if "src=" in attrs or "application/json" in attrs:
                continue
            malos.append(p.name)
    assert not malos, f"scripts con código en línea: {sorted(set(malos))}"


def test_sin_manejadores_en_linea():
    malos = [p.name for p in PAGINAS if MANEJADOR.search(p.read_text(encoding="utf-8"))]
    assert not malos, f"atributos on*= en línea: {malos}"


def test_csp_sin_unsafe_inline_en_scripts():
    from web import app
    script = [d for d in app.CSP.split(";") if d.strip().startswith("script-src")][0]
    assert "unsafe-inline" not in script
