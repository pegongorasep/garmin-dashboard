"""Conexión C9: ui.sync, franja.js en las páginas, «Falta tu historial» y la altura fija de la franja (Chrome headless)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from test_conexion import sesion
from test_guia import conectada, gh, token   # noqa: F401
from test_conexion import gh as _gh   # noqa: F401
from test_web_tubo import ctx   # noqa: F401
from web import sincronizar
from web.modelos import Sincronizacion, Usuario

SITE = Path(__file__).resolve().parent.parent / "site"
CHROME = shutil.which("google-chrome") or shutil.which("chromium") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def test_ui_sync_por_defecto_en_build():
    from dashboard import build
    from ajustes import cargar_config
    cfg = cargar_config(None) if callable(cargar_config) else {}
    ui = build.build_ui(cfg, {"weeks": []}, [])
    assert ui["sync"] == {"puede": False, "url_autorizar": None, "historial_pendiente": False}


def test_sync_ui_sin_app_deja_el_default(ctx):
    from web import sync_web
    u = Usuario(correo="x@x.mx")
    assert sync_web.sync_ui(ctx.settings, u) is None


def test_sync_ui_con_app(ctx, gh):
    from web import sync_web
    cl, uid = conectada(ctx, gh)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.historial_pendiente = True
        db.commit()
        assert sync_web.sync_ui(ctx.settings, u) == {"puede": True, "url_autorizar": None, "historial_pendiente": True}
        u.gh_instalacion = None
        assert sync_web.sync_ui(ctx.settings, u)["url_autorizar"] == "/conectar/github?para=conectado"


def test_base_incluye_la_franja(ctx, gh):
    cl, _ = sesion(ctx)
    html = cl.get("/perfil").text
    assert '<script src="/franja.js" data-campo="' in html
    assert cl.get("/franja.js").status_code == 200


def test_falta_historial_persiste(ctx, gh):
    cl, uid = conectada(ctx, gh)
    assert cl.get("/api/sync").json()["sinc"] is None
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.historial_pendiente = True
        s, _ = sincronizar.pedir(db, u, "historial")
        sincronizar.terminar(db, s, ok=False, error="otra")
        s.terminada = s.terminada.replace(year=2020)   # hace mucho: la franja sigue mostrándolo
        db.commit()
    j = cl.get("/api/sync").json()["sinc"]
    assert j["texto"] == "Falta tu historial" and j["accion"]["post"]["tipo"] == "historial"
    with ctx.sesiones() as db:
        db.get(Usuario, uid).historial_pendiente = False
        db.commit()
    assert cl.get("/api/sync").json()["sinc"] is None


@pytest.mark.skipif(not Path(CHROME).exists() and not shutil.which(CHROME), reason="sin Chrome")
def test_franja_en_chrome(tmp_path):
    pagina = tmp_path / "p.html"
    estados = {
        "arranca": {"estado": "esperando", "texto": "Despertando tu sincronización…", "porcentaje": 5},
        "detalles": {"estado": "corriendo", "paso": "detalles", "texto": "Bajando tus kilómetros · 5 de 12" + " largo" * 30, "porcentaje": 49},
        "ok": {"estado": "ok", "texto": "✓ ¡Listo! 3 actividades nuevas", "porcentaje": 100, "terminada_hace_s": 0},
        "error": {"estado": "error", "texto": "Falta tu historial", "porcentaje": 5,
                  "accion": {"texto": "Reintentar", "post": {"url": "/api/sync", "tipo": "historial"}}}}
    pagina.write_text(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<link rel="stylesheet" href="file://{SITE}/tokens.css"><link rel="stylesheet" href="file://{SITE}/componentes.css">
<body><main>contenido</main><pre id="salida"></pre>
<script>
const viva = {json.dumps(estados["detalles"])};
window.fetch = () => Promise.resolve({{ ok: true, json: () => Promise.resolve({{ sinc: window.RESP }}) }});
window.RESP = viva;
</script>
<script src="file://{SITE}/franja.js" data-campo="x"></script>
<script>
setTimeout(() => {{
  const out = {{}};
  const f = document.querySelector(".franja");
  out.viva_visible = !!f && !f.hidden;
  out.boton_funcion = typeof Franja.empezar;
  const main0 = document.querySelector('main').getBoundingClientRect().top;
  const alturas = {{}};
  for (const [k, s] of Object.entries({json.dumps(estados)})) {{ Franja._pintar(s); alturas[k] = document.querySelector(".franja").getBoundingClientRect().height; }}
  out.alturas = alturas;
  Franja._pintar(null);
  out.empuja = document.querySelector('main').getBoundingClientRect().top - main0;
  out.reposo = document.querySelector(".franja").hidden && !document.documentElement.classList.contains("franja-on");
  document.getElementById("salida").textContent = JSON.stringify(out);
}}, 300);
</script>""")
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files",
                        "--virtual-time-budget=3000", "--window-size=390,700", "--dump-dom", f"file://{pagina}"],
                       capture_output=True, text=True, timeout=60)
    sal = r.stdout.split('<pre id="salida">')[1].split("</pre>")[0].replace("&quot;", '"')
    out = json.loads(sal)
    assert out["viva_visible"] and out["reposo"]
    assert out["boton_funcion"] == "function"
    assert len(set(out["alturas"].values())) == 1 and out["alturas"]["arranca"] >= 40, out["alturas"]
    assert out["empuja"] == 0   # flotante: el contenido no se mueve


@pytest.mark.skipif(not Path(CHROME).exists() and not shutil.which(CHROME), reason="sin Chrome")
def test_franja_en_el_encabezado(tmp_path):
    pagina = tmp_path / "e.html"
    estados = {"arranca": {"estado": "esperando", "texto": "Despertando tu sincronización…", "porcentaje": 5},
               "detalles": {"estado": "corriendo", "texto": "Bajando tus kilómetros · 5 de 12" + " largo" * 30, "porcentaje": 49},
               "ok": {"estado": "ok", "texto": "✓ ¡Listo!", "porcentaje": 100, "terminada_hace_s": 0},
               "error": {"estado": "error", "texto": "Falta tu historial", "porcentaje": 5,
                         "accion": {"texto": "Reintentar", "post": {"url": "/api/sync", "tipo": "historial"}}}}
    pagina.write_text(f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<link rel="stylesheet" href="file://{SITE}/tokens.css"><link rel="stylesheet" href="file://{SITE}/componentes.css">
<body><div id="encabezado"><header class="encabezado"><div class="encabezado-fila">Titulo</div><p class="act"><span>Actualizado hace 1 h</span> · <a href="#">jalar datos</a></p></header></div>
<main>contenido</main><pre id="salida"></pre>
<script>window.fetch = () => Promise.resolve({{ ok: true, json: () => Promise.resolve({{ sinc: null }}) }});</script>
<script src="file://{SITE}/franja.js" data-campo="x"></script>
<script>
setTimeout(() => {{
  const enc = () => document.querySelector(".encabezado").getBoundingClientRect().height;
  const act = () => document.querySelector(".act").getBoundingClientRect().height;
  const main0 = document.querySelector("main").getBoundingClientRect().top;
  const out = {{ enc0: enc(), act0: act(), enc: {{}}, act: {{}}, flota: !!document.querySelector(".franja") }};
  for (const [k, s] of Object.entries({json.dumps(estados)})) {{ Franja._pintar(s); out.enc[k] = enc(); out.act[k] = act(); }}
  out.sync = document.querySelector(".encabezado").classList.contains("sync-on");
  out.mueve = document.querySelector("main").getBoundingClientRect().top - main0;
  Franja._pintar(null);
  out.vuelve = enc() === out.enc0 && !document.querySelector(".encabezado").classList.contains("sync-on");
  document.getElementById("salida").textContent = JSON.stringify(out);
}}, 300);
</script>""")
    r = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--allow-file-access-from-files",
                        "--virtual-time-budget=3000", "--window-size=390,700", "--dump-dom", f"file://{pagina}"],
                       capture_output=True, text=True, timeout=60)
    out = json.loads(r.stdout.split('<pre id="salida">')[1].split("</pre>")[0].replace("&quot;", '"'))
    assert not out["flota"] and out["sync"] and out["vuelve"] and out["mueve"] == 0, out
    assert set(out["enc"].values()) == {out["enc0"]} and set(out["act"].values()) == {out["act0"]}, out


def _accion_sync(ui, viva=False):
    """Corre accionSync de site/vistas.js en node con h/T/window de mentiras; devuelve lo que pinta."""
    src = (SITE / "vistas.js").read_text()
    i = src.index("function accionSync(u)")
    fn = src[i:src.index("\n}\n", i) + 3]
    js = ("const h=(t,a,x)=>({t,a,x}); const T=k=>k; const location={href:'/'}; let llamado=null;\n"
          f"const window={{Franja:{{viva:()=>{str(viva).lower()},empezar:t=>{{llamado=t}}}}}};\n{fn}\n"
          f"const r=accionSync({json.dumps(ui)}); if(r&&r.a.onclick)r.a.onclick();\n"
          "console.log(JSON.stringify({r:r&&{t:r.t,id:r.a.id,href:r.a.href,disabled:r.a.disabled},llamado,href:location.href}));")
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="sin node")
def test_encabezado_accion_sync():
    sin = _accion_sync({"acciones_url": "https://g/x", "sync": {"puede": False, "url_autorizar": None}})
    assert sin["r"]["id"] == "acciones-link" and sin["llamado"] is None
    puede = _accion_sync({"acciones_url": "https://g/x", "sync": {"puede": True, "url_autorizar": None}})
    assert puede["r"]["id"] == "sync-btn" and puede["llamado"] == "normal" and puede["href"] == "/"
    auto = _accion_sync({"acciones_url": "https://g/x", "sync": {"puede": False, "url_autorizar": "/conectar/github?para=conectado"}})
    assert auto["r"]["id"] == "sync-btn" and auto["llamado"] is None and auto["href"] == "/conectar/github?para=conectado"
