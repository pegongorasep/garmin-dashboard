"""Sistema de diseño en código (D2): componentes.css sin valores sueltos, cada componente con su bloque y su ejemplo
en el catálogo, y /diseno solo para el admin."""
import re
from pathlib import Path

from test_web_cuentas import crear_usuario, entrar
from web.app import ESTATICOS_SITE
from web.modelos import Usuario

ROOT = Path(__file__).resolve().parent.parent
CSS = (ROOT / "site" / "componentes.css").read_text()
CATALOGO = (ROOT / "site" / "catalogo.html").read_text()
COMPONENTES_JS = (ROOT / "site" / "componentes.js").read_text()

# Componentes del sistema: carpeta del diseño -> (clase CSS de su bloque, función de DS que lo arma)
COMPONENTES = {
    "BannerCambio": ("banner-cambio", "bannerCambio"),
    "BarraTroteCaminata": ("barra-rw", "barraTroteCaminata"),
    "Boton": ("boton", "boton"),
    "Campo": ("campo", "campo"),
    "Casilla": ("opcion", "opciones"),
    "Chip": ("chip", "chip"),
    "Confirmacion": ("confirmacion", "confirmacion"),
    "Copiar": ("copiar", "copiar"),
    "Desplegable": ("desplegable", "desplegable"),
    "Encabezado": ("encabezado", "encabezado"),
    "ErrorCarga": ("error-carga", "errorCarga"),
    "EstadoVacio": ("vacio", "estadoVacio"),
    "FilaHistorial": ("historial", "filaHistorial"),
    "FilaSesion": ("fila-ses", "filaSesion"),
    "Formulario": ("formulario", "formulario"),
    "GraficaBarras": ("graf", "graficaBarras"),
    "GraficaLinea": ("graf", "graficaLinea"),
    "HojaInBody": ("ib-grupo", "hojaInBody"),
    "Menu": ("menu", "menu"),
    "Pasos": ("pasos", "pasos"),
    "Pestanas": ("segmento", "segmento"),
    "Pie": ("pie", "pie"),
    "Ranking": ("marca-t", "ranking"),
    "Senales": ("senales", "senales"),
    "Silueta": ("slt", "silueta"),
    "Tabla": ("tabla", "tabla"),
}

# Únicos valores crudos que se permiten en componentes.css (decisión explícita; todo lo demás va con var(--token))
COLORES_PERMITIDOS = {("#fff", ".zbar div"), ("rgba(0, 0, 0, .28)", ".menu")}
RADIOS_PX_PERMITIDOS = {"3px", "8px", "3px 3px 0 0"}   # chip de leyenda, tooltip y corchete de la silueta
NOMBRES_DE_COLOR = ("white|black|red|green|blue|gray|grey|yellow|orange|purple|pink|brown|silver|navy|teal|aqua|lime|"
                    "maroon|olive|fuchsia|cyan|magenta|gold|crimson|coral|salmon|tomato|violet|indigo|ivory|beige")


def reglas(css: str):
    """[(selector, cuerpo)] de las reglas sin anidar; las @media/@container se aplanan (sus reglas internas cuentan)."""
    sin_comentarios = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    return [(s.strip(), c) for s, c in re.findall(r"([^{}]+)\{([^{}]*)\}", sin_comentarios)]


def test_sin_colores_ni_radios_sueltos():
    crudos = []
    for selector, cuerpo in reglas(CSS):
        selector = re.sub(r"^@[^{]*\s", "", selector).strip()
        for m in re.finditer(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\([^)]*\)", cuerpo):
            if (m.group(0), selector) not in COLORES_PERMITIDOS:
                crudos.append((selector, m.group(0)))
        for m in re.finditer(rf"(?<![-\w#.])(?:{NOMBRES_DE_COLOR})(?![-\w(])", cuerpo):
            crudos.append((selector, m.group(0)))
        for m in re.finditer(r"border(?:-[a-z]+)*-radius\s*:\s*([^;]+)", cuerpo):
            valor = re.sub(r"var\([^)]*\)", "", m.group(1)).strip()
            if re.search(r"\d+(?:\.\d+)?px", valor) and valor not in RADIOS_PX_PERMITIDOS:
                crudos.append((selector, f"border-radius: {valor}"))
    assert not crudos, crudos
    # y lo permitido sí aparece donde se dijo (si deja de usarse, que se quite de la lista)
    for color, selector in COLORES_PERMITIDOS:
        assert any(color in c and selector == s for s, c in reglas(CSS)), (color, selector)


def test_cada_componente_tiene_bloque_y_ejemplo_en_el_catalogo():
    selectores = " ".join(s for s, _ in reglas(CSS))
    for nombre, (clase, funcion) in COMPONENTES.items():
        assert re.search(rf"\.{re.escape(clase)}(?![\w-])", selectores), f"{nombre}: falta .{clase} en componentes.css"
        assert re.search(rf"\b{funcion}\s*[:=(]|\b{funcion}\s*,", COMPONENTES_JS), f"{nombre}: falta DS.{funcion} en componentes.js"
        assert f"DS.{funcion}(" in CATALOGO, f"{nombre}: falta su ejemplo (DS.{funcion}) en catalogo.html"


def test_catalogo_solo_carga_tokens_y_componentes():
    assert 'href="tokens.css"' in CATALOGO and 'href="componentes.css"' in CATALOGO and "styles.css" not in CATALOGO
    scripts = re.findall(r'<script src="([^"]+)"', CATALOGO)
    assert scripts == ["base.js", "iconos.js", "charts.js", "componentes.js"]
    assert "Sistema de diseño" in CATALOGO and "data-theme" in CATALOGO


def test_diseno_solo_para_admin(web_ctx):
    assert web_ctx.cliente().get("/diseno").status_code == 404      # sin sesión
    crear_usuario(web_ctx, "normal@x.com")
    r = entrar(web_ctx, web_ctx.cliente(), "normal@x.com").get("/diseno")
    assert r.status_code == 404                                       # con sesión, pero no admin
    admin = crear_usuario(web_ctx, "admin@x.com")
    with web_ctx.sesiones() as db:
        db.get(Usuario, admin).es_admin = True
        db.commit()
    r = entrar(web_ctx, web_ctx.cliente(), "admin@x.com").get("/diseno")
    assert r.status_code == 200 and "Sistema de diseño" in r.text and "DS.boton(" in r.text


def test_catalogo_no_es_estatico_y_los_nuevos_si():
    assert "catalogo.html" not in ESTATICOS_SITE
    for nombre in ("base.js", "componentes.js", "componentes.css"):
        assert nombre in ESTATICOS_SITE


def test_orden_de_scripts_del_sitio():
    html = (ROOT / "site" / "index.html").read_text()
    assert re.findall(r'<script src="([^"]+)"', html) == ["base.js", "iconos.js", "charts.js", "componentes.js", "app.js", "vistas.js"]


def test_el_motor_no_publica_el_catalogo_a_los_amigos():
    wf = (ROOT / ".github" / "workflows" / "motor.yml").read_text()
    assert wf.index("rm -f motor/site/catalogo.html") < wf.index("actions/upload-pages-artifact")
