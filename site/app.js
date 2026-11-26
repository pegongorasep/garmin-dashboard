// Dashboard: solo pinta lo que recibe de data.json (la lógica vive en dashboard/build.py).
const VISTAS = ["hoy", "plan", "progreso", "ayuda"];   // Progreso tiene dos subvistas: Corridas (#progreso) y Cuerpo (#progreso/cuerpo)
let datos = null;
// Lo que cada vista vuelve a dibujar cuando ya tiene ancho (gráficas) o cambia el tamaño; lo llena su render.
const PINTAR = { hoy: [], plan: [], progreso: [], cuerpo: [] };   // `cuerpo` = subvista Cuerpo de Progreso

// --- utilidades (h, fmt, parseFecha y MESES viven en base.js) ---

function fechaCorta(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()]} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function haceCuanto(iso) {
  if (!iso) return null;
  const t = Date.parse(iso.replace(/T(\d\d:\d\d)([+-]\d\d:\d\d)$/, "T$1:00$2"));
  if (Number.isNaN(t)) return null;
  const min = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (min < 1) return T("sitio.hace_momento");
  if (min < 60) return T("sitio.hace_min", { n: min });
  if (min < 1440) return T("sitio.hace_h", { n: Math.round(min / 60) });
  return T("sitio.hace_d", { n: Math.round(min / 1440) });
}

// --- estado con ícono + texto ---

const SEMAFORO_BASE = { verde: ["ok", "✓"], amarillo: ["warn", "!"], rojo: ["bad", "✕"], sin_datos: ["nd", "—"] };
const estadoSemaforo = (id) => {
  const b = SEMAFORO_BASE[id];
  return b && { clase: b[0], icono: b[1], titulo: T(`sitio.semaforo.${id}`), texto: T(`sitio.semaforo.${id}_t`) };
};

const badge = (clase, simbolo, etiqueta) => DS.insignia(clase, simbolo, etiqueta);

const estadoSenal = (estado) => (estado === "ok" ? { clase: "ok", simbolo: "✓" } : estado === "fuera" ? { clase: "warn", simbolo: "!" } : { clase: "nd", simbolo: "—" });

// --- vista Hoy ---

const ui = () => (datos && datos.ui) || { categorias: [], textos: {} };
const categoria = (id) => ui().categorias.find((c) => c.id === id) || { id, nombre: id, letra: id.slice(0, 2).toUpperCase(), clase: "azul" };
const nombreSenal = (id) => (["hrv", "rhr", "sueno"].includes(id) ? T(`sitio.senal.${id}`) : id);

/** "Esfuerzo 8.7 · RPE 7" (el RPE solo si existe). */
const textoEsfuerzo = (x) => [x.esfuerzo != null ? T("sitio.esfuerzo", { v: fmt(x.esfuerzo, 1) }) : null, x.rpe != null ? T("sitio.rpe", { v: fmt(x.rpe, 0) }) : null].filter(Boolean).join(" · ");
const etiquetaPaso = (k) => (["warmup", "run", "walk", "cooldown"].includes(k) ? T(`sitio.paso.${k}`) : k);

function pasoLi(p) {
  if (p.kind === "repeat") {
    return h("li", {}, h("span", { class: "min" }, `${p.times}× (`), h("ul", {}, p.steps.map(pasoLi)), h("span", { class: "min" }, ")"));
  }
  const z = p.zone;
  // Mismos colores que la silueta de la sesión (zonas de Garmin); cada paso trae una sola zona.
  const color = z.startsWith("Z") ? `var(--g${z.slice(1, 2)})` : "var(--axis)";
  const nota = p.note && !(p.optional && p.nota_id === "opcional") && p.note !== etiquetaPaso(p.kind) ? ` · ${p.note}` : "";
  return h("li", {},
    h("span", { class: "min" }, `${p.minutes} min`),
    h("span", { class: "zchip" }, h("i", { style: `background:${color}`, "aria-hidden": "true" }), z),
    p.lpm ? h("span", { class: "lpm" }, `${p.lpm[0]}–${p.lpm[1]} ${T("sitio.lpm")}`) : null,
    h("span", { class: "nota" }, etiquetaPaso(p.kind), p.optional ? ` ${T("sitio.paso.opcional")}` : "", nota));
}

const mmss = (seg) => {
  if (seg === null || seg === undefined) return "—";
  const t = Math.round(seg);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
};

function barraRW(tr) {
  const total = tr.trote_min + tr.camina_min;
  return total <= 0 ? null : DS.barraTroteCaminata({ trote: Math.round(tr.trote_min), caminata: Math.round(tr.camina_min) });
}

function detalleTrote(u) {
  const tr = u.trote;
  if (!tr) return [h("p", { class: "nota" }, T("sitio.sin_tramos"))];
  const patron = tr.caminatas > 0
    ? T("sitio.patron", { c: T(tr.caminatas === 1 ? "sitio.caminata_1" : "sitio.caminata_n", { n: tr.caminatas }), a: mmss((tr.patron_trote_min || 0) * 60), b: mmss((tr.patron_camina_min || 0) * 60) })
    : T("sitio.sin_caminatas");
  const ritmo = tr.ritmo_trote_s
    ? (tr.fc_trote ? T("sitio.ritmo_trotando_fc", { r: mmss(tr.ritmo_trote_s), fc: fmt(tr.fc_trote, 0) }) : T("sitio.ritmo_trotando", { r: mmss(tr.ritmo_trote_s) })) + (u.caminadora ? ` · ${T("sitio.caminadora")}` : "")
    : null;
  return [barraRW(tr), h("p", { class: "nota" }, patron), ritmo ? h("p", {}, ritmo) : null].filter(Boolean);
}

// --- Sesiones del plan ---

/** Estado de una sesión del plan como {clase, simbolo, texto, etiqueta} para DS.filaSesion. */
function estadoSesion(est) {
  if (!est) return null;
  if (est.estado === "pendiente") return { clase: "nd", simbolo: "—", texto: T("sitio.ses.pendiente"), etiqueta: T("sitio.ses.pendiente_e") };
  if (est.estado === "incompleta") return { clase: "warn", simbolo: "!", texto: T("sitio.ses.incompleta"), etiqueta: T("sitio.ses.incompleta_e") };
  if (est.ajustada) return { clase: "warn", simbolo: "!", texto: T("sitio.ses.ajustada"), etiqueta: T("sitio.ses.ajustada_e") };
  return { clase: "ok", simbolo: "✓", texto: T("sitio.ses.hecha"), etiqueta: T("sitio.ses.hecha_e") };
}

/** Sesión de calidad: estructura legible y zona objetivo con sus lpm. */
function bloqueCalidad(s) {
  if (!s || !s.objetivo) return null;
  const o = s.objetivo;
  return h("div", { class: "calidad" }, h("p", { class: "b-t" }, s.estructura),
    h("p", { class: "nota" }, T("sitio.zona_objetivo", { z: o.zona, lpm: o.lpm ? ` (${o.lpm[0]}–${o.lpm[1]} ${T("sitio.lpm")})` : "", min: o.minutos })));
}

/** Título y silueta a color de la sesión; los minutos y la zona de cada tramo van escritos arriba (sin leyenda). */
function bloqueSilueta(ses) {
  if (!ses || !ses.silueta || !ses.silueta.length) return null;
  return h("div", { class: "bloque-sil" }, ses.titulo ? h("p", { class: "titulo-sil" }, ses.titulo) : null,
    DS.silueta(ses.silueta, { alto: 40, conTip: true, rachas: ses.rachas, con_calentamiento: ses.con_calentamiento, con_enfriamiento: ses.con_enfriamiento }), leyendaRachas(ses.rachas));
}

/** Leyenda de una silueta compacta (más de una zona: arriba solo van los minutos): color, zona y sus lpm. */
function leyendaRachas(rachas) {
  if (!rachas || rachas.length <= 1) return null;
  const lpm = {};
  for (const r of rachas) lpm[r.zona] = lpm[r.zona] || r.lpm;
  return DS.leyenda(Object.keys(lpm).sort().map((z) =>
    [`var(--g${z.slice(1)})`, [h("b", {}, z), lpm[z] ? h("small", {}, ` ${lpm[z][0]}–${lpm[z][1]}`) : null]]));
}

/** Lo que la silueta no dice. Sesión sencilla (hasta 3 rachas, sin repeticiones): solo las notas de sus pasos
 *  ("Trote: arranca suave…"). Si no, la lista de pasos dentro de un "Ver pasos" cerrado. */
function detallePasos(ses) {
  const pasos = ses.steps || [];
  if ((ses.rachas || []).length <= 3 && !pasos.some((p) => p.kind === "repeat")) {
    const notas = pasos.filter((p) => p.note && p.nota_id !== "opcional" && p.note !== etiquetaPaso(p.kind)).map((p) => {
      const tipo = etiquetaPaso(p.kind);
      return h("p", { class: "nota" }, `${tipo[0].toUpperCase()}${tipo.slice(1)}${p.optional ? ` ${T("sitio.paso.opcional")}` : ""}: ${p.note}`);
    });
    return notas.length ? h("div", { class: "notas-paso" }, ...notas) : null;
  }
  return DS.desplegable({ titulo: T("sitio.ver_pasos"), liga: true }, h("ul", { class: "pasos-ses" }, pasos.map(pasoLi)));
}

/** Cuerpo desplegable de una sesión del plan (la silueta ya se ve en la fila): pasos y versión suave. */
function cuerpoPlan(s) {
  return [bloqueCalidad(s), s.nota ? h("p", { class: "nota" }, s.nota) : null, detallePasos(s), versionSuave(s)].filter(Boolean);
}

function versionSuave(s) {
  return s.easy ? DS.desplegable({ titulo: T("sitio.version_suave", { min: s.easy.minutes }), liga: true }, bloqueSilueta(s.easy), detallePasos(s.easy)) : null;
}

/** Silueta a color dentro de la fila cerrada (sin globito: tocarla abre la fila), con su leyenda si es compacta. */
const silFila = (s) => (s && s.silueta && s.silueta.length
  ? h("span", { class: "sil-fila" }, DS.silueta(s.silueta, { alto: 36, conTip: false, rachas: s.rachas, con_calentamiento: s.con_calentamiento, con_enfriamiento: s.con_enfriamiento }), leyendaRachas(s.rachas)) : null);

/** Fila compacta de una sesión del plan: nombre, minutos, estado y su silueta; al abrirla, pasos y versión suave. */
function filaSesion(s, est, extra = {}) {
  return DS.filaSesion({ nombre: s.name, minutos: s.minutes, estado: estadoSesion(est), silueta: silFila(s), titulo: s.titulo, cuerpo: cuerpoPlan(s), ...extra });
}

const nombreSesion = (estado, id) => ((estado || []).find((e) => e.id === id) || {}).name;

function textoBanner(d) {
  const t = d.hoy.tarjeta, plan = d.plan || {}, est = plan.estado_sesiones || [];
  const prox = nombreSesion(est, t.proxima_id);
  if (t.tipo === "otra") return prox ? T("sitio.banner.otra_prox", { cat: t.categoria, prox }) : T("sitio.banner.otra", { cat: t.categoria });
  if (t.tipo === "sesion") { const sig = nombreSesion(est, t.sesion_id); return sig ? T("sitio.banner.proxima", { sig }) : null; }
  if (t.tipo === "hecha_hoy") return prox ? T("sitio.banner.hecha_prox", { prox }) : T("sitio.banner.hecha");
  if (t.tipo === "sin_plan" || t.tipo === "primera_sync" || t.tipo === "pausa") return t.texto;
  if (t.tipo === "completa") return T("sitio.banner.completa");
  if (t.tipo === "plan_terminado") return null;   // lo dice su propia tarjeta
  return null;
}

/** Banner de la sesión de hoy con el semáforo como chip: «Recuperación: verde · ver señales» abre las señales. */
function bannerHoy(d) {
  const sem = d.hoy.semaforo, est = estadoSemaforo(sem.color) || estadoSemaforo("sin_datos");
  const texto = textoBanner(d);
  const ayer = d.hoy.ayer ? T("sitio.ayer", { cat: d.hoy.ayer.categoria, esf: d.hoy.ayer.esfuerzo != null ? T("sitio.ayer_esfuerzo", { v: fmt(d.hoy.ayer.esfuerzo, 1) }) : "" }) : null;
  return DS.tarjeta({ clase: "ancha banner" },
    texto ? h("p", { class: "b-t" }, texto) : null,
    DS.desplegable({ titulo: [badge(est.clase, est.icono, est.titulo), T("sitio.recuperacion", { estado: sem.color === "sin_datos" ? T("sitio.sin_datos_min") : est.titulo.toLowerCase() }), h("span", { class: "mu" }, T("sitio.ver_senales"))] },
      DS.senales({ senales: (d.hoy["señales"] || []).map((x) => ({ ...estadoSenal(x.estado), nombre: nombreSenal(x.id), texto: x.texto })), nota: ayer })));
}

const nombrePrueba = (tipo) => T(`sitio.prueba.${tipo}`);

/** "7:42 /km", "93 % de trote" o "25:00" según la prueba. */
function valorPrueba(tipo, v) {
  return tipo === "trote_continuo" ? (v >= 95 ? T("sitio.prueba.seguidos", { v: fmt(v, 0) }) : T("sitio.prueba.pct_trote", { v: fmt(v, 0) })) : tipo === "5k" ? tiempoLargo(v) : `${mmss(v)} /km`;
}

/** Tarjeta "Plan terminado": resultado de la prueba contra el inicio (o contra la prueba anterior) y el siguiente paso. */
function tarjetaPlanTerminado(d) {
  const t = d.hoy.tarjeta;
  if (t.tipo !== "plan_terminado") return null;
  const p = t.prueba;
  const c = DS.tarjeta({ titulo: T("sitio.fin.titulo"), clase: "ancha plan-fin" });
  if (!p) c.append(DS.estado("nd", "—", T("sitio.fin.falta"), T("sitio.estado.falta")));
  else {
    c.append(h("p", { class: "big" }, p.valor == null ? T("sitio.fin.sin_resultado", { p: nombrePrueba(p.tipo) }) : valorPrueba(p.tipo, p.valor)),
      h("p", { class: "nota" }, T("sitio.fin.prueba", { p: nombrePrueba(p.tipo), fecha: fechaCorta(p.fecha), km: p.km ? ` · ${fmt(p.km, 2)} km` : "" })));
    if (p.base && p.dif != null) {
      const donde = p.base.fuente === "prueba" ? T("sitio.fin.prueba_del", { fecha: fechaCorta(p.base.fecha) }) : p.base.fuente === "mejor_5k" ? T("sitio.fin.mejor5k", { fecha: fechaCorta(p.base.fecha) }) : T("sitio.fin.inicio");
      const mag = p.tipo === "trote_continuo" ? T("sitio.fin.puntos", { v: fmt(Math.abs(p.dif), 0) }) : p.tipo === "5k" ? tiempoLargo(Math.abs(p.dif)) : T("sitio.fin.spkm", { v: fmt(Math.abs(p.dif), 0) });
      const mejor = T(p.tipo === "trote_continuo" ? "sitio.fin.mas_trote" : "sitio.fin.mas_rapido"), peor = T(p.tipo === "trote_continuo" ? "sitio.fin.menos_trote" : "sitio.fin.mas_lento");
      c.append(p.mejor == null ? DS.estado("nd", "=", T("sitio.fin.igual", { donde, v: valorPrueba(p.tipo, p.base.valor) }), T("sitio.estado.igual"))
        : DS.estado(p.mejor ? "ok" : "warn", p.mejor ? "✓" : "!", T("sitio.fin.comp", { mag, dir: p.mejor ? mejor : peor, donde, v: valorPrueba(p.tipo, p.base.valor) }), T(p.mejor ? "sitio.estado.mejor" : "sitio.estado.peor")));
    } else if (!p.base) c.append(h("p", { class: "nota" }, T("sitio.fin.sin_base")));
  }
  c.append(h("p", {}, t.siguiente || T("sitio.fin.siguiente"),
    t.siguiente_url ? [" · ", h("a", { href: t.siguiente_url }, T("sitio.fin.armar"))] : null));
  return c;
}

/** Resumen de la semana pasada (calculado en Python): una línea y, al tocarla, el resto. */
function resumenSemanaPasada(d) {
  const r = d.hoy.semana_pasada;
  if (!r) return null;
  const sug = r.sugerencia;
  const linea = [r.sesiones_total != null ? T("sitio.sp.sesiones", { a: r.sesiones_hechas, b: r.sesiones_total }) : null,
    r.plan_min != null ? T("sitio.sp.min", { a: fmt(r.minutos, 0), b: fmt(r.plan_min, 0) }) : T("sitio.min_n", { n: fmt(r.minutos, 0) }),
    T("sitio.sp.verdes", { v: r.dias_verdes, sd: r.dias_sin_datos ? T("sitio.sp.sin_datos", { n: r.dias_sin_datos }) : "" })].filter(Boolean);
  const cuando = (a, b) => (a == null || b == null ? null : Math.abs(a - b) < 3 ? T("sitio.sp.igual") : T(a < b ? "sitio.sp.mas_rapido" : "sitio.sp.mas_lento", { v: mmss(b) }));
  const carga = r.carga_anterior ? T("sitio.sp.carga_vs", { c: fmt(r.carga, 0), f: r.carga >= r.carga_anterior ? "▲" : "▼", p: Math.abs(Math.round(((r.carga - r.carga_anterior) / r.carga_anterior) * 100)), a: fmt(r.carga_anterior, 0) }) : T("sitio.sp.carga", { c: fmt(r.carga, 0) });
  const ritmo = r.ritmo_ref_s != null ? T("sitio.sp.ritmo", { fc: (d.progreso || {}).fc_ref, r: mmss(r.ritmo_ref_s), cmp: cuando(r.ritmo_ref_s, r.ritmo_ref_anterior_s) ? `, ${cuando(r.ritmo_ref_s, r.ritmo_ref_anterior_s)}` : "" }) : null;
  const dist = r.intensidad || {};
  return DS.tarjeta({ clase: "ancha banner semana-pasada" }, DS.desplegable({
    titulo: h("span", { class: "sp-titulo" }, h("span", { class: "sp-linea" }, T("sitio.sp.titulo", { l: linea.join(" · ") })),
      sug ? h("span", { class: "estado" }, badge(sug.tipo === "sigue" ? "ok" : "warn", sug.tipo === "sigue" ? "✓" : "!", T("sitio.sugerencia")), sug.texto) : null) },
  h("div", { class: "sp-cuerpo" },
    h("p", {}, T("sitio.km_n", { n: fmt(r.km) }) + (r.pct_trote != null ? T("sitio.sp.trote", { v: fmt(r.pct_trote, 0) }) : "")),
    dist.bajo != null ? h("p", {}, T("sitio.sp.dist", { b: fmt(dist.bajo, 0), l: fmt(dist.limbo, 0), a: fmt(dist.alto, 0) })) : null,
    h("p", {}, carga), ritmo ? h("p", {}, ritmo) : null,
    ...(r.plan_vs_real || []).map((x) => h("div", {}, h("p", { class: "nota" }, x.sesion), lineasPlanVsReal(x.filas))))));
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
    ? (total ? T("sitio.sel.semana_de", { n: s.n, t: total, r: rangoSemana(s) }) : T("sitio.sel.semana", { n: s.n, r: rangoSemana(s) })) + (s.kind ? ` · ${tipoSemana(s.kind)}` : "")
    : T("sitio.sel.del", { r: rangoSemana(s) });
}

function selectorSemana(d) {
  const sems = semanasHoy(d), s = sems[semIdx];
  const mover = (delta) => () => { semIdx = Math.min(Math.max(semIdx + delta, 0), sems.length - 1); pintarSemana(d); };
  const hoyIdx = d.semana_hoy_idx ?? 0;
  return h("div", { class: "selector ancha" },
    DS.selectorSemana({ texto: etiquetaSelector(d, s), sinAnterior: semIdx <= 0, sinSiguiente: semIdx >= sems.length - 1, onAnterior: mover(-1), onSiguiente: mover(1) }),
    semIdx !== hoyIdx ? DS.boton(T("sitio.sel.volver"), { variante: "texto", chico: true, onclick: () => { semIdx = hoyIdx; pintarSemana(d); } }) : null);
}

function tituloSemana(d, s) {
  if (s.estado === "actual") return T("sitio.tit.actual");
  return s.estado === "pasada" && semIdx === (d.semana_hoy_idx ?? 0) - 1 ? T("sitio.tit.pasada") : T("sitio.tit.esa");
}

function comparacion(s) {
  const a = s.anterior, st = s.stats;
  if (!a || s.estado === "futura") return null;
  const previa = T(s.estado === "actual" ? "sitio.cmp.pasada" : "sitio.cmp.anterior");
  if (!a.minutos && !a.km) return T("sitio.cmp.sin", { p: previa });
  const total = T("sitio.cmp.total", { p: previa, m: fmt(a.minutos, 0), k: fmt(a.km) });
  // Solo se compara cuando esta semana ya la superó; a media semana una flecha ▼ asusta sin razón.
  if ((st.minutos || 0) < a.minutos) return total;
  const dm = Math.round(st.minutos - a.minutos), dk = Math.round(((st.km || 0) - a.km) * 10) / 10;
  return T("sitio.cmp.supero", { t: total, a: flecha(dm, T("sitio.min_n", { n: Math.abs(dm) })), b: flecha(dk, T("sitio.km_n", { n: fmt(Math.abs(dk)) })) });
}

const flecha = (delta, texto) => `${delta > 0 ? "▲" : delta < 0 ? "▼" : "="} ${texto}`;

function tarjetaEstaSemana(d, s) {
  const st = s.stats || {};
  const partes = st.corridas
    ? [Tn("sitio.corrida", st.corridas), st.minutos != null ? T("sitio.min_n", { n: fmt(st.minutos, 0) }) : null,
      st.km != null ? T("sitio.km_n", { n: fmt(st.km) }) : null, st.pct_trote != null ? T("sitio.trote_pct", { v: fmt(st.pct_trote, 0) }) : null].filter(Boolean)
    : [T(s.estado === "futura" ? "sitio.aun_no" : "sitio.sin_corridas")];
  const c = DS.tarjeta({ titulo: tituloSemana(d, s), clase: "ancha" }, h("p", { class: "titular" }, partes.join(" · ")), intensidadCompacta(s));
  const p = s.plan;
  if (p) {
    if (s.estado === "futura") c.append(h("p", { class: "nota" }, T("sitio.plan.futura", { t: p.total, m: fmt(p.plan_min, 0) })));
    else {
      const min = st.minutos || 0, pct = Math.round((min / p.plan_min) * 100);
      c.append(DS.anilloPlan({ pct, titulo: `${fmt(min, 0)} / ${fmt(p.plan_min, 0)} min · ${pct} %`,
        texto: T("sitio.plan.hechas", { h: p.hechas, t: p.total, inc: p.incompletas ? ` · ${Tn("sitio.incompleta", p.incompletas)}` : "" }),
        etiqueta: T("sitio.plan.min_de", { a: fmt(min, 0), b: fmt(p.plan_min, 0) }) }));
    }
  }
  const comp = comparacion(s);
  if (comp) c.append(h("p", { class: "nota" }, comp));
  c.append(calendarioSemana(d, s));
  return c;
}

const diaTexto = (x) => {
  const partes = [];
  if (x.corrida) partes.push(T("sitio.dia.de", { k: T(x.corrida.carrera ? "sitio.dia.carrera" : "sitio.dia.corrida"), m: fmt(x.corrida.minutos, 0), s: x.corrida.sesion_nombre, e: ["hecha", "incompleta", "extra"].includes(x.corrida.estado) ? T(`sitio.dia.${x.corrida.estado}`) : x.corrida.estado }));
  if (x.planeado && !x.corrida) partes.push(T("sitio.dia.planeada"));
  if (x.corridas_n > 1) partes.push(T("sitio.dia.corridas", { n: x.corridas_n }));
  for (const cf of x.otras || []) {
    partes.push(`${categoria(cf.cat).nombre}${cf.minutos ? ` ${T("sitio.min_n", { n: fmt(cf.minutos, 0) })}` : ""}${cf.esfuerzo != null ? T("sitio.dia.esfuerzo", { v: fmt(cf.esfuerzo, 1) }) : ""}${cf.rpe != null ? T("sitio.dia.rpe", { v: fmt(cf.rpe, 0) }) : ""}`);
  }
  return `${fechaCorta(x.fecha)}: ${partes.length ? partes.join("; ") : T("sitio.dia.sin")}`;
};

function diaCalendario(x, hoyIso, seleccionado, alTocar) {
  const varias = ui().categorias.length > 1;   // con una sola categoría no hace falta distinguir por color
  const marcaCat = (cat, cfTxt) => {
    const c = categoria(cat);
    return h("span", { class: `cf${varias ? ` cat ${c.clase}` : ""}`, title: c.nombre }, DS.ico(c.icono), cfTxt ? h("span", {}, cfTxt) : null);
  };
  let marca = [];
  if (x.corrida) {
    const cls = x.corrida.estado === "hecha" ? "" : x.corrida.estado === "incompleta" ? " incompleta" : " extra";
    marca = [h("span", { class: `circ${cls}${x.corrida.carrera ? " carrera" : ""}`, "aria-hidden": "true" }, parseFecha(x.fecha).getDate()),
      h("span", { class: "sn" }, DS.ico(x.corrida.icono || (x.corrida.carrera ? "medalla" : "correr")), h("span", {}, `${fmt(x.corrida.minutos, 0)}' ${x.corrida.sesion_nombre}` + (x.corridas_n > 1 ? ` +${x.corridas_n - 1}` : ""))),
      x.corrida.carrera ? h("span", { class: "sn-carrera" }, T("sitio.dia.carrera")) : null];
  }
  if (!marca.length && x.planeado) marca = [h("span", { class: "circ planeado", "aria-hidden": "true" }, parseFecha(x.fecha).getDate())];   // corrida planeada, aún sin hacer
  const cfMarca = (x.otras || []).map((cf) => marcaCat(cf.cat, cf.esfuerzo != null ? fmt(cf.esfuerzo, 1) : null));
  return DS.diaCal({ nombre: x.dia_semana, numero: parseFecha(x.fecha).getDate(), hoy: x.fecha === hoyIso, titulo: diaTexto(x), numeroEnMarca: marca.length > 0, hijos: [...marca, ...cfMarca], seleccionado, alTocar });
}

/** El detalle de una actividad (todo viene calculado de Python; lo que falta no se pinta). */
function detalleActividad(dt, a) {
  const tile = (k, valor, unidad) => (valor == null ? null : DS.tile({ k: T(`sitio.act.${k}`), valor, unidad }));
  const ritmo = dt.ritmo_s != null ? tile("ritmo", mmss(dt.ritmo_s), "/km") : tile("vel", dt.vel_kmh != null ? fmt(dt.vel_kmh, 1) : null, "km/h");
  const tiles = [tile("duracion", fmt(dt.duracion_min, 0), T("sitio.sl.min")), tile("dist", dt.km != null ? fmt(dt.km) : null, "km"), ritmo,
    tile("fc", dt.fc_prom != null ? fmt(dt.fc_prom, 0) : null, T("sitio.lpm")), tile("fcmax", dt.fc_max != null ? fmt(dt.fc_max, 0) : null, T("sitio.lpm")),
    tile("kcal", dt.kcal != null ? fmt(dt.kcal, 0) : null, "kcal"), tile("desnivel", dt.desnivel_m != null ? fmt(dt.desnivel_m, 0) : null, "m"),
    tile("cadencia", dt.cadencia != null ? fmt(dt.cadencia, 0) : null, T("sitio.act.ppm"))].filter(Boolean);
  const te = dt.te_aerobico != null || dt.te_anaerobico != null
    ? h("p", {}, T("sitio.act.te", { a: dt.te_aerobico != null ? fmt(dt.te_aerobico, 1) : "—", n: dt.te_anaerobico != null ? fmt(dt.te_anaerobico, 1) : "—" }) + (dt.te_etiqueta ? ` · ${dt.te_etiqueta}` : "")) : null;
  const pulso = dt.pulso ? h("p", { class: "nota" }, T("sitio.act.pulso", { p: T(dt.pulso === "banda" ? "sitio.act.pulso_banda" : "sitio.act.pulso_muneca") })
    + (dt.pulso === "muñeca" && dt.ritmo_s != null ? ` · ${T("sitio.act.sin_deriva")}` : "")) : null;
  return h("div", { class: "act-cuerpo" }, DS.tiles({ etiqueta: a.nombre, clase: "act-tiles" }, ...tiles), pulso,
    dt.zonas ? h("div", {}, h("p", { class: "nota" }, T("sitio.act.zonas")), DS.barraZonas(dt.zonas, { compacta: true, sinMeta: true, leyenda: true })) : null, te,
    dt.ritmos_km ? h("p", { class: "nota" }, `${T("sitio.act.por_km")}: ${dt.ritmos_km.map(mmss).join(" · ")}`) : null,
    dt.curva_fc ? h("div", {}, h("p", { class: "nota" }, T("sitio.act.curva_t")), DS.curvaFc(dt.curva_fc)) : null);
}

/** Una actividad del día: tipo, minutos, km y FC prom.; en corridas, la sesión del plan y si se hizo. Al tocarla se abre su detalle. */
function filaActividad(a) {
  const datos = [T("sitio.min_n", { n: fmt(a.minutos, 0) }), a.km != null ? T("sitio.km_n", { n: fmt(a.km) }) : null,
    a.fc_prom != null ? `${fmt(a.fc_prom, 0)} ${T("sitio.lpm")}` : null].filter(Boolean).join(" · ");
  const ses = a.sesion ? `${a.sesion.nombre} · ${["hecha", "incompleta", "extra", "no_hecha", "pendiente"].includes(a.sesion.estado) ? T(`sitio.dia.${a.sesion.estado}`) : a.sesion.estado}` : null;
  const cabeza = [h("span", { class: "act-t" }, DS.ico(a.icono || "punto"), a.nombre), h("span", {}, datos), ses ? h("span", { class: "nota" }, ses) : null];
  if (!a.detalle) return h("div", { class: "act-fila" }, ...cabeza);
  return DS.desplegable({ titulo: h("span", { class: "act-fila" }, ...cabeza), clase: "act-det" }, detalleActividad(a.detalle, a));
}

/** Texto del día sin actividad: [título, línea]. Los textos vienen de Python (`plan_ses`: nombre de la sesión, "" = descanso, ausente = sin plan). */
function vacioDia(x, hoyIso) {
  const futuro = x.fecha >= hoyIso, ses = x.plan_ses;
  if (ses === undefined || ses === null) return [T("sitio.dia.sin_act"), null];
  if (ses) return futuro ? [T("sitio.dia.toca", { s: ses }), null] : [T("sitio.dia.sin_act"), T("sitio.dia.plan_era", { s: ses })];
  return [T("sitio.dia.vacio_descanso"), futuro ? T("sitio.dia.toca_descanso") : T("sitio.dia.plan_descanso")];
}

/** Tarjeta del día tocado, de alto fijo: cabecera + 2 espacios de fila (`.dia-ranura`). Con 3 o más actividades, la segunda ranura dice
 *  «+N más» y al tocarla se abren todas (crecer ahí es explícito). Sin actividad, un estado que llena las mismas ranuras. */
function tarjetaDia(x, hoyIso) {
  const acts = x.actividades || [];
  const ranura = (...hijos) => h("div", { class: "dia-ranura" }, ...hijos);
  let filas;
  if (!acts.length) {
    const [t, sub] = vacioDia(x, hoyIso);
    filas = [ranura(h("div", { class: "act-fila" }, h("span", { class: "act-t" }, t), sub ? h("span", { class: "nota" }, sub) : null)), ranura()];
  } else if (acts.length <= 2) {
    filas = [...acts.map((a) => ranura(filaActividad(a))), ...(acts.length < 2 ? [ranura()] : [])];
  } else {
    const caja = h("div", { class: "dia-filas" });
    const mas = h("button", { type: "button", class: "dia-mas", onclick: () => caja.replaceChildren(...acts.map((a) => ranura(filaActividad(a)))) },
      T("sitio.dia.mas", { n: acts.length - 1 }));
    caja.append(ranura(filaActividad(acts[0])), ranura(mas));
    return h("div", { class: "dia-det", "aria-live": "polite" }, h("p", { class: "prog-t" }, fechaCorta(x.fecha)), caja);
  }
  return h("div", { class: "dia-det", "aria-live": "polite" }, h("p", { class: "prog-t" }, fechaCorta(x.fecha)), h("div", { class: "dia-filas" }, ...filas));
}

/** Calendario de 7 días tocables + la tarjeta del día elegido (hoy; en otra semana, el último con actividad). `mk(x, sel, alTocar)` pinta cada día. */
function calendarioTocable(dias, hoyIso, mk) {
  if (!dias.length) return [];
  const inicial = dias.find((x) => x.fecha === hoyIso) || [...dias].reverse().find((x) => (x.actividades || []).length) || dias[0];
  const det = h("div", {}), botones = [];
  const elegir = (x) => {
    for (const [b, f] of botones) { b.classList.toggle("dia-sel", f === x.fecha); b.setAttribute("aria-pressed", String(f === x.fecha)); }
    det.replaceChildren(tarjetaDia(x, hoyIso));
  };
  const cal = DS.calendario(dias.map((x) => { const b = mk(x, x.fecha === inicial.fecha, () => elegir(x)); botones.push([b, x.fecha]); return b; }));
  elegir(inicial);
  return [cal, det];
}

function calendarioSemana(d, s) {
  const hoyIso = (d.generado || "").slice(0, 10);
  return h("div", { class: "cal-caja" }, ...calendarioTocable(s.dias || [], hoyIso, (x, sel, tocar) => diaCalendario(x, hoyIso, sel, tocar)),
    h("p", { class: "nota" }, T("sitio.cal.nota")));
}

/** Plan vs real por zona: "Z3 o más · 2 de 4 min · 50 %" con ✓/⚠; con una sola zona planeada, "Z2 · 19 de 20 min ✓". */
function lineasPlanVsReal(filas) {
  if (!filas || !filas.length) return null;
  const solo = filas.length === 1;
  return h("div", { class: "pvr" }, filas.map((f) => {
    const nombre = solo ? f.zona : f.zona === "Z5" ? "Z5" : T("sitio.pvr.o_mas", { z: f.zona });
    const v = { n: nombre, h: fmt(f.hecho_min, 0), p: fmt(f.plan_min, 0), pct: f.pct };
    const txt = T(solo ? "sitio.pvr.fila" : "sitio.pvr.fila_pct", v);
    return f.ok ? DS.estado("ok", "✓", `${txt} ✓`, T("sitio.pvr.cumplido")) : DS.estado("warn", "!", `${txt} ⚠`, T("sitio.pvr.debajo"));
  }), filas[0].mucho_arriba
    ? DS.estado("warn", "!", T("sitio.pvr.arriba", { m: fmt(filas[0].arriba_min, 0), z: filas[0].zona }), T("sitio.pvr.muy_arriba"))
    : null);
}

function lineaTecho(c) {
  const txt = T("sitio.techo.txt", { m: fmt(c.min_sobre_techo), t: fmt(c.tolerancia_min, 0) });
  return c.techo_ok ? DS.estado("ok", "✓", txt, T("sitio.techo.ok")) : DS.estado("warn", "!", txt, T("sitio.techo.no"));
}

function lineaDeriva(c) {
  const txt = T("sitio.deriva.txt", { v: fmt(c.deriva_pct, 1) });
  return c.deriva_ok ? DS.estado("ok", "✓", `${txt} ✓`, T("sitio.deriva.baja")) : DS.estado("warn", "!", T("sitio.deriva.buena", { t: txt }), T("sitio.deriva.alta"));
}

/** Fila de una corrida hecha o extra: estado + título, y al abrirla (ya viene abierta) datos, techo y detalle de trote/caminata. */
function filaCorrida(estado, titulo, c, extra = {}) {
  c = c || {};
  const datos = [c.minutos != null ? `${fmt(c.minutos, 0)}'` : null, c.km != null ? T("sitio.km_n", { n: fmt(c.km) }) : null,
    c.pct_trote != null ? T("sitio.trote_pct", { v: fmt(c.pct_trote, 0) }) : null,
    c.ritmo_trote_s ? `${mmss(c.ritmo_trote_s)} /km${c.caminadora ? ` (${T("sitio.caminadora")})` : ""}` : null, textoEsfuerzo(c) || null].filter(Boolean);
  return DS.filaSesion({ nombre: titulo, estado, ...extra, cuerpo: [
    c.carrera ? DS.chip(T("sitio.carrera_chip"), "neutro") : null,
    datos.length ? h("p", {}, datos.join(" · ")) : null,
    c.plan_vs_real ? lineasPlanVsReal(c.plan_vs_real) : null,
    c.techo_ok !== undefined ? lineaTecho(c) : null,
    c.deriva_pct != null ? lineaDeriva(c) : null,
    DS.desplegable({ titulo: T("sitio.ver_detalle"), liga: true }, ...detalleTrote({ trote: c.trote_min != null ? c : null, caminadora: c.caminadora }),
      c.ritmo_ref_s ? h("p", {}, T("sitio.ritmo_fc", { fc: (datos.progreso || {}).fc_ref, r: mmss(c.ritmo_ref_s) })) : null)].filter(Boolean) });
}

const filaHecha = (e) => filaCorrida(estadoSesion(e), `${e.name} · ${e.fecha ? fechaCorta(e.fecha) : ""}`, e.corrida);

function filaExtra(x) {
  return filaCorrida({ clase: "nd", simbolo: "+", texto: T("sitio.extra"), etiqueta: T("sitio.extra_e") }, T("sitio.extra_f", { f: fechaCorta(x.fecha) }), x);
}

function filaNoHecha(e, s) {
  return DS.filaSesion({ nombre: e.name, sub: s ? T("sitio.min_n", { n: s.minutes }) : null, estado: { clase: "nd", simbolo: "✗", texto: T("sitio.nohecha"), etiqueta: T("sitio.nohecha_e") } });
}

/** Hoy con selector de versión (normal / suave / descanso). Solo pinta: Python manda `opciones` y `recomendada`.
 *  Todas las versiones viven en la misma celda (alto fijo); elegir solo cambia cuál se ve. No se guarda la elección. */
function filaHoyElegir(e, s, t, abierta) {
  const rec = t.recomendada, ops = t.opciones;
  const sesDe = (v) => (v === "suave" ? s.easy : s);
  const cuerpoDe = (v) => (v === "descanso" ? [h("p", {}, T("sitio.descanso"))]
    : [bloqueSilueta(sesDe(v)), bloqueCalidad(sesDe(v)), detallePasos(sesDe(v))].filter(Boolean));
  const nombreDe = (v) => T(`sitio.hoy.n_${v}`, { n: e.name });
  const minDe = (v) => (v === "descanso" ? "" : `· ${T("sitio.min_n", { n: sesDe(v).minutes })}`);
  const textoPor = (v) => {
    if (v !== rec) return T("sitio.hoy.elegiste", { e: T(`sitio.hoy.l_${v}`), r: T(`sitio.hoy.l_${rec}`) });
    if (rec === "normal") return T("sitio.hoy.rec_normal");
    return t.motivo ? T(`sitio.hoy.rec_${rec}_m`, { m: t.motivo }) : T(`sitio.hoy.rec_${rec}`);
  };
  const nom = h("span", {}, nombreDe(rec)), mi = h("small", {}, minDe(rec));
  const por = h("p", { class: "nota hoy-por" }, textoPor(rec));   // ranura reservada de 2 líneas: elegir no cambia el alto
  // Todas las versiones en la misma celda: el alto es el de la más alta y no cambia al elegir; solo se ve la activa.
  const vers = Object.fromEntries(ops.map((v) => [v, h("div", { class: "hoy-ver", "aria-hidden": String(v !== rec) }, ...cuerpoDe(v))]));
  const mostrar = (v) => { for (const [k, el] of Object.entries(vers)) { el.classList.toggle("oculta", k !== v); el.setAttribute("aria-hidden", String(k !== v)); } };
  mostrar(rec);
  const cont = h("div", { class: "hoy-vers" }, ...Object.values(vers));
  const seg = DS.segmento({ etiqueta: T("sitio.hoy.aria"), modo: "botones", activo: rec,
    opciones: ops.map((v) => ({ id: v, texto: v === "descanso" ? T("sitio.hoy.v_descanso") : T(`sitio.hoy.v_${v}`, { min: sesDe(v).minutes }) })),
    onCambio: (v) => { nom.textContent = nombreDe(v); mi.textContent = minDe(v); por.textContent = textoPor(v); mostrar(v); } });
  const cuerpo = [seg, por, cont];
  if (t.aviso) cuerpo.push(DS.aviso({ clase: "warn", simbolo: "!", texto: t.aviso }));
  return DS.filaSesion({ nombre: h("span", {}, nom, " ", mi), hoy: true, abierta,
    estado: { clase: "nd", simbolo: "—", texto: T("sitio.ses.pendiente"), etiqueta: T("sitio.ses.pendiente_e") }, cuerpo });
}

function filaHoy(e, s, t, abierta) {
  if (s && s.easy && Array.isArray(t.opciones) && t.opciones.length && t.opciones.includes(t.recomendada)) return filaHoyElegir(e, s, t, abierta);
  const suave = t.version === "suave";
  const ses = s && suave ? s.easy : s;
  const cuerpo = [];
  if (t.motivo) cuerpo.push(h("p", { class: "nota" }, T("sitio.por", { m: t.motivo })));
  if (t.version === "descanso") cuerpo.push(h("p", {}, T("sitio.descanso")));
  else if (ses) cuerpo.push(...[bloqueSilueta(ses), bloqueCalidad(ses), detallePasos(ses), suave ? null : versionSuave(s)].filter(Boolean));
  if (t.aviso) cuerpo.push(DS.aviso({ clase: "warn", simbolo: "!", texto: t.aviso }));
  return DS.filaSesion({ nombre: t.version === "descanso" ? e.name : `${e.name}${suave ? T("sitio.suave_par") : ""}`, minutos: t.version === "descanso" || !ses ? null : ses.minutes,
    hoy: true, abierta, estado: { clase: "nd", simbolo: "—", texto: T("sitio.ses.pendiente"), etiqueta: T("sitio.ses.pendiente_e") }, cuerpo });
}

function filaPendiente(e, s, abierta) {
  const larga = e.tipo === "larga";
  return DS.filaSesion({ nombre: e.name, sub: `${s ? T("sitio.min_n", { n: s.minutes }) : ""}${larga ? `${s ? " · " : ""}${T("sitio.sab_dom")}` : ""}` || null, abierta,
    estado: { clase: "nd", simbolo: "—", texto: T("sitio.ses.pendiente"), etiqueta: T("sitio.ses.pendiente_e") },
    cuerpo: s ? [bloqueSilueta(s), ...cuerpoPlan(s)].filter(Boolean) : [] });
}

function tarjetaTusCorridas(d, s, ancha) {
  const plan = d.plan || {}, t = d.hoy.tarjeta;
  const w = s.n != null ? (plan.semanas || []).find((x) => x.n === s.n) : null;
  const esHoy = (e) => s.estado === "actual" && t.tipo === "sesion" && t.sesion_id === e.id && e.estado !== "hecha" && e.estado !== "incompleta" && e.estado !== "no_hecha";
  const pend = (e) => e.estado !== "hecha" && e.estado !== "incompleta" && e.estado !== "no_hecha";
  // Solo se abre la que sigue: la de hoy si está pendiente; si no, la primera pendiente. Si no hay, todas cerradas.
  const sig = (s.sesiones || []).find(esHoy) || (s.sesiones || []).find(pend);
  const filas = (s.sesiones || []).map((e) => {
    const ses = w ? (w.sessions || []).find((x) => x.id === e.id) : null;
    if (e.estado === "hecha" || e.estado === "incompleta") return filaHecha(e);
    if (e.estado === "no_hecha") return filaNoHecha(e, ses);
    if (s.estado === "actual" && t.tipo === "sesion" && t.sesion_id === e.id) return filaHoy(e, t.sesion || ses, t, e === sig);
    return filaPendiente(e, ses, e === sig);
  });
  filas.push(...(s.extras || []).map(filaExtra));
  return DS.tarjeta({ titulo: T("sitio.tus_corridas"), clase: `filas${ancha ? " ancha" : ""}` },
    ...(filas.length ? filas : [DS.estadoVacio({ icono: null, titulo: T("sitio.sin_corridas_sem") })]));
}

// --- cómo vas mejorando ---

const mesAnio = (iso) => { const f = parseFecha(iso); return `${f.getDate()} ${MESES[f.getMonth()]} ${f.getFullYear()}`; };

/** Cambio respecto a la medición anterior: ▼/▲ con 1 decimal; verde si es bueno, tinta neutra si no (sin rojo). */
function deltaInbody(delta, buenoSiBaja) {
  if (delta === null || delta === undefined) return null;
  if (delta === 0) return h("span", { class: "delta neutro" }, "= 0.0");
  const bueno = buenoSiBaja ? delta < 0 : delta > 0;
  return h("span", { class: `delta${bueno ? "" : " neutro"}` }, `${delta > 0 ? "▲" : "▼"}${Math.abs(delta).toFixed(1)}`);
}

/** Leyenda con los íconos de entreno que aparecen arriba de las barras (`semanas[].entrenos`), detrás de `base`. */
function leyendaIconos(semanas, base) {
  const vistos = new Map();
  for (const e of semanas.flatMap((s) => s.entrenos || [])) vistos.set(e.icono, e.nombre);
  const ley = DS.leyenda(base);
  ley.append(...[...vistos].map(([ic, nombre]) => h("span", {}, DS.ico(ic), nombre)));
  return ley;
}

/** Tarjeta "Cómo vas mejorando": cuadritos con lo ya calculado en Python (ritmo a FC ref, deriva y, si hay, la prueba).
 *  Verde = mejora, ámbar = empeora; siempre con flecha y texto. */
function tarjetaMejora(d) {
  const mj = (d.progreso || {}).mejora;
  if (!mj || !mj.ritmo) return null;
  const clase = (v) => (v == null ? "neutro" : v ? "" : "mal");   // "" = verde (mejora); "mal" = ámbar; "neutro" = tinta
  const cuadro = (titulo, valor, sub, bueno, extra) => DS.tile({ k: titulo, valor: valor ?? "—", deltas: [[sub, clase(bueno)], ...(extra ? [[extra, "neutro"]] : [])] });
  const r = mj.ritmo, v = mj.deriva, p = mj.prueba;
  const cuadros = [cuadro(T("sitio.mej.ritmo", { fc: r.fc_ref }), r.valor,
    r.valor == null ? r.motivo : r.cambio ? `${r.cambio}${r.mejora == null ? "" : T(r.mejora ? "sitio.mej.mejor" : "sitio.mej.lento")}` : r.motivo,
    r.mejora, r.valor != null && r.cambio ? r.motivo : null)];
  cuadros.push(cuadro(T("sitio.mej.deriva"), v.valor,
    v.valor == null ? v.motivo : `${T(v.ok ? "sitio.mej.cumple" : "sitio.mej.paso")} · ${fechaCorta(v.fecha)}`, v.valor == null ? null : v.ok));
  if (p) cuadros.push(cuadro(T("sitio.mej.prueba", { n: p.nombre }), p.valor, p.cambio, p.mejor));
  return DS.tarjeta({ titulo: T("sitio.mej.titulo"), clase: "ancha" }, DS.tiles({ etiqueta: T("sitio.mej.titulo"), clase: "mejora" }, ...cuadros));
}

/** " · 2× Corrida · 1× CrossFit" a partir de los entrenos de la semana (para el globito y lectores de pantalla). */
const textoEntrenos = (entrenos) => (entrenos || []).map((e) => ` · ${e.n}× ${e.nombre}`).join("");

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
  const num = (valor, etiqueta) => h("div", {}, h("div", { class: "big" }, valor), h("div", { class: "k" }, etiqueta));
  return DS.tarjeta({ titulo: [DS.ico(c.icono || "medalla"), T("sitio.carr.titulo", { f: fechaLarga(c.fecha) })], clase: "carrera carrera-hoy" },
    h("div", { class: "nums4" },
      num(`${fmt(c.distancia_km, 2)} km`, T("sitio.carr.dist")), num(tiempoLargo(c.tiempo_s), T("sitio.carr.tiempo")),
      num(c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : "—", T("sitio.carr.ritmo")), num(c.fc_prom != null ? `${fmt(c.fc_prom, 0)} ${T("sitio.lpm")}` : "—", T("sitio.carr.fc"))),
    h("a", { class: "liga", href: "#progreso", onclick: () => { abrirCarrera = true; } }, T("sitio.carr.ver")));
}

/** Sin plan: «tu semana». Python ya calculó todo (`semana_libre`); aquí solo se pinta. */
function renderHoySinPlan(d) {
  const sl = d.semana_libre || {};
  const dif = (v, prom, unidad) => (prom ? [[T("sitio.sl.vs", { p: fmt(prom, 0), u: unidad }), "neutro"]] : [[T("sitio.sl.sin_prom"), "neutro"]]);
  const hoyIso = (d.generado || "").slice(0, 10);
  const dias = calendarioTocable(sl.dias || [], hoyIso, (x, sel, tocar) => DS.diaCal({ nombre: x.dia_semana, numero: parseFecha(x.fecha).getDate(), hoy: x.hoy,
    titulo: `${fechaCorta(x.fecha)}: ${x.actividades.length ? x.actividades.map((a) => `${a.nombre} ${T("sitio.min_n", { n: fmt(a.minutos, 0) })}`).join("; ") : T("sitio.dia.sin")}`,
    hijos: x.actividades.map((a) => h("span", { class: "cf" }, DS.ico(a.icono || "punto"), h("span", {}, fmt(a.minutos, 0)))), seleccionado: sel, alTocar: tocar }));
  const rec = sl.recuperacion;
  const racha = sl.racha_semanas || 0;
  $("vista-hoy").replaceChildren(...[
    bannerHoy(d),
    DS.tarjeta({ titulo: T("sitio.sl.titulo"), clase: "ancha" },
      sl.actividades ? DS.tiles({ etiqueta: T("sitio.sl.titulo") },
        DS.tile({ k: T("sitio.sl.minutos"), valor: fmt(sl.minutos, 0), unidad: T("sitio.sl.min"), deltas: dif(sl.minutos, sl.promedio_minutos, T("sitio.sl.min")) }),
        DS.tile({ k: T("sitio.sl.km"), valor: fmt(sl.km, 1), unidad: "km", deltas: dif(sl.km, sl.promedio_km, "km") }),
        DS.tile({ k: T("sitio.sl.racha"), valor: String(racha), unidad: T(racha === 1 ? "sitio.sl.semana_1" : "sitio.sl.semana_n") }))
        : DS.estadoVacio({ icono: null, titulo: T("sitio.sl.vacia") }),
      h("div", { class: "cal-caja" }, ...dias)),
    sl.intensidad ? zonaBar(sl.intensidad) : null,
    rec ? DS.tarjeta({ titulo: T("sitio.sl.recup") },
      rec.hrv_7d != null ? h("div", { class: "kv" }, h("span", {}, T("sitio.sl.hrv")), h("span", {}, `${fmt(rec.hrv_7d, 0)} ms`)) : null,
      rec.rhr_7d != null ? h("div", { class: "kv" }, h("span", {}, T("sitio.sl.rhr")), h("span", {}, `${fmt(rec.rhr_7d, 0)} ${T("sitio.lpm")}`)) : null,
      rec["sueño_7d"] != null ? h("div", { class: "kv" }, h("span", {}, T("sitio.sl.sueno")), h("span", {}, T("sitio.sl.horas", { n: fmt(rec["sueño_7d"], 1) }))) : null) : null,
    d.aviso_zonas ? DS.aviso({ clase: "warn", simbolo: "!", extra: "ancha", texto: d.aviso_zonas }) : null].filter(Boolean));
}

function renderHoy(d) {
  PINTAR.hoy = [];
  if (ui().sin_plan && d.semana_libre) return renderHoySinPlan(d);
  const sems = semanasHoy(d);
  if (semIdx === null) semIdx = Math.min(Math.max((d.semana_hoy_idx ?? 0) + semInicial, 0), Math.max(sems.length - 1, 0));
  $("vista-hoy").replaceChildren(...[
    d.hoy.semaforo.repetir_semana
      ? DS.aviso({ clase: "bad", simbolo: "✕", extra: "ancha", texto: [h("strong", {}, T("sitio.rep.t")), T("sitio.rep.d")] })
      : null,
    bannerHoy(d), tarjetaPlanTerminado(d), resumenSemanaPasada(d), h("div", { id: "hoy-semana" }),
    d.aviso_zonas ? DS.aviso({ clase: "warn", simbolo: "!", extra: "ancha", texto: d.aviso_zonas }) : null].filter(Boolean));
  pintarSemana(d);
}
function bloqueCarga(s) {
  const a = s.carga.total, b = s.carga_anterior.total;
  let delta = T("sitio.carga.sin");
  if (b > 0) {
    const pct = Math.round(((a - b) / b) * 100);
    delta = T("sitio.carga.vs", { f: pct >= 0 ? "▲" : "▼", p: Math.abs(pct), b: fmt(b, 0) });
  }
  return DS.tarjeta({ titulo: T("sitio.carga.titulo") },
    h("p", { class: "big" }, fmt(a, 0)),
    h("p", { class: "nota" }, delta),
    ...ui().categorias.map((c) => h("div", { class: "kv" }, h("span", {}, c.nombre), h("span", {}, fmt(s.carga[c.id], 0)))),
    h("div", { class: "kv" }, h("span", {}, T("sitio.carga.corridas")), h("span", {}, fmt(s.carga.run, 0))));
}

/** 80/20 de una semana de Hoy, como la de Plan › Intensidad: zona y % dentro de la barra y "Bajo 72 % · meta 80 %".
 *  Sin minutos en zonas, no se pinta. */
function intensidadCompacta(s) {
  const dist = s.intensidad;
  if (!dist || !dist.minutos) return null;
  const barra = DS.barraZonas(dist, { etiquetas: true });
  if (!barra) return null;
  return h("div", { class: "int-sem" }, barra, h("p", { class: "nota" }, T("sitio.int.bajo_meta", { v: fmt(dist.bajo, 0) })));
}

function zonaBar(dist) {
  const z = ["Z1", "Z2", "Z3", "Z4", "Z5"];
  const total = z.reduce((a, k) => a + dist.minutos[k], 0);
  const raiz = DS.tarjeta({ titulo: [T("sitio.int.titulo"), DS.chip(T("sitio.int.ref"), "neutro")] });
  if (total <= 0) {
    raiz.append(DS.estadoVacio({ icono: null, titulo: T("sitio.int.sin") }));
    return raiz;
  }
  const pct = (k) => (dist.minutos[k] / total) * 100;
  raiz.append(DS.barraZonas(dist));
  const grupo = (zs, nombre, valor, meta) => h("div", { class: "grupo" },
    h("span", { class: "sw", "aria-hidden": "true" }, zs.map((k) => h("i", { style: `background:var(--${k.toLowerCase()})` }))),
    h("strong", {}, `${nombre} ${zs.length > 1 ? `${zs[0]}–${zs[1]}` : zs[0]}`),
    h("span", {}, `${fmt(valor, 0)} %`), meta ? h("span", { class: "nota" }, meta) : null);
  raiz.append(h("div", { class: "grupos" },
    grupo(["Z1", "Z2"], T("sitio.int.bajo"), dist.bajo, T("sitio.int.meta")),
    grupo(["Z3"], T("sitio.int.limbo"), dist.limbo, T("sitio.int.menos")),
    grupo(["Z4", "Z5"], T("sitio.int.alto"), dist.alto, T("sitio.int.veinte"))));
  raiz.append(h("p", { class: "nota" }, T("sitio.int.nota", { i: ui().textos.incluye || T("sitio.int.incluye") })));
  raiz.append(DS.desplegable({ titulo: T("sitio.int.tabla"), liga: true }, DS.tabla({ etiqueta: T("sitio.int.min_zona"),
    columnas: [{ texto: T("sitio.int.zona") }, { texto: T("sitio.int.min"), num: true }, { texto: "%", num: true }],
    filas: z.map((k) => ({ celdas: [k, fmt(dist.minutos[k]), fmt(pct(k), 0)] })) })));
  return raiz;
}
