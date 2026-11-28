// Utilidades compartidas (sitio, catálogo de diseño y gráficas). Se carga antes que todo lo demás.
/* Idioma: los textos viven en i18n/<idioma>.json (los escribe el build desde i18n/*.yaml). T("<clave>", {var}) los pinta (claves sitio.*). */
const IDIOMAS = ["es", "en"];
let IDIOMA = "es";
let TEXTOS = {};
const MESES = [];      // se llenan en cargarIdioma (T("sitio.meses"))
const DIAS_LARGO = []; // idem (T("sitio.dias"))

function T(clave, vars) {
  let t = TEXTOS[clave];
  if (t === undefined) t = clave;
  return vars ? t.replace(/\{(\w+)\}/g, (m, k) => (vars[k] === undefined ? m : vars[k])) : t;
}
/** "en-US" → "en"; lo que no tengamos → "es". */
function idiomaDe(pref) {
  const b = String(pref || "").slice(0, 2).toLowerCase();
  return IDIOMAS.includes(b) ? b : "es";
}
/** Idioma a usar antes de tener data.json: el último que se vio en este equipo, o el del navegador. */
function idiomaInicial() {
  try { const g = localStorage.getItem("idioma"); if (g) return idiomaDe(g); } catch (e) {}
  return idiomaDe(navigator.language);   // solo antes de tener data.json (pantalla de carga)
}
/** Carga i18n/<idioma>.json; si falla deja lo que había (las claves se ven tal cual, nunca se rompe). */
async function cargarIdioma(idioma) {
  idioma = idiomaDe(idioma);
  try {
    const r = await fetch(`${window.RUTA_I18N || ""}i18n/${idioma}.json`);   // RUTA_I18N = "/" en las páginas de la web que no cuelgan de la raíz
    if (r.ok) TEXTOS = await r.json();
  } catch (e) {}
  IDIOMA = idioma;
  document.documentElement.lang = idioma;
  MESES.splice(0, MESES.length, ...T("sitio.meses").split(","));
  DIAS_LARGO.splice(0, DIAS_LARGO.length, ...T("sitio.dias").split(","));
  try { localStorage.setItem("idioma", idioma); } catch (e) {}
}
/** Plural simple: Tn("sitio.corrida", 3) usa sitio.corrida_1 o sitio.corrida_n con {n}. */
const Tn = (base, n, vars) => T(`${base}_${n === 1 ? "1" : "n"}`, { n, ...(vars || {}) });
const LOCALES = { es: "es-MX", en: "en-US" };
const NS = "http://www.w3.org/2000/svg";

function h(tag, attrs, ...hijos) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    el.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
  }
  return el;
}

/** Elemento SVG: sv("rect", {x: 1}, hijos…). Los atributos nulos se omiten. */
function sv(tag, attrs, ...hijos) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const hijo of hijos.flat()) if (hijo) el.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
  return el;
}

const fmt = (n, d = 1) => (n === null || n === undefined ? "—" : Number(n).toLocaleString(LOCALES[IDIOMA] || "es-MX", { maximumFractionDigits: d }));

function parseFecha(iso) {
  // "YYYY-MM-DD" como fecha local, sin saltos por zona horaria
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}
