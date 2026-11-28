/* Tema antes de pintar: lo guardado, o oscuro por defecto. ?tema=claro|oscuro fuerza uno solo para capturas (no se guarda). */
(function () {
  var t = "dark";
  try {
    var q = /[?&]tema=(claro|oscuro)/.exec(location.search);
    var g = localStorage.getItem("tema");
    if (q) t = q[1] === "claro" ? "light" : "dark"; else if (g === "light" || g === "dark") t = g;
  } catch (e) {}
  document.documentElement.setAttribute("data-theme", t);
  document.querySelector('meta[name="color-scheme"]').setAttribute("content", t);
})();
