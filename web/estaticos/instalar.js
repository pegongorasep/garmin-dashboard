// /instalar: se salta si la app ya está instalada o la persona dijo «Ahora no»; ofrece instalar en Android/Chrome.
(function () {
  var sig = (document.currentScript && document.currentScript.dataset.siguiente) || "/";
  var LLAVE = "instalar_ahora_no";
  function seguir() { location.replace(sig); }
  var standalone = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone;
  var dijoNo = false;
  try { dijoNo = localStorage.getItem(LLAVE) === "1"; } catch (e) {}
  if (standalone || dijoNo) { seguir(); return; }
  document.querySelectorAll("a[href]").forEach(function (a) {
    if (a.textContent.trim() === "Ahora no") a.addEventListener("click", function () { try { localStorage.setItem(LLAVE, "1"); } catch (e) {} });
  });
  var evento = null, caja = document.getElementById("inst-android"), nota = document.getElementById("inst-nota-android");
  window.addEventListener("beforeinstallprompt", function (e) {
    e.preventDefault(); evento = e;
    if (caja) caja.hidden = false;
    if (nota) nota.hidden = true;
  });
  if (caja) caja.addEventListener("click", function () {
    if (!evento) return;
    evento.prompt();
    evento.userChoice.then(function () { seguir(); }, seguir);
  });
})();
