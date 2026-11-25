// Componentes del sistema de diseño «Ahí la Llevas». Cada función arma el HTML con EXACTAMENTE las clases de su
// preview (componentes.css) y devuelve un nodo (o un fragmento). Solo pinta: lo que se muestra lo decide Python.
// Van colgadas de `DS` para no chocar con los nombres de app.js / vistas.js (aviso, badge, silueta…).
// Necesita base.js (h, sv, fmt), iconos.js (icono) y charts.js (lineChart, barChart, silueta…) cargados antes.
const DS = (() => {
  let _id = 0;
  const uid = (pre) => `${pre}-${++_id}`;

  /** Ícono del sistema (clase `ico`, el tamaño lo da el CSS). Recibe el nombre de iconos.js. */
  const ico = (nombre) => {
    const s = icono(nombre, 20);
    s.setAttribute("class", "ico");
    s.removeAttribute("width");
    s.removeAttribute("height");
    return s;
  };

  const BARRAS_LOGO = [[6, 38, 16, "var(--z1)"], [17, 30, 24, "var(--z2)"], [28, 22, 32, "var(--z3)"], [39, 15, 39, "var(--z4)"], [50, 8, 46, "var(--z5)"]];
  /** Logo de 5 barras con los colores de zona (--z1…--z5). Recibe una clase opcional para el SVG. */
  const logo = (clase) => sv("svg", { viewBox: "0 0 64 64", "aria-hidden": "true", class: clase || null },
    BARRAS_LOGO.map(([x, y, alto, fill]) => sv("rect", { x, y, width: 8, height: alto, rx: 4, fill })));

  const fragmento = (...hijos) => {
    const f = document.createDocumentFragment();
    f.append(...hijos.flat().filter((n) => n !== null && n !== undefined && n !== false));
    return f;
  };

  // ---------- marca y contenedores ----------

  /** Marca: logo + nombre. Recibe el nombre (por defecto «ahí la llevas»). */
  const marca = (nombre = "ahí la llevas") => h("span", { class: "marca" }, logo(), h("span", { class: "nombre" }, nombre));

  /** Tarjeta. Recibe { titulo, clase, tag } y los hijos; el título va en <h3 class="card-t">. */
  const tarjeta = ({ titulo, clase, tag = "section" } = {}, ...hijos) =>
    h(tag, { class: `card${clase ? ` ${clase}` : ""}` }, titulo ? h("h3", { class: "card-t" }, titulo) : null, ...hijos);

  /** Pie de página. Recibe { aviso, fuente, enlace: {texto, href} }. */
  const pie = ({ aviso = "Esto no es consejo médico: si algo duele, para.", fuente = "Datos de Garmin", enlace = { texto: "Aviso de privacidad", href: "/privacidad" } } = {}) =>
    h("footer", { class: "pie" }, h("p", {}, aviso),
      h("p", {}, fuente, enlace ? " · " : null, enlace ? h("a", { href: enlace.href }, enlace.texto) : null));

  /** Pantalla de carga: el logo se arma. Recibe la frase que va debajo. */
  const cargando = (frase = "Cargando…") => h("div", { class: "cargando", role: "status" }, logo(), h("p", { class: "frase" }, frase));

  /** Error de carga. Recibe { titulo, texto, detalle, onReintentar }. */
  const errorCarga = ({ titulo = "No pudimos cargar tus datos", texto = "", detalle = "", onReintentar } = {}) =>
    h("div", { class: "error-carga", role: "alert" }, logo("logo-quieto"), h("p", { class: "ec-t" }, titulo), h("p", { class: "ec-x" }, texto),
      h("button", { class: "boton", type: "button", onclick: onReintentar }, "Volver a intentar"),
      detalle ? h("details", {}, h("summary", {}, "Detalle"), h("code", {}, detalle)) : null);

  /** Estado vacío. Recibe { icono, titulo, texto, accion: {texto, href} }; se pone dentro de una tarjeta. */
  const estadoVacio = ({ icono: nombre = "punto", titulo, texto, accion } = {}) =>
    h("div", { class: "vacio" }, ico(nombre), h("p", { class: "vc-t" }, titulo), texto ? h("p", { class: "vc-x" }, texto) : null,
      accion ? h("a", { class: "boton", href: accion.href }, accion.texto) : null);

  /** Aviso con fondo. Recibe { clase: "warn"|"ok"|"bad", titulo, texto }. */
  const aviso = ({ clase = "warn", titulo, texto } = {}) =>
    h("div", { class: `aviso-fondo ${clase}`, role: "status" }, titulo ? h("div", { class: "b-t" }, titulo) : null, texto);

  /** Aviso del coach (cuando ves a otra persona). Recibe el nombre. */
  const avisoCoach = (nombre) => h("p", { class: "coach-aviso" }, insignia("warn", "!"), h("span", {}, "Estás viendo a ", h("b", {}, nombre), " como su coach."));

  /** Confirmación antes de borrar o perder datos. Recibe { titulo, texto, lista:[], nota, confirmar, cancelar, onConfirmar, onCancelar }. */
  const confirmacion = ({ titulo, texto, lista = [], nota, confirmar = "Sí, continuar", cancelar = "Cancelar", onConfirmar, onCancelar } = {}) => {
    const id = uid("cf");
    return h("div", { class: "confirmacion", role: "alertdialog", "aria-labelledby": id },
      h("p", { class: "cf-t", id }, insignia("bad", "!"), titulo),
      texto ? h("p", {}, texto) : null,
      lista.length ? h("ul", {}, lista.map((t) => h("li", {}, t))) : null,
      nota ? h("p", { class: "mu" }, nota) : null,
      h("div", { class: "botones" }, boton(confirmar, { variante: "peligro", onclick: onConfirmar }), boton(cancelar, { variante: "sec", onclick: onCancelar })));
  };

  /** Banner «alguien más cambió tu plan». Recibe { quien, texto, cuando, verHref, onDeshacer }. */
  const bannerCambio = ({ quien, texto, cuando, verHref = "#", onDeshacer } = {}) =>
    h("div", { class: "banner-cambio", role: "status" },
      h("span", { class: "bc-t" }, h("b", {}, quien), ` ${texto}${cuando ? ` · ${cuando}` : ""}`),
      h("span", { class: "bc-acc" }, h("a", { class: "boton texto chico", href: verHref }, "Ver"),
        boton("Deshacer", { variante: "sec", chico: true, ico: "deshacer", onclick: onDeshacer })));

  /** Lista de cambios del plan. Recibe [{ quien, cuando, origen, texto, nuevo, deshecho, onDeshacer }]. */
  const filaHistorial = (items = []) => h("ul", { class: "historial" }, items.map((it) =>
    h("li", { class: `${it.nuevo ? "nuevo" : ""}${it.deshecho ? " deshecho" : ""}`.trim() || null },
      h("p", { class: "fh-q" }, h("b", {}, it.quien), ` · ${it.cuando}`, it.origen ? " · " : null, it.origen ? chip(it.origen, "neutro") : null),
      h("p", { class: "fh-d" }, it.texto),
      it.deshecho ? null : boton("Deshacer", { variante: "sec", chico: true, ico: "deshacer", onclick: it.onDeshacer }))));

  // ---------- controles ----------

  /** Botón o liga con aspecto de botón. Recibe el texto y { variante: "sec"|"texto"|"peligro", chico, ico, cargando, deshabilitado, href, tipo, onclick }. */
  const boton = (texto, { variante, chico, ico: nombreIco, cargando: carg, deshabilitado, href, tipo = "button", onclick, ...resto } = {}) => {
    const clase = ["boton", variante, chico ? "chico" : null, carg ? "cargando" : null].filter(Boolean).join(" ");
    const hijos = [nombreIco ? ico(nombreIco) : null, texto];
    return href
      ? h("a", { class: clase, href, onclick, ...resto }, ...hijos)
      : h("button", { class: clase, type: tipo, disabled: !!deshabilitado, "aria-busy": carg ? "true" : null, onclick, ...resto }, ...hijos);
  };

  /** Botón redondo de solo ícono. Recibe el nombre del ícono, su etiqueta accesible y { onclick, expandido }. */
  const botonIco = (nombre, etiqueta, { onclick, expandido } = {}) =>
    h("button", { class: "boton-ico", type: "button", "aria-label": etiqueta, "aria-expanded": expandido === undefined ? null : String(expandido), onclick }, ico(nombre));

  /** Campo con etiqueta. Recibe { etiqueta, opcional, tipo, valor, opciones:[{valor,texto}|texto], ayuda, error, corto, deshabilitado, nombre, attrs }. */
  const campo = ({ etiqueta, opcional, tipo = "text", valor, opciones, ayuda, error, corto, deshabilitado, nombre, attrs = {} } = {}) => {
    const idErr = error ? uid("err") : null;
    const comunes = { name: nombre, disabled: !!deshabilitado, "aria-invalid": error ? "true" : null, "aria-describedby": idErr, ...attrs };
    const control = opciones
      ? h("select", comunes, opciones.map((o) => {
        const op = typeof o === "object" ? o : { valor: o, texto: o };
        return h("option", { value: op.valor, selected: String(op.valor) === String(valor) }, op.texto);
      }))
      : h("input", { type: tipo, value: valor, ...comunes });
    return h("label", { class: `campo${error ? " error" : ""}${corto ? " corto" : ""}` },
      h("span", { class: "campo-t" }, etiqueta, opcional ? " " : null, opcional ? h("small", {}, `(${opcional})`) : null),
      control,
      error ? h("span", { class: "error-t", id: idErr, role: "alert" }, insignia("bad", "✕"), error) : null,
      ayuda ? h("span", { class: "ayuda" }, ayuda) : null);
  };

  /** Casillas o radios. Recibe { titulo, pista, tipo: "checkbox"|"radio", nombre, items:[{texto, nota, marcado, deshabilitado, valor}] }. */
  const opciones = ({ titulo, pista, tipo = "checkbox", nombre, items = [] } = {}) =>
    h("fieldset", { class: "opciones" },
      h("legend", { class: "campo-t" }, titulo, pista ? " " : null, pista ? h("small", {}, pista) : null),
      items.map((it) => h("label", { class: "opcion" },
        h("input", { type: tipo, name: nombre, value: it.valor, checked: !!it.marcado, disabled: !!it.deshabilitado }),
        h("span", {}, it.texto, it.nota ? h("small", {}, it.nota) : null))));

  /** Chip de mayúsculas cortas. Recibe el texto y la variante ("suave"|"neutro"|"borde"; sin ella, el principal). */
  const chip = (texto, variante) => h("span", { class: `chip${variante ? ` ${variante}` : ""}` }, texto);

  /** Texto que se copia con un toque. Recibe { texto, etiqueta, aviso, copiado } (`copiado` = pintarlo ya en «Copiado»). */
  const copiar = ({ texto, etiqueta, aviso: etiquetaBoton = "Copiar código", copiado = false } = {}) => {
    const btn = h("button", { type: "button", class: copiado ? "listo" : null, "aria-label": copiado ? null : etiquetaBoton, "aria-live": copiado ? "polite" : null });
    const pintar = (listo) => {
      btn.className = listo ? "listo" : "";
      if (listo) btn.setAttribute("aria-live", "polite");
      btn.replaceChildren(ico(listo ? "check" : "copiar"), listo ? "Copiado" : "Copiar");
    };
    pintar(copiado);
    btn.addEventListener("click", () => {
      try { navigator.clipboard.writeText(texto).catch(() => {}); } catch (e) { /* sin portapapeles: igual avisa */ }
      pintar(true);
      setTimeout(() => pintar(false), 2000);
    });
    const caja = h("div", { class: "copiar" }, h("code", {}, texto), btn);
    return etiqueta ? h("label", { class: "campo" }, h("span", { class: "campo-t" }, etiqueta), caja) : caja;
  };

  /** Formulario en tarjeta. Recibe { secciones:[{leyenda, opciones:boolean, hijos:[]}], botones:[], onSubmit }. */
  const formulario = ({ secciones = [], botones = [], onSubmit } = {}) =>
    h("form", { class: "card formulario", onsubmit: onSubmit || ((ev) => ev.preventDefault()) },
      secciones.map((s) => h("fieldset", { class: s.opciones ? "opciones" : null }, s.leyenda ? h("legend", {}, s.leyenda) : null, ...s.hijos)),
      botones.length ? h("div", { class: "botones" }, ...botones) : null);

  /** Dos o más campos en una fila (se acomodan solos). Recibe los campos. */
  const filaCampos = (...campos) => h("div", { class: "fila-campos" }, ...campos);

  // ---------- estado ----------

  /** Insignia redonda de estado. Recibe la clase ("ok"|"warn"|"bad"|"nd"), el símbolo y, si va sola, su etiqueta accesible. */
  const insignia = (clase, simbolo, etiqueta) =>
    h("span", { class: `badge ${clase}`, role: etiqueta ? "img" : null, "aria-label": etiqueta || null }, simbolo);

  /** Línea de estado: insignia + texto. Recibe la clase, el símbolo y el texto. */
  const estado = (clase, simbolo, texto) => h("p", { class: "estado" }, insignia(clase, simbolo), texto);

  // ---------- navegación ----------

  /** Encabezado. Recibe { nombre, actualizado (texto o nodos), tema: "oscuro"|"claro", conAyuda, conMenu, menuAbierto, onAyuda, onTema, onMenu }. */
  const encabezado = ({ nombre, actualizado, tema = "oscuro", conAyuda = true, conMenu = false, menuAbierto = false, onAyuda, onTema, onMenu } = {}) =>
    h("header", { class: "encabezado" },
      h("div", { class: "encabezado-fila" }, marca(nombre),
        conAyuda ? botonIco("ayuda", "Ayuda", { onclick: onAyuda }) : null,
        botonIco(tema === "oscuro" ? "sol" : "luna", `Cambiar a tema ${tema === "oscuro" ? "claro" : "oscuro"}`, { onclick: onTema }),
        conMenu ? botonIco("menu", "Menú", { expandido: menuAbierto, onclick: onMenu }) : null),
      actualizado ? h("p", { class: "act" }, actualizado) : null);

  /** Menú del ☰. Recibe { quien, items:[{texto, icono, href, actual, onclick} | {separador:true}] } (sin href = botón). */
  const menu = ({ quien, items = [] } = {}) =>
    h("nav", { class: "menu", "aria-label": "Cuenta" }, quien ? h("p", { class: "menu-quien" }, quien) : null,
      items.map((it) => {
        if (it.separador) return h("hr");
        const hijos = [it.icono ? ico(it.icono) : null, it.texto];
        return it.href !== undefined
          ? h("a", { href: it.href, "aria-current": it.actual ? "page" : null, onclick: it.onclick }, ...hijos)
          : h("button", { type: "button", onclick: it.onclick }, ...hijos);
      }));

  /** Avance del onboarding. Recibe { pasos:[nombres], actual (índice desde 0), texto }. Devuelve la lista y su texto. */
  const pasos = ({ pasos: nombres = [], actual = 0, texto } = {}) => fragmento(
    h("ol", { class: "pasos", "aria-label": "Avance" }, nombres.map((n, i) =>
      h("li", { class: i < actual ? "hecho" : i === actual ? "actual" : null, "aria-current": i === actual ? "step" : null }, n))),
    texto ? h("p", { class: "pasos-t" }, texto) : null);

  /** Pestañas secundarias. Recibe { etiqueta, opciones:[{id, texto}], activo, modo: "tabs"|"grupo", onCambio(id) }. */
  const segmento = ({ etiqueta, opciones: ops = [], activo, modo = "tabs", onCambio } = {}) => {
    const tabs = modo === "tabs";
    const caja = h("div", { class: "segmento", role: tabs ? "tablist" : "group", "aria-label": etiqueta });
    const marcar = (id) => caja.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.id === String(id);
      b.setAttribute(tabs ? "aria-selected" : "aria-pressed", String(on));
    });
    caja.append(...ops.map((o) => h("button", { type: "button", role: tabs ? "tab" : null, "data-id": o.id,
      onclick: () => { marcar(o.id); if (onCambio) onCambio(o.id); } }, o.texto)));
    marcar(activo);
    return caja;
  };

  /** Abrir más detalle. Recibe { titulo, sub, abierto, liga (estilo «Ver pasos») } y los hijos. */
  const desplegable = ({ titulo, sub, abierto, liga } = {}, ...hijos) =>
    h("details", { class: `desplegable${liga ? " liga-d" : ""}`, open: !!abierto },
      h("summary", {}, titulo, sub ? " " : null, sub ? h("small", {}, `· ${sub}`) : null, ico("flecha-abajo")), ...hijos);

  // ---------- datos ----------

  /** Señales de recuperación. Recibe { estado:{clase,simbolo,titulo,texto}, senales:[{clase,simbolo,nombre,texto}], nota }. */
  const senales = ({ estado: est, senales: lista = [], nota } = {}) => fragmento(
    est ? h("p", { class: "estado" }, insignia(est.clase, est.simbolo), h("span", {}, h("b", {}, est.titulo), " ", est.texto ? h("span", { class: "mu" }, `· ${est.texto}`) : null)) : null,
    h("ul", { class: "senales" }, lista.map((s) => h("li", {}, insignia(s.clase, s.simbolo), h("div", {}, h("div", { class: "sn-n" }, s.nombre), h("div", { class: "sn-t" }, s.texto))))),
    nota ? h("p", { class: "nota" }, nota) : null);

  /** Tabla con scroll lateral. Recibe { etiqueta, columnas:[{texto, num}], filas:[{celdas:[texto | {t, clase}], destacada}] }. */
  const tabla = ({ etiqueta, columnas = [], filas = [] } = {}) =>
    h("div", { class: "tabla-scroll", tabindex: "0", role: "region", "aria-label": etiqueta },
      h("table", { class: "tabla" },
        h("thead", {}, h("tr", {}, columnas.map((c) => h("th", { class: c.num ? "num" : null }, c.texto)))),
        h("tbody", {}, filas.map((f) => h("tr", { class: f.destacada ? "destacada" : null }, f.celdas.map((c, i) => {
          const celda = typeof c === "object" && c !== null ? c : { t: c };
          return h("td", { class: [columnas[i] && columnas[i].num ? "num" : null, celda.clase].filter(Boolean).join(" ") || null }, celda.t);
        }))))));

  /** Mejores marcas y carreras. Recibe { marcas:[{icono, nombre, valor, fecha, nueva, etiqueta}], carreras:[{fecha, resumen, filas:[[k, v]], abierta}] }. */
  const ranking = ({ marcas = [], carreras = [] } = {}) => fragmento(
    h("div", { class: "marcas" }, marcas.map((m) =>
      h("div", { class: "marca-t", role: "group", "aria-label": m.etiqueta || `${m.nombre}: ${m.valor}, ${m.fecha}` },
        h("span", { class: "mt-n" }, ico(m.icono || "medalla"), m.nombre, m.nueva ? chip("NUEVO") : null),
        h("span", { class: "mt-v" }, m.valor), h("span", { class: "mt-f" }, m.fecha)))),
    carreras.length ? h("div", { class: "carreras" }, carreras.map((c) =>
      h("details", { class: "desplegable", open: !!c.abierta },
        h("summary", {}, ico("medalla"), c.fecha, h("span", { class: "cr-v" }, c.resumen), ico("flecha-abajo")),
        h("div", {}, (c.filas || []).map(([k, v]) => h("div", { class: "kv" }, h("span", {}, k), h("span", {}, v))))))) : null);

  /** Hoja InBody. Recibe { franja:[{texto, pct, normal}], filas:[{nombre, unidad, zona, textoZona, aria, normal:[izq, ancho], barra, valor, dentro, ticks:[[izq, texto]]}], puntuacion:{...}, visceral:{...} }. */
  const hojaInBody = ({ franja = [], filas = [], puntuacion, visceral } = {}) => fragmento(
    h("div", { class: "ib-grupo" },
      franja.length ? h("div", { class: "ib-franja", "aria-hidden": "true" }, franja.map((f) => h("span", { class: f.normal ? "normal" : null, style: `width:${f.pct}%` }, f.texto))) : null,
      filas.map((f) => h("div", { class: "ib-fila", role: "img", "aria-label": f.aria },
        h("div", { class: "ib-nombre" }, h("b", {}, f.nombre), h("small", {}, f.unidad), h("span", { class: `ib-zona ${f.zona}` }, f.textoZona)),
        h("div", { class: "ib-pista" }, h("i", { class: "ib-normal", style: `left:${f.normal[0]}%;width:${f.normal[1]}%` }),
          h("i", { class: "ib-barra", style: `width:${f.barra}%` }),
          h("span", { class: `ib-valor${f.dentro ? " dentro" : ""}`, style: `left:${f.barra}%` }, f.valor)),
        h("div", { class: "ib-ticks", "aria-hidden": "true" }, f.ticks.map(([izq, t]) => h("span", { style: `left:${izq}%` }, t)))))),
    puntuacion || visceral ? h("div", { class: "ib-punt" },
      puntuacion ? h("div", { class: "tile" }, h("span", { class: "k" }, "Puntuación InBody"),
        h("span", { class: "big" }, puntuacion.valor, h("small", {}, "/100")), puntuacion.delta ? h("span", { class: "delta" }, puntuacion.delta) : null) : null,
      visceral ? h("div", { class: "tile" }, h("span", { class: "k" }, "Grasa visceral"),
        h("span", { class: "big" }, visceral.valor, h("small", {}, ` · rango ${visceral.rango}`)), estado(visceral.clase, visceral.simbolo, visceral.texto)) : null) : null);

  /**
   * Sesión del plan, cerrada y que se abre. Recibe { nombre, minutos, hoy, abierta, estado:{clase,simbolo,texto},
   * silueta (nodo, p. ej. DS.silueta(...)), titulo (de la silueta), cuerpo:[nodos] (lo que se ve al abrir) }.
   */
  const filaSesion = ({ nombre, minutos, hoy, abierta, estado: est, silueta: sil, titulo, cuerpo = [] } = {}) =>
    h("details", { class: `fila-ses${hoy ? " hoy" : ""}`, open: !!abierta },
      h("summary", {},
        h("span", { class: "fs-n" }, hoy ? chip("HOY") : null, nombre, " ", h("small", {}, `· ${minutos} min`)),
        est ? h("span", { class: "estado" }, insignia(est.clase, est.simbolo), est.texto) : null,
        sil ? h("span", { class: "fs-sil" }, titulo ? h("span", { class: "titulo-sil" }, titulo) : null, sil) : null),
      cuerpo.length ? h("div", { class: "fs-cuerpo" }, ...cuerpo) : null);

  /** Barra de minutos trotando contra caminando. Recibe { trote, caminata, nota } en minutos. */
  const barraTroteCaminata = ({ trote = 0, caminata = 0, nota } = {}) => fragmento(
    h("div", { class: "barra-rw", role: "img", "aria-label": `Trote ${trote} min, caminata ${caminata} min` },
      h("i", { class: "trote", style: `flex:${trote} 1 0` }), h("i", { class: "camina", style: `flex:${caminata} 1 0` })),
    h("div", { class: "leyenda" }, h("span", {}, h("i", { class: "trote", "aria-hidden": "true" }), `Trote ${trote}′`),
      h("span", {}, h("i", { class: "camina", "aria-hidden": "true" }), `Caminata ${caminata}′`)),
    nota ? h("p", { class: "nota" }, nota) : null);

  // ---------- gráficas ----------

  /** Leyenda de colores. Recibe [[color CSS, texto]] (p. ej. ["var(--serie-1)", "Trote"]). */
  const leyenda = (items = []) => h("div", { class: "leyenda" }, items.map(([color, texto]) => h("span", {}, h("i", { style: `background:${color}` }), texto)));

  /** Contenedor que mide su ancho y vuelve a dibujar la gráfica al cambiarlo. `dibujar(ancho)` devuelve el nodo. */
  const conAncho = (dibujar) => {
    const cont = h("div", { class: "graf-w" });
    alAncho(cont, (w) => cont.replaceChildren(dibujar(w)));
    return cont;
  };

  /** Gráfica de línea con cruz y tooltip (envoltorio de lineChart). Recibe el cfg de lineChart sin `ancho`. */
  const graficaLinea = (cfg) => conAncho((ancho) => lineChart({ ...cfg, ancho }));

  /** Barras apiladas por semana (envoltorio de barChart). Recibe el cfg de barChart sin `ancho`. */
  const graficaBarras = (cfg) => conAncho((ancho) => barChart({ ...cfg, ancho }));

  return {
    ico, logo, marca, tarjeta, pie, cargando, errorCarga, estadoVacio, aviso, avisoCoach, confirmacion, bannerCambio, filaHistorial,
    boton, botonIco, campo, opciones, chip, copiar, formulario, filaCampos, insignia, estado,
    encabezado, menu, pasos, segmento, desplegable, senales, tabla, ranking, hojaInBody, filaSesion, barraTroteCaminata,
    leyenda, graficaLinea, graficaBarras,
    /** Silueta de sesión (envoltorio de siluetaSesion): [[min, zona, opcional?]], rachas con lpm, y { alto, conTip, con_calentamiento… }. */
    silueta: (tramos, { alto = 44, conTip = true, rachas = null, ...rampas } = {}) => siluetaSesion(tramos, alto, conTip, rachas, rampas),
  };
})();
