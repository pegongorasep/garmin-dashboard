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

  function ofrecer(worker) {
    if (linea || !texto) return;
    const boton = document.createElement("button");
    boton.type = "button"; boton.className = "boton texto chico"; boton.textContent = accion;
    boton.addEventListener("click", () => { pidio = true; boton.disabled = true; worker.postMessage("SKIP_WAITING"); });
    const span = document.createElement("span");
    span.textContent = texto + " · ";
    linea = document.createElement("div");
    linea.className = "aviso-version"; linea.setAttribute("role", "status");
    linea.append(span, boton);
    document.body.appendChild(linea);
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
