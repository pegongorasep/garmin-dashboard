// Dashboard: solo pinta lo que recibe de data.json (la lógica vive en dashboard/build.py).
const VISTAS = ["hoy", "progreso", "detalles"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const DIAS_LARGO = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
let datos = null;

// --- utilidades ---

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

const fmt = (n, d = 1) => (n === null || n === undefined ? "—" : Number(n).toLocaleString("es-MX", { maximumFractionDigits: d }));

function parseFecha(iso) {
  // "YYYY-MM-DD" como fecha local, sin saltos por zona horaria
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return new Date(y, m - 1, d);
}

function fechaCorta(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()]} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function haceCuanto(iso) {
  if (!iso) return null;
  const t = Date.parse(iso.replace(/T(\d\d:\d\d)([+-]\d\d:\d\d)$/, "T$1:00$2"));
  if (Number.isNaN(t)) return null;
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 1) return "hace un momento";
  if (min < 60) return `hace ${min} min`;
  if (min < 1440) return `hace ${Math.round(min / 60)} h`;
  return `hace ${Math.round(min / 1440)} d`;
}

// --- estado con ícono + texto ---

const ESTADO_SEMAFORO = {
  verde: { clase: "ok", icono: "✓", titulo: "Verde", texto: "Recuperación: todo bien" },
  amarillo: { clase: "warn", icono: "!", titulo: "Amarillo", texto: "Recuperación: suave hoy" },
  rojo: { clase: "bad", icono: "✕", titulo: "Rojo", texto: "Recuperación: descanso hoy" },
  sin_datos: { clase: "nd", icono: "—", titulo: "Sin datos", texto: "Recuperación: sin datos de anoche" },
};

const badge = (clase, icono, etiqueta) =>
  h("span", { class: `badge ${clase}`, role: "img", "aria-label": etiqueta }, icono);

function badgeSenal(estado) {
  if (estado === "ok") return badge("ok", "✓", "en rango");
  if (estado === "fuera") return badge("warn", "!", "fuera de rango");
  return badge("nd", "—", "sin dato");
}

// --- vista Hoy ---

const NOMBRE_SENAL = { hrv: "HRV de anoche", rhr: "FC en reposo", sueno: "Sueño", rpe: "RPE del CrossFit de ayer" };
const ETIQUETA_PASO = { warmup: "calentamiento", run: "trote", walk: "caminata", cooldown: "enfriamiento" };

function pasoLi(p) {
  if (p.kind === "repeat") {
    return h("li", {}, h("span", { class: "min" }, `${p.times}× (`), h("ul", {}, p.steps.map(pasoLi)), h("span", { class: "min" }, ")"));
  }
  const z = p.zone;
  const color = z.startsWith("Z") ? `var(--z${z.slice(1, 2)})` : "var(--axis)";
  const nota = p.note && !(p.optional && p.note === "opcional") ? ` · ${p.note}` : "";
  return h("li", {},
    h("span", { class: "min" }, `${p.minutes} min`),
    h("span", { class: "zchip" }, h("i", { style: `background:${color}`, "aria-hidden": "true" }), z),
    p.lpm ? h("span", { class: "lpm" }, `${p.lpm[0]}–${p.lpm[1]} lpm`) : null,
    h("span", { class: "nota" }, ETIQUETA_PASO[p.kind] || p.kind, p.optional ? " (opcional)" : "", nota));
}

const mmss = (seg) => {
  if (seg === null || seg === undefined) return "—";
  const t = Math.round(seg);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

function barraRW(tr) {
  const total = tr.trote_min + tr.camina_min;
  if (total <= 0) return null;
  const seg = (min, cls) => (min > 0 ? h("div", { class: cls, style: `flex:${min} 1 0` }) : null);
  return h("div", {},
    h("div", { class: "barra-rw", role: "img", "aria-label": `Trote ${fmt(tr.trote_min, 0)} min, caminata ${fmt(tr.camina_min, 0)} min` },
      seg(tr.trote_min, "trote"), seg(tr.camina_min, "camina")),
    h("div", { class: "leyenda" },
      h("span", {}, h("i", { class: "sw s1", "aria-hidden": "true" }), `Trote ${fmt(tr.trote_min, 0)}'`),
      h("span", {}, h("i", { class: "sw walk", "aria-hidden": "true" }), `Caminata ${fmt(tr.camina_min, 0)}'`)));
}

function detalleTrote(u) {
  const tr = u.trote;
  if (!tr) return [h("p", { class: "nota" }, "Garmin no detectó tramos de trote y caminata en esta corrida.")];
  const patron = tr.caminatas > 0
    ? `${tr.caminatas} ${tr.caminatas === 1 ? "caminata" : "caminatas"} · patrón ≈ ${mmss((tr.patron_trote_min || 0) * 60)} / ${mmss((tr.patron_camina_min || 0) * 60)}`
    : "Sin caminatas: trotaste todo el tiempo";
  const ritmo = tr.ritmo_trote_s
    ? `Ritmo trotando ${mmss(tr.ritmo_trote_s)} /km${tr.fc_trote ? ` a ${fmt(tr.fc_trote, 0)} lpm` : ""}${u.caminadora ? " · caminadora" : ""}`
    : null;
  return [barraRW(tr), h("p", { class: "nota", style: "margin-top:8px" }, patron), ritmo ? h("p", {}, ritmo) : null].filter(Boolean);
}

// --- Sesiones del plan ---

function estadoSesion(est) {
  if (!est) return null;
  if (est.estado === "pendiente") return h("span", { class: "estado" }, badge("nd", "—", "pendiente"), "Pendiente");
  if (est.estado === "incompleta") return h("span", { class: "estado" }, badge("warn", "!", "incompleta"), "Incompleta");
  if (est.ajustada) return h("span", { class: "estado" }, badge("warn", "!", "hecha y ajustada"), "Hecha · ajustada");
  return h("span", { class: "estado" }, badge("ok", "✓", "hecha"), "Hecha");
}

const GARMIN_COMO = "Entrenamientos → Crear entrenamiento → Correr. Agrega un paso por línea (los grupos “N× ( … )” van como repetición). En cada paso elige duración en minutos y, como objetivo, “Alerta de FC” con el rango de lpm de arriba.";

/** Pasos, versión suave y cómo crearla en Garmin Connect (cuerpo desplegable de una sesión del plan). */
function cuerpoPlan(s) {
  return [h("ul", { class: "pasos" }, (s.steps || []).map(pasoLi)),
    s.easy ? h("details", {}, h("summary", {}, `Versión suave (${s.easy.minutes} min)`),
      h("ul", { class: "pasos" }, (s.easy.steps || []).map(pasoLi))) : null,
    comoGarmin()];
}

const comoGarmin = () =>
  h("details", {}, h("summary", {}, "Cómo crearla en Garmin Connect"), h("p", { class: "nota", style: "margin-top:6px" }, GARMIN_COMO));

/** Fila compacta de una sesión: nombre, minutos y estado; al abrirla, pasos, versión suave y cómo crearla en Garmin. */
function filaSesion(s, est) {
  return h("details", { class: "ses" },
    h("summary", {}, h("span", { class: "n" }, s.name), h("span", { class: "m" }, `${s.minutes} min`), estadoSesion(est)),
    ...cuerpoPlan(s));
}

const enlaceDetalles = () => h("a", { class: "enlace-detalles", href: "#detalles" }, "Detalles: zonas, reglas, intensidad y carga →");

// --- vista Hoy ---

const nombreSesion = (estado, id) => ((estado || []).find((e) => e.id === id) || {}).name;

function banner(d) {
  const t = d.hoy.tarjeta, plan = d.plan || {}, est = plan.estado_sesiones || [];
  const prox = nombreSesion(est, t.proxima_id);
  let texto = null;
  if (t.tipo === "crossfit") texto = prox ? `Hoy CrossFit · próxima corrida: ${prox}` : "Hoy CrossFit";
  else if (t.tipo === "hecha_hoy") texto = prox ? `Corrida de hoy hecha · próxima: ${prox}` : "Corrida de hoy hecha";
  else if (t.tipo === "sin_plan") {
    texto = plan.inicio && (d.generado || "").slice(0, 10) < plan.inicio ? `El plan arranca el ${fechaCorta(plan.inicio)}` : "Hoy no hay semana de plan activa";
  } else if (t.tipo === "completa") texto = "Semana completa: hiciste las 3";
  return texto ? h("p", { class: "banner" }, texto) : null;
}

function flecha(delta, texto) {
  return `${delta > 0 ? "▲" : delta < 0 ? "▼" : "="} ${texto}`;
}

function comparacion(s) {
  const a = s.anterior;
  if (!a) return null;
  if (!a.minutos && !a.km) return "Semana pasada sin corridas";
  const total = `Semana pasada: ${fmt(a.minutos, 0)} min · ${fmt(a.km)} km`;
  // Solo se compara cuando esta semana ya la superó; a media semana una flecha ▼ asusta sin razón.
  if ((s.minutos || 0) < a.minutos) return total;
  const dm = Math.round(s.minutos - a.minutos), dk = Math.round(((s.km || 0) - a.km) * 10) / 10;
  return `${total} · ya la superaste: ${flecha(dm, `${Math.abs(dm)} min`)} · ${flecha(dk, `${fmt(Math.abs(dk))} km`)}`;
}

/** Barra de progreso: minutos hechos / minutos del plan; el relleno se corta en 100 %. */
function barraProgreso(min, plan) {
  if (!plan) return h("p", { class: "prog-txt" }, `${fmt(min, 0)} min`);
  const pct = Math.round((min / plan) * 100);
  return h("div", {},
    h("div", { class: "prog", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": Math.min(pct, 100),
      "aria-label": `${fmt(min, 0)} de ${fmt(plan, 0)} minutos` }, h("div", { style: `width:${Math.min(pct, 100)}%` })),
    h("p", { class: "prog-txt" }, `${fmt(min, 0)} / ${fmt(plan, 0)} min · ${pct} %`));
}

function tarjetaEstaSemana(d) {
  const s = d.semana, plan = d.plan || {}, semanas = plan.semanas || [];
  const w = semanas.find((x) => x.n === plan.semana_actual);
  const titulo = w ? `Esta semana · Semana ${w.n} de ${semanas.length} · ${w.kind}` : "Esta semana";
  const c = h("div", { class: "card" }, h("h2", {}, titulo));
  if (s.sesiones_total > 0) {
    c.append(h("div", { class: "grande" }, `${s.hechas} de ${s.sesiones_total} corridas`,
      s.incompletas > 0 ? h("span", { class: "chico" }, ` · ${s.incompletas} ${s.incompletas === 1 ? "incompleta" : "incompletas"}`) : null));
  }
  c.append(barraProgreso(s.minutos || 0, s.plan_min));
  const partes = [s.km !== null && s.km !== undefined ? `${fmt(s.km)} km` : null,
    s.min_trote ? `${fmt(s.min_trote, 0)}' trotando` : null,
    s.pct_trote !== null && s.pct_trote !== undefined ? `${fmt(s.pct_trote, 0)} % trote` : null].filter(Boolean);
  if (partes.length && s.minutos) c.append(h("p", { class: "resumen-sem" }, partes.join(" · ")));
  const comp = comparacion(s);
  if (comp) c.append(h("p", { class: "nota" }, comp));
  const u = d.ultima_corrida;
  if (u && s.hechas + s.incompletas === 0 && !s.minutos) {
    c.append(h("p", { class: "nota" }, `Última corrida: ${fechaCorta(u.fecha)} · ${fmt(u.minutos, 0)}' · ${fmt(u.km)} km`));
  }
  return c;
}

function lineaTecho(c) {
  const txt = `${fmt(c.min_sobre_techo)}' sobre el techo (tolerancia ${fmt(c.tolerancia_min, 0)}')`;
  return c.techo_ok
    ? h("p", { class: "estado" }, badge("ok", "✓", "dentro del techo"), txt)
    : h("p", { class: "estado" }, badge("warn", "!", "sobre el techo"), txt);
}

function filaHecha(e) {
  const c = e.corrida || {};
  const datos = [c.minutos != null ? `${fmt(c.minutos, 0)}'` : null, c.km != null ? `${fmt(c.km)} km` : null,
    c.pct_trote != null ? `${fmt(c.pct_trote, 0)} % trote` : null,
    c.ritmo_trote_s ? `${mmss(c.ritmo_trote_s)} /km${c.caminadora ? " (caminadora)" : ""}` : null].filter(Boolean);
  return h("div", { class: "corrida" },
    h("div", { class: "cab-c" }, estadoSesion(e), h("span", { class: "n" }, `${e.name} · ${e.fecha ? fechaCorta(e.fecha) : ""}`)),
    datos.length ? h("p", { class: "datos" }, datos.join(" · ")) : null,
    c.techo_ok !== undefined ? lineaTecho(c) : null,
    h("details", {}, h("summary", {}, "Ver detalle"),
      ...detalleTrote({ trote: c.trote_min != null ? c : null, caminadora: c.caminadora })));
}

function filaHoy(e, s, t) {
  const suave = t.version === "suave";
  const ses = s && suave ? s.easy : s;
  const c = h("div", { class: "corrida hoy" },
    h("div", { class: "cab-c" }, h("span", { class: "chip-hoy" }, "HOY"),
      h("span", { class: "n" }, t.version === "descanso" ? e.name : `${e.name}${ses ? ` · ${ses.minutes} min` : ""}${suave ? " (versión suave)" : ""}`)));
  if (t.motivo) c.append(h("p", { class: "nota" }, `Por: ${t.motivo}`));
  if (t.version === "descanso") {
    c.append(h("p", {}, "Hoy descanso o caminata ligera de 20–30' en Z1"));
  } else if (ses) {
    c.append(h("ul", { class: "pasos" }, ses.steps.map(pasoLi)));
  }
  if (t.aviso) c.append(h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, t.aviso)));
  if (t.version !== "descanso" && ses) c.append(comoGarmin());
  return c;
}

function filaPendiente(e, s) {
  const larga = e.tipo === "larga";
  return h("details", { class: "ses corrida" },
    h("summary", {}, h("span", { class: "n" }, e.name),
      h("span", { class: "m" }, `${s ? `${s.minutes} min` : ""}${larga ? `${s ? " · " : ""}sáb o dom` : ""}`)),
    ...(s ? cuerpoPlan(s) : []));
}

function tarjetaTusCorridas(d) {
  const plan = d.plan || {}, est = plan.estado_sesiones || [], t = d.hoy.tarjeta;
  const w = (plan.semanas || []).find((x) => x.n === plan.semana_actual);
  if (!w || !est.length) return null;
  const filas = est.map((e) => {
    const s = (w.sessions || []).find((x) => x.id === e.id);
    if (e.estado !== "pendiente") return filaHecha(e);
    if (t.tipo === "sesion" && t.sesion_id === e.id) return filaHoy(e, t.sesion || s, t);
    return filaPendiente(e, s);
  });
  return h("div", { class: "card" }, h("h2", {}, `Tus ${est.length} corridas`), ...filas);
}

function recuperacion(d) {
  const sem = d.hoy.semaforo, est = ESTADO_SEMAFORO[sem.color] || ESTADO_SEMAFORO.sin_datos;
  return h("details", { class: "recup" },
    h("summary", {}, badge(est.clase, est.icono, est.titulo), est.texto, h("span", { class: "nota" }, " · ver señales")),
    h("ul", { class: "senales" }, (d.hoy["señales"] || []).map((x) =>
      h("li", {}, badgeSenal(x.estado),
        h("div", {}, h("div", { class: "nombre" }, NOMBRE_SENAL[x.id] || x.id), h("div", { class: "nota" }, x.texto))))));
}

function renderHoy(d) {
  $("vista-hoy").replaceChildren(...[
    d.hoy.semaforo.repetir_semana
      ? h("div", { class: "aviso bad" }, badge("bad", "✕", "aviso"),
        h("div", {}, h("strong", {}, "Repetir la semana. "), "Dos días seguidos en rojo: repite la semana anterior del plan."))
      : null,
    banner(d), tarjetaEstaSemana(d), tarjetaTusCorridas(d), recuperacion(d),
    d.aviso_zonas ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, d.aviso_zonas)) : null,
    enlaceDetalles()].filter(Boolean));
}
function bloqueCarga(s) {
  const a = s.carga.total, b = s.carga_anterior.total;
  let delta = "Sin semana anterior para comparar";
  if (b > 0) {
    const pct = Math.round(((a - b) / b) * 100);
    delta = `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct)} % vs semana anterior (${fmt(b, 0)})`;
  }
  return h("div", { class: "card" }, h("h2", {}, "Carga semanal (RPE × min)"),
    h("div", { class: "grande" }, fmt(a, 0)),
    h("p", { class: "nota" }, delta),
    h("div", { class: "kv" }, h("span", {}, "CrossFit"), h("span", {}, fmt(s.carga.crossfit, 0))),
    h("div", { class: "kv" }, h("span", {}, "Corridas"), h("span", {}, fmt(s.carga.run, 0))),
    s.carga.sin_rpe > 0
      ? h("p", { class: "nota" }, `${s.carga.sin_rpe} ${s.carga.sin_rpe === 1 ? "sesión sin RPE" : "sesiones sin RPE"} (no cuentan en la carga)`)
      : null);
}

function zonaBar(dist) {
  const z = ["Z1", "Z2", "Z3", "Z4", "Z5"];
  const total = z.reduce((a, k) => a + dist.minutos[k], 0);
  const raiz = h("div", { class: "card" });
  raiz.append(h("h2", {}, "Intensidad de la semana", h("span", { class: "etiqueta" }, "referencia")));
  if (total <= 0) {
    raiz.append(h("p", { class: "vacio" }, "Aún no hay minutos en zonas esta semana."));
    return raiz;
  }
  const pct = (k) => (dist.minutos[k] / total) * 100;
  const wrap = h("div", { class: "zbar-wrap" });
  const barra = h("div", { class: "zbar", role: "img", "aria-label": `Bajo ${fmt(dist.bajo, 0)} %, limbo ${fmt(dist.limbo, 0)} %, alto ${fmt(dist.alto, 0)} %` });
  const tip = h("div", { class: "tip", hidden: true, role: "status" });
  const mostrar = (seg, k) => {
    tip.textContent = `${k} · ${fmt(dist.minutos[k])} min · ${fmt(pct(k), 0)} %`;
    tip.hidden = false;
    const r = seg.getBoundingClientRect(), w = wrap.getBoundingClientRect();
    const x = r.left - w.left + r.width / 2;
    tip.style.left = `${Math.min(Math.max(x, 60), w.width - 60)}px`;
  };
  for (const k of z) {
    const seg = h("div", { style: `flex:${Math.max(dist.minutos[k], 0)} 1 0;background:var(--${k.toLowerCase()})`, tabindex: "0",
      "aria-label": `${k}: ${fmt(dist.minutos[k])} minutos, ${fmt(pct(k), 0)} %` });
    if (dist.minutos[k] <= 0) seg.style.display = "none";
    seg.addEventListener("pointerenter", () => mostrar(seg, k));
    seg.addEventListener("pointerdown", () => mostrar(seg, k));
    seg.addEventListener("focus", () => mostrar(seg, k));
    seg.addEventListener("pointerleave", () => (tip.hidden = true));
    seg.addEventListener("blur", () => (tip.hidden = true));
    barra.append(seg);
  }
  const brackets = h("div", { class: "brackets", "aria-hidden": "true" },
    [["Z1", "Z2"], ["Z3"], ["Z4", "Z5"]].map((g) => {
      const m = g.reduce((a, k) => a + dist.minutos[k], 0);
      return h("div", { style: `flex:${m} 1 0;${m <= 0 ? "display:none" : ""}` });
    }));
  const meta = h("div", { class: "meta80", "aria-hidden": "true" }, h("span", {}, "meta 80 %"));
  wrap.append(tip, barra, brackets, meta);
  raiz.append(wrap);

  const grupo = (zs, nombre, valor, meta) => h("div", { class: "grupo" },
    h("span", { class: "sw", "aria-hidden": "true" }, zs.map((k) => h("i", { style: `background:var(--${k.toLowerCase()})` }))),
    h("strong", {}, `${nombre} ${zs.length > 1 ? `${zs[0]}–${zs[1]}` : zs[0]}`),
    h("span", {}, `${fmt(valor, 0)} %`), meta ? h("span", { class: "nota" }, meta) : null);
  raiz.append(h("div", { class: "grupos" },
    grupo(["Z1", "Z2"], "Bajo", dist.bajo, "· meta 80 %"),
    grupo(["Z3"], "Limbo", dist.limbo, "· lo menos posible"),
    grupo(["Z4", "Z5"], "Alto", dist.alto, "· 20 %")));
  raiz.append(h("p", { class: "nota", style: "margin-top:10px" }, "Incluye CrossFit y corridas. Solo referencia: no cambia el plan. El tiempo bajo Z1 (Z0) es descanso y no cuenta."));
  raiz.append(h("details", {}, h("summary", {}, "Ver como tabla"),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Zona"), h("th", {}, "Min"), h("th", {}, "%"))),
      h("tbody", {}, z.map((k) => h("tr", {}, h("td", {}, k), h("td", {}, fmt(dist.minutos[k])), h("td", {}, fmt(pct(k), 0))))))));
  return raiz;
}

