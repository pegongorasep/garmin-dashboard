// Piezas comunes de las vistas (tarjeta con vistas, unidad min/km). Se carga antes de vista_plan.js, vista_progreso.js, vista_grupo.js y vistas.js.
const $ = (id) => document.getElementById(id);

function fechaLarga(iso) {
  const f = parseFecha(iso);
  return `${DIAS_LARGO[f.getDay()].slice(0, 3)} ${f.getDate()} ${MESES[f.getMonth()]}`;
}

function horasMin(hh) {
  const min = Math.floor(hh * 60 + 1e-6);
  return T("sitio.h_min", { h: Math.floor(min / 60), m: String(min % 60).padStart(2, "0") });
}

/** «Ver como tabla»: desplegable con una tabla (la primera columna a la izquierda, las demás a la derecha). */
function tablaDatos(cabeza, filas, titulo = T("sitio.ver_tabla")) {
  return DS.desplegable({ titulo, liga: true }, DS.tabla({ etiqueta: titulo,
    columnas: cabeza.map((texto, i) => ({ texto, num: i > 0 })), filas: filas.map((celdas) => ({ celdas })) }));
}

/** Color CSS de cada clase de serie de las gráficas (para las leyendas). */
const COLOR_CLASE = { s1: "var(--serie-1)", s2: "var(--serie-2)", walk: "var(--caminata)", z1: "var(--z1)", z3: "var(--z3)", z4: "var(--z4)",
  azul: "var(--cat-1)", aqua: "var(--cat-2)", violeta: "var(--cat-3)", amarillo: "var(--cat-4)" };

// --- tarjeta con vistas ---

const SEL = {};   // vista elegida en cada tarjeta, solo en memoria

/**
 * Tarjeta que agrupa un tema con botones para cambiar de vista (en vez de tarjetas apiladas).
 * vistas: [{ etiqueta, pintar:(ancho)=>Node }]. Solo cambia el contenido de abajo. Devuelve la tarjeta y
 * registra su dibujo en PINTAR[vista] (las gráficas necesitan el ancho, que solo existe con la vista visible).
 */
function tarjetaConVistas(vista, titulo, resumen, vistas, opts = {}) {
  if (!(SEL[titulo] < vistas.length)) SEL[titulo] = 0;
  const cuerpo = h("div", { class: "vista-cuerpo", role: "tabpanel" });
  const pintar = () => {
    const ancho = cuerpo.clientWidth;
    if (ancho) cuerpo.replaceChildren(vistas[SEL[titulo]].pintar(ancho));
  };
  PINTAR[vista].push(pintar);
  return DS.tarjeta({ titulo, clase: opts.clase || "" }, resumen ? h("p", { class: "nota" }, resumen) : null,
    vistas.length > 1 ? DS.segmento({ etiqueta: titulo, opciones: vistas.map((v, i) => ({ id: i, texto: v.etiqueta })), activo: SEL[titulo],
      onCambio: (i) => { SEL[titulo] = Number(i); pintar(); } }) : null, cuerpo, ...(opts.pie || []));
}

// --- unidad de las gráficas y del bloque: min o km (solo cambia qué valor se pinta; Python manda los dos) ---
const UNIDADES = ["min", "km"];
let unidad = (() => { try { const u = localStorage.getItem("unidad"); return UNIDADES.includes(u) ? u : "min"; } catch (e) { return "min"; } })();
const REPINTAR_UNIDAD = [];   // cada pieza que muestra volumen se apunta aquí; las que ya no están en la página se sueltan

/** Cambia la unidad (se recuerda en este navegador) y repinta lo que depende de ella. */
function elegirUnidad(u) {
  if (!UNIDADES.includes(u) || u === unidad) return;
  unidad = u;
  try { localStorage.setItem("unidad", u); } catch (e) { /* sin almacenamiento: vale solo esta visita */ }
  for (let i = REPINTAR_UNIDAD.length - 1; i >= 0; i--) { if (REPINTAR_UNIDAD[i].conectado()) REPINTAR_UNIDAD[i].pintar(); else REPINTAR_UNIDAD.splice(i, 1); }
}

/** El selector min / km de la página; todos los selectores abiertos marcan siempre la unidad vigente. */
function selectorUnidad() {
  const caja = DS.selectorUnidad({ etiqueta: T("sitio.u.etiqueta"), activo: unidad, textos: { min: T("sitio.u.min"), km: T("sitio.u.km") }, onCambio: elegirUnidad });
  REPINTAR_UNIDAD.push({ conectado: () => caja.isConnected, pintar: () => caja.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.id === unidad))) });
  return caja;
}

/** Volumen de una semana del bloque en la unidad vigente. Del plan solo hay minutos; en km sale lo hecho o, en las futuras, el
 *  km estimado que manda Python (≈); sin estimado (sin corridas aún, o actividades ocultas) se queda en minutos. */
function textoVolumen(x) {
  const hecho = x.minutos != null;
  if (unidad === "km" && hecho) return T("sitio.plan.vol_km", { k: fmt(x.km || 0, 1) });
  if (unidad === "km" && x.plan_km != null) return T("sitio.plan.vol_km_est", { k: fmt(x.plan_km, 1) });
  if (hecho) return x.plan_min ? T("sitio.plan.vol_hp", { h: fmt(x.minutos, 0), p: x.plan_min }) : T("sitio.plan.vol_h", { h: fmt(x.minutos, 0) });
  return x.plan_min ? T("sitio.plan.vol_p", { p: x.plan_min }) : "";
}

