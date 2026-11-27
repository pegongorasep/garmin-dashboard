// Vistas Plan y Progreso (Corridas · Cuerpo), más el arranque.
const $ = (id) => document.getElementById(id);

function fechaLarga(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()].slice(0, 3)} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function horasMin(hh) {
  const min = Math.floor(hh * 60 + 1e-6);
  return T("sitio.h_min", { h: Math.floor(min / 60), m: String(min % 60).padStart(2, "0") });
}

/** «Ver como tabla»: desplegable con una tabla (la primera columna a la izquierda, las demás a la derecha). */
function tablaDatos(cabeza, filas, titulo = T("sitio.ver_tabla")) {
  return DS.desplegable({ titulo, liga: true }, DS.tabla({ etiqueta: titulo,
    columnas: cabeza.map((texto, i) => ({ texto, num: i > 0 })), filas: filas.map((celdas) => ({ celdas })) }));
}

/** Color CSS de cada clase de serie de las gráficas (para las leyendas). */
const COLOR_CLASE = { s1: "var(--serie-1)", s2: "var(--serie-2)", walk: "var(--caminata)", z1: "var(--z1)", z3: "var(--z3)", z4: "var(--z4)",
  azul: "var(--cat-1)", aqua: "var(--cat-2)", violeta: "var(--cat-3)", amarillo: "var(--cat-4)" };

// --- tarjeta con vistas ---

const SEL = {};   // vista elegida en cada tarjeta, solo en memoria

/**
 * Tarjeta que agrupa un tema con botones para cambiar de vista (en vez de tarjetas apiladas).
 * vistas: [{ etiqueta, pintar:(ancho)=>Node }]. Solo cambia el contenido de abajo. Devuelve la tarjeta y
 * registra su dibujo en PINTAR[vista] (las gráficas necesitan el ancho, que solo existe con la vista visible).
 */
function tarjetaConVistas(vista, titulo, resumen, vistas, opts = {}) {
  if (!(SEL[titulo] < vistas.length)) SEL[titulo] = 0;
  const cuerpo = h("div", { class: "vista-cuerpo", role: "tabpanel" });
  const pintar = () => {
    const ancho = cuerpo.clientWidth;
    if (ancho) cuerpo.replaceChildren(vistas[SEL[titulo]].pintar(ancho));
  };
  PINTAR[vista].push(pintar);
  return DS.tarjeta({ titulo, clase: opts.clase || "" }, resumen ? h("p", { class: "nota" }, resumen) : null,
    vistas.length > 1 ? DS.segmento({ etiqueta: titulo, opciones: vistas.map((v, i) => ({ id: i, texto: v.etiqueta })), activo: SEL[titulo],
      onCambio: (i) => { SEL[titulo] = Number(i); pintar(); } }) : null, cuerpo, ...(opts.pie || []));
}

// --- Progreso ---

let periodo = 8;
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

function renderProgreso(d) {
  PINTAR.progreso = [];
  PINTAR.cuerpo = [];
  const raiz = $("vista-progreso");
  const prog = d.progreso || {};
  if (ui().solo_cuerpo) {   // «solo cuerpo»: sin Corridas ni selector; sin mediciones, un estado vacío con el botón
    const comp = tarjetaComposicion(d.composicion);
    raiz.replaceChildren(h("div", { class: "sub", id: "prog-cuerpo" }, comp ? [cabCuerpo(), comp] : DS.estadoVacio({ icono: null, titulo: T("sitio.ib.vacio_t"), texto: T("sitio.ib.vacio_x"),
      accion: { href: ui().cuerpo_nuevo || "/cuerpo/nuevo", texto: T("sitio.ib.agregar") } })));
    return;
  }
  raiz.replaceChildren(selectorProgreso(),
    h("div", { class: "sub", id: "prog-corridas", hidden: subProgreso !== "corridas" }, ...[
      DS.segmento({ etiqueta: T("sitio.prog.periodo"), modo: "grupo", clase: "ancha", activo: periodo, opciones: [4, 8, 12].map((n) => ({ id: n, texto: T("sitio.prog.n_sem", { n }) })),
        onCambio: (n) => { periodo = Number(n); renderProgreso(d); mostrarSubvista(); REDIBUJAR.progreso(); } }),
      filaNumeros(d),
      tarjetaMejora(d),
      tarjetaCorridasProgreso(d),
      tarjetaIntensidadSemanas(d),
      tarjetaMarcasYCarreras(d),
      d.detalles && d.detalles.carga ? tarjetaCarga(d.detalles) : null].filter(Boolean)),
    h("div", { class: "sub", id: "prog-cuerpo", hidden: subProgreso !== "cuerpo" },
      ...[cabCuerpo(), tarjetaRecuperacion(d), tarjetaComposicion(d.composicion)].filter(Boolean)));
}

/** Muestra Corridas o Cuerpo según `subProgreso` y marca el botón elegido. */
function mostrarSubvista() {
  const corr = $("prog-corridas"), cue = $("prog-cuerpo");
  if (ui().solo_cuerpo) { if (cue) cue.hidden = false; return; }
  if (!corr || !cue) return;
  corr.hidden = subProgreso !== "corridas";
  cue.hidden = subProgreso !== "cuerpo";
  document.querySelectorAll("#prog-subtabs button").forEach((b) => {
    const on = b.dataset.id === subProgreso;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
}

// --- Plan ---

/** Tarjetita del catálogo: silueta en tinta (sin color ni tooltip), nombre y descripción. */
function tipoCard(t, enPlan) {
  return h("div", { class: "tipo" }, siluetaForma(t.forma, 48, T("sitio.tipo.forma", { n: t.nombre })),
    enPlan ? h("div", {}, DS.chip(T("sitio.tipo.en_plan"), "suave")) : null, h("h3", {}, t.nombre), h("p", {}, t.descripcion));
}

function tarjetaTipos(d) {
  const tp = d.tipos;
  if (!tp || !(tp.catalogo || []).length) return null;
  const enPlan = new Set(tp.en_plan || []);
  const nombreGrupo = Object.fromEntries((tp.grupos || []).map((g) => [g.id, g.nombre]));
  const c = DS.tarjeta({ titulo: T("sitio.tipo.titulo"), clase: "ancha" },
    h("p", { class: "nota" }, T("sitio.tipo.nota")));
  const suyos = tp.catalogo.filter((t) => enPlan.has(t.id));
  if (suyos.length) c.append(h("div", { class: "tipos" }, suyos.map((t) => tipoCard(t, true))));
  const resto = tp.catalogo.filter((t) => !enPlan.has(t.id));
  if (resto.length) {
    const det = DS.desplegable({ titulo: T(suyos.length ? "sitio.tipo.ver_todos" : "sitio.tipo.ver"), liga: true, clase: "todos-tipos" });
    for (const g of tp.grupos || []) {
      const del = resto.filter((t) => t.grupo === g.id);
      if (del.length) det.append(h("h3", { class: "tipos-grupo" }, nombreGrupo[g.id] || g.id), h("div", { class: "tipos" }, del.map((t) => tipoCard(t, false))));
    }
    c.append(det);
  }
  return c;
}

function renderPlan(d) {
  PINTAR.plan = [];
  const det = d.detalles || {};
  const acciones = ui().plan_acciones || [];
  const guardado = new URLSearchParams(location.search).get("ok") === "plan";   // viene de guardar un formulario del plan
  if (guardado) history.replaceState(null, "", location.pathname + location.hash);   // el aviso sale una vez, no en cada recarga
  if (ui().sin_plan) {   // sin plan: la pestaña no existe, pero la ruta #plan puede abrirse a mano
    const accion = (ui().menu || []).length ? { texto: T("sitio.sl.quiero"), href: "/plan/nuevo" } : null;
    $("vista-plan").replaceChildren(DS.tarjeta({ titulo: T("sitio.sl.sin_plan_t") }, DS.estadoVacio({ icono: null, titulo: T("sitio.sl.sin_plan_t"), texto: T("sitio.sl.sin_plan_x"), accion })));
    return;
  }
  $("vista-plan").replaceChildren(...[
    guardado ? DS.aviso({ clase: "ok", simbolo: "✔", titulo: T("sitio.plan.listo"), texto: T("sitio.plan.guardado") }) : null,
    acciones.length ? h("div", { class: "botones ancha" }, acciones.map((a) => DS.boton(a.texto, { variante: "sec", href: a.url }))) : null,
    ui().plan_url ? h("div", { class: "botones ancha" }, DS.boton(T("sitio.plan.ajustar"), { variante: "sec", href: ui().plan_url })) : null,
    tarjetaDoceSemanas(d),
    tarjetaTipos(d),
    tarjetaFcMax(d),
    (ui().avisos || {}).zonas_garmin ? avisoCerrable("zonas_garmin", { clase: "warn", simbolo: "!", extra: "ancha", titulo: T("sitio.zonas.sugerir_t"), texto: T("sitio.zonas.sugerir") }) : null,
    det.distribucion ? zonaBar(det.distribucion) : null].filter(Boolean));
}

/** Líneas del «?» de las 12 semanas: cada una con su muestra dibujada con las mismas piezas que los cuadritos reales. */
function ayudaSemanas() {
  const mini = (c) => h("span", { class: `mini-sem ${c}` });
  const ev = (k) => h("span", { class: "sem-ev", "data-ev": k }, DS.ico(ICONO_MARCA[k]));
  const marca = (c, t) => h("span", { class: "sem-prog", "data-cump": c }, t);
  return [
    [[mini("")], "carga"], [[mini("desc")], "desc"],
    [["anillo-actual", "anillo-carrera", "anillo-prueba"].map((c) => mini(c)), "anillos"],
    [["carrera", "prueba", "viaje", "enfermedad"].map(ev), "iconos"],
    [[marca("completa", "✓✓"), marca("casi", "✓"), marca("baja", "–")], "marcas"],
  ].map(([m, k]) => DS.filaMuestra(m, T(`sitio.plan.ayuda_${k}`)));
}

function tarjetaDoceSemanas(d) {
  const plan = d.plan || {};
  const semanas = plan.semanas || [];
  const ayuda = DS.dialogo({ titulo: T("sitio.plan.ayuda_t"), cuerpo: ayudaSemanas() });
  const c = DS.tarjeta({ titulo: [T("sitio.plan.doce"), DS.botonIco("ayuda", T("sitio.plan.ayuda_btn"), { onclick: () => ayuda.showModal() })], clase: "ancha" }, ayuda);
  if (!semanas.length) { c.append(DS.estadoVacio({ icono: null, titulo: T("sitio.plan.sin_plan") })); return c; }
  const actual = plan.semana_actual ?? null;
  if (planSel === null || !semanas.some((w) => w.n === planSel)) planSel = actual ?? semanas[0].n;
  const w = semanas.find((x) => x.n === planSel);
  const linea = h("div", { class: "linea" });
  for (const bloque of [1, 2, 3]) {
    const del = semanas.filter((x) => x.block === bloque);
    if (!del.length) continue;
    linea.append(h("div", { class: "bloque" }, h("div", { class: "nota" }, T("sitio.plan.bloque", { n: bloque })),
      h("div", { class: "semanas" }, del.map((x) =>
        h("button", { type: "button", class: `sem ${x.kind === "descarga" ? "desc" : ""} ${x.n === actual ? "actual" : ""} ${anilloSemana(x, actual)}`,
          "aria-pressed": x.n === planSel ? "true" : "false",
          "aria-label": T("sitio.plan.aria", { n: x.n, e: etiquetaSemana(x), act: (x.n === actual ? T("sitio.plan.act_aria") : "") + textoMarca(x) }),
          onclick: () => { planSel = x.n; const n = tarjetaDoceSemanas(d); c.replaceWith(n); const b = n.querySelector('.sem[aria-pressed="true"]'); if (b) b.focus({ preventScroll: true }); } },
          x.n === actual ? h("em", {}, T("sitio.plan.actual")) : null,
          h("span", { class: "sem-cab" }, h("strong", {}, x.n),
            iconosSemana(x).map((k) => DS.burbuja(h("span", { class: "sem-ev", "data-ev": k }, DS.ico(ICONO_MARCA[k])), textoBurbuja(x, k)))),
          h("span", {}, tipoSemana(x.etiqueta || x.kind)),
          marcaProgreso(x, actual))))));
  }
  const est = actual === w.n ? plan.estado_sesiones ?? [] : w.estados ?? [];   // el estado de cada semana lo calcula Python
  c.append(linea,
    h("p", { class: "nota" }, T("sitio.plan.nota", { d: ui().textos.descarga || T("sitio.plan.descarga_nota") })),
    h("h3", { class: "titular" }, T("sitio.plan.titulo_sem", { n: w.n, b: w.block, k: tipoSemana(w.kind) })),
    h("p", { class: "nota" }, w.focus || ""),
    w.ajuste_texto ? h("p", { class: "nota" }, w.ajuste_texto) : null,
    actual === w.n && plan.faltan ? h("p", { class: "nota" }, plan.faltan) : null,
    h("div", { class: "filas" }, (w.sessions || []).map((s) => filaSesion(s, est.find((e) => e.id === s.id), (ui().editar_urls || {})[`${w.n}/${s.id}`]
      ? { cuerpo: [...cuerpoPlan(s), DS.boton(T("sitio.plan.editar"), { variante: "sec", chico: true, href: ui().editar_urls[`${w.n}/${s.id}`] })] } : {}))),
    ...((plan.semanas_repetidas || []).length ? [h("p", { class: "nota" }, T("sitio.plan.repetidas", { l: plan.semanas_repetidas.join(", ") }))] : []),
    ...listaEventos(plan.eventos));
  return c;
}

const nombreEvento = (t) => (["viaje", "enfermedad", "lesion", "carrera"].includes(t) ? T(`sitio.ev.${t}`) : t);
const tipoSemana = (k) => (k === "descarga" || k === "carga" ? T(`sitio.plan.${k}`) : k);
/** `etiqueta` es carga o descarga; `marca` (carrera, viaje, enfermedad, prueba) pone el ícono de la esquina: los textos salen del catálogo. */
const etiquetaSemana = (x) => tipoSemana(x.etiqueta || x.kind) + (x.marca ? `, ${T(`sitio.plan.et_${x.marca}`)}` : "");
/** Anillo exterior de la semana: carrera (rojo) gana a prueba (morado) y a la semana actual (azul); viaje y enfermedad no llevan. */
const anilloSemana = (x, actual) => (x.marca === "carrera" ? "anillo-carrera" : x.marca === "prueba" ? "anillo-prueba" : x.n === actual ? "anillo-actual" : "");
/** Íconos junto al número: el evento principal (`marca`) y, si hay otro, el de `marcas` (en orden de prioridad). */
const iconosSemana = (x) => [...new Set([x.marca, ...(x.marcas || [])].filter(Boolean))];
/** Texto accesible de la marca de avance (el mismo que ve quien usa lector de pantalla). */
const textoMarca = (x) => (x.cumplimiento ? `, ${T(`sitio.plan.cump_${x.cumplimiento}`, x.progreso || {})}` : x.progreso ? T("sitio.plan.prog_aria", { h: x.progreso.hechas, t: x.progreso.total }) : "");
/** Ranura de avance: ✓✓ / ✓ verdes, «–» gris en las pasadas; hechas/total en la actual; vacía (misma altura) en las futuras. */
function marcaProgreso(x, actual) {
  const p = x.progreso;
  const simbolo = x.cumplimiento === "completa" ? "✓✓" : x.cumplimiento === "casi" ? "✓" : x.cumplimiento === "baja" ? "–" : x.n === actual && p ? `${p.hechas}/${p.total}` : "";
  return h("span", { class: "sem-prog", "data-cump": x.cumplimiento || null, "aria-hidden": "true" }, simbolo || " ");
}
/** Texto de la burbuja de un ícono: lo específico (fechas, prueba) sale de `marcas_det`; sin él, el nombre del evento. */
function textoBurbuja(x, k) {
  const dt = (x.marcas_det || {})[k] || {};
  const f = !dt.d ? "" : dt.h && dt.h !== dt.d ? `${fechaLarga(dt.d)} – ${fechaLarga(dt.h)}` : fechaLarga(dt.d);
  if (k === "prueba") return dt.n ? T("sitio.plan.bur_prueba_n", { n: dt.n }) : T("sitio.plan.bur_prueba");
  return f ? T(`sitio.plan.bur_${k}`, { f }) : T(`sitio.plan.et_${k}`);
}
const ICONO_MARCA = { carrera: "medalla", viaje: "avion", enfermedad: "termometro", prueba: "cronometro" };

/** Viajes, enfermedades y carreras con fecha (plan.eventos, solo en la web); nada si no hay. */
function listaEventos(eventos) {
  if (!(eventos || []).length) return [];
  return [h("h3", { class: "titular" }, T("sitio.ev.titulo")),
    ...eventos.map((e) => h("p", { class: "nota" },
      `${nombreEvento(e.tipo)}${e.nombre ? ` «${e.nombre}»` : ""} · ${e.desde}${e.hasta && e.hasta !== e.desde ? T("sitio.ev.al", { h: e.hasta }) : e.hasta ? "" : T("sitio.ev.sigue")}${e.distancia_km ? ` · ${e.distancia_km} km` : ""}`))];
}

/** Contexto del periodo elegido: corridas al aire libre dentro del periodo y el dominio del eje x. */
function contextoPeriodo(d) {
  const prog = d.progreso || {};
  const hoyMs = parseFecha((d.generado || "").slice(0, 10) || "2000-01-01").getTime();
  const corte = hoyMs - periodo * 7 * 86400000;
  return { prog, dominio: [corte + 86400000, hoyMs],
    aire: (prog.corridas || []).filter((r) => !r.caminadora && parseFecha(r.fecha).getTime() > corte) };
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
  const semanas = (prog.semanas || []).slice(-periodo);
  const hay = semanas.some((s) => (s.minutos || 0) > 0 || s.plan_min);
  if (!hay) return DS.estadoVacio({ icono: null, titulo: T("sitio.vol.sin") });
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.min_trote || 0, s.min_camina || 0], meta: s.plan_min || 0, s }));
  return h("div", {}, h("p", { class: "nota" }, T("sitio.vol.nota")),
    barChart({ ancho, semanas: barras, clases: ["s1", "walk"], etiqueta: T("sitio.vol.et"),
      entrenos: semanas.some((s) => (s.entrenos || []).length) ? (b) => b.s.entrenos || [] : null,
      texto: (b) => T("sitio.vol.txt", { f: fechaLarga(b.inicio), m: fmt(b.s.minutos, 0), plan: b.s.plan_min ? T("sitio.vol.plan", { p: b.s.plan_min }) : "", k: fmt(b.s.km), t: fmt(b.s.min_trote, 0), e: textoEntrenos(b.s.entrenos) }) }),
    leyendaIconos(semanas, [[COLOR_CLASE.s1, T("sitio.vol.trote")], [COLOR_CLASE.walk, T("sitio.vol.camina")], ["raya", T("sitio.vol.plan_l")]]),
    tablaDatos(T("sitio.vol.cols").split(","), semanas.slice().reverse().map((s) =>
      [fechaLarga(s.inicio), fmt(s.minutos, 0), s.plan_min ?? "—", fmt(s.km), fmt(s.min_trote, 0), fmt(s.min_camina, 0)]), T("sitio.vol.tabla")));
}

function graficaKm(d, ancho) {
  const semanas = ((d.progreso || {}).semanas || []).slice(-periodo);
  if (!semanas.some((s) => (s.km || 0) > 0)) return DS.estadoVacio({ icono: null, titulo: T("sitio.vol.sin") });
  return h("div", {}, h("p", { class: "nota" }, T("sitio.km.nota")),
    barChart({ ancho, semanas: semanas.map((s) => ({ inicio: s.inicio, valores: [s.km || 0], s })), clases: ["s1"],
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
    const sem = todas.slice(-periodo);
    const con = sem.filter((x) => Object.values(x.minutos || {}).some((v) => v > 0));
    if (!con.length) { caja.replaceChildren(DS.estadoVacio({ icono: null, titulo: T("sitio.ig.sin") })); pie.replaceChildren(); return; }
    caja.replaceChildren(barChart({
      ancho, alto: 130, tope: 100, ref: { y: 80, etiqueta: T("sitio.ig.meta_ref") }, clases: intGrupos().map((g) => g[2]),
      etiqueta: T("sitio.ig.et"),
      semanas: sem.map((x) => ({ inicio: x.inicio, valores: intGrupos().map(([k]) => x[k] || 0), x })),
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
  if (!c || !(c.mediciones || []).length) return null;
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

// --- Plan: zonas y reglas · Progreso: carga ---

const DET = {};

function tarjetaFcMax(d) {
  const f = (d.detalles || {}).fc_max || {};
  const u = (d.detalles || {}).umbrales || {};
  const ses = f.sesiones || [];
  const faltan = Math.max(0, 2 - (f.semanas_medidas || 0));
  const cuerpo = !ses.length
    ? [h("p", { class: "nota" }, ui().textos.fcmax_vacia || T("sitio.fcm.vacia"))]
    : [h("div", { class: "kv" }, h("span", {}, T("sitio.fcm.clases")), h("span", {}, ses.length)),
      h("div", { class: "kv" }, h("span", {}, T("sitio.fcm.pico")), h("span", {}, `${fmt(f.pico, 0)} ${T("sitio.lpm")}`)),
      h("div", { class: "kv" }, h("span", {}, T("sitio.fcm.est", { m: fmt(u.max_hr_floor, 0) })), h("span", {}, `${fmt(f.estimacion, 0)} ${T("sitio.lpm")}`)),
      f.listo ? DS.estado("ok", "✓", T("sitio.fcm.lista"), T("sitio.fcm.lista_e")) : DS.estado("nd", "—", Tn("sitio.fcm.faltan", faltan), T("sitio.fcm.en_curso")),
      f.revisar ? avisoCerrable("fcmax", { clase: "warn", simbolo: "!", texto: T("sitio.fcm.revisar", { v: fmt(u.max_hr_review_above, 0) }) }) : null];
  const zonas = d.zonas || [];
  return DS.tarjeta({ titulo: T("sitio.fcz.titulo") }, ...cuerpo,
    zonas.length ? h("div", { class: "zonas-fc" }, h("p", { class: "nota" }, T("sitio.fcz.uso", { v: fmt(f.config, 0), f: T(f.fuente === "reloj" ? "sitio.fcz.reloj" : "sitio.fcz.respaldo"), r: fmt(d.rhr_promedio_7d, 0) })),
      DS.tabla({ etiqueta: T("sitio.fcz.tabla"), columnas: [{ texto: T("sitio.fcz.zona") }, { texto: T("sitio.fcz.rango"), num: true }],
        filas: zonas.map((z) => ({ celdas: [h("span", { class: "zchip" }, h("i", { style: `background:var(--${z.zona.toLowerCase()})`, "aria-hidden": "true" }), z.zona), `${z.piso}–${z.techo}`] })) }))
      : DS.estadoVacio({ icono: null, titulo: T("sitio.fcz.sin") }));
}

// --- ayuda (#ayuda): bloques ya armados en Python con la config de cada persona ---

let rutaPrevia = "#hoy";   // a dónde regresa «← Volver»

function renderAyuda(d) {
  const bloques = d.ayuda || [];
  const volver = h("div", { class: "ancha" }, DS.boton(T("sitio.ay.volver"), { variante: "texto", onclick: () => { location.hash = rutaPrevia; } }));
  const tarjeta = (b) => DS.tarjeta({ titulo: b.titulo, clase: "ancha ayuda-bloque" },
    ...(b.parrafos || []).map((p) => h("p", {}, p)),
    (b.lista || []).length ? h("ul", { class: "reglas" }, b.lista.map((i) => h("li", {}, i.t ? h("strong", {}, `${i.t}: `) : null, i.x))) : null);
  $("vista-ayuda").replaceChildren(volver, h("h2", { class: "titular ancha" }, T("sitio.ay.titulo")),
    ...(bloques.length ? bloques.map(tarjeta) : [DS.estadoVacio({ icono: null, titulo: T("sitio.ay.sin") })]));
}

function tarjetaCarga(det) {
  PINTAR.progreso.push(dibujarDetalles);
  const c = bloqueCarga(det);
  DET.carga = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", { class: "pie-graf" }) };
  c.append(h("h3", { class: "titular" }, T("sitio.carga.12")), DET.carga.sub, DET.carga.chart, DET.carga.extra);
  c.classList.add("ancha");
  return c;
}

function dibujarDetalles() {
  if (!DET.carga || !datos) return;
  const ancho = DET.carga.chart.clientWidth;
  if (!ancho) return;
  const t = DET.carga;
  const semanas = ((datos.detalles || {}).carga_semanas || []);
  const cats = ui().categorias, clases = [...cats.map((c) => c.clase), "s2"];
  const nombres = [...cats.map((c) => c.nombre), T("sitio.carga.corrida")];
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [...cats.map((c) => (s.cargas || {})[c.id] || 0), s.carga_corrida || 0] }));
  const suma = (s) => s.valores.reduce((a, v) => a + v, 0);
  t.sub.textContent = T("sitio.carga.nota");
  t.chart.replaceChildren(barChart({
    ancho, semanas: barras, etiqueta: T("sitio.carga.et"), clases,
    texto: (s) => T("sitio.carga.txt", { f: fechaLarga(s.inicio), n: nombres.map((n, i) => `${n} ${fmt(s.valores[i], 0)}`).join(" · "), t: fmt(suma(s), 0) }),
  }));
  t.extra.replaceChildren(DS.leyenda(clases.map((c, i) => [COLOR_CLASE[c], nombres[i]])),
    barras.length ? tablaDatos([T("sitio.vol.cols").split(",")[0], ...nombres], barras.slice().reverse().map((s) => [fechaLarga(s.inicio), ...s.valores.map((v) => fmt(v, 0))])) : "");
}

// --- tema ---

const temaActual = () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");

function cambiarTema(ev) {
  const nuevo = temaActual() === "light" ? "dark" : "light";
  const aplicar = () => {
    document.documentElement.setAttribute("data-theme", nuevo);
    document.querySelector('meta[name="color-scheme"]').setAttribute("content", nuevo);
    try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento: vale solo esta visita */ }
    pintarEncabezado();
  };
  DS.animar.tema(aplicar, ev && ev.currentTarget);
}

// --- arranque ---

// --- Grupo: la pestaña con la gente de tus grupos (todo lo calcula la web; aquí solo se pinta) ---
let grupoTurno = 0;   // descarta respuestas viejas si la persona cambia de ruta mientras carga
const NOV_EMOJI = { semana_completa: "🎉", record_distancia: "🏃", racha: "🔥", carrera_cerca: "🏁" };

const grupoGet = async (url) => {
  const r = await fetch(url, { headers: { Accept: "application/json" }, cache: "no-store" });
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
};

const grupoAbiertos = () => { try { return JSON.parse(localStorage.getItem("grupoAbiertos") || "{}"); } catch (e) { return {}; } };
const grupoGuardarAbierto = (clave, on) => {
  try { const a = grupoAbiertos(); if (on) a[clave] = 1; else delete a[clave]; localStorage.setItem("grupoAbiertos", JSON.stringify(a)); } catch (e) { /* sin almacenamiento: solo no se recuerda */ }
};

const grupoTiempo = (min) => {
  const hh = Math.floor(min / 60), mm = Math.round(min % 60);
  return hh && mm ? T("sitio.gr.t_hm", { h: hh, m: mm }) : hh ? T("sitio.gr.t_h", { h: hh }) : T("sitio.gr.t_m", { m: mm });
};

function grupoTextoNovedad(n, nombre) {
  const d = n.datos || {};
  if (n.tipo === "semana_completa") return d.total ? T("sitio.gr.nov.semana_completa", { nombre, n: d.n, total: d.total }) : T("sitio.gr.nov.semana_completa_sola", { nombre, n: d.n });
  if (n.tipo === "record_distancia") return T("sitio.gr.nov.record_distancia", { nombre, km: fmt(d.km, 1) });
  if (n.tipo === "racha") return T("sitio.gr.nov.racha", { nombre, semanas: d.semanas });
  if (n.tipo === "carrera_cerca") return d.dias === 0 ? T("sitio.gr.nov.carrera_hoy", { nombre }) : d.dias === 1 ? T("sitio.gr.nov.carrera_manana", { nombre }) : T("sitio.gr.nov.carrera_cerca", { nombre, dias: d.dias });
  return "";
}

function grupoDialogo(titulo, cuerpo) {
  const d = DS.dialogo({ titulo, cuerpo });
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}

function pintarGrupo(g) {
  const raiz = $("vista-grupo"), porId = Object.fromEntries(g.miembros.map((m) => [m.usuario_id, m]));
  const catEmoji = (c) => (g.emoji_cat || {})[c] || (g.emoji_cat || {}).otra || "🤸";
  const tarjeta = (m) => {
    const t = m.tarjeta, clave = `${g.grupo.id}:${m.usuario_id}`;
    const pausa = t.estado === "pausa";
    const ins = g.insignias.filter((i) => i.usuario_ids.includes(m.usuario_id)).map((i) => T(`sitio.gr.ins.${i.clave}`));
    const partes = [];
    if (t.semana) {
      const s = t.semana;
      if (s.km > 0 || s.minutos > 0) partes.push(`🏃 ${T("sitio.gr.corrida", { km: fmt(s.km, 1), min: fmt(s.minutos, 0) })}`);
      for (const [c, n] of Object.entries(s.otras || {})) partes.push(`${catEmoji(c)} ${n}`);
    }
    const sp = t.sem_plan, letras = [0, 1, 2, 3, 4, 5, 6].map((i) => T(`sitio.gr.c.d${i}`));
    const semana = DS.semanaPlanTarjeta(pausa || !sp ? {} : {
      minutos: sp.objetivo ? T("sitio.gr.p.min_de", { hechos: fmt(sp.minutos, 0), meta: fmt(sp.objetivo, 0) }) : T("sitio.gr.p.min_solo", { hechos: fmt(sp.minutos, 0) }),
      faltan: !sp.objetivo ? "" : sp.faltan.length ? T("sitio.gr.p.faltan", { lista: personaFaltan(sp.faltan) }) : T("sitio.gr.c.completa"),
      completa: !!sp.objetivo && !sp.faltan.length });
    const cal = !pausa && t.cal && t.cal.length === 7 ? DS.miniSemana({ letras, etiqueta: T("sitio.gr.c.dias_aria", { n: t.cal.filter((d) => d.hecha).length }),
      celdas: t.cal.map((d) => ({ hecha: d.hecha, hoy: d.hoy, emoji: d.cats.length ? (d.cats[0] === "run" ? "🏃" : catEmoji(d.cats[0])) : null })) }) : DS.miniSemana({ letras });
    const detalle = [];
    if (t.plan && t.plan.n) {
      const p = t.progreso;
      detalle.push(h("p", {}, t.plan.total ? T("sitio.gr.semana_n", { n: t.plan.n, total: t.plan.total }) : T("sitio.gr.semana_sola", { n: t.plan.n })));
      if (t.plan.total) detalle.push(DS.barraFina({ pct: 100 * t.plan.n / t.plan.total, etiqueta: T("sitio.gr.semana_n", { n: t.plan.n, total: t.plan.total }) }));
      if (p && !t.semana) detalle.push(h("p", {}, T("sitio.gr.progreso_aria", { hechas: p.hechas, total: p.total })));
    }
    if (t.adherencia !== null && t.adherencia !== undefined) detalle.push(h("p", {}, T("sitio.gr.adherencia", { pct: fmt(t.adherencia, 0) })));
    if (t.carrera) detalle.push(h("p", {}, t.meta || t.carrera.nombre ? T("sitio.gr.carrera", { nombre: t.carrera.nombre || t.meta, dias: t.carrera.dias }) : T("sitio.gr.carrera_sola", { dias: t.carrera.dias })));
    const racha = t.racha || (t.libre && t.libre.racha) || 0;
    if (racha > 0) detalle.push(h("p", {}, `🔥 ${T("sitio.gr.racha", { n: racha })}`));
    if (t.ultima) detalle.push(h("p", {}, T("sitio.gr.ultima", { fecha: fechaCorta(t.ultima) })));
    const iniciales = m.nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("") || "?";
    return DS.tarjetaMiembro({ nombre: m.nombre, foto: m.foto, iniciales, color: m.usuario_id, insignias: ins,
      pct: !pausa && t.progreso && t.progreso.total ? 100 * t.progreso.hechas / t.progreso.total : null,
      etiquetaAnillo: t.progreso ? T("sitio.gr.progreso_aria", { hechas: t.progreso.hechas, total: t.progreso.total }) : null,
      pausa: pausa ? T("sitio.gr.pausa") : null,
      linea: partes.length ? partes.join(" · ") : T(t.semana ? "sitio.gr.sin_actividad" : "sitio.gr.sin_datos"),
      dias: t.dias || [], etiquetaDias: T("sitio.gr.dias_aria", { n: (t.dias || []).filter((d) => d === "hecha").length }),
      semana, calendario: cal,
      detalle: [...detalle, personaEnlace(m.usuario_id, m.nombre)], alPersona: () => { location.hash = `#juntos/persona/${m.usuario_id}`; },
      abierto: !!grupoAbiertos()[clave], etiquetaAbrir: T("sitio.gr.detalle", { nombre: m.nombre }),
      onAlternar: (on) => grupoGuardarAbierto(clave, on) });
  };

  const nov = g.novedades.filter((n) => porId[n.usuario_id]);
  raiz.replaceChildren(...[
    h("div", { class: "grupo-cab ancha" }, h("h2", {}, g.grupo.nombre), h("a", { href: g.admin_url }, T("sitio.gr.administrar"))),
    h("div", { class: "ancha" }, DS.boton(T("sitio.gr.todos"), { variante: "texto", chico: true, onclick: () => { location.hash = "#juntos"; } })),
    h("p", { class: "grupo-total ancha" }, T("sitio.gr.juntos", { km: fmt(g.total.km, 1), tiempo: grupoTiempo(g.total.minutos) })),
    nov.length ? DS.tarjeta({ titulo: T("sitio.gr.novedades"), clase: "ancha" }, h("ul", { class: "novedades" }, nov.map((n) => {
      const m = porId[n.usuario_id];
      return h("li", { class: "nov-fila" }, h("span", {}, `${NOV_EMOJI[n.tipo] || "•"} ${grupoTextoNovedad(n, m.nombre)}`));
    }))) : null,
    ...g.miembros.map(tarjeta)].filter(Boolean));
}

// ---- Feed de actividades de Juntos: lo que entrenan las personas con las que compartes un grupo (el servidor decide quién aparece) ----
const feedCache = { items: [], siguiente: null, emojis: [], listo: false, vuelo: null };
const feedAbiertas = new Set();

/** Manda (o quita) una reacción a una actividad y devuelve las reacciones nuevas. El CSRF va como campo de formulario, nunca en JSON. */
async function feedReaccionar(it, emoji) {
  const r = await fetch("/api/juntos/reaccionar", { method: "POST", headers: { Accept: "application/json" },
    body: new URLSearchParams({ csrf: $("app").dataset.csrf || "", dueno: String(it.usuario_id), clave: it.clave, emoji }) });
  if (!r.ok) throw new Error(String(r.status));
  return (await r.json()).reacciones || {};
}

function feedCuando(fecha) {
  const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
  const dias = Math.round((hoy - parseFecha(fecha)) / 864e5);
  return dias <= 0 ? T("sitio.gr.f.hoy") : dias === 1 ? T("sitio.gr.f.ayer") : dias < 7 ? T("sitio.gr.f.hace", { n: dias }) : fechaCorta(fecha);
}

function feedDetalle(it) {
  const d = it.detalle || {}, z = d.zonas, t = it.trote;
  const p = (txt) => h("p", {}, txt);
  return [
    it.fc_prom || d.fc_max ? p([it.fc_prom ? T("sitio.gr.f.fc", { v: it.fc_prom }) : null, d.fc_max ? T("sitio.gr.f.fcmax", { v: d.fc_max }) : null].filter(Boolean).join(" · ")) : null,
    d.kcal || d.desnivel_m ? p([d.kcal ? T("sitio.gr.f.kcal", { v: fmt(d.kcal, 0) }) : null, d.desnivel_m ? T("sitio.gr.f.desnivel", { v: d.desnivel_m }) : null].filter(Boolean).join(" · ")) : null,
    z ? p(T("sitio.gr.f.zonas", { bajo: fmt(z.bajo, 0), limbo: fmt(z.limbo, 0), alto: fmt(z.alto, 0) })) : null,
    t ? p(T("sitio.gr.f.trote", { pct: fmt(t.pct_trote, 0), t: fmt(t.trote_min, 0), c: fmt(t.camina_min, 0) })) : null,
    it.partes && it.partes.length > 1 ? p(T("sitio.gr.f.partes", { n: it.partes.length })) : null,
  ].filter(Boolean);
}

/** Comentarios de una actividad (texto plano: el panel los pinta como nodos de texto). Se bajan al abrir la fila la primera vez. */
function feedPostComentarios(url, campos) {
  return fetch(url, { method: "POST", headers: { Accept: "application/json" }, body: new URLSearchParams({ csrf: $("app").dataset.csrf || "", ...campos }) })
    .then(async (r) => {
      if (r.status === 429) throw new Error(T("sitio.gr.f.com_limite"));
      if (!r.ok) throw new Error(T("sitio.gr.f.com_err"));
      return r.json();
    });
}

function feedComentarios(it, alCambiar) {
  let estado = { cargando: true, items: [], listo: false };
  const aItems = (r) => r.comentarios.map((c) => ({ id: c.id, texto: c.texto, puede_borrar: c.puede_borrar,
    nombre: c.mia ? T("sitio.gr.f.yo") : c.nombre || T("sitio.gr.f.alguien"), cuando: feedCuando(c.creado.slice(0, 10)) }));
  const recibir = (r) => { estado = { listo: true, items: aItems(r) }; it.comentarios = r.n; panel.pintar(estado); alCambiar(); };
  const panel = DS.panelComentarios({ max: 280, ayuda: T("sitio.gr.f.com_ayuda"), etiquetaCaja: T("sitio.gr.f.com_caja"), placeholder: T("sitio.gr.f.com_ph"),
    enviarTxt: T("sitio.gr.f.com_enviar"), borrarTxt: T("sitio.gr.f.com_borrar"), vacio: T("sitio.gr.f.com_vacio"), cargandoTxt: T("sitio.gr.f.com_cargando"),
    onEnviar: async (texto) => recibir(await feedPostComentarios("/api/juntos/comentar", { dueno: String(it.usuario_id), clave: it.clave, texto })),
    onBorrar: async (c) => { try { recibir(await feedPostComentarios("/api/juntos/comentario/borrar", { id: String(c.id) })); } catch (e) { panel.pintar({ ...estado, error: e.message }); } } });
  panel.cargar = async () => {
    if (estado.listo) return;
    panel.pintar({ cargando: true });
    try { recibir(await grupoGet(`/api/juntos/comentarios?dueno=${it.usuario_id}&clave=${encodeURIComponent(it.clave)}`)); }
    catch (e) { panel.pintar({ error: T("sitio.gr.f.com_err"), items: [] }); }
  };
  panel.pintar(estado);
  return panel;
}

function feedFila(it, aviso, conPerfil = true) {
  const nombre = it.mia ? T("sitio.gr.f.yo") : it.nombre;
  const fila = h("div", { class: "reacciones" });
  let articulo = null;
  const panel = feedComentarios(it, () => repintar());
  const botonCom = () => DS.botonComentarios({ n: it.comentarios || 0, etiqueta: T("sitio.gr.f.com_n", { n: it.comentarios || 0, tipo: it.tipo, nombre }),
    onclick: () => { const cab = articulo.querySelector(".act-cab"); if (cab.getAttribute("aria-expanded") !== "true") cab.click(); articulo.querySelector(".coments-caja").focus(); } });
  const repintar = (nuevo) => {
    fila.replaceChildren(...[...feedCache.emojis.filter((e) => it.reacciones[e]).map((e) => {
      const r = it.reacciones[e], quienes = r.quienes.join(", ");
      return DS.chipReaccion({ emoji: e, n: r.n, mia: r.mia, nueva: e === nuevo,
        etiqueta: r.mia ? T("sitio.gr.quitar", { emoji: e, quienes }) : T("sitio.gr.ver_quienes", { emoji: e, quienes }),
        onclick: r.mia ? () => enviar(e)
          : () => grupoDialogo(T("sitio.gr.quienes_t", { emoji: e }), [h("p", {}, T("sitio.gr.quienes", { emoji: e })), quienes ? h("p", {}, quienes) : null].filter(Boolean)) });
    }), it.mia ? null : DS.botonReaccion({ etiqueta: T("sitio.gr.f.reaccionar", { nombre: it.nombre }), onclick: elegir }), botonCom()].filter(Boolean));
  };
  const enviar = async (emoji) => {
    try {
      const antes = !!(it.reacciones[emoji] && it.reacciones[emoji].mia);
      it.reacciones = await feedReaccionar(it, emoji);
      aviso.replaceChildren();
      repintar(antes ? null : emoji);
    } catch (e) { aviso.replaceChildren(DS.aviso({ clase: "bad", simbolo: "!", texto: T("sitio.gr.err_reaccion") })); }
  };
  const elegir = () => {
    const d = grupoDialogo(T("sitio.gr.f.reaccionar", { nombre: it.nombre }), [DS.selectorReaccion({ emojis: feedCache.emojis, onElegir: (e) => { d.close(); enviar(e); } })]);
  };
  repintar();
  const iniciales = it.nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("") || "?";
  const resumen = [it.km != null ? T("sitio.km_n", { n: fmt(it.km, 1) }) : null, it.minutos ? T("sitio.min_n", { n: fmt(it.minutos, 0) }) : null].filter(Boolean).join(" · ");
  articulo = DS.filaActividad({ nombre, foto: it.foto, iniciales, color: it.usuario_id, cuando: feedCuando(it.fecha), emoji: it.emoji, tipo: it.tipo, resumen,
    esfuerzo: textoEsfuerzo(it), sesion: it.sesion ? T("sitio.gr.f.sesion", { sesion: it.sesion.nombre, n: it.sesion.n }) : null,
    detalle: [...feedDetalle(it), conPerfil ? personaEnlace(it.usuario_id, it.mia ? T("sitio.gr.f.yo") : it.nombre) : null].filter(Boolean),
    alPersona: conPerfil ? () => { location.hash = `#juntos/persona/${it.usuario_id}`; } : null, reacciones: fila, comentarios: panel, abierto: feedAbiertas.has(it.clave), etiquetaAbrir: T("sitio.gr.f.ver", { tipo: it.tipo, nombre }),
    onAlternar: (on) => { if (on) { feedAbiertas.add(it.clave); panel.cargar(); } else feedAbiertas.delete(it.clave); } });
  if (feedAbiertas.has(it.clave)) panel.cargar();
  return articulo;
}

function pintarFeed(sec, error) {
  const f = feedCache, aviso = h("div", { "aria-live": "polite" });
  const mas = f.siguiente ? h("div", { class: "feed-mas" }, DS.boton(T("sitio.gr.feed_mas"), { variante: "sec", chico: true, onclick: (e) => feedMas(sec, e.currentTarget) })) : null;
  const cuerpo = f.items.length ? [aviso, ...f.items.map((it) => feedFila(it, aviso)), mas]
    : f.listo ? [DS.estadoVacio({ icono: "personas", titulo: T("sitio.gr.feed_vacio_t"), texto: T("sitio.gr.feed_vacio"), accion: { texto: T("sitio.gr.feed_vacio_acc"), href: "/grupos/nuevo" } })]
    : error ? [DS.errorCarga({ titulo: T("sitio.gr.err_t"), texto: T("sitio.gr.feed_err"), detalle: error, onReintentar: () => feedRefrescar() })]
    : [DS.cargando(T("sitio.gr.cargando"))];
  sec.replaceChildren(h("h3", {}, T("sitio.gr.feed")), ...cuerpo.filter(Boolean));
}

const feedSeccion = () => $("vista-grupo").querySelector(".juntos-feed");

async function feedMas(sec, boton) {
  boton.disabled = true;
  try {
    const r = await grupoGet(`/api/juntos/feed?antes=${encodeURIComponent(feedCache.siguiente)}`);
    const claves = new Set(feedCache.items.map((x) => x.clave));
    feedCache.items.push(...r.items.filter((x) => !claves.has(x.clave)));
    feedCache.siguiente = r.siguiente;
  } catch (e) { boton.disabled = false; return; }
  const actual = feedSeccion();
  if (actual) pintarFeed(actual);
}

/** Baja la primera página y repinta solo si cambió algo (así no se pierde lo abierto ni se salta la pantalla). */
function feedRefrescar() {
  if (feedCache.vuelo) return;
  feedCache.vuelo = grupoGet("/api/juntos/feed").then((r) => {
    const antes = JSON.stringify([feedCache.items.slice(0, r.items.length), feedCache.listo]);
    const igual = feedCache.listo && antes === JSON.stringify([r.items, true]);
    feedCache.emojis = r.emojis;
    if (!igual) { feedCache.items = r.items; feedCache.siguiente = r.siguiente; }
    feedCache.listo = true;
    const sec = feedSeccion();
    if (sec && !igual) pintarFeed(sec);
  }).catch((e) => { const sec = feedSeccion(); if (sec && !feedCache.listo) pintarFeed(sec, e && e.message ? e.message : String(e)); })
    .finally(() => { feedCache.vuelo = null; });
}

function pintarListaGrupos(lista) {
  const sec = h("section", { class: "juntos-feed ancha", "aria-label": T("sitio.gr.feed") });
  pintarFeed(sec);
  $("vista-grupo").replaceChildren(h("h2", { class: "grupo-cab ancha" }, T("sitio.gr.tus_grupos")),
    h("div", { class: "grupos-lista ancha" }, lista.map((x) => h("a", { class: "grupo-fila", href: `#juntos/${x.id}` },
      h("span", {}, x.nombre), h("small", {}, T("sitio.gr.personas", { n: x.miembros_n }))))), sec);
  feedRefrescar();
}

// Caché en memoria de la pestaña Juntos: se precarga al abrir la app y se refresca en silencio al entrar.
const grupoCache = { lista: null, grupos: {}, vuelo: null };

/** Baja la lista (y el grupo si es único, o el pedido) y la deja en la caché. Devuelve { lista, g, gid }. */
async function grupoBajar(id) {
  let gid = id, lista = grupoCache.lista;
  if (!gid) {
    lista = await grupoGet("/api/grupos");
    grupoCache.lista = lista;
    return { lista, g: null, gid: null };   // el inicio de Juntos muestra siempre los botones, también con un solo grupo
  }
  const g = await grupoGet(`/api/grupos/${encodeURIComponent(gid)}`);
  grupoCache.grupos[gid] = g;
  return { lista, g, gid };
}

/** Pregunta en silencio si hay novedades (un GET ligero) y enciende o apaga el puntito de la pestaña. */
function juntosRevisar() {
  if (!(nGrupos() > 0)) return;
  grupoGet("/api/juntos/nuevo").then((r) => { juntosNuevo = !!r.nuevo && location.hash.replace(/^#/, "").split("/")[0] !== "juntos"; pintarPuntoJuntos(); }).catch(() => {});
}

/** Abrir el inicio de Juntos lo marca como visto (POST con CSRF) y apaga el puntito. */
function juntosVisto() {
  juntosNuevo = false; pintarPuntoJuntos();
  fetch("/api/juntos/visto", { method: "POST", headers: { Accept: "application/json" }, body: new URLSearchParams({ csrf: $("app").dataset.csrf || "" }) }).catch(() => {});
}
document.addEventListener("visibilitychange", () => { if (!document.hidden) juntosRevisar(); });

/** Precarga en segundo plano (tras data.json, con al menos un grupo). Los errores se ignoran: al entrar se reintenta. */
function precargarGrupo() {
  if (!(nGrupos() > 0) || grupoCache.vuelo) return;
  juntosRevisar();
  grupoCache.vuelo = grupoBajar(null).then(async (r) => {   // y cada grupo, para que al tocarlo salga al instante
    await Promise.all(r.lista.slice(0, 8).map((x) => grupoBajar(x.id).catch(() => null)));
  }).catch(() => null).finally(() => { grupoCache.vuelo = null; });
}

const grupoPintarCache = (id) => {
  if (id) { const g = grupoCache.grupos[id]; if (g) { pintarGrupo(g); return true; } return false; }
  if (!grupoCache.lista) return false;
  pintarListaGrupos(grupoCache.lista);
  return true;
};

/** Entrar a la pestaña: pinta la caché al instante (sin cargador) y refresca en silencio; sin caché, baja con cargador. */
async function cargarGrupo(id) {
  const turno = ++grupoTurno, raiz = $("vista-grupo");
  if (!id) juntosVisto();
  let pintado = grupoPintarCache(id);
  const antes = pintado ? JSON.stringify([grupoCache.lista, id ? grupoCache.grupos[id] : null]) : "";
  try {
    if (!pintado) {
      raiz.replaceChildren(DS.cargando(T("sitio.gr.cargando")));
      if (grupoCache.vuelo) { await grupoCache.vuelo; if (turno !== grupoTurno) return; if (grupoPintarCache(id)) pintado = true; }
      if (!pintado) {
        const r = await grupoBajar(id);
        if (turno !== grupoTurno) return;
        if (r.g) pintarGrupo(r.g); else pintarListaGrupos(r.lista);
        return;
      }
    }
    const r = await grupoBajar(id);
    if (turno !== grupoTurno) return;
    const despues = JSON.stringify([grupoCache.lista, id ? grupoCache.grupos[id] : null]);
    if (despues !== antes) { if (r.g) pintarGrupo(r.g); else pintarListaGrupos(r.lista); }
  } catch (e) {
    if (turno !== grupoTurno || pintado) return;   // con la caché ya pintada, un fallo del refresco no tumba la vista
    raiz.replaceChildren(DS.errorCarga({ titulo: T("sitio.gr.err_t"), texto: T("sitio.gr.err"), detalle: e && e.message ? e.message : String(e), onReintentar: () => cargarGrupo(id) }));
  }
}

// ---- Perfil de una persona dentro de Juntos (#juntos/persona/<id>): todo lo arma /api/juntos/persona/<id>; aquí solo se pinta ----
let personaVolver = "#juntos";
const personaEnlace = (id, nombre) => h("a", { class: "pers-ver", href: `#juntos/persona/${id}` }, T("sitio.gr.p.ver", { nombre }));
const personaIniciales = (n) => n.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("") || "?";
const personaLista = (partes) => (partes.length < 2 ? partes.join("") : `${partes.slice(0, -1).join(", ")} ${T("sitio.gr.p.y")} ${partes[partes.length - 1]}`);

function personaFaltan(f) {
  return personaLista(f.map((x) => (x.k === "facil" ? T(x.n === 1 ? "sitio.gr.p.f_facil_uno" : "sitio.gr.p.f_facil_n", { n: x.n }) : T(`sitio.gr.p.f_${x.k}`))));
}

function pintarPersona(p) {
  const oculto = (clave) => h("p", { class: "pers-oculto" }, T(clave));
  const sec = (titulo, ...hijos) => DS.tarjeta({ titulo, clase: "pers-sec ancha" }, ...hijos.filter(Boolean));
  const nombre = p.mia ? T("sitio.gr.f.yo") : p.nombre;
  const enComun = p.grupos.map((g) => g.nombre).join(", ");
  const partes = [
    h("div", { class: "grupo-cab ancha" }, h("a", { href: personaVolver }, `← ${T("sitio.tab.grupo")}`)),
    p.mia ? DS.aviso({ clase: "ok", simbolo: "i", titulo: T("sitio.gr.p.asi_t"),
      texto: [T("sitio.gr.p.asi_a"), " ", h("a", { href: "/ajustes#compartir" }, T("sitio.gr.p.asi_ajustes"))], extra: "ancha" }) : null,
    DS.tarjeta({ clase: "ancha" }, DS.cabeceraPersona({ nombre: p.nombre, foto: p.foto, iniciales: personaIniciales(p.nombre), color: p.usuario_id,
      nivel: p.nivel ? T(`sitio.gr.p.nivel.${p.nivel}`) : null, grupos: p.mia ? T("sitio.gr.p.tus_grupos", { grupos: enComun }) : T("sitio.gr.p.en_comun", { grupos: enComun }) })),
  ];
  if (p.pausa) partes.push(sec(T("sitio.gr.p.semana_t"), oculto("sitio.gr.p.pausa")));
  else {
    // Esta semana contra el plan
    const s = p.semana;
    partes.push(sec(T("sitio.gr.p.semana_t"),
      s ? h("p", { class: "pers-dato" }, s.objetivo ? T("sitio.gr.p.min_de", { hechos: fmt(s.minutos, 0), meta: fmt(s.objetivo, 0) }) : T("sitio.gr.p.min_solo", { hechos: fmt(s.minutos, 0) })) : oculto("sitio.gr.p.sin_datos"),
      p.comparte.plan && s && s.objetivo ? h("p", { class: "pers-faltan" }, s.faltan.length ? T("sitio.gr.p.faltan", { lista: personaFaltan(s.faltan) }) : T("sitio.gr.p.al_dia")) : null,
      !p.comparte.plan ? oculto("sitio.gr.p.no_plan") : null));
    // Calendario del plan: esta semana y la siguiente
    if (p.calendario) {
      partes.push(sec(T("sitio.gr.p.plan_t"), DS.calendarioPlan({ semanas: p.calendario.map((w) => ({
        titulo: w.n ? T("sitio.gr.p.sem_n", { n: w.n, fecha: fechaCorta(w.inicio) }) : T("sitio.gr.p.sem_f", { fecha: fechaCorta(w.inicio) }),
        dias: w.dias.map((d) => ({ nombre: d.dia, numero: parseFecha(d.fecha).getDate(), hoy: d.hoy, hecha: d.hecha, etiqueta: d.etiqueta })),
        sesiones: w.sesiones.map((x) => ({ texto: x.nombre, hecha: x.estado === "hecha" })) })) })));
    }
    // Progreso
    const pr = p.progreso;
    partes.push(sec(T("sitio.gr.p.prog_t"),
      pr && pr.semanas.length ? h("div", { class: "pers-graf" }, DS.graficaBarras({ alto: 120, clases: ["s1"], etiqueta: T("sitio.gr.p.graf"),
        semanas: pr.semanas.map((w) => ({ inicio: w.inicio, valores: [w.minutos] })),
        texto: (w) => T("sitio.gr.p.graf_tip", { fecha: fechaCorta(w.inicio), min: fmt(w.valores[0], 0) }) })) : oculto("sitio.gr.p.sin_datos"),
      p.nivel ? h("p", { class: "pers-dato" }, T("sitio.gr.p.nivel_l", { nivel: T(`sitio.gr.p.nivel.${p.nivel}`) })) : null,
      pr && pr.racha !== null ? h("p", { class: "pers-dato" }, pr.racha > 0 ? `🔥 ${T("sitio.gr.racha", { n: pr.racha })}` : T("sitio.gr.p.sin_racha")) : null,
      pr && pr.carreras ? (pr.carreras.length ? h("ul", { class: "pers-lista" }, pr.carreras.map((c) => h("li", {}, `🏁 ${c.distancia_km ? T("sitio.gr.p.carrera", { km: fmt(c.distancia_km, 1), fecha: fechaCorta(c.fecha) }) : T("sitio.gr.p.carrera_sola", { fecha: fechaCorta(c.fecha) })}`)))
        : h("p", { class: "pers-dato" }, T("sitio.gr.p.sin_carreras"))) : null));
    // Actividades recientes
    if (p.actividades) {
      const lista = h("div", { class: "pers-acts" }), aviso = h("div", { "aria-live": "polite" });
      let siguiente = p.actividades.siguiente;
      if (!feedCache.emojis.length) feedCache.emojis = p.emojis || [];
      const mas = h("div", { class: "feed-mas" });
      const pintarMas = () => mas.replaceChildren(...(siguiente ? [DS.boton(T("sitio.gr.feed_mas"), { variante: "sec", chico: true, onclick: async (e) => {
        e.currentTarget.disabled = true;
        try {
          const r = await grupoGet(`/api/juntos/feed?persona=${p.usuario_id}&antes=${encodeURIComponent(siguiente)}`);
          lista.append(...r.items.map((it) => feedFila(it, aviso, false)));
          siguiente = r.siguiente;
        } catch (err) { /* el botón se reactiva abajo */ }
        pintarMas();
      } })] : []));
      lista.append(aviso, ...p.actividades.items.map((it) => feedFila(it, aviso, false)));
      if (!p.actividades.items.length) lista.append(h("p", { class: "pers-oculto" }, T("sitio.gr.p.sin_act")));
      pintarMas();
      partes.push(h("section", { class: "juntos-feed ancha", "aria-label": T("sitio.gr.p.act_t") }, h("h3", {}, T("sitio.gr.p.act_t")), lista, mas));
    } else partes.push(sec(T("sitio.gr.p.act_t"), oculto("sitio.gr.p.no_act")));
  }
  $("vista-grupo").replaceChildren(...partes);
}

async function cargarPersona(id) {
  const turno = ++personaTurno; ++grupoTurno;
  const raiz = $("vista-grupo");
  raiz.replaceChildren(DS.cargando(T("sitio.gr.cargando")));
  try {
    const p = await grupoGet(`/api/juntos/persona/${id}`);
    if (turno === personaTurno) pintarPersona(p);
  } catch (e) {
    if (turno !== personaTurno) return;
    const noEsta = e && /: 404$/.test(e.message || "");
    raiz.replaceChildren(noEsta ? DS.estadoVacio({ icono: "personas", titulo: T("sitio.gr.p.no_enc_t"), texto: T("sitio.gr.p.no_enc"), accion: { texto: T("sitio.tab.grupo"), href: "#juntos" } })
      : DS.errorCarga({ titulo: T("sitio.gr.err_t"), texto: T("sitio.gr.err"), detalle: e && e.message ? e.message : String(e), onReintentar: () => cargarPersona(id) }));
  }
}
let personaTurno = 0;

// Plan y Hoy redibujan lo suyo; Progreso, solo la subvista visible (las gráficas necesitan ancho).
const REDIBUJAR = {
  hoy: () => PINTAR.hoy.forEach((f) => f()),
  plan: () => PINTAR.plan.forEach((f) => f()),
  progreso: () => PINTAR[subProgreso === "cuerpo" ? "cuerpo" : "progreso"].forEach((f) => f()),
  ayuda: () => {},
  grupo: () => {},   // se baja de la red al entrar (cargarGrupo), no al cambiar el tamaño
};
let vistaActual = null;

// Rutas viejas que siguen sirviendo.
const ALIAS_RUTA = { cuerpo: "progreso/cuerpo", detalles: "plan" };

// Cuántos grupos hay: con data.json, el suyo; antes, el que la web puso en <main data-grupos> (sin atributo: 0).
const nGrupos = () => datos && ui().grupos != null ? ui().grupos : parseInt(($("app") && $("app").dataset.grupos) || "0", 10) || 0;
const tabsDef = () => ui().solo_cuerpo ? [] : [{ id: "hoy", texto: T("sitio.tab.hoy"), icono: "hoy", href: "#hoy" },
  ...(ui().sin_plan ? [] : [{ id: "plan", texto: T("sitio.tab.plan"), icono: "plan", href: "#plan" }]),   // sin plan: no hay pestaña Plan (L2 la reemplaza por una tarjeta)
  { id: "progreso", texto: T("sitio.tab.progreso"), icono: "progreso", href: "#progreso" },
  ...(nGrupos() > 0 ? [{ id: "grupo", texto: T("sitio.tab.grupo"), icono: "personas", href: "#juntos", punto: true, nuevo: juntosNuevo }] : [])];   // solo en la web y con al menos un grupo
let juntosNuevo = false;   // ¿hay algo nuevo en Juntos desde la última vez que se abrió? (lo decide el servidor)
const pintarPuntoJuntos = () => { const a = document.querySelector('#tabs [data-tab="grupo"]'); if (a) a.dataset.nuevo = String(juntosNuevo); };
const selBotonMenu = () => `#encabezado [aria-label="${T("sitio.ds.menu")}"]`;

/** Ícono de cada liga del menú ☰ (si ui.menu trae `icono`, gana el suyo). */
const ICONO_MENU = { "/ajustes": "editar", "/plan": "plan", "/cuerpo": "progreso", "/historial": "deshacer", "/coach": "medalla", "/privacidad": "check", "/salir": "flecha", "/diseno": "hoy" };

let menuAbierto = false;

/** Abre o cierra el menú ☰: Esc y tocar fuera lo cierran, y el foco regresa al botón. */
function ponerMenu(abrir, foco = true) {
  const pop = $("menu-pop"), btn = document.querySelector(selBotonMenu());
  menuAbierto = abrir;
  pop.hidden = !abrir;
  if (btn) btn.setAttribute("aria-expanded", String(abrir));
  if (abrir) {
    pop.replaceChildren(DS.menu({ quien: ui().usuario || null, items: (ui().menu || []).map((i) => ({ texto: i.texto, href: i.url, icono: i.icono || ICONO_MENU[i.url] || "punto" })) }));
    const primera = pop.querySelector("a, button");
    if (primera) primera.focus();
  } else if (foco && btn) btn.focus();
}

/** Encabezado del sistema: logo y título, «Actualizado hace…» (con la liga a Garmin si existe), ayuda, tema y, en la web, el ☰. */
function pintarEncabezado() {
  const u = ui(), items = u.menu || [];
  if (u.titulo) document.title = `Garmin · ${u.titulo}`;
  const act = h("span", { id: "actualizado", "aria-live": "polite" });
  const enc = DS.encabezado({ nombre: u.titulo || T("sitio.titulo_defecto"), tema: temaActual() === "light" ? "claro" : "oscuro", conAyuda: !!(datos && (datos.ayuda || []).length),
    conMenu: items.length > 0, menuAbierto, actualizado: [act, ...(u.acciones_url ? [" · ", h("a", { id: "acciones-link", href: u.acciones_url, target: "_blank", rel: "noopener",
      title: T("sitio.enc.acciones_tip") }, T("sitio.enc.jalar"))] : [])],
    onAyuda: () => { location.hash = "#ayuda"; }, onTema: cambiarTema, onMenu: () => ponerMenu(!menuAbierto) });
  $("encabezado").replaceChildren(enc);
  if (!items.length) ponerMenu(false, false);
  actualizarEncabezado();
  // Barra de «Modo coach» (la decide Python: ui.coach = {nombre, volver} solo cuando un coach ve a su atleta).
  const bc = $("barra-coach");
  bc.hidden = !u.coach;
  bc.replaceChildren(...(u.coach ? [DS.avisoCoach(u.coach)] : []));
  // Aviso de repo atrasado (lo decide Python: ui.repo_estado = {texto, ligas}).
  const re = $("repo-estado"), est = u.repo_estado;
  re.hidden = !est;
  re.replaceChildren(...(est ? [DS.aviso({ clase: "warn", simbolo: "!", texto: [est.texto, " ", ...(est.ligas || []).map((l) => h("a", { href: l.url, target: "_blank", rel: "noopener" }, `${l.texto} `))] })] : []));
  // Avisos de cambios del coach o de tu IA (data.avisos, solo en la web): ver y deshacer en el historial.
  const av = $("avisos-web"), lista = (datos && datos.avisos) || [];
  av.hidden = !lista.length;
  av.replaceChildren(...lista.map((a) => DS.bannerCambio({ texto: a.texto, verHref: a.url, verTexto: T("sitio.enc.ver_deshacer") })));
}

function actualizarEncabezado() {
  const iso = datos && (datos.datos_al || datos.generado);
  const hace = haceCuanto(iso);
  const act = $("actualizado");
  if (act) act.textContent = hace ? T("sitio.enc.actualizado", { h: hace }) : "";
}

function mostrarVista() {
  const ruta = location.hash.slice(1).split("?")[0];   // "#hoy?sem=+1" solo se lee al arrancar
  const [nombre0, sub, sub2] = (ALIAS_RUTA[ruta] || ruta.replace(/^grupo(?=\/|$)/, "juntos")).split("/");   // #grupo y #grupo/<id> (viejos) valen como #juntos
  const nombre = nombre0 === "juntos" ? "grupo" : nombre0;
  if (/^grupo(\/|$)/.test(ruta)) history.replaceState(null, "", `#${ruta.replace(/^grupo/, "juntos")}`);
  const solo = !!ui().solo_cuerpo;   // solo cuerpo: todo cae en Progreso > Cuerpo (la ayuda sigue)
  const v = solo && nombre !== "ayuda" ? "progreso" : nombre === "grupo" && !(nGrupos() > 0) ? "hoy" : VISTAS.includes(nombre) ? nombre : "hoy";
  subProgreso = solo || (v === "progreso" && sub === "cuerpo") ? "cuerpo" : "corridas";
  if (v === "grupo" && sub === "persona" && !/^#juntos\/persona\//.test(rutaPrevia)) personaVolver = /^#juntos(\/\d+)?$/.test(rutaPrevia) ? rutaPrevia : "#juntos";   // el «volver» del perfil; sin historial, a Juntos
  if (v !== "ayuda") rutaPrevia = `#${ruta.replace(/^grupo(?=\/|$)/, "juntos") || "hoy"}`;
  vistaActual = v;
  for (const id of VISTAS) $(`vista-${id}`).hidden = id !== v;
  for (const a of document.querySelectorAll(".tabs a")) {
    if (a.dataset.tab === v) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  mostrarSubvista();
  REDIBUJAR[v]();
  if (v === "grupo") { if (sub === "persona" && /^\d+$/.test(sub2 || "")) cargarPersona(sub2); else cargarGrupo(sub && sub !== "persona" ? sub : null); }
  window.scrollTo(0, 0);
  if (datos && /[?&]abrir\b/.test(location.hash)) {   // para capturas: ?abrir despliega sesiones y "Ver todos los tipos"
    document.querySelectorAll(`#vista-${v} details.fila-ses, #vista-${v} details.todos-tipos`).forEach((x) => { x.open = true; });
  }
  if (v === "progreso" && subProgreso === "cuerpo" && /[?&]hoja\b/.test(location.hash)) {   // para capturas: #cuerpo?hoja abre «Ver hoja completa»
    const hoja = document.querySelector(".ib-hoja");
    if (hoja) hoja.open = true;
  }
  if (datos && abrirCarrera && v === "progreso" && subProgreso === "corridas") {   // venimos de la tarjeta de carrera de Hoy
    abrirCarrera = false;
    const det = document.querySelector("#prog-carreras details");
    if (det) { det.open = true; det.scrollIntoView({ block: "start" }); }
  }
}

function aviso(id, msg) {
  $(`vista-${id}`).replaceChildren(DS.estadoVacio({ icono: null, titulo: msg }));
}

async function iniciar() {
  await cargarIdioma(idiomaInicial());   // el último idioma visto o el del navegador; con data.json se corrige si hace falta
  $("tabs").replaceChildren(DS.tabs({ items: tabsDef(), actual: null }));
  pintarEncabezado();
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && menuAbierto) ponerMenu(false); });
  document.addEventListener("pointerdown", (ev) => { if (menuAbierto && !ev.target.closest(`#menu-pop, ${selBotonMenu()}`)) ponerMenu(false, false); });
  leerSemanaInicial();
  window.addEventListener("hashchange", mostrarVista);
  let resizeT;
  window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { for (const f of Object.values(REDIBUJAR)) f(); }, 150); });
  mostrarVista();
  // Mientras llega data.json: el logo que se arma; si falla, el error con «Volver a intentar».
  $("app").hidden = true;
  $("carga").replaceChildren(DS.cargando(T("sitio.carga_frase"), { pagina: true }));
  try {
    const resp = await fetch("data.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(`data.json: ${resp.status}`);
    datos = await resp.json();
    // Idioma: el de data.json (lo manda la web); sin él, el del navegador.
    const idioma = idiomaDe(datos.idioma || navigator.language);
    if (idioma !== IDIOMA) {
      await cargarIdioma(idioma);
      $("tabs").replaceChildren(DS.tabs({ items: tabsDef(), actual: null }));
    }
  } catch (e) {
    $("carga").replaceChildren(DS.errorCarga({ texto: T("sitio.err.texto"),
      detalle: e && e.message ? e.message : String(e), onReintentar: () => location.reload() }));
    return;
  }
  $("carga").replaceChildren();
  $("app").hidden = false;
  pintarEncabezado();
  setInterval(actualizarEncabezado, 60000);
  $("tabs").replaceChildren(DS.tabs({ items: tabsDef(), actual: null }));
  repintarVistas();
  precargarGrupo();
}

/** Pinta todas las vistas con `datos` (al arrancar y cuando cambia algo local, como dar un aviso por «Entendido»). */
function repintarVistas() {
  const vistas = ui().solo_cuerpo ? { progreso: renderProgreso } : { hoy: renderHoy, plan: renderPlan, progreso: renderProgreso, ayuda: renderAyuda };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, T("sitio.err.vista")); }
  }
  mostrarVista();
}

iniciar();
