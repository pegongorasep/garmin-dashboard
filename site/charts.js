// Gráficas SVG a mano: una sola escala por gráfica, marcas finas, rejilla tenue.
const NS = "http://www.w3.org/2000/svg";

function sv(tag, attrs, ...hijos) {
  const el = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v !== null && v !== undefined) el.setAttribute(k, v);
  for (const hijo of hijos.flat()) if (hijo) el.append(hijo.nodeType ? hijo : document.createTextNode(String(hijo)));
  return el;
}

function pasoNice(crudo) {
  const p = 10 ** Math.floor(Math.log10(crudo));
  const f = crudo / p;
  return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p;
}

function ticksNice(lo, hi, n = 3) {
  if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
  const paso = pasoNice((hi - lo) / n);
  const out = [];
  for (let v = Math.floor(lo / paso) * paso; ; v += paso) {
    out.push(Number(v.toFixed(6)));
    if (v >= hi - paso * 0.001) break;
  }
  return out;
}

const fechaCorta2 = (ms) => { const f = new Date(ms); return `${f.getDate()} ${MESES[f.getMonth()]}`; };

function tooltipEn(cont) {
  const tip = h("div", { class: "tip", hidden: true });
  cont.append(tip);
  return {
    mostrar(texto, x, y) {
      tip.textContent = texto;
      tip.hidden = false;
      const w = cont.clientWidth, tw = tip.offsetWidth;
      tip.style.left = `${Math.min(Math.max(x, tw / 2 + 2), w - tw / 2 - 2)}px`;
      tip.style.top = `${Math.max(y - 8, 0)}px`;
    },
    ocultar() { tip.hidden = true; },
  };
}

/**
 * Gráfica de línea.
 * cfg: { ancho, alto, serie:[{fecha, y}], banda:[{lo,hi}] (misma longitud que serie, opcional),
 *        ref:{y, etiqueta}, dominio:[ms0, ms1], marcadores:boolean, texto:(punto)=>string, fmtY }
 * Los y nulos cortan la línea (no se interpola).
 */
function lineChart(cfg) {
  const { ancho: W, alto: H = 170, serie } = cfg;
  const cont = h("div", { class: "chart" });
  const ml = 38, mr = 10, mt = 10, mb = 22;
  const t = serie.map((p) => parseFecha(p.fecha).getTime());
  const [t0, t1] = cfg.dominio || [Math.min(...t), Math.max(...t)];
  const x = (ms) => ml + (t1 === t0 ? (W - ml - mr) / 2 : ((ms - t0) / (t1 - t0)) * (W - ml - mr));
  const ys = serie.map((p) => p.y).filter((v) => v !== null && v !== undefined);
  if (!ys.length) return h("p", { class: "vacio" }, "Sin datos en este periodo.");
  const extra = [];
  (cfg.banda || []).forEach((b) => { if (b && b.lo != null) extra.push(b.lo, b.hi); });
  if (cfg.ref) extra.push(cfg.ref.y);
  let lo = Math.min(...ys, ...extra), hi = Math.max(...ys, ...extra);
  const pad = (hi - lo) * 0.12 || 1;
  lo -= pad; hi += pad;
  const ticks = ticksNice(lo, hi, 3);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const y = (v) => mt + (1 - (v - lo) / (hi - lo)) * (H - mt - mb);
  const fmtY = cfg.fmtY || ((v) => fmt(v, 1));

  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.etiqueta || "Gráfica" });
  for (const v of ticks) {
    svg.append(sv("line", { class: "grid", x1: ml, x2: W - mr, y1: y(v), y2: y(v) }),
      sv("text", { class: "eje", x: ml - 6, y: y(v) + 4, "text-anchor": "end" }, fmtY(v)));
  }
  svg.append(sv("line", { class: "base", x1: ml, x2: W - mr, y1: H - mb, y2: H - mb }));
  const nx = W < 300 ? 3 : 4;
  for (let i = 0; i < nx; i++) {
    const ms = t0 + ((t1 - t0) * i) / (nx - 1);
    svg.append(sv("text", { class: "eje", x: x(ms), y: H - 6, "text-anchor": i === 0 ? "start" : i === nx - 1 ? "end" : "middle" }, fechaCorta2(ms)));
  }
  // banda: un polígono por tramo continuo
  const tramos = (ok) => {
    const out = []; let cur = [];
    serie.forEach((p, i) => { if (ok(i)) cur.push(i); else if (cur.length) { out.push(cur); cur = []; } });
    if (cur.length) out.push(cur);
    return out;
  };
  if (cfg.banda) {
    for (const tr of tramos((i) => cfg.banda[i] && cfg.banda[i].lo != null)) {
      const arriba = tr.map((i) => `${x(t[i])},${y(cfg.banda[i].hi)}`);
      const abajo = tr.slice().reverse().map((i) => `${x(t[i])},${y(cfg.banda[i].lo)}`);
      svg.append(sv("polygon", { class: "banda", points: [...arriba, ...abajo].join(" ") }));
    }
  }
  if (cfg.ref) {
    svg.append(sv("line", { class: "ref", x1: ml, x2: W - mr, y1: y(cfg.ref.y), y2: y(cfg.ref.y) }));
    if (cfg.ref.etiqueta) svg.append(sv("text", { class: "eje ref-t", x: W - mr, y: y(cfg.ref.y) - 4, "text-anchor": "end" }, cfg.ref.etiqueta));
  }
  const validos = tramos((i) => serie[i].y != null);
  for (const tr of validos) {
    if (tr.length === 1) svg.append(sv("circle", { class: "pt", cx: x(t[tr[0]]), cy: y(serie[tr[0]].y), r: 3.5 }));
    else svg.append(sv("polyline", { class: "ln", points: tr.map((i) => `${x(t[i])},${y(serie[i].y)}`).join(" ") }));
  }
  if (cfg.marcadores) for (const i of validos.flat()) svg.append(sv("circle", { class: "pt", cx: x(t[i]), cy: y(serie[i].y), r: 4 }));
  const ult = validos.flat().pop();
  if (ult !== undefined) svg.append(sv("circle", { class: "pt fin", cx: x(t[ult]), cy: y(serie[ult].y), r: 4.5 }));

  // cruz + tooltip
  const cruz = sv("line", { class: "cruz", y1: mt, y2: H - mb, visibility: "hidden" });
  const punto = sv("circle", { class: "pt fin", r: 4.5, visibility: "hidden" });
  const capa = sv("rect", { class: "capa", x: ml, y: 0, width: W - ml - mr, height: H, tabindex: 0,
    "aria-label": "Recorre los puntos con las flechas" });
  svg.append(cruz, punto, capa);
  cont.append(svg);
  const tip = tooltipEn(cont);
  const idxs = validos.flat();
  const ir = (i) => {
    cruz.setAttribute("x1", x(t[i])); cruz.setAttribute("x2", x(t[i])); cruz.setAttribute("visibility", "visible");
    punto.setAttribute("cx", x(t[i])); punto.setAttribute("cy", y(serie[i].y)); punto.setAttribute("visibility", "visible");
    tip.mostrar(cfg.texto(serie[i]), x(t[i]), y(serie[i].y));
  };
  const fuera = () => { cruz.setAttribute("visibility", "hidden"); punto.setAttribute("visibility", "hidden"); tip.ocultar(); };
  const cercano = (ev) => {
    const r = svg.getBoundingClientRect();
    const px = ev.clientX - r.left;
    return idxs.reduce((m, i) => (Math.abs(x(t[i]) - px) < Math.abs(x(t[m]) - px) ? i : m), idxs[0]);
  };
  let actual = idxs[idxs.length - 1];
  capa.addEventListener("pointermove", (ev) => { actual = cercano(ev); ir(actual); });
  capa.addEventListener("pointerdown", (ev) => { actual = cercano(ev); ir(actual); });
  capa.addEventListener("pointerleave", fuera);
  capa.addEventListener("blur", fuera);
  capa.addEventListener("focus", () => ir(actual));
  capa.addEventListener("keydown", (ev) => {
    const k = idxs.indexOf(actual);
    if (ev.key === "ArrowLeft" && k > 0) actual = idxs[k - 1];
    else if (ev.key === "ArrowRight" && k < idxs.length - 1) actual = idxs[k + 1];
    else return;
    ev.preventDefault(); ir(actual);
  });
  return cont;
}

/**
 * Barras apiladas por semana. cfg: { ancho, alto, semanas:[{inicio, valores:[a,b], sin_rpe}], texto:(semana)=>string }
 * Segmentos separados por 2 px de superficie; barra de 24 px como máximo; extremo superior redondeado.
 */
function barChart(cfg) {
  const { ancho: W, alto: H = 170, semanas } = cfg;
  const cont = h("div", { class: "chart" });
  const ml = 38, mr = 10, mt = 14, mb = 22;
  const total = (s) => s.valores.reduce((a, v) => a + v, 0);
  const max = Math.max(...semanas.map(total), 0);
  if (max <= 0) return h("p", { class: "vacio" }, "Sin carga registrada en este periodo.");
  const ticks = ticksNice(0, max * 1.08, 3);
  const hi = ticks[ticks.length - 1];
  const y = (v) => mt + (1 - v / hi) * (H - mt - mb);
  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.etiqueta || "Barras" });
  for (const v of ticks) {
    svg.append(sv("line", { class: "grid", x1: ml, x2: W - mr, y1: y(v), y2: y(v) }),
      sv("text", { class: "eje", x: ml - 6, y: y(v) + 4, "text-anchor": "end" }, fmt(v, 0)));
  }
  svg.append(sv("line", { class: "base", x1: ml, x2: W - mr, y1: H - mb, y2: H - mb }));
  const slot = (W - ml - mr) / semanas.length;
  const ancho = Math.min(24, slot * 0.64);
  const cada = Math.max(1, Math.ceil(42 / slot));
  const tip = tooltipEn(cont);
  semanas.forEach((s, i) => {
    const cx = ml + slot * i + slot / 2;
    let base = H - mb;
    const idxPositivos = s.valores.map((v, k) => (v > 0 ? k : -1)).filter((k) => k >= 0);
    const ultimo = idxPositivos[idxPositivos.length - 1];
    s.valores.forEach((v, k) => {
      if (v <= 0) return;
      const alto = Math.max((v / hi) * (H - mt - mb) - (k === idxPositivos[0] ? 0 : 2), 1);
      const top = base - alto, x0 = cx - ancho / 2;
      const r = k === ultimo ? Math.min(4, alto) : 0;
      const d = r > 0
        ? `M${x0},${base} V${top + r} Q${x0},${top} ${x0 + r},${top} H${x0 + ancho - r} Q${x0 + ancho},${top} ${x0 + ancho},${top + r} V${base} Z`
        : `M${x0},${base} V${top} H${x0 + ancho} V${base} Z`;
      svg.append(sv("path", { class: `serie s${k + 1}`, d }));
      base = top - 2;
    });
    if (s.sin_rpe > 0) svg.append(sv("text", { class: "eje ast", x: cx, y: Math.max(base - 2, 12), "text-anchor": "middle" }, "*"));
    if (i % cada === 0) svg.append(sv("text", { class: "eje", x: cx, y: H - 6, "text-anchor": "middle" }, fechaCorta2(parseFecha(s.inicio).getTime())));
    const hit = sv("rect", { class: "capa", x: cx - slot / 2, y: 0, width: slot, height: H - mb, tabindex: 0,
      "aria-label": cfg.texto(s) });
    const ver = () => tip.mostrar(cfg.texto(s), cx, y(total(s)));
    hit.addEventListener("pointerenter", ver);
    hit.addEventListener("pointerdown", ver);
    hit.addEventListener("focus", ver);
    hit.addEventListener("pointerleave", () => tip.ocultar());
    hit.addEventListener("blur", () => tip.ocultar());
    svg.append(hit);
  });
  cont.prepend(svg);
  return cont;
}
