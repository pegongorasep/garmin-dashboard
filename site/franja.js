/* Franja de sincronización: fija hasta arriba, sin cerrar, misma altura en todos los estados. Sin librerías.
   La lógica (textos, porcentaje, acción) la manda Python en GET /api/sync; aquí solo se pinta y se sondea.
   Expone window.Franja.empezar(tipo) y emite `franja:lista` (al terminar bien lo que se vio correr) y `franja:estado` {viva}. */
(function () {
  if (window.Franja || /^\/a\//.test(location.pathname)) return;   // un coach viendo a su atleta no sincroniza por él
  const script = document.currentScript;
  const CSRF = (script && script.dataset.campo) || "";
  const OK_MS = 4000;
  // Dos modos, un solo componente: en la página del sitio (con `.encabezado .act`) el texto ocupa la ranura de «Actualizado hace…»
  // y una barra de 3 px absoluta pega al borde de abajo del encabezado; en las demás páginas, una franja fija que flota sin empujar nada.
  let flota = null, enc = null, pend = null, temporizador = null, ocultar = null, vistaViva = false, viva = false, ultimo = null, visible = false;

  function armar(clase) {
    const mk = (tag, c) => { const n = document.createElement(tag); n.className = c; return n; };
    const texto = mk("span", "franja-t"), boton = mk("button", "franja-b"), enlace = mk("a", "franja-b"), relleno = mk("i", "");
    boton.type = "button"; boton.hidden = enlace.hidden = true;
    const fila = mk("div", "franja-fila"); fila.append(texto, boton, enlace);
    const barra = mk("div", "franja-barra"); barra.append(relleno);
    return { texto, boton, enlace, relleno, fila, barra };
  }

  function destino() {
    const act = document.querySelector(".encabezado .act");
    if (act) {
      if (!enc) {
        enc = armar();
        enc.raiz = document.createElement("span"); enc.raiz.className = "franja-enc"; enc.raiz.setAttribute("role", "status"); enc.raiz.setAttribute("aria-live", "polite");
        enc.raiz.append(enc.texto, enc.boton, enc.enlace);
        enc.barra.className = "franja-enc-barra";
      }
      const cab = act.closest(".encabezado");
      if (enc.raiz.parentNode !== act) act.append(enc.raiz);
      if (enc.barra.parentNode !== cab) cab.append(enc.barra);
      return { m: enc, cab };
    }
    if (document.getElementById("encabezado")) {   // página del sitio con el encabezado aún sin pintar: nada flota; se cuelga en `reponer`
      if (!pend) { pend = armar(); pend.raiz = document.createElement("span"); }
      return { m: pend, cab: null };
    }
    if (!flota) {
      flota = armar();
      flota.raiz = document.createElement("div"); flota.raiz.className = "franja"; flota.raiz.hidden = true;
      flota.raiz.setAttribute("role", "status"); flota.raiz.setAttribute("aria-live", "polite");
      flota.raiz.append(flota.fila, flota.barra);
      document.body.prepend(flota.raiz);
    }
    return { m: flota, cab: null };
  }

  function mostrar(si) {
    visible = si;
    const { m, cab } = destino();
    if (cab) cab.classList.toggle("sync-on", si); else if (m !== pend) m.raiz.hidden = !si;
  }

  function reponer() { if (visible && ultimo) pintar(ultimo); }   // el sitio repinta el encabezado: la franja se vuelve a colgar

  function emitir(nombre, detalle) { window.dispatchEvent(new CustomEvent(nombre, { detail: detalle })); }

  function ponerViva(v) {
    if (viva !== v) { viva = v; emitir("franja:estado", { viva: v }); }
  }

  function pintar(s) {
    clearTimeout(ocultar); clearTimeout(temporizador); temporizador = null;
    ultimo = s;
    if (!s) { ponerViva(false); mostrar(false); return; }
    const { m } = destino();
    const termino = s.estado === "ok" || s.estado === "error";
    m.texto.textContent = s.texto || "";
    m.raiz.dataset.estado = s.estado;
    if (m.barra) m.barra.dataset.estado = s.estado;
    m.relleno.style.width = Math.max(0, Math.min(100, s.porcentaje || 0)) + "%";
    m.boton.hidden = m.enlace.hidden = true;
    if (s.estado === "error" && s.accion) {
      if (s.accion.url) { m.enlace.href = s.accion.url; m.enlace.textContent = s.accion.texto; m.enlace.hidden = false; }
      else if (s.accion.post) { m.boton.textContent = s.accion.texto; m.boton.onclick = () => empezar(s.accion.post.tipo); m.boton.hidden = false; }
    }
    if (!termino) {
      vistaViva = true; ponerViva(true); mostrar(true);
      temporizador = setTimeout(sondear, document.hidden ? 5000 : 2000);
      return;
    }
    ponerViva(false);
    if (s.estado === "ok") {
      const resta = OK_MS - (s.terminada_hace_s || 0) * 1000;
      if (resta <= 0) { mostrar(false); vistaViva = false; return; }
      mostrar(true);
      if (vistaViva) { vistaViva = false; emitir("franja:lista", { nuevas: s.nuevas }); }
      ocultar = setTimeout(() => mostrar(false), Math.min(resta, OK_MS));
      return;
    }
    vistaViva = false;
    mostrar(true);   // error: se queda hasta que la persona toque la acción o el servidor ya no lo traiga
  }

  async function sondear() {
    try {
      const r = await fetch("/api/sync", { cache: "no-store", credentials: "same-origin" });
      if (!r.ok) { if (viva) temporizador = setTimeout(sondear, 5000); return; }
      pintar((await r.json()).sinc);
    } catch (e) { if (viva) temporizador = setTimeout(sondear, 5000); }
  }

  async function empezar(tipo) {
    try {
      const r = await fetch("/api/sync", { method: "POST", credentials: "same-origin",
        headers: { "Content-Type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ csrf: CSRF, tipo: tipo || "normal" }) });
      const j = await r.json().catch(() => ({}));
      if (r.status === 409 && j.url) { location.href = j.url; return; }
      if (r.status === 429) { pintar({ estado: "error", texto: j.texto || "", porcentaje: 0, accion: null }); return; }
      if (j.sinc) { vistaViva = true; pintar(j.sinc); }
    } catch (e) { /* sin red: no pasa nada, se vuelve a intentar al tocar */ }
  }

  window.Franja = { empezar, viva: () => viva, reponer, _pintar: pintar };
  document.addEventListener("visibilitychange", () => { if (viva && !document.hidden) { clearTimeout(temporizador); sondear(); } });
  const iniciar = () => sondear();
  if (document.body) iniciar(); else document.addEventListener("DOMContentLoaded", iniciar);
})();
