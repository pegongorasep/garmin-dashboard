"""Genera site/tokens.css desde diseno/tokens.json y site/iconos.js desde diseno/iconos/*.svg (sistema «Ahí la Llevas»).

Oscuro va en :root (es el tema por defecto); claro con [data-theme="light"] o, sin atributo, con el sistema.
Uso: python scripts/tokens.py [--check]   (--check falla si algo no está al día)
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FUENTE = ROOT / "diseno" / "tokens.json"
SALIDA = ROOT / "site" / "tokens.css"
ICONOS = ROOT / "diseno" / "iconos"
SALIDA_ICONOS = ROOT / "site" / "iconos.js"
TEMAS = ("oscuro", "claro")


def _valor(token: dict, tema: str):
    v = token["value"]
    return v[tema] if isinstance(v, dict) else v


def _resolver(vals: dict) -> dict:
    """Valores tipo "{accent}" toman el de otro token del mismo tema."""
    def uno(nombre, vistos=()):
        v = str(vals[nombre])
        m = re.fullmatch(r"\{([\w-]+)\}", v)
        if not m:
            return v
        if m.group(1) in vistos or m.group(1) not in vals:
            raise ValueError(f"referencia rota en token {nombre}: {v}")
        return uno(m.group(1), vistos + (nombre,))
    return {k: uno(k) for k in vals}


def variables(t: dict, tema: str) -> dict:
    vals = {x["name"]: _valor(x, tema) for x in t["color"]["tokens"]}
    vals.update({x["name"]: _valor(x, tema) for x in t["shadow"]["tokens"]})
    return _resolver(vals)


def generar(t: dict) -> str:
    fijas = {x["name"]: x["value"] for g in ("spacing", "radius") for x in t[g]["tokens"]}
    fijas.update({f"font-{k}": v for k, v in t["type"]["families"].items()})
    oscuro, claro = variables(t, "oscuro"), variables(t, "claro")
    solo_claro = {k: v for k, v in claro.items() if oscuro.get(k) != v}

    def bloque(sel, vals, esquema, sangria=""):
        cuerpo = "".join(f"{sangria}  --{k}: {v};\n" for k, v in vals.items())
        return f"{sangria}{sel} {{\n{sangria}  color-scheme: {esquema};\n{cuerpo}{sangria}}}\n"

    out = [f"/* Generado por scripts/tokens.py desde diseno/tokens.json ({t.get('name', '')} v{t.get('version', '')}). "
           "No lo edites a mano. */\n"]
    for f in t["type"].get("fonts", []):
        rango = f"\n  unicode-range: {f['unicodeRange']};" if f.get("unicodeRange") else ""
        archivo = "fuentes/" + Path(f["file"]).name
        out.append(f"@font-face {{\n  font-family: {f['family']};\n  src: url(\"{archivo}\") format(\"woff2\");\n"
                   f"  font-weight: {f['weight']};\n  font-style: {f.get('style', 'normal')};\n  font-display: swap;{rango}\n}}\n")
    out.append(bloque(":root", {**fijas, **oscuro}, "dark"))
    out.append("@media (prefers-color-scheme: light) {\n"
               + bloque(':root:not([data-theme="dark"])', solo_claro, "light", "  ") + "}\n")
    out.append(bloque(':root[data-theme="light"]', solo_claro, "light"))
    for g in t["type"]["groups"]:
        familia = f"var(--font-{g.get('family', 'sans')})"
        for s in g["styles"]:
            lh = s["lineHeight"]
            extra = f" letter-spacing: {s['letterSpacing']};" if s.get("letterSpacing") else ""
            out.append(f".t-{s['name']} {{ font: {s['fontWeight']} {s['fontSize']}/{lh} {familia};{extra} }}\n")
    return "".join(out)


def generar_iconos(carpeta: Path) -> str:
    """Cada SVG del sistema → [[etiqueta, {atributos}], …] para `icono()` (el trazo lo pone la función)."""
    lineas = []
    for f in sorted(carpeta.glob("*.svg")):
        cuerpo = re.search(r"<svg[^>]*>(.*)</svg>", f.read_text(), re.S).group(1)
        partes = []
        for tag, attrs in re.findall(r"<(\w+)([^>]*?)/?>", cuerpo):
            a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
            a = {k: (float(v) if re.fullmatch(r"-?[\d.]+", v) else v) for k, v in a.items()}
            a = {k: (int(v) if isinstance(v, float) and v.is_integer() else v) for k, v in a.items()}
            partes.append([tag, a])
        lineas.append(f'  "{f.stem}": {json.dumps(partes, ensure_ascii=False)},')
    return ("// Generado por scripts/tokens.py desde diseno/iconos/*.svg. No lo edites a mano.\n"
            "// Íconos de línea (trazo 1.75, viewBox 24). Python decide cuál va en cada lugar; aquí solo se pintan.\n"
            "// Siempre decorativos (aria-hidden): al lado va el texto o un title.\n"
            "const ICONOS = {\n" + "\n".join(lineas) + "\n};\n\n"
            "/** SVG de línea 24×24 (`tam` px, hereda `currentColor`). Un nombre desconocido o ausente pinta \"punto\". */\n"
            "function icono(nombre, tam = 18) {\n"
            "  const partes = ICONOS[nombre] || ICONOS.punto;\n"
            "  const svg = sv(\"svg\", { viewBox: \"0 0 24 24\", width: tam, height: tam, class: \"ico-svg\", \"aria-hidden\": \"true\", focusable: \"false\",\n"
            "    fill: \"none\", stroke: \"currentColor\", \"stroke-width\": 1.75, \"stroke-linecap\": \"round\", \"stroke-linejoin\": \"round\" });\n"
            "  for (const [tag, attrs] of partes) svg.append(sv(tag, attrs));\n"
            "  return svg;\n}\n")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    salidas = {SALIDA: generar(json.loads(FUENTE.read_text())), SALIDA_ICONOS: generar_iconos(ICONOS)}
    viejas = [p for p, texto in salidas.items() if not p.exists() or p.read_text() != texto]
    if "--check" in argv:
        for p in viejas:
            print(f"{p.relative_to(ROOT)} no está al día: corre python scripts/tokens.py")
        return 1 if viejas else 0
    for p in viejas:
        p.write_text(salidas[p])
        print(f"escribí {p.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
