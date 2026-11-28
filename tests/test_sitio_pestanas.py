"""Animaciones A1: las cuatro pestañas fijas y los estados vacíos de Plan y Grupos (sitio con node y stubs)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sin node")


def _trozo(archivo, desde, hasta="\n}\n"):
    src = (SITE / archivo).read_text(encoding="utf-8")
    i = src.index(desde)
    return src[i:src.index(hasta, i) + len(hasta)]


def _node(js):
    return json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)


def _pestanas(datos, atributo=None):
    """Las pestañas que arma vistas.js con ese data.json (None = aún no llega) y ese <main data-grupos> (None = sin atributo)."""
    js = """
const datos=%s, atributo=%s; const T=(k)=>k;
const $=()=>({dataset: atributo===null?{}:{grupos:atributo}}); const ui=()=>(datos&&datos.ui)||{};
%s
console.log(JSON.stringify(tabsDef().map((t)=>t.id)));
""" % (json.dumps(datos), json.dumps(atributo), _trozo("vistas.js", "const nGrupos", "let juntosNuevo") + " = false;")
    return _node(js)


FIJAS = ["hoy", "plan", "progreso"]
WEB = {"crear": "/grupos/nuevo", "invitar": "/grupos"}


@pytest.mark.parametrize("datos,atributo,grupos", [
    (None, "0", True),     # web propia antes de data.json, aun sin grupos
    (None, "2", True),
    (None, None, False),   # coach o build local antes de data.json
    ({"ui": {"grupos": 0, "sin_plan": True, "vacios": {"grupos": WEB}}}, "0", True),
    ({"ui": {"grupos": 0, "vacios": {"grupos": None}, "coach": {"nombre": "Ana"}}}, None, False),
    ({"ui": {"grupos": 0}}, None, False),   # build local estático
    ({"ui": {"grupos": 0}}, "0", False),    # sin la clave nueva: como antes
    ({"ui": {"grupos": 1}}, "1", True),
])
def test_pestanas_fijas_y_grupos_solo_en_la_web_propia(datos, atributo, grupos):
    assert _pestanas(datos, atributo) == FIJAS + (["grupo"] if grupos else [])


def test_grupos_sin_ningun_grupo_no_pide_nada():
    fuente = "".join(_trozo("vista_grupo.js", f) for f in
                     ("function juntosRevisar(", "function precargarGrupo(", "function pintarSinGrupos(", "async function cargarGrupo("))
    js = """
const T=(k)=>k; const pedidos=[]; const nGrupos=()=>0; let grupoTurno=0; const grupoCache={lista:null,grupos:{},vuelo:null};
const grupoGet=(u)=>{pedidos.push(u);return Promise.resolve({})}; const grupoBajar=grupoGet; const juntosVisto=()=>pedidos.push("visto");
const caja={hijos:null,replaceChildren(...x){this.hijos=x}}; const $=()=>caja;
const ui=()=>({vacios:{grupos:{crear:"/grupos/nuevo",invitar:"/grupos"}}});
const DS={tarjeta:(o,...x)=>({o,x}),estadoVacio:(o)=>o};
%s
juntosRevisar(); precargarGrupo(); cargarGrupo(null).then(()=>cargarGrupo("3")).then(()=>console.log(JSON.stringify({pedidos,vacio:caja.hijos[0].x[0]})));
""" % fuente
    r = _node(js)
    assert r["pedidos"] == []
    assert r["vacio"]["titulo"] == "sitio.gr.sin_t" and r["vacio"]["texto"] == "sitio.gr.sin_x"
    assert r["vacio"]["accion"] == {"texto": "sitio.gr.sin_acc", "href": "/grupos/nuevo"}


@pytest.mark.parametrize("ui,href", [({"vacios": {"grupos": {"invitar": "/grupos/7"}}}, "/grupos/7"), ({}, "/grupos")])
def test_feed_vacio_lleva_a_la_liga_que_dice_python(ui, href):
    js = """
const T=(k)=>k; const h=()=>({}); const feedCache={items:[],listo:true,siguiente:null}; const ui=()=>(%s);
const DS={estadoVacio:(o)=>o}; let hijos; const sec={replaceChildren(...x){hijos=x}};
%s
pintarFeed(sec); console.log(JSON.stringify(hijos[1]));
""" % (json.dumps(ui), _trozo("vista_grupo.js", "function pintarFeed("))
    r = _node(js)
    assert r["titulo"] == "sitio.gr.feed_vacio_t" and r["accion"] == {"texto": "sitio.gr.feed_vacio_acc", "href": href}


@pytest.mark.parametrize("plan,texto,accion", [
    ({"estado": "sin_plan", "armar": "/a/3/plan/nuevo"}, "sitio.sl.sin_plan_x", {"texto": "sitio.sl.armar", "href": "/a/3/plan/nuevo"}),
    ({"estado": "esperando", "armar": "/plan/nuevo"}, "sitio.sl.sin_plan_espera", {"texto": "sitio.sync.espera", "deshabilitado": True}),
    ({"estado": "sin_plan", "armar": None}, "sitio.sl.sin_plan_x", None),
    ({"estado": "esperando", "armar": None}, "sitio.sl.sin_plan_espera", None),
    (None, "sitio.sl.sin_plan_x", None),   # sin la clave nueva (build local): sin botón
])
def test_plan_vacio(plan, texto, accion):
    js = """
const T=(k)=>k; const ui=()=>(%s); const DS={tarjeta:(o,...x)=>({o,x}),estadoVacio:(o)=>o};
%s
console.log(JSON.stringify(planVacio()));
""" % (json.dumps({"vacios": {"plan": plan}} if plan else {}), _trozo("vista_plan.js", "function planVacio("))
    r = _node(js)
    assert "titulo" not in r["o"]   # el título va una sola vez: el del estado vacío
    assert r["x"][0]["titulo"] == "sitio.sl.sin_plan_t" and r["x"][0]["texto"] == texto and r["x"][0]["accion"] == accion
