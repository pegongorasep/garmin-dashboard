"""Animaciones A5: sesión cumplida en Hoy (node, DOM mínimo): cuándo se celebra, qué se recuerda y qué se mueve."""
import json
import shutil

import pytest

from test_sitio_arte import SITE, _node

pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="sin node")

LLAVE = "semana-vista-7"


def semana(hechas=(), pct=0, *, inicio="2026-11-23", estado="actual", total=3):
    ids = ["a", "b", "c"][:total]
    return {"inicio": inicio, "estado": estado, "plan": {"hechas": len(hechas), "total": total, "min_pct": pct},
            "sesiones": [{"id": i, "estado": "hecha" if i in hechas else "incompleta" if i == "c" else "pendiente",
                          "fecha": f"2026-11-{24 + n}" if i in hechas else None} for n, i in enumerate(ids)],
            "dias": [{"fecha": f"2026-11-{23 + n}"} for n in range(7)]}


def visto(hechas=(), pct=0, inicio="2026-11-23"):
    return {LLAVE: json.dumps({"semana": inicio, "hechas": list(hechas), "pct": pct})}


def correr(pasos, *, guardado=None, falla=(), coach=False):
    """`pasos`: JS que usa pintar(semana), con `guardado` en el teléfono. `falla`: "leer" y/o "guardar" de localStorage truenan.
    Cada llamada a DS.animar.logro queda en `logros` (días y filas por su índice)."""
    src = (SITE / "app.js").read_text(encoding="utf-8")
    fuente = src[src.index("// --- sesión cumplida ---"):src.index("// --- carrera destacada")]
    ui = {"primer_inicio": {"registrar": "/x", "pasos": []} if coach else {"barras": {"llave": 7}}}
    stubs = """
const guardado = %s, logros = []; let ahora = 1000; Date.now = () => ahora;
globalThis.localStorage = { getItem: (k) => { if (%s) throw new Error("no"); return guardado[k] ?? null; }, setItem: (k, v) => { if (%s) throw new Error("no"); guardado[k] = v; } };
const ui = () => (%s); const $ = () => ({ querySelector: () => "logo" });
DS.animar.logro = (o) => logros.push(o);
const tarjetas = (s) => {
  const t = new Nodo("div"), c = new Nodo("div");
  t.querySelector = () => "anillo"; t.querySelectorAll = () => s.dias.map((_, i) => ({ querySelector: () => `dia${i}` }));
  c.querySelectorAll = () => s.sesiones.map((_, i) => ({ querySelector: () => `fila${i}` }));
  return [t, c];
};
const pintar = (s, { escondido = false } = {}) => { const [t, c] = tarjetas(s); t.escondido = escondido; sesionCumplida(s, t, c); enPagina = [t]; DS.animar.unaVez(); return t; };
const foto = () => ({ logros: logros.splice(0), visto: guardado["%s"] ? JSON.parse(guardado["%s"]) : null });
""" % (json.dumps(guardado or {}), json.dumps("leer" in falla), json.dumps("guardar" in falla), json.dumps(ui), LLAVE, LLAVE)
    return _node(stubs + fuente + "const r = [];\n" + pasos + "\nconsole.log(JSON.stringify(r));")


def pintar(s, **kw):
    return correr("pintar(%s); r.push(foto());" % json.dumps(s), **kw)[0]


def test_la_primera_vez_solo_guarda():
    r = pintar(semana("a", 28))
    assert r == {"logros": [], "visto": {"semana": "2026-11-23", "hechas": ["a"], "pct": 28}}


def test_sesion_nueva_avanza_desde_lo_visto_y_una_sola_vez():
    s = json.dumps(semana("ab", 56))
    primera, repintado, despues = correr("""
pintar(%s); r.push(foto()); ahora += 800; pintar(%s); r.push(foto()); ahora += 3000; pintar(%s); r.push(foto());
""" % (s, s, s), guardado=visto("a", 28))
    assert primera["logros"] == [{"pasado": 0, "desde": 28, "llena": False, "anillo": "anillo", "dias": ["dia2"], "palomitas": ["fila1"], "logo": "logo"}]
    assert primera["visto"] == {"semana": "2026-11-23", "hechas": ["a", "b"], "pct": 56}
    assert repintado["logros"] == [{**primera["logros"][0], "pasado": 800}]   # a medias: la retoma donde iba
    assert despues["logros"] == []


def test_mas_minutos_o_una_incompleta_no_celebran():
    r = pintar(semana("a", 60), guardado=visto("a", 28))
    assert r["logros"] == [] and r["visto"]["pct"] == 60


def test_semana_completa_recien_lograda():
    r = pintar(semana("abc", 104), guardado=visto("a", 28))
    assert r["logros"][0]["llena"] is True and r["logros"][0]["palomitas"] == ["fila1", "fila2"] and r["logros"][0]["dias"] == ["dia2", "dia3"]
    assert pintar(semana("abc", 120), guardado=visto("abc", 104))["logros"] == []


def test_semana_nueva_parte_de_cero():
    r = pintar(semana("a", 28), guardado=visto("abc", 100, "2026-11-16"))
    assert r["logros"][0]["desde"] == 0 and r["logros"][0]["palomitas"] == ["fila0"] and r["visto"]["semana"] == "2026-11-23"
    sin = pintar(semana((), 0), guardado=visto("abc", 100, "2026-11-16"))
    assert sin["logros"] == [] and sin["visto"] == {"semana": "2026-11-23", "hechas": [], "pct": 0}


@pytest.mark.parametrize("s", [semana("abc", 100, inicio="2026-11-16", estado="pasada"), semana((), 0, inicio="2026-11-30", estado="futura"),
                               {**semana(), "plan": None}])
def test_otra_semana_o_sin_plan_no_celebra_ni_pisa(s):
    r = pintar(s, guardado=visto("a", 28))
    assert r == {"logros": [], "visto": {"semana": "2026-11-23", "hechas": ["a"], "pct": 28}}


def test_datos_mas_viejos_que_lo_visto_no_pisan():
    r = pintar(semana("ab", 56, inicio="2026-11-16"), guardado=visto("a", 28))
    assert r["logros"] == [] and r["visto"]["semana"] == "2026-11-23"


def test_hoy_oculto_o_app_en_segundo_plano_espera():
    s = json.dumps(semana("ab", 56))
    escondido, fondo, a_la_vista = correr("""
const t = pintar(%s, { escondido: true }); r.push(foto());
t.escondido = false; document.hidden = true; DS.animar.unaVez(); r.push(foto());
document.hidden = false; ahora += 60000; DS.animar.unaVez(); DS.animar.unaVez(); r.push(foto());
""" % s, guardado=visto("a", 28))
    assert escondido["logros"] == fondo["logros"] == [] and escondido["visto"]["hechas"] == fondo["visto"]["hechas"] == ["a"]
    assert len(a_la_vista["logros"]) == 1 and a_la_vista["logros"][0]["pasado"] == 0 and a_la_vista["visto"]["hechas"] == ["a", "b"]


def test_el_coach_no_ve_ni_guarda_nada():
    assert pintar(semana("ab", 56), guardado=visto("a", 28), coach=True) == {"logros": [], "visto": {"semana": "2026-11-23", "hechas": ["a"], "pct": 28}}


@pytest.mark.parametrize("falla,guardado", [(("leer", "guardar"), None), (("guardar",), visto("a", 28))])
def test_sin_almacenamiento_no_rompe_ni_repite(falla, guardado):
    s = json.dumps(semana("ab", 56))
    r = correr("pintar(%s); r.push(foto()); ahora += 9000; pintar(%s); r.push(foto());" % (s, s), guardado=guardado, falla=falla)
    assert len(r[0]["logros"]) == (1 if guardado else 0) and r[1]["logros"] == []


def test_un_registro_roto_cuenta_como_primera_vez():
    for roto in ("{", "3", json.dumps({"semana": 1})):
        r = pintar(semana("a", 28), guardado={LLAVE: roto})
        assert r["logros"] == [] and r["visto"]["hechas"] == ["a"]


def animar(opciones, *, quieto=False):
    return _node("""
globalThis.window = { matchMedia: true }; globalThis.matchMedia = () => ({ matches: %s });
const movidos = [], quitadas = [];
const nodo = (nombre, attrs = {}) => { const n = new Nodo(nombre); n.attrs = { ...attrs };
  n.getAttribute = (k) => n.attrs[k];
  n.animate = (cuadros, o) => { const a = { nombre, cuadros, o }; movidos.push(a); return a; }; return n; };
Nodo.prototype.prepend = function (x) { x.animate = (cuadros, o) => { const a = { nombre: "onda", cuadros, o }; movidos.push(a); return a; }; x.remove = () => quitadas.push(1); this.hijos.unshift(x); };
Nodo.prototype.replaceChildren = function (...x) { this.hijos = x; x[0].hijos[0].animate = (cuadros, o) => { const a = { nombre: "palomita", cuadros, o }; movidos.push(a); return a; }; };
const l = nodo("anillo", { "stroke-dasharray": "100", "stroke-dashoffset": "44" }), svg = nodo("svg"), anillo = nodo("plan");
anillo.querySelector = (s) => (s === ".l" ? l : svg);
const insignia = nodo("insignia"), logo = nodo("logo"); logo.querySelectorAll = () => [0, 1, 2, 3, 4].map(() => nodo("barra"));
DS.animar.logro({ anillo, dias: [nodo("dia"), undefined], palomitas: [insignia, undefined], logo, ...%s });
const terminadas = movidos.filter((a) => a.nombre === "onda"); terminadas.forEach((a) => a.onfinish());
console.log(JSON.stringify({ movidos: movidos.map((a) => [a.nombre, a.o.delay, a.currentTime]), anillo: (movidos[0] || {}).cuadros, clase: anillo.attrs.class || null,
  quitadas: quitadas.length, estilos: todos(insignia).concat(svg.hijos).filter((n) => (n.attrs || {}).style).length }));
""" % (json.dumps(quieto), json.dumps(opciones)))


def test_sesion_mueve_anillo_dia_y_palomita():
    r = animar({"desde": 28, "pasado": 500})
    assert r["movidos"] == [["anillo", 150, 500], ["dia", 700, 500], ["palomita", 900, 500]]
    assert r["anillo"] == [{"strokeDashoffset": "72px"}, {"strokeDashoffset": "44px"}] and r["clase"] == "logro" and r["estilos"] == 0


def test_semana_completa_suma_dos_ondas_y_el_logo():
    r = animar({"desde": 130, "llena": True})
    nombres = [m[0] for m in r["movidos"]]
    assert nombres == ["anillo", "onda", "onda", "dia", "palomita"] + ["barra"] * 5 and r["quitadas"] == 2
    assert r["anillo"][0] == {"strokeDashoffset": "0px"}   # el % anterior se topa en 100


def test_con_reducir_movimiento_no_se_mueve_nada():
    r = animar({"desde": 28, "llena": True}, quieto=True)
    assert r["movidos"] == [] and r["clase"] is None
