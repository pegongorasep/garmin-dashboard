(function () {
  var T = JSON.parse(document.getElementById("bv-datos").textContent).T;
  var LIGAS = JSON.parse(document.getElementById("bv-datos").textContent).LIGAS;
  var lugar = document.getElementById("copiar-nombre");
  if (lugar && typeof DS !== "undefined" && DS.copiar) lugar.replaceChildren(DS.copiar({ texto: "PERSONAL_API_KEY", aviso: document.currentScript.dataset.copiar }));
  var txt = document.getElementById("guia-estado-t"), barra = document.getElementById("guia-barra-r"),
      botones = document.getElementById("guia-estado-b"), forma = document.getElementById("guia-forma"),
      csrf = document.getElementById("guia-csrf").value;
  var disparada = false, yendo = false, ocupado = false;
  function pinta(t, pct, bot) {
    txt.textContent = t || "\u00a0";
    barra.style.width = (pct == null ? 0 : pct) + "%";
    botones.replaceChildren();
    if (bot) {
      var a = document.createElement(bot.href ? "a" : "button");
      a.className = "boton chico"; a.textContent = bot.texto;
      if (bot.href) { a.href = bot.href; a.target = "_blank"; a.rel = "noopener"; } else a.onclick = bot.fn;
      botones.appendChild(a);
    }
  }
  function pctDe(s) {
    if (!s) return 5;
    if (s.estado === "ok") return 100;
    if (s.total) return Math.min(95, 10 + 85 * (s.hechos || 0) / s.total);
    return s.estado === "corriendo" ? 30 : 10;
  }
  function mostrarSinc(s) {
    if (s.estado === "ok") {
      pinta(T.ok, 100);
      if (!yendo) { yendo = true; setTimeout(function () { location.href = "/"; }, 2000); }
    } else if (s.estado === "error") {
      var c = s.error || "otra";
      if (c === "key_rechazada") pinta(T.key_rechazada, 0, { texto: T.b_garmin, href: LIGAS.key });
      else if (c === "sin_key") pinta(T.sin_key, 0, { texto: T.b_poner, href: LIGAS.secreto });
      else if (c === "nombre_mal") pinta(T.nombre_mal.replace("{n}", "?"), 0, { texto: T.b_corregir, href: LIGAS.secreto });
      else pinta(T.otra, 0, { texto: T.b_otra, fn: function () { disparada = false; comprobar(); } });
    } else pinta(s.estado === "corriendo" ? T.corriendo : T.esperando, pctDe(s));
  }
  function comprobar() {
    if (ocupado) return; ocupado = true; disparada = true;
    pinta(T.esperando, 5);
    fetch("/api/conexion/comprobar", { method: "POST", body: new URLSearchParams({ csrf: csrf }), cache: "no-store" })
      .then(function (r) { return r.json(); })
      .then(function (j) { ocupado = false; if (j.sinc) mostrarSinc(j.sinc); else if (j.error === "otra") mostrarSinc({ estado: "error", error: "otra" }); })
      .catch(function () { ocupado = false; disparada = false; pinta(T.red, 0); });
  }
  function consulta() {
    if (yendo || ocupado) return;
    fetch("/api/conexion/estado", { cache: "no-store" }).then(function (r) { return r.json(); }).then(function (j) {
      if (j.sinc && (j.viva || j.sinc.estado === "ok" || disparada)) return mostrarSinc(j.sinc);
      if (j.secreto === "listo") { if (!disparada) comprobar(); }
      else if (j.secreto === "nombre_mal") pinta(T.nombre_mal.replace("{n}", j.nombre || "?"), 0, { texto: T.b_corregir, href: LIGAS.secreto });
      else if (j.error === "otra") pinta(T.otra, 0);
      else pinta(T.falta, 0);
    }).catch(function () {});
  }
  forma.addEventListener("submit", function (e) { e.preventDefault(); consulta(); });
  document.addEventListener("visibilitychange", function () { if (!document.hidden) consulta(); });
  window.addEventListener("focus", consulta);
  setInterval(function () { if (!document.hidden) consulta(); }, 5000);
  consulta();
})();
