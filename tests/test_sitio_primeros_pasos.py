"""Animaciones A4: lo que pinta Hoy con ui.primer_inicio (node, DOM mínimo): vistas, barras, saltar y el 5 de 5."""
import json
import shutil

import pytest

from test_sitio_arte import SITE, _node

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sin node")

IDS = ["cuenta", "garmin", "plan", "grupo", "inbody"]


def barras(vista, hechos, siguiente=None, lista=()):
    return {"llave": 7, "vista": vista, "hechos": len(hechos), "siguiente": siguiente, "lista": list(lista), "liga": "/liga", "ocultar": "/ocultar",
            "pasos": [{"id": p, "hecho": p in hechos, "url": f"/{p}", "saltar": f"salta_{p}"} for p in IDS]}


def correr(js, *, guardado=None, quieto=False, sin_almacen=False, ok=True):
    """Corre `js` con primerInicio() y sus ayudas; `guardado` = lo que el teléfono recuerda."""
    src = (SITE / "app.js").read_text(encoding="utf-8")
    fuente = src[src.index("function barrasVistas("):src.index("function recordatorioCorrida()")]
    stubs = """
const guardado = %s, posts = [], timers = []; let recargas = 0, PI = null;
globalThis.localStorage = { getItem: (k) => { if (%s) throw new Error("no"); return guardado[k] ?? null; }, setItem: (k, v) => { if (%s) throw new Error("no"); guardado[k] = v; } };
globalThis.window = { matchMedia: true }; globalThis.matchMedia = () => ({ matches: %s });
globalThis.fetch = async (url, o) => { posts.push([url, Object.fromEntries(o.body)]); return { ok: %s, url }; };
globalThis.setTimeout = (f, ms) => timers.push([f, ms]);
const $ = () => ({ dataset: { csrf: "c" } }); const ui = () => ({ primer_inicio: PI }); const recargarDatos = async () => { recargas++; };
Nodo.prototype.addEventListener = function (e, f) { (this.al = this.al || {})[e] = f; };
Nodo.prototype.remove = function () { this.quitado = true; };
const texto = (n) => n.texto !== undefined ? n.texto : (n.hijos || []).map(texto).join(" ");
const clases = (n) => todos(n).map((x) => (x.attrs || {}).class || "").filter(Boolean);
const botones = (n) => todos(n).filter((x) => ["a", "button"].includes(x.tag));
const barra = (n) => { const gs = todos(n).filter((x) => x.tag === "g"); return gs.map((g) => g.hijos.map((r) => r.attrs.class || r.attrs.fill)); };
""" % (json.dumps(guardado or {}), json.dumps(sin_almacen), json.dumps(sin_almacen), json.dumps(quieto), json.dumps(ok))
    return _node(stubs + fuente + js)


def pintar(b, **kw):
    return correr("""
PI = { registrar: "/actividad/nueva", barras: %s };
const out = primerInicio(), c = out.length > 1 ? out[0] : null;
let visto = null;
if (c) { c.alVerse(); visto = { ...guardado }; }
console.log(JSON.stringify({ n: out.length, una: c && c.attrs["data-una-vez"], texto: c && texto(c), clases: c && clases(c), barras: c && barra(c),
  botones: c && botones(c).map((x) => [texto(x), x.attrs.href || null]), visto, guardado, esperas: timers.map((t) => t[1]), ultimo: texto(out[out.length - 1]) }));
""" % json.dumps(b), **kw)


def test_grande_sin_garmin():
    r = pintar(barras("garmin", ["cuenta"], "garmin", ["plan", "grupo", "inbody"]))
    assert r["n"] == 2 and r["ultimo"] == "sitio.pi.registrar" and r["una"] == "pasos-7-garmin-1"
    assert "card pi-tarjeta pi-grande" in r["clases"] and "pi-msg" in r["clases"]
    assert r["botones"][:3] == [["sitio.pi.conectar", "/garmin"], ["sitio.pi.liga", None], ["sitio.pi.sin_garmin", None]]
    assert [b[1] for b in r["botones"][3:]] == ["/plan", "/grupo", "/inbody"]
    assert r["barras"][0] == ["var(--grid)", "a-sube a-d1"]           # primera vez: la encendida sube
    assert r["barras"][1] == ["var(--grid)", "a-asoma"]               # la que sigue se asoma
    assert r["barras"][2:] == [["var(--grid)"]] * 3
    assert r["visto"] == {"pasos-7": "1"}


def test_historial_se_arma_sin_boton_ni_saltar():
    r = pintar(barras("historial", ["cuenta", "garmin"], None, ["grupo", "inbody"]))
    assert "card pi-tarjeta pi-grande pi-espera" in r["clases"] and r["clases"].count("a-arma") == 5
    assert [b[1] for b in r["botones"]] == ["/grupo", "/inbody"] and "sitio.pi.mientras" in r["texto"]
    assert r["visto"] == {"pasos-7": "0"}   # las barras no dicen cuántas van: al llegar el historial se encienden
    assert pintar(barras("historial", ["cuenta", "garmin"]), guardado={"pasos-7": "1"})["visto"] == {"pasos-7": "1"}


def test_compacta_enciende_solo_la_barra_nueva():
    b = barras("compacta", ["cuenta", "garmin", "grupo"], "plan")
    r = pintar(b, guardado={"pasos-7": "2"})
    assert "card pi-tarjeta pi-compacta" in r["clases"] and "sitio.pi.compacta" in r["texto"]
    assert r["botones"] == [["sitio.pi.paso_plan", "/plan"], ["sitio.pi.saltar", None]]
    assert r["barras"] == [["var(--grid)", "var(--z1)"], ["var(--grid)", "var(--z2)"], ["var(--grid)", "a-sube a-d3"], ["var(--grid)", "a-asoma"], ["var(--grid)"]]
    assert r["visto"] == {"pasos-7": "3"}
    assert not any("a-sube" in c for c in pintar(b, guardado={"pasos-7": "3"})["clases"])


def test_cinco_de_cinco_solo_si_aqui_se_vio_incompleta():
    b = barras("completa", IDS)
    r = pintar(b, guardado={"pasos-7": "4"})
    assert r["n"] == 2 and r["clases"].count("a-brinca") == 5 and "sitio.pi.n_de" in r["texto"]
    assert r["botones"] == [] and r["visto"] == {"pasos-7": "5"} and r["esperas"] == [2200]
    for guardado in ({}, {"pasos-7": "5"}, {"pasos-8": "2"}):   # nunca la vio, ya la despidió, u otra cuenta
        r = pintar(b, guardado=guardado)
        assert r["n"] == 1 and r["guardado"] == guardado
    quieto = pintar(b, guardado={"pasos-7": "4"}, quieto=True)
    assert quieto["n"] == 1 and quieto["guardado"] == {"pasos-7": "5"}


def test_sin_almacenamiento_no_rompe():
    assert pintar(barras("compacta", ["cuenta", "garmin"], "plan"), sin_almacen=True)["n"] == 2
    assert pintar(barras("completa", IDS), sin_almacen=True)["n"] == 1


@pytest.mark.parametrize("ok,recargas", [(True, 1), (False, 0)])
def test_saltar_manda_el_aviso_y_vuelve_a_pedir_los_datos(ok, recargas):
    r = correr("""
PI = { barras: %s };
const c = primerInicio()[0], b = botones(c).find((x) => texto(x) === "sitio.pi.saltar");
(async () => { await b.al.click(); console.log(JSON.stringify({ posts, recargas, disabled: b.disabled })); })();
""" % json.dumps(barras("compacta", ["cuenta", "garmin"], "plan")), ok=ok)
    assert r["posts"] == [["/ocultar", {"csrf": "c", "id": "salta_plan", "huella": "0"}]]
    assert r["recargas"] == recargas and r["disabled"] is False


def test_coach_ve_la_lista_sin_barras_y_sin_clave_no_hay_nada():
    r = correr("""
PI = { registrar: "/a/3/actividad/nueva", pasos: [{ id: "plan", url: "/a/3/plan/nuevo" }] };
const coach = primerInicio();
PI = { registrar: null, pasos: [] }; const solo = primerInicio().length;
PI = undefined;
console.log(JSON.stringify({ clases: coach.flatMap(clases), texto: coach.map(texto), solo, sin: primerInicio().length }));
""")
    assert not any(c.startswith("pi-tarjeta") or "pi-barras" in c for c in r["clases"]) and "pi-paso" in r["clases"]
    assert "sitio.pi.pasos_t" in r["texto"][1] and r["solo"] == 0 and r["sin"] == 0


def test_la_barra_se_marca_vista_solo_a_la_vista():
    r = _node("""
const n = new Nodo("div"); n.setAttribute("data-una-vez", "pasos"); n.escondido = true; let veces = 0; n.alVerse = () => veces++; enPagina = [n];
const pasos = []; DS.animar.unaVez(); pasos.push(veces); n.escondido = false; DS.animar.unaVez(); pasos.push(veces); DS.animar.unaVez(); pasos.push(veces);
console.log(JSON.stringify(pasos));
""")
    assert r == [0, 1, 1]


@pytest.mark.parametrize("sin_actividad,rec,esperado", [(True, None, []), (True, {"rhr_7d": 55}, ["sitio.sl.recup"]),
                                                        (False, None, ["sitio.sl.titulo", "sitio.sl.recup"])])
def test_hoy_sin_plan_esconde_las_tarjetas_vacias(sin_actividad, rec, esperado):
    src = (SITE / "app.js").read_text(encoding="utf-8")
    fuente = src[src.index("function renderHoySinPlan("):src.index("function renderHoy(d)")]
    r = _node("""
const raiz = new Nodo("section"); raiz.replaceChildren = (...x) => { raiz.hijos = x; };
const $ = () => raiz; const ui = () => ({ primer_inicio: { sin_actividad: %s } });
const nada = () => null; const saludoHoy = nada, recordatorioCorrida = nada, avisoKeyRechazada = nada, calendarioTocable = () => [], primerInicio = () => [], zonaBar = nada;
DS.tarjeta = (o) => o.titulo; DS.tiles = nada; DS.estadoVacio = nada;
%s
renderHoySinPlan({ semana_libre: { actividades: 0, recuperacion: %s } });
console.log(JSON.stringify(raiz.hijos));
""" % (json.dumps(sin_actividad), fuente, json.dumps(rec)))
    assert r == esperado
