// Registra el service worker y avisa cuando hay una versión nueva esperando (sin recargar solo). Lo cargan las páginas de la web y el sitio.
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

  const cuerpo = yo && yo.dataset.cuerpo, luego = yo && yo.dataset.luego;
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
    si.addEventListener("click", () => { pidio = true; si.disabled = true; no.disabled = true; worker.postMessage("SKIP_WAITING"); });
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

  // Solo recarga si la persona pidió actualizar (así la primera instalación, que también "toma el control", no recarga) y una sola vez.
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!pidio || recargando) return;
    recargando = true;
    location.reload();
  });

  navigator.serviceWorker.register("/sw.js").then((reg) => {
    const hayPrevio = () => !!navigator.serviceWorker.controller;   // sin controlador previo = primera instalación: no se avisa nada
    if (reg.waiting && hayPrevio()) ofrecer(reg.waiting);
    reg.addEventListener("updatefound", () => {
      const nuevo = reg.installing;
      if (!nuevo) return;
      nuevo.addEventListener("statechange", () => { if (nuevo.state === "installed" && hayPrevio()) ofrecer(nuevo); });
    });
    // iOS casi nunca revisa solo: al volver a la app, preguntar.
    document.addEventListener("visibilitychange", () => { if (!document.hidden) reg.update().catch(() => {}); });
  }).catch(() => {});
})();
