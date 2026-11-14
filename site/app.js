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
  verde: { clase: "ok", icono: "✓", titulo: "Verde", texto: "Recuperado: sesión normal" },
  amarillo: { clase: "warn", icono: "!", titulo: "Amarillo", texto: "Precaución: versión suave" },
  rojo: { clase: "bad", icono: "✕", titulo: "Rojo", texto: "Alerta: descanso o caminata ligera" },
  sin_datos: { clase: "nd", icono: "—", titulo: "Sin datos", texto: "No hay datos de anoche: decide por cómo te sientes" },
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

function semaforoCard(d) {
  const sem = d.hoy.semaforo, est = ESTADO_SEMAFORO[sem.color] || ESTADO_SEMAFORO.sin_datos;
  const nota = sem.color === "sin_datos" ? "Sin HRV, FC en reposo ni sueño de anoche" : sem.fuera === 0 ? "Ninguna señal fuera de rango"
    : `${sem.fuera} señal${sem.fuera === 1 ? "" : "es"} fuera de rango`;
  return h("div", { class: `semaforo ${sem.color}`, role: "group", "aria-label": `Semáforo ${est.titulo}` },
    h("div", { class: "cab" },
      badge(est.clase, est.icono, est.titulo),
      h("div", {}, h("div", { class: "titulo" }, est.titulo), h("div", {}, est.texto), h("div", { class: "nota" }, nota))),
    h("ul", { class: "senales" }, (d.hoy["señales"] || []).map((s) =>
      h("li", {}, badgeSenal(s.estado),
        h("div", {}, h("div", { class: "nombre" }, NOMBRE_SENAL[s.id] || s.id), h("div", { class: "nota" }, s.texto))))));
}

function cuerpoSesion(t, plan) {
  const s = t.sesion;
  const aviso = t.aviso ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, t.aviso)) : null;
  if (t.version === "descanso") {
    return [h("h3", {}, "Hoy: descanso o caminata ligera"), aviso,
      h("p", { class: "nota" }, `La sesión ${s ? s.name : ""} queda pendiente. Si la señal mejora, repónla otro día libre de esta semana.`)];
  }
  if (!s) return [h("h3", {}, t.texto), aviso];
  const suave = t.version === "suave";
  const ses = suave ? s.easy : s;
  return [h("h3", {}, `Sesión ${s.name} · ${ses.minutes} min${suave ? " (versión suave)" : ""}`), aviso,
    h("ul", { class: "pasos" }, ses.steps.map(pasoLi))];
}

function tarjetaHoy(d) {
  const t = d.hoy.tarjeta, plan = d.plan || {};
  const c = h("div", { class: "card" }, h("h2", {}, "Sesión de hoy"));
  const poner = (...xs) => c.append(...xs.filter(Boolean));
  const aviso = t.aviso && t.tipo !== "sesion" ? h("p", { class: "nota" }, t.aviso) : null;
  if (t.tipo === "crossfit") {
    poner(h("h3", {}, "Hoy es CrossFit"), h("p", { class: "nota" }, "Las corridas van en días sin CrossFit."), aviso);
  } else if (t.tipo === "hecha_hoy") {
    poner(h("h3", {}, "Corrida de hoy hecha"), h("p", { class: "nota" }, "Buen trabajo. Descansa el resto del día."), aviso);
  } else if (t.tipo === "sin_plan") {
    poner(h("h3", {}, plan.inicio && (d.generado || "").slice(0, 10) < plan.inicio ? `El plan arranca el ${fechaCorta(plan.inicio)}` : "Hoy no hay semana de plan activa"),
      h("p", { class: "nota" }, "Mientras tanto, el semáforo ya muestra cómo amaneciste."), aviso);
  } else if (t.tipo === "completa") {
    poner(h("h3", {}, "Semana completa"), h("p", { class: "nota" }, "Ya hiciste las corridas de la semana. Descansa."), aviso);
  } else if (t.tipo === "sesion") {
    c.append(...cuerpoSesion(t, plan).filter(Boolean));
  } else {
    c.append(h("p", {}, t.texto));
  }
  return c;
}

// --- Última corrida: ¿lo hice bien? ---

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

function tarjetaUltima(d) {
  const u = d.ultima_corrida;
  const c = h("div", { class: "card" }, h("h2", {}, "Última corrida · ¿lo hice bien?"));
  if (!u) { c.append(h("p", { class: "vacio" }, "Aún no hay corridas registradas.")); return c; }
  const s = u.sesion;
  const ses = s ? `${s.name}${s.version === "suave" ? " (suave)" : ""} · plan ${s.minutes_plan}'` : "sin sesión del plan";
  const techo = u.techo_ok
    ? h("p", { class: "estado" }, badge("ok", "✓", "dentro del techo"), `${fmt(u.min_sobre_techo)}' sobre el techo (tolerancia ${fmt(u.tolerancia_min, 0)}')`)
    : h("p", { class: "estado" }, badge("warn", "!", "sobre el techo"), `${fmt(u.min_sobre_techo)}' sobre el techo (tolerancia ${fmt(u.tolerancia_min, 0)}')`);
  c.append(h("div", { class: "nota" }, `${fechaCorta(u.fecha)} · ${ses}`),
    h("div", { class: "grande" }, `${fmt(u.minutos, 0)} min · ${fmt(u.km)} km`), techo, ...detalleTrote(u));
  return c;
}

// --- Semana y plan de la semana ---

function estadoSesion(est) {
  if (!est) return null;
  if (est.estado === "pendiente") return h("span", { class: "estado" }, badge("nd", "—", "pendiente"), "Pendiente");
  if (est.estado === "incompleta") return h("span", { class: "estado" }, badge("warn", "!", "incompleta"), "Incompleta");
  if (est.ajustada) return h("span", { class: "estado" }, badge("warn", "!", "hecha y ajustada"), "Hecha · ajustada");
  return h("span", { class: "estado" }, badge("ok", "✓", "hecha"), "Hecha");
}

const GARMIN_COMO = "Entrenamientos → Crear entrenamiento → Correr. Agrega un paso por línea (los grupos “N× ( … )” van como repetición). En cada paso elige duración en minutos y, como objetivo, “Alerta de FC” con el rango de lpm de arriba.";

/** Fila compacta de una sesión: nombre, minutos y estado; al abrirla, pasos, versión suave y cómo crearla en Garmin. */
function filaSesion(s, est) {
  return h("details", { class: "ses" },
    h("summary", {}, h("span", { class: "n" }, s.name), h("span", { class: "m" }, `${s.minutes} min`), estadoSesion(est)),
    h("ul", { class: "pasos" }, (s.steps || []).map(pasoLi)),
    s.easy ? h("details", {}, h("summary", {}, `Versión suave (${s.easy.minutes} min)`),
      h("ul", { class: "pasos" }, (s.easy.steps || []).map(pasoLi))) : null,
    h("details", {}, h("summary", {}, "Cómo crearla en Garmin Connect"), h("p", { class: "nota", style: "margin-top:6px" }, GARMIN_COMO)));
}

const NOMBRE_TIPO = { crossfit: "CrossFit", corrida: "Corrida", descanso: "Libre", hoy: "Hoy", futuro: "—" };
const GLIFO_TIPO = { crossfit: "◆", corrida: "●", descanso: "○", hoy: "▸", futuro: "·" };
const LUZ_BADGE = { verde: ["ok", "✓"], amarillo: ["warn", "!"], rojo: ["bad", "✕"], sin_datos: ["nd", "—"] };

function tira(dias, hoyIso) {
  return h("div", { class: "tira" }, dias.map((x) => {
    const luz = x.luz ? LUZ_BADGE[x.luz] : null;
    return h("div", { class: `dia ${x.tipo === "hoy" || x.fecha === hoyIso ? "hoy" : ""} ${x.tipo === "futuro" ? "futuro" : ""}` },
      h("span", { class: "d" }, x.dia_semana),
      h("span", { class: "g", "aria-hidden": "true" }, GLIFO_TIPO[x.tipo]),
      h("span", {}, NOMBRE_TIPO[x.tipo]),
      luz ? badge(luz[0], luz[1], `semáforo ${x.luz}`) : h("span", { class: "badge nd", "aria-hidden": "true", style: "visibility:hidden" }, "·"));
  }));
}

function tarjetaSemana(d) {
  const s = d.semana;
  const hoyIso = (s.dias.find((x) => x.tipo === "hoy") || {}).fecha;
  const partes = [];
  partes.push(s.sesiones_total > 0 ? `${s.hechas} de ${s.sesiones_total} corridas` : "Sin plan activo");
  partes.push(`${fmt(s.km)} km`, `${fmt(s.min_trote, 0)}' trotando`);
  if (s.incompletas > 0) partes.push(`${s.incompletas} ${s.incompletas === 1 ? "incompleta" : "incompletas"}`);
  return h("div", { class: "card" }, h("h2", {}, "Esta semana"), tira(s.dias, hoyIso),
    h("p", { class: "resumen-sem" }, partes.join(" · ")),
    h("p", { class: "nota" }, "Ícono bajo cada día: semáforo de ese día."));
}

function tarjetaPlanSemana(d) {
  const plan = d.plan || {};
  const semanas = plan.semanas || [];
  const w = semanas.find((x) => x.n === plan.semana_actual);
  const c = h("div", { class: "card" }, h("h2", {}, "Plan de la semana"));
  if (!w) {
    const antes = plan.inicio && (d.generado || "").slice(0, 10) < plan.inicio;
    c.append(h("p", {}, antes ? `El plan arranca el ${fechaCorta(plan.inicio)}` : "No hay una semana del plan activa."));
    return c;
  }
  c.append(h("h3", {}, `Semana ${w.n} de ${semanas.length} · bloque ${w.block} · ${w.kind}`), h("p", { class: "nota" }, w.focus || ""),
    ...(w.sessions || []).map((s) => filaSesion(s, (plan.estado_sesiones || []).find((e) => e.id === s.id))));
  return c;
}

const enlaceDetalles = () => h("a", { class: "enlace-detalles", href: "#detalles" }, "Detalles: zonas, reglas, intensidad y carga →");

function renderHoy(d) {
  $("vista-hoy").replaceChildren(...[
    semaforoCard(d),
    d.hoy.semaforo.repetir_semana
      ? h("div", { class: "aviso bad" }, badge("bad", "✕", "aviso"),
        h("div", {}, h("strong", {}, "Repetir la semana. "), "Dos días seguidos en rojo: repite la semana anterior del plan."))
      : null,
    d.aviso_zonas ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, d.aviso_zonas)) : null,
    tarjetaHoy(d), tarjetaUltima(d), tarjetaSemana(d), tarjetaPlanSemana(d), enlaceDetalles()].filter(Boolean));
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

