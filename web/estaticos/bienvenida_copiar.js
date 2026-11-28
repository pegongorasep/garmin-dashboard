(function () {
  var lugar = document.getElementById("copiar-nombre");
  if (!lugar || typeof DS === "undefined" || !DS.copiar) return;
  lugar.replaceChildren(DS.copiar({ texto: "PERSONAL_API_KEY", aviso: document.currentScript.dataset.copiar }));
})();
