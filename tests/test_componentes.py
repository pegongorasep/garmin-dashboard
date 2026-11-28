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
    "Avatar": ("avatar", "avatar"),
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
    "FilaActividad": ("act-fila", "filaActividad"),
    "CabeceraPersona": ("pers-cab", "cabeceraPersona"),
    "SelectorUnidad": ("unidad", "selectorUnidad"),
    "Semana de una tarjeta de miembro": ("mini-semana", "miniSemana"),
    "PanelComentarios": ("coments", "panelComentarios"),
    "BotonComentarios": ("reac-com", "botonComentarios"),
    "Ranking": ("marca-t", "ranking"),
    "Senales": ("senales", "senales"),
    "Silueta": ("slt", "silueta"),
    "Tabla": ("tabla", "tabla"),
    # Piezas de Hoy que no tenían preview propio (se agregaron en D3a)
    "SelectorSemana": ("sel", "selectorSemana"),
    "AnilloPlan": ("plan", "anilloPlan"),
    "Calendario": ("cal", "calendario"),
    "Numeros": ("tiles", "tiles"),
    "BarraZonas": ("zbar-w", "barraZonas"),
    "Pestanas inferiores": ("tabs", "tabs"),
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


def test_filas_de_botones_y_textos_largos_no_desbordan():
    cuerpo = dict(reglas(CSS))
    assert "flex-wrap: wrap" in cuerpo[".botones"] and "flex-wrap: wrap" in cuerpo[".banner-cambio .bc-acc"]
    assert "overflow-wrap: anywhere" in cuerpo[".error-carga .ec-t, .error-carga .ec-x, .confirmacion p, .confirmacion li, .vacio .vc-t, .vacio .vc-x"]


def _clases_usadas():
    """Clases que arman app.js, vistas.js, componentes.js y charts.js (class: "a b", plantillas con ${}, classList.add) y index.html."""
    usadas = set()
    for nombre in ("app.js", "vistas.js", "componentes.js", "charts.js", "iconos.js"):
        texto = (ROOT / "site" / nombre).read_text()
        for m in re.finditer(r'class(?:Name)?\s*[:=]\s*("([^"]*)"|`([^`]*)`)', texto):
            crudo = m.group(2) if m.group(2) is not None else m.group(3)
            usadas |= {t for t in re.sub(r"\$\{[^}]*\}", " ", crudo).split() if re.fullmatch(r"[A-Za-z][\w-]*", t)}
        usadas |= set(re.findall(r'classList\.add\("([^"]+)"\)', texto))
    for m in re.finditer(r'class="([^"]+)"', (ROOT / "site" / "index.html").read_text()):
        usadas |= set(m.group(1).split())
    return usadas


def _clases_de(css: str):
    return set(re.findall(r"\.([A-Za-z_][\w-]*)", re.sub(r"/\*.*?\*/", "", css, flags=re.S)))


def test_toda_clase_usada_por_el_sitio_tiene_regla():
    reglas = _clases_de(CSS) | _clases_de((ROOT / "site" / "styles.css").read_text())
    assert not sorted(_clases_usadas() - reglas)


def test_styles_css_no_tiene_reglas_muertas():
    codigo = "".join((ROOT / "site" / n).read_text() for n in ("app.js", "vistas.js", "componentes.js", "charts.js", "iconos.js", "index.html"))
    dinamicas = {"g0", "g1", "g2", "g3", "g4", "g5", "z1", "z2", "z3", "z4", "z5", "s1", "s2", "walk", "azul", "aqua", "violeta", "amarillo"}   # se arman con ${…}
    propias = _clases_de((ROOT / "site" / "styles.css").read_text())
    muertas = {c for c in propias if c not in dinamicas and not re.search(rf"(?<![\w-]){re.escape(c)}(?![\w-])", codigo)}
    assert not muertas, muertas


def test_simulador_solo_admin_y_completo(web_ctx):
    from plan import simulador
    assert web_ctx.cliente().get("/admin/simulador").status_code == 404      # sin sesión
    crear_usuario(web_ctx, "normal@x.com")
    assert entrar(web_ctx, web_ctx.cliente(), "normal@x.com").get("/admin/simulador").status_code == 404
    admin = crear_usuario(web_ctx, "admin@x.com")
    with web_ctx.sesiones() as db:
        db.get(Usuario, admin).es_admin = True
        db.commit()
    c = entrar(web_ctx, web_ctx.cliente(), "admin@x.com")
    r = c.get("/admin/simulador")
    assert r.status_code == 200 and "sim-matriz" in r.text and "Umbrales" in r.text
    for p in simulador.cargar_personas():
        assert p["nombre"].replace("'", "&#39;") in r.text
    assert "progresion_pct" in r.text and "<option" not in r.text.split("sim-matriz")[0].split("<h1")[-1]   # umbrales del motor v6 a la vista, sin selector de motor
    assert "/admin/simulador" in c.get("/admin").text


def _args_replace_children(src):
    """Argumentos (texto) de cada `.replaceChildren(...)` con paréntesis balanceados."""
    for m in re.finditer(r"replaceChildren\(", src):
        i, nivel = m.end(), 1
        while i < len(src) and nivel:
            nivel += {"(": 1, ")": -1}.get(src[i], 0)
            i += 1
        yield src[m.end():i - 1]


def test_replacechildren_no_recibe_null_sin_filtrar():
    """`replaceChildren(null)` escribe «null» en la página: si un hijo puede ser null, se filtra."""
    malos = []
    for js in sorted((ROOT / "site").glob("*.js")):
        for args in _args_replace_children(js.read_text()):
            plano, nivel = "", 0   # solo lo que está fuera de (...) y {...}: los hijos directos
            for c in args:
                if c in "({":
                    nivel += 1
                if nivel == 0:
                    plano += c
                if c in ")}":
                    nivel -= 1
            tern_null = re.search(r"\?\s*null\s*:|\?[^?:]*:\s*null\s*[,)\]]", plano)
            if tern_null and ".filter(" not in args:
                malos.append(f"{js.name}: {args[:60]!r}")
    assert not malos, malos
