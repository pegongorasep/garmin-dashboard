"""F7c: PWA instalable."""
import json
from pathlib import Path


def test_manifest_valido_con_iconos(web_ctx):
    r = web_ctx.cliente().get("/manifest.webmanifest")
    assert r.status_code == 200 and "manifest+json" in r.headers["content-type"]
    m = json.loads(r.text)
    assert m["name"] == "Ahí la Llevas" and m["display"] == "standalone"
    assert {"192x192", "512x512"} <= {i["sizes"] for i in m["icons"]}
    assert any(i["purpose"] == "maskable" for i in m["icons"])
    for i in m["icons"]:
        png = web_ctx.cliente().get(i["src"])
        assert png.status_code == 200 and png.content.startswith(b"\x89PNG")


def test_sw_y_paginas(web_ctx):
    cl = web_ctx.cliente()
    r = cl.get("/sw.js")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/javascript")
    for ruta in ("/api", "/oauth", "/mcp", "/admin"):
        assert ruta.strip("/") in r.text
    assert cl.get("/apple-touch-icon.png").status_code == 200
    h = cl.get("/entrar").text
    assert 'rel="manifest"' in h and 'name="theme-color"' in h and "serviceWorker" in h
    assert 'rel="manifest"' in (Path(__file__).parent.parent / "site" / "index.html").read_text()
