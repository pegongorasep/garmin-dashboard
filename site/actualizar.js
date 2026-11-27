// Registra el service worker y, si sale una versión nueva con la app ya abierta, la ofrece (sin recargar solo). Lo cargan las páginas de la web y el sitio.
(function () {
  // Selector de idioma del pie: al cambiar envía el mismo formulario (sin JS queda el botón del <noscript>).
  document.addEventListener("change", (e) => {
    const sel = e.target;
    if (sel && sel.matches && sel.matches(".pie-idioma select") && sel.form) sel.form.requestSubmit ? sel.form.requestSubmit() : sel.form.submit();
  });
  if (!("serviceWorker" in navigator)) return;
  const yo = document.currentScript;
  const texto = yo && yo.dataset.texto, accion = yo && yo.dataset.accion;
  let pidio = false, recargando = false, linea = null;

  const cuerpo = yo && yo.dataset.cuerpo, luego = yo && yo.dataset.luego, haciendo = yo && yo.dataset.actualizando;
  let registro = null;   // el registro del service worker: su .waiting es siempre el worker vigente
  const descartados = new WeakSet();   // «Ahora no»: no se vuelve a mostrar en esta sesión de la página para ese mismo worker

  function ofrecer(worker) {
    if (linea || !texto || descartados.has(worker)) return;
    const d = document.createElement("dialog");
    d.className = "dialogo dialogo-version";
    d.setAttribute("aria-labelledby", "dv-titulo"); d.setAttribute("aria-describedby", "dv-cuerpo");
    const t = document.createElement("h3"); t.className = "dl-t"; t.id = "dv-titulo"; t.textContent = texto;
    const p = document.createElement("p"); p.id = "dv-cuerpo"; p.className = "dv-cuerpo"; p.textContent = cuerpo || "";
    const si = document.createElement("button"); si.type = "button"; si.className = "boton"; si.textContent = accion;
    const no = document.createElement("button"); no.type = "button"; no.className = "boton texto"; no.textContent = luego || "";
    const fila = document.createElement("div"); fila.className = "dv-botones"; fila.append(no, si);
    d.append(t, p, fila);
    si.addEventListener("click", () => {
      pidio = true; si.disabled = true; no.disabled = true;
      if (haciendo) si.textContent = haciendo;
      // Al worker que espera AHORA (el capturado pudo quedar redundante si salió otra versión); si no hay, al capturado.
      const vigente = (registro && registro.waiting) || worker;
      try { vigente.postMessage("SKIP_WAITING"); } catch (_) {}
      // Si el cambio de controlador no llega en 3 s, recarga igual (una sola vez).
      setTimeout(recargar, 3000);
    });
    // «Ahora no», Esc (evento close) o tocar afuera: cierra y no vuelve a salir para este worker en esta página.
    const soltar = () => { if (!pidio) descartados.add(worker); if (linea === d) linea = null; d.remove(); };   // idempotente
    no.addEventListener("click", () => { d.close(); soltar(); });
    d.addEventListener("click", (e) => { if (e.target === d) { d.close(); soltar(); } });
    d.addEventListener("close", soltar);
    linea = d;
    document.body.appendChild(d);
    if (d.showModal) d.showModal(); else d.setAttribute("open", "");
    si.focus();   // showModal ya atrapa el foco dentro del diálogo
  }

  // Recién abierta o refrescada, la página ya trae lo último (el service worker pide primero a la red): la versión nueva se
  // activa en silencio. Solo a la app que ya estaba abierta y a la que se regresa se le ofrece actualizar.
  let volvio = false;
  function llego(worker) {
    if (volvio) return ofrecer(worker);
    try { worker.postMessage("SKIP_WAITING"); } catch (_) {}
  }

  // Solo recarga si la persona pidió actualizar (así la primera instalación, que también "toma el control", no recarga) y una sola vez.
  function recargar() {
    if (!pidio || recargando) return;
    recargando = true;
    location.reload();
  }
  navigator.serviceWorker.addEventListener("controllerchange", recargar);

  navigator.serviceWorker.register("/sw.js").then((reg) => {
    registro = reg;
    const hayPrevio = () => !!navigator.serviceWorker.controller;   // sin controlador previo = primera instalación: no se avisa nada
    if (reg.waiting && hayPrevio()) llego(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const nuevo = reg.installing;
      if (!nuevo) return;
      nuevo.addEventListener("statechange", () => { if (nuevo.state === "installed" && hayPrevio()) llego(nuevo); });
    });
    // iOS casi nunca revisa solo: al volver a la app, preguntar.
    document.addEventListener("visibilitychange", () => { if (!document.hidden) { volvio = true; reg.update().catch(() => {}); } });
  }).catch(() => {});
})();
