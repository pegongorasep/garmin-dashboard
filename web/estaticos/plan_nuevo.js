// Vista previa de «Quiero un plan» (paso 3). Python decide todo (textos, botones, plan); aquí solo se pinta.
// - Los botones de volumen piden /plan/nuevo/vista.json (sin guardar nada) y repintan la fila, la ranura, la gráfica, «Por qué» y el plan completo.
// - «Ver el plan completo» es la misma tarjeta de la pestaña Plan (`tarjetaPlan`, site/vistas.js), solo lectura, dentro de un desplegable.
// Sin JS los botones siguen siendo un POST normal a /plan/nuevo/vista.
(async function () {
  const raiz = document.getElementById("pn-prev"), crudo = document.getElementById("pn-datos");
  if (!raiz || !crudo) return;
  window.RUTA_I18N = "/";
  await cargarIdioma(document.documentElement.lang);
  const $ = (id) => document.getElementById(id);
  let datos = JSON.parse(crudo.textContent);
  let sel = null;              // semana que se está viendo en la tarjeta
  let abierto = false;         // ¿el desplegable estaba abierto?
  let desplegable = null;

  const pintarPlan = () => {
    const sitio = $("pn-plan");
    if (!sitio || !datos.plan) return;
    const tarjeta = tarjetaPlan(datos.plan, { sel, alElegir: (n) => { sel = n; }, clase: "" });
    desplegable = DS.desplegable({ titulo: sitio.dataset.titulo, abierto }, tarjeta);
    desplegable.addEventListener("toggle", () => { abierto = desplegable.open; });
    sitio.replaceChildren(desplegable);
  };

  const pintar = () => {
    const v = datos.volumen;
    $("pn-vol-t").textContent = v.texto;
    const [menos, mas] = $("pn-volumen").querySelectorAll("button");
    for (const [b, x, pordefecto] of [[menos, v.menos, v.etiqueta_menos], [mas, v.mas, v.etiqueta_mas]]) {
      b.disabled = !x;
      b.textContent = x ? x.etiqueta : pordefecto;
      if (x) b.value = String(x.valor); else b.removeAttribute("value");
    }
    const r = v.recomendacion;
    $("pn-ranura").replaceChildren(r.clase === "warn" ? DS.aviso({ clase: "warn", texto: r.texto }) : h("p", { class: "nota" }, r.texto),
      ...(v.maximo ? [h("p", { class: "nota" }, v.maximo)] : []));
    $("pn-barras").replaceChildren(...datos.semanas.map((s) => h("li", { class: `pn-barra ${s.kind}` },
      h("span", { class: "pn-sem" }, s.etiqueta), h("progress", { max: datos.tope, value: s.min }, String(s.min)), h("span", { class: "pn-min" }, s.texto))));
    $("pn-porques").replaceChildren(...datos.porques.map((p) => h("li", {}, p)));
    raiz.querySelectorAll('input[type="hidden"][name="ajuste_pct"]').forEach((i) => { i.value = String(datos.ajuste_pct); });   // Confirmar guarda lo que se ve
    pintarPlan();
  };

  // El botón de volumen manda el formulario por fetch; si algo falla, se deja el envío normal (la página se recarga con el mismo resultado).
  $("pn-volumen").addEventListener("submit", async (ev) => {
    const boton = ev.submitter;
    if (!boton || !boton.name) return;
    ev.preventDefault();
    const f = $("pn-volumen"), cuerpo = new URLSearchParams(new FormData(f));
    cuerpo.set(boton.name, boton.value);
    f.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      const r = await fetch(raiz.dataset.url, { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" }, body: cuerpo });
      if (!r.ok) throw new Error(String(r.status));
      datos = await r.json();
      pintar();
    } catch (e) {
      f.append(h("input", { type: "hidden", name: boton.name, value: boton.value }));
      f.submit();
    }
  });
  pintarPlan();
})();
