/* Diálogos nativos de la web. Un botón con data-abre="id" abre <dialog id>; data-cierra (dentro) lo cierra.
   Se abre solo si la URL trae #id o si el dialog tiene data-abierto (p. ej. tras un error de validación). */
(function () {
  document.documentElement.classList.add("js");
  const dialogos = () => Array.from(document.querySelectorAll("dialog.dialogo"));
  function abrir(d, vuelta) {
    if (!d || d.open) return;
    dialogos().forEach((o) => { if (o.open) o.close(); });
    d.showModal();
    const campo = d.querySelector("input:not([type=hidden]), select, textarea, button");
    if (campo) campo.focus();
    d.__vuelta = vuelta || null;
  }
  document.addEventListener("click", (e) => {
    const a = e.target.closest("[data-abre]");
    if (a) { abrir(document.getElementById(a.dataset.abre), a); return; }
    if (e.target.closest("[data-cierra]")) { const d = e.target.closest("dialog"); if (d) d.close(); return; }
    if (e.target.tagName === "DIALOG" && e.target.classList.contains("dialogo")) e.target.close();   // clic en el fondo
  });
  document.addEventListener("close", (e) => { const d = e.target; if (d.__vuelta) d.__vuelta.focus(); }, true);
  function porUrl() {
    const id = decodeURIComponent(location.hash.slice(1));
    const d = id && dialogos().find((x) => x.id === id);
    if (d) abrir(d);
  }
  dialogos().forEach((d) => { if (d.hasAttribute("data-abierto")) abrir(d); });
  porUrl();
  window.addEventListener("hashchange", porUrl);
})();
