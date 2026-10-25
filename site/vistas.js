// Vistas Plan, Tendencias y Más, más el arranque.
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

// --- Plan ---

let planSel = null;

function estadoSesion(est) {
  if (!est) return null;
  if (est.estado === "pendiente") return h("span", { class: "estado" }, badge("nd", "—", "pendiente"), "Pendiente");
  if (est.ajustada) return h("span", { class: "estado" }, badge("warn", "!", "hecha y ajustada"), "Hecha · ajustada");
  return h("span", { class: "estado" }, badge("ok", "✓", "hecha"), "Hecha");
}

function tarjetaPlan(s, est) {
  return h("div", { class: "card" },
    h("div", { class: "fila" }, h("h3", {}, `Sesión ${s.id} · ${s.name}`), estadoSesion(est)),
    h("p", { class: "nota" }, `${s.minutes} min`),
    h("ul", { class: "pasos" }, (s.steps || []).map(pasoLi)),
    s.easy ? h("details", {}, h("summary", {}, `Versión suave · ${s.easy.name} (${s.easy.minutes} min)`),
      h("ul", { class: "pasos" }, (s.easy.steps || []).map(pasoLi))) : null,
    h("details", {}, h("summary", {}, "Cómo crearla en Garmin Connect"),
      h("p", { class: "nota", style: "margin-top:6px" },
        "Entrenamientos → Crear entrenamiento → Correr. Agrega un paso por línea (los grupos “N× ( … )” van como repetición). En cada paso elige duración en minutos y, como objetivo, “Alerta de FC” con el rango de lpm de arriba.")));
}

function renderPlan(d) {
  const raiz = $("vista-plan");
  const plan = d.plan || {};
  const semanas = plan.semanas ?? [];
  if (!semanas.length) { raiz.replaceChildren(h("p", { class: "vacio" }, "Aún no hay plan cargado.")); return; }
  const actual = plan.semana_actual ?? null;
  if (planSel === null || !semanas.some((w) => w.n === planSel)) planSel = actual ?? semanas[0].n;
  const w = semanas.find((x) => x.n === planSel);
  const proxima = actual === null && w.n === semanas[0].n;

  const linea = h("div", { class: "linea" });
  for (const bloque of [1, 2, 3]) {
    const del = semanas.filter((x) => x.block === bloque);
    if (!del.length) continue;
    linea.append(h("div", { class: "bloque" }, h("div", { class: "nota" }, `Bloque ${bloque}`),
      h("div", { class: "semanas" }, del.map((x) =>
        h("button", { type: "button", class: `sem ${x.kind === "descarga" ? "desc" : ""} ${x.n === actual ? "actual" : ""}`,
          "aria-pressed": x.n === planSel ? "true" : "false",
          "aria-label": `Semana ${x.n}, ${x.kind}${x.n === actual ? ", semana actual" : ""}`,
          onclick: () => { planSel = x.n; renderPlan(d); } },
          h("strong", {}, x.n), h("span", {}, x.kind === "descarga" ? "descarga" : "carga"), x.n === actual ? h("em", {}, "actual") : null)))));
  }
  const est = actual === w.n ? plan.estado_sesiones ?? [] : [];
  raiz.replaceChildren(
    h("div", { class: "card" }, h("h2", {}, proxima ? "Próxima semana" : actual === w.n ? "Semana actual" : "Semana del plan"),
      h("h3", {}, `Semana ${w.n} · bloque ${w.block} · ${w.kind}`),
      h("p", { class: "nota" }, w.focus || ""),
      proxima ? h("p", { class: "nota" }, `Arranca el ${fechaCorta(plan.inicio)}.`) : null,
      (plan.semanas_repetidas || []).length ? h("p", { class: "nota" }, `Semanas repetidas: ${plan.semanas_repetidas.join(", ")}.`) : null),
    ...(w.sessions || []).map((s) => tarjetaPlan(s, est.find((e) => e.id === s.id))),
    h("div", { class: "card" }, h("h2", {}, "12 semanas"), linea,
      h("p", { class: "nota" }, "Las semanas de descarga (línea punteada) son todo continuo en Z1–Z2. Toca una semana para ver sus sesiones.")));
}

// --- Tendencias ---

let periodo = 8;
const TEND = {};

function renderTendencias(d) {
  const raiz = $("vista-tendencias");
  const tend = d.tendencias || {};
  if (!(tend.dias || []).length && !(tend.semanas || []).length) {
    raiz.replaceChildren(h("p", { class: "vacio" }, "Aún no hay datos para las tendencias."));
    return;
  }
  const boton = (n) => h("button", { type: "button", "aria-pressed": n === periodo ? "true" : "false",
    onclick: () => { periodo = n; renderTendencias(d); dibujarTendencias(); } }, `${n} semanas`);
  const tarjeta = (id, titulo) => {
    TEND[id] = { sub: h("p", { class: "nota" }), chart: h("div", { class: "chart-wrap" }), extra: h("div", {}) };
    return h("div", { class: "card" }, h("h2", {}, titulo), TEND[id].sub, TEND[id].chart, TEND[id].extra);
  };
  raiz.replaceChildren(
    h("div", { class: "toggle", role: "group", "aria-label": "Periodo" }, [4, 8, 12].map(boton)),
    tarjeta("hrv", "HRV nocturna"), tarjeta("rhr", "FC en reposo"), tarjeta("sueno", "Sueño"), tarjeta("carga", "Carga semanal"));
}

function ultimoValor(serie) {
  for (let i = serie.length - 1; i >= 0; i--) if (serie[i].y != null) return serie[i];
  return null;
}

function dibujarTendencias() {
  if (!TEND.hrv || !datos) return;
  const ancho = TEND.hrv.chart.clientWidth;
  if (!ancho) return;
  const tend = datos.tendencias || {};
  const dias = (tend.dias || []).slice(-periodo * 7);
  const semanas = (tend.semanas || []).slice(-periodo);
  const dominio = dias.length ? [parseFecha(dias[0].fecha).getTime(), parseFecha(dias[dias.length - 1].fecha).getTime()] : null;
  const umbral = (datos.umbrales || {}).sleep_min_hours;

  const linea = (id, serie, extra, unidad, resumen, tabla) => {
    const t = TEND[id];
    const ult = ultimoValor(serie);
    t.sub.textContent = ult ? resumen(ult) : "";
    t.chart.replaceChildren(lineChart({ ancho, serie, dominio, ...extra }));
    const filas = serie.filter((p) => p.y != null).reverse().map(tabla);
    t.extra.replaceChildren(filas.length ? tablaDatos(["Fecha", unidad], filas) : "");
  };
  linea("hrv", dias.map((x) => ({ fecha: x.fecha, y: x.hrv, lo: x.hrv_base_baja, hi: x.hrv_base_alta })), {
    banda: dias.map((x) => ({ lo: x.hrv_base_baja, hi: x.hrv_base_alta })), fmtY: (v) => fmt(v, 0), etiqueta: "HRV por noche con su rango base",
    texto: (p) => `${fechaLarga(p.fecha)} · ${fmt(p.y, 0)} ms${p.lo != null ? ` (base ${p.lo}–${p.hi})` : ""}`,
  }, "HRV (ms)", (p) => `Última: ${fmt(p.y, 0)} ms · ${fechaLarga(p.fecha)}. La banda es tu rango base.`, (p) => [fechaLarga(p.fecha), `${fmt(p.y, 0)}${p.lo != null ? ` (base ${p.lo}–${p.hi})` : ""}`]);
  linea("rhr", dias.map((x) => ({ fecha: x.fecha, y: x.rhr })), {
    fmtY: (v) => fmt(v, 0), etiqueta: "FC en reposo por día",
    texto: (p) => `${fechaLarga(p.fecha)} · ${fmt(p.y, 0)} lpm`,
  }, "FC reposo (lpm)", (p) => `Última: ${fmt(p.y, 0)} lpm · ${fechaLarga(p.fecha)}`, (p) => [fechaLarga(p.fecha), fmt(p.y, 0)]);
  linea("sueno", dias.map((x) => ({ fecha: x.fecha, y: x["sueño_h"] })), {
    ref: umbral != null ? { y: umbral, etiqueta: `mín ${fmt(umbral, 1)} h` } : null, fmtY: (v) => fmt(v, 1), etiqueta: "Horas de sueño por noche",
    texto: (p) => `${fechaLarga(p.fecha)} · ${horasMin(p.y)}`,
  }, "Sueño (h)", (p) => `Última noche: ${horasMin(p.y)} · ${fechaLarga(p.fecha)}`, (p) => [fechaLarga(p.fecha), horasMin(p.y)]);

  const c = TEND.carga;
  const sinRpe = semanas.filter((s) => s.sin_rpe > 0);
  c.sub.textContent = semanas.length ? "RPE × minutos por semana (lun–dom)." : "";
  const datosBarras = semanas.map((s) => ({ inicio: s.inicio, valores: [s.carga_crossfit || 0, s.carga_corrida || 0], sin_rpe: s.sin_rpe || 0 }));
  c.chart.replaceChildren(semanas.length ? barChart({
    ancho, semanas: datosBarras, etiqueta: "Carga semanal apilada",
    texto: (s) => `Semana del ${fechaLarga(s.inicio)} · CrossFit ${fmt(s.valores[0], 0)} · Corrida ${fmt(s.valores[1], 0)} · Total ${fmt(s.valores[0] + s.valores[1], 0)}${s.sin_rpe ? ` · ${s.sin_rpe} sin RPE` : ""}`,
  }) : h("p", { class: "vacio" }, "Sin semanas en este periodo."));
  c.extra.replaceChildren(
    semanas.length ? leyenda([["sw s1", "CrossFit"], ["sw s2", "Corrida"]]) : "",
    sinRpe.length ? h("p", { class: "nota" }, `* ${sinRpe.length === 1 ? "Una semana tiene" : `${sinRpe.length} semanas tienen`} sesiones sin RPE: la carga real es mayor.`) : "",
    semanas.length ? tablaDatos(["Semana", "CrossFit", "Corrida", "Sin RPE"], datosBarras.slice().reverse().map((s) => [fechaLarga(s.inicio), fmt(s.valores[0], 0), fmt(s.valores[1], 0), s.sin_rpe])) : "");
}

// --- Más ---

const MAS = {};

function tarjetaCorridas(corridas) {
  const orden = corridas.slice().sort((a, b) => b.fecha.localeCompare(a.fecha));
  MAS.efic = { sub: h("p", { class: "nota" }, "Metros por minuto por latido; si sube a la misma FC, mejora tu base. Solo corridas al aire libre."), chart: h("div", { class: "chart-wrap" }) };
  return [
    h("div", { class: "card" }, h("h2", {}, "Corridas"),
      orden.length ? h("div", { class: "tabla-scroll" }, h("table", {},
        h("thead", {}, h("tr", {}, ["Fecha", "Min", "FC prom", "% Z1–Z2", "Efic."].map((c) => h("th", {}, c)))),
        h("tbody", {}, orden.map((r) => h("tr", {}, h("td", {}, fechaLarga(r.fecha)), h("td", {}, fmt(r.minutos, 0)), h("td", {}, fmt(r.fc_prom, 0)),
          h("td", {}, r.pct_z1z2 == null ? "—" : `${fmt(r.pct_z1z2, 0)} %`), h("td", {}, r.eficiencia == null ? "—" : fmt(r.eficiencia, 2))))))) : h("p", { class: "vacio" }, "Aún no hay corridas registradas.")),
    h("div", { class: "card" }, h("h2", {}, "Eficiencia aeróbica"), MAS.efic.sub, MAS.efic.chart),
  ];
}

function tarjetaFcMax(d) {
  const f = d.fc_max || {};
  const ses = f.sesiones || [];
  const faltan = Math.max(0, 2 - (f.semanas_medidas || 0));
  const cuerpo = !ses.length
    ? [h("p", { class: "nota" }, "Aún no hay clases de CrossFit medidas con correa. Con 2 semanas de mediciones se calcula la FC máx definitiva.")]
    : [h("div", { class: "kv" }, h("span", {}, "Clases medidas"), h("span", {}, ses.length)),
      h("div", { class: "kv" }, h("span", {}, "Pico"), h("span", {}, `${fmt(f.pico, 0)} lpm`)),
      h("div", { class: "kv" }, h("span", {}, "FC máx estimada (pico + 3, mín 183)"), h("span", {}, `${fmt(f.estimacion, 0)} lpm`)),
      h("p", { class: "estado" }, f.listo ? badge("ok", "✓", "listo") : badge("nd", "—", "en curso"),
        f.listo ? "Lista para actualizar la FC máx" : `Faltan ${faltan} ${faltan === 1 ? "semana" : "semanas"} de medición`),
      f.revisar ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, "La estimación pasa de 200 lpm: revísala antes de usarla.")) : null];
  const zonas = d.zonas || [];
  return h("div", { class: "card" }, h("h2", {}, "FC máxima y zonas"), ...cuerpo,
    zonas.length ? h("div", {}, h("p", { class: "nota", style: "margin-top:10px" }, `FC máx en uso: ${fmt(f.config, 0)} lpm · reposo promedio 7 días: ${fmt(d.rhr_promedio_7d, 0)} lpm (Karvonen)`),
      h("table", {}, h("thead", {}, h("tr", {}, ["Zona", "Rango (lpm)"].map((c) => h("th", {}, c)))),
        h("tbody", {}, zonas.map((z) => h("tr", {}, h("td", {}, h("span", { class: "zchip" }, h("i", { style: `background:var(--${z.zona.toLowerCase()})`, "aria-hidden": "true" }), z.zona)), h("td", {}, `${z.piso}–${z.techo}`)))))) : h("p", { class: "vacio" }, "Sin zonas calculadas."));
}

function tarjetaComoFunciona(d) {
  const u = d.umbrales || {};
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
      li(badge("bad", "✕", "rojo"), " Rojo: dos o más señales fuera, o HRV baja → descanso o caminata ligera. Dos días rojos seguidos: repetir la semana.")),
    h("p", { class: "nota" }, "Una señal sin dato no cuenta como fuera. Las zonas usan Karvonen (% de la reserva de FC)."),
    h("p", {}, h("a", { href: `${REPO_DOCS}REQUISITOS.md`, target: "_blank", rel: "noopener" }, "Requisitos"), " · ",
      h("a", { href: `${REPO_DOCS}PLAN_ENTRENAMIENTO.md`, target: "_blank", rel: "noopener" }, "Plan de entrenamiento")));
}

function renderMas(d) {
  $("vista-mas").replaceChildren(...tarjetaCorridas(d.corridas || []), tarjetaFcMax(d), tarjetaComoFunciona(d));
}

function dibujarMas() {
  if (!MAS.efic || !datos) return;
  const ancho = MAS.efic.chart.clientWidth;
  if (!ancho) return;
  const pts = (datos.corridas || []).filter((r) => r.eficiencia != null).sort((a, b) => a.fecha.localeCompare(b.fecha));
  MAS.efic.chart.replaceChildren(pts.length
    ? lineChart({ ancho, serie: pts.map((r) => ({ fecha: r.fecha, y: r.eficiencia, fc: r.fc_prom })), marcadores: true, fmtY: (v) => fmt(v, 2),
      etiqueta: "Eficiencia aeróbica por corrida", texto: (p) => `${fechaLarga(p.fecha)} · ${fmt(p.y, 2)} m/min por lpm${p.fc ? ` (FC ${fmt(p.fc, 0)})` : ""}` })
    : h("p", { class: "vacio" }, "Aún no hay corridas al aire libre con FC."));
}

// --- arranque ---

const REDIBUJAR = { tendencias: dibujarTendencias, mas: dibujarMas };

function actualizarEncabezado() {
  const iso = datos && (datos.datos_al || datos.generado);
  const hace = haceCuanto(iso);
  $("actualizado").textContent = hace ? `Actualizado ${hace}` : "";
}

function mostrarVista() {
  const v = VISTAS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "hoy";
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
  const vistas = { hoy: renderHoy, semana: renderSemana, plan: renderPlan, tendencias: renderTendencias, mas: renderMas };
  for (const [id, fn] of Object.entries(vistas)) {
    try { fn(datos); } catch (e) { console.error(`Vista ${id}:`, e); aviso(id, "No se pudo mostrar esta sección con los datos actuales."); }
  }
  mostrarVista();
}

iniciar();
