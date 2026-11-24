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

function tablaDatos(cabeza, filas, titulo = "Ver como tabla") {
  return h("details", {}, h("summary", {}, titulo),
    h("div", { class: "tabla-scroll" }, h("table", {},
      h("thead", {}, h("tr", {}, cabeza.map((c) => h("th", {}, c)))),
      h("tbody", {}, filas.map((f) => h("tr", {}, f.map((c) => h("td", {}, c))))))));
}

const leyenda = (items) => h("div", { class: "leyenda" }, items.map(([cls, txt]) => h("span", {}, h("i", { class: cls, "aria-hidden": "true" }), txt)));

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
  const botones = vistas.map((v, i) => h("button", { type: "button", role: "tab", onclick: () => elegir(i, false),
    onkeydown: (ev) => {
      const k = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
      if (k) { ev.preventDefault(); elegir((SEL[titulo] + k + vistas.length) % vistas.length, true); }
    } }, v.etiqueta));
  const pintar = () => {
    const ancho = cuerpo.clientWidth;
    if (ancho) cuerpo.replaceChildren(vistas[SEL[titulo]].pintar(ancho));
  };
  const marcar = () => botones.forEach((b, i) => {
    b.setAttribute("aria-selected", i === SEL[titulo] ? "true" : "false");
    b.tabIndex = i === SEL[titulo] ? 0 : -1;
  });
  function elegir(i, foco) { SEL[titulo] = i; marcar(); pintar(); if (foco) botones[i].focus(); }
  marcar();
  PINTAR[vista].push(pintar);
  return h("div", { class: `card ${opts.clase || ""}` }, h("h2", {}, titulo), resumen ? h("p", { class: "nota" }, resumen) : null,
    vistas.length > 1 ? h("div", { class: "toggle segs", role: "tablist", "aria-label": titulo }, botones) : null, cuerpo, ...(opts.pie || []));
}

// --- Progreso ---

let periodo = 8;
let planSel = null;

const NUMEROS = {
  corridas: ["Corridas por semana", (v) => fmt(v, 1), ""], minutos: ["Minutos por semana", (v) => fmt(v, 0), "min"],
  km: ["Km por semana", (v) => fmt(v, 1), "km"], ritmo_z2: ["Ritmo en Z2", (v) => mmss(v), "/km"], pct_trote: ["% trote", (v) => fmt(v, 0), "%"],
};

/** Fila de números del periodo (ya calculados en Python) con el cambio contra el periodo anterior. */
function filaNumeros(d) {
  const items = (((d.progreso || {}).numeros || {}).periodos || {})[String(periodo)] || [];
  return h("div", { class: "numeros ancha", role: "group", "aria-label": `Números de las últimas ${periodo} semanas` }, items.map((x) => {
    const [nombre, fv, unidad] = NUMEROS[x.id] || [x.id, (v) => fmt(v, 1), ""];
    const cambio = x.valor == null ? "Sin corridas"
      : x.anterior == null ? "Sin periodo anterior"
        : x.delta === 0 || x.delta == null ? "= igual que el periodo anterior"
          : `${x.delta > 0 ? "▲" : "▼"} ${fv(Math.abs(x.delta))}${x.id === "ritmo_z2" ? "/km" : unidad && unidad !== "/km" ? " " + unidad : ""} vs periodo anterior`;
    return h("div", { class: "num" }, h("div", { class: "nota" }, nombre),
      h("div", { class: "num-v" }, x.valor == null ? "—" : fv(x.valor), x.valor != null && unidad ? h("span", { class: "num-u" }, ` ${unidad}`) : null),
      h("div", { class: `num-d${x.bueno ? " bien" : ""}` }, cambio));
  }));
}

function renderProgreso(d) {
  PINTAR.progreso = [];
  const raiz = $("vista-progreso");
  const prog = d.progreso || {};
  const boton = (n) => h("button", { type: "button", "aria-pressed": n === periodo ? "true" : "false",
    onclick: () => { periodo = n; renderProgreso(d); REDIBUJAR.progreso(); } }, `${n} semanas`);
  raiz.replaceChildren(...[
    h("div", { class: "toggle ancha", role: "group", "aria-label": "Periodo" }, [4, 8, 12].map(boton)),
    filaNumeros(d),
    tarjetaMejora(d),
    tarjetaCorridasProgreso(d),
    tarjetaMejoresMarcas(d),
    tarjetaCarreras(d),
    tarjetaDoceSemanas(d),
    enlaceDetalles()].filter(Boolean));
}

function tarjetaDoceSemanas(d) {
  const plan = d.plan || {};
  const semanas = plan.semanas || [];
  const c = h("div", { class: "card ancha" }, h("h2", {}, "12 semanas"));
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
          onclick: () => { planSel = x.n; c.replaceWith(tarjetaDoceSemanas(d)); } },
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

/** Contexto del periodo elegido: corridas al aire libre dentro del periodo y el dominio del eje x. */
function contextoPeriodo(d) {
  const prog = d.progreso || {};
  const hoyMs = parseFecha((d.generado || "").slice(0, 10) || "2000-01-01").getTime();
  const corte = hoyMs - periodo * 7 * 86400000;
  return { prog, dominio: [corte + 86400000, hoyMs],
    aire: (prog.corridas || []).filter((r) => !r.caminadora && parseFecha(r.fecha).getTime() > corte) };
}

function graficaCorridas(d, ancho, id) {
  const { aire, dominio } = contextoPeriodo(d);
  const cfg = id === "ritmo"
    ? { filtro: (r) => r.ritmo_trote_s != null, y: (r) => r.ritmo_trote_s, nota: "Arriba = más rápido. Solo corridas al aire libre.",
      extra: { fmtY: mmss, invertir: true, etiqueta: "Ritmo trotando por corrida" },
      texto: (r) => `${fechaLarga(r.fecha)} · ${mmss(r.ritmo_trote_s)} /km${r.fc_trote ? ` · FC trotando ${fmt(r.fc_trote, 0)}` : ""}` }
    : { filtro: (r) => r.pct_trote != null, y: (r) => r.pct_trote, nota: "Porcentaje del tiempo de la corrida que fue trote. Solo al aire libre.",
      extra: { fmtY: (v) => fmt(v, 0), etiqueta: "Porcentaje del tiempo trotando por corrida" },
      texto: (r) => `${fechaLarga(r.fecha)} · ${fmt(r.pct_trote, 0)} % trotando · trote ${fmt(r.trote_min, 0)}' / caminata ${fmt(r.camina_min, 0)}'` };
  const pts = aire.filter(cfg.filtro).map((r) => ({ fecha: r.fecha, y: cfg.y(r), r }));
  return h("div", {}, h("p", { class: "nota" }, cfg.nota),
    pts.length ? lineChart({ ancho, serie: pts, dominio, marcadores: true, ...cfg.extra, texto: (p) => cfg.texto(p.r) })
      : h("p", { class: "vacio" }, "Aún no hay corridas al aire libre en este periodo."));
}

function graficaVolumen(d, ancho) {
  const prog = d.progreso || {};
  const semanas = (prog.semanas || []).slice(-periodo);
  const hay = semanas.some((s) => (s.minutos || 0) > 0 || s.plan_min);
  if (!hay) return h("p", { class: "vacio" }, "Sin corridas en este periodo.");
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.min_trote || 0, s.min_camina || 0], meta: s.plan_min || 0, s }));
  return h("div", {}, h("p", { class: "nota" }, "Minutos de reloj por semana (lun–dom); la raya marca el plan."),
    barChart({ ancho, semanas: barras, clases: ["s1", "walk"], etiqueta: "Volumen semanal: trote y caminata con raya del plan",
      texto: (b) => `Semana del ${fechaLarga(b.inicio)} · ${fmt(b.s.minutos, 0)}'${b.s.plan_min ? ` (plan ${b.s.plan_min}')` : ""} · ${fmt(b.s.km)} km · trote ${fmt(b.s.min_trote, 0)}'` }),
    leyenda([["sw s1", "Trote"], ["sw walk", "Caminata"], ["raya", "Plan"]]),
    tablaDatos(["Semana", "Min", "Plan", "Km", "Trote", "Caminata"], semanas.slice().reverse().map((s) =>
      [fechaLarga(s.inicio), fmt(s.minutos, 0), s.plan_min ?? "—", fmt(s.km), fmt(s.min_trote, 0), fmt(s.min_camina, 0)]), "Ver semanas como tabla"));
}

function tarjetaCorridasProgreso(d) {
  const prog = d.progreso || {};
  const hayCaminatas = ((prog.numeros || {}).caminatas || {})[String(periodo)];
  const vistas = [{ etiqueta: "Volumen", pintar: (a) => graficaVolumen(d, a) },
    { etiqueta: "Ritmo", pintar: (a) => graficaCorridas(d, a, "ritmo") },
    ...(hayCaminatas ? [{ etiqueta: "% trote", pintar: (a) => graficaCorridas(d, a, "pct") }] : [])];
  return tarjetaConVistas("progreso", "Corridas", `Últimas ${periodo} semanas`, vistas, { clase: "ancha", pie: tablaCorridas(prog.corridas || []) });
}

function tablaCorridas(corridas) {
  const orden = corridas.slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
  const celdas = (r) => [fechaLarga(r.fecha), `${r.sesion || "—"}${r.carrera ? " · carrera" : ""}`, fmt(r.minutos, 0), fmt(r.km),
    r.pct_trote == null ? "—" : `${fmt(r.pct_trote, 0)} %`,
    r.caminadora ? "cam." : r.ritmo_trote_s == null ? "—" : mmss(r.ritmo_trote_s),
    r.fc_prom == null ? "—" : fmt(r.fc_prom, 0)];
  return [h("details", {}, h("summary", {}, "Ver como tabla"),
    orden.length ? h("div", { class: "tabla-scroll ancha" }, h("table", {},
      h("thead", {}, h("tr", {}, ["Fecha", "Sesión", "Min", "Km", "% trote", "Ritmo", "FC"].map((c) => h("th", {}, c)))),
      h("tbody", {}, orden.map((r) => h("tr", {}, celdas(r).map((c) => h("td", {}, c))))))) : h("p", { class: "vacio" }, "Aún no hay corridas registradas."),
    orden.some((r) => r.caminadora) ? h("p", { class: "nota", style: "margin-top:8px" }, "cam. = caminadora (su ritmo no se compara).") : null)];
}

// --- mejores marcas y carreras ---

const fechaConAnio = (iso, ref) => {
  const f = parseFecha(iso), anioRef = parseFecha((ref || iso).slice(0, 10)).getFullYear();
  return `${f.getDate()} ${MESES[f.getMonth()]}${f.getFullYear() !== anioRef ? ` ${f.getFullYear()}` : ""}`;
};

function tarjetaMejoresMarcas(d) {
  const marcas = d.mejores_marcas || [];
  const c = h("div", { class: "card" }, h("h2", {}, "Mejores marcas"));
  if (!marcas.length) { c.append(h("p", { class: "vacio" }, "Aún no hay marcas: se llenan con tus corridas de Garmin.")); return c; }
  c.append(h("div", { class: "marcas" }, marcas.map((x) => {
    const larga = x.clave === "larga";
    return h("div", { class: "marca", role: "group", "aria-label": `${x.nombre}: ${larga ? `${fmt(x.distancia_km, 2)} km en ${tiempoLargo(x.tiempo_s)}` : tiempoLargo(x.tiempo_s)}, ${fechaConAnio(x.fecha, d.generado)}` },
      h("div", { class: "marca-n" }, x.nombre, x.nuevo ? h("span", { class: "nuevo" }, "nuevo") : null),
      h("div", { class: "marca-v" }, larga ? `${fmt(x.distancia_km, 2)} km` : tiempoLargo(x.tiempo_s)),
      h("div", { class: "nota" }, larga ? `${tiempoLargo(x.tiempo_s)} · ` : "", fechaConAnio(x.fecha, d.generado)));
  })));
  return c;
}

function filaStat(nombre, valor) {
  return valor == null ? null : h("div", { class: "kv" }, h("span", {}, nombre), h("span", {}, valor));
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
    h("div", { class: "leyenda" }, ks.map((k) => h("span", {}, h("i", { style: `background:var(--${k.toLowerCase()})`, "aria-hidden": "true" }), `${k} ${fmt(z[k], 0)}'`))));
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

function carreraDetalle(c, abierta, ref) {
  const det = h("details", { class: "ses carrera-det", open: abierta },
    h("summary", {}, h("span", { class: "n" }, fechaLarga(c.fecha)),
      h("span", { class: "m" }, `${fmt(c.distancia_km, 2)} km · ${tiempoLargo(c.tiempo_s)}`)),
    h("div", { class: "carrera-cuerpo" },
      filaStat("Distancia", `${fmt(c.distancia_km, 2)} km`), filaStat("Tiempo", tiempoLargo(c.tiempo_s)),
      filaStat("Ritmo promedio", c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : null),
      filaStat("FC promedio / máxima", c.fc_prom != null ? `${fmt(c.fc_prom, 0)} / ${c.fc_max != null ? fmt(c.fc_max, 0) : "—"} lpm` : null),
      filaStat("Km más rápido", c.km_mas_rapido_s ? `${mmss(c.km_mas_rapido_s)} /km` : null),
      filaStat("Cadencia", c.cadencia ? `${c.cadencia} pasos/min` : null),
      filaStat("Desnivel", c.desnivel_m != null ? `+${c.desnivel_m} m` : null),
      barrasKm(c), zonasCarrera(c), comparacionCarrera(c)));
  return det;
}

function tarjetaCarreras(d) {
  const cs = d.carreras || [];
  const c = h("div", { class: "card", id: "prog-carreras" }, h("h2", {}, "Carreras"));
  if (!cs.length) { c.append(h("p", { class: "vacio" }, "Cuando marques una actividad como Carrera en Garmin, aparece aquí.")); return c; }
  c.append(...cs.map((x, i) => carreraDetalle(x, i === 0 && abrirCarrera)));
  return c;
}

// --- Composición corporal estilo InBody ---

const ZONA_TXT = { bajo: ["▼", "bajo"], normal: ["✓", "normal"], alto: ["▲", "alto"] };
const fechaMes = (iso) => { const f = parseFecha(iso); return `${f.getDate()} ${MESES[f.getMonth()]} ${String(f.getFullYear()).slice(2)}`; };
const kg1 = (v) => fmt(v, 1);

/** Una barra de la hoja: la franja Bajo·Normal·Alto va arriba del grupo; la barra llega a `pos` y su valor va al final. */
function barraInbody(f) {
  const txt = f.estimado ? `≈${fmt(f.valor, 1)}` : fmt(f.valor, 1);
  const [icono, zona] = ZONA_TXT[f.zona];
  const dentro = f.pos > 0.8;
  const etiqueta = `${f.nombre}: ${fmt(f.valor, 1)} ${f.unidad}${f.pct != null ? `, ${f.pct} % del valor estándar` : ""}${f.estimado ? " (estimado)" : ""}, zona ${zona}`;
  return h("div", { class: "ib-fila", role: "img", "aria-label": etiqueta },
    h("div", { class: "ib-nombre" }, h("strong", {}, f.nombre), h("span", { class: "nota" }, ` ${f.unidad}`),
      h("span", { class: `ib-zona ${f.zona}`, "aria-hidden": "true" }, `${icono} ${zona}`)),
    h("div", { class: "ib-pista" },
      h("i", { class: "ib-normal", style: `left:${f.normal_pos[0] * 100}%;width:${(f.normal_pos[1] - f.normal_pos[0]) * 100}%` }),
      h("i", { class: "ib-barra", style: `width:${f.pos * 100}%` }),
      h("span", { class: `ib-valor${dentro ? " dentro" : ""}`, style: `left:${f.pos * 100}%` }, txt)),
    h("div", { class: "ib-ticks", "aria-hidden": "true" }, f.escala.map((v, i) => h("span", { style: `left:${(i / (f.escala.length - 1)) * 100}%` }, fmt(v, v % 1 ? 1 : 0)))));
}

function grupoInbody(titulo, filas) {
  if (!filas || !filas.length) return null;
  const n = filas[0].normal_pos;
  return h("div", { class: "ib-grupo" }, h("h3", {}, titulo),
    h("div", { class: "ib-franja", "aria-hidden": "true" },
      h("span", { style: `width:${n[0] * 100}%` }, "Bajo"), h("span", { class: "normal", style: `width:${(n[1] - n[0]) * 100}%` }, "Normal"),
      h("span", { style: `width:${(1 - n[1]) * 100}%` }, "Alto")),
    filas.map(barraInbody));
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
    h("p", { class: "meta-prime" }, meta.faltan_pgc > 0 ? `Te faltan ${fmt(meta.faltan_pgc, 1)} % de grasa para tu prime` : "Ya superaste tu prime en grasa ✓"),
    meta.mme_ok ? h("p", { class: "nota" }, "Tu músculo ya está arriba del de tu prime ✓") : h("p", { class: "nota" }, `Te faltan ${fmt(meta.faltan_mme, 1)} kg de músculo para tu prime`));
}

function puntuacionInbody(c) {
  const pts = c.puntuacion || [], v = c.visceral;
  if (!pts.length && !v) return null;
  const ult = pts[pts.length - 1];
  const bloqueP = ult ? h("div", { class: "ib-punt" }, h("h3", {}, "Puntuación InBody"),
    h("div", { class: "ib-punt-n" }, h("span", { class: "grande" }, fmt(ult.puntos, 0)), h("span", { class: "nota" }, "/100"),
      ult.delta != null ? h("span", { class: `delta${ult.delta > 0 ? " bien" : ""}` }, ` ${ult.delta > 0 ? "▲" : ult.delta < 0 ? "▼" : "="}${Math.abs(ult.delta)}`) : null),
    h("div", { class: "ib-punt-h" }, miniPuntuacion(pts))) : null;
  const rango = v ? v.rango : null;
  const [icono, clase] = v ? (v.zona === "normal" ? ["✓", "ok"] : v.zona === "alto" ? ["!", "warn"] : ["!", "warn"]) : [];
  const bloqueV = v ? h("div", { class: "ib-visc" }, h("h3", {}, "Grasa visceral"),
    h("div", { class: "ib-punt-n" }, h("span", { class: "grande" }, fmt(v.valor, 0)), h("span", { class: "nota" }, ` · rango ${rango[0]}–${rango[1]}`)),
    h("p", { class: "estado" }, badge(clase, icono, `grasa visceral ${v.zona}`),
      v.zona === "normal" ? "Dentro del rango" : v.zona === "alto" ? "Por encima del rango" : "Por debajo del rango")) : null;
  return h("div", { class: "ib-grupo ib-fila2" }, bloqueP, bloqueV);
}

/** Historial de la puntuación: con un solo punto, solo el punto y una nota. */
function miniPuntuacion(pts) {
  const caja = h("div", { class: "ib-punt-g" });
  PINTAR.cuerpo.push(() => {
    const ancho = caja.clientWidth;
    if (!ancho) return;
    caja.replaceChildren(miniLinea({ ancho, valores: pts.map((p) => p.puntos), clase: "s1", prime: null, fmt: (v) => fmt(v, 0),
      fechas: pts.map((p) => fechaMes(p.fecha)), etiqueta: "Historial de la puntuación InBody" }),
    pts.length === 1 ? h("p", { class: "nota" }, "Se llena con tus próximas mediciones.") : null);
  });
  return caja;
}

const SEGMENTOS = [["brazo_izq", "Brazo izq."], ["brazo_der", "Brazo der."], ["tronco", "Tronco"], ["pierna_izq", "Pierna izq."], ["pierna_der", "Pierna der."]];

function hojaCompleta(c) {
  const hoja = c.hoja;
  if (!hoja) return null;
  const tabla = (cabeza, filas) => h("div", { class: "tabla-scroll ancha" }, h("table", {},
    h("thead", {}, h("tr", {}, cabeza.map((x) => h("th", {}, x)))), h("tbody", {}, filas.map((f) => h("tr", {}, f.map((x) => h("td", {}, x)))))));
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
  return h("details", { class: "ib-hoja" }, h("summary", {}, "Ver hoja completa"), ...bloques);
}

/** Tarjeta única «Composición corporal · fecha» en el orden de la hoja InBody. Sin InBody no hay tarjeta. */
function tarjetaComposicion(c) {
  if (!c || !(c.mediciones || []).length) return null;
  const hoja = c.hoja || {};
  return h("div", { class: "card ancha ib" }, h("h2", {}, `Composición corporal · ${fechaMes(hoja.fecha || c.ultima.fecha)}`),
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
    leyenda([["pto", "Diario"], ["rayaln", "Promedio 7 días"], ...(id === "hrv" && dias.some((x) => x.hrv_base_alta != null) ? [["banda-sw", "Rango base (HRV)"]] : [])]),
    filas.length ? tablaDatos(["Fecha", def.unidad || "Sueño", "Prom. 7 d"], filas) : "");
}

function tarjetaRecuperacion(d) {
  return tarjetaConVistas("cuerpo", "Recuperación", "Últimas 12 semanas", [
    { etiqueta: "HRV", pintar: (a) => graficaRecuperacion(d, a, "hrv") },
    { etiqueta: "FC reposo", pintar: (a) => graficaRecuperacion(d, a, "rhr") },
    { etiqueta: "Sueño", pintar: (a) => graficaRecuperacion(d, a, "sueno") }]);
}

function renderCuerpo(d) {
  PINTAR.cuerpo = [];
  $("vista-cuerpo").replaceChildren(...[tarjetaRecuperacion(d), tarjetaComposicion(d.composicion), tarjetaFcMax(d), enlaceDetalles()].filter(Boolean));
}

// --- Detalles ---

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
      h("p", { class: "estado" }, f.listo ? badge("ok", "✓", "listo") : badge("nd", "—", "en curso"),
        f.listo ? "Medición lista" : `Faltan ${faltan} ${faltan === 1 ? "semana" : "semanas"} de medición`),
      f.revisar ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, `La estimación pasa de ${fmt(u.max_hr_review_above, 0)} lpm: revísala antes de usarla.`)) : null];
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
      li(h("strong", {}, `${nombreSenal("rpe")}: `), `fuera si fue ${fmt(u.rpe_heavy, 0)} o más.`)),
    h("ul", { class: "reglas" },
      li(badge("ok", "✓", "verde"), " Verde: ninguna señal fuera → sesión normal."),
      li(badge("warn", "!", "amarillo"), " Amarillo: una señal fuera → versión suave."),
      li(badge("bad", "✕", "rojo"), " Rojo: dos o más señales fuera, o HRV baja → descanso o caminata ligera. Dos días rojos seguidos: repetir la semana."),
      li(badge("nd", "—", "sin datos"), " Sin datos: HRV, FC en reposo y sueño sin dato de anoche → sesión normal; decides por cómo te sientes.")),
    h("p", { class: "nota" }, "Una señal sin dato no cuenta como fuera."),
    h("h3", { style: "margin-top:12px" }, "Tus 3 corridas"),
    h("ul", { class: "reglas" },
      li(ui().textos.semana || "Cada semana: tus sesiones del plan; la Larga va sábado o domingo."),
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
  PINTAR.detalles = [dibujarDetalles];
  $("vista-detalles").replaceChildren(
    h("a", { class: "volver ancha", href: "#hoy", onclick: (ev) => { ev.preventDefault(); location.hash = `#${vistaAnterior}`; } }, "← Volver"),
    tarjetaComoFunciona(d),
    det.distribucion ? zonaBar(det.distribucion) : null,
    det.carga ? tarjetaCarga(det) : null);
}

function dibujarDetalles() {
  if (!DET.carga || !datos) return;
  const ancho = DET.carga.chart.clientWidth;
  if (!ancho) return;
  const t = DET.carga;
  const semanas = ((datos.detalles || {}).carga_semanas || []);
  const cats = ui().categorias, clases = [...cats.map((c) => c.clase), "s2"];
  const nombres = [...cats.map((c) => c.nombre), "Corrida"];
  const barras = semanas.map((s) => ({ inicio: s.inicio, valores: [...cats.map((c) => (s.cargas || {})[c.id] || 0), s.carga_corrida || 0], sin_rpe: s.sin_rpe || 0 }));
  const suma = (s) => s.valores.reduce((a, v) => a + v, 0);
  const sinRpe = semanas.filter((s) => s.sin_rpe > 0);
  t.sub.textContent = "RPE × minutos por semana (lun–dom). Solo referencia.";
  t.chart.replaceChildren(barChart({
    ancho, semanas: barras, etiqueta: "Carga semanal apilada", clases,
    texto: (s) => `Semana del ${fechaLarga(s.inicio)} · ${nombres.map((n, i) => `${n} ${fmt(s.valores[i], 0)}`).join(" · ")} · Total ${fmt(suma(s), 0)}${s.sin_rpe ? ` · ${s.sin_rpe} sin RPE` : ""}`,
  }));
  t.extra.replaceChildren(leyenda(clases.map((c, i) => [`sw ${c}`, nombres[i]])),
    sinRpe.length ? h("p", { class: "nota" }, `* ${sinRpe.length === 1 ? "Una semana tiene" : `${sinRpe.length} semanas tienen`} sesiones sin RPE: la carga real es mayor.`) : "",
    barras.length ? tablaDatos(["Semana", ...nombres, "Sin RPE"], barras.slice().reverse().map((s) => [fechaLarga(s.inicio), ...s.valores.map((v) => fmt(v, 0)), s.sin_rpe])) : "");
}

// --- tema ---

const temaActual = () => (document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");

function pintarBotonTema() {
  const claro = temaActual() === "light", btn = $("tema-btn");
  btn.firstChild.textContent = claro ? "☾" : "☀";
  btn.setAttribute("aria-label", claro ? "Cambiar a tema oscuro" : "Cambiar a tema claro");
}

function cambiarTema() {
  const nuevo = temaActual() === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", nuevo);
  document.querySelector('meta[name="color-scheme"]').setAttribute("content", nuevo);
  try { localStorage.setItem("tema", nuevo); } catch (e) { /* sin almacenamiento: vale solo esta visita */ }
  pintarBotonTema();
}

// --- arranque ---

const REDIBUJAR = Object.fromEntries(VISTAS.map((v) => [v, () => PINTAR[v].forEach((f) => f())]));
let vistaActual = null;
let vistaAnterior = "hoy";

/** Título y enlace de GitHub Actions vienen de data.json (ui), no del HTML. */
function pintarEncabezado() {
  const u = ui();
  if (u.titulo) { $("titulo").textContent = u.titulo; document.title = `Garmin · ${u.titulo}`; }
  $("acciones").hidden = !u.acciones_url;
  if (u.acciones_url) $("acciones-link").href = u.acciones_url;
}

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
  if (abrirCarrera && v === "progreso") {   // venimos de la tarjeta de carrera de Hoy
    abrirCarrera = false;
    const det = document.querySelector("#prog-carreras .carrera-det");
    if (det) { det.open = true; det.scrollIntoView({ block: "start" }); }
  }
}

function aviso(id, msg) {
  $(`vista-${id}`).replaceChildren(h("p", { class: "vacio" }, msg));
}

async function iniciar() {
  pintarBotonTema();
  $("tema-btn").addEventListener("click", cambiarTema);
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
  pintarEncabezado();
  actualizarEncabezado();
  setInterval(actualizarEncabezado, 60000);
  const vistas = { hoy: renderHoy, progreso: renderProgreso, cuerpo: renderCuerpo, detalles: renderDetalles };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, "No se pudo mostrar esta sección con los datos actuales."); }
  }
  mostrarVista();
}

iniciar();
