// Vistas Progreso y Detalles, más el arranque.
const $ = (id) => document.getElementById(id);
const REPO_DOCS = "https://github.com/pegongorasep/garmin-dashboard/blob/main/docs/";

function fechaLarga(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()].slice(0, 3)} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function horasMin(hh) {
  const min = Math.floor(hh * 60 + 1e-6);
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
}

function tablaDatos(cabeza, filas) {
  return h("details", {}, h("summary", {}, "Ver como tabla"),
    h("div", { class: "tabla-scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, cabeza.map((c) => h("th", {}, c)))),
      h("tbody", {}, filas.map((f) => h("tr", {}, f.map((c) => h("td", {}, c))))))));
}

const leyenda = (items) => h("div", { class: "leyenda" }, items.map(([cls, txt]) => h("span", {}, h("i", { class: cls, "aria-hidden": "true" }), txt)));

// --- Progreso ---

let periodo = 8;
let planSel = null;
const PROG = {};

function renderProgreso(d) {
  const raiz = $("vista-progreso");
  const prog = d.progreso || {};
  const boton = (n) => h("button", { type: "button", "aria-pressed": n === periodo ? "true" : "false",
    onclick: () => { periodo = n; renderProgreso(d); dibujarProgreso(); } }, `${n} semanas`);
  const tarjeta = (id, titulo, ...extra) => {
    PROG[id] = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", {}) };
    return h("div", { class: "card" }, h("h2", {}, titulo), PROG[id].sub, PROG[id].chart, PROG[id].extra, ...extra);
  };
  const bloqueRec = (id, titulo) => {
    PROG[id] = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", {}) };
    return h("div", { class: "rec" }, h("h3", {}, titulo), PROG[id].sub, PROG[id].chart, PROG[id].extra);
  };
  raiz.replaceChildren(
    h("div", { class: "toggle", role: "group", "aria-label": "Periodo" }, [4, 8, 12].map(boton)),
    h("p", { class: "frase", "aria-live": "polite" }, (prog.resumen || {})[String(periodo)] || "Aún no hay corridas suficientes para comparar"),
    tarjeta("pct", "% del tiempo trotando"),
    tarjeta("ritmo", "Ritmo trotando"),
    tarjeta("vol", "Volumen semanal"),
    h("div", { class: "card" }, h("h2", {}, "Recuperación"), h("div", { class: "leyenda", id: "ley-rec" }),
      bloqueRec("hrv", "HRV nocturna"), bloqueRec("rhr", "FC en reposo"), bloqueRec("sueno", "Sueño")),
    tarjetaDoceSemanas(d),
    tarjetaCorridas(prog.corridas || []),
    enlaceDetalles());
}

function tarjetaDoceSemanas(d) {
  const plan = d.plan || {};
  const semanas = plan.semanas || [];
  const c = h("div", { class: "card" }, h("h2", {}, "12 semanas"));
  if (!semanas.length) { c.append(h("p", { class: "vacio" }, "Aún no hay plan cargado.")); return c; }
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
          "aria-label": `Semana ${x.n}, ${x.kind}${x.n === actual ? ", semana actual" : ""}`,
          onclick: () => { planSel = x.n; renderProgreso(d); dibujarProgreso(); } },
          h("strong", {}, x.n), h("span", {}, x.kind === "descarga" ? "descarga" : "carga"), x.n === actual ? h("em", {}, "actual") : null)))));
  }
  const est = actual === w.n ? plan.estado_sesiones ?? [] : [];
  c.append(linea,
    h("p", { class: "nota", style: "margin-top:10px" }, "Las semanas de descarga (línea punteada) son todo continuo en Z1–Z2. Toca una semana para ver sus sesiones."),
    h("h3", { style: "margin-top:12px" }, `Semana ${w.n} · bloque ${w.block} · ${w.kind}`),
    h("p", { class: "nota" }, w.focus || ""),
    ...(w.sessions || []).map((s) => filaSesion(s, est.find((e) => e.id === s.id))),
    ...((plan.semanas_repetidas || []).length ? [h("p", { class: "nota" }, `Semanas repetidas: ${plan.semanas_repetidas.join(", ")}.`)] : []));
  return c;
}

function tarjetaCorridas(corridas) {
  const orden = corridas.slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
  const celdas = (r) => [fechaLarga(r.fecha), r.sesion || "—", fmt(r.minutos, 0), fmt(r.km),
    r.pct_trote == null ? "—" : `${fmt(r.pct_trote, 0)} %`,
    r.caminadora ? "cam." : r.ritmo_trote_s == null ? "—" : mmss(r.ritmo_trote_s),
    r.fc_prom == null ? "—" : fmt(r.fc_prom, 0)];
  return h("div", { class: "card" }, h("h2", {}, "Corridas"),
    orden.length ? h("div", { class: "tabla-scroll ancha" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Fecha", "Sesión", "Min", "Km", "% trote", "Ritmo", "FC"].map((c) => h("th", {}, c)))),
      h("tbody", {}, orden.map((r) => h("tr", {}, celdas(r).map((c) => h("td", {}, c))))))) : h("p", { class: "vacio" }, "Aún no hay corridas registradas."),
    orden.some((r) => r.caminadora) ? h("p", { class: "nota", style: "margin-top:8px" }, "cam. = caminadora (su ritmo no se compara).") : null);
}

const ultimoValor = (serie) => { for (let i = serie.length - 1; i >= 0; i--) if (serie[i].y != null) return serie[i]; return null; };

function dibujarProgreso() {
  if (!PROG.pct || !datos) return;
  const ancho = PROG.pct.chart.clientWidth;
  if (!ancho) return;
  const prog = datos.progreso || {};
  const hoyMs = parseFecha((datos.generado || "").slice(0, 10) || "2000-01-01").getTime();
  const corte = hoyMs - periodo * 7 * 86400000;
  const aire = (prog.corridas || []).filter((r) => !r.caminadora && parseFecha(r.fecha).getTime() > corte);
  const dominio = [corte + 86400000, hoyMs];

  const puntosCorrida = (id, filtro, y, extra, texto, unidad, celda) => {
    const t = PROG[id];
    const pts = aire.filter(filtro).map((r) => ({ fecha: r.fecha, y: y(r), r }));
    t.chart.replaceChildren(pts.length ? lineChart({ ancho, serie: pts, dominio, marcadores: true, ...extra, texto: (p) => texto(p.r) })
      : h("p", { class: "vacio" }, "Aún no hay corridas al aire libre en este periodo."));
    t.sub.textContent = "Solo corridas al aire libre; la caminadora no entra.";
    t.extra.replaceChildren(pts.length ? tablaDatos(["Fecha", unidad], pts.slice().reverse().map((p) => [fechaLarga(p.fecha), celda(p.r)])) : "");
  };
  puntosCorrida("pct", (r) => r.pct_trote != null, (r) => r.pct_trote, { fmtY: (v) => `${fmt(v, 0)}`, etiqueta: "Porcentaje del tiempo trotando por corrida" },
    (r) => `${fechaLarga(r.fecha)} · ${fmt(r.pct_trote, 0)} % trotando · trote ${fmt(r.trote_min, 0)}' / caminata ${fmt(r.camina_min, 0)}'`, "% trotando", (r) => `${fmt(r.pct_trote, 0)} %`);
  puntosCorrida("ritmo", (r) => r.ritmo_trote_s != null, (r) => r.ritmo_trote_s, { fmtY: (v) => mmss(v), invertir: true, etiqueta: "Ritmo trotando por corrida" },
    (r) => `${fechaLarga(r.fecha)} · ${mmss(r.ritmo_trote_s)} /km${r.fc_trote ? ` · FC trotando ${fmt(r.fc_trote, 0)}` : ""}`, "Ritmo (min/km)", (r) => mmss(r.ritmo_trote_s));
  PROG.ritmo.sub.textContent = "Arriba = más rápido. Solo corridas al aire libre.";

  dibujarVolumen(ancho, prog);
  dibujarRecuperacion(ancho, prog, dominio);
}

function dibujarVolumen(ancho, prog) {
  const t = PROG.vol;
  const semanas = (prog.semanas || []).slice(-periodo);
  const hay = semanas.some((s) => (s.minutos || 0) > 0 || s.plan_min);
  t.sub.textContent = hay ? "Minutos de reloj por semana (lun–dom); la raya marca el plan." : "";
  const datosBarras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.min_trote || 0, s.min_camina || 0], meta: s.plan_min || 0, s }));
  t.chart.replaceChildren(hay ? barChart({
    ancho, semanas: datosBarras, clases: ["s1", "walk"], etiqueta: "Volumen semanal: trote y caminata con raya del plan",
    texto: (b) => `Semana del ${fechaLarga(b.inicio)} · ${fmt(b.s.minutos, 0)}'${b.s.plan_min ? ` (plan ${b.s.plan_min}')` : ""} · ${fmt(b.s.km)} km · trote ${fmt(b.s.min_trote, 0)}'`,
  }) : h("p", { class: "vacio" }, "Sin corridas en este periodo."));
  t.extra.replaceChildren(hay ? leyenda([["sw s1", "Trote"], ["sw walk", "Caminata"], ["raya", "Plan"]]) : "",
    hay ? tablaDatos(["Semana", "Min", "Plan", "Km", "Trote", "Caminata"], semanas.slice().reverse().map((s) =>
      [fechaLarga(s.inicio), fmt(s.minutos, 0), s.plan_min ?? "—", fmt(s.km), fmt(s.min_trote, 0), fmt(s.min_camina, 0)])) : "");
}

function dibujarRecuperacion(ancho, prog, dominio) {
  const dias = (prog.dias || []).slice(-periodo * 7);
  const umbral = ((datos.detalles || {}).umbrales || {}).sleep_min_hours;
  $("ley-rec").replaceChildren(...leyenda([["pto", "Diario"], ["rayaln", "Promedio 7 días"]]).children,
    ...(dias.some((x) => x.hrv_base_alta != null) ? [h("span", {}, h("i", { class: "banda-sw", "aria-hidden": "true" }), "Rango base (HRV)")] : []));
  const dom = dias.length ? [parseFecha(dias[0].fecha).getTime(), parseFecha(dias[dias.length - 1].fecha).getTime()] : dominio;
  const serie = (id, campo, campo7, extra, fmtV, unidad, nombre) => {
    const t = PROG[id];
    const s = dias.map((x) => ({ fecha: x.fecha, y: x[campo], p: x[campo7], lo: x.hrv_base_baja, hi: x.hrv_base_alta }));
    const ult = s.slice().reverse().find((p) => p.p != null);
    t.sub.textContent = ult ? `Promedio 7 días: ${fmtV(ult.p)}${unidad ? " " + unidad : ""} · ${fechaLarga(ult.fecha)}` : "Aún no hay promedio de 7 días (faltan datos).";
    t.chart.replaceChildren(lineChart({ ancho, serie: s, dominio: dom, puntos: true, promedio: s.map((p) => p.p), etiqueta: nombre, ...extra,
      texto: (p, prom) => `${fechaLarga(p.fecha)} · ${fmtV(p.y)}${unidad ? " " + unidad : ""}${prom != null ? ` · prom. 7 d ${fmtV(prom)}` : ""}${extra.banda && p.lo != null ? ` · base ${p.lo}–${p.hi}` : ""}` }));
    const filas = s.filter((p) => p.y != null).reverse().map((p) => [fechaLarga(p.fecha), fmtV(p.y), p.p == null ? "—" : fmtV(p.p)]);
    t.extra.replaceChildren(filas.length ? tablaDatos(["Fecha", unidad || "Sueño", "Prom. 7 d"], filas) : "");
  };
  serie("hrv", "hrv", "hrv_7d", { banda: dias.map((x) => ({ lo: x.hrv_base_baja, hi: x.hrv_base_alta })), fmtY: (v) => fmt(v, 0) }, (v) => fmt(v, 0), "ms", "HRV por noche");
  serie("rhr", "rhr", "rhr_7d", { fmtY: (v) => fmt(v, 0) }, (v) => fmt(v, 0), "lpm", "FC en reposo por día");
  serie("sueno", "sueño_h", "sueño_7d", { ref: umbral != null ? { y: umbral, etiqueta: null } : null, fmtY: (v) => fmt(v, 1) }, horasMin, "", "Horas de sueño");
  if (umbral != null) PROG.sueno.sub.textContent += ` · la raya marca ${horasMin(umbral)}`;
}

// --- Detalles ---

const DET = {};

function tarjetaFcMax(d) {
  const f = (d.detalles || {}).fc_max || {};
  const ses = f.sesiones || [];
  const faltan = Math.max(0, 2 - (f.semanas_medidas || 0));
  const cuerpo = !ses.length
    ? [h("p", { class: "nota" }, "Aún no hay clases de CrossFit medidas con correa. Con 2 semanas de mediciones se calcula la FC máx definitiva.")]
    : [h("div", { class: "kv" }, h("span", {}, "Clases medidas"), h("span", {}, ses.length)),
      h("div", { class: "kv" }, h("span", {}, "Pico"), h("span", {}, `${fmt(f.pico, 0)} lpm`)),
      h("div", { class: "kv" }, h("span", {}, "FC máx estimada (pico + 3, mín 183)"), h("span", {}, `${fmt(f.estimacion, 0)} lpm`)),
      h("p", { class: "estado" }, f.listo ? badge("ok", "✓", "listo") : badge("nd", "—", "en curso"),
        f.listo ? "Medición lista" : `Faltan ${faltan} ${faltan === 1 ? "semana" : "semanas"} de medición`),
      f.revisar ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, "La estimación pasa de 200 lpm: revísala antes de usarla.")) : null];
  const zonas = d.zonas || [];
  return h("div", { class: "card" }, h("h2", {}, "FC máxima y zonas"), ...cuerpo,
    zonas.length ? h("div", {}, h("p", { class: "nota", style: "margin-top:10px" }, `FC máx en uso: ${fmt(f.config, 0)} lpm (${f.fuente === "reloj" ? "del reloj" : "respaldo, el reloj no la dio"}) · reposo promedio 7 días: ${fmt(d.rhr_promedio_7d, 0)} lpm (Karvonen)`),
      h("table", {}, h("thead", {}, h("tr", {}, ["Zona", "Rango (lpm)"].map((c) => h("th", {}, c)))),
        h("tbody", {}, zonas.map((z) => h("tr", {}, h("td", {}, h("span", { class: "zchip" }, h("i", { style: `background:var(--${z.zona.toLowerCase()})`, "aria-hidden": "true" }), z.zona)), h("td", {}, `${z.piso}–${z.techo}`)))))) : h("p", { class: "vacio" }, "Sin zonas calculadas."));
}

function tarjetaComoFunciona(d) {
  const u = (d.detalles || {}).umbrales || {};
  const li = (...t) => h("li", {}, ...t);
  return h("div", { class: "card" }, h("h2", {}, "Cómo funciona"),
    h("p", {}, "Cada mañana se revisan 4 señales; el semáforo decide la sesión de hoy."),
    h("ul", { class: "reglas" },
      li(h("strong", {}, "HRV: "), "fuera si anoche quedó por debajo de tu rango base. Si el reloj la marca “baja”, el semáforo va directo a rojo."),
      li(h("strong", {}, "FC en reposo: "), `fuera si supera el promedio de 7 días + ${fmt(u.rhr_tolerance_bpm, 0)} lpm.`),
      li(h("strong", {}, "Sueño: "), `fuera si dormiste menos de ${fmt(u.sleep_min_hours, 1)} h.`),
      li(h("strong", {}, "RPE del CrossFit de ayer: "), `fuera si fue ${fmt(u.rpe_heavy, 0)} o más.`)),
    h("ul", { class: "reglas" },
      li(badge("ok", "✓", "verde"), " Verde: ninguna señal fuera → sesión normal."),
      li(badge("warn", "!", "amarillo"), " Amarillo: una señal fuera → versión suave."),
      li(badge("bad", "✕", "rojo"), " Rojo: dos o más señales fuera, o HRV baja → descanso o caminata ligera. Dos días rojos seguidos: repetir la semana."),
      li(badge("nd", "—", "sin datos"), " Sin datos: HRV, FC en reposo y sueño sin dato de anoche → sesión normal; decides por cómo te sientes.")),
    h("p", { class: "nota" }, "Una señal sin dato no cuenta como fuera."),
    h("h3", { style: "margin-top:12px" }, "Tus 3 corridas"),
    h("ul", { class: "reglas" },
      li("Cada semana: Z2 #1, Z2 #2 y la Larga (sábado o domingo). CrossFit lunes, martes y jueves."),
      li(h("strong", {}, "Asignación automática: "), "una corrida de sábado o domingo que dure al menos el ", fmt((u.done_ratio ?? 0.7) * 100, 0), " % de la Larga cuenta como Larga; las demás llenan Z2 #1 y Z2 #2 en orden. Si haces más, las sobrantes no se asignan."),
      li(h("strong", {}, "Hecha / incompleta: "), "hecha si duró al menos el ", fmt((u.done_ratio ?? 0.7) * 100, 0), " % de lo planeado (o de la versión suave si ese día era amarillo o rojo, y entonces sale “ajustada”); si duró menos, incompleta."),
      li(h("strong", {}, "¿Lo hice bien?: "), `los minutos sobre el techo de Z2 (zonas 3 a 5) deben ser ${fmt(u.ceiling_tolerance_min ?? 2, 0)}' o menos; en la Z2 #1 con picos opcionales de Z3 se permiten 2' más.`),
      li(h("strong", {}, "Tiempo: "), "es tiempo de reloj, caminatas incluidas. Trote y caminata vienen de los tramos que detecta Garmin; el ritmo trotando no cuenta la caminata.")),
    h("p", { class: "nota" }, "Las zonas usan Karvonen (% de la reserva de FC)."),
    h("p", {}, h("a", { href: `${REPO_DOCS}REQUISITOS.md`, target: "_blank", rel: "noopener" }, "Requisitos"), " · ",
      h("a", { href: `${REPO_DOCS}PLAN_ENTRENAMIENTO.md`, target: "_blank", rel: "noopener" }, "Plan de entrenamiento")));
}

function tarjetaCarga(det) {
  const c = bloqueCarga(det);
  DET.carga = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", {}) };
  c.append(h("h3", { style: "margin-top:14px" }, "Últimas 12 semanas"), DET.carga.sub, DET.carga.chart, DET.carga.extra);
  return c;
}

function renderDetalles(d) {
  const det = d.detalles || {};
  $("vista-detalles").replaceChildren(
    h("a", { class: "volver", href: "#hoy", onclick: (ev) => { ev.preventDefault(); location.hash = `#${vistaAnterior}`; } }, "← Volver"),
    tarjetaFcMax(d), tarjetaComoFunciona(d),
    det.distribucion ? zonaBar(det.distribucion) : null,
    det.carga ? tarjetaCarga(det) : null);
}

function dibujarDetalles() {
  if (!DET.carga || !datos) return;
  const ancho = DET.carga.chart.clientWidth;
  if (!ancho) return;
  const t = DET.carga;
  const semanas = ((datos.detalles || {}).carga_semanas || []);
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.carga_crossfit || 0, s.carga_corrida || 0], sin_rpe: s.sin_rpe || 0 }));
  const sinRpe = semanas.filter((s) => s.sin_rpe > 0);
  t.sub.textContent = "RPE × minutos por semana (lun–dom). Solo referencia.";
  t.chart.replaceChildren(barChart({
    ancho, semanas: barras, etiqueta: "Carga semanal apilada",
    texto: (s) => `Semana del ${fechaLarga(s.inicio)} · CrossFit ${fmt(s.valores[0], 0)} · Corrida ${fmt(s.valores[1], 0)} · Total ${fmt(s.valores[0] + s.valores[1], 0)}${s.sin_rpe ? ` · ${s.sin_rpe} sin RPE` : ""}`,
  }));
  t.extra.replaceChildren(leyenda([["sw s1", "CrossFit"], ["sw s2", "Corrida"]]),
    sinRpe.length ? h("p", { class: "nota" }, `* ${sinRpe.length === 1 ? "Una semana tiene" : `${sinRpe.length} semanas tienen`} sesiones sin RPE: la carga real es mayor.`) : "",
    barras.length ? tablaDatos(["Semana", "CrossFit", "Corrida", "Sin RPE"], barras.slice().reverse().map((s) => [fechaLarga(s.inicio), fmt(s.valores[0], 0), fmt(s.valores[1], 0), s.sin_rpe])) : "");
}

// --- arranque ---

const REDIBUJAR = { hoy: dibujarMejora, progreso: dibujarProgreso, detalles: dibujarDetalles };
let vistaActual = null;
let vistaAnterior = "hoy";

function actualizarEncabezado() {
  const iso = datos && (datos.datos_al || datos.generado);
  const hace = haceCuanto(iso);
  $("actualizado").textContent = hace ? `Actualizado ${hace}` : "";
}

function mostrarVista() {
  const nombre = location.hash.slice(1).split("?")[0];   // "#hoy?sem=+1" solo se lee al arrancar
  const v = VISTAS.includes(nombre) ? nombre : "hoy";
  if (vistaActual && vistaActual !== v && v === "detalles") vistaAnterior = vistaActual;
  vistaActual = v;
  for (const id of VISTAS) $(`vista-${id}`).hidden = id !== v;
  for (const a of document.querySelectorAll(".tabs a")) {
    if (a.dataset.tab === v) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  if (REDIBUJAR[v]) REDIBUJAR[v]();
  window.scrollTo(0, 0);
}

function aviso(id, msg) {
  $(`vista-${id}`).replaceChildren(h("p", { class: "vacio" }, msg));
}

async function iniciar() {
  leerSemanaInicial();
  window.addEventListener("hashchange", mostrarVista);
  let resizeT;
  window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { for (const f of Object.values(REDIBUJAR)) f(); }, 150); });
  mostrarVista();
  try {
    const resp = await fetch("data.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(resp.status);
    datos = await resp.json();
  } catch (e) {
    $("actualizado").textContent = "Sin datos";
    aviso("hoy", "No se pudieron cargar los datos. Intenta de nuevo en unos minutos.");
    return;
  }
  actualizarEncabezado();
  setInterval(actualizarEncabezado, 60000);
  const vistas = { hoy: renderHoy, progreso: renderProgreso, detalles: renderDetalles };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, "No se pudo mostrar esta sección con los datos actuales."); }
  }
  mostrarVista();
}

iniciar();
