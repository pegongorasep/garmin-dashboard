"""Animaciones A2: los dibujos de los estados vacíos, la regla «una vez por apertura y pantalla» y el plan recién guardado (node, DOM mínimo)."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parent.parent / "site"
con_node = pytest.mark.skipif(not shutil.which("node"), reason="sin node")

# Lo justo del DOM para que h(), sv(), icono() y los componentes armen nodos que se puedan revisar.
DOM = """
class Nodo {
  constructor(tag) { this.nodeType = 1; this.tag = tag; this.attrs = {}; this.hijos = []; this.dataset = {}; this.escondido = false;
    const clases = () => (this.attrs.class || "").split(" ").filter(Boolean);
    this.classList = { add: (c) => { this.attrs.class = [...new Set([...clases(), c])].join(" "); }, remove: (c) => { this.attrs.class = clases().filter((x) => x !== c).join(" "); },
      contains: (c) => clases().includes(c) }; }
  set className(v) { this.attrs.class = v; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (k.startsWith("data-")) this.dataset[k.slice(5).replace(/-(.)/g, (m, c) => c.toUpperCase())] = String(v); }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener() {}
  append(...x) { this.hijos.push(...x); }
  closest(s) { return s === "[hidden]" && this.escondido ? this : null; }
}
let enPagina = [];
globalThis.document = { createElement: (t) => new Nodo(t), createElementNS: (_, t) => new Nodo(t), createTextNode: (t) => ({ texto: t }), querySelectorAll: () => enPagina };
const todos = (n) => [n, ...(n.hijos || []).flatMap(todos)];
"""


def _node(js):
    fuente = "".join((SITE / f).read_text(encoding="utf-8") for f in ("base.js", "iconos.js", "componentes.js", "arte.js"))
    return json.loads(subprocess.run(["node", "-e", DOM + fuente + js], capture_output=True, text=True, check=True).stdout)


@con_node
def test_dibujos_en_su_caja_y_con_colores_de_tokens():
    r = _node("""
const ver = (s) => ({ caja: s.attrs.viewBox, clase: s.attrs.class, clases: todos(s).flatMap((n) => ((n.attrs || {}).class || "").split(" ")),
  colores: todos(s).flatMap((n) => [(n.attrs || {}).fill, (n.attrs || {}).stroke]).filter(Boolean) });
console.log(JSON.stringify([ARTE.anillo(), ARTE.anillo({ espera: true }), ARTE.personas({ libres: true }), ARTE.personas(),
  ARTE.grafica(), ARTE.grafica({ espera: true })].map(ver)));
""")
    for d in r:
        assert d["caja"] == "0 0 240 180" and d["clase"] == "arte"
        assert all(c in ("none", "currentColor") or c.startswith("var(--") for c in d["colores"]), d["colores"]
    anillo, espera, libres, grupo, grafica, redibuja = (d["clases"] for d in r)
    assert grafica.count("a-sube") == 6 and "a-trazo" in grafica and "a-pop" in grafica and "a-espera" not in grafica
    assert "a-espera" in redibuja and "a-trazo" not in redibuja and "a-pop" not in redibuja   # en espera: sin punto final
    assert "a-rotulo" in grafica and "a-rotulo" in redibuja   # siempre dice «Ejemplo»
    assert "a-trazo" in anillo and "a-espera" not in anillo
    assert "a-espera" in espera and "a-trazo" not in espera
    assert libres.count("a-late") == 2 and "a-flota" not in libres   # tú y dos lugares libres
    assert grupo.count("a-flota") == 3 and "a-late" not in grupo      # las personas


@con_node
def test_estado_vacio_con_arte_y_liga_y_sin_cambiar_los_de_antes():
    r = _node("""
const resumen = (n) => ({ clase: n.attrs.class, una: n.attrs["data-una-vez"] || null, hijos: n.hijos.map((x) => [x.tag, x.attrs.class || "", x.hijos.length]) });
console.log(JSON.stringify([
  DS.estadoVacio({ icono: null, titulo: "t", texto: "x", accion: { texto: "a", href: "/a" } }),
  DS.estadoVacio({ arte: ARTE.anillo(), titulo: "t", accion: { texto: "a", href: "/a" }, secundaria: { texto: "b", href: "/b" }, unaVez: "plan" }),
  DS.estadoVacio({ arte: ARTE.anillo({ espera: true }), espera: true, titulo: "t", accion: { texto: "a", deshabilitado: true }, unaVez: null }),
].map(resumen)));
""")
    antes, con_arte, espera = r
    assert antes == {"clase": "vacio", "una": None, "hijos": [["p", "vc-t", 1], ["p", "vc-x", 1], ["a", "boton", 1]]}
    assert con_arte["clase"] == "vacio con-arte" and con_arte["una"] == "plan"
    assert [h[0] for h in con_arte["hijos"]] == ["svg", "p", "a", "div"] and con_arte["hijos"][-1] == ["div", "vc-sec", 1]
    assert espera["clase"] == "vacio con-arte espera" and espera["una"] is None
    assert espera["hijos"][-1] == ["div", "vc-sec", 0]   # la ranura de la liga se reserva aunque no haya


@con_node
def test_se_anima_una_vez_por_apertura_y_pantalla():
    r = _node("""
const nodo = (nombre, escondido = false) => { const n = new Nodo("div"); n.setAttribute("data-una-vez", nombre); n.escondido = escondido; return n; };
const anim = () => { DS.animar.unaVez(); return enPagina.map((n) => n.classList.contains("anim")); };
const plan = nodo("plan", true), grupos = nodo("grupos");
const pasos = [];
enPagina = [plan, grupos]; pasos.push(anim());          // Plan escondido: no gasta su animación
plan.escondido = false; grupos.escondido = true; pasos.push(anim());   // se cambia de pestaña
pasos.push(anim());                                     // otra llamada a la vista: sigue
plan.escondido = true; grupos.escondido = false; pasos.push(anim());   // volver a Grupos: quieto
enPagina = [nodo("grupos"), nodo("plan")]; pasos.push(anim());         // repintado: quietos
console.log(JSON.stringify(pasos));
""")
    assert r == [[False, True], [True, False], [True, False], [False, False], [False, False]]


@con_node
def test_plan_recien_guardado_toma_la_semana_real():
    src = (SITE / "vista_plan.js").read_text(encoding="utf-8")
    fuente = src[src.index("function anilloRecien("):src.index("function renderPlan(")]
    js = """
let planRecien = false;
const semanasHoy = (d) => d.semanas_hoy || []; const etiquetaSelector = (d, s) => s.id; const anilloSemanaPlan = (s) => s.id;
DS.tarjeta = (o, x) => x;
%s
const con = { id: "hoy", plan: {} }, antes = { id: "antes", plan: null, plan_empieza: { idx: 1 } }, s1 = { id: "s1", plan: {} };
const n = new Nodo("section"), m = new Nodo("section");
entraUnaVez(n, "plan-semanas"); planRecien = true; entraUnaVez(m, "plan-semanas");
console.log(JSON.stringify([anilloRecien({ semanas_hoy: [con], semana_hoy_idx: 0 }), anilloRecien({ semanas_hoy: [antes, s1], semana_hoy_idx: 0 }),
  anilloRecien({ semanas_hoy: [{ id: "x", plan: null }], semana_hoy_idx: 0 }), anilloRecien({}), n.attrs, m.attrs, m.dataset.unaVez]));
""" % fuente
    hoy, primera, sin_plan, sin_datos, quieta, recien, nombre = _node(js)
    assert (hoy, primera, sin_plan, sin_datos) == ("hoy", "s1", None, None)
    assert quieta == {} and recien == {"class": "recien"} and nombre == "plan-semanas"


def test_lo_animado_respeta_reducir_movimiento():
    """Toda regla que usa los keyframes nuevos vive dentro de `prefers-reduced-motion: no-preference`."""
    for archivo in ("componentes.css", "styles.css"):
        css = re.sub(r"/\*.*?\*/", "", (SITE / archivo).read_text(encoding="utf-8"), flags=re.S)
        fuera = re.sub(r"@media \(prefers-reduced-motion: no-preference\) \{(?:[^{}]*\{[^{}]*\})*\s*\}", "", css)
        usos = re.findall(r"animation:\s*(ahi-(?:trazo|redibuja|pop|aparece|flota|late|barra|asoma|brinca)|anim-anillo)\b", fuera)
        assert not usos, (archivo, usos)
    css = "".join((SITE / a).read_text(encoding="utf-8") for a in ("componentes.css", "styles.css"))
    nombres = re.findall(r"@keyframes ([\w-]+)", css)
    assert len(nombres) == len(set(nombres)), nombres   # un nombre repetido pisaría la animación anterior (p. ej. la del logo)
    html = (SITE / "index.html").read_text(encoding="utf-8")
    assert html.index("componentes.js") < html.index("arte.js") < html.index("vistas.js")
