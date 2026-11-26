// /instalar: se salta si la app ya está instalada o la persona dijo «Ahora no»; muestra solo las instrucciones del sistema de la persona (iPhone/iPad o Android); en compu, salta directo.
(function () {
  var sig = (document.currentScript && document.currentScript.dataset.siguiente) || "/";
  var LLAVE = "instalar_ahora_no";
  function seguir() { location.replace(sig); }
  var standalone = (window.matchMedia && matchMedia("(display-mode: standalone)").matches) || navigator.standalone;
  var dijoNo = false;
  try { dijoNo = localStorage.getItem(LLAVE) === "1"; } catch (e) {}
  var ua = navigator.userAgent || "";
  var ios = /iPhone|iPad|iPod/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);   // iPadOS se presenta como Mac con pantalla táctil
  var android = !ios && /Android/.test(ua);
  if (standalone || dijoNo || (!ios && !android)) { seguir(); return; }
  var cAnd = document.getElementById("inst-card-android"), cIos = document.getElementById("inst-card-ios");
  if (cAnd) cAnd.hidden = !android;
  if (cIos) cIos.hidden = !ios;
  var cont = document.getElementById("inst"); if (cont) cont.hidden = false;
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
