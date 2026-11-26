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

  const ZONA_VAR = { Z1: "var(--z1)", Z2: "var(--z2)", Z3: "var(--z3)", Z4: "var(--z4)", Z5: "var(--z5)" };
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
  const pie = ({ aviso = T("sitio.ds.pie_aviso"), fuente = T("sitio.ds.pie_fuente"), enlace = { texto: T("sitio.ds.pie_privacidad"), href: "/privacidad" } } = {}) =>
    h("footer", { class: "pie" }, h("p", {}, aviso),
      h("p", {}, fuente, enlace ? " · " : null, enlace ? h("a", { href: enlace.href }, enlace.texto) : null));

  /** Pantalla de carga: el logo se arma. Recibe la frase que va debajo. */
  const cargando = (frase = T("sitio.ds.cargando"), { pagina = false } = {}) => h("div", { class: pagina ? "cargando pagina" : "cargando", role: "status" }, logo(), h("p", { class: "frase" }, frase));

  /** Error de carga. Recibe { titulo, texto, detalle, onReintentar }. */
  const errorCarga = ({ titulo = T("sitio.ds.error_t"), texto = "", detalle = "", onReintentar } = {}) =>
    h("div", { class: "error-carga", role: "alert" }, logo("logo-quieto"), h("p", { class: "ec-t" }, titulo), h("p", { class: "ec-x" }, texto),
      h("button", { class: "boton", type: "button", onclick: onReintentar }, T("sitio.ds.reintentar")),
      detalle ? h("details", {}, h("summary", {}, T("sitio.ds.detalle")), h("code", {}, detalle)) : null);

  /** Estado vacío. Recibe { icono (null = sin ícono), titulo, texto, accion: {texto, href} }; se pone dentro de una tarjeta. */
  const estadoVacio = ({ icono: nombre, titulo, texto, accion } = {}) =>
    h("div", { class: "vacio" }, nombre === null ? null : ico(nombre || "punto"), h("p", { class: "vc-t" }, titulo), texto ? h("p", { class: "vc-x" }, texto) : null,
      accion ? h("a", { class: "boton", href: accion.href }, accion.texto) : null);

  /** Avatar: foto (`foto` = url) o iniciales con color estable. Recibe { iniciales, color (0..5), foto, grande }. */
  const avatar = ({ iniciales = "?", color = 0, foto, grande = false } = {}) =>
    h("span", { class: `avatar ${["av-0", "av-1", "av-2", "av-3", "av-4", "av-5"][color % 6]}${grande ? " g" : ""}`, "aria-hidden": "true" },
      foto ? h("img", { src: foto, alt: "", width: 256, height: 256 }) : iniciales);

  /** Aviso con fondo. Recibe { clase: "warn"|"ok"|"bad", simbolo (insignia al inicio: el color no va solo), titulo, texto, onEntendido (agrega el botón «Entendido») }. */
  const aviso = ({ clase = "warn", simbolo, titulo, texto, extra, onEntendido } = {}) =>
    h("div", { class: `aviso-fondo ${clase}${extra ? ` ${extra}` : ""}`, role: "status" }, titulo ? h("div", { class: "b-t" }, titulo) : null,
      simbolo ? h("div", { class: "estado" }, insignia(clase, simbolo), h("span", {}, texto)) : texto,
      onEntendido ? h("div", { class: "aviso-acc" }, boton(T("sitio.aviso.entendido"), { variante: "texto", chico: true, onclick: onEntendido })) : null);

  /** Aviso del coach (cuando ves a otra persona). Recibe el nombre. */
  /** Línea discreta «Hay una versión nueva · Actualizar» (fija arriba; el real lo arma actualizar.js con el mismo marcado). */
  const avisoVersion = ({ alPulsar = () => {}, estatico = false } = {}) => h("div", { class: "aviso-version" + (estatico ? " estatico" : ""), role: "status" },
    h("span", {}, T("sitio.version_nueva"), " · "), h("button", { type: "button", class: "boton texto chico", onclick: alPulsar }, T("sitio.version_actualizar")));
  const avisoCoach = (nombre) => h("p", { class: "coach-aviso" }, insignia("warn", "!"), h("span", {}, T("sitio.ds.viendo"), h("b", {}, nombre), T("sitio.ds.como_coach")));

  /** Confirmación antes de borrar o perder datos. Recibe { titulo, texto, lista:[], nota, confirmar, cancelar, onConfirmar, onCancelar }. */
  const confirmacion = ({ titulo, texto, lista = [], nota, confirmar = T("sitio.ds.si"), cancelar = T("sitio.ds.cancelar"), onConfirmar, onCancelar } = {}) => {
    const id = uid("cf");
    return h("div", { class: "confirmacion", role: "alertdialog", "aria-labelledby": id },
      h("p", { class: "cf-t", id }, insignia("bad", "!"), titulo),
      texto ? h("p", {}, texto) : null,
      lista.length ? h("ul", {}, lista.map((t) => h("li", {}, t))) : null,
      nota ? h("p", { class: "mu" }, nota) : null,
      h("div", { class: "botones" }, boton(confirmar, { variante: "peligro", onclick: onConfirmar }), boton(cancelar, { variante: "sec", onclick: onCancelar })));
  };

  /** Banner «alguien más cambió tu plan». Recibe { quien, texto, cuando, verHref, verTexto, onDeshacer } (sin onDeshacer no hay botón). */
  const bannerCambio = ({ quien, texto, cuando, verHref = "#", verTexto = T("sitio.ds.ver"), onDeshacer } = {}) =>
    h("div", { class: "banner-cambio", role: "status" },
      h("span", { class: "bc-t" }, quien ? h("b", {}, quien) : null, `${quien ? " " : ""}${texto}${cuando ? ` · ${cuando}` : ""}`),
      h("span", { class: "bc-acc" }, h("a", { class: "boton texto chico", href: verHref }, verTexto),
        onDeshacer ? boton(T("sitio.ds.deshacer"), { variante: "sec", chico: true, ico: "deshacer", onclick: onDeshacer }) : null));

  /** Lista de cambios del plan. Recibe [{ quien, cuando, origen, texto, nuevo, deshecho, onDeshacer }]. */
  const filaHistorial = (items = []) => h("ul", { class: "historial" }, items.map((it) =>
    h("li", { class: `${it.nuevo ? "nuevo" : ""}${it.deshecho ? " deshecho" : ""}`.trim() || null },
      h("p", { class: "fh-q" }, h("b", {}, it.quien), ` · ${it.cuando}`, it.origen ? " · " : null, it.origen ? chip(it.origen, "neutro") : null),
      h("p", { class: "fh-d" }, it.texto),
      it.deshecho ? null : boton(T("sitio.ds.deshacer"), { variante: "sec", chico: true, ico: "deshacer", onclick: it.onDeshacer }))));

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

  /** Diálogo nativo (<dialog>): se abre con `.showModal()`, cierra con Esc, con el botón o tocando afuera. Recibe { titulo, cuerpo, cerrar }. */
  const dialogo = ({ titulo, cuerpo = [], cerrar = T("sitio.ds.cerrar") } = {}) => {
    const id = uid("dl");
    const d = h("dialog", { class: "dialogo", "aria-labelledby": id },
      h("div", { class: "dl-cab" }, h("h3", { class: "dl-t", id }, titulo), botonIco("cerrar", cerrar, { onclick: () => d.close() })),
      h("div", { class: "dl-cuerpo" }, cuerpo));
    d.addEventListener("click", (e) => { if (e.target === d) d.close(); });
    return d;
  };

  /** Fila de ayuda con su muestra visual a la izquierda (mini cuadrito, ícono o marca) y el texto a la derecha. `muestras` son nodos ya armados. */
  const filaMuestra = (muestras, texto) =>
    h("div", { class: "fila-muestra" }, h("span", { class: "fm-muestra", "aria-hidden": "true" }, muestras), h("p", {}, texto));

  /** Burbuja de texto al pasar o enfocar con teclado (no cambia el layout: va absoluta). Recibe el elemento y el texto; devuelve el elemento con
   *  tabindex y aria-describedby. Necesita un ancestro con position: relative (el propio elemento lo es). */
  const burbuja = (el, texto) => {
    const id = uid("bu");
    el.classList.add("con-burbuja");
    el.setAttribute("tabindex", "0");
    el.setAttribute("aria-describedby", id);
    const b = h("span", { class: "burbuja", role: "tooltip", id }, texto);
    el.append(b);
    const ajustar = () => {   // recorta al viewport: se corre lo que se salga por los lados
      b.style.setProperty("--bu-dx", "0px");
      const r = b.getBoundingClientRect(), m = 6, ancho = document.documentElement.clientWidth;
      b.style.setProperty("--bu-dx", `${r.left < m ? m - r.left : r.right > ancho - m ? ancho - m - r.right : 0}px`);
    };
    el.addEventListener("mouseenter", ajustar);
    el.addEventListener("focus", ajustar);
    return el;
  };

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
  const copiar = ({ texto, etiqueta, aviso: etiquetaBoton = T("sitio.ds.copiar_codigo"), copiado = false } = {}) => {
    const btn = h("button", { type: "button", class: copiado ? "listo" : null, "aria-label": copiado ? null : etiquetaBoton, "aria-live": copiado ? "polite" : null });
    const pintar = (listo) => {
      btn.className = listo ? "listo" : "";
      if (listo) btn.setAttribute("aria-live", "polite");
      btn.replaceChildren(ico(listo ? "check" : "copiar"), listo ? T("sitio.ds.copiado") : T("sitio.ds.copiar"));
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

  /** Punto de color de 8 px (semáforo de recuperación): clase "ok"|"warn"|"bad"|"nd" y su texto solo para lectores de pantalla. */
  const punto = (clase, etiqueta) => h("span", { class: `punto-luz ${clase}` }, h("span", { class: "solo-lector" }, etiqueta));

  /** Línea de estado: insignia + texto. Recibe la clase, el símbolo, el texto y, si hace falta, la etiqueta accesible de la insignia. */
  const estado = (clase, simbolo, texto, etiqueta) => h("p", { class: "estado" }, insignia(clase, simbolo, etiqueta), texto);

  // ---------- navegación ----------

  /** Encabezado. Recibe { nombre, actualizado (texto o nodos), tema: "oscuro"|"claro", conAyuda, conMenu, menuAbierto, onAyuda, onTema, onMenu }. */
  const encabezado = ({ nombre, actualizado, tema = "oscuro", conAyuda = true, conMenu = false, menuAbierto = false, onAyuda, onTema, onMenu } = {}) =>
    h("header", { class: "encabezado" },
      h("div", { class: "encabezado-fila" }, marca(nombre),
        conAyuda ? botonIco("ayuda", T("sitio.ds.ayuda"), { onclick: onAyuda }) : null,
        botonIco(tema === "oscuro" ? "sol" : "luna", T(tema === "oscuro" ? "sitio.ds.tema_claro" : "sitio.ds.tema_oscuro"), { onclick: onTema }),
        conMenu ? botonIco("menu", T("sitio.ds.menu"), { expandido: menuAbierto, onclick: onMenu }) : null),
      actualizado ? h("p", { class: "act" }, actualizado) : null);

  /** Menú del ☰. Recibe { quien, items:[{texto, icono, href, actual, onclick} | {separador:true}] } (sin href = botón). */
  const menu = ({ quien, items = [] } = {}) =>
    h("nav", { class: "menu", "aria-label": T("sitio.ds.cuenta") }, quien ? h("p", { class: "menu-quien" }, quien) : null,
      items.map((it) => {
        if (it.separador) return h("hr");
        const hijos = [it.icono ? ico(it.icono) : null, it.texto];
        return it.href !== undefined
          ? h("a", { href: it.href, "aria-current": it.actual ? "page" : null, onclick: it.onclick }, ...hijos)
          : h("button", { type: "button", onclick: it.onclick }, ...hijos);
      }));

  /** Avance del onboarding. Recibe { pasos:[nombres], actual (índice desde 0), texto }. Devuelve la lista y su texto. */
  const pasos = ({ pasos: nombres = [], actual = 0, texto } = {}) => fragmento(
    h("ol", { class: "pasos", "aria-label": T("sitio.ds.avance") }, nombres.map((n, i) =>
      h("li", { class: i < actual ? "hecho" : i === actual ? "actual" : null, "aria-current": i === actual ? "step" : null }, n))),
    texto ? h("p", { class: "pasos-t" }, texto) : null);

  /** Pestañas secundarias. Recibe { etiqueta, opciones:[{id, texto}], activo, modo: "tabs"|"grupo", onCambio(id), id, clase }.
   *  En modo tabs: una sola pestaña en el orden de tabulación y flechas izquierda/derecha para moverse. */
  const segmento = ({ etiqueta, opciones: ops = [], activo, modo = "tabs", onCambio, id, clase } = {}) => {
    const tabs = modo === "tabs";
    const caja = h("div", { class: `segmento${clase ? ` ${clase}` : ""}`, id, role: tabs ? "tablist" : "group", "aria-label": etiqueta });
    const botones = () => [...caja.querySelectorAll("button")];
    const marcar = (cual) => botones().forEach((b) => {
      const on = b.dataset.id === String(cual);
      b.setAttribute(tabs ? "aria-selected" : "aria-pressed", String(on));
      if (tabs) b.tabIndex = on ? 0 : -1;
    });
    const elegir = (op, foco) => { marcar(op.id); if (foco) botones().find((b) => b.dataset.id === String(op.id)).focus(); if (onCambio) onCambio(op.id); };
    caja.append(...ops.map((o, i) => h("button", { type: "button", role: tabs ? "tab" : null, "data-id": o.id,
      onclick: () => elegir(o, false),
      onkeydown: tabs ? (ev) => {
        const k = { ArrowRight: 1, ArrowLeft: -1 }[ev.key];
        if (k) { ev.preventDefault(); elegir(ops[(i + k + ops.length) % ops.length], true); }
      } : null }, o.texto)));
    marcar(activo);
    return caja;
  };

  /** Abrir más detalle. Recibe { titulo (texto o nodos), sub, abierto, liga (estilo «Ver pasos»), clase } y los hijos. */
  const desplegable = ({ titulo, sub, abierto, liga, clase } = {}, ...hijos) =>
    h("details", { class: `desplegable${liga ? " liga-d" : ""}${clase ? ` ${clase}` : ""}`, open: !!abierto },
      h("summary", {}, titulo, sub ? " " : null, sub ? h("small", {}, `· ${sub}`) : null, ico("flecha-abajo")), ...hijos);

  /** Barra de navegación inferior. Recibe { items:[{id, texto, icono, href}], actual (id) }. */
  const tabs = ({ items = [], actual } = {}) =>
    h("nav", { class: "tabs", "aria-label": T("sitio.ds.secciones") }, items.map((it) =>
      h("a", { href: it.href, "data-tab": it.id, "aria-current": it.id === actual ? "page" : null }, ico(it.icono), it.texto)));

  /** Selector de semana. Recibe { texto, onAnterior, onSiguiente, sinAnterior, sinSiguiente }. */
  const selectorSemana = ({ texto, onAnterior, onSiguiente, sinAnterior, sinSiguiente } = {}) =>
    h("div", { class: "sel" },
      h("button", { type: "button", "aria-label": T("sitio.ds.sem_ant"), disabled: !!sinAnterior, onclick: onAnterior }, "‹"),
      h("span", { "aria-live": "polite" }, texto),
      h("button", { type: "button", "aria-label": T("sitio.ds.sem_sig"), disabled: !!sinSiguiente, onclick: onSiguiente }, "›"));

  /** Anillo de avance del plan. Recibe { pct (0–100), titulo, texto, etiqueta (aria-label del anillo) }. */
  const anilloPlan = ({ pct = 0, titulo, texto, etiqueta } = {}) => {
    const C = 2 * Math.PI * 30, p = Math.min(Math.max(pct, 0), 100);
    return h("div", { class: "plan" },
      sv("svg", { viewBox: "0 0 72 72", role: "img", "aria-label": etiqueta || `${Math.round(pct)} %` },
        sv("circle", { class: "f", cx: 36, cy: 36, r: 30 }),
        sv("circle", { class: "l", cx: 36, cy: 36, r: 30, "stroke-dasharray": C.toFixed(2), "stroke-dashoffset": (C * (1 - p / 100)).toFixed(2) }),
        sv("text", { x: 36, y: 41 }, `${Math.round(pct)} %`)),
      h("div", {}, titulo ? h("p", { class: "prog-t" }, titulo) : null, texto ? h("p", { class: "nota" }, texto) : null));
  };

  /** Un día del calendario de la semana. Recibe { nombre (lun…), numero, hoy, titulo (tooltip y lectores), hijos:[nodos],
   numeroEnMarca, alTocar (función: el día pasa a ser un botón), seleccionado }. Con numeroEnMarca el número del día va
   dentro del círculo (hijos) y no se repite arriba. */
  const diaCal = ({ nombre, numero, hoy, titulo, hijos = [], numeroEnMarca = false, alTocar, seleccionado = false } = {}) => {
    const partes = [h("span", { class: "dn" }, nombre), numeroEnMarca ? null : h("span", { class: "df" }, numero), ...hijos];
    const clase = `dia${hoy ? " hoy" : ""}${alTocar && seleccionado ? " dia-sel" : ""}`;
    return alTocar
      ? h("button", { type: "button", class: clase, title: titulo, "aria-label": titulo, "aria-pressed": String(!!seleccionado), onclick: alTocar }, ...partes)
      : h("div", { class: clase, role: "group", title: titulo, "aria-label": titulo }, ...partes);
  };

  /**
   * Curva de frecuencia cardiaca de una actividad. Recibe { seg (duración total en segundos), fc:[lpm] (≤120 puntos, ya
   * bajados en Python) }. Línea simple en SVG, con rejilla y los minutos en el eje x.
   */
  const curvaFc = ({ seg, fc } = {}) => {
    const v = (fc || []).filter((x) => x != null);
    if (v.length < 2 || !seg) return null;
    const lo0 = Math.min(...v), hi0 = Math.max(...v);
    const ticks = ticksNice(lo0 - 2, hi0 + 2, 3);
    const lo = Math.min(lo0 - 2, ticks[0]), hi = Math.max(hi0 + 2, ticks[ticks.length - 1]);
    // Alto fijo (CSS) a cualquier ancho: el trazo va en un SVG que se estira (sin escalar el grosor) y los textos son HTML de 11 px reales.
    const X = (i) => (i / (fc.length - 1)) * 100, Y = (f) => 4 + ((hi - f) / (hi - lo)) * 92;
    const svg = sv("svg", { viewBox: "0 0 100 100", preserveAspectRatio: "none", "aria-hidden": "true" });
    for (const t of ticks) svg.append(sv("line", { class: "rej", x1: 0, x2: 100, y1: Y(t), y2: Y(t) }));
    svg.append(sv("polyline", { class: "ln", points: fc.map((f, i) => (f == null ? null : `${X(i).toFixed(2)},${Y(f).toFixed(2)}`)).filter(Boolean).join(" ") }));
    return h("div", { class: "graf curva-fc", role: "img", "aria-label": T("sitio.act.curva", { a: Math.round(lo0), b: Math.round(hi0) }) },
      h("div", { class: "cf-y" }, ...ticks.map((t) => h("span", { style: `top:${Y(t)}%` }, fmt(t, 0)))),
      h("div", { class: "cf-plot" }, svg),
      h("div", { class: "cf-x" }, ...[0, 0.5, 1].map((f) => h("span", {}, T("sitio.min_n", { n: fmt((seg * f) / 60, 0) })))));
  };

  /** Calendario de 7 días. Recibe los días (DS.diaCal). */
  const calendario = (...dias) => h("div", { class: "cal" }, ...dias.flat());

  /** Cuadro de número: { k (rótulo), valor, unidad, delta, deltaClase: "mal"|"neutro"|"" (o deltas:[[texto, clase]] para varias líneas) }. */
  const tile = ({ k, valor, unidad, delta, deltaClase, deltas } = {}) =>
    h("div", { class: "tile" }, h("span", { class: "k" }, k),
      h("span", { class: "big" }, valor, unidad ? h("small", {}, ` ${unidad}`) : null),
      (deltas || (delta ? [[delta, deltaClase]] : [])).map(([t, c]) => h("span", { class: `delta${c ? ` ${c}` : ""}` }, t)));

  /** Rejilla de cuadros de número. Recibe { etiqueta, clase } y los cuadros (DS.tile). */
  const tiles = ({ etiqueta, clase } = {}, ...cuadros) =>
    h("div", { class: `tiles${clase ? ` ${clase}` : ""}`, role: "group", "aria-label": etiqueta }, ...cuadros);

  /**
   * Barra de minutos por zona (Z1–Z5) con la marca de 80 %. dist = { minutos:{Z1…Z5}, bajo, limbo, alto }.
   * opts: { sinMeta (sin la marca de 80 %: la meta es semanal), leyenda (leyenda fija con % bajo la barra), compacta (delgada, sin corchetes), etiquetas (zona y % dentro de cada tramo, con leyenda en pantalla chica) }.
   */
  const barraZonas = (dist, { compacta = false, etiquetas = false, sinMeta = false, leyenda = false } = {}) => {
    const z = ["Z1", "Z2", "Z3", "Z4", "Z5"];
    const total = z.reduce((a, k) => a + dist.minutos[k], 0);
    if (total <= 0) return null;
    const pct = (k) => (dist.minutos[k] / total) * 100;
    const wrap = h("div", { class: `zbar-w${compacta ? " compacta" : ""}${etiquetas ? " con-etiquetas" : ""}` });
    const barra = h("div", { class: "zbar", role: "img", "aria-label": T("sitio.zb.aria", { b: fmt(dist.bajo, 0), l: fmt(dist.limbo, 0), a: fmt(dist.alto, 0) }) });
    const tip = h("div", { class: "tip zb-tip", hidden: true, role: "status" });
    const mostrar = (seg, k) => {
      tip.replaceChildren(h("b", {}, T("sitio.zb.tip", { k, m: fmt(dist.minutos[k]), p: fmt(pct(k), 0) })));
      tip.hidden = false;
      const r = seg.getBoundingClientRect(), w = wrap.getBoundingClientRect();
      tip.style.left = `${Math.min(Math.max(r.left - w.left + r.width / 2, 60), w.width - 60)}px`;
    };
    for (const k of z) {
      if (dist.minutos[k] <= 0) continue;   // un tramo vacío no se pinta: así el primero y el último con datos llevan las esquinas redondas
      const seg = h("div", { style: `flex:${dist.minutos[k]} 1 0;background:${ZONA_VAR[k]}`, tabindex: "0",
        "aria-label": T("sitio.zb.seg", { k, m: fmt(dist.minutos[k]), p: fmt(pct(k), 0) }) });
      if (etiquetas) seg.append(h("span", { class: "zb-t", "aria-hidden": "true" }, h("span", { class: "zb-z" }, k), h("span", {}, `${fmt(pct(k), 0)} %`)));
      seg.addEventListener("pointerenter", () => mostrar(seg, k));
      seg.addEventListener("pointerdown", () => mostrar(seg, k));
      seg.addEventListener("focus", () => mostrar(seg, k));
      seg.addEventListener("pointerleave", () => (tip.hidden = true));
      seg.addEventListener("blur", () => (tip.hidden = true));
      barra.append(seg);
    }
    wrap.append(tip, barra);
    if (!compacta && !sinMeta) {
      wrap.append(h("div", { class: "brackets", "aria-hidden": "true" }, [["Z1", "Z2"], ["Z3"], ["Z4", "Z5"]].map((g) => {
        const m = g.reduce((a, k) => a + dist.minutos[k], 0);
        return h("div", { style: `flex:${m} 1 0;${m <= 0 ? "display:none" : ""}` });
      })));
    }
    if (!sinMeta) wrap.append(h("div", { class: "meta80", "aria-hidden": "true" }, compacta ? null : h("i", {}, T("sitio.zb.meta"))));
    if (leyenda) {
      wrap.append(h("div", { class: "leyenda zb-ley fija" }, z.filter((k) => dist.minutos[k] > 0).map((k) =>
        h("span", {}, h("i", { style: `background:${ZONA_VAR[k]}`, "aria-hidden": "true" }), `${k} ${fmt(pct(k), 0)} %`))));
    } else if (etiquetas) {
      wrap.append(h("div", { class: "leyenda zb-ley" }, z.filter((k) => dist.minutos[k] > 0).map((k) =>
        h("span", {}, h("i", { style: `background:${ZONA_VAR[k]}`, "aria-hidden": "true" }), k))));
    }
    return wrap;
  };

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
          const celda = c !== null && typeof c === "object" && !c.nodeType ? c : { t: c };
          return h("td", { class: [columnas[i] && columnas[i].num ? "num" : null, celda.clase].filter(Boolean).join(" ") || null }, celda.t);
        }))))));

  /** Mejores marcas y carreras. Recibe { marcas:[{icono, nombre, valor, fecha, nueva, etiqueta}], carreras:[{fecha, icono, resumen, filas:[[k, v]], cuerpo:[nodos], abierta, id}] }. */
  const ranking = ({ marcas = [], carreras = [] } = {}) => fragmento(
    h("div", { class: "marcas" }, marcas.map((m) =>
      h("div", { class: "marca-t", role: "group", "aria-label": m.etiqueta || `${m.nombre}: ${m.valor}, ${m.fecha}` },
        h("span", { class: "mt-n" }, ico(m.icono || "medalla"), m.nombre, m.nueva ? chip(T("sitio.ds.nuevo")) : null),
        h("span", { class: "mt-v" }, m.valor), h("span", { class: "mt-f" }, m.fecha)))),
    carreras.length ? h("div", { class: "carreras" }, carreras.map((c) =>
      h("details", { class: "desplegable", open: !!c.abierta },
        h("summary", {}, ico(c.icono || "medalla"), c.fecha, h("span", { class: "cr-v" }, c.resumen), ico("flecha-abajo")),
        h("div", {}, (c.filas || []).map(([k, v]) => h("div", { class: "kv" }, h("span", {}, k), h("span", {}, v))), ...(c.cuerpo || []))))) : null);

  /** Grupo de barras de la hoja InBody. Recibe { titulo, franja:[{texto, pct, normal}], filas:[{nombre, unidad, zona, textoZona, aria, normal:[izq, ancho], barra, valor, dentro, ticks:[[izq, texto]]}] }. */
  const ibGrupo = ({ titulo, franja = [], filas = [] } = {}) =>
    h("div", { class: "ib-grupo" },
      titulo ? h("h3", {}, titulo) : null,
      franja.length ? h("div", { class: "ib-franja", "aria-hidden": "true" }, franja.map((f) => h("span", { class: f.normal ? "normal" : null, style: `width:${f.pct}%` }, f.texto))) : null,
      filas.map((f) => h("div", { class: "ib-fila", role: "img", "aria-label": f.aria },
        h("div", { class: "ib-nombre" }, h("b", {}, f.nombre), h("small", {}, f.unidad), h("span", { class: `ib-zona ${f.zona}`, "aria-hidden": "true" }, f.textoZona)),
        h("div", { class: "ib-pista" }, h("i", { class: "ib-normal", style: `left:${f.normal[0]}%;width:${f.normal[1]}%` }),
          h("i", { class: "ib-barra", style: `width:${f.barra}%` }),
          h("span", { class: `ib-valor${f.dentro ? " dentro" : ""}`, style: `left:${f.barra}%` }, f.valor)),
        h("div", { class: "ib-ticks", "aria-hidden": "true" }, f.ticks.map(([izq, t]) => h("span", { style: `left:${izq}%` }, t))))));

  /** Puntuación InBody y grasa visceral en dos cuadros. Recibe { puntuacion:{valor, delta, deltaClase}, visceral:{valor, rango, clase, simbolo, texto} } (cualquiera puede faltar). */
  const ibPuntuacion = ({ puntuacion, visceral } = {}) =>
    h("div", { class: "ib-punt" },
      puntuacion ? h("div", { class: "tile" }, h("span", { class: "k" }, T("sitio.ds.ib_punt")),
        h("span", { class: "big" }, puntuacion.valor, h("small", {}, "/100")),
        puntuacion.delta ? h("span", { class: `delta${puntuacion.deltaClase ? ` ${puntuacion.deltaClase}` : ""}` }, puntuacion.delta) : null) : null,
      visceral ? h("div", { class: "tile" }, h("span", { class: "k" }, T("sitio.ds.visceral")),
        h("span", { class: "big" }, visceral.valor, h("small", {}, T("sitio.ds.rango", { r: visceral.rango }))), estado(visceral.clase, visceral.simbolo, visceral.texto)) : null);

  /** Hoja InBody: un grupo de barras y, debajo, la puntuación. Recibe lo de ibGrupo más { puntuacion, visceral }. */
  const hojaInBody = ({ franja = [], filas = [], puntuacion, visceral } = {}) => fragmento(
    ibGrupo({ franja, filas }), puntuacion || visceral ? ibPuntuacion({ puntuacion, visceral }) : null);

  /**
   * Sesión del plan, cerrada y que se abre. Recibe { nombre, minutos (o sub: texto en lugar de «N min»), hoy, abierta, estado:{clase,simbolo,texto},
   * silueta (nodo, p. ej. DS.silueta(...)), titulo (de la silueta), cuerpo:[nodos] (lo que se ve al abrir) }.
   */
  const filaSesion = ({ nombre, minutos, sub, hoy, abierta, estado: est, silueta: sil, titulo, cuerpo = [], id } = {}) =>
    h("details", { class: `fila-ses${hoy ? " hoy" : ""}`, open: !!abierta, id },
      h("summary", {},
        h("span", { class: "fs-n" }, hoy ? chip(T("sitio.ds.hoy")) : null, nombre, sub || minutos != null ? " " : null,
          sub || minutos != null ? h("small", {}, `· ${sub || T("sitio.min_n", { n: minutos })}`) : null),
        est ? h("span", { class: "estado" }, insignia(est.clase, est.simbolo), est.texto) : null,
        sil ? h("span", { class: "fs-sil" }, titulo ? h("span", { class: "titulo-sil" }, titulo) : null, sil) : null),
      cuerpo.length ? h("div", { class: "fs-cuerpo" }, ...cuerpo) : null);

  /** Barra de minutos trotando contra caminando. Recibe { trote, caminata, nota } en minutos. */
  const barraTroteCaminata = ({ trote = 0, caminata = 0, nota } = {}) => fragmento(
    h("div", { class: "barra-rw", role: "img", "aria-label": T("sitio.rw.aria", { t: trote, c: caminata }) },
      h("i", { class: "trote", style: `flex:${trote} 1 0` }), h("i", { class: "camina", style: `flex:${caminata} 1 0` })),
    h("div", { class: "leyenda" }, h("span", {}, h("i", { class: "trote", "aria-hidden": "true" }), T("sitio.rw.trote", { t: trote })),
      h("span", {}, h("i", { class: "camina", "aria-hidden": "true" }), T("sitio.rw.camina", { c: caminata }))),
    nota ? h("p", { class: "nota" }, nota) : null);

  // ---------- gráficas ----------

  /** Leyenda. Recibe [[color o clase, texto o nodos]]: "var(--serie-1)" pinta el cuadrito de ese color; otro texto es la clase de la marca (raya, pto…). */
  const leyenda = (items = []) => h("div", { class: "leyenda" }, items.map(([c, texto]) =>
    h("span", {}, h("i", { style: c.includes("var(") ? `background:${c}` : null, class: c.includes("var(") ? null : c, "aria-hidden": "true" }), texto)));

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
    ico, logo, marca, avatar, tarjeta, pie, cargando, errorCarga, estadoVacio, aviso, avisoVersion, avisoCoach, confirmacion, bannerCambio, filaHistorial,
    boton, botonIco, dialogo, filaMuestra, burbuja, campo, opciones, chip, copiar, formulario, filaCampos, insignia, punto, estado,
    encabezado, menu, pasos, segmento, desplegable, senales, tabla, ranking, hojaInBody, filaSesion, barraTroteCaminata,
    leyenda, graficaLinea, graficaBarras, tabs, selectorSemana, anilloPlan, diaCal, calendario, curvaFc, tile, tiles, barraZonas, ibGrupo, ibPuntuacion,
    /** Silueta de sesión (envoltorio de siluetaSesion): [[min, zona, opcional?]], rachas con lpm, y { alto, conTip, con_calentamiento… }. */
    silueta: (tramos, { alto = 44, conTip = true, rachas = null, ...rampas } = {}) => siluetaSesion(tramos, alto, conTip, rachas, rampas),
  };
})();
