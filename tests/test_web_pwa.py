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
    assert 'rel="manifest"' in h and 'name="theme-color"' in h and "/actualizar.js" in h
    assert 'rel="manifest"' in (Path(__file__).parent.parent / "site" / "index.html").read_text()


def test_sw_espera_y_la_pagina_avisa(web_ctx):
    """La versión nueva no se activa sola: espera SKIP_WAITING; la página avisa y recarga una sola vez."""
    cl = web_ctx.cliente()
    sw = cl.get("/sw.js").text
    assert "SKIP_WAITING" in sw and "self.skipWaiting()" in sw and sw.count("skipWaiting()") == 1   # solo dentro del mensaje
    assert "actualizar.js" in sw
    js = cl.get("/actualizar.js")
    assert js.status_code == 200 and js.headers["content-type"].startswith("text/javascript")
    for clave in ("updatefound", "visibilitychange", "controllerchange", "SKIP_WAITING", "reg.update()"):
        assert clave in js.text, clave
    assert 'data-texto="Hay una versión nueva"' in cl.get("/entrar").text
    h = cl.get("/entrar").text
    assert 'data-cuerpo="Actualiza para ver los cambios."' in h and 'data-luego="Ahora no"' in h
    for clave in ("showModal", "dialogo-version", "descartados"):
        assert clave in js.text, clave


def test_sw_no_guarda_las_respuestas_de_grupos():
    """/api/grupos lleva datos de otras personas: el service worker solo deja pasar a la red (PROHIBIDO) y nunca lo lista como estático."""
    import re
    from pathlib import Path
    sw = (Path(__file__).resolve().parent.parent / "site" / "sw.js").read_text()
    prohibido = re.search(r"PROHIBIDO = /(.+)/;", sw).group(1)
    assert re.search(prohibido, "/api/grupos") and re.search(prohibido, "/api/grupos/3")
    assert "/api/grupos" not in sw.split("PROHIBIDO")[0]   # y no está en la lista de estáticos
    assert "PROHIBIDO.test(url.pathname)) return;" in sw    # sin respondWith: pasa directo a la red
