(function () {
  var T = JSON.parse(document.getElementById("gk-datos").textContent);
  var lugar = document.getElementById("copiar-nombre");
  if (lugar && typeof DS !== "undefined" && DS.copiar) lugar.replaceChildren(DS.copiar({ texto: "PERSONAL_API_KEY", aviso: document.currentScript.dataset.copiar }));
  var txt = document.getElementById("guia-estado-t"), barra = document.getElementById("guia-barra-r"),
      botones = document.getElementById("guia-estado-b"), forma = document.getElementById("guia-forma"),
      csrf = document.getElementById("guia-csrf").value;
  var disparada = false, ocupado = false, fin = false;
  function pinta(t, pct, bot) {
    txt.textContent = t || " ";
    barra.style.width = (pct == null ? 0 : pct) + "%";
    botones.replaceChildren();
    if (bot) { var a = document.createElement("button"); a.className = "boton chico"; a.textContent = bot.texto; a.onclick = bot.fn; botones.appendChild(a); }
  }
  function pctDe(s) {
    if (s.estado === "ok") return 100;
    if (s.total) return Math.min(95, 10 + 85 * (s.hechos || 0) / s.total);
    return s.estado === "corriendo" ? 30 : 10;
  }
  function mostrar(s) {
    if (s.estado === "ok") { pinta(T.ok, 100); fin = true; return; }
    if (s.estado === "error") {
      if (s.error === "key_rechazada") pinta(T.rechazada, 0);
      else pinta(T.otra, 0, { texto: T.b_otra, fn: function () { disparada = false; comprobar(false); } });
      return;
    }
    pinta(s.estado === "corriendo" ? T.corriendo : T.esperando, pctDe(s));
  }
  function comprobar(forzar) {
    if (ocupado || fin) return; ocupado = true; disparada = true;
    pinta(T.esperando, 5);
    var cuerpo = { csrf: csrf }; if (forzar) cuerpo.forzar = "1";
    fetch("/api/garmin/key/comprobar", { method: "POST", body: new URLSearchParams(cuerpo), cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { ocupado = false; if (j.sinc) mostrar(j.sinc); else if (j.error === "sin_cambio") { disparada = false; pinta(T.espera, 0); } else mostrar({ estado: "error", error: "otra" }); })
      .catch(function () { ocupado = false; disparada = false; pinta(T.red, 0); });
  }
  function consulta() {
    if (fin || ocupado) return;
    fetch("/api/garmin/key", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.resuelta) return mostrar({ estado: "ok" });
      if (disparada || j.viva) { if (j.sinc) mostrar(j.sinc); return; }
      if (j.cambiada) comprobar(false); else pinta(T.espera, 0);
    }).catch(function () {});
  }
  forma.addEventListener("submit", function (e) { e.preventDefault(); disparada = false; comprobar(true); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) consulta(); });
  window.addEventListener("focus", consulta);
  setInterval(function () { if (!document.hidden) consulta(); }, 5000);
  consulta();
})();
