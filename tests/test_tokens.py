"""site/tokens.css sale de diseno/tokens.json y todo el CSS/JS usa solo variables que existen."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
from scripts import tokens

USAN = [*ROOT.glob("site/*.css"), *ROOT.glob("site/*.js"), *ROOT.glob("web/estaticos/*.css"),
        *ROOT.glob("web/plantillas/*.html")]


def test_tokens_css_al_dia():
    assert tokens.main(["--check"]) == 0, "corre: python scripts/tokens.py"


def test_referencias_resueltas_y_tema_por_tema():
    css = (ROOT / "site/tokens.css").read_text()
    assert "{" not in "".join(re.findall(r"--[\w-]+: ([^;]*);", css))   # sin "{accent}" literal
    assert len(re.findall(r"^\s*color-scheme: dark;", css, re.M)) == 1 and len(re.findall(r"^\s*color-scheme: light;", css, re.M)) == 2
    t = json.loads((ROOT / "diseno/tokens.json").read_text())
    assert tokens.variables(t, "oscuro")["focus"] == tokens.variables(t, "oscuro")["accent"]


def test_toda_variable_usada_existe():
    css = (ROOT / "site/tokens.css").read_text()
    definidas = set(re.findall(r"--([\w-]+):", css))
    faltan = {}
    for f in USAN:
        texto = f.read_text()
        locales = set(re.findall(r"--([\w-]+)\s*:", texto)) | set(re.findall(r'setProperty\("--([\w-]+)"', texto))
        for v in re.findall(r"var\(--([\w-]+)", texto):
            if v not in definidas and v not in locales and not re.fullmatch(r"g", v):   # var(--g${n}) en app.js
                faltan.setdefault(f.name, set()).add(v)
    assert not faltan, faltan


def test_pie_idioma_es_selector():
    from web.app import pie_sitio
    h = pie_sitio("en", "tok", "/x")
    assert '<select id="pie-idioma-sel" name="idioma">' in h and '<option value="en" lang="en" selected>' in h
    assert "<noscript>" in h and 'name="siguiente" value="/x"' in h and "aria-current" not in h
