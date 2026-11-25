// Gráficas SVG a mano: una sola escala por gráfica, marcas finas, rejilla tenue.
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

/** Globito sobre la gráfica. Si el texto trae "\n", la primera línea va en negritas (<b>) y las demás en <small>. */
function tooltipEn(cont) {
  const tip = h("div", { class: "tip", hidden: true });
  cont.append(tip);
  return {
    mostrar(texto, x, y) {
      const [primera, ...resto] = String(texto).split("\n");
      tip.replaceChildren(h("b", {}, primera), ...resto.map((t) => h("small", {}, t)));
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
 *        ref:{y, etiqueta}, dominio:[ms0, ms1], marcadores:boolean, texto:(punto)=>string, fmtY,
 *        puntos:boolean (la serie son puntos de r=2.5 sin línea), promedio:[y] (misma longitud; línea de 2 px),
 *        invertir:boolean (arriba = valor menor, p. ej. ritmo), etiquetaFinal:string (valor del último punto, escrito sobre él),
 *        clase:"s1"|"s2" (color de la serie principal), nombre:string (etiqueta directa de la serie principal),
 *        extra:[{y:[...] (misma longitud que serie), clase, nombre}] (más series en el mismo eje, con marcadores),
 *        verticales:[{fecha, etiqueta}] (rayas verticales tenues), fmtX:(ms)=>string (rótulos del eje x) }
 * Los y nulos cortan la línea (no se interpola).
 */
function lineChart(cfg) {
  const { ancho: W, alto: H = 170, serie } = cfg;
  const cont = h("div", { class: "graf" });
  const ml = 38, mr = 10, mt = 10, mb = 22;
  const t = serie.map((p) => parseFecha(p.fecha).getTime());
  const [t0, t1] = cfg.dominio || [Math.min(...t), Math.max(...t)];
  const x = (ms) => ml + (t1 === t0 ? (W - ml - mr) / 2 : ((ms - t0) / (t1 - t0)) * (W - ml - mr));
  const prom = cfg.promedio || [];
  const ys = [...serie.map((p) => p.y), ...prom, ...(cfg.extra || []).flatMap((e) => e.y)].filter((v) => v !== null && v !== undefined);
  if (!ys.length) return h("p", { class: "vacio" }, "Sin datos en este periodo.");
  const extra = [];
  (cfg.banda || []).forEach((b) => { if (b && b.lo != null) extra.push(b.lo, b.hi); });
  if (cfg.ref) extra.push(cfg.ref.y);
  let lo = Math.min(...ys, ...extra), hi = Math.max(...ys, ...extra);
  const pad = (hi - lo) * 0.12 || 1;
  lo -= pad; hi += pad;
  const ticks = ticksNice(lo, hi, 3);
  lo = Math.min(lo, ticks[0]); hi = Math.max(hi, ticks[ticks.length - 1]);
  const y = (v) => mt + (cfg.invertir ? (v - lo) : (hi - v)) / (hi - lo) * (H - mt - mb);
  const fmtY = cfg.fmtY || ((v) => fmt(v, 1));

  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.etiqueta || "Gráfica" });
  for (const v of ticks) {
    svg.append(sv("line", { class: "rej", x1: ml, x2: W - mr, y1: y(v), y2: y(v) }),
      sv("text", { x: ml - 6, y: y(v) + 4, "text-anchor": "end" }, fmtY(v)));
  }
  svg.append(sv("line", { class: "eje", x1: ml, x2: W - mr, y1: H - mb, y2: H - mb }));
  const nx = W < 300 ? 3 : 4;
  for (let i = 0; i < nx; i++) {
    const ms = t0 + ((t1 - t0) * i) / (nx - 1);
    svg.append(sv("text", { x: x(ms), y: H - 6, "text-anchor": i === 0 ? "start" : i === nx - 1 ? "end" : "middle" }, (cfg.fmtX || fechaCorta2)(ms)));
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
    if (cfg.ref.etiqueta) svg.append(sv("text", { class: "ref-t", x: W - mr, y: y(cfg.ref.y) - 4, "text-anchor": "end" }, cfg.ref.etiqueta));
  }
  for (const v of cfg.verticales || []) {
    const vx = x(parseFecha(v.fecha).getTime());
    svg.append(sv("line", { class: "vert", x1: vx, x2: vx, y1: mt, y2: H - mb }),
      sv("text", { class: "vert-t", x: vx + 4, y: mt + 9, "text-anchor": "start" }, v.etiqueta));
  }
  const cl = cfg.clase || "s1";
  const validos = tramos((i) => serie[i].y != null);
  if (cfg.promedio) {
    for (const tr of tramos((i) => prom[i] != null)) {
      if (tr.length > 1) svg.append(sv("polyline", { class: "ln", points: tr.map((i) => `${x(t[i])},${y(prom[i])}`).join(" ") }));
    }
  }
  for (const tr of validos) {
    if (cfg.puntos) {
      for (const i of tr) svg.append(sv("circle", { class: `pt-d ${cl}`, cx: x(t[i]), cy: y(serie[i].y), r: 2.5 }));
    } else if (tr.length === 1) svg.append(sv("circle", { class: "pt", cx: x(t[tr[0]]), cy: y(serie[tr[0]].y), r: 3.5 }));
    else svg.append(sv("polyline", { class: `ln ${cl}`, points: tr.map((i) => `${x(t[i])},${y(serie[i].y)}`).join(" ") }));
  }
  // series extra: misma escala y mismas fechas; línea de 2 px con marcadores y etiqueta directa
  const dibujarExtra = (e) => {
    const idx = serie.map((_, i) => i).filter((i) => e.y[i] != null);
    if (idx.length > 1) svg.append(sv("polyline", { class: `ln ${e.clase}`, points: idx.map((i) => `${x(t[i])},${y(e.y[i])}`).join(" ") }));
    for (const i of idx) svg.append(sv("circle", { class: `pt ${e.clase}`, cx: x(t[i]), cy: y(e.y[i]), r: 4 }));
    return idx;
  };
  // la etiqueta va arriba del último punto, o abajo si la serie venía bajando (así no tapa la línea)
  const etiquetaDirecta = (nombre, i, v, previo) => svg.append(sv("text", { class: "dato", x: Math.min(x(t[i]) + 4, W - 2),
    y: previo != null && previo > v ? Math.min(y(v) + 16, H - mb - 2) : Math.max(y(v) - 9, 10), "text-anchor": "end" }, nombre));
  for (const e of cfg.extra || []) {
    const idx = dibujarExtra(e);
    if (e.nombre && idx.length) etiquetaDirecta(e.nombre, idx[idx.length - 1], e.y[idx[idx.length - 1]], idx.length > 1 ? e.y[idx[idx.length - 2]] : null);
  }
  if (cfg.marcadores) for (const i of validos.flat()) svg.append(sv("circle", { class: `pt ${cl}`, cx: x(t[i]), cy: y(serie[i].y), r: 4 }));
  const ult = validos.flat().pop();
  const valoresValidos = validos.flat();
  const prev = valoresValidos.length > 1 ? serie[valoresValidos[valoresValidos.length - 2]].y : null;
  if (ult !== undefined && cfg.nombre) etiquetaDirecta(cfg.nombre, ult, serie[ult].y, prev);
  if (ult !== undefined && !cfg.puntos) svg.append(sv("circle", { class: `pt ${cl}`, cx: x(t[ult]), cy: y(serie[ult].y), r: 4.5 }));
  if (ult !== undefined && cfg.etiquetaFinal) {
    etiquetaDirecta(cfg.etiquetaFinal, ult, serie[ult].y, prev);
  }

  // cruz + tooltip
  const cruz = sv("line", { class: "cruz", y1: mt, y2: H - mb, visibility: "hidden" });
  const punto = sv("circle", { class: `pt ${cl}`, r: 4.5, visibility: "hidden" });
  const capa = sv("rect", { class: "capa", x: ml, y: 0, width: W - ml - mr, height: H, tabindex: 0,
    "aria-label": "Recorre los puntos con las flechas" });
  svg.append(cruz, punto, capa);
  cont.append(svg);
  const tip = tooltipEn(cont);
  const idxs = validos.flat();
  const ir = (i) => {
    cruz.setAttribute("x1", x(t[i])); cruz.setAttribute("x2", x(t[i])); cruz.setAttribute("visibility", "visible");
    punto.setAttribute("cx", x(t[i])); punto.setAttribute("cy", y(serie[i].y)); punto.setAttribute("visibility", "visible");
    tip.mostrar(cfg.texto(serie[i], prom[i]), x(t[i]), y(serie[i].y));
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
 * Barras apiladas por semana. cfg: { ancho, alto, semanas:[{inicio, valores:[a,b], meta}], texto:(semana)=>string,
 *   clases:["s1","s2"], etiquetaFinal:string (valor de la última barra, escrito sobre ella) }  `meta` = raya fina horizontal (p. ej. minutos del plan), en color de texto secundario.
 * Segmentos separados por 2 px de superficie; barra de 24 px como máximo; extremo superior redondeado.
 */
function barChart(cfg) {
  const { ancho: W, semanas } = cfg;
  const cont = h("div", { class: "graf" });
  const ml = 38, mr = 10, mb = 22;
  // `entrenos`: (semana) => [{icono, n}]; arriba de cada barra, un renglón por tipo: ícono y "2x" si hubo más de uno
  const slot = (W - ml - mr) / semanas.length;
  const ICO = slot >= 60 ? 16 : 13, PASO = ICO + 2;
  const filasIco = cfg.entrenos ? Math.max(0, ...semanas.map((s) => cfg.entrenos(s).length)) : 0;
  const franja = filasIco ? filasIco * PASO + 6 : 0;
  const mt = 14 + franja, H = (cfg.alto || 170) + franja;
  const total = (s) => s.valores.reduce((a, v) => a + v, 0);
  const clases = cfg.clases || ["s1", "s2"];
  const max = cfg.tope || Math.max(...semanas.map((s) => Math.max(total(s), s.meta || 0)), 0);
  if (max <= 0) return h("p", { class: "vacio" }, "Sin carga registrada en este periodo.");
  // `tope`: eje fijo 0–tope (p. ej. 100 %); `entero`: marcas en números enteros (conteos de sesiones)
  const ticks = cfg.tope ? [0, cfg.tope / 2, cfg.tope]
    : cfg.entero ? Array.from({ length: Math.ceil(max / Math.ceil(max / 3)) + 1 }, (_, i) => i * Math.ceil(max / 3)) : ticksNice(0, max * 1.08, 3);
  const hi = ticks[ticks.length - 1];
  const y = (v) => mt + (1 - v / hi) * (H - mt - mb);
  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.etiqueta || "Barras" });
  for (const v of ticks) {
    svg.append(sv("line", { class: "rej", x1: ml, x2: W - mr, y1: y(v), y2: y(v) }),
      sv("text", { x: ml - 6, y: y(v) + 4, "text-anchor": "end" }, fmt(v, 0)));
  }
  svg.append(sv("line", { class: "eje", x1: ml, x2: W - mr, y1: H - mb, y2: H - mb }));
  if (cfg.ref) {   // línea de referencia a todo el ancho (p. ej. meta 80 %)
    svg.append(sv("line", { class: "meta-ref", x1: ml, x2: W - mr, y1: y(cfg.ref.y), y2: y(cfg.ref.y) }, sv("title", {}, cfg.ref.etiqueta)));
  }
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
      svg.append(sv("path", { class: `serie ${clases[k] || "s" + (k + 1)}`, d }));
      base = top - 2;
    });
    if (filasIco) {   // pegados encima de la barra (o de la raya del plan), de abajo hacia arriba; la franja deja el espacio
      const piso = y(Math.max(total(s), s.meta || 0)) - 4;
      cfg.entrenos(s).forEach((e, k) => {
        const yy = piso - (k + 1) * PASO, txt = e.n > 1 ? `${e.n}x` : "";
        const x0 = cx - (ICO + (txt ? 3 + txt.length * 6 : 0)) / 2;
        const ic = icono(e.icono, ICO);
        ic.setAttribute("x", x0);
        ic.setAttribute("y", yy);
        ic.classList.add("ico-sem");
        svg.append(ic);
        if (txt) svg.append(sv("text", { class: "ico-n", x: x0 + ICO + 2, y: yy + ICO - 2 }, txt));
      });
    }
    if (s.meta) svg.append(sv("line", { class: "meta", x1: cx - ancho / 2 - 3, x2: cx + ancho / 2 + 3, y1: y(s.meta), y2: y(s.meta) }));
    if (cfg.etiquetaFinal && i === semanas.length - 1) {
      svg.append(sv("text", { class: "dato", x: Math.min(cx + 6, W - 2), y: Math.max(y(Math.max(total(s), s.meta || 0)) - 5, 10), "text-anchor": "end" }, cfg.etiquetaFinal));
    }
    if (i % cada === 0) svg.append(sv("text", { x: cx, y: H - 6, "text-anchor": "middle" }, fechaCorta2(parseFecha(s.inicio).getTime())));
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

/**
 * Mini gráfica de línea con los puntos igual de separados (como el historial de la hoja InBody): el valor va sobre
 * cada punto y la medición `prime` lleva un anillo y la palabra «prime».
 * Devuelve un `.graf` con el SVG dentro. cfg: { ancho, valores:[n], fechas:[texto] (se escriben abajo si vienen), prime:índice|null, clase:"s1"|"s2"|"neutro",
 *        fmt:(v)=>string, etiqueta:string, textos:[string] (hover de cada punto) }
 */
function miniLinea(cfg) {
  const { ancho: W, valores, fechas, prime, clase = "s1" } = cfg;
  const fmtV = cfg.fmt || ((v) => fmt(v, 1));
  const pad = 30, mt = 22, mb = fechas ? 46 : 32, H = mt + 28 + mb;
  // un valor null es una medición sin ese dato: lleva su fecha y un "—", y la línea une los puntos que sí tienen
  const hay = valores.filter((v) => v != null);
  const n = valores.length, lo = Math.min(...hay), hi = Math.max(...hay);
  const x = (i) => (n === 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (n - 1));
  const y = (v) => mt + (hi === lo ? 14 : ((hi - v) / (hi - lo)) * 28);
  const svg = sv("svg", { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": cfg.etiqueta || "Historial" });
  svg.append(sv("line", { class: "eje", x1: 4, x2: W - 4, y1: H - mb + 6, y2: H - mb + 6 }));
  if (hay.length > 1) svg.append(sv("polyline", { class: `ln ${clase}`,
    points: valores.map((v, i) => (v == null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ") }));
  valores.forEach((v, i) => {
    if (v == null) {
      svg.append(sv("text", { x: x(i), y: H - mb + 2, "text-anchor": "middle" }, "—"));
      if (fechas) svg.append(sv("text", { x: x(i), y: H - 6, "text-anchor": "middle" }, fechas[i]));
      return;
    }
    if (i === prime) svg.append(sv("circle", { class: "anillo-prime", cx: x(i), cy: y(v), r: 8.5 }));
    svg.append(sv("circle", { class: `pt ${clase}`, cx: x(i), cy: y(v), r: 4 }, sv("title", {}, (cfg.textos || [])[i] || fmtV(v))));
    svg.append(sv("text", { class: "dato", x: x(i), y: y(v) - (i === prime ? 13 : 9), "text-anchor": "middle" }, fmtV(v)));
    if (i === prime) svg.append(sv("text", { class: "prime-t", x: x(i), y: y(v) + 22, "text-anchor": "middle" }, "prime"));
    if (fechas) svg.append(sv("text", { x: x(i), y: H - 6, "text-anchor": "middle" }, fechas[i]));
  });
  return h("div", { class: "graf" }, svg);
}

// --- siluetas de entreno: puerto de la Silueta del sistema de diseño (px reales, se redibuja al cambiar el ancho) ---

const NIVEL_ZONA = { Z1: 0.25, Z2: 0.45, Z3: 0.65, Z4: 0.82, Z5: 0.97 };
const nivelZona = (z) => NIVEL_ZONA[z] ?? 0.45;
const claseZona = (z) => `g${(z || "Z2").slice(1)}`;
const minTxt = (m) => (m < 1 ? `${Math.round(m * 60)}″` : `${fmt(m, 1)}′`);

/** Polilínea [[x,y],…] -> trazo con esquinas suaves (curva cuadrática por vértice, radio ≤ r y ≤ mitad de cada lado). */
function trazoRedondo(pts, r) {
  pts = pts.filter((p, i) => i === 0 || Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) > 1e-6);
  if (pts.length < 2) return "";
  let d = `M${pts[0][0].toFixed(2)},${pts[0][1].toFixed(2)}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1], [x, y] = pts[i], [nx, ny] = pts[i + 1];
    const l1 = Math.hypot(x - px, y - py), l2 = Math.hypot(nx - x, ny - y);
    const k = Math.min(r, l1 / 2, l2 / 2);
    const a = [x - ((x - px) / l1) * k, y - ((y - py) / l1) * k], b = [x + ((nx - x) / l2) * k, y + ((ny - y) / l2) * k];
    d += ` L${a[0].toFixed(2)},${a[1].toFixed(2)} Q${x.toFixed(2)},${y.toFixed(2)} ${b[0].toFixed(2)},${b[1].toFixed(2)}`;
  }
  const u = pts[pts.length - 1];
  return `${d} L${u[0].toFixed(2)},${u[1].toFixed(2)}`;
}

/** Vuelve a dibujar cuando cambia el ancho de `cont` (y no antes de que tenga ancho). Va en el siguiente cuadro para no encadenar avisos del observador. */
function alAncho(cont, dibujar) {
  let w0 = 0;
  new ResizeObserver(() => { const w = cont.clientWidth; if (w && w !== w0) { w0 = w; requestAnimationFrame(() => dibujar(w)); } }).observe(cont);
}

/** Bloques que se repiten 3 veces o más (patrón de 1 a 3 tramos [[min, zona, opcional?]]) se juntan en un grupo. */
function agrupar(tr) {
  const igual = (a, b) => a[0] === b[0] && a[1] === b[1] && !!a[2] === !!b[2];
  const out = [];
  for (let i = 0; i < tr.length;) {
    let mejor = null;
    for (let p = 1; p <= 3; p++) {
      let k = 1;
      while (i + (k + 1) * p <= tr.length && tr.slice(i + k * p, i + (k + 1) * p).every((t, j) => igual(t, tr[i + j]))) k++;
      if (k >= 3 && (!mejor || k * p > mejor.k * mejor.p)) mejor = { p, k };
    }
    if (mejor) { out.push({ i, n: mejor.p * mejor.k, ...mejor }); i += mejor.p * mejor.k; } else { out.push({ i, n: 1 }); i++; }
  }
  return out;
}

/** Área invisible más grande que la marca: dedo, mouse y teclado muestran el tooltip. */
function capaTip(svg, tip, attrs, mostrar) {
  const r = sv("rect", { ...attrs, class: "capa", tabindex: "0" });
  for (const ev of ["pointerenter", "pointerdown", "focus"]) r.addEventListener(ev, mostrar);
  for (const ev of ["pointerleave", "blur"]) r.addEventListener(ev, tip.ocultar);
  svg.append(r);
  return r;
}

/**
 * Silueta de una sesión. tramos: [[minutos, zona, opcional?]]. opts: { alto, rachas:[{min, zona, lpm:[a,b], opcional}]
 * (de ahí salen los lpm; sin lpm no hay renglón), conCal/conEnf (la sesión ya trae su calentamiento/enfriamiento: la
 * rampa dura 1 min y sin etiqueta), conTip (false = sin tooltip, p. ej. dentro de una fila que se abre al tocar) }.
 * Una zona: etiqueta grande («20 min Z2 / 138–150 lpm»). Varias: solo minutos con guía de color; las repeticiones
 * (3 o más) se juntan en un corchete «10 × 1′ Z5 + 1′ Z1».
 */
function silueta(tramos, opts = {}) {
  const alto = opts.alto || 44, pad = 4;
  const Ri = opts.conCal ? 1 : 5, Rf = opts.conEnf ? 1 : 5;
  const total = tramos.reduce((a, t) => a + t[0], 0) + Ri + Rf;
  const una = tramos.length === 1, grupos = agrupar(tramos);
  const lpm = {};
  for (const r of opts.rachas || []) if (r.lpm && !lpm[r.zona]) lpm[r.zona] = `${r.lpm[0]}–${r.lpm[1]}`;
  const resumen = tramos.map(([m, z]) => `${fmt(m, 1)} min ${z}`).join(", ");
  const etiqueta = opts.etiqueta || `Silueta de la sesión: ${opts.conCal ? "" : "5 min de calentamiento, "}${resumen}${opts.conEnf ? "" : " y 5 min de enfriamiento"}`;
  const cont = h("div", { class: "slt-w", style: `min-height:${alto}px` });
  if (!tramos.length) return cont;
  alAncho(cont, (W) => {
    const caja = h("div", { class: "slt" });
    cont.replaceChildren(caja);
    const x = (m) => (m / total) * W, y = (n) => alto - pad - n * (alto - 2 * pad);
    const svg = sv("svg", { width: W, height: alto, viewBox: `0 0 ${W} ${alto}`, role: "img", "aria-label": etiqueta });
    caja.append(svg);
    let t0 = Ri;
    const pos = tramos.map((t) => { const p = { t, a: t0, b: t0 + t[0] }; t0 += t[0]; return p; });
    const piso = y(0.1), pri = pos[0], ult = pos[pos.length - 1];
    svg.append(sv("path", { d: `M0,${piso} L${x(Ri)},${y(nivelZona(pri.t[1]))}`, class: "slt-ln g0" }),
      sv("path", { d: `M${x(ult.b)},${y(nivelZona(ult.t[1]))} L${W},${piso}`, class: "slt-ln g0" }));
    pos.forEach(({ t, a, b }, i) => {
      const yy = y(nivelZona(t[1])), ant = pos[i - 1], sig = pos[i + 1], pts = [];
      if (ant) pts.push([x(a), (y(nivelZona(ant.t[1])) + yy) / 2]);
      pts.push([x(a), yy], [x(b), yy]);
      if (sig) pts.push([x(b), (yy + y(nivelZona(sig.t[1]))) / 2]);
      svg.append(sv("path", { d: trazoRedondo(pts, 4), class: `slt-ln ${claseZona(t[1])}${t[2] ? " opc" : ""}` }));
    });

    // etiquetas: rampas y etiqueta grande (fijas), corchetes de repeticiones y minutos sueltos con guía de color
    const items = [];
    if (!opts.conCal) items.push({ c: x(Ri / 2), top: `${fmt(Ri, 0)} min`, sub: "calentar", fija: true });
    if (una) {
      const [m, z, opc] = tramos[0];
      items.push({ c: x(Ri + m / 2), top: `${fmt(m, 1)} min ${z}`, fija: true,
        sub: [lpm[z] ? `${lpm[z]} lpm` : null, opc ? "opcional" : null].filter(Boolean).join(" · ") });
    } else {
      for (const g of grupos) {
        const a = pos[g.i].a, b = pos[g.i + g.n - 1].b;
        if (g.n === 1) {
          const [m, z] = tramos[g.i];
          items.push({ c: x((a + b) / 2), top: minTxt(m), guia: claseZona(z), yy: y(nivelZona(z)), xa: x(a) + 2, xb: x(b) - 2 });
        } else {
          const patron = tramos.slice(g.i, g.i + g.p).map(([m, z]) => `${minTxt(m)} ${z}`).join(" + ");
          items.push({ c: x((a + b) / 2), top: `${g.k} × ${patron}`, corto: `${g.k} ×`, grupo: [x(a), x(b)] });
        }
      }
    }
    if (!opts.conEnf) items.push({ c: W - x(Rf / 2), top: `${fmt(Rf, 0)} min`, sub: "enfriar", fija: true });

    const niveles = [];
    let techo = 0;
    const ocupa = (k, a, b) => (niveles[k] = niveles[k] || []).push([a, b]);
    const libre = (k, a, b) => !(niveles[k] || []).some(([p, q]) => a < q + 4 && b + 4 > p);
    const els = items.map((it) => {
      const el = h("span", { class: `slt-etq${it.fija ? " fija" : ""}${it.guia ? " min" : ""}`, "aria-hidden": "true" },
        h("b", {}, it.top), it.sub ? h("small", {}, it.sub) : null);
      caja.append(el);
      return el;
    });
    // primero lo fijo, después los corchetes y al final los minutos sueltos
    const rango = (it) => (it.fija ? 0 : it.grupo ? 1 : 2);
    const orden = items.map((it, i) => i).sort((p, q) => rango(items[p]) - rango(items[q]));
    for (const i of orden) {
      const it = items[i], el = els[i];
      let w = el.offsetWidth, hh = el.offsetHeight, izq = Math.min(Math.max(it.c - w / 2, 0), Math.max(W - w, 0));
      // corchete sin lugar para el texto completo: solo «10 ×» (el color dice las zonas y el tooltip el detalle)
      if (it.grupo && !(libre(0, izq, izq + w) && libre(1, izq, izq + w))) {
        el.firstChild.textContent = it.corto;
        w = el.offsetWidth; izq = Math.min(Math.max(it.c - w / 2, 0), Math.max(W - w, 0));
      }
      el.style.left = `${izq}px`;
      if (it.fija) {
        el.style.bottom = "calc(100% + 2px)";
        for (const k of una ? [0] : [0, 1]) ocupa(k, izq, izq + w);
        techo = Math.max(techo, hh + 2);
      } else if (it.grupo) {
        const [a, b] = it.grupo;
        caja.append(h("span", { class: "slt-corchete", style: `left:${a + 1}px;width:${Math.max(b - a - 2, 2)}px` }));
        el.style.bottom = "calc(100% + 9px)";
        for (const k of [0, 1]) ocupa(k, Math.min(izq, a), Math.max(izq + w, b));
        techo = Math.max(techo, hh + 9);
      } else {
        // la guía puede ir en cualquier punto de su tramo, pero no cruza etiquetas de niveles de abajo
        const xs = [];
        for (let d = 0; d <= Math.max(it.c - it.xa, it.xb - it.c); d += 2) xs.push(it.c - d, it.c + d);
        let hallado = null;
        for (let k = 0; k < 5 && !hallado; k++) {
          for (const gx of xs) {
            if (gx < it.xa || gx > it.xb) continue;
            const iz = Math.min(Math.max(gx - w / 2, 0), Math.max(W - w, 0));
            let ok = libre(k, iz, iz + w);
            for (let j = 0; ok && j < k; j++) ok = libre(j, gx - 1, gx + 1);
            if (ok) { hallado = { k, gx, iz }; break; }
          }
        }
        if (!hallado) { el.remove(); continue; }   // no cabe: el tooltip del tramo lo dice
        const { k, gx, iz } = hallado;
        ocupa(k, iz, iz + w);
        const L = 6 + k * 14;
        el.style.left = `${iz}px`;
        el.style.bottom = `calc(100% + ${L}px)`;
        caja.append(h("span", { class: `slt-guia ${it.guia}`, style: `left:${gx}px;top:${-L}px;height:${L + it.yy}px`, "aria-hidden": "true" }));
        techo = Math.max(techo, L + hh);
      }
    }
    caja.style.marginTop = `${techo + 4}px`;

    if (opts.conTip === false) return;
    const tip = tooltipEn(caja);
    pos.forEach(({ t: [m, z, opc], a, b }) => {
      const texto = `${minTxt(m)} · ${z}${opc ? " (opcional)" : ""}${lpm[z] ? `\n${lpm[z]} lpm` : ""}`;
      capaTip(svg, tip, { x: x(a), y: 0, width: Math.max(x(b) - x(a), 1), height: alto, "aria-label": texto.replace("\n", " · ") },
        () => tip.mostrar(texto, x((a + b) / 2), y(nivelZona(z)) + 2));
    });
  });
  return cont;
}

/** Catálogo de tipos: forma [[d, n] | [d, n1, n2]] (niveles 0–1) -> silueta en tinta, sin zonas, etiquetas ni tooltip. */
function siluetaForma(forma, alto = 48, etiqueta) {
  const pad = 4, total = forma.reduce((a, f) => a + f[0], 0) || 1;
  const cont = h("div", { class: "slt-w", style: `min-height:${alto}px` });
  alAncho(cont, (W) => {
    const caja = h("div", { class: "slt", style: "margin-top:6px" });
    cont.replaceChildren(caja);
    const y = (n) => alto - pad - n * (alto - 2 * pad);
    const svg = sv("svg", { width: W, height: alto, viewBox: `0 0 ${W} ${alto}`, role: "img", "aria-label": etiqueta || "Forma de la sesión" });
    const pts = [];
    let x0 = 0;
    for (const [d, n, n2] of forma) {
      const x1 = x0 + (d / total) * W;
      pts.push([x0, y(n)], [x1, y(n2 === undefined ? n : n2)]);
      x0 = x1;
    }
    svg.append(sv("path", { d: trazoRedondo(pts, 5), class: "slt-ln tinta" }));
    caja.append(svg);
  });
  return cont;
}

/** Sesión: [[minutos, zona, opcional?]] -> silueta con el color Garmin de cada zona. `rampas`: la sesión (con_calentamiento…). */
const siluetaSesion = (sil, alto = 40, conTip = true, rachas = null, rampas = {}) =>
  silueta(sil, { alto, conTip, rachas: rachas || [], conCal: !!rampas.con_calentamiento, conEnf: !!rampas.con_enfriamiento });
