      (function () {
        var q = function (n) { return document.querySelector('[name="' + n + '"]'); }, conf = document.getElementById("g-conf");
        function lanzar(tipo) { if (window.Franja) window.Franja.empezar(tipo); }
        q("g-sync").addEventListener("click", function () { lanzar("normal"); });
        q("g-treinta").addEventListener("click", function () { lanzar("treinta"); });
        q("g-desc").addEventListener("click", function () { conf.classList.add("abierta"); });
        q("g-no").addEventListener("click", function () { conf.classList.remove("abierta"); });
      })();
      