(function () {
  var t = "dark";
  try { var g = localStorage.getItem("tema"); if (g === "light" || g === "dark") t = g; } catch (e) {}
  document.documentElement.setAttribute("data-theme", t);
})();
