(function () {   // solo muestra u oculta (el espacio se queda) y cambia la unidad; la lógica vive en el servidor
  var f = document.getElementById("act-form"), sel = f.elements.otro;
  function ver() {
    var r = f.querySelector('input[name="tipo"]:checked'), u = r ? r.dataset.unidad : "km";
    document.getElementById("act-otro").classList.toggle("oculta", u !== "lista");
    if (u === "lista") u = sel.selectedOptions[0].dataset.unidad;
    document.getElementById("act-dist").classList.toggle("oculta", u === "oculta");
    if (u !== "oculta") document.getElementById("act-unidad").textContent = u === "m" ? f.dataset.m : f.dataset.km;
  }
  f.addEventListener("change", ver);
  ver();
})();
