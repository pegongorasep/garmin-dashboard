(function () {
  var d = document.currentScript.dataset;
  var mq = window.matchMedia && window.matchMedia("(max-width: 700px), (pointer: coarse)");
  var cel = document.getElementById("guia-celular");
  if (cel && mq && mq.matches) {
    cel.hidden = false;
    var f = document.createElement("form");
    f.method = "post"; f.action = "/bienvenida/liga";
    f.innerHTML = '<input type="hidden" name="csrf" value="' + d.csrf + '"><button class="boton sec chico" type="submit">' + d.texto + '</button>';
    cel.appendChild(f);
  }
})();
