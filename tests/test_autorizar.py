"""C9d: el diálogo «Autoriza una vez» antes de mandar a GitHub (Ajustes en Python; sitio con node y stubs)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from web import sync_web
from web.modelos import Usuario
from ayudas import con_ajustes, sesion

RAIZ = Path(__file__).resolve().parent.parent
SITE = RAIZ / "site"


def test_ajustes_trae_el_dialogo_con_la_copia(ctx, gh):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    h = cl.get("/ajustes").text          # conectado a la manera vieja: sin instalación
    assert 'id="dlg-autorizar"' in h and 'data-abre="dlg-autorizar"' in h
    assert 'href="/conectar/github?para=ajustes"' in h          # sin JS, liga normal a GitHub
    assert "<strong>ana/ahilallevas-datos</strong>" in h and "<strong>Only select repositories</strong>" in h
    assert "Install &amp; Authorize" in h and "nunca vemos tu key" in h and "dibujo-gh" in h
    with ctx.sesiones() as db:
        db.get(Usuario, uid).gh_instalacion = 55
        db.commit()
    assert "dlg-autorizar" not in cl.get("/ajustes").text       # ya autorizada: sin diálogo


def test_sin_app_ajustes_sin_dialogo(ctx):
    cl, uid = sesion(ctx)
    con_ajustes(ctx, uid)
    assert "dlg-autorizar" not in cl.get("/ajustes").text


def test_ui_sync_repo_solo_la_propia_cuenta(ctx, gh):
    u = Usuario(correo="r@x.mx", repo="ana/ahilallevas-datos", repo_id=7)
    assert sync_web.sync_ui(ctx.settings, u)["repo"] == "ana/ahilallevas-datos"
    assert sync_web.sync_ui(ctx.settings, Usuario(correo="s@x.mx"))["repo"] is None
    # el coach viendo a su atleta no recibe ui.sync: sitio.py solo lo calcula si atleta.id == usuario.id
    assert "if atleta.id == getattr(usuario, 'id', None) else None" in (RAIZ / "web" / "sitio.py").read_text()


def test_svg_del_sitio_es_el_mismo_dibujo_de_la_guia():
    svg = (SITE / "dibujo-github.svg").read_text(encoding="utf-8")
    parcial = (RAIZ / "web" / "plantillas" / "_dibujo_paso3.html").read_text(encoding="utf-8")
    cuerpo = parcial.split(">", 1)[1].rsplit("</svg>", 1)[0]
    assert cuerpo in svg and svg.startswith("<svg") and 'viewBox="0 0 420 240"' in svg


def _correr(fn_nombre, extra_js):
    """Extrae funciones de vistas.js y las corre en node con h/DS/document de mentiras."""
    src = (SITE / "vistas.js").read_text(encoding="utf-8")
    trozos = []
    for nombre in ("conNegritas", "dialogoAutorizar"):
        i = src.index(f"function {nombre}(")
        trozos.append(src[i:src.index("\n}\n", i) + 3])
    js = """
const h=(t,a,...x)=>({t,a:a||{},x:x.flat(9)}); const T=(k,v)=>k+(v?JSON.stringify(v):"");
const cerrado=[]; const body={hijos:[],append(d){this.hijos.push(d)}}; const document={body};
const ui=()=>({sync:{repo:%s}});
const fetch=()=>Promise.resolve({ok:true,text:()=>Promise.resolve("<svg></svg>")});
const DS={dialogo:({titulo,cuerpo,cerrar})=>({titulo,cuerpo,cerrar,classList:{add(){}},listeners:{},addEventListener(e,f){this.listeners[e]=f},showModal(){this.abierto=true},close(){this.abierto=false;cerrado.push(1)},remove(){}}),
  boton:(t,o={})=>({boton:t,href:o.href,onclick:o.onclick})};
%s
const txt=n=>typeof n==="string"?n:(n.x||[]).map(txt).join("");
const d=dialogoAutorizar("/conectar/github?para=conectado");
const bot=[]; const rec=n=>{ if(n&&n.boton) bot.push(n); (n&&n.x||[]).forEach(rec); }; d.cuerpo.forEach(rec);
const cierra=bot.find(b=>b.onclick); cierra.onclick();
console.log(JSON.stringify({titulo:d.titulo,abierto:body.hijos.length===1&&d.abierto===false,texto:d.cuerpo.map(txt).join("|"),
  botones:bot.map(b=>[b.boton,b.href||null]),cerrado:cerrado.length,dibujo:JSON.stringify(d.cuerpo).includes("dl-dibujo")}));
""" % (json.dumps(extra_js), "\n".join(trozos))
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


@pytest.mark.skipif(not shutil.which("node"), reason="sin node")
def test_dialogo_del_sitio_con_y_sin_repo():
    con = _correr("d", "ana/ahilallevas-datos")
    assert con["titulo"] == "sitio.auth.titulo" and con["dibujo"]
    assert 'sitio.auth.p2{"repo":"ana/ahilallevas-datos"}' in con["texto"] and "sitio.auth.p2_sin" not in con["texto"]
    assert con["botones"] == [["sitio.auth.ir", "/conectar/github?para=conectado"], ["sitio.auth.ahora_no", None]]
    assert con["cerrado"] == 1
    sin = _correr("d", None)
    assert "sitio.auth.p2_sin" in sin["texto"] and "sitio.auth.p2{" not in sin["texto"]


def test_los_tres_lugares_abren_el_dialogo_y_el_sw_sube_version():
    vistas = (SITE / "vistas.js").read_text(encoding="utf-8")
    app = (SITE / "app.js").read_text(encoding="utf-8")
    assert "else dialogoAutorizar(sy.url_autorizar)" in vistas and "location.href = sy.url_autorizar" not in vistas
    assert "avisoMigrar" not in app   # el aviso rojo se fue: el botón del encabezado autoriza
    sw = (SITE / "sw.js").read_text(encoding="utf-8")
    assert 'VERSION = "v89"' in sw and "/dibujo-github.svg" in sw


def test_ruta_estatica_del_dibujo(ctx):
    r = ctx.cliente().get("/dibujo-github.svg")
    assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml")
