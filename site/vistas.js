// Vistas Plan y Progreso (Corridas · Cuerpo), más el arranque.
const $ = (id) => document.getElementById(id);

function fechaLarga(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()].slice(0, 3)} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function horasMin(hh) {
  const min = Math.floor(hh * 60 + 1e-6);
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

/** «Ver como tabla»: desplegable con una tabla (la primera columna a la izquierda, las demás a la derecha). */
function tablaDatos(cabeza, filas, titulo = "Ver como tabla") {
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

const NUMEROS = {
  corridas: ["Corridas por semana", (v) => fmt(v, 1), ""], minutos: ["Minutos por semana", (v) => fmt(v, 0), "min"],
  km: ["Km por semana", (v) => fmt(v, 1), "km"], ritmo_ref: ["Ritmo a FC ref", (v) => mmss(v), "/km"], pct_trote: ["% trote", (v) => fmt(v, 0), "%"],
};

/** Fila de números del periodo (ya calculados en Python) con el cambio contra el periodo anterior. */
function filaNumeros(d) {
  const prog = d.progreso || {};
  const items = ((prog.numeros || {}).periodos || {})[String(periodo)] || [];
  return DS.tiles({ etiqueta: `Números de las últimas ${periodo} semanas`, clase: "ancha" }, ...items.map((x) => {
    let [nombre, fv, unidad] = NUMEROS[x.id] || [x.id, (v) => fmt(v, 1), ""];
    if (x.id === "ritmo_ref" && prog.fc_ref) nombre = `Ritmo a ${prog.fc_ref} lpm`;
    const cambio = x.valor == null ? "Sin corridas"
      : x.anterior == null ? "Sin periodo anterior"
        : x.delta === 0 || x.delta == null ? "= igual que el periodo anterior"
          : `${x.delta > 0 ? "▲" : "▼"} ${fv(Math.abs(x.delta))}${x.id === "ritmo_ref" ? "/km" : unidad && unidad !== "/km" ? " " + unidad : ""} vs periodo anterior`;
    return DS.tile({ k: nombre, valor: x.valor == null ? "—" : fv(x.valor), unidad: x.valor != null && unidad ? unidad : null, delta: cambio, deltaClase: x.bueno ? "" : "neutro" });
  }));
}

let subProgreso = "corridas";   // "corridas" | "cuerpo", lo decide la ruta (#progreso o #progreso/cuerpo)

/** Control segmentado Corridas | Cuerpo. Cambia la ruta; mostrarVista hace el resto. */
function selectorProgreso() {
  return DS.segmento({ id: "prog-subtabs", clase: "ancha", etiqueta: "Progreso", activo: subProgreso,
    opciones: [{ id: "corridas", texto: "Corridas" }, { id: "cuerpo", texto: "Cuerpo" }],
    onCambio: (id) => { location.hash = id === "cuerpo" ? "#progreso/cuerpo" : "#progreso"; } });
}

function renderProgreso(d) {
  PINTAR.progreso = [];
  PINTAR.cuerpo = [];
  const raiz = $("vista-progreso");
  const prog = d.progreso || {};
  raiz.replaceChildren(selectorProgreso(),
    h("div", { class: "sub", id: "prog-corridas", hidden: subProgreso !== "corridas" }, ...[
      DS.segmento({ etiqueta: "Periodo", modo: "grupo", clase: "ancha", activo: periodo, opciones: [4, 8, 12].map((n) => ({ id: n, texto: `${n} semanas` })),
        onCambio: (n) => { periodo = Number(n); renderProgreso(d); mostrarSubvista(); REDIBUJAR.progreso(); } }),
      filaNumeros(d),
      tarjetaMejora(d),
      tarjetaCorridasProgreso(d),
      tarjetaIntensidadSemanas(d),
      tarjetaMarcasYCarreras(d),
      d.detalles && d.detalles.carga ? tarjetaCarga(d.detalles) : null].filter(Boolean)),
    h("div", { class: "sub", id: "prog-cuerpo", hidden: subProgreso !== "cuerpo" },
      ...[tarjetaRecuperacion(d), tarjetaComposicion(d.composicion)].filter(Boolean)));
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

// --- Plan ---

/** Tarjetita del catálogo: silueta en tinta (sin color ni tooltip), nombre y descripción. */
function tipoCard(t, enPlan) {
  return h("div", { class: "tipo" }, siluetaForma(t.forma, 48, `Forma de ${t.nombre}`),
    enPlan ? h("div", {}, DS.chip("EN TU PLAN", "suave")) : null, h("h3", {}, t.nombre), h("p", {}, t.descripcion));
}

function tarjetaTipos(d) {
  const tp = d.tipos;
  if (!tp || !(tp.catalogo || []).length) return null;
  const enPlan = new Set(tp.en_plan || []);
  const nombreGrupo = Object.fromEntries((tp.grupos || []).map((g) => [g.id, g.nombre]));
  const c = DS.tarjeta({ titulo: "Tipos de entreno", clase: "ancha" },
    h("p", { class: "nota" }, "Así sube y baja tu esfuerzo en cada tipo de sesión. La Larga es un continuo más largo."));
  const suyos = tp.catalogo.filter((t) => enPlan.has(t.id));
  if (suyos.length) c.append(h("div", { class: "tipos" }, suyos.map((t) => tipoCard(t, true))));
  const resto = tp.catalogo.filter((t) => !enPlan.has(t.id));
  if (resto.length) {
    const det = DS.desplegable({ titulo: suyos.length ? "Ver todos los tipos" : "Ver los tipos", liga: true, clase: "todos-tipos" });
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
  $("vista-plan").replaceChildren(...[
    guardado ? DS.aviso({ clase: "ok", simbolo: "✔", titulo: "Listo", texto: "Guardamos tu plan." }) : null,
    acciones.length ? h("div", { class: "botones" }, acciones.map((a) => DS.boton(a.texto, { variante: "sec", href: a.url }))) : null,
    tarjetaDoceSemanas(d),
    tarjetaTipos(d),
    tarjetaFcMax(d),
    det.distribucion ? zonaBar(det.distribucion) : null].filter(Boolean));
}

function tarjetaDoceSemanas(d) {
  const plan = d.plan || {};
  const semanas = plan.semanas || [];
  const c = DS.tarjeta({ titulo: "12 semanas", clase: "ancha" });
  if (!semanas.length) { c.append(DS.estadoVacio({ icono: null, titulo: "Aún no hay plan cargado." })); return c; }
  const actual = plan.semana_actual ?? null;
  if (planSel === null || !semanas.some((w) => w.n === planSel)) planSel = actual ?? semanas[0].n;
  const w = semanas.find((x) => x.n === planSel);
  const linea = h("div", { class: "linea" });
  for (const bloque of [1, 2, 3]) {
    const del = semanas.filter((x) => x.block === bloque);
    if (!del.length) continue;
    linea.append(h("div", { class: "bloque" }, h("div", { class: "nota" }, `Bloque ${bloque}`),
      h("div", { class: "semanas" }, del.map((x) =>
        h("button", { type: "button", class: `sem ${x.kind === "descarga" ? "desc" : ""} ${x.n === actual ? "actual" : ""}`,
          "aria-pressed": x.n === planSel ? "true" : "false",
          "aria-label": `Semana ${x.n}, ${x.etiqueta || x.kind}${x.n === actual ? ", semana actual" : ""}`,
          onclick: () => { planSel = x.n; c.replaceWith(tarjetaDoceSemanas(d)); } },
          h("strong", {}, x.n), h("span", { class: "con-ico" }, x.etiqueta === "carrera" ? DS.ico("medalla") : x.etiqueta === "viaje" ? DS.ico("avion") : null, x.etiqueta || (x.kind === "descarga" ? "descarga" : "carga")), x.n === actual ? h("em", {}, "actual") : null)))));
  }
  const est = actual === w.n ? plan.estado_sesiones ?? [] : [];
  c.append(linea,
    h("p", { class: "nota" }, `${ui().textos.descarga || "Las semanas de descarga (línea punteada) bajan la carga."} Toca una semana para ver sus sesiones.`),
    h("h3", { class: "titular" }, `Semana ${w.n} · bloque ${w.block} · ${w.kind}`),
    h("p", { class: "nota" }, w.focus || ""),
    h("div", { class: "filas" }, (w.sessions || []).map((s) => filaSesion(s, est.find((e) => e.id === s.id), (ui().editar_urls || {})[`${w.n}/${s.id}`]
      ? { cuerpo: [...cuerpoPlan(s), DS.boton("Editar", { variante: "sec", chico: true, href: ui().editar_urls[`${w.n}/${s.id}`] })] } : {}))),
    ...((plan.semanas_repetidas || []).length ? [h("p", { class: "nota" }, `Semanas repetidas: ${plan.semanas_repetidas.join(", ")}.`)] : []),
    ...listaEventos(plan.eventos));
  return c;
}

const NOMBRE_EVENTO = { viaje: "Viaje", enfermedad: "Enfermedad", lesion: "Lesión", carrera: "Carrera" };

/** Viajes, enfermedades y carreras con fecha (plan.eventos, solo en la web); nada si no hay. */
function listaEventos(eventos) {
  if (!(eventos || []).length) return [];
  return [h("h3", { class: "titular" }, "Eventos"),
    ...eventos.map((e) => h("p", { class: "nota" },
      `${NOMBRE_EVENTO[e.tipo] || e.tipo}${e.nombre ? ` «${e.nombre}»` : ""} · ${e.desde}${e.hasta && e.hasta !== e.desde ? ` al ${e.hasta}` : e.hasta ? "" : " · sigue"}${e.distancia_km ? ` · ${e.distancia_km} km` : ""}`))];
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
      nota: `Cada corrida llevada a ${ref} lpm (la mitad de tu Z2): arriba = más rápido. La línea es el promedio de 4 corridas. El calor sube la FC: mira la tendencia, no una corrida suelta. Solo al aire libre, sin carreras.`,
      extra: { fmtY: mmss, invertir: true, etiqueta: `Ritmo a ${ref} lpm por corrida` },
      vacio: "Aún no hay corridas al aire libre con el trote en Z2 en este periodo.",
      texto: (r) => `${fechaLarga(r.fecha)} · ${mmss(r.ritmo_ref_s)} /km a ${ref} lpm${r.fc_trote ? ` (trotaste a ${fmt(r.fc_trote, 0)} lpm)` : ""}` },
    deriva: { filtro: (r) => r.deriva_pct != null, y: (r) => r.deriva_pct, all: true,
      nota: "Cuánto cae tu eficiencia (velocidad ÷ FC) de la primera mitad a la segunda, sin los primeros 10 min. Menos de 5 % (la raya) es buena base. Solo corridas de 40 min o más, casi sin caminar, a ritmo parejo y casi toda en Z2.",
      extra: { fmtY: (v) => fmt(v, 0), ref: { y: 5, etiqueta: "5 %" }, etiqueta: "Deriva cardiaca por corrida, con raya en 5 %" },
      vacio: "Aún no hay corridas que cumplan (40 min o más, casi sin caminar, a ritmo parejo y casi toda en Z2) en este periodo.",
      texto: (r) => `${fechaLarga(r.fecha)} · deriva ${fmt(r.deriva_pct, 1)} % ${r.deriva_ok ? "✓" : "⚠"}` },
    pct: { filtro: (r) => r.pct_trote != null, y: (r) => r.pct_trote, nota: "Porcentaje del tiempo de la corrida que fue trote. Solo al aire libre.",
      extra: { fmtY: (v) => fmt(v, 0), etiqueta: "Porcentaje del tiempo trotando por corrida" },
      vacio: "Aún no hay corridas al aire libre en este periodo.",
      texto: (r) => `${fechaLarga(r.fecha)} · ${fmt(r.pct_trote, 0)} % trotando · trote ${fmt(r.trote_min, 0)}' / caminata ${fmt(r.camina_min, 0)}'` },
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
  if (!hay) return DS.estadoVacio({ icono: null, titulo: "Sin corridas en este periodo." });
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.min_trote || 0, s.min_camina || 0], meta: s.plan_min || 0, s }));
  return h("div", {}, h("p", { class: "nota" }, "Minutos de reloj por semana (lun–dom); la raya marca el plan y arriba van tus entrenos de la semana."),
    barChart({ ancho, semanas: barras, clases: ["s1", "walk"], etiqueta: "Volumen semanal: trote y caminata con raya del plan y un ícono por entreno",
      entrenos: semanas.some((s) => (s.entrenos || []).length) ? (b) => b.s.entrenos || [] : null,
      texto: (b) => `Semana del ${fechaLarga(b.inicio)} · ${fmt(b.s.minutos, 0)}'${b.s.plan_min ? ` (plan ${b.s.plan_min}')` : ""} · ${fmt(b.s.km)} km · trote ${fmt(b.s.min_trote, 0)}'${textoEntrenos(b.s.entrenos)}` }),
    leyendaIconos(semanas, [[COLOR_CLASE.s1, "Trote"], [COLOR_CLASE.walk, "Caminata"], ["raya", "Plan"]]),
    tablaDatos(["Semana", "Min", "Plan", "Km", "Trote", "Caminata"], semanas.slice().reverse().map((s) =>
      [fechaLarga(s.inicio), fmt(s.minutos, 0), s.plan_min ?? "—", fmt(s.km), fmt(s.min_trote, 0), fmt(s.min_camina, 0)]), "Ver semanas como tabla"));
}

function graficaKm(d, ancho) {
  const semanas = ((d.progreso || {}).semanas || []).slice(-periodo);
  if (!semanas.some((s) => (s.km || 0) > 0)) return DS.estadoVacio({ icono: null, titulo: "Sin corridas en este periodo." });
  return h("div", {}, h("p", { class: "nota" }, "Kilómetros por semana (lun–dom), trote y caminata."),
    barChart({ ancho, semanas: semanas.map((s) => ({ inicio: s.inicio, valores: [s.km || 0], s })), clases: ["s1"],
      etiqueta: "Kilómetros por semana",
      texto: (b) => `Semana del ${fechaLarga(b.inicio)} · ${fmt(b.s.km)} km` }),
    tablaDatos(["Semana", "Km"], semanas.slice().reverse().map((s) => [fechaLarga(s.inicio), fmt(s.km)]), "Ver semanas como tabla"));
}

function tarjetaCorridasProgreso(d) {
  const prog = d.progreso || {};
  const hayCaminatas = ((prog.numeros || {}).caminatas || {})[String(periodo)];
  const hayDeriva = (prog.corridas || []).some((r) => r.deriva_pct != null);
  const vistas = [{ etiqueta: "Volumen", pintar: (a) => graficaVolumen(d, a) },
    { etiqueta: "Km", pintar: (a) => graficaKm(d, a) },
    { etiqueta: "Ritmo", pintar: (a) => graficaCorridas(d, a, "ritmo") },
    ...(hayDeriva ? [{ etiqueta: "Deriva", pintar: (a) => graficaCorridas(d, a, "deriva") }] : []),
    ...(hayCaminatas ? [{ etiqueta: "% trote", pintar: (a) => graficaCorridas(d, a, "pct") }] : [])];
  return tarjetaConVistas("progreso", "Corridas", `Últimas ${periodo} semanas`, vistas, { clase: "ancha", pie: tablaCorridas(prog.corridas || []) });
}

function tablaCorridas(corridas) {
  const orden = corridas.slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
  const celdas = (r) => [fechaLarga(r.fecha), h("span", { class: "con-ico" }, DS.ico(r.icono || (r.carrera ? "medalla" : "correr")), `${r.sesion || "—"}${r.carrera ? " · carrera" : ""}`), fmt(r.minutos, 0), fmt(r.km),
    r.pct_trote == null ? "—" : `${fmt(r.pct_trote, 0)} %`,
    r.caminadora ? "cam." : r.ritmo_trote_s == null ? "—" : mmss(r.ritmo_trote_s),
    r.ritmo_ref_s == null ? "—" : mmss(r.ritmo_ref_s), r.deriva_pct == null ? "—" : `${fmt(r.deriva_pct, 1)} %`,
    r.fc_prom == null ? "—" : fmt(r.fc_prom, 0), textoEsfuerzo(r) || "—"];
  const cab = ["Fecha", "Sesión", "Min", "Km", "% trote", "Ritmo trote", "Ritmo a FC ref", "Deriva", "FC", "Esfuerzo"];
  return [DS.desplegable({ titulo: "Ver cada corrida como tabla", liga: true },
    orden.length ? DS.tabla({ etiqueta: "Corridas", columnas: cab.map((texto, i) => ({ texto, num: i > 1 })), filas: orden.map((r) => ({ celdas: celdas(r) })) })
      : DS.estadoVacio({ icono: null, titulo: "Aún no hay corridas registradas." }),
    orden.some((r) => r.caminadora) ? h("p", { class: "nota" }, "cam. = caminadora (su ritmo no se compara).") : null)];
}

// --- intensidad por semana (80/20) ---

const INT_GRUPOS = [["bajo", "Bajo Z1–Z2", "z1"], ["limbo", "Limbo Z3", "z3"], ["alto", "Alto Z4–Z5", "z4"]];

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
    if (!con.length) { caja.replaceChildren(DS.estadoVacio({ icono: null, titulo: "Sin minutos en zonas en este periodo." })); pie.replaceChildren(); return; }
    caja.replaceChildren(barChart({
      ancho, alto: 130, tope: 100, ref: { y: 80, etiqueta: "meta 80 % bajo" }, clases: INT_GRUPOS.map((g) => g[2]),
      etiqueta: "Intensidad por semana: porcentaje bajo, limbo y alto, con meta de 80 % bajo",
      semanas: sem.map((x) => ({ inicio: x.inicio, valores: INT_GRUPOS.map(([k]) => x[k] || 0), x })),
      texto: (b) => `Semana del ${fechaLarga(b.inicio)} · Bajo ${fmt(b.x.bajo, 0)} % · Limbo ${fmt(b.x.limbo, 0)} % · Alto ${fmt(b.x.alto, 0)} %`,
    }));
    pie.replaceChildren(DS.leyenda([...INT_GRUPOS.map(([, n, c]) => [COLOR_CLASE[c], n]), ["raya-disc", "Meta: 80 % bajo (la raya punteada)"]]),
      tablaDatos(["Semana", "Bajo %", "Limbo %", "Alto %"], con.slice().reverse().map((x) => [fechaLarga(x.inicio), fmt(x.bajo, 0), fmt(x.limbo, 0), fmt(x.alto, 0)])));
  };
  PINTAR.progreso.push(pintar);
  return DS.tarjeta({ titulo: "Intensidad por semana", clase: "ancha" },
    h("p", { class: "nota" }, `Últimas ${periodo} semanas: qué parte del tiempo en zonas fue suave (Z1–Z2), media (Z3) o fuerte (Z4–Z5), con tus corridas y actividades. Solo referencia.`),
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
      etiqueta: `${x.nombre}: ${larga ? `${fmt(x.distancia_km, 2)} km en ${tiempoLargo(x.tiempo_s)}` : tiempoLargo(x.tiempo_s)}, ${fecha}${x.nuevo ? ", nueva" : ""}` };
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
  return h("div", { class: "ritmos-km" }, h("h3", {}, "Ritmo por km"),
    h("div", { role: "list" }, km.map((s, i) => h("div", { class: "rk", role: "listitem", "aria-label": `Km ${i + 1}: ${mmss(s)} por km` },
      h("span", { class: "rk-n" }, i + 1),
      h("span", { class: "rk-barra" }, h("i", { style: `width:${Math.round(55 + 45 * (lento === rapido ? 1 : (lento - s) / (lento - rapido)))}%`, class: s === rapido ? "rapido" : "" })),
      h("span", { class: `rk-v${s === rapido ? " rapido" : ""}` }, mmss(s))))),
    h("p", { class: "nota" }, "Barra más larga = km más rápido."));
}

function zonasCarrera(c) {
  const z = c.zonas_min;
  if (!z) return null;
  const ks = ["Z1", "Z2", "Z3", "Z4", "Z5"], total = ks.reduce((a, k) => a + z[k], 0);
  if (total <= 0) return null;
  return h("div", {}, h("h3", {}, "Minutos por zona"),
    h("div", { class: "zbar", role: "img", "aria-label": ks.map((k) => `${k} ${fmt(z[k], 0)} min`).join(", ") },
      ks.filter((k) => z[k] > 0).map((k) => h("div", { style: `flex:${z[k]} 1 0;background:var(--${k.toLowerCase()})` }))),
    DS.leyenda(ks.map((k) => [`var(--${k.toLowerCase()})`, `${k} ${fmt(z[k], 0)}'`])));
}

function comparacionCarrera(c) {
  const k = c.comparacion;
  if (!k) return null;
  const rel = (v, unidad, menosBueno) => (v === 0 || v == null ? null : `${unidad(Math.abs(v))} ${v < 0 ? menosBueno[0] : menosBueno[1]}`);
  const partes = [rel(k.dif_tiempo_s, tiempoLargo, ["más rápido", "más lento"]), rel(k.dif_ritmo_s, (s) => `${mmss(s)} /km`, ["menos por km", "más por km"]),
    rel(k.dif_fc, (v) => `${fmt(v, 0)} lpm`, ["menos de FC", "más de FC"])].filter(Boolean);
  return h("div", {}, h("h3", {}, "Contra tu carrera anterior"),
    h("p", { class: "nota" }, `${fechaConAnio(k.fecha)} · ${fmt(k.distancia_km, 2)} km en ${tiempoLargo(k.tiempo_s)}`),
    h("p", {}, partes.length ? `Ahora: ${partes.join(" · ")}` : "Igual que la anterior"));
}

/** Una carrera como entrada de DS.ranking: fecha, resumen, filas de datos y, abajo, ritmo por km, zonas y comparación. */
function carreraDetalle(c, abierta) {
  return { icono: c.icono || "medalla", fecha: fechaLarga(c.fecha), resumen: `${fmt(c.distancia_km, 2)} km · ${tiempoLargo(c.tiempo_s)}`, abierta,
    filas: [
      filaStat("Distancia", `${fmt(c.distancia_km, 2)} km`), filaStat("Tiempo", tiempoLargo(c.tiempo_s)),
      filaStat("Ritmo promedio", c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : null),
      filaStat("FC promedio / máxima", c.fc_prom != null ? `${fmt(c.fc_prom, 0)} / ${c.fc_max != null ? fmt(c.fc_max, 0) : "—"} lpm` : null),
      filaStat("Km más rápido", c.km_mas_rapido_s ? `${mmss(c.km_mas_rapido_s)} /km` : null),
      filaStat("Cadencia", c.cadencia ? `${c.cadencia} pasos/min` : null),
      filaStat("Desnivel", c.desnivel_m != null ? `+${c.desnivel_m} m` : null)].filter(Boolean),
    cuerpo: [barrasKm(c), zonasCarrera(c), comparacionCarrera(c)].filter(Boolean) };
}

/** "Marcas y carreras": marcas arriba y, si hay carreras, su lista debajo. Sin ninguna de las dos, no sale. */
function tarjetaMarcasYCarreras(d) {
  const marcas = datosMarcas(d), cs = d.carreras || [];
  if (!marcas.length && !cs.length) return null;
  const r = DS.ranking({ marcas, carreras: cs.map((x, i) => carreraDetalle(x, i === 0 && abrirCarrera)) });
  const lista = r.querySelector(".carreras");
  if (lista) { lista.id = "prog-carreras"; lista.before(h("h3", { class: "sub-carreras" }, "Carreras")); }
  return DS.tarjeta({ titulo: "Marcas y carreras", clase: "ancha" }, r);
}

// --- Composición corporal estilo InBody ---

const ZONA_TXT = { bajo: ["▼", "bajo"], normal: ["✓", "normal"], alto: ["▲", "alto"] };
const fechaMes = (iso) => { const f = parseFecha(iso); return `${f.getDate()} ${MESES[f.getMonth()]} ${String(f.getFullYear()).slice(2)}`; };
const kg1 = (v) => fmt(v, 1);

/** Una barra de la hoja como fila de DS.ibGrupo: la barra llega a `pos` y su valor va al final. */
function filaInbody(f) {
  const txt = f.estimado ? `≈${fmt(f.valor, 1)}` : fmt(f.valor, 1);
  const [simbolo, zona] = ZONA_TXT[f.zona];
  const etiqueta = `${f.nombre}: ${fmt(f.valor, 1)} ${f.unidad}${f.pct != null ? `, ${f.pct} % del valor estándar` : ""}${f.estimado ? " (estimado)" : ""}, zona ${zona}`;
  return { nombre: f.nombre, unidad: f.unidad, zona: f.zona, textoZona: `${simbolo} ${zona}`, aria: etiqueta,
    normal: [f.normal_pos[0] * 100, (f.normal_pos[1] - f.normal_pos[0]) * 100], barra: f.pos * 100, valor: txt, dentro: f.pos > 0.8,
    ticks: f.escala.map((v, i) => [(i / (f.escala.length - 1)) * 100, fmt(v, v % 1 ? 1 : 0)]) };
}

function grupoInbody(titulo, filas) {
  if (!filas || !filas.length) return null;
  const n = filas[0].normal_pos;
  return DS.ibGrupo({ titulo, franja: [{ texto: "Bajo", pct: n[0] * 100 }, { texto: "Normal", pct: (n[1] - n[0]) * 100, normal: true }, { texto: "Alto", pct: (1 - n[1]) * 100 }],
    filas: filas.map(filaInbody) });
}

function historialInbody(c) {
  const hist = c.historial || [];
  if (!hist.length) return null;
  const caja = h("div", { class: "ib-hist" });
  const primeIdx = hist.findIndex((x) => x.es_prime);
  const defs = [["Peso (kg)", "peso_kg", "neutro"], ["MME (kg)", "mme_kg", "s1"], ["PGC (%)", "pgc", "s2"]];
  const pintar = () => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    caja.replaceChildren(...defs.map(([nombre, campo, clase], k) => h("div", { class: "ib-mini" }, h("h3", {}, nombre),
      miniLinea({ ancho, valores: hist.map((x) => x[campo]), clase, prime: primeIdx >= 0 ? primeIdx : null, fmt: kg1,
        fechas: k === defs.length - 1 ? hist.map((x) => fechaMes(x.fecha)) : null, etiqueta: `Historial de ${nombre}`,
        textos: hist.map((x) => `${fechaMes(x.fecha)} · ${kg1(x[campo])}${x.es_prime ? " · prime" : ""}`) }))));
  };
  PINTAR.cuerpo.push(pintar);
  const meta = c.meta || {};
  return h("div", { class: "ib-grupo" }, h("h3", {}, "Historial de composición corporal"), caja,
    h("p", { class: "titular" }, meta.faltan_pgc > 0 ? `Te faltan ${fmt(meta.faltan_pgc, 1)} % de grasa para tu prime` : "Ya superaste tu prime en grasa ✓"),
    meta.mme_ok ? h("p", { class: "nota" }, "Tu músculo ya está arriba del de tu prime ✓") : h("p", { class: "nota" }, `Te faltan ${fmt(meta.faltan_mme, 1)} kg de músculo para tu prime`));
}

function puntuacionInbody(c) {
  const pts = c.puntuacion || [], v = c.visceral;
  if (!pts.length && !v) return null;
  const ult = [...pts].reverse().find((p) => p.puntos != null);
  const [simbolo, clase] = v ? (v.zona === "normal" ? ["✓", "ok"] : ["!", "warn"]) : [];
  return h("div", { class: "ib-grupo" }, DS.ibPuntuacion({
    puntuacion: ult ? { valor: fmt(ult.puntos, 0), delta: ult.delta != null ? `${ult.delta > 0 ? "▲" : ult.delta < 0 ? "▼" : "="}${Math.abs(ult.delta)}` : null, deltaClase: ult.delta > 0 ? "" : "neutro" } : null,
    visceral: v ? { valor: fmt(v.valor, 0), rango: `${v.rango[0]}–${v.rango[1]}`, clase, simbolo,
      texto: v.zona === "normal" ? "Dentro del rango" : v.zona === "alto" ? "Por encima del rango" : "Por debajo del rango" } : null }),
    ult ? miniPuntuacion(pts) : null);
}

/** Historial de la puntuación: con un solo punto, solo el punto y una nota. */
function miniPuntuacion(pts) {
  const caja = h("div", { class: "ib-punt-g" });
  PINTAR.cuerpo.push(() => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    const graf = miniLinea({ ancho, valores: pts.map((p) => p.puntos), clase: "s1", prime: null, fmt: (v) => fmt(v, 0),
      fechas: pts.map((p) => fechaMes(p.fecha)), etiqueta: "Historial de la puntuación InBody" });
    const con = pts.filter((p) => p.puntos != null).length;
    caja.replaceChildren(graf, ...(con === 1 ? [h("p", { class: "nota" }, "Se llena con tus próximas mediciones.")]
      : con < pts.length ? [h("p", { class: "nota" }, "— = esa medición no tiene la hoja con puntuación.")] : []));
  });
  return caja;
}

const SEGMENTOS = [["brazo_izq", "Brazo izq."], ["brazo_der", "Brazo der."], ["tronco", "Tronco"], ["pierna_izq", "Pierna izq."], ["pierna_der", "Pierna der."]];

function hojaCompleta(c) {
  const hoja = c.hoja;
  if (!hoja) return null;
  const tabla = (cabeza, filas) => DS.tabla({ etiqueta: cabeza.filter(Boolean).join(", ") || "Hoja InBody",
    columnas: cabeza.map((texto, i) => ({ texto, num: i > 0 })), filas: filas.map((celdas) => ({ celdas })) });
  const zonaTxt = (z) => `${ZONA_TXT[z][0]} ${ZONA_TXT[z][1]}`;
  const bloques = [];
  const barras = [...(hoja.musculo_grasa || []), ...(hoja.obesidad || [])];
  if (barras.length) bloques.push(h("h3", {}, "Análisis músculo-grasa y de obesidad"),
    tabla(["", "Valor", "% estándar", "Normal", "Zona"], barras.map((f) => [f.nombre, `${f.estimado ? "≈" : ""}${fmt(f.valor, 1)} ${f.unidad}`,
      f.pct != null ? `${f.pct} %` : "—", `${fmt(f.normal[0], 1)}–${fmt(f.normal[1], 1)}${f.pct != null ? " %" : ""}`, zonaTxt(f.zona)])));
  const cp = hoja.control_peso;
  if (cp) bloques.push(h("h3", {}, "Control de peso"), tabla(["", "kg"], [["Peso ideal", fmt(cp.peso_ideal_kg, 1)], ["Control de peso", fmt(cp.control_peso_kg, 1)],
    ["Control de grasa", fmt(cp.control_grasa_kg, 1)], ["Control de músculo", fmt(cp.control_musculo_kg, 1)]]));
  const grupos = [...new Set((hoja.rangos || []).map((r) => r.grupo))];
  for (const g of grupos) bloques.push(h("h3", {}, g), tabla(["", "Valor", "Rango", "Zona"], hoja.rangos.filter((r) => r.grupo === g).map((r) =>
    [r.nombre, `${fmt(r.valor, 2)}${r.unidad ? " " + r.unidad : ""}`, `${fmt(r.min, 2)}–${fmt(r.max, 2)}`, zonaTxt(r.zona)])));
  if (hoja.segmental_magra || hoja.segmental_grasa) {
    const f = (o, k) => (o && o[k] ? [`${fmt(o[k][0], 2)} kg`, `${fmt(o[k][1], 0)} %`] : ["—", "—"]);
    bloques.push(h("h3", {}, "Análisis segmental"), tabla(["", "Magra", "% ideal", "Grasa", "% ideal"],
      SEGMENTOS.map(([k, n]) => [n, ...f(hoja.segmental_magra, k), ...f(hoja.segmental_grasa, k)])));
  }
  const meds = c.mediciones || [];
  bloques.push(h("h3", {}, "Mediciones"), tabla(["Fecha", "Peso", "% grasa", "Grasa kg", "MME", "Punt.", "Visc."], meds.slice().reverse().map((x) =>
    [fechaMes(x.fecha) + (x.fecha === c.prime.fecha ? " ★ prime" : ""), ...[x.peso_kg, x.pgc, x.masa_grasa_kg, x.mme_kg].map((v) => (v == null ? "—" : v.toFixed(1))),
      x.puntuacion == null ? "—" : fmt(x.puntuacion, 0), x.grasa_visceral == null ? "—" : fmt(x.grasa_visceral, 0)])),
  h("p", { class: "nota" }, "MME = masa muscular esquelética. Visc. = grasa visceral. — = sin dato. ≈ = estimado de la barra."));
  return DS.desplegable({ titulo: "Ver hoja completa", liga: true, clase: "ib-hoja" }, ...bloques);
}

/** Tarjeta única «Composición corporal · fecha» en el orden de la hoja InBody. Sin InBody no hay tarjeta. */
function tarjetaComposicion(c) {
  if (!c || !(c.mediciones || []).length) return null;
  const hoja = c.hoja || {};
  return DS.tarjeta({ titulo: `Composición corporal · ${fechaMes(hoja.fecha || c.ultima.fecha)}`, clase: "ancha ib" },
    grupoInbody("Análisis músculo-grasa", hoja.musculo_grasa), grupoInbody("Análisis de obesidad", hoja.obesidad),
    historialInbody(c), puntuacionInbody(c), hojaCompleta(c));
}

// --- Cuerpo: recuperación ---

/** Una serie de recuperación (HRV, FC en reposo o sueño): promedio de 7 días, gráfica y tabla; 12 semanas fijas. */
function graficaRecuperacion(d, ancho, id) {
  const prog = d.progreso || {};
  const dias = (prog.dias || []).slice(-84);
  const umbral = ((d.detalles || {}).umbrales || {}).sleep_min_hours;
  const def = {
    hrv: { campo: "hrv", prom: "hrv_7d", unidad: "ms", fmtV: (v) => fmt(v, 0), nombre: "HRV por noche", extra: { banda: dias.map((x) => ({ lo: x.hrv_base_baja, hi: x.hrv_base_alta })), fmtY: (v) => fmt(v, 0) } },
    rhr: { campo: "rhr", prom: "rhr_7d", unidad: "lpm", fmtV: (v) => fmt(v, 0), nombre: "FC en reposo por día", extra: { fmtY: (v) => fmt(v, 0) } },
    sueno: { campo: "sueño_h", prom: "sueño_7d", unidad: "", fmtV: horasMin, nombre: "Horas de sueño", extra: { ref: umbral != null ? { y: umbral, etiqueta: null } : null, fmtY: (v) => fmt(v, 1) } },
  }[id];
  const dom = dias.length ? [parseFecha(dias[0].fecha).getTime(), parseFecha(dias[dias.length - 1].fecha).getTime()] : [0, 1];
  const s = dias.map((x) => ({ fecha: x.fecha, y: x[def.campo], p: x[def.prom], lo: x.hrv_base_baja, hi: x.hrv_base_alta }));
  const ult = s.slice().reverse().find((p) => p.p != null);
  const u = def.unidad ? " " + def.unidad : "";
  let sub = ult ? `Promedio 7 días: ${def.fmtV(ult.p)}${u} · ${fechaLarga(ult.fecha)}` : "Aún no hay promedio de 7 días (faltan datos).";
  if (id === "sueno" && umbral != null) sub += ` · la raya marca ${horasMin(umbral)}`;
  const filas = s.filter((p) => p.y != null).reverse().map((p) => [fechaLarga(p.fecha), def.fmtV(p.y), p.p == null ? "—" : def.fmtV(p.p)]);
  return h("div", {}, h("p", { class: "nota" }, sub),
    lineChart({ ancho, serie: s, dominio: dom, puntos: true, promedio: s.map((p) => p.p), etiqueta: def.nombre, ...def.extra,
      texto: (p, prom) => `${fechaLarga(p.fecha)} · ${def.fmtV(p.y)}${u}${prom != null ? ` · prom. 7 d ${def.fmtV(prom)}` : ""}${def.extra.banda && p.lo != null ? ` · base ${p.lo}–${p.hi}` : ""}` }),
    DS.leyenda([["pto", "Diario"], ["rayaln", "Promedio 7 días"], ...(id === "hrv" && dias.some((x) => x.hrv_base_alta != null) ? [["banda-sw", "Rango base (HRV)"]] : [])]),
    filas.length ? tablaDatos(["Fecha", def.unidad || "Sueño", "Prom. 7 d"], filas) : "");
}

function tarjetaRecuperacion(d) {
  return tarjetaConVistas("cuerpo", "Recuperación", "Últimas 12 semanas", [
    { etiqueta: "HRV", pintar: (a) => graficaRecuperacion(d, a, "hrv") },
    { etiqueta: "FC reposo", pintar: (a) => graficaRecuperacion(d, a, "rhr") },
    { etiqueta: "Sueño", pintar: (a) => graficaRecuperacion(d, a, "sueno") }], { clase: "ancha" });
}

// --- Plan: zonas y reglas · Progreso: carga ---

const DET = {};

function tarjetaFcMax(d) {
  const f = (d.detalles || {}).fc_max || {};
  const u = (d.detalles || {}).umbrales || {};
  const ses = f.sesiones || [];
  const faltan = Math.max(0, 2 - (f.semanas_medidas || 0));
  const cuerpo = !ses.length
    ? [h("p", { class: "nota" }, ui().textos.fcmax_vacia || "Aún no hay sesiones medidas con correa.")]
    : [h("div", { class: "kv" }, h("span", {}, "Clases medidas"), h("span", {}, ses.length)),
      h("div", { class: "kv" }, h("span", {}, "Pico"), h("span", {}, `${fmt(f.pico, 0)} lpm`)),
      h("div", { class: "kv" }, h("span", {}, `FC máx estimada (pico + 3, mín ${fmt(u.max_hr_floor, 0)})`), h("span", {}, `${fmt(f.estimacion, 0)} lpm`)),
      f.listo ? DS.estado("ok", "✓", "Medición lista", "listo") : DS.estado("nd", "—", `Faltan ${faltan} ${faltan === 1 ? "semana" : "semanas"} de medición`, "en curso"),
      f.revisar ? DS.aviso({ clase: "warn", simbolo: "!", texto: `La estimación pasa de ${fmt(u.max_hr_review_above, 0)} lpm: revísala antes de usarla.` }) : null];
  const zonas = d.zonas || [];
  return DS.tarjeta({ titulo: "FC máxima y zonas" }, ...cuerpo,
    zonas.length ? h("div", { class: "zonas-fc" }, h("p", { class: "nota" }, `FC máx en uso: ${fmt(f.config, 0)} lpm (${f.fuente === "reloj" ? "del reloj" : "respaldo, el reloj no la dio"}) · reposo promedio 7 días: ${fmt(d.rhr_promedio_7d, 0)} lpm (Karvonen)`),
      DS.tabla({ etiqueta: "Zonas de FC", columnas: [{ texto: "Zona" }, { texto: "Rango (lpm)", num: true }],
        filas: zonas.map((z) => ({ celdas: [h("span", { class: "zchip" }, h("i", { style: `background:var(--${z.zona.toLowerCase()})`, "aria-hidden": "true" }), z.zona), `${z.piso}–${z.techo}`] })) }))
      : DS.estadoVacio({ icono: null, titulo: "Sin zonas calculadas." }));
}

// --- ayuda (#ayuda): bloques ya armados en Python con la config de cada persona ---

let rutaPrevia = "#hoy";   // a dónde regresa «← Volver»

function renderAyuda(d) {
  const bloques = d.ayuda || [];
  const volver = h("div", { class: "ancha" }, DS.boton("← Volver", { variante: "texto", onclick: () => { location.hash = rutaPrevia; } }));
  const tarjeta = (b) => DS.tarjeta({ titulo: b.titulo, clase: "ancha ayuda-bloque" },
    ...(b.parrafos || []).map((p) => h("p", {}, p)),
    (b.lista || []).length ? h("ul", { class: "reglas" }, b.lista.map((i) => h("li", {}, i.t ? h("strong", {}, `${i.t}: `) : null, i.x))) : null);
  $("vista-ayuda").replaceChildren(volver, h("h2", { class: "titular ancha" }, "Ayuda"),
    ...(bloques.length ? bloques.map(tarjeta) : [DS.estadoVacio({ icono: null, titulo: "Aún no hay ayuda disponible." })]));
}

function tarjetaCarga(det) {
  PINTAR.progreso.push(dibujarDetalles);
  const c = bloqueCarga(det);
  DET.carga = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", { class: "pie-graf" }) };
  c.append(h("h3", { class: "titular" }, "Últimas 12 semanas"), DET.carga.sub, DET.carga.chart, DET.carga.extra);
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
  const nombres = [...cats.map((c) => c.nombre), "Corrida"];
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [...cats.map((c) => (s.cargas || {})[c.id] || 0), s.carga_corrida || 0] }));
  const suma = (s) => s.valores.reduce((a, v) => a + v, 0);
  t.sub.textContent = "Esfuerzo × minutos por semana (lun–dom). La fuerza con la FC baja da poca carga. Solo referencia.";
  t.chart.replaceChildren(barChart({
    ancho, semanas: barras, etiqueta: "Carga semanal apilada", clases,
    texto: (s) => `Semana del ${fechaLarga(s.inicio)} · ${nombres.map((n, i) => `${n} ${fmt(s.valores[i], 0)}`).join(" · ")} · Total ${fmt(suma(s), 0)}`,
  }));
  t.extra.replaceChildren(DS.leyenda(clases.map((c, i) => [COLOR_CLASE[c], nombres[i]])),
    barras.length ? tablaDatos(["Semana", ...nombres], barras.slice().reverse().map((s) => [fechaLarga(s.inicio), ...s.valores.map((v) => fmt(v, 0))])) : "");
}

// --- tema ---

const temaActual = () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");

function cambiarTema() {
  const nuevo = temaActual() === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", nuevo);
  document.querySelector('meta[name="color-scheme"]').setAttribute("content", nuevo);
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento: vale solo esta visita */ }
  pintarEncabezado();
}

// --- arranque ---

// Plan y Hoy redibujan lo suyo; Progreso, solo la subvista visible (las gráficas necesitan ancho).
const REDIBUJAR = {
  hoy: () => PINTAR.hoy.forEach((f) => f()),
  plan: () => PINTAR.plan.forEach((f) => f()),
  progreso: () => PINTAR[subProgreso === "cuerpo" ? "cuerpo" : "progreso"].forEach((f) => f()),
  ayuda: () => {},
};
let vistaActual = null;

// Rutas viejas que siguen sirviendo.
const ALIAS_RUTA = { cuerpo: "progreso/cuerpo", detalles: "plan" };

const TABS = [{ id: "hoy", texto: "Hoy", icono: "hoy", href: "#hoy" }, { id: "plan", texto: "Plan", icono: "plan", href: "#plan" },
  { id: "progreso", texto: "Progreso", icono: "progreso", href: "#progreso" }];

/** Ícono de cada liga del menú ☰ (si ui.menu trae `icono`, gana el suyo). */
const ICONO_MENU = { "/ajustes": "editar", "/plan": "plan", "/cuerpo": "progreso", "/historial": "deshacer", "/coach": "medalla", "/privacidad": "check", "/salir": "flecha", "/diseno": "hoy" };

let menuAbierto = false;

/** Abre o cierra el menú ☰: Esc y tocar fuera lo cierran, y el foco regresa al botón. */
function ponerMenu(abrir, foco = true) {
  const pop = $("menu-pop"), btn = document.querySelector("#encabezado [aria-label=\"Menú\"]");
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
  const enc = DS.encabezado({ nombre: u.titulo || "Mi entreno", tema: temaActual() === "light" ? "claro" : "oscuro", conAyuda: !!(datos && (datos.ayuda || []).length),
    conMenu: items.length > 0, menuAbierto, actualizado: [act, ...(u.acciones_url ? [" · ", h("a", { id: "acciones-link", href: u.acciones_url, target: "_blank", rel: "noopener",
      title: "En GitHub toca «Run workflow»; en 1–2 min recarga esta página" }, "Jalar datos de Garmin ↗")] : [])],
    onAyuda: () => { location.hash = "#ayuda"; }, onTema: cambiarTema, onMenu: () => ponerMenu(!menuAbierto) });
  $("encabezado").replaceChildren(enc);
  if (!items.length) ponerMenu(false, false);
  actualizarEncabezado();
  // Aviso de repo atrasado (lo decide Python: ui.repo_estado = {texto, ligas}); no existe en GitHub Pages.
  const re = $("repo-estado"), est = u.repo_estado;
  re.hidden = !est;
  re.replaceChildren(...(est ? [DS.aviso({ clase: "warn", simbolo: "!", texto: [est.texto, " ", ...(est.ligas || []).map((l) => h("a", { href: l.url, target: "_blank", rel: "noopener" }, `${l.texto} `))] })] : []));
  // Avisos de cambios del coach o de tu IA (data.avisos, solo en la web): ver y deshacer en el historial.
  const av = $("avisos-web"), lista = (datos && datos.avisos) || [];
  av.hidden = !lista.length;
  av.replaceChildren(...lista.map((a) => DS.bannerCambio({ texto: a.texto, verHref: a.url, verTexto: "Ver y deshacer" })));
}

function actualizarEncabezado() {
  const iso = datos && (datos.datos_al || datos.generado);
  const hace = haceCuanto(iso);
  const act = $("actualizado");
  if (act) act.textContent = hace ? `Actualizado ${hace}` : "";
}

function mostrarVista() {
  const ruta = location.hash.slice(1).split("?")[0];   // "#hoy?sem=+1" solo se lee al arrancar
  const [nombre, sub] = (ALIAS_RUTA[ruta] || ruta).split("/");
  const v = VISTAS.includes(nombre) ? nombre : "hoy";
  subProgreso = v === "progreso" && sub === "cuerpo" ? "cuerpo" : "corridas";
  if (v !== "ayuda") rutaPrevia = `#${ruta || "hoy"}`;
  vistaActual = v;
  for (const id of VISTAS) $(`vista-${id}`).hidden = id !== v;
  for (const a of document.querySelectorAll(".tabs a")) {
    if (a.dataset.tab === v) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  mostrarSubvista();
  REDIBUJAR[v]();
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
  $("tabs").replaceChildren(DS.tabs({ items: TABS, actual: null }));
  pintarEncabezado();
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape" && menuAbierto) ponerMenu(false); });
  document.addEventListener("pointerdown", (ev) => { if (menuAbierto && !ev.target.closest("#menu-pop, #encabezado [aria-label=\"Menú\"]")) ponerMenu(false, false); });
  leerSemanaInicial();
  window.addEventListener("hashchange", mostrarVista);
  let resizeT;
  window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { for (const f of Object.values(REDIBUJAR)) f(); }, 150); });
  mostrarVista();
  // Mientras llega data.json: el logo que se arma; si falla, el error con «Volver a intentar».
  $("app").hidden = true;
  $("carga").replaceChildren(DS.cargando("Armando tu semana…"));
  try {
    const resp = await fetch("data.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(`data.json: ${resp.status}`);
    datos = await resp.json();
  } catch (e) {
    $("carga").replaceChildren(DS.errorCarga({ texto: "Revisa tu conexión y vuelve a intentar. Si sigue igual, puede que tu repo no haya subido datos hoy.",
      detalle: e && e.message ? e.message : String(e), onReintentar: () => location.reload() }));
    return;
  }
  $("carga").replaceChildren();
  $("app").hidden = false;
  pintarEncabezado();
  setInterval(actualizarEncabezado, 60000);
  const vistas = { hoy: renderHoy, plan: renderPlan, progreso: renderProgreso, ayuda: renderAyuda };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, "No se pudo mostrar esta sección con los datos actuales."); }
  }
  mostrarVista();
}

iniciar();
