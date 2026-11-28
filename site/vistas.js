// Ayuda, tema, rutas, menú y arranque. Se carga al final, después de vista_*.js.
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
  c.append(h("h3", { class: "titular" }, T("sitio.ult_n_sem", { n: (det.carga_semanas || []).length })), DET.carga.sub, DET.carga.chart, DET.carga.extra);
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
  const barras = semanas.map((s) => ({ inicio: s.inicio, actual: s.actual, valores: [...cats.map((c) => (s.cargas || {})[c.id] || 0), s.carga_corrida || 0] }));
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
// ¿Va la pestaña Grupos? Solo en la web propia, también con 0 grupos: lo dice Python con ui.vacios.grupos (null al coach; el build local no lo trae).
// Antes de data.json, la web marca la página propia con <main data-grupos>. Sin la clave nueva, como antes: solo con algún grupo.
const hayGrupos = () => (datos ? !ui().coach && (!!(ui().vacios || {}).grupos || nGrupos() > 0) : !!$("app") && $("app").dataset.grupos != null);
const tabsDef = () => [{ id: "hoy", texto: T("sitio.tab.hoy"), icono: "hoy", href: "#hoy" },
  { id: "plan", texto: T("sitio.tab.plan"), icono: "plan", href: "#plan" },
  { id: "progreso", texto: T("sitio.tab.progreso"), icono: "progreso", href: "#progreso" },
  ...(hayGrupos() ? [{ id: "grupo", texto: T("sitio.tab.grupo"), icono: "personas", href: "#juntos", punto: true, nuevo: juntosNuevo }] : [])];
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

/** Texto con **negritas** → nodos (texto y <strong>). */
function conNegritas(texto) {
  return String(texto).split("**").map((x, i) => (i % 2 ? h("strong", {}, x) : x));
}

/** Diálogo «Autoriza una vez»: explica qué pasa en GitHub antes de mandar a la persona (liga `url`, normalmente ui.sync.url_autorizar).
 *  El nombre de su copia sale de ui.sync.repo. El dibujo es el mismo SVG de la guía, metido inline para que tome los colores del tema;
 *  su caja reserva el alto (aspect-ratio) y, si no carga, queda vacía sin mover nada. */
function dialogoAutorizar(url) {
  const repo = (ui().sync || {}).repo;
  const dibujo = h("div", { class: "dl-dibujo", role: "img", "aria-label": T("sitio.auth.dibujo_aria") });
  fetch("/dibujo-github.svg").then((r) => (r.ok ? r.text() : "")).then((svg) => { if (svg.startsWith("<svg")) dibujo.innerHTML = svg; }).catch(() => {});
  const d = DS.dialogo({ titulo: T("sitio.auth.titulo"), cerrar: T("sitio.auth.ahora_no"), cuerpo: [
    h("p", {}, T("sitio.auth.intro")),
    h("ol", { class: "auth-pasos" },
      h("li", {}, conNegritas(T("sitio.auth.p1"))),
      h("li", {}, conNegritas(repo ? T("sitio.auth.p2", { repo }) : T("sitio.auth.p2_sin"))),
      h("li", {}, conNegritas(T("sitio.auth.p3")), " ", h("small", { class: "auth-nota" }, T("sitio.auth.nota")))),
    dibujo,
    h("p", {}, T("sitio.auth.vuelta")),
    h("p", { class: "auth-nota" }, T("sitio.auth.permisos")),
    h("div", { class: "acciones" },
      DS.boton(T("sitio.auth.ir"), { href: url || "/conectar/github?para=conectado" }),
      DS.boton(T("sitio.auth.ahora_no"), { variante: "sec", onclick: () => d.close() })),
  ] });
  d.classList.add("dialogo-autorizar");
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}

/** Ranura de sincronizar del encabezado. Con la GitHub App encendida (ui.sync trae `puede` o `url_autorizar`) siempre es el botón «Sincronizar»
 *  (con `puede` sincroniza; sin él lleva a autorizar la app una vez); apagada, la liga «jalar datos» de siempre. */
function accionSync(u) {
  const sy = u.sync || {};
  if (sy.puede || sy.url_autorizar) {
    const viva = !!(window.Franja && window.Franja.viva());
    return h("button", { id: "sync-btn", class: "enlace-boton", type: "button", disabled: sy.puede && viva,
      onclick: () => { if (sy.puede) { if (window.Franja) window.Franja.empezar("normal"); } else dialogoAutorizar(sy.url_autorizar); } },
      T(sy.puede ? "sitio.sync.boton" : "sitio.sync.autorizar"));
  }
  return u.acciones_url ? h("a", { id: "acciones-link", href: u.acciones_url, target: "_blank", rel: "noopener", title: T("sitio.enc.acciones_tip") }, T("sitio.enc.jalar")) : null;
}

/** Encabezado del sistema: logo y título, «Actualizado hace…» (con la liga a Garmin si existe), ayuda, tema y, en la web, el ☰. */
function pintarEncabezado() {
  const u = ui(), items = u.menu || [];
  if (u.titulo) document.title = `Garmin · ${u.titulo}`;
  const act = h("span", { id: "actualizado", "aria-live": "polite" });
  const jalar = accionSync(u);
  const enc = DS.encabezado({ nombre: u.titulo || T("sitio.titulo_defecto"), tema: temaActual() === "light" ? "claro" : "oscuro", conAyuda: !!(datos && (datos.ayuda || []).length),
    conMenu: items.length > 0, menuAbierto, actualizado: [act, ...(jalar ? [" · ", jalar] : [])],
    onAyuda: () => { location.hash = "#ayuda"; }, onTema: cambiarTema, onMenu: () => ponerMenu(!menuAbierto) });
  $("encabezado").replaceChildren(enc);
  if (!items.length) ponerMenu(false, false);
  actualizarEncabezado();
  if (window.Franja) window.Franja.reponer();   // si estaba sincronizando, la franja se vuelve a colgar del encabezado nuevo
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
  const csrf = $("app").dataset.csrf;
  const cerrar = (a) => async (caja) => {   // ✕ «Entendido»: solo InBody (lo decide Python con `cerrable`)
    try {
      const r = await fetch(`/historial/${a.id}/visto`, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ csrf }) });
      if (!r.ok) return;
    } catch (e) { return; }
    caja.style.height = `${caja.offsetHeight}px`;   // colapsa suave: alto → 0, luego se quita
    caja.classList.add("cerrando");
    requestAnimationFrame(() => { caja.style.height = "0px"; });
    setTimeout(() => { caja.remove(); av.hidden = !av.children.length; }, 300);
  };
  av.replaceChildren(...lista.map((a) => DS.bannerCambio({ texto: a.texto, verHref: a.url, verTexto: T("sitio.ds.ver"), onCerrar: a.cerrable && csrf ? cerrar(a) : undefined })));
}

function actualizarEncabezado() {
  const iso = datos && datos.datos_al;
  const hace = haceCuanto(iso);
  const act = $("actualizado");
  if (act) act.textContent = hace ? T("sitio.enc.actualizado", { h: hace }) : "";
}

function mostrarVista() {
  const ruta = location.hash.slice(1).split("?")[0];   // "#hoy?sem=+1" solo se lee al arrancar
  const [nombre0, sub, sub2] = (ALIAS_RUTA[ruta] || ruta.replace(/^grupo(?=\/|$)/, "juntos")).split("/");   // #grupo y #grupo/<id> (viejos) valen como #juntos
  const nombre = nombre0 === "juntos" ? "grupo" : nombre0;
  if (/^grupo(\/|$)/.test(ruta)) history.replaceState(null, "", `#${ruta.replace(/^grupo/, "juntos")}`);
  const v = nombre === "grupo" && !hayGrupos() ? "hoy" : VISTAS.includes(nombre) ? nombre : "hoy";
  subProgreso = v === "progreso" && sub === "cuerpo" ? "cuerpo" : "corridas";
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
  if (v === "grupo") { if (nGrupos() > 0 && sub === "persona" && /^\d+$/.test(sub2 || "")) cargarPersona(sub2); else cargarGrupo(sub && sub !== "persona" ? sub : null); }
  DS.animar.unaVez();
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
  $("app").hidden = true;   // antes de pintar: nada cuenta como «a la vista» (ni gasta su animación) hasta que llegue data.json
  mostrarVista();
  // Mientras llega data.json: el logo que se arma; si falla, el error con «Volver a intentar».
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

/** Al terminar una sincronización (franja:lista): vuelve a pedir data.json y repinta sin recargar la página. */
async function recargarDatos() {
  try {
    const resp = await fetch("data.json", { cache: "no-cache" });
    if (!resp.ok) return;
    datos = await resp.json();
    pintarEncabezado();
    repintarVistas();
  } catch (e) { console.error("recargarDatos:", e); }
}
// Otras páginas de la web (p. ej. la vista previa de «Quiero un plan») cargan estos scripts solo para pintar piezas (tarjetaPlan): sin #app no arranca nada.
const ES_SITIO = !!$("app");
if (ES_SITIO) {
window.addEventListener("franja:lista", recargarDatos);
window.addEventListener("franja:sin_app", (ev) => { ev.preventDefault(); recargarDatos(); });   // desinstalaron la app: el encabezado vuelve a ofrecer autorizar
window.addEventListener("franja:estado", (ev) => { const b = $("sync-btn"); if (b && b.tagName === "BUTTON") b.disabled = !!(ev.detail && ev.detail.viva); });
}

/** Pinta todas las vistas con `datos` (al arrancar y cuando cambia algo local, como dar un aviso por «Entendido»). */
function repintarVistas() {
  const vistas = { hoy: renderHoy, plan: renderPlan, progreso: renderProgreso, ayuda: renderAyuda };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, T("sitio.err.vista")); }
  }
  mostrarVista();
}

if (ES_SITIO) iniciar();
