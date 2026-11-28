// Vista Progreso: Corridas (periodo, gráficas, marcas) y Cuerpo (InBody, recuperación). Usa lo de vista_comun.js.
// --- Progreso ---

let periodo = 8;
let periodoTodo = false;   // «Todo el plan»: la ventana son las semanas del plan, no las últimas `periodo`

/** Ventana del periodo elegido sobre una serie por semanas (de la más vieja a la actual): «todo el plan» = las semanas entre
 *  `desde` y `hasta` que manda Python; si no, las últimas `n` que terminan en la semana actual. Python ya dejó semanas de sobra. */
function ventanaSemanas(serie, ops, n = periodo, todo = periodoTodo) {
  const t = todo ? (ops || []).find((p) => p.todo) : null;
  if (t && t.desde) return serie.filter((s) => s.inicio >= t.desde && s.inicio <= t.hasta);
  let i = serie.length - 1;
  while (i > 0 && !serie[i].actual) i--;
  return serie.slice(Math.max(0, i - n + 1), i + 1);
}
const opsDe = (d) => (d.progreso || {}).periodos;
let planSel = null;

const NUMEROS = () => ({
  corridas: [T("sitio.num.corridas"), (v) => fmt(v, 1), ""], minutos: [T("sitio.num.minutos"), (v) => fmt(v, 0), "min"],
  km: [T("sitio.num.km"), (v) => fmt(v, 1), "km"], ritmo_ref: [T("sitio.num.ritmo_ref"), (v) => mmss(v), "/km"], pct_trote: [T("sitio.num.pct_trote"), (v) => fmt(v, 0), "%"],
});

/** Fila de números del periodo (ya calculados en Python) con el cambio contra el periodo anterior. */
function filaNumeros(d) {
  const prog = d.progreso || {};
  const items = ((prog.numeros || {}).periodos || {})[String(periodo)] || [];
  return DS.tiles({ etiqueta: T("sitio.num.etiqueta", { n: periodo }), clase: "ancha" }, ...items.map((x) => {
    let [nombre, fv, unidad] = NUMEROS()[x.id] || [x.id, (v) => fmt(v, 1), ""];
    if (x.id === "ritmo_ref" && prog.fc_ref) nombre = T("sitio.mej.ritmo", { fc: prog.fc_ref });
    const cambio = x.valor == null ? T("sitio.num.sin_corridas")
      : x.anterior == null ? T("sitio.num.sin_anterior")
        : x.delta === 0 || x.delta == null ? T("sitio.num.igual")
          : T("sitio.num.vs", { f: x.delta > 0 ? "▲" : "▼", v: fv(Math.abs(x.delta)), u: x.id === "ritmo_ref" ? "/km" : unidad && unidad !== "/km" ? " " + unidad : "" });
    return DS.tile({ k: nombre, valor: x.valor == null ? "—" : fv(x.valor), unidad: x.valor != null && unidad ? unidad : null, delta: cambio, deltaClase: x.bueno ? "" : "neutro" });
  }));
}

let subProgreso = "corridas";   // "corridas" | "cuerpo", lo decide la ruta (#progreso o #progreso/cuerpo)

/** Control segmentado Corridas | Cuerpo. Cambia la ruta; mostrarVista hace el resto. */
function selectorProgreso() {
  return DS.segmento({ id: "prog-subtabs", clase: "ancha", etiqueta: T("sitio.prog.titulo"), activo: subProgreso,
    opciones: [{ id: "corridas", texto: T("sitio.prog.corridas") }, { id: "cuerpo", texto: T("sitio.prog.cuerpo") }],
    onCambio: (id) => { location.hash = id === "cuerpo" ? "#progreso/cuerpo" : "#progreso"; } });
}

/** Cabecera de Progreso > Cuerpo: «Agregar medición» (solo si la web trae ui.cuerpo_nuevo; en el sitio local no hay botón). */
function cabCuerpo() {
  const url = ui().cuerpo_nuevo;
  return url ? h("div", { class: "cuerpo-cab" }, h("a", { class: "boton chico", href: url }, T("sitio.ib.agregar"))) : null;
}

/** Opciones del selector de periodo: las manda Python (4/8/12 o, con plan, hasta «todo el plan»); la página solo elige. */
function opcionesPeriodo(d) {
  const ops = (d.progreso || {}).periodos;
  return ops && ops.length ? ops : [4, 8, 12].map((n) => ({ n, todo: false }));
}

function renderProgreso(d) {
  const ops = opcionesPeriodo(d);
  if (periodoTodo && !ops.some((p) => p.todo)) periodoTodo = false;   // ya no hay plan
  if (!periodoTodo && ![4, 8, 12].includes(periodo)) periodo = 8;
  if (periodoTodo) periodo = ops.find((p) => p.todo).n;   // para los textos y los números del periodo
  PINTAR.progreso = [];
  PINTAR.cuerpo = [];
  const raiz = $("vista-progreso");
  const prog = d.progreso || {};
  const hayCorridas = (prog.corridas || []).length || (prog.semanas || []).some((x) => (x.minutos || 0) > 0);
  raiz.replaceChildren(selectorProgreso(),
    h("div", { class: "sub", id: "prog-corridas", hidden: subProgreso !== "corridas" }, ...(!hayCorridas ? [   // sin una sola corrida: un estado vacío que dice cómo llenarlo
      DS.tarjeta({ titulo: T("sitio.cp.titulo"), clase: "ancha" }, DS.estadoVacio({ icono: null, titulo: T("sitio.cp.vacio_t"), texto: T("sitio.cp.vacio_x") }))] : [
      DS.segmento({ etiqueta: T("sitio.prog.periodo"), modo: "grupo", clase: "ancha", activo: periodoTodo ? "todo" : periodo, opciones: opcionesPeriodo(d).map((p) => ({ id: p.todo ? "todo" : p.n, texto: p.todo ? T("sitio.prog.todo") : T("sitio.prog.n_sem", { n: p.n }) })),
        onCambio: (n) => { periodoTodo = n === "todo"; periodo = periodoTodo ? periodo : Number(n); renderProgreso(d); mostrarSubvista(); REDIBUJAR.progreso(); } }),
      filaNumeros(d),
      tarjetaMejora(d),
      tarjetaCorridasProgreso(d),
      tarjetaIntensidadSemanas(d),
      tarjetaMarcasYCarreras(d),
      d.detalles && d.detalles.carga ? tarjetaCarga(d.detalles) : null]).filter(Boolean)),
    h("div", { class: "sub", id: "prog-cuerpo", hidden: subProgreso !== "cuerpo" },
      ...[cabCuerpo(), tarjetaRecuperacion(d), tarjetaComposicion(d.composicion)].filter(Boolean)));
}

/** Muestra Corridas o Cuerpo según `subProgreso` y marca el botón elegido. */
function mostrarSubvista() {
  const corr = $("prog-corridas"), cue = $("prog-cuerpo");
  if (!corr || !cue) return;
  corr.hidden = subProgreso !== "corridas";
  cue.hidden = subProgreso !== "cuerpo";
  document.querySelectorAll("#prog-subtabs button").forEach((b) => {
    const on = b.dataset.id === subProgreso;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
}

function contextoPeriodo(d) {
  const prog = d.progreso || {};
  const hoyMs = parseFecha((d.generado || "").slice(0, 10) || "2000-01-01").getTime();
  const t = periodoTodo ? (prog.periodos || []).find((p) => p.todo) : null;
  const corte = t && t.desde ? parseFecha(t.desde).getTime() - 86400000 : hoyMs - periodo * 7 * 86400000;
  const fin = t && t.hasta ? Math.max(hoyMs, parseFecha(t.hasta).getTime() + 6 * 86400000) : hoyMs;
  return { prog, dominio: [corte + 86400000, fin],
    aire: (prog.corridas || []).filter((r) => !r.caminadora && parseFecha(r.fecha).getTime() > corte && parseFecha(r.fecha).getTime() <= fin) };
}

function graficaCorridas(d, ancho, id) {
  const { aire, dominio, prog } = contextoPeriodo(d);
  const ref = prog.fc_ref;
  const cfg = {
    ritmo: { filtro: (r) => r.ritmo_ref_s != null, y: (r) => r.ritmo_ref_s, prom: (r) => r.ritmo_ref_prom_s,
      nota: T("sitio.gc.ritmo_nota", { ref }),
      extra: { fmtY: mmss, invertir: true, etiqueta: T("sitio.gc.ritmo_et", { ref }) },
      vacio: T("sitio.gc.ritmo_vacio"),
      texto: (r) => T("sitio.gc.ritmo_txt", { f: fechaLarga(r.fecha), r: mmss(r.ritmo_ref_s), ref, fc: r.fc_trote ? T("sitio.gc.trotaste", { v: fmt(r.fc_trote, 0) }) : "" }) },
    deriva: { filtro: (r) => r.deriva_pct != null, y: (r) => r.deriva_pct, all: true,
      nota: T("sitio.gc.deriva_nota"),
      extra: { fmtY: (v) => fmt(v, 0), ref: { y: 5, etiqueta: "5 %" }, etiqueta: T("sitio.gc.deriva_et") },
      vacio: T("sitio.gc.deriva_vacio"),
      texto: (r) => T("sitio.gc.deriva_txt", { f: fechaLarga(r.fecha), v: fmt(r.deriva_pct, 1), ok: r.deriva_ok ? "✓" : "⚠" }) },
    pct: { filtro: (r) => r.pct_trote != null, y: (r) => r.pct_trote, nota: T("sitio.gc.pct_nota"),
      extra: { fmtY: (v) => fmt(v, 0), etiqueta: T("sitio.gc.pct_et") },
      vacio: T("sitio.gc.pct_vacio"),
      texto: (r) => T("sitio.gc.pct_txt", { f: fechaLarga(r.fecha), v: fmt(r.pct_trote, 0), t: fmt(r.trote_min, 0), c: fmt(r.camina_min, 0) }) },
  }[id];
  const base = cfg.all ? (prog.corridas || []).filter((r) => parseFecha(r.fecha).getTime() > dominio[0] - 86400000) : aire;
  const pts = base.filter(cfg.filtro).map((r) => ({ fecha: r.fecha, y: cfg.y(r), r }));
  const extra = { ...cfg.extra, ...(cfg.prom ? { promedio: pts.map((p) => cfg.prom(p.r) ?? null) } : {}) };
  return h("div", {}, h("p", { class: "nota" }, cfg.nota),
    pts.length ? lineChart({ ancho, serie: pts, dominio, marcadores: !cfg.prom, puntos: !!cfg.prom, ...extra, texto: (p) => cfg.texto(p.r) })
      : DS.estadoVacio({ icono: null, titulo: cfg.vacio }));
}

function graficaVolumen(d, ancho) {
  const prog = d.progreso || {};
  const semanas = ventanaSemanas(prog.semanas || [], prog.periodos);
  const hay = semanas.some((s) => (s.minutos || 0) > 0 || s.plan_min);
  if (!hay) return DS.estadoVacio({ icono: null, titulo: T("sitio.vol.sin") });
  const barras = semanas.map((s) => ({ inicio: s.inicio, actual: s.actual, valores: [s.min_trote || 0, s.min_camina || 0], meta: s.plan_min || 0, s }));
  return h("div", {}, h("p", { class: "nota" }, T("sitio.vol.nota")),
    barChart({ ancho, semanas: barras, clases: ["s1", "walk"], etiqueta: T("sitio.vol.et"),
      entrenos: semanas.some((s) => (s.entrenos || []).length) ? (b) => b.s.entrenos || [] : null,
      texto: (b) => T("sitio.vol.txt", { f: fechaLarga(b.inicio), m: fmt(b.s.minutos, 0), plan: b.s.plan_min ? T("sitio.vol.plan", { p: b.s.plan_min }) : "", k: fmt(b.s.km), t: fmt(b.s.min_trote, 0), e: textoEntrenos(b.s.entrenos) }) }),
    leyendaIconos(semanas, [[COLOR_CLASE.s1, T("sitio.vol.trote")], [COLOR_CLASE.walk, T("sitio.vol.camina")], ["raya", T("sitio.vol.plan_l")]]),
    tablaDatos(T("sitio.vol.cols").split(","), semanas.slice().reverse().map((s) =>
      [fechaLarga(s.inicio), fmt(s.minutos, 0), s.plan_min ?? "—", fmt(s.km), fmt(s.min_trote, 0), fmt(s.min_camina, 0)]), T("sitio.vol.tabla")));
}

function graficaKm(d, ancho) {
  const semanas = ventanaSemanas((d.progreso || {}).semanas || [], opsDe(d));
  if (!semanas.some((s) => (s.km || 0) > 0)) return DS.estadoVacio({ icono: null, titulo: T("sitio.vol.sin") });
  return h("div", {}, h("p", { class: "nota" }, T("sitio.km.nota")),
    barChart({ ancho, semanas: semanas.map((s) => ({ inicio: s.inicio, actual: s.actual, valores: [s.km || 0], s })), clases: ["s1"],
      etiqueta: T("sitio.km.et"),
      texto: (b) => T("sitio.km.txt", { f: fechaLarga(b.inicio), k: fmt(b.s.km) }) }),
    tablaDatos(T("sitio.km.cols").split(","), semanas.slice().reverse().map((s) => [fechaLarga(s.inicio), fmt(s.km)]), T("sitio.vol.tabla")));
}

function tarjetaCorridasProgreso(d) {
  const prog = d.progreso || {};
  const hayCaminatas = ((prog.numeros || {}).caminatas || {})[String(periodo)];
  const hayDeriva = (prog.corridas || []).some((r) => r.deriva_pct != null);
  const vistas = [{ etiqueta: T("sitio.cp.volumen"), pintar: (a) => graficaVolumen(d, a) },
    { etiqueta: T("sitio.cp.km"), pintar: (a) => graficaKm(d, a) },
    { etiqueta: T("sitio.cp.ritmo"), pintar: (a) => graficaCorridas(d, a, "ritmo") },
    ...(hayDeriva ? [{ etiqueta: T("sitio.cp.deriva"), pintar: (a) => graficaCorridas(d, a, "deriva") }] : []),
    ...(hayCaminatas ? [{ etiqueta: T("sitio.cp.pct"), pintar: (a) => graficaCorridas(d, a, "pct") }] : [])];
  return tarjetaConVistas("progreso", T("sitio.cp.titulo"), T("sitio.cp.ult", { n: periodo }), vistas, { clase: "ancha", pie: tablaCorridas(prog.corridas || []) });
}

function tablaCorridas(corridas) {
  const orden = corridas.slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
  const celdas = (r) => [fechaLarga(r.fecha), h("span", { class: "con-ico" }, DS.ico(r.icono || (r.carrera ? "medalla" : "correr")), `${r.sesion || "—"}${r.carrera ? T("sitio.tc.carrera") : ""}`), fmt(r.minutos, 0), fmt(r.km),
    r.pct_trote == null ? "—" : `${fmt(r.pct_trote, 0)} %`,
    r.caminadora ? T("sitio.tc.cam") : r.ritmo_trote_s == null ? "—" : mmss(r.ritmo_trote_s),
    r.ritmo_ref_s == null ? "—" : mmss(r.ritmo_ref_s), r.deriva_pct == null ? "—" : `${fmt(r.deriva_pct, 1)} %`,
    r.fc_prom == null ? "—" : fmt(r.fc_prom, 0), textoEsfuerzo(r) || "—"];
  const cab = T("sitio.tc.cab").split(",");
  return [DS.desplegable({ titulo: T("sitio.tc.ver"), liga: true },
    orden.length ? DS.tabla({ etiqueta: T("sitio.cp.titulo"), columnas: cab.map((texto, i) => ({ texto, num: i > 1 })), filas: orden.map((r) => ({ celdas: celdas(r) })) })
      : DS.estadoVacio({ icono: null, titulo: T("sitio.tc.sin") }),
    orden.some((r) => r.caminadora) ? h("p", { class: "nota" }, T("sitio.tc.nota")) : null)];
}

// --- intensidad por semana (80/20) ---

const intGrupos = () => [["bajo", T("sitio.ig.bajo"), "z1"], ["limbo", T("sitio.ig.limbo"), "z3"], ["alto", T("sitio.ig.alto"), "z4"]];

/** Barras apiladas al 100 % por semana (Bajo / Limbo / Alto) con la raya de la meta de 80 % bajo. Sigue el selector 4/8/12. */
function tarjetaIntensidadSemanas(d) {
  const todas = (d.progreso || {}).intensidad_semanas || [];
  if (!todas.length) return null;
  const caja = h("div", { class: "chart-wrap" });
  const pie = h("div", { class: "pie-graf" });
  const pintar = () => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    const sem = ventanaSemanas(todas, opsDe(d));
    const con = sem.filter((x) => Object.values(x.minutos || {}).some((v) => v > 0));
    if (!con.length) { caja.replaceChildren(DS.estadoVacio({ icono: null, titulo: T("sitio.ig.sin") })); pie.replaceChildren(); return; }
    caja.replaceChildren(barChart({
      ancho, alto: 130, tope: 100, ref: { y: 80, etiqueta: T("sitio.ig.meta_ref") }, clases: intGrupos().map((g) => g[2]),
      etiqueta: T("sitio.ig.et"),
      semanas: sem.map((x) => ({ inicio: x.inicio, actual: x.actual, valores: intGrupos().map(([k]) => x[k] || 0), x })),
      texto: (b) => T("sitio.ig.txt", { f: fechaLarga(b.inicio), b: fmt(b.x.bajo, 0), l: fmt(b.x.limbo, 0), a: fmt(b.x.alto, 0) }),
    }));
    pie.replaceChildren(DS.leyenda([...intGrupos().map(([, n, c]) => [COLOR_CLASE[c], n]), ["raya-disc", T("sitio.ig.leyenda")]]),
      tablaDatos(T("sitio.ig.cols").split(","), con.slice().reverse().map((x) => [fechaLarga(x.inicio), fmt(x.bajo, 0), fmt(x.limbo, 0), fmt(x.alto, 0)])));
  };
  PINTAR.progreso.push(pintar);
  return DS.tarjeta({ titulo: T("sitio.ig.titulo"), clase: "ancha" },
    h("p", { class: "nota" }, T("sitio.ig.nota", { n: periodo })),
    caja, pie);
}

// --- mejores marcas y carreras ---

const fechaConAnio = (iso, ref) => {
  const f = parseFecha(iso), anioRef = parseFecha((ref || iso).slice(0, 10)).getFullYear();
  return `${f.getDate()} ${MESES[f.getMonth()]}${f.getFullYear() !== anioRef ? ` ${f.getFullYear()}` : ""}`;
};

/** Mejores marcas (siempre que haya), como entradas de DS.ranking. */
function datosMarcas(d) {
  return (d.mejores_marcas || []).map((x) => {
    const larga = x.clave === "larga";
    const fecha = fechaConAnio(x.fecha, d.generado);
    return { icono: x.icono || "medalla", nombre: x.nombre, nueva: !!x.nuevo, valor: larga ? `${fmt(x.distancia_km, 2)} km` : tiempoLargo(x.tiempo_s),
      fecha: larga ? `${tiempoLargo(x.tiempo_s)} · ${fecha}` : fecha,
      etiqueta: T("sitio.mc.etiqueta", { n: x.nombre, v: larga ? T("sitio.mc.km_en", { d: fmt(x.distancia_km, 2), t: tiempoLargo(x.tiempo_s) }) : tiempoLargo(x.tiempo_s), f: fecha, nueva: x.nuevo ? T("sitio.mc.nueva") : "" }) };
  });
}

/** Una fila nombre/valor del detalle de una carrera (null si no hay dato). */
function filaStat(nombre, valor) {
  return valor == null ? null : [nombre, valor];
}

/** Ritmo de cada km como barras pequeñas: más larga = más rápido. El valor siempre va en texto. */
function barrasKm(c) {
  const km = c.km || [];
  if (!km.length) return null;
  const rapido = Math.min(...km), lento = Math.max(...km);
  return h("div", { class: "ritmos-km" }, h("h3", {}, T("sitio.rk.titulo")),
    h("div", { role: "list" }, km.map((s, i) => h("div", { class: "rk", role: "listitem", "aria-label": T("sitio.rk.aria", { i: i + 1, p: mmss(s) }) },
      h("span", { class: "rk-n" }, i + 1),
      h("span", { class: "rk-barra" }, h("i", { style: `width:${Math.round(55 + 45 * (lento === rapido ? 1 : (lento - s) / (lento - rapido)))}%`, class: s === rapido ? "rapido" : "" })),
      h("span", { class: `rk-v${s === rapido ? " rapido" : ""}` }, mmss(s))))),
    h("p", { class: "nota" }, T("sitio.rk.nota")));
}

function zonasCarrera(c) {
  const z = c.zonas_min;
  if (!z) return null;
  const ks = ["Z1", "Z2", "Z3", "Z4", "Z5"], total = ks.reduce((a, k) => a + z[k], 0);
  if (total <= 0) return null;
  return h("div", {}, h("h3", {}, T("sitio.zc.titulo")),
    h("div", { class: "zbar", role: "img", "aria-label": ks.map((k) => `${k} ${fmt(z[k], 0)} min`).join(", ") },
      ks.filter((k) => z[k] > 0).map((k) => h("div", { style: `flex:${z[k]} 1 0;background:var(--${k.toLowerCase()})` }))),
    DS.leyenda(ks.map((k) => [`var(--${k.toLowerCase()})`, `${k} ${fmt(z[k], 0)}'`])));
}

function comparacionCarrera(c) {
  const k = c.comparacion;
  if (!k) return null;
  const rel = (v, unidad, menosBueno) => (v === 0 || v == null ? null : `${unidad(Math.abs(v))} ${v < 0 ? menosBueno[0] : menosBueno[1]}`);
  const partes = [rel(k.dif_tiempo_s, tiempoLargo, [T("sitio.cc.mas_rapido"), T("sitio.cc.mas_lento")]), rel(k.dif_ritmo_s, (s) => `${mmss(s)} /km`, [T("sitio.cc.menos_km"), T("sitio.cc.mas_km")]),
    rel(k.dif_fc, (v) => `${fmt(v, 0)} ${T("sitio.lpm")}`, [T("sitio.cc.menos_fc"), T("sitio.cc.mas_fc")])].filter(Boolean);
  return h("div", {}, h("h3", {}, T("sitio.cc.titulo")),
    h("p", { class: "nota" }, T("sitio.cc.en", { f: fechaConAnio(k.fecha), d: fmt(k.distancia_km, 2), t: tiempoLargo(k.tiempo_s) })),
    h("p", {}, partes.length ? T("sitio.cc.ahora", { p: partes.join(" · ") }) : T("sitio.cc.igual")));
}

/** Una carrera como entrada de DS.ranking: fecha, resumen, filas de datos y, abajo, ritmo por km, zonas y comparación. */
function carreraDetalle(c, abierta) {
  return { icono: c.icono || "medalla", fecha: fechaLarga(c.fecha), resumen: `${fmt(c.distancia_km, 2)} km · ${tiempoLargo(c.tiempo_s)}`, abierta,
    filas: [
      filaStat(T("sitio.cd.dist"), `${fmt(c.distancia_km, 2)} km`), filaStat(T("sitio.cd.tiempo"), tiempoLargo(c.tiempo_s)),
      filaStat(T("sitio.cd.ritmo"), c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : null),
      filaStat(T("sitio.cd.fc"), c.fc_prom != null ? `${fmt(c.fc_prom, 0)} / ${c.fc_max != null ? fmt(c.fc_max, 0) : "—"} ${T("sitio.lpm")}` : null),
      filaStat(T("sitio.cd.km_rapido"), c.km_mas_rapido_s ? `${mmss(c.km_mas_rapido_s)} /km` : null),
      filaStat(T("sitio.cd.cadencia"), c.cadencia ? T("sitio.cd.pasos", { c: c.cadencia }) : null),
      filaStat(T("sitio.cd.desnivel"), c.desnivel_m != null ? `+${c.desnivel_m} m` : null)].filter(Boolean),
    cuerpo: [barrasKm(c), zonasCarrera(c), comparacionCarrera(c)].filter(Boolean) };
}

/** "Marcas y carreras": marcas arriba y, si hay carreras, su lista debajo. Sin ninguna de las dos, no sale. */
function tarjetaMarcasYCarreras(d) {
  const marcas = datosMarcas(d), cs = d.carreras || [];
  if (!marcas.length && !cs.length) return null;
  const r = DS.ranking({ marcas, carreras: cs.map((x, i) => carreraDetalle(x, i === 0 && abrirCarrera)) });
  const lista = r.querySelector(".carreras");
  if (lista) { lista.id = "prog-carreras"; lista.before(h("h3", { class: "sub-carreras" }, T("sitio.mr.carreras"))); }
  return DS.tarjeta({ titulo: T("sitio.mr.titulo"), clase: "ancha" }, r);
}

// --- Composición corporal estilo InBody ---

const ZONA_SIM = { bajo: "▼", normal: "✓", alto: "▲" };
const zonaTxt = (z) => [ZONA_SIM[z], T(`sitio.ib.zona_${z}`)];
const fechaMes = (iso) => { const f = parseFecha(iso); return `${f.getDate()} ${MESES[f.getMonth()]} ${String(f.getFullYear()).slice(2)}`; };
const kg1 = (v) => fmt(v, 1);

/** Una barra de la hoja como fila de DS.ibGrupo: la barra llega a `pos` y su valor va al final. */
function filaInbody(f) {
  const txt = f.estimado ? `≈${fmt(f.valor, 1)}` : fmt(f.valor, 1);
  const [simbolo, zona] = zonaTxt(f.zona);
  const etiqueta = T("sitio.ib.aria", { n: f.nombre, v: fmt(f.valor, 1), u: f.unidad, pct: f.pct != null ? T("sitio.ib.aria_pct", { p: f.pct }) : "", est: f.estimado ? T("sitio.ib.aria_est") : "", z: zona });
  return { nombre: f.nombre, unidad: f.unidad, zona: f.zona, textoZona: `${simbolo} ${zona}`, aria: etiqueta,
    normal: [f.normal_pos[0] * 100, (f.normal_pos[1] - f.normal_pos[0]) * 100], barra: f.pos * 100, valor: txt, dentro: f.pos > 0.8,
    ticks: f.escala.map((v, i) => [(i / (f.escala.length - 1)) * 100, fmt(v, v % 1 ? 1 : 0)]) };
}

function grupoInbody(titulo, filas) {
  if (!filas || !filas.length) return null;
  const n = filas[0].normal_pos;
  return DS.ibGrupo({ titulo, franja: [{ texto: T("sitio.ib.f_bajo"), pct: n[0] * 100 }, { texto: T("sitio.ib.f_normal"), pct: (n[1] - n[0]) * 100, normal: true }, { texto: T("sitio.ib.f_alto"), pct: (1 - n[1]) * 100 }],
    filas: filas.map(filaInbody) });
}

function historialInbody(c) {
  const hist = c.historial || [];
  if (!hist.length) return null;
  const caja = h("div", { class: "ib-hist" });
  const primeIdx = hist.findIndex((x) => x.es_prime);
  const defs = [[T("sitio.ib.peso"), "peso_kg", "neutro"], [T("sitio.ib.mme"), "mme_kg", "s1"], [T("sitio.ib.pgc"), "pgc", "s2"]];
  const pintar = () => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    caja.replaceChildren(...defs.map(([nombre, campo, clase], k) => h("div", { class: "ib-mini" }, h("h3", {}, nombre),
      miniLinea({ ancho, valores: hist.map((x) => x[campo]), clase, prime: primeIdx >= 0 ? primeIdx : null, fmt: kg1,
        fechas: k === defs.length - 1 ? hist.map((x) => fechaMes(x.fecha)) : null, etiqueta: T("sitio.ib.hist_de", { n: nombre }),
        textos: hist.map((x) => `${fechaMes(x.fecha)} · ${kg1(x[campo])}${x.es_prime ? T("sitio.ib.prime") : ""}`) }))));
  };
  PINTAR.cuerpo.push(pintar);
  const meta = c.meta || {};
  return h("div", { class: "ib-grupo" }, h("h3", {}, T("sitio.ib.hist_titulo")), caja,
    h("p", { class: "titular" }, meta.faltan_pgc > 0 ? T("sitio.ib.faltan_pgc", { v: fmt(meta.faltan_pgc, 1) }) : T("sitio.ib.super_pgc")),
    meta.mme_ok ? h("p", { class: "nota" }, T("sitio.ib.mme_ok")) : h("p", { class: "nota" }, T("sitio.ib.faltan_mme", { v: fmt(meta.faltan_mme, 1) })));
}

function puntuacionInbody(c) {
  const pts = c.puntuacion || [], v = c.visceral;
  if (!pts.length && !v) return null;
  const ult = [...pts].reverse().find((p) => p.puntos != null);
  const [simbolo, clase] = v ? (v.zona === "normal" ? ["✓", "ok"] : ["!", "warn"]) : [];
  return h("div", { class: "ib-grupo" }, DS.ibPuntuacion({
    puntuacion: ult ? { valor: fmt(ult.puntos, 0), delta: ult.delta != null ? `${ult.delta > 0 ? "▲" : ult.delta < 0 ? "▼" : "="}${Math.abs(ult.delta)}` : null, deltaClase: ult.delta > 0 ? "" : "neutro" } : null,
    visceral: v ? { valor: fmt(v.valor, 0), rango: `${v.rango[0]}–${v.rango[1]}`, clase, simbolo,
      texto: T(v.zona === "normal" ? "sitio.ib.dentro" : v.zona === "alto" ? "sitio.ib.encima" : "sitio.ib.debajo") } : null }),
    ult ? miniPuntuacion(pts) : null);
}

/** Historial de la puntuación: con un solo punto, solo el punto y una nota. */
function miniPuntuacion(pts) {
  const caja = h("div", { class: "ib-punt-g" });
  PINTAR.cuerpo.push(() => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    const graf = miniLinea({ ancho, valores: pts.map((p) => p.puntos), clase: "s1", prime: null, fmt: (v) => fmt(v, 0),
      fechas: pts.map((p) => fechaMes(p.fecha)), etiqueta: T("sitio.ib.hist_punt") });
    const con = pts.filter((p) => p.puntos != null).length;
    caja.replaceChildren(graf, ...(con === 1 ? [h("p", { class: "nota" }, T("sitio.ib.se_llena"))]
      : con < pts.length ? [h("p", { class: "nota" }, T("sitio.ib.sin_hoja"))] : []));
  });
  return caja;
}

const segmentos = () => { const n = T("sitio.ib.seg").split(","); return ["brazo_izq", "brazo_der", "tronco", "pierna_izq", "pierna_der"].map((k, i) => [k, n[i]]); };

function hojaCompleta(c) {
  const hoja = c.hoja;
  if (!hoja) return null;
  const tabla = (cabeza, filas) => DS.tabla({ etiqueta: cabeza.filter(Boolean).join(", ") || T("sitio.ib.hoja"),
    columnas: cabeza.map((texto, i) => ({ texto, num: i > 0 })), filas: filas.map((celdas) => ({ celdas })) });
  const zonaStr = (z) => zonaTxt(z).join(" ");
  const bloques = [];
  const barras = [...(hoja.musculo_grasa || []), ...(hoja.obesidad || [])];
  if (barras.length) bloques.push(h("h3", {}, T("sitio.ib.mg_ob")),
    tabla(T("sitio.ib.cols_mg").split(","), barras.map((f) => [f.nombre, `${f.estimado ? "≈" : ""}${fmt(f.valor, 1)} ${f.unidad}`,
      f.pct != null ? `${f.pct} %` : "—", `${fmt(f.normal[0], 1)}–${fmt(f.normal[1], 1)}${f.pct != null ? " %" : ""}`, zonaStr(f.zona)])));
  const cp = hoja.control_peso;
  if (cp) bloques.push(h("h3", {}, T("sitio.ib.cp")), tabla(["", "kg"], [[T("sitio.ib.cp_ideal"), fmt(cp.peso_ideal_kg, 1)], [T("sitio.ib.cp_ctl"), fmt(cp.control_peso_kg, 1)],
    [T("sitio.ib.cp_grasa"), fmt(cp.control_grasa_kg, 1)], [T("sitio.ib.cp_musculo"), fmt(cp.control_musculo_kg, 1)]]));
  const grupos = [...new Set((hoja.rangos || []).map((r) => r.grupo))];
  for (const g of grupos) bloques.push(h("h3", {}, g), tabla(T("sitio.ib.cols_rango").split(","), hoja.rangos.filter((r) => r.grupo === g).map((r) =>
    [r.nombre, `${fmt(r.valor, 2)}${r.unidad ? " " + r.unidad : ""}`, `${fmt(r.min, 2)}–${fmt(r.max, 2)}`, zonaStr(r.zona)])));
  if (hoja.segmental_magra || hoja.segmental_grasa) {
    const f = (o, k) => (o && o[k] ? [`${fmt(o[k][0], 2)} kg`, `${fmt(o[k][1], 0)} %`] : ["—", "—"]);
    bloques.push(h("h3", {}, T("sitio.ib.segmental")), tabla(T("sitio.ib.cols_seg").split(","),
      segmentos().map(([k, n]) => [n, ...f(hoja.segmental_magra, k), ...f(hoja.segmental_grasa, k)])));
  }
  const meds = c.mediciones || [];
  bloques.push(h("h3", {}, T("sitio.ib.mediciones")), tabla(T("sitio.ib.cols_med").split(","), meds.slice().reverse().map((x) =>
    [fechaMes(x.fecha) + (x.fecha === c.prime.fecha ? T("sitio.ib.star_prime") : ""), ...[x.peso_kg, x.pgc, x.masa_grasa_kg, x.mme_kg].map((v) => (v == null ? "—" : v.toFixed(1))),
      x.puntuacion == null ? "—" : fmt(x.puntuacion, 0), x.grasa_visceral == null ? "—" : fmt(x.grasa_visceral, 0)])),
  h("p", { class: "nota" }, T("sitio.ib.leyenda_tabla")));
  return DS.desplegable({ titulo: T("sitio.ib.ver_hoja"), liga: true, clase: "ib-hoja" }, ...bloques);
}

/** Tarjeta única «Composición corporal · fecha» en el orden de la hoja InBody. Sin InBody no hay tarjeta. */
function tarjetaComposicion(c) {
  if (!c || !(c.mediciones || []).length) return DS.tarjeta({ titulo: T("sitio.ib.titulo_vacio"), clase: "ancha" }, DS.estadoVacio({ icono: null, titulo: T("sitio.ib.vacio_t"), texto: T("sitio.ib.vacio_x") }));   // el botón «Agregar medición» ya está arriba
  const hoja = c.hoja || {};
  return DS.tarjeta({ titulo: T("sitio.ib.comp", { f: fechaMes(hoja.fecha || c.ultima.fecha) }), clase: "ancha ib" },
    grupoInbody(T("sitio.ib.mg"), hoja.musculo_grasa), grupoInbody(T("sitio.ib.ob"), hoja.obesidad),
    historialInbody(c), puntuacionInbody(c), hojaCompleta(c));
}

// --- Cuerpo: recuperación ---

/** Una serie de recuperación (HRV, FC en reposo o sueño): promedio de 7 días, gráfica y tabla; 12 semanas fijas. */
function graficaRecuperacion(d, ancho, id) {
  const prog = d.progreso || {};
  const dias = (prog.dias || []).slice(-84);
  const umbral = ((d.detalles || {}).umbrales || {}).sleep_min_hours;
  const def = {
    hrv: { campo: "hrv", prom: "hrv_7d", unidad: "ms", fmtV: (v) => fmt(v, 0), nombre: T("sitio.rec.hrv"), extra: { banda: dias.map((x) => ({ lo: x.hrv_base_baja, hi: x.hrv_base_alta })), fmtY: (v) => fmt(v, 0) } },
    rhr: { campo: "rhr", prom: "rhr_7d", unidad: T("sitio.lpm"), fmtV: (v) => fmt(v, 0), nombre: T("sitio.rec.rhr"), extra: { fmtY: (v) => fmt(v, 0) } },
    sueno: { campo: "sueño_h", prom: "sueño_7d", unidad: "", fmtV: horasMin, nombre: T("sitio.rec.sueno"), extra: { ref: umbral != null ? { y: umbral, etiqueta: null } : null, fmtY: (v) => fmt(v, 1) } },
  }[id];
  const dom = dias.length ? [parseFecha(dias[0].fecha).getTime(), parseFecha(dias[dias.length - 1].fecha).getTime()] : [0, 1];
  const s = dias.map((x) => ({ fecha: x.fecha, y: x[def.campo], p: x[def.prom], lo: x.hrv_base_baja, hi: x.hrv_base_alta }));
  const ult = s.slice().reverse().find((p) => p.p != null);
  const u = def.unidad ? " " + def.unidad : "";
  let sub = ult ? T("sitio.rec.prom", { v: def.fmtV(ult.p), u, f: fechaLarga(ult.fecha) }) : T("sitio.rec.sin_prom");
  if (id === "sueno" && umbral != null) sub += T("sitio.rec.raya", { h: horasMin(umbral) });
  const filas = s.filter((p) => p.y != null).reverse().map((p) => [fechaLarga(p.fecha), def.fmtV(p.y), p.p == null ? "—" : def.fmtV(p.p)]);
  return h("div", {}, h("p", { class: "nota" }, sub),
    lineChart({ ancho, serie: s, dominio: dom, puntos: true, promedio: s.map((p) => p.p), etiqueta: def.nombre, ...def.extra,
      texto: (p, prom) => T("sitio.rec.txt", { f: fechaLarga(p.fecha), v: def.fmtV(p.y), u, prom: prom != null ? T("sitio.rec.txt_prom", { v: def.fmtV(prom) }) : "", base: def.extra.banda && p.lo != null ? T("sitio.rec.txt_base", { a: p.lo, b: p.hi }) : "" }) }),
    DS.leyenda([["pto", T("sitio.rec.diario")], ["rayaln", T("sitio.rec.prom_l")], ...(id === "hrv" && dias.some((x) => x.hrv_base_alta != null) ? [["banda-sw", T("sitio.rec.rango")]] : [])]),
    filas.length ? tablaDatos(T("sitio.rec.cols", { u: def.unidad || T("sitio.rec.sueno_col") }).split(","), filas) : "");
}

function tarjetaRecuperacion(d) {
  return tarjetaConVistas("cuerpo", T("sitio.rec.titulo"), T("sitio.rec.12"), [
    { etiqueta: T("sitio.rec.t_hrv"), pintar: (a) => graficaRecuperacion(d, a, "hrv") },
    { etiqueta: T("sitio.rec.t_rhr"), pintar: (a) => graficaRecuperacion(d, a, "rhr") },
    { etiqueta: T("sitio.rec.t_sueno"), pintar: (a) => graficaRecuperacion(d, a, "sueno") }], { clase: "ancha" });
}

