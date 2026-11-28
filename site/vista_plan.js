// Vista Plan: tipos de sesión, el bloque de semanas, repetir/retomar. Usa lo de vista_comun.js.
// --- Plan ---

/** Tarjetita del catálogo: silueta en tinta (sin color ni tooltip), nombre y descripción. */
function tipoCard(t, enPlan) {
  return h("div", { class: "tipo" }, siluetaForma(t.forma, 48, T("sitio.tipo.forma", { n: t.nombre })),
    enPlan ? h("div", {}, DS.chip(T("sitio.tipo.en_plan"), "suave")) : null, h("h3", {}, t.nombre), h("p", {}, t.descripcion));
}

function tarjetaTipos(d) {
  const tp = d.tipos;
  if (!tp || !(tp.catalogo || []).length) return null;
  const enPlan = new Set(tp.en_plan || []);
  const nombreGrupo = Object.fromEntries((tp.grupos || []).map((g) => [g.id, g.nombre]));
  const c = DS.tarjeta({ titulo: T("sitio.tipo.titulo"), clase: "ancha" },
    h("p", { class: "nota" }, T("sitio.tipo.nota")));
  const suyos = tp.catalogo.filter((t) => enPlan.has(t.id));
  if (suyos.length) c.append(h("div", { class: "tipos" }, suyos.map((t) => tipoCard(t, true))));
  const resto = tp.catalogo.filter((t) => !enPlan.has(t.id));
  if (resto.length) {
    const det = DS.desplegable({ titulo: T(suyos.length ? "sitio.tipo.ver_todos" : "sitio.tipo.ver"), liga: true, clase: "todos-tipos" });
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
  if (ui().sin_plan) {   // sin plan: la pestaña no existe, pero la ruta #plan puede abrirse a mano
    const espera = !!(ui().sync || {}).historial_pendiente;   // sin historial aún: el botón de armar el plan espera (misma ranura)
    const accion = (ui().menu || []).length ? (espera ? { texto: T("sitio.sync.espera"), deshabilitado: true } : { texto: T("sitio.sl.quiero"), href: "/plan/nuevo" }) : null;
    $("vista-plan").replaceChildren(DS.tarjeta({ titulo: T("sitio.sl.sin_plan_t") }, DS.estadoVacio({ icono: null, titulo: T("sitio.sl.sin_plan_t"), texto: T("sitio.sl.sin_plan_x"), accion })));
    return;
  }
  $("vista-plan").replaceChildren(...[
    recordatorioCorrida(),
    guardado ? DS.aviso({ clase: "ok", simbolo: "✔", titulo: T("sitio.plan.listo"), texto: T("sitio.plan.guardado") }) : null,
    acciones.length ? h("div", { class: "botones ancha" }, acciones.map((a) => DS.boton(a.texto, { variante: "sec", href: a.url }))) : null,
    ui().plan_url ? h("div", { class: "botones ancha" }, DS.boton(T("sitio.plan.ajustar"), { variante: "sec", href: ui().plan_url })) : null,
    botonRepetirRetomar(),
    tarjetaDoceSemanas(d),
    tarjetaTipos(d),
    tarjetaFcMax(d),
    (ui().avisos || {}).zonas_garmin ? avisoCerrable("zonas_garmin", { clase: "warn", simbolo: "!", extra: "ancha", titulo: T("sitio.zonas.sugerir_t"), texto: T("sitio.zonas.sugerir") }) : null,
    det.distribucion ? zonaBar(det.distribucion) : null].filter(Boolean));
}

/** Líneas del «?» de las 12 semanas: cada una con su muestra dibujada con las mismas piezas que los cuadritos reales. */
function ayudaSemanas() {
  const mini = (c) => h("span", { class: `mini-sem ${c}` });
  const ev = (k) => h("span", { class: "sem-ev", "data-ev": k }, DS.ico(ICONO_MARCA[k]));
  const marca = (c, t) => h("span", { class: "sem-prog", "data-cump": c }, t);
  return [
    [[mini("")], "carga"], [[mini("desc")], "desc"],
    [["anillo-actual", "anillo-carrera", "anillo-prueba"].map((c) => mini(c)), "anillos"],
    [["carrera", "prueba", "viaje", "enfermedad"].map(ev), "iconos"],
    [[marca("completa", "✓✓"), marca("casi", "✓"), marca("baja", "–")], "marcas"],
  ].map(([m, k]) => DS.filaMuestra(m, T(`sitio.plan.ayuda_${k}`)));
}

/**
 * El bloque del plan de cualquier largo (8, 12, 16 semanas…): lo usan la pestaña Plan y el perfil de otra persona, con el mismo `plan` de Python
 * (en el perfil, ya filtrado en el servidor). Recibe el plan y opciones: { editarUrls ({"n/id": url}; sin ligas, solo lectura), textoDescarga,
 * sel (semana abierta al inicio), alElegir (n), titulo, clase }. No lee nada global del sitio, así vale en ambos lados.
 */
function tarjetaPlan(plan, { editarUrls = {}, textoDescarga = "", sel = null, alElegir = null, titulo = null, clase = "ancha" } = {}) {
  const semanas = (plan || {}).semanas || [];
  const largo = plan.largo || semanas.length;
  const ayuda = DS.dialogo({ titulo: T("sitio.plan.ayuda_t", { n: largo }), cuerpo: ayudaSemanas() });
  const c = DS.tarjeta({ titulo: [titulo || T("sitio.plan.n_sem", { n: largo }), DS.botonIco("ayuda", T("sitio.plan.ayuda_btn"), { onclick: () => ayuda.showModal() })], clase }, ayuda);
  if (!semanas.length) { c.append(DS.estadoVacio({ icono: null, titulo: T("sitio.plan.sin_plan") })); return c; }
  const actual = plan.semana_actual ?? null;
  if (sel === null || !semanas.some((w) => w.n === sel)) sel = actual ?? semanas[0].n;
  const w = semanas.find((x) => x.n === sel);
  const bloques = plan.bloques || [...new Set(semanas.map((x) => x.block))];
  const vols = [];
  const linea = h("div", { class: "linea" });
  for (const bloque of bloques) {
    const del = semanas.filter((x) => x.block === bloque);
    if (!del.length) continue;
    linea.append(h("div", { class: "bloque" }, h("div", { class: "nota" }, T("sitio.plan.bloque", { n: bloque })),
      h("div", { class: "semanas" }, del.map((x) => {
        const vol = h("span", { class: "sem-vol", "aria-hidden": "true" }, textoVolumen(x) || " ");
        vols.push([vol, x]);
        return h("button", { type: "button", class: `sem ${x.kind === "descarga" ? "desc" : ""} ${x.n === actual ? "actual" : ""} ${anilloSemana(x, actual)}`,
          "aria-pressed": x.n === sel ? "true" : "false",
          "aria-label": T("sitio.plan.aria", { n: x.n, e: etiquetaSemana(x), act: (x.n === actual ? T("sitio.plan.act_aria") : "") + textoMarca(x) }),
          onclick: () => { if (alElegir) alElegir(x.n); const n = tarjetaPlan(plan, { editarUrls, textoDescarga, sel: x.n, alElegir, titulo, clase }); c.replaceWith(n); const b = n.querySelector('.sem[aria-pressed="true"]'); if (b) b.focus({ preventScroll: true }); } },
          x.n === actual ? h("em", {}, T("sitio.plan.actual")) : null,
          h("span", { class: "sem-cab" }, h("strong", {}, x.n),
            iconosSemana(x).map((k) => DS.burbuja(h("span", { class: "sem-ev", "data-ev": k }, DS.ico(ICONO_MARCA[k])), textoBurbuja(x, k)))),
          h("span", {}, tipoSemana(x.etiqueta || x.kind)),
          marcaProgreso(x, actual), vol);
      }))));
  }
  const est = actual === w.n ? plan.estado_sesiones ?? [] : w.estados ?? [];   // el estado de cada semana lo calcula Python
  const filas = h("div", { class: "filas" }, (w.sessions || []).map((s) => filaSesion(s, est.find((e) => e.id === s.id), editarUrls[`${w.n}/${s.id}`]
    ? { cuerpo: [...cuerpoPlan(s), DS.boton(T("sitio.plan.editar"), { variante: "sec", chico: true, href: editarUrls[`${w.n}/${s.id}`] })] } : {})));
  const textoSesion = (s) => (unidad === "km" && s.km_est != null ? T("sitio.plan.vol_km_est", { k: fmt(s.km_est, 1) }) : T("sitio.min_n", { n: s.minutes }));
  const pintarSesiones = () => filas.querySelectorAll(".fila-ses").forEach((f, i) => { const sm = f.querySelector(".fs-n small"); if (sm && w.sessions[i]) sm.textContent = `· ${textoSesion(w.sessions[i])}`; });
  pintarSesiones();   // la unidad ya puede ser km al abrir (p. ej. el perfil de otra persona): las filas nacen en minutos
  REPINTAR_UNIDAD.push({ conectado: () => c.isConnected, pintar: () => { vols.forEach(([v, x]) => { v.textContent = textoVolumen(x) || " "; }); pintarSesiones(); } });
  c.append(h("div", { class: "unidad-fila" }, selectorUnidad(), h("p", { class: "nota" }, T("sitio.u.nota"))), linea,
    h("p", { class: "nota" }, T("sitio.plan.nota", { d: textoDescarga || T("sitio.plan.descarga_nota") })),
    h("h3", { class: "titular" }, T("sitio.plan.titulo_sem", { n: w.n, b: w.block, k: tipoSemana(w.kind) })),
    h("p", { class: "nota" }, w.focus || ""),
    ...(actual === w.n && plan.faltan ? [h("p", { class: "nota" }, plan.faltan)] : []),
    filas,
    ...((plan.semanas_repetidas || []).length ? [h("p", { class: "nota" }, T("sitio.plan.repetidas", { l: plan.semanas_repetidas.join(", ") }))] : []),
    ...listaEventos(plan.eventos));
  pintarSesiones();
  return c;
}

/** La tarjeta de la pestaña Plan: el bloque con las opciones propias de quien lo ve (ligas de editar, texto de descarga, semana elegida). */
const tarjetaDoceSemanas = (d) => tarjetaPlan(d.plan || {}, { editarUrls: ui().editar_urls || {}, textoDescarga: (ui().textos || {}).descarga, sel: planSel, alElegir: (n) => { planSel = n; } });

/** «Repetir o retomar»: diálogo con las opciones; al elegir una pide la propuesta al servidor y la pinta con la misma tarjeta del plan. `inicial`
 *  ({accion, semana}) salta directo a la vista previa. «Sí, aplicar» manda el POST (con CSRF) y recarga; «No» cierra. Python decide todo. */
function abrirRepetirRetomar(inicial = null) {
  const u = ui(), app = $("app");
  if (!u.propuesta_url) return;
  const d = DS.dialogo({ titulo: T("sitio.plan.rr_titulo"), cuerpo: [] });
  const cuerpo = d.querySelector(".dl-cuerpo");
  d.addEventListener("close", () => d.remove());
  const error = (txt) => cuerpo.replaceChildren(h("p", { class: "nota", role: "alert" }, txt), DS.boton(T("sitio.plan.rr_no"), { variante: "sec", onclick: () => d.close() }));
  const aplicar = async (a) => {
    try {
      const body = new URLSearchParams({ csrf: app.dataset.csrf });
      if (a.semana != null) body.set("semana", String(a.semana));
      const r = await fetch(a.url, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" }, body });
      if (r.ok) location.reload(); else error(T("sitio.plan.rr_error"));
    } catch (e) { error(T("sitio.plan.rr_error")); }
  };
  const previa = async (accion, semana) => {
    cuerpo.replaceChildren(h("p", { class: "nota" }, T("sitio.plan.rr_cargando")));
    try {
      const q = new URLSearchParams({ accion, ...(semana != null ? { semana: String(semana) } : {}) });
      const r = await fetch(`${u.propuesta_url}?${q}`, { headers: { Accept: "application/json" } });
      const resp = await r.json();
      if (!r.ok) return error(resp.error || T("sitio.plan.rr_error"));
      const fin = resp.info && resp.info.fin ? fechaLarga(resp.info.fin) : null;
      cuerpo.replaceChildren(
        ...(resp.aviso ? [DS.aviso({ clase: "warn", simbolo: "!", texto: resp.aviso })] : []),
        ...(fin ? [h("p", { class: "nota" }, T("sitio.plan.rr_fin", { f: fin }))] : []),
        tarjetaPlan(resp.plan, { titulo: T("sitio.plan.rr_propuesta"), sel: resp.plan.semana_actual ?? null, clase: "" }),
        h("div", { class: "botones" }, DS.boton(T("sitio.plan.rr_aplicar"), { onclick: () => aplicar(resp.aplicar) }),
          DS.boton(T("sitio.plan.rr_no"), { variante: "sec", onclick: () => d.close() })));
    } catch (e) { error(T("sitio.plan.rr_error")); }
  };
  const actual = ((datos && datos.plan) || {}).semana_actual;
  cuerpo.replaceChildren(
    DS.boton(T("sitio.plan.rr_repetir", { n: actual ?? "" }), { variante: "sec", onclick: () => previa("repetir") }),
    ...((u.retomar_opciones || []).length ? [h("p", { class: "nota" }, T("sitio.plan.rr_retomar_t")),
      h("div", { class: "botones" }, u.retomar_opciones.map((o) => DS.boton(T("sitio.plan.rr_retomar", { n: o.semana, d: fechaLarga(o.desde), h: fechaLarga(o.hasta) }),
        { variante: "sec", onclick: () => previa("retomar", o.semana) })))] : []));
  document.body.append(d);
  d.showModal();
  if (inicial) previa(inicial.accion, inicial.semana);
}

/** La tarjeta de la pestaña Plan: botón «Repetir o retomar» (solo si el servidor dio `propuesta_url`) y el bloque de semanas. */
const botonRepetirRetomar = () => (ui().propuesta_url && $("app").dataset.csrf
  ? h("div", { class: "botones ancha" }, DS.boton(T("sitio.plan.rr_boton"), { variante: "sec", onclick: () => abrirRepetirRetomar() })) : null);

const nombreEvento = (t) => (["viaje", "enfermedad", "lesion", "carrera"].includes(t) ? T(`sitio.ev.${t}`) : t);
const tipoSemana = (k) => (k === "descarga" || k === "carga" ? T(`sitio.plan.${k}`) : k);
/** `etiqueta` es carga o descarga; `marca` (carrera, viaje, enfermedad, prueba) pone el ícono de la esquina: los textos salen del catálogo. */
const etiquetaSemana = (x) => tipoSemana(x.etiqueta || x.kind) + (x.marca ? `, ${T(`sitio.plan.et_${x.marca}`)}` : "");
/** Anillo exterior de la semana: carrera (rojo) gana a prueba (morado) y a la semana actual (azul); viaje y enfermedad no llevan. */
const anilloSemana = (x, actual) => (x.marca === "carrera" ? "anillo-carrera" : x.marca === "prueba" ? "anillo-prueba" : x.n === actual ? "anillo-actual" : "");
/** Íconos junto al número: el evento principal (`marca`) y, si hay otro, el de `marcas` (en orden de prioridad). */
const iconosSemana = (x) => [...new Set([x.marca, ...(x.marcas || [])].filter(Boolean))];
/** Texto accesible de la marca de avance (el mismo que ve quien usa lector de pantalla). */
const textoMarca = (x) => (x.cumplimiento ? `, ${T(`sitio.plan.cump_${x.cumplimiento}`, x.progreso || {})}` : x.progreso ? T("sitio.plan.prog_aria", { h: x.progreso.hechas, t: x.progreso.total }) : "");
/** Ranura de avance: ✓✓ / ✓ verdes, «–» gris en las pasadas; hechas/total en la actual; vacía (misma altura) en las futuras. */
function marcaProgreso(x, actual) {
  const p = x.progreso;
  const simbolo = x.cumplimiento === "completa" ? "✓✓" : x.cumplimiento === "casi" ? "✓" : x.cumplimiento === "baja" ? "–" : x.n === actual && p ? `${p.hechas}/${p.total}` : "";
  return h("span", { class: "sem-prog", "data-cump": x.cumplimiento || null, "aria-hidden": "true" }, simbolo || " ");
}
/** Texto de la burbuja de un ícono: lo específico (fechas, prueba) sale de `marcas_det`; sin él, el nombre del evento. */
function textoBurbuja(x, k) {
  const dt = (x.marcas_det || {})[k] || {};
  const f = !dt.d ? "" : dt.h && dt.h !== dt.d ? `${fechaLarga(dt.d)} – ${fechaLarga(dt.h)}` : fechaLarga(dt.d);
  if (k === "prueba") return dt.n ? T("sitio.plan.bur_prueba_n", { n: dt.n }) : T("sitio.plan.bur_prueba");
  return f ? T(`sitio.plan.bur_${k}`, { f }) : T(`sitio.plan.et_${k}`);
}
const ICONO_MARCA = { carrera: "medalla", viaje: "avion", enfermedad: "termometro", prueba: "cronometro" };

/** Viajes, enfermedades y carreras con fecha (plan.eventos, solo en la web); nada si no hay. */
function listaEventos(eventos) {
  if (!(eventos || []).length) return [];
  return [h("h3", { class: "titular" }, T("sitio.ev.titulo")),
    ...eventos.map((e) => h("p", { class: "nota" },
      `${nombreEvento(e.tipo)}${e.nombre ? ` «${e.nombre}»` : ""} · ${e.desde}${e.hasta && e.hasta !== e.desde ? T("sitio.ev.al", { h: e.hasta }) : e.hasta ? "" : T("sitio.ev.sigue")}${e.distancia_km ? ` · ${e.distancia_km} km` : ""}`))];
}

/** Contexto del periodo elegido: corridas al aire libre dentro del periodo y el dominio del eje x. */
