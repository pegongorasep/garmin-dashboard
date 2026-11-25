// Utilidades compartidas (sitio, catálogo de diseño y gráficas). Se carga antes que todo lo demás.
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
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

const fmt = (n, d = 1) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: d }));

function parseFecha(iso) {
  // "YYYY-MM-DD" como fecha local, sin saltos por zona horaria
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}
