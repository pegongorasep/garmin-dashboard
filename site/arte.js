// Dibujos de los estados vacíos y de espera: SVG a mano en una caja de 240 × 180. Aquí van solo las formas; los colores salen de
// tokens.css y el movimiento (clases a-*) de componentes.css, que en reposo deja el dibujo completo. Necesita base.js (sv) e iconos.js.
const ARTE = (() => {
  const lienzo = (...hijos) => sv("svg", { class: "arte", viewBox: "0 0 240 180", "aria-hidden": "true", focusable: "false" }, ...hijos);
  const g = (clase, ...hijos) => sv("g", { class: clase }, ...hijos);
  const circulo = (cx, cy, r, attrs) => sv("circle", { cx, cy, r, ...attrs });

  /** Tres sesiones de ejemplo bajo el anillo: [x de la píldora, [[x, ancho, color] de cada barra]]. */
  const SESIONES = [[26, [[38, 32, "var(--z2)"]]], [92, [[104, 12, "var(--z2)"], [118, 18, "var(--z3)"]]], [158, [[168, 36, "var(--z1)"]]]];

  /** Plan: un anillo que se traza, quien corre y tres sesiones. Con `espera` el anillo se vuelve a trazar sin parar. */
  const anillo = ({ espera = false } = {}) => {
    const aro = (stroke, attrs) => circulo(120, 72, 54, { fill: "none", stroke, "stroke-width": 12, ...attrs });
    const quien = icono("correr", 48);
    quien.setAttribute("x", 96);
    quien.setAttribute("y", 48);
    return lienzo(
      aro("var(--grid)"),
      aro("var(--accent)", { class: espera ? "a-espera" : "a-trazo", "stroke-linecap": "round", "stroke-dasharray": "339.3 420", transform: "rotate(-90 120 72)" }),
      g("a-pop a-d6", quien),
      SESIONES.map(([x, barras], i) => g(`a-aparece a-d${i + 5}`, sv("rect", { x, y: 146, width: 56, height: 26, rx: 13, fill: "var(--accent-bg)" }),
        barras.map(([bx, width, fill]) => sv("rect", { x: bx, y: 156, width, height: 6, rx: 3, fill })))));
  };

  /** Una persona: marco redondo, cabeza y hombros del mismo color. */
  const persona = ({ cx, cy, r, color, cabeza, hombros }) => [
    circulo(cx, cy, r, { fill: "var(--surface)", stroke: color, "stroke-width": 3 }),
    circulo(cx, cabeza[0], cabeza[1], { fill: color }),
    sv("path", { d: hombros, fill: color })];
  const YO = { cx: 120, cy: 82, r: 40, color: "var(--accent)", cabeza: [71, 13], hombros: "M97 106c4-18 42-18 46 0" };
  const OTRAS = [{ cx: 66, cy: 98, r: 32, color: "var(--z1)", cabeza: [89, 10], hombros: "M48 117c3-13 33-13 36 0" },
    { cx: 174, cy: 98, r: 32, color: "var(--z4)", cabeza: [89, 10], hombros: "M156 117c3-13 33-13 36 0" }];

  /** Grupos: con `libres`, tú y dos lugares por llenar; sin él, las personas del grupo. */
  const personas = ({ libres = false } = {}) => {
    const retardo = ["a-d3", "a-d5"];
    if (libres) return lienzo(
      OTRAS.map((p, i) => g(`a-pop ${retardo[i]}`, circulo(p.cx, p.cy, p.r, { class: "a-late", fill: "none", stroke: "var(--muted)", "stroke-width": 2, "stroke-dasharray": "6 6" }))),
      g("a-pop", persona(YO)));
    return lienzo([...OTRAS, YO].map((p, i) => g("a-flota", g(`a-pop ${["", ...retardo][i]}`, persona(p)))));
  };

  return { anillo, personas };
})();
