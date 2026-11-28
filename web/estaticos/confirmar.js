document.querySelectorAll("form[data-confirmar]").forEach(function (f) {   // pedir confirmación antes de borrar
  f.addEventListener("submit", function (e) { if (!confirm(f.dataset.confirmar)) e.preventDefault(); });
});
