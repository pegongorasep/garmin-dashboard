// Íconos de línea (trazo 1.75, viewBox 24, a mano). Python decide cuál va en cada lugar; aquí solo se pintan.
// Siempre decorativos (aria-hidden): al lado va el texto o un title.
const ICONOS = {
  correr: [["circle", { cx: 15, cy: 4.6, r: 1.9 }],
    ["path", { d: "M13.4 8.6 10.6 13.6 M13.4 8.6 17.2 11.4 18.8 9.6 M13.2 9.2 9.6 10.8 7.6 9.2" }],
    ["path", { d: "M10.6 13.6 14.2 16 13 20.6 M10.6 13.6 8.4 17.4 5.2 18.4" }]],
  medalla: [["circle", { cx: 12, cy: 15, r: 5.2 }],
    ["path", { d: "M8.4 2.6 10.8 9.9 M15.6 2.6 13.2 9.9 M12 12.6v4.8" }]],
  mancuerna: [["path", { d: "M6.5 6.5v11 M3.5 9.5v5 M17.5 6.5v11 M20.5 9.5v5 M6.5 12h11" }]],
  rayo: [["path", { d: "M13.2 2.6 5.2 13.4h6l-1 8 8-10.8h-6z" }]],
  bici: [["circle", { cx: 5.8, cy: 16, r: 3.6 }], ["circle", { cx: 18.2, cy: 16, r: 3.6 }],
    ["path", { d: "M5.8 16 9.6 8.6h5.2l3.4 7.4 M9.6 8.6 12.2 16 14.8 8.6 M14.8 8.6l-.9-2.4h2.4 M8.2 8.6h2.8" }]],
  nadar: [["circle", { cx: 16.4, cy: 6, r: 1.9 }],
    ["path", { d: "M4.2 12.4 9.4 9.4l5.2 2.2 M2.4 17.4q2.4-2.4 4.8 0t4.8 0 4.8 0 4.8 0 M2.4 21q2.4-2.4 4.8 0t4.8 0 4.8 0 4.8 0" }]],
  caminar: [["circle", { cx: 13, cy: 4.6, r: 1.9 }],
    ["path", { d: "M12.6 8.4 11.6 14 M11.6 14l2.6 6.2 M11.6 14l-3 6.4 M12.6 9.4 9.6 12.4 M12.6 9.4l3 2.8" }]],
  yoga: [["circle", { cx: 12, cy: 5, r: 2 }],
    ["path", { d: "M12 8.2v5 M12 9.4 7 6.4 M12 9.4l5-3 M12 13.2q-6 .2-8 4.8h16q-2-4.6-8-4.8z" }]],
  punto: [["circle", { cx: 12, cy: 12, r: 3 }]],
};

/** SVG de línea 24×24 (`tam` px, hereda `currentColor`). Un nombre desconocido o ausente pinta "punto". */
function icono(nombre, tam = 18) {
  const partes = ICONOS[nombre] || ICONOS.punto;
  const svg = sv("svg", { viewBox: "0 0 24 24", width: tam, height: tam, class: "ico-svg", "aria-hidden": "true", focusable: "false",
    fill: "none", stroke: "currentColor", "stroke-width": 1.75, "stroke-linecap": "round", "stroke-linejoin": "round" });
  for (const [tag, attrs] of partes) svg.append(sv(tag, attrs));
  return svg;
}
