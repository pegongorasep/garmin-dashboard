// Pestaña Juntos: grupos, feed y perfil de una persona (todo lo calcula la web; aquí solo se pinta).
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
    const cal = !pausa && t.cal && t.cal.length === 7 ? DS.miniSemana({ letras, etiqueta: T("sitio.gr.c.dias_aria", { n: t.dias_hechos || 0 }),
      celdas: t.cal.map((d) => ({ hecha: d.hecha, hoy: d.hoy, emoji: d.cats.length ? (d.cats[0] === "run" ? "🏃" : catEmoji(d.cats[0])) : null })) }) : DS.miniSemana({ letras });
    const detalle = [];
    if (t.plan && t.plan.n) {
      const p = t.progreso;
      detalle.push(h("p", {}, t.plan.total ? T("sitio.gr.semana_n", { n: t.plan.n, total: t.plan.total }) : T("sitio.gr.semana_sola", { n: t.plan.n })));
      if (t.plan.total) detalle.push(DS.barraFina({ pct: t.plan.pct || 0, etiqueta: T("sitio.gr.semana_n", { n: t.plan.n, total: t.plan.total }) }));
      if (p && !t.semana) detalle.push(h("p", {}, T("sitio.gr.progreso_aria", { hechas: p.hechas, total: p.total })));
    }
    if (t.adherencia !== null && t.adherencia !== undefined) detalle.push(h("p", {}, T("sitio.gr.adherencia", { pct: fmt(t.adherencia, 0) })));
    if (t.carrera) detalle.push(h("p", {}, t.meta || t.carrera.nombre ? T("sitio.gr.carrera", { nombre: t.carrera.nombre || t.meta, dias: t.carrera.dias }) : T("sitio.gr.carrera_sola", { dias: t.carrera.dias })));
    const racha = t.racha || 0;
    if (racha > 0) detalle.push(h("p", {}, `🔥 ${T("sitio.gr.racha", { n: racha })}`));
    if (t.ultima) detalle.push(h("p", {}, T("sitio.gr.ultima", { fecha: fechaCorta(t.ultima) })));
    const iniciales = m.nombre.split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("") || "?";
    return DS.tarjetaMiembro({ nombre: m.nombre, foto: m.foto, iniciales, color: m.usuario_id, insignias: ins,
      pct: !pausa && t.progreso && t.progreso.total ? t.progreso.pct : null,
      etiquetaAnillo: t.progreso ? T("sitio.gr.progreso_aria", { hechas: t.progreso.hechas, total: t.progreso.total }) : null,
      pausa: pausa ? T("sitio.gr.pausa") : null,
      linea: partes.length ? partes.join(" · ") : T(t.semana ? "sitio.gr.sin_actividad" : "sitio.gr.sin_datos"),
      dias: t.dias || [], etiquetaDias: T("sitio.gr.dias_aria", { n: t.dias_n || 0 }),
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
  const resumen = [it.manual ? T("sitio.dia.a_mano") : null, it.km != null ? T("sitio.km_n", { n: fmt(it.km, 1) }) : null, it.minutos ? T("sitio.min_n", { n: fmt(it.minutos, 0) }) : null].filter(Boolean).join(" · ");
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
    : f.listo ? [DS.tarjeta({}, DS.estadoVacio({ arte: ARTE.personas(), titulo: T("sitio.gr.feed_vacio_t"), texto: T("sitio.gr.feed_vacio"), unaVez: "grupos",
      accion: { texto: T("sitio.gr.feed_vacio_acc"), href: ((ui().vacios || {}).grupos || {}).invitar || "/grupos" } }))]
    : error ? [DS.errorCarga({ titulo: T("sitio.gr.err_t"), texto: T("sitio.gr.feed_err"), detalle: error, onReintentar: () => feedRefrescar() })]
    : [DS.cargando(T("sitio.gr.cargando"))];
  sec.replaceChildren(h("h3", {}, T("sitio.gr.feed")), ...cuerpo.filter(Boolean));
  if (sec.isConnected) DS.animar.unaVez();   // el feed llega tarde; con la sección aún suelta, lo que está en la página es lo viejo y gastaría la animación
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
  DS.animar.unaVez();
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
document.addEventListener("visibilitychange", () => { if (!document.hidden && $("app")) juntosRevisar(); });

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

/** Sin ningún grupo: solo el estado vacío. */
function pintarSinGrupos() {
  const v = (ui().vacios || {}).grupos || {};
  $("vista-grupo").replaceChildren(DS.tarjeta({ clase: "ancha" }, DS.estadoVacio({ arte: ARTE.personas({ libres: true }), titulo: T("sitio.gr.sin_t"),
    texto: T("sitio.gr.sin_x"), unaVez: "grupos", accion: { texto: T("sitio.gr.sin_acc"), href: v.crear || "/grupos/nuevo" } })));
}

/** Entrar a la pestaña: pinta la caché al instante (sin cargador) y refresca en silencio; sin caché, baja con cargador.
 *  Con 0 grupos no se pide nada (ni lista, ni feed, ni «visto»). */
async function cargarGrupo(id) {
  const turno = ++grupoTurno, raiz = $("vista-grupo");
  if (!(nGrupos() > 0)) { pintarSinGrupos(); return; }
  if (!id) juntosVisto();
  let pintado = grupoPintarCache(id);
  const antes = pintado ? JSON.stringify([grupoCache.lista, id ? grupoCache.grupos[id] : null]) : "";
  try {
    if (!pintado) {
      raiz.replaceChildren(DS.cargando(T("sitio.gr.cargando"), { pagina: true }));   // al centro de la pantalla: en la vista de 2 columnas caería solo a la izquierda
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

/** Minutos o km de carrera por semana del perfil: todas las semanas (con ceros), la actual marcada; el selector solo cambia qué valor se pinta. */
function graficaPersona(semanas, periodos) {
  const caja = h("div", { class: "pers-graf" });
  const ops = periodos && periodos.length ? periodos : [4, 8, 12].map((n) => ({ n, todo: false }));
  let sel = ops.some((p) => p.n === 8 && !p.todo) ? 8 : ops[0].n, todo = false;   // altura fija: elegir solo cambia las barras
  const selector = h("div", {});
  const pintar = () => {
    const km = unidad === "km";
    const ven = ventanaSemanas(semanas, ops, sel, todo);
    caja.replaceChildren(DS.graficaBarras({ alto: 120, clases: ["s1"], etiqueta: T(km ? "sitio.gr.p.graf_km" : "sitio.gr.p.graf", { n: ven.length }),
      semanas: ven.map((w) => ({ inicio: w.inicio, actual: w.actual, valores: [(km ? w.km : w.minutos) || 0] })),
      texto: (w) => (km ? T("sitio.gr.p.graf_tip_km", { fecha: fechaCorta(w.inicio), km: fmt(w.valores[0], 1) }) : T("sitio.gr.p.graf_tip", { fecha: fechaCorta(w.inicio), min: fmt(w.valores[0], 0) })) }));
  };
  const pintarSel = () => selector.replaceChildren(DS.segmento({ etiqueta: T("sitio.prog.periodo"), modo: "grupo", activo: todo ? "todo" : sel,
    opciones: ops.map((p) => ({ id: p.todo ? "todo" : p.n, texto: p.todo ? T("sitio.prog.todo") : T("sitio.prog.n_sem", { n: p.n }) })),
    onCambio: (id) => { todo = id === "todo"; if (!todo) sel = Number(id); pintarSel(); pintar(); } }));
  REPINTAR_UNIDAD.push({ conectado: () => caja.isConnected, pintar });
  pintarSel();
  pintar();
  return h("div", {}, selectorUnidad(), selector, caja);
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
    // El plan: el mismo bloque de la pestaña Plan (sin días de la semana: no los asignamos), con lo que su dueña comparte
    if (p.plan) partes.push(tarjetaPlan(p.plan, { titulo: T("sitio.gr.p.plan_n", { n: p.plan.largo || (p.plan.semanas || []).length }), clase: "pers-sec ancha" }));
    // Progreso
    const pr = p.progreso;
    partes.push(sec(T("sitio.gr.p.prog_t"),
      pr && pr.semanas.length ? graficaPersona(pr.semanas, pr.periodos) : oculto("sitio.gr.p.sin_datos"),
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
  raiz.replaceChildren(DS.cargando(T("sitio.gr.p.cargando"), { pagina: true }));
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
