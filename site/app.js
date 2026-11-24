// Dashboard: solo pinta lo que recibe de data.json (la lógica vive en dashboard/build.py).
const VISTAS = ["hoy", "plan", "progreso"];   // Progreso tiene dos subvistas: Corridas (#progreso) y Cuerpo (#progreso/cuerpo)
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const DIAS_LARGO = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
let datos = null;
// Lo que cada vista vuelve a dibujar cuando ya tiene ancho (gráficas) o cambia el tamaño; lo llena su render.
const PINTAR = { hoy: [], plan: [], progreso: [], cuerpo: [] };   // `cuerpo` = subvista Cuerpo de Progreso

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

const NOMBRE_SENAL = { hrv: "HRV de anoche", rhr: "FC en reposo", sueno: "Sueño" };
const ui = () => (datos && datos.ui) || { categorias: [], textos: {} };
const categoria = (id) => ui().categorias.find((c) => c.id === id) || { id, nombre: id, letra: id.slice(0, 2).toUpperCase(), clase: "azul" };
const nombreSenal = (id) => NOMBRE_SENAL[id] || id;

/** "Esfuerzo 8.7 · RPE 7" (el RPE solo si existe). */
const textoEsfuerzo = (x) => [x.esfuerzo != null ? `Esfuerzo ${fmt(x.esfuerzo, 1)}` : null, x.rpe != null ? `RPE ${fmt(x.rpe, 0)}` : null].filter(Boolean).join(" · ");
const ETIQUETA_PASO = { warmup: "calentamiento", run: "trote", walk: "caminata", cooldown: "enfriamiento" };

function pasoLi(p) {
  if (p.kind === "repeat") {
    return h("li", {}, h("span", { class: "min" }, `${p.times}× (`), h("ul", {}, p.steps.map(pasoLi)), h("span", { class: "min" }, ")"));
  }
  const z = p.zone;
  // Mismos colores que la silueta de la sesión (zonas de Garmin); cada paso trae una sola zona.
  const color = z.startsWith("Z") ? `var(--g${z.slice(1, 2)})` : "var(--axis)";
  const nota = p.note && !(p.optional && p.note === "opcional") && p.note !== ETIQUETA_PASO[p.kind] ? ` · ${p.note}` : "";
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

/** Sesión de calidad: estructura legible y zona objetivo con sus lpm. */
function bloqueCalidad(s) {
  if (!s || !s.objetivo) return null;
  const o = s.objetivo;
  return h("div", { class: "calidad" }, h("p", { class: "estructura" }, s.estructura),
    h("p", { class: "nota" }, `Zona objetivo: ${o.zona}${o.lpm ? ` (${o.lpm[0]}–${o.lpm[1]} lpm)` : ""} · ${o.minutos} min de trabajo`));
}

/** Título y silueta a color de la sesión; los minutos y la zona de cada tramo van escritos arriba (sin leyenda). */
function bloqueSilueta(ses) {
  if (!ses || !ses.silueta || !ses.silueta.length) return null;
  return h("div", { class: "bloque-sil" }, ses.titulo ? h("p", { class: "titulo-sil" }, ses.titulo) : null,
    siluetaSesion(ses.silueta, 40, true, ses.rachas, ses), leyendaRachas(ses.rachas));
}

/** Leyenda de una silueta compacta (más de una zona: arriba solo van los minutos): color, zona y sus lpm. */
function leyendaRachas(rachas) {
  if (!rachas || rachas.length <= 1) return null;
  const lpm = {};
  for (const r of rachas) lpm[r.zona] = lpm[r.zona] || r.lpm;
  return h("div", { class: "leyenda ley-sil" }, Object.keys(lpm).sort().map((z) =>
    h("span", {}, h("i", { class: `g${z.slice(1)}`, "aria-hidden": "true" }), h("b", {}, z),
      lpm[z] ? h("small", {}, `${lpm[z][0]}–${lpm[z][1]}`) : null)));
}

/** Lo que la silueta no dice. Sesión sencilla (hasta 3 rachas, sin repeticiones): solo las notas de sus pasos
 *  ("Trote: arranca suave…"). Si no, la lista de pasos dentro de un "Ver pasos" cerrado. */
function detallePasos(ses) {
  const pasos = ses.steps || [];
  if ((ses.rachas || []).length <= 3 && !pasos.some((p) => p.kind === "repeat")) {
    const notas = pasos.filter((p) => p.note && p.note !== "opcional" && p.note !== ETIQUETA_PASO[p.kind]).map((p) => {
      const tipo = ETIQUETA_PASO[p.kind] || p.kind;
      return h("p", { class: "nota nota-paso" }, `${tipo[0].toUpperCase()}${tipo.slice(1)}${p.optional ? " (opcional)" : ""}: ${p.note}`);
    });
    return notas.length ? h("div", {}, ...notas) : null;
  }
  return h("details", {}, h("summary", {}, "Ver pasos"), h("ul", { class: "pasos" }, pasos.map(pasoLi)));
}

/** Cuerpo desplegable de una sesión del plan (la silueta ya se ve en la fila): pasos y versión suave. */
function cuerpoPlan(s) {
  return [bloqueCalidad(s), s.nota ? h("p", { class: "nota" }, s.nota) : null, detallePasos(s), versionSuave(s)];
}

function versionSuave(s) {
  return s.easy ? h("details", {}, h("summary", {}, `Versión suave (${s.easy.minutes} min)`),
    bloqueSilueta(s.easy), detallePasos(s.easy)) : null;
}

/** Silueta a color dentro de la fila cerrada (sin globito: tocarla abre la fila). */
const silFila = (s) => (s && s.silueta && s.silueta.length
  ? h("div", { class: "sil-fila" }, s.titulo ? h("p", { class: "titulo-sil" }, s.titulo) : null, siluetaSesion(s.silueta, 36, false, s.rachas, s), leyendaRachas(s.rachas)) : null);

/** Fila compacta de una sesión: nombre, minutos, estado y su silueta; al abrirla, pasos y versión suave. */
function filaSesion(s, est) {
  return h("details", { class: "ses" },
    h("summary", {}, h("span", { class: "n" }, s.name), h("span", { class: "m" }, `${s.minutes} min`), estadoSesion(est), silFila(s)),
    ...cuerpoPlan(s));
}

const nombreSesion = (estado, id) => ((estado || []).find((e) => e.id === id) || {}).name;

function textoBanner(d) {
  const t = d.hoy.tarjeta, plan = d.plan || {}, est = plan.estado_sesiones || [];
  const prox = nombreSesion(est, t.proxima_id);
  if (t.tipo === "otra") return prox ? `Hoy: ${t.categoria} ✓ · próxima corrida: ${prox}` : `Hoy: ${t.categoria} ✓`;
  if (t.tipo === "sesion") { const sig = nombreSesion(est, t.sesion_id); return sig ? `Próxima corrida: ${sig}` : null; }
  if (t.tipo === "hecha_hoy") return prox ? `Corrida de hoy hecha · próxima: ${prox}` : "Corrida de hoy hecha";
  if (t.tipo === "sin_plan" || t.tipo === "primera_sync") return t.texto;
  if (t.tipo === "completa") return "Semana completa: hiciste las 3";
  return null;
}

/** Banner de la sesión de hoy con el semáforo como chip: «Recuperación: verde · ver señales» abre las señales. */
function bannerHoy(d) {
  const sem = d.hoy.semaforo, est = ESTADO_SEMAFORO[sem.color] || ESTADO_SEMAFORO.sin_datos;
  const texto = textoBanner(d);
  return h("div", { class: "banner ancha" },
    texto ? h("p", { class: "banner-txt" }, texto) : null,
    h("details", { class: "recup" },
      h("summary", { class: "chip-recup" }, badge(est.clase, est.icono, est.titulo),
        `Recuperación: ${sem.color === "sin_datos" ? "sin datos" : est.titulo.toLowerCase()}`, h("span", { class: "nota" }, " · ver señales")),
      h("ul", { class: "senales" }, (d.hoy["señales"] || []).map((x) =>
        h("li", {}, badgeSenal(x.estado),
          h("div", {}, h("div", { class: "nombre" }, nombreSenal(x.id)), h("div", { class: "nota" }, x.texto))))),
      d.hoy.ayer ? h("p", { class: "nota ayer" }, `Ayer: ${d.hoy.ayer.categoria}${d.hoy.ayer.esfuerzo != null ? `, esfuerzo ${fmt(d.hoy.ayer.esfuerzo, 1)}` : ""}`) : null));
}

// --- semanas navegables: selector, esta semana, calendario ---

let semIdx = null;           // índice en d.semanas_hoy de la semana elegida
let semInicial = 0;          // desplazamiento pedido por #hoy?sem=+1 (solo se lee al arrancar)

function leerSemanaInicial() {
  const m = location.hash.match(/[?&]sem=([+-]?\d+)/);
  semInicial = m ? parseInt(m[1], 10) : 0;
  if (/[?&]carrera\b/.test(location.hash)) abrirCarrera = true;   // para capturas: #progreso?carrera abre la carrera más nueva
}

const semanasHoy = (d) => d.semanas_hoy || [];

function rangoSemana(s) {
  const a = parseFecha(s.inicio), b = parseFecha(s.fin);
  return a.getMonth() === b.getMonth()
    ? `${a.getDate()}–${b.getDate()} ${MESES[b.getMonth()]}`
    : `${a.getDate()} ${MESES[a.getMonth()]}–${b.getDate()} ${MESES[b.getMonth()]}`;
}

function etiquetaSelector(d, s) {
  const total = ((d.plan || {}).semanas || []).length;
  return s.n !== null && s.n !== undefined
    ? `Semana ${s.n}${total ? ` de ${total}` : ""} · ${rangoSemana(s)}${s.kind ? ` · ${s.kind}` : ""}`
    : `Semana del ${rangoSemana(s)}`;
}

function selectorSemana(d) {
  const sems = semanasHoy(d), s = sems[semIdx];
  const mover = (delta) => () => { semIdx = Math.min(Math.max(semIdx + delta, 0), sems.length - 1); pintarSemana(d); };
  const hoyIdx = d.semana_hoy_idx ?? 0;
  return h("div", { class: "selector ancha" },
    h("div", { class: "selector-fila" },
      h("button", { type: "button", "aria-label": "Semana anterior", disabled: semIdx <= 0, onclick: mover(-1) }, "‹"),
      h("div", { class: "selector-txt", "aria-live": "polite" }, etiquetaSelector(d, s)),
      h("button", { type: "button", "aria-label": "Semana siguiente", disabled: semIdx >= sems.length - 1, onclick: mover(1) }, "›")),
    semIdx !== hoyIdx
      ? h("button", { type: "button", class: "volver-sem", onclick: () => { semIdx = hoyIdx; pintarSemana(d); } }, "Volver a esta semana")
      : null);
}

const plural = (n, uno, varios) => `${n} ${n === 1 ? uno : varios}`;

function tituloSemana(d, s) {
  if (s.estado === "actual") return "Esta semana";
  return s.estado === "pasada" && semIdx === (d.semana_hoy_idx ?? 0) - 1 ? "Semana pasada" : "Esa semana";
}

function comparacion(s) {
  const a = s.anterior, st = s.stats;
  if (!a || s.estado === "futura") return null;
  const previa = s.estado === "actual" ? "Semana pasada" : "Semana anterior";
  if (!a.minutos && !a.km) return `${previa} sin corridas`;
  const total = `${previa}: ${fmt(a.minutos, 0)} min · ${fmt(a.km)} km`;
  // Solo se compara cuando esta semana ya la superó; a media semana una flecha ▼ asusta sin razón.
  if ((st.minutos || 0) < a.minutos) return total;
  const dm = Math.round(st.minutos - a.minutos), dk = Math.round(((st.km || 0) - a.km) * 10) / 10;
  return `${total} · ya la superaste: ${flecha(dm, `${Math.abs(dm)} min`)} · ${flecha(dk, `${fmt(Math.abs(dk))} km`)}`;
}

const flecha = (delta, texto) => `${delta > 0 ? "▲" : delta < 0 ? "▼" : "="} ${texto}`;

/** Barra de progreso: minutos hechos / minutos del plan; el relleno se corta en 100 %. */
function barraProgreso(min, plan) {
  const pct = Math.round((min / plan) * 100);
  return h("div", {},
    h("div", { class: "prog fina", role: "progressbar", "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": Math.min(pct, 100),
      "aria-label": `${fmt(min, 0)} de ${fmt(plan, 0)} minutos` }, h("div", { style: `width:${Math.min(pct, 100)}%` })),
    h("p", { class: "prog-txt" }, `${fmt(min, 0)} / ${fmt(plan, 0)} min · ${pct} %`));
}

function tarjetaEstaSemana(d, s) {
  const st = s.stats || {};
  const c = h("div", { class: "card ancha" }, h("h2", {}, tituloSemana(d, s)));
  const partes = st.corridas
    ? [plural(st.corridas, "corrida", "corridas"), st.minutos != null ? `${fmt(st.minutos, 0)} min` : null,
      st.km != null ? `${fmt(st.km)} km` : null, st.pct_trote != null ? `${fmt(st.pct_trote, 0)} % trote` : null].filter(Boolean)
    : [s.estado === "futura" ? "Aún no empieza" : "Sin corridas"];
  c.append(h("div", { class: "grande" }, partes.join(" · ")), ...[intensidadCompacta(s)].filter(Boolean));
  const p = s.plan;
  if (p) {
    if (s.estado === "futura") c.append(h("p", { class: "nota" }, `Plan: ${p.total} sesiones · ${fmt(p.plan_min, 0)} min`));
    else {
      c.append(h("p", { class: "nota", style: "margin-top:8px" },
        `Plan: ${p.hechas} de ${p.total} sesiones${p.incompletas ? ` · ${plural(p.incompletas, "incompleta", "incompletas")}` : ""}`),
        barraProgreso(st.minutos || 0, p.plan_min));
    }
  }
  const comp = comparacion(s);
  if (comp) c.append(h("p", { class: "nota" }, comp));
  c.append(calendarioSemana(d, s));
  return c;
}

const diaTexto = (x) => {
  const partes = [];
  if (x.corrida) partes.push(`${x.corrida.carrera ? "carrera" : "corrida"} de ${fmt(x.corrida.minutos, 0)} min (${x.corrida.sesion_nombre}, ${{ hecha: "hecha", incompleta: "incompleta", extra: "sin sesión" }[x.corrida.estado] || x.corrida.estado})`);
  if (x.corridas_n > 1) partes.push(`${x.corridas_n} corridas ese día`);
  for (const cf of x.otras || []) {
    partes.push(`${categoria(cf.cat).nombre}${cf.minutos ? ` ${fmt(cf.minutos, 0)} min` : ""}${cf.esfuerzo != null ? `, esfuerzo ${fmt(cf.esfuerzo, 1)}` : ""}${cf.rpe != null ? `, RPE ${fmt(cf.rpe, 0)}` : ""}`);
  }
  return `${fechaCorta(x.fecha)}: ${partes.length ? partes.join("; ") : "sin actividad"}`;
};

function diaCalendario(x, hoyIso) {
  const varias = ui().categorias.length > 1;   // con una sola categoría no hace falta distinguir por color
  const marcaCat = (cat, cfTxt) => {
    const c = categoria(cat);
    return h("span", { class: `cf${varias ? ` cat ${c.clase}` : ""}`, title: c.nombre }, h("b", {}, icono(c.icono, 18)), cfTxt ? h("span", {}, cfTxt) : null);
  };
  let marca = null;
  if (x.corrida) {
    const cls = x.corrida.estado === "hecha" ? "hecha" : x.corrida.estado === "incompleta" ? "incompleta" : "extra";
    marca = [h("span", { class: `circ ${cls}${x.corrida.carrera ? " carrera" : ""}`, "aria-hidden": "true" }, fmt(x.corrida.minutos, 0)),
      h("span", { class: "sn" }, icono(x.corrida.icono || (x.corrida.carrera ? "medalla" : "correr"), 14), h("span", {}, x.corrida.sesion_nombre + (x.corridas_n > 1 ? ` +${x.corridas_n - 1}` : ""))),
      x.corrida.carrera ? h("span", { class: "sn-carrera" }, "carrera") : null];
  }
  const cfMarca = (x.otras || []).map((cf) => marcaCat(cf.cat, cf.esfuerzo != null ? fmt(cf.esfuerzo, 1) : null));
  return h("div", { class: `dia${x.fecha === hoyIso ? " es-hoy" : ""}`, role: "group", title: diaTexto(x), "aria-label": diaTexto(x) },
    h("span", { class: "dn" }, x.dia_semana), h("span", { class: "df" }, parseFecha(x.fecha).getDate()),
    marca, cfMarca);
}

function calendarioSemana(d, s) {
  const hoyIso = (d.generado || "").slice(0, 10);
  return h("div", { class: "cal" },
    h("div", { class: "dias7" }, (s.dias || []).map((x) => diaCalendario(x, hoyIso))),
    h("p", { class: "nota leyenda-cal" }, "número = esfuerzo calculado con tu FC (1–10)"));
}

/** "Minutos en Z4: 17 de 20 ✓" y aviso si pasó mucho tiempo por encima de la zona. */
function lineaCalidad(q) {
  const txt = `Minutos en ${q.zona}: ${fmt(q.min_zona, 0)} de ${fmt(q.objetivo_min, 0)}`;
  return h("div", {},
    q.ok ? h("p", { class: "estado" }, badge("ok", "✓", "objetivo cumplido"), `${txt} ✓`)
      : h("p", { class: "estado" }, badge("warn", "!", "por debajo del objetivo"), txt),
    q.mucho_arriba ? h("p", { class: "nota" }, `Pasaste ${fmt(q.min_arriba, 0)}' por encima de ${q.zona}: la próxima baja un poco el ritmo.`) : null);
}

function lineaTecho(c) {
  const txt = `${fmt(c.min_sobre_techo)}' sobre el techo (tolerancia ${fmt(c.tolerancia_min, 0)}')`;
  return c.techo_ok
    ? h("p", { class: "estado" }, badge("ok", "✓", "dentro del techo"), txt)
    : h("p", { class: "estado" }, badge("warn", "!", "sobre el techo"), txt);
}

/** Fila de una corrida hecha: cabecera (estado + título), datos, techo y detalle de trote/caminata. */
function filaCorrida(cabeza, titulo, c) {
  c = c || {};
  const datos = [c.minutos != null ? `${fmt(c.minutos, 0)}'` : null, c.km != null ? `${fmt(c.km)} km` : null,
    c.pct_trote != null ? `${fmt(c.pct_trote, 0)} % trote` : null,
    c.ritmo_trote_s ? `${mmss(c.ritmo_trote_s)} /km${c.caminadora ? " (caminadora)" : ""}` : null, textoEsfuerzo(c) || null].filter(Boolean);
  return h("div", { class: "corrida" },
    h("div", { class: "cab-c" }, cabeza, h("span", { class: "n" }, titulo), c.carrera ? h("span", { class: "etiqueta-carrera" }, "Carrera") : null),
    datos.length ? h("p", { class: "datos" }, datos.join(" · ")) : null,
    c.calidad ? lineaCalidad(c.calidad) : c.techo_ok !== undefined ? lineaTecho(c) : null,
    h("details", {}, h("summary", {}, "Ver detalle"),
      ...detalleTrote({ trote: c.trote_min != null ? c : null, caminadora: c.caminadora })));
}

const filaHecha = (e) => filaCorrida(estadoSesion(e), `${e.name} · ${e.fecha ? fechaCorta(e.fecha) : ""}`, e.corrida);

function filaExtra(x) {
  return filaCorrida(h("span", { class: "estado" }, badge("nd", "+", "extra")), `Extra · ${fechaCorta(x.fecha)}`, x);
}

function filaNoHecha(e, s) {
  return h("div", { class: "corrida no-hecha" },
    h("div", { class: "cab-c" }, h("span", { class: "estado" }, badge("nd", "✗", "no hecha"), "No hecha"),
      h("span", { class: "n" }, `${e.name}${s ? ` · ${s.minutes} min` : ""}`)));
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
    c.append(...[bloqueSilueta(ses), bloqueCalidad(ses), detallePasos(ses), suave ? null : versionSuave(s)].filter(Boolean));
  }
  if (t.aviso) c.append(h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, t.aviso)));
  return c;
}

function filaPendiente(e, s) {
  const larga = e.tipo === "larga";
  return h("details", { class: "ses corrida" },
    h("summary", {}, h("span", { class: "n" }, e.name),
      h("span", { class: "m" }, `${s ? `${s.minutes} min` : ""}${larga ? `${s ? " · " : ""}sáb o dom` : ""}`), silFila(s)),
    ...(s ? cuerpoPlan(s) : []));
}

function tarjetaTusCorridas(d, s, ancha) {
  const plan = d.plan || {}, t = d.hoy.tarjeta;
  const w = s.n != null ? (plan.semanas || []).find((x) => x.n === s.n) : null;
  const filas = (s.sesiones || []).map((e) => {
    const ses = w ? (w.sessions || []).find((x) => x.id === e.id) : null;
    if (e.estado === "hecha" || e.estado === "incompleta") return filaHecha(e);
    if (e.estado === "no_hecha") return filaNoHecha(e, ses);
    if (s.estado === "actual" && t.tipo === "sesion" && t.sesion_id === e.id) return filaHoy(e, t.sesion || ses, t);
    return filaPendiente(e, ses);
  });
  filas.push(...(s.extras || []).map(filaExtra));
  return h("div", { class: `card${ancha ? " ancha" : ""}` }, h("h2", {}, "Tus corridas"),
    ...(filas.length ? filas : [h("p", { class: "vacio" }, "Sin corridas esta semana")]));
}

// --- cómo vas mejorando ---

const MEJ = {};
const mesAnio = (iso) => { const f = parseFecha(iso); return `${f.getDate()} ${MESES[f.getMonth()]} ${f.getFullYear()}`; };

/** Cambio respecto a la medición anterior: ▼/▲ con 1 decimal; verde si es bueno, tinta neutra si no (sin rojo). */
function deltaInbody(delta, buenoSiBaja) {
  if (delta === null || delta === undefined) return null;
  if (delta === 0) return h("span", { class: "delta" }, "= 0.0");
  const bueno = buenoSiBaja ? delta < 0 : delta > 0;
  return h("span", { class: `delta${bueno ? " bien" : ""}` }, `${delta > 0 ? "▲" : "▼"}${Math.abs(delta).toFixed(1)}`);
}

/** Leyenda con los íconos de entreno que aparecen arriba de las barras (`semanas[].entrenos`), detrás de `base`. */
function leyendaIconos(semanas, base) {
  const vistos = new Map();
  for (const e of semanas.flatMap((s) => s.entrenos || [])) vistos.set(e.icono, e.nombre);
  const ley = leyenda(base);
  ley.append(...[...vistos].map(([ic, nombre]) => h("span", {}, icono(ic, 14), nombre)));
  return ley;
}

function tarjetaMejora(d) {
  const mj = (d.progreso || {}).mejora;
  if (!mj) return null;
  const hayMin = (mj.semanas || []).some((s) => (s.minutos || 0) > 0);
  const ritmo = mj.modo === "ritmo";
  const hayPct = ritmo ? (mj.ritmo || []).length > 0 : (mj.corridas || []).some((c) => c.pct_trote != null);
  MEJ.min = h("div", { class: "chart-wrap" });
  MEJ.pct = h("div", { class: "chart-wrap" });
  const graficas = hayMin || hayPct
    ? h("div", { class: "mini2" },
      h("div", {}, h("h3", {}, "Minutos por semana"), MEJ.min, leyenda([["raya", "Plan"]])),
      h("div", {}, h("h3", {}, ritmo ? "Ritmo en Z2" : "% trote por corrida"), MEJ.pct))
    : null;
  PINTAR.progreso.push(dibujarMejora);
  return h("div", { class: "card ancha" }, h("h2", {}, "Cómo vas mejorando"),
    h("p", { class: "frase-mej" }, mj.frase), graficas);
}

/** " · 2× Corrida · 1× CrossFit" a partir de los entrenos de la semana (para el globito y lectores de pantalla). */
const textoEntrenos = (entrenos) => (entrenos || []).map((e) => ` · ${e.n}× ${e.nombre}`).join("");

function dibujarMejora() {
  if (!MEJ.min || !datos) return;
  const mj = (datos.progreso || {}).mejora;
  if (!mj) return;
  const dibujar = (cont, fn) => { const w = cont.clientWidth; if (w) cont.replaceChildren(fn(w)); };
  const semanas = mj.semanas || [];
  const ult = semanas[semanas.length - 1];
  dibujar(MEJ.min, (ancho) => barChart({
    ancho, alto: 100, clases: ["s1"], etiqueta: "Minutos por semana, últimas 8 semanas, con raya del plan",
    semanas: semanas.map((s) => ({ inicio: s.inicio, valores: [s.minutos || 0], meta: s.plan_min || 0, s })),
    etiquetaFinal: ult ? `${fmt(ult.minutos, 0)}'` : null,
    texto: (b) => `Semana del ${fechaLarga(b.inicio)} · ${fmt(b.s.minutos, 0)}'${b.s.plan_min ? ` (plan ${b.s.plan_min}')` : ""}`,
  }));
  if (mj.modo === "ritmo") {
    const rp = (mj.ritmo || []).map((c) => ({ fecha: c.fecha, y: c.ritmo_s }));
    dibujar(MEJ.pct, (ancho) => rp.length
      ? lineChart({ ancho, alto: 100, serie: rp, marcadores: true, invertir: true, fmtY: mmss, etiqueta: "Ritmo en Z2 por corrida, arriba es más rápido",
        etiquetaFinal: `${mmss(rp[rp.length - 1].y)}/km`, texto: (p) => `${fechaLarga(p.fecha)} · ${mmss(p.y)} /km en Z2` })
      : h("p", { class: "vacio" }, "Aún no hay corridas en Z2."));
    return;
  }
  const pts = (mj.corridas || []).filter((c) => c.pct_trote != null).map((c) => ({ fecha: c.fecha, y: c.pct_trote }));
  dibujar(MEJ.pct, (ancho) => pts.length
    ? lineChart({ ancho, alto: 100, serie: pts, marcadores: true, fmtY: (v) => fmt(v, 0), etiqueta: "Porcentaje del tiempo trotando por corrida",
      etiquetaFinal: `${fmt(pts[pts.length - 1].y, 0)} %`, texto: (p) => `${fechaLarga(p.fecha)} · ${fmt(p.y, 0)} % trotando` })
    : h("p", { class: "vacio" }, "Aún no hay corridas con trote y caminata."));
}

function pintarSemana(d) {
  const sems = semanasHoy(d), s = sems[semIdx];
  const caja = $("hoy-semana");
  if (!s) { caja.replaceChildren(); return; }
  const reciente = carreraReciente(d);
  caja.replaceChildren(...[selectorSemana(d), tarjetaEstaSemana(d, s), tarjetaTusCorridas(d, s, !reciente), reciente ? tarjetaCarreraHoy(reciente) : null].filter(Boolean));
}

// --- carrera destacada (últimos 7 días) ---

const carreraReciente = (d) => ((d.carreras || [])[0] || {}).reciente ? d.carreras[0] : null;
let abrirCarrera = false;   // «Ver en Progreso › Carreras» pide abrir y mostrar la carrera más nueva

/** hh:mm:ss si pasa de una hora, si no mm:ss. */
const tiempoLargo = (seg) => {
  const t = Math.round(seg), hh = Math.floor(t / 3600);
  return hh ? `${hh}:${String(Math.floor((t % 3600) / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}` : mmss(t);
};

function tarjetaCarreraHoy(c) {
  const num = (valor, etiqueta) => h("div", { class: "num4" }, h("div", { class: "num4-v" }, valor), h("div", { class: "nota" }, etiqueta));
  return h("div", { class: "card carrera-hoy" }, h("h2", { class: "con-ico" }, icono(c.icono || "medalla", 18), `Tu carrera del ${fechaLarga(c.fecha)}`),
    h("div", { class: "nums4" },
      num(`${fmt(c.distancia_km, 2)} km`, "Distancia"), num(tiempoLargo(c.tiempo_s), "Tiempo"),
      num(c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : "—", "Ritmo"), num(c.fc_prom != null ? `${fmt(c.fc_prom, 0)} lpm` : "—", "FC promedio")),
    h("a", { class: "ver-progreso", href: "#progreso", onclick: () => { abrirCarrera = true; } }, "Ver todo en Progreso › Carreras"));
}

function renderHoy(d) {
  PINTAR.hoy = [];
  const sems = semanasHoy(d);
  if (semIdx === null) semIdx = Math.min(Math.max((d.semana_hoy_idx ?? 0) + semInicial, 0), Math.max(sems.length - 1, 0));
  $("vista-hoy").replaceChildren(...[
    d.hoy.semaforo.repetir_semana
      ? h("div", { class: "aviso bad ancha" }, badge("bad", "✕", "aviso"),
        h("div", {}, h("strong", {}, "Repetir la semana. "), "Dos días seguidos en rojo: repite la semana anterior del plan."))
      : null,
    bannerHoy(d), h("div", { id: "hoy-semana" }),
    d.aviso_zonas ? h("div", { class: "aviso warn ancha" }, badge("warn", "!", "aviso"), h("div", {}, d.aviso_zonas)) : null].filter(Boolean));
  pintarSemana(d);
}
function bloqueCarga(s) {
  const a = s.carga.total, b = s.carga_anterior.total;
  let delta = "Sin semana anterior para comparar";
  if (b > 0) {
    const pct = Math.round(((a - b) / b) * 100);
    delta = `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct)} % vs semana anterior (${fmt(b, 0)})`;
  }
  return h("div", { class: "card" }, h("h2", {}, "Carga semanal (esfuerzo × min)"),
    h("div", { class: "grande" }, fmt(a, 0)),
    h("p", { class: "nota" }, delta),
    ...ui().categorias.map((c) => h("div", { class: "kv" }, h("span", {}, c.nombre), h("span", {}, fmt(s.carga[c.id], 0)))),
    h("div", { class: "kv" }, h("span", {}, "Corridas"), h("span", {}, fmt(s.carga.run, 0))));
}

/** Barra de minutos por zona (Z1–Z5) con la marca de 80 %. Compacta: más delgada, sin brackets ni textos de la marca. */
/** Barra de minutos por zona. `compacta`: delgada y sin corchetes. `etiquetas`: zona y % dentro de cada tramo (en
 *  pantalla chica solo el %, y abajo una leyenda); cada tramo esconde lo que no le cabe (container queries en styles.css). */
function barraZonas(dist, compacta = false, etiquetas = false) {
  const z = ["Z1", "Z2", "Z3", "Z4", "Z5"];
  const total = z.reduce((a, k) => a + dist.minutos[k], 0);
  if (total <= 0) return null;
  const pct = (k) => (dist.minutos[k] / total) * 100;
  const wrap = h("div", { class: `zbar-wrap${compacta ? " compacta" : ""}${etiquetas ? " con-etiquetas" : ""}` });
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
    const p = pct(k);
    if (etiquetas) seg.append(h("span", { class: "zb-t", "aria-hidden": "true" }, h("span", { class: "zb-z" }, k), h("span", {}, `${fmt(p, 0)} %`)));
    seg.addEventListener("pointerenter", () => mostrar(seg, k));
    seg.addEventListener("pointerdown", () => mostrar(seg, k));
    seg.addEventListener("focus", () => mostrar(seg, k));
    seg.addEventListener("pointerleave", () => (tip.hidden = true));
    seg.addEventListener("blur", () => (tip.hidden = true));
    barra.append(seg);
  }
  wrap.append(tip, barra);
  if (!compacta) {
    wrap.append(h("div", { class: "brackets", "aria-hidden": "true" },
      [["Z1", "Z2"], ["Z3"], ["Z4", "Z5"]].map((g) => {
        const m = g.reduce((a, k) => a + dist.minutos[k], 0);
        return h("div", { style: `flex:${m} 1 0;${m <= 0 ? "display:none" : ""}` });
      })));
  }
  wrap.append(h("div", { class: "meta80", "aria-hidden": "true" }, compacta ? null : h("span", {}, "meta 80 %")));
  if (etiquetas) {
    wrap.append(h("div", { class: "leyenda zb-ley" }, z.filter((k) => dist.minutos[k] > 0).map((k) =>
      h("span", {}, h("i", { class: "sw", style: `background:var(--${k.toLowerCase()})`, "aria-hidden": "true" }), k))));
  }
  return wrap;
}

/** 80/20 de una semana de Hoy, como la de Plan › Intensidad: zona y % dentro de la barra y "Bajo 72 % · meta 80 %".
 *  Sin minutos en zonas, no se pinta. */
function intensidadCompacta(s) {
  const dist = s.intensidad;
  if (!dist || !dist.minutos) return null;
  const barra = barraZonas(dist, false, true);
  if (!barra) return null;
  return h("div", { class: "int-sem" }, barra, h("p", { class: "nota" }, `Bajo ${fmt(dist.bajo, 0)} % · meta 80 %`));
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
  raiz.append(barraZonas(dist));

  const grupo = (zs, nombre, valor, meta) => h("div", { class: "grupo" },
    h("span", { class: "sw", "aria-hidden": "true" }, zs.map((k) => h("i", { style: `background:var(--${k.toLowerCase()})` }))),
    h("strong", {}, `${nombre} ${zs.length > 1 ? `${zs[0]}–${zs[1]}` : zs[0]}`),
    h("span", {}, `${fmt(valor, 0)} %`), meta ? h("span", { class: "nota" }, meta) : null);
  raiz.append(h("div", { class: "grupos" },
    grupo(["Z1", "Z2"], "Bajo", dist.bajo, "· meta 80 %"),
    grupo(["Z3"], "Limbo", dist.limbo, "· lo menos posible"),
    grupo(["Z4", "Z5"], "Alto", dist.alto, "· 20 %")));
  raiz.append(h("p", { class: "nota", style: "margin-top:10px" }, `${ui().textos.incluye || "Incluye tus actividades y corridas."} Solo referencia: no cambia el plan. El tiempo bajo Z1 (Z0) es descanso y no cuenta.`));
  raiz.append(h("details", {}, h("summary", {}, "Ver como tabla"),
    h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "Zona"), h("th", {}, "Min"), h("th", {}, "%"))),
      h("tbody", {}, z.map((k) => h("tr", {}, h("td", {}, k), h("td", {}, fmt(dist.minutos[k])), h("td", {}, fmt(pct(k), 0))))))));
  return raiz;
}

