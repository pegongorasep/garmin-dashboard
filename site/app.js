// Dashboard: solo pinta lo que recibe de data.json (la lógica vive en dashboard/build.py).
const VISTAS = ["hoy", "plan", "progreso", "ayuda"];   // Progreso tiene dos subvistas: Corridas (#progreso) y Cuerpo (#progreso/cuerpo)
const DIAS_LARGO = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];
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

const badge = (clase, simbolo, etiqueta) => DS.insignia(clase, simbolo, etiqueta);

const estadoSenal = (estado) => (estado === "ok" ? { clase: "ok", simbolo: "✓" } : estado === "fuera" ? { clase: "warn", simbolo: "!" } : { clase: "nd", simbolo: "—" });

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
  return total <= 0 ? null : DS.barraTroteCaminata({ trote: Math.round(tr.trote_min), caminata: Math.round(tr.camina_min) });
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
  return [barraRW(tr), h("p", { class: "nota" }, patron), ritmo ? h("p", {}, ritmo) : null].filter(Boolean);
}

// --- Sesiones del plan ---

/** Estado de una sesión del plan como {clase, simbolo, texto, etiqueta} para DS.filaSesion. */
function estadoSesion(est) {
  if (!est) return null;
  if (est.estado === "pendiente") return { clase: "nd", simbolo: "—", texto: "Pendiente", etiqueta: "pendiente" };
  if (est.estado === "incompleta") return { clase: "warn", simbolo: "!", texto: "Incompleta", etiqueta: "incompleta" };
  if (est.ajustada) return { clase: "warn", simbolo: "!", texto: "Hecha · ajustada", etiqueta: "hecha y ajustada" };
  return { clase: "ok", simbolo: "✓", texto: "Hecha", etiqueta: "hecha" };
}

/** Sesión de calidad: estructura legible y zona objetivo con sus lpm. */
function bloqueCalidad(s) {
  if (!s || !s.objetivo) return null;
  const o = s.objetivo;
  return h("div", { class: "calidad" }, h("p", { class: "b-t" }, s.estructura),
    h("p", { class: "nota" }, `Zona objetivo: ${o.zona}${o.lpm ? ` (${o.lpm[0]}–${o.lpm[1]} lpm)` : ""} · ${o.minutos} min de trabajo`));
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
    const notas = pasos.filter((p) => p.note && p.note !== "opcional" && p.note !== ETIQUETA_PASO[p.kind]).map((p) => {
      const tipo = ETIQUETA_PASO[p.kind] || p.kind;
      return h("p", { class: "nota" }, `${tipo[0].toUpperCase()}${tipo.slice(1)}${p.optional ? " (opcional)" : ""}: ${p.note}`);
    });
    return notas.length ? h("div", { class: "notas-paso" }, ...notas) : null;
  }
  return DS.desplegable({ titulo: "Ver pasos", liga: true }, h("ul", { class: "pasos-ses" }, pasos.map(pasoLi)));
}

/** Cuerpo desplegable de una sesión del plan (la silueta ya se ve en la fila): pasos y versión suave. */
function cuerpoPlan(s) {
  return [bloqueCalidad(s), s.nota ? h("p", { class: "nota" }, s.nota) : null, detallePasos(s), versionSuave(s)].filter(Boolean);
}

function versionSuave(s) {
  return s.easy ? DS.desplegable({ titulo: `Versión suave (${s.easy.minutes} min)`, liga: true }, bloqueSilueta(s.easy), detallePasos(s.easy)) : null;
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
  if (t.tipo === "otra") return prox ? `Hoy: ${t.categoria} ✓ · próxima corrida: ${prox}` : `Hoy: ${t.categoria} ✓`;
  if (t.tipo === "sesion") { const sig = nombreSesion(est, t.sesion_id); return sig ? `Próxima corrida: ${sig}` : null; }
  if (t.tipo === "hecha_hoy") return prox ? `Corrida de hoy hecha · próxima: ${prox}` : "Corrida de hoy hecha";
  if (t.tipo === "sin_plan" || t.tipo === "primera_sync" || t.tipo === "pausa") return t.texto;
  if (t.tipo === "completa") return "Semana completa: hiciste las 3";
  if (t.tipo === "plan_terminado") return null;   // lo dice su propia tarjeta
  return null;
}

/** Banner de la sesión de hoy con el semáforo como chip: «Recuperación: verde · ver señales» abre las señales. */
function bannerHoy(d) {
  const sem = d.hoy.semaforo, est = ESTADO_SEMAFORO[sem.color] || ESTADO_SEMAFORO.sin_datos;
  const texto = textoBanner(d);
  const ayer = d.hoy.ayer ? `Ayer: ${d.hoy.ayer.categoria}${d.hoy.ayer.esfuerzo != null ? `, esfuerzo ${fmt(d.hoy.ayer.esfuerzo, 1)}` : ""}` : null;
  return DS.tarjeta({ clase: "ancha banner" },
    texto ? h("p", { class: "b-t" }, texto) : null,
    DS.desplegable({ titulo: [badge(est.clase, est.icono, est.titulo), `Recuperación: ${sem.color === "sin_datos" ? "sin datos" : est.titulo.toLowerCase()}`, h("span", { class: "mu" }, " · ver señales")] },
      DS.senales({ senales: (d.hoy["señales"] || []).map((x) => ({ ...estadoSenal(x.estado), nombre: nombreSenal(x.id), texto: x.texto })), nota: ayer })));
}

const PRUEBA_NOMBRE = { fc_fija: "30 min a FC fija", trote_continuo: "trote continuo", "5k": "5 km" };

/** "7:42 /km", "93 % de trote" o "25:00" según la prueba. */
function valorPrueba(tipo, v) {
  return tipo === "trote_continuo" ? (v >= 95 ? `30 min seguidos (${fmt(v, 0)} % de trote)` : `${fmt(v, 0)} % de trote`) : tipo === "5k" ? tiempoLargo(v) : `${mmss(v)} /km`;
}

/** Tarjeta "Plan terminado": resultado de la prueba contra el inicio (o contra la prueba anterior) y el siguiente paso. */
function tarjetaPlanTerminado(d) {
  const t = d.hoy.tarjeta;
  if (t.tipo !== "plan_terminado") return null;
  const p = t.prueba;
  const c = DS.tarjeta({ titulo: "Plan terminado", clase: "ancha plan-fin" });
  if (!p) c.append(DS.estado("nd", "—", "Falta la prueba: no hay una corrida de la última semana que cuente como prueba.", "falta"));
  else {
    c.append(h("p", { class: "big" }, p.valor == null ? `Prueba de ${PRUEBA_NOMBRE[p.tipo]}: sin resultado` : valorPrueba(p.tipo, p.valor)),
      h("p", { class: "nota" }, `Prueba de ${PRUEBA_NOMBRE[p.tipo]} · ${fechaCorta(p.fecha)}${p.km ? ` · ${fmt(p.km, 2)} km` : ""}`));
    if (p.base && p.dif != null) {
      const donde = p.base.fuente === "prueba" ? `tu prueba del ${fechaCorta(p.base.fecha)}` : p.base.fuente === "mejor_5k" ? `tu mejor 5 km (${fechaCorta(p.base.fecha)})` : "el inicio del plan (semanas 1–2)";
      const mag = p.tipo === "trote_continuo" ? `${fmt(Math.abs(p.dif), 0)} puntos de trote` : p.tipo === "5k" ? tiempoLargo(Math.abs(p.dif)) : `${fmt(Math.abs(p.dif), 0)} s/km`;
      const mejor = p.tipo === "trote_continuo" ? "más trote" : "más rápido", peor = p.tipo === "trote_continuo" ? "menos trote" : "más lento";
      c.append(p.mejor == null ? DS.estado("nd", "=", `Igual que ${donde} (${valorPrueba(p.tipo, p.base.valor)})`, "igual")
        : DS.estado(p.mejor ? "ok" : "warn", p.mejor ? "✓" : "!", `${mag} ${p.mejor ? mejor : peor} que ${donde} (${valorPrueba(p.tipo, p.base.valor)})`, p.mejor ? "mejor" : "peor"));
    } else if (!p.base) c.append(h("p", { class: "nota" }, "Sin base para comparar: la próxima prueba se comparará con esta."));
  }
  c.append(h("p", {}, t.siguiente || "Corre /ajustar para el siguiente bloque",
    t.siguiente_url ? [" · ", h("a", { href: t.siguiente_url }, "Armar siguiente bloque")] : null));
  return c;
}

/** Resumen de la semana pasada (calculado en Python): una línea y, al tocarla, el resto. */
function resumenSemanaPasada(d) {
  const r = d.hoy.semana_pasada;
  if (!r) return null;
  const sug = r.sugerencia;
  const linea = [    r.sesiones_total != null ? `${r.sesiones_hechas} de ${r.sesiones_total}` : null,
    r.plan_min != null ? `${fmt(r.minutos, 0)} / ${fmt(r.plan_min, 0)} min` : `${fmt(r.minutos, 0)} min`,
    `${r.dias_verdes} de 7 días verdes${r.dias_sin_datos ? ` (${r.dias_sin_datos} sin datos)` : ""}`].filter(Boolean);
  const cuando = (a, b) => (a == null || b == null ? null : Math.abs(a - b) < 3 ? "igual que la anterior" : `${a < b ? "más rápido" : "más lento"} que la anterior (${mmss(b)})`);
  const carga = r.carga_anterior ? `Carga ${fmt(r.carga, 0)} (${r.carga >= r.carga_anterior ? "▲" : "▼"} ${Math.abs(Math.round(((r.carga - r.carga_anterior) / r.carga_anterior) * 100))} % vs ${fmt(r.carga_anterior, 0)})` : `Carga ${fmt(r.carga, 0)}`;
  const ritmo = r.ritmo_ref_s != null ? `Ritmo a ${(d.progreso || {}).fc_ref} lpm: ${mmss(r.ritmo_ref_s)} /km${cuando(r.ritmo_ref_s, r.ritmo_ref_anterior_s) ? `, ${cuando(r.ritmo_ref_s, r.ritmo_ref_anterior_s)}` : ""}` : null;
  const dist = r.intensidad || {};
  return DS.tarjeta({ clase: "ancha banner semana-pasada" }, DS.desplegable({
    titulo: h("span", { class: "sp-titulo" }, h("span", { class: "sp-linea" }, `Semana pasada: ${linea.join(" · ")}`),
      sug ? h("span", { class: "estado" }, badge(sug.tipo === "sigue" ? "ok" : "warn", sug.tipo === "sigue" ? "✓" : "!", "sugerencia"), sug.texto) : null) },
  h("div", { class: "sp-cuerpo" },
    h("p", {}, `${fmt(r.km)} km${r.pct_trote != null ? ` · ${fmt(r.pct_trote, 0)} % trote` : ""}`),
    dist.bajo != null ? h("p", {}, `80/20: bajo ${fmt(dist.bajo, 0)} % · limbo ${fmt(dist.limbo, 0)} % · alto ${fmt(dist.alto, 0)} %`) : null,
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
    ? `Semana ${s.n}${total ? ` de ${total}` : ""} · ${rangoSemana(s)}${s.kind ? ` · ${s.kind}` : ""}`
    : `Semana del ${rangoSemana(s)}`;
}

function selectorSemana(d) {
  const sems = semanasHoy(d), s = sems[semIdx];
  const mover = (delta) => () => { semIdx = Math.min(Math.max(semIdx + delta, 0), sems.length - 1); pintarSemana(d); };
  const hoyIdx = d.semana_hoy_idx ?? 0;
  return h("div", { class: "selector ancha" },
    DS.selectorSemana({ texto: etiquetaSelector(d, s), sinAnterior: semIdx <= 0, sinSiguiente: semIdx >= sems.length - 1, onAnterior: mover(-1), onSiguiente: mover(1) }),
    semIdx !== hoyIdx ? DS.boton("Volver a esta semana", { variante: "texto", chico: true, onclick: () => { semIdx = hoyIdx; pintarSemana(d); } }) : null);
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

function tarjetaEstaSemana(d, s) {
  const st = s.stats || {};
  const partes = st.corridas
    ? [plural(st.corridas, "corrida", "corridas"), st.minutos != null ? `${fmt(st.minutos, 0)} min` : null,
      st.km != null ? `${fmt(st.km)} km` : null, st.pct_trote != null ? `${fmt(st.pct_trote, 0)} % trote` : null].filter(Boolean)
    : [s.estado === "futura" ? "Aún no empieza" : "Sin corridas"];
  const c = DS.tarjeta({ titulo: tituloSemana(d, s), clase: "ancha" }, h("p", { class: "titular" }, partes.join(" · ")), intensidadCompacta(s));
  const p = s.plan;
  if (p) {
    if (s.estado === "futura") c.append(h("p", { class: "nota" }, `Plan: ${p.total} sesiones · ${fmt(p.plan_min, 0)} min`));
    else {
      const min = st.minutos || 0, pct = Math.round((min / p.plan_min) * 100);
      c.append(DS.anilloPlan({ pct, titulo: `${fmt(min, 0)} / ${fmt(p.plan_min, 0)} min · ${pct} %`,
        texto: `Plan: ${p.hechas} de ${p.total} sesiones${p.incompletas ? ` · ${plural(p.incompletas, "incompleta", "incompletas")}` : ""}`,
        etiqueta: `${fmt(min, 0)} de ${fmt(p.plan_min, 0)} minutos` }));
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
  if (x.planeado && !x.corrida) partes.push("corrida planeada");
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
    return h("span", { class: `cf${varias ? ` cat ${c.clase}` : ""}`, title: c.nombre }, DS.ico(c.icono), cfTxt ? h("span", {}, cfTxt) : null);
  };
  let marca = [];
  if (x.corrida) {
    const cls = x.corrida.estado === "hecha" ? "" : x.corrida.estado === "incompleta" ? " incompleta" : " extra";
    marca = [h("span", { class: `circ${cls}${x.corrida.carrera ? " carrera" : ""}`, "aria-hidden": "true" }, parseFecha(x.fecha).getDate()),
      h("span", { class: "sn" }, DS.ico(x.corrida.icono || (x.corrida.carrera ? "medalla" : "correr")), h("span", {}, `${fmt(x.corrida.minutos, 0)}' ${x.corrida.sesion_nombre}` + (x.corridas_n > 1 ? ` +${x.corridas_n - 1}` : ""))),
      x.corrida.carrera ? h("span", { class: "sn-carrera" }, "carrera") : null];
  }
  if (!marca.length && x.planeado) marca = [h("span", { class: "circ planeado", "aria-hidden": "true" }, parseFecha(x.fecha).getDate())];   // corrida planeada, aún sin hacer
  const cfMarca = (x.otras || []).map((cf) => marcaCat(cf.cat, cf.esfuerzo != null ? fmt(cf.esfuerzo, 1) : null));
  return DS.diaCal({ nombre: x.dia_semana, numero: parseFecha(x.fecha).getDate(), hoy: x.fecha === hoyIso, titulo: diaTexto(x), numeroEnMarca: marca.length > 0, hijos: [...marca, ...cfMarca] });
}

function calendarioSemana(d, s) {
  const hoyIso = (d.generado || "").slice(0, 10);
  return h("div", { class: "cal-caja" }, DS.calendario((s.dias || []).map((x) => diaCalendario(x, hoyIso))),
    h("p", { class: "nota" }, "número = esfuerzo calculado con tu FC (1–10)"));
}

/** Plan vs real por zona: "Z3 o más · 2 de 4 min · 50 %" con ✓/⚠; con una sola zona planeada, "Z2 · 19 de 20 min ✓". */
function lineasPlanVsReal(filas) {
  if (!filas || !filas.length) return null;
  const solo = filas.length === 1;
  return h("div", { class: "pvr" }, filas.map((f) => {
    const nombre = solo ? f.zona : f.zona === "Z5" ? "Z5" : `${f.zona} o más`;
    const txt = solo ? `${nombre} · ${fmt(f.hecho_min, 0)} de ${fmt(f.plan_min, 0)} min` : `${nombre} · ${fmt(f.hecho_min, 0)} de ${fmt(f.plan_min, 0)} min · ${f.pct} %`;
    return f.ok ? DS.estado("ok", "✓", `${txt} ✓`, "cumplido") : DS.estado("warn", "!", `${txt} ⚠`, "por debajo del plan");
  }), filas[0].mucho_arriba
    ? DS.estado("warn", "!", `${fmt(filas[0].arriba_min, 0)}' por encima de ${filas[0].zona} ⚠`, "muy por encima")
    : null);
}

function lineaTecho(c) {
  const txt = `${fmt(c.min_sobre_techo)}' sobre el techo (tolerancia ${fmt(c.tolerancia_min, 0)}')`;
  return c.techo_ok ? DS.estado("ok", "✓", txt, "dentro del techo") : DS.estado("warn", "!", txt, "sobre el techo");
}

function lineaDeriva(c) {
  const txt = `Deriva ${fmt(c.deriva_pct, 1)} %`;
  return c.deriva_ok ? DS.estado("ok", "✓", `${txt} ✓`, "deriva baja") : DS.estado("warn", "!", `${txt} (menos de 5 % es buena base)`, "deriva alta");
}

/** Fila de una corrida hecha o extra: estado + título, y al abrirla (ya viene abierta) datos, techo y detalle de trote/caminata. */
function filaCorrida(estado, titulo, c, extra = {}) {
  c = c || {};
  const datos = [c.minutos != null ? `${fmt(c.minutos, 0)}'` : null, c.km != null ? `${fmt(c.km)} km` : null,
    c.pct_trote != null ? `${fmt(c.pct_trote, 0)} % trote` : null,
    c.ritmo_trote_s ? `${mmss(c.ritmo_trote_s)} /km${c.caminadora ? " (caminadora)" : ""}` : null, textoEsfuerzo(c) || null].filter(Boolean);
  return DS.filaSesion({ nombre: titulo, estado, abierta: true, ...extra, cuerpo: [
    c.carrera ? DS.chip("CARRERA", "neutro") : null,
    datos.length ? h("p", {}, datos.join(" · ")) : null,
    c.plan_vs_real ? lineasPlanVsReal(c.plan_vs_real) : null,
    c.techo_ok !== undefined ? lineaTecho(c) : null,
    c.deriva_pct != null ? lineaDeriva(c) : null,
    DS.desplegable({ titulo: "Ver detalle", liga: true }, ...detalleTrote({ trote: c.trote_min != null ? c : null, caminadora: c.caminadora }),
      c.ritmo_ref_s ? h("p", {}, `Ritmo a ${(datos.progreso || {}).fc_ref} lpm: ${mmss(c.ritmo_ref_s)} /km`) : null)].filter(Boolean) });
}

const filaHecha = (e) => filaCorrida(estadoSesion(e), `${e.name} · ${e.fecha ? fechaCorta(e.fecha) : ""}`, e.corrida);

function filaExtra(x) {
  return filaCorrida({ clase: "nd", simbolo: "+", texto: "Extra", etiqueta: "extra" }, `Extra · ${fechaCorta(x.fecha)}`, x);
}

function filaNoHecha(e, s) {
  return DS.filaSesion({ nombre: e.name, sub: s ? `${s.minutes} min` : null, estado: { clase: "nd", simbolo: "✗", texto: "No hecha", etiqueta: "no hecha" } });
}

function filaHoy(e, s, t) {
  const suave = t.version === "suave";
  const ses = s && suave ? s.easy : s;
  const cuerpo = [];
  if (t.motivo) cuerpo.push(h("p", { class: "nota" }, `Por: ${t.motivo}`));
  if (t.version === "descanso") cuerpo.push(h("p", {}, "Hoy descanso o caminata ligera de 20–30' en Z1"));
  else if (ses) cuerpo.push(...[bloqueSilueta(ses), bloqueCalidad(ses), detallePasos(ses), suave ? null : versionSuave(s)].filter(Boolean));
  if (t.aviso) cuerpo.push(DS.aviso({ clase: "warn", simbolo: "!", texto: t.aviso }));
  return DS.filaSesion({ nombre: t.version === "descanso" ? e.name : `${e.name}${suave ? " (versión suave)" : ""}`, minutos: t.version === "descanso" || !ses ? null : ses.minutes,
    hoy: true, abierta: true, cuerpo });
}

function filaPendiente(e, s) {
  const larga = e.tipo === "larga";
  return DS.filaSesion({ nombre: e.name, sub: `${s ? `${s.minutes} min` : ""}${larga ? `${s ? " · " : ""}sáb o dom` : ""}` || null,
    silueta: silFila(s), titulo: s && s.titulo, cuerpo: s ? cuerpoPlan(s) : [] });
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
  return DS.tarjeta({ titulo: "Tus corridas", clase: `filas${ancha ? " ancha" : ""}` },
    ...(filas.length ? filas : [DS.estadoVacio({ icono: null, titulo: "Sin corridas esta semana" })]));
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
  const cuadros = [cuadro(`Ritmo a ${r.fc_ref} lpm`, r.valor,
    r.valor == null ? r.motivo : r.cambio ? `${r.cambio}${r.mejora == null ? "" : r.mejora ? " · mejor" : " · más lento"}` : r.motivo,
    r.mejora, r.valor != null && r.cambio ? r.motivo : null)];
  cuadros.push(cuadro("Deriva cardiaca", v.valor,
    v.valor == null ? v.motivo : `${v.ok ? "✓ cumple" : "⚠ pasó de 5 %"} · ${fechaCorta(v.fecha)}`, v.valor == null ? null : v.ok));
  if (p) cuadros.push(cuadro(`Prueba · ${p.nombre}`, p.valor, p.cambio, p.mejor));
  return DS.tarjeta({ titulo: "Cómo vas mejorando", clase: "ancha" }, DS.tiles({ etiqueta: "Cómo vas mejorando", clase: "mejora" }, ...cuadros));
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
  return DS.tarjeta({ titulo: [DS.ico(c.icono || "medalla"), `Tu carrera del ${fechaLarga(c.fecha)}`], clase: "carrera carrera-hoy" },
    h("div", { class: "nums4" },
      num(`${fmt(c.distancia_km, 2)} km`, "Distancia"), num(tiempoLargo(c.tiempo_s), "Tiempo"),
      num(c.ritmo_s ? `${mmss(c.ritmo_s)} /km` : "—", "Ritmo"), num(c.fc_prom != null ? `${fmt(c.fc_prom, 0)} lpm` : "—", "FC promedio")),
    h("a", { class: "liga", href: "#progreso", onclick: () => { abrirCarrera = true; } }, "Ver todo en Progreso › Carreras"));
}

function renderHoy(d) {
  PINTAR.hoy = [];
  const sems = semanasHoy(d);
  if (semIdx === null) semIdx = Math.min(Math.max((d.semana_hoy_idx ?? 0) + semInicial, 0), Math.max(sems.length - 1, 0));
  $("vista-hoy").replaceChildren(...[
    d.hoy.semaforo.repetir_semana
      ? DS.aviso({ clase: "bad", simbolo: "✕", extra: "ancha", texto: [h("strong", {}, "Repetir la semana. "), "Dos días seguidos en rojo: repite la semana anterior del plan."] })
      : null,
    bannerHoy(d), tarjetaPlanTerminado(d), resumenSemanaPasada(d), h("div", { id: "hoy-semana" }),
    d.aviso_zonas ? DS.aviso({ clase: "warn", simbolo: "!", extra: "ancha", texto: d.aviso_zonas }) : null].filter(Boolean));
  pintarSemana(d);
}
function bloqueCarga(s) {
  const a = s.carga.total, b = s.carga_anterior.total;
  let delta = "Sin semana anterior para comparar";
  if (b > 0) {
    const pct = Math.round(((a - b) / b) * 100);
    delta = `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct)} % vs semana anterior (${fmt(b, 0)})`;
  }
  return DS.tarjeta({ titulo: "Carga semanal (esfuerzo × min)" },
    h("p", { class: "big" }, fmt(a, 0)),
    h("p", { class: "nota" }, delta),
    ...ui().categorias.map((c) => h("div", { class: "kv" }, h("span", {}, c.nombre), h("span", {}, fmt(s.carga[c.id], 0)))),
    h("div", { class: "kv" }, h("span", {}, "Corridas"), h("span", {}, fmt(s.carga.run, 0))));
}

/** 80/20 de una semana de Hoy, como la de Plan › Intensidad: zona y % dentro de la barra y "Bajo 72 % · meta 80 %".
 *  Sin minutos en zonas, no se pinta. */
function intensidadCompacta(s) {
  const dist = s.intensidad;
  if (!dist || !dist.minutos) return null;
  const barra = DS.barraZonas(dist, { etiquetas: true });
  if (!barra) return null;
  return h("div", { class: "int-sem" }, barra, h("p", { class: "nota" }, `Bajo ${fmt(dist.bajo, 0)} % · meta 80 %`));
}

function zonaBar(dist) {
  const z = ["Z1", "Z2", "Z3", "Z4", "Z5"];
  const total = z.reduce((a, k) => a + dist.minutos[k], 0);
  const raiz = DS.tarjeta({ titulo: ["Intensidad de la semana", DS.chip("REFERENCIA", "neutro")] });
  if (total <= 0) {
    raiz.append(DS.estadoVacio({ icono: null, titulo: "Aún no hay minutos en zonas esta semana." }));
    return raiz;
  }
  const pct = (k) => (dist.minutos[k] / total) * 100;
  raiz.append(DS.barraZonas(dist));
  const grupo = (zs, nombre, valor, meta) => h("div", { class: "grupo" },
    h("span", { class: "sw", "aria-hidden": "true" }, zs.map((k) => h("i", { style: `background:var(--${k.toLowerCase()})` }))),
    h("strong", {}, `${nombre} ${zs.length > 1 ? `${zs[0]}–${zs[1]}` : zs[0]}`),
    h("span", {}, `${fmt(valor, 0)} %`), meta ? h("span", { class: "nota" }, meta) : null);
  raiz.append(h("div", { class: "grupos" },
    grupo(["Z1", "Z2"], "Bajo", dist.bajo, "· meta 80 %"),
    grupo(["Z3"], "Limbo", dist.limbo, "· lo menos posible"),
    grupo(["Z4", "Z5"], "Alto", dist.alto, "· 20 %")));
  raiz.append(h("p", { class: "nota" }, `${ui().textos.incluye || "Incluye tus actividades y corridas."} Solo referencia: no cambia el plan. El tiempo bajo Z1 (Z0) es descanso y no cuenta.`));
  raiz.append(DS.desplegable({ titulo: "Ver como tabla", liga: true }, DS.tabla({ etiqueta: "Minutos por zona",
    columnas: [{ texto: "Zona" }, { texto: "Min", num: true }, { texto: "%", num: true }],
    filas: z.map((k) => ({ celdas: [k, fmt(dist.minutos[k]), fmt(pct(k), 0)] })) })));
  return raiz;
}
