// Dashboard: solo pinta lo que recibe de data.json (la lógica vive en dashboard/build.py).
const VISTAS = ["hoy", "semana", "plan", "tendencias", "mas"];
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

function pasoLi(p) {
  if (p.kind === "repeat") {
    return h("li", {}, h("span", { class: "min" }, `Repetir ${p.times}×`), h("ul", {}, p.steps.map(pasoLi)));
  }
  const z = p.zone;
  const color = z.startsWith("Z") ? `var(--z${z.slice(1, 2)})` : "var(--axis)";
  return h("li", {},
    h("span", { class: "min" }, `${p.minutes} min`),
    h("span", { class: "zchip" }, h("i", { style: `background:${color}`, "aria-hidden": "true" }), z),
    p.lpm ? h("span", { class: "lpm" }, `${p.lpm[0]}–${p.lpm[1]} lpm`) : null,
    h("span", { class: "nota" }, ETIQUETA_PASO[p.kind] || p.kind, p.note ? ` · ${p.note}` : ""));
}
const ETIQUETA_PASO = { warmup: "calentamiento", run: "trote", walk: "caminata", cooldown: "enfriamiento" };

function tarjetaHoy(d) {
  const t = d.hoy.tarjeta;
  const c = h("div", { class: "card" }, h("h2", {}, "Hoy"));
  if (t.tipo === "crossfit") {
    c.append(h("h3", {}, "Hoy es CrossFit"), h("p", { class: "nota" }, "Las corridas van en días sin CrossFit."));
  } else if (t.tipo === "hecha_hoy") {
    c.append(h("h3", {}, "Corrida de hoy hecha"), h("p", { class: "nota" }, "Buen trabajo. Descansa el resto del día."));
  } else if (t.tipo === "sin_plan") {
    const inicio = d.plan.inicio;
    c.append(h("h3", {}, `El plan arranca el ${fechaCorta(inicio)}`),
      h("p", { class: "nota" }, "Mientras tanto, el semáforo ya muestra cómo amaneciste."));
  } else if (t.tipo === "completa") {
    c.append(h("h3", {}, "Semana completa, descansa"), h("p", { class: "nota" }, "Ya hiciste las 2 corridas de la semana."));
  } else if (t.tipo === "sesion") {
    c.append(...tarjetaSesion(t));
  } else {
    c.append(h("p", {}, t.texto));
  }
  return c;
}

function tarjetaSesion(t) {
  const s = t.sesion;
  if (t.version === "descanso") {
    return [h("h3", {}, "Hoy: descanso o caminata ligera"),
      h("p", { class: "nota" }, `La sesión ${t.sesion_id}${s ? ` (${s.name})` : ""} queda pendiente. Si la señal mejora, repónla otro día libre de esta semana.`)];
  }
  if (!s) return [h("h3", {}, t.texto)];
  const suave = t.version === "suave";
  const ses = suave ? s.easy : s;
  return [
    h("h3", {}, `${suave ? "Versión suave" : "Sesión normal"} · ${ses.name}`),
    h("p", { class: "nota" }, `Sesión ${s.id} · ${ses.minutes} min`),
    h("ul", { class: "pasos" }, ses.steps.map(pasoLi)),
  ];
}

function renderHoy(d) {
  const sem = d.hoy.semaforo, est = ESTADO_SEMAFORO[sem.color];
  const raiz = document.getElementById("vista-hoy");
  raiz.replaceChildren(...[
    h("div", { class: `semaforo ${sem.color}`, role: "group", "aria-label": `Semáforo ${est.titulo}` },
      badge(est.clase, est.icono, est.titulo),
      h("div", {}, h("div", { class: "titulo" }, est.titulo), h("div", {}, est.texto),
        h("div", { class: "nota" }, sem.fuera === 0 ? "Ninguna señal fuera de rango" : `${sem.fuera} señal${sem.fuera === 1 ? "" : "es"} fuera de rango`))),
    sem.repetir_semana
      ? h("div", { class: "aviso bad" }, badge("bad", "✕", "aviso"),
        h("div", {}, h("strong", {}, "Repetir la semana. "), "Dos días seguidos en rojo: repite la semana anterior del plan."))
      : null,
    d.aviso_zonas
      ? h("div", { class: "aviso warn" }, badge("warn", "!", "aviso"), h("div", {}, d.aviso_zonas))
      : null,
    tarjetaHoy(d),
    h("div", { class: "card" }, h("h2", {}, "Anoche y ayer"),
      h("ul", { class: "senales" }, d.hoy["señales"].map((s) =>
        h("li", {}, badgeSenal(s.estado),
          h("div", {}, h("div", { class: "nombre" }, NOMBRE_SENAL[s.id] || s.id), h("div", { class: "nota" }, s.texto))))))].filter(Boolean));
}

// --- vista Semana ---

const NOMBRE_TIPO = { crossfit: "CrossFit", corrida: "Corrida", descanso: "Descanso", hoy: "Hoy", futuro: "—" };
const GLIFO_TIPO = { crossfit: "◆", corrida: "●", descanso: "○", hoy: "▸", futuro: "·" };
const LUZ_BADGE = { verde: ["ok", "✓"], amarillo: ["warn", "!"], rojo: ["bad", "✕"] };

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
  wrap.append(tip, barra, brackets);
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

function renderSemana(d) {
  const s = d.semana;
  const hoyIso = (s.dias.find((x) => x.tipo === "hoy") || {}).fecha;
  document.getElementById("vista-semana").replaceChildren(
    h("div", { class: "card" }, h("h2", {}, "Esta semana (lun–dom)"), tira(s.dias, hoyIso),
      h("p", { class: "nota", style: "margin-top:10px" }, "Ícono bajo cada día: semáforo de ese día.")),
    h("div", { class: "card" }, h("h2", {}, "Corridas"),
      h("div", { class: "grande" }, `${s.corridas_hechas} de 2`),
      h("p", { class: "nota" }, s.corridas_hechas >= 2 ? "Semana de corridas completa" : "Las corridas van en días sin CrossFit; si falla una, repónla en esta misma semana.")),
    bloqueCarga(s),
    zonaBar(s.distribucion));
}

// --- arranque ---

function actualizarEncabezado() {
  const el = document.getElementById("actualizado");
  const iso = datos && (datos.datos_al || datos.generado);
  const hace = haceCuanto(iso);
  el.textContent = hace ? `Actualizado ${hace}` : "";
}

function mostrarVista() {
  const v = VISTAS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "hoy";
  for (const id of VISTAS) document.getElementById(`vista-${id}`).hidden = id !== v;
  for (const a of document.querySelectorAll(".tabs a")) {
    if (a.dataset.tab === v) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  }
  window.scrollTo(0, 0);
}

function error(msg) {
  document.getElementById("actualizado").textContent = "Sin datos";
  document.getElementById("vista-hoy").replaceChildren(h("p", { class: "vacio" }, msg));
}

async function iniciar() {
  window.addEventListener("hashchange", mostrarVista);
  mostrarVista();
  try {
    const resp = await fetch("data.json", { cache: "no-cache" });
    if (!resp.ok) throw new Error(resp.status);
    datos = await resp.json();
  } catch (e) {
    error("No se pudieron cargar los datos. Intenta de nuevo en unos minutos.");
    return;
  }
  actualizarEncabezado();
  setInterval(actualizarEncabezado, 60000);
  try {
    renderHoy(datos);
    renderSemana(datos);
  } catch (e) {
    error("Los datos tienen un formato inesperado.");
  }
}

iniciar();
