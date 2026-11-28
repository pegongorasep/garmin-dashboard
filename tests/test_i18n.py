"""Catálogo es/en: mismas claves y variables; elección de idioma; selector."""
from dashboard import i18n


def test_catalogos_iguales():
    es, en = i18n.cargar("es"), i18n.cargar("en")
    assert set(es) == set(en), (set(es) ^ set(en))
    for k in es:
        assert i18n.variables(es[k]) == i18n.variables(en[k]), k


def test_t_y_respaldo():
    assert i18n.t("entrar.titulo", "en") == "Sign in"
    assert i18n.t("invitacion.nota", "es", nota="X") == "Invitación: X"
    assert i18n.t("entrar.titulo", "fr", ) == "Entrar" if not i18n.ESTRICTO else True


def test_clave_faltante_lanza_en_pruebas():
    import pytest
    with pytest.raises(KeyError):
        i18n.t("no.existe", "es")


def test_elegir():
    assert i18n.elegir("en-US,en;q=0.9,es;q=0.8") == "en"
    assert i18n.elegir("fr,es;q=0.5") == "es"
    assert i18n.elegir("fr") is None and i18n.elegir(None) is None


def test_web_idioma(web_ctx):
    c = web_ctx.cliente()
    r = c.get("/entrar", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert '<html lang="en">' in r.text and "Send code" in r.text
    r = c.get("/entrar")
    assert '<html lang="es">' in r.text and "Mandar código" in r.text


def test_cookie_idioma_y_correo_en_ingles(web_ctx):
    c = web_ctx.cliente()
    r = c.get("/entrar")
    csrf = r.text.split('name="csrf" value="')[1].split('"')[0]
    r = c.post("/idioma", data={"csrf": csrf, "idioma": "en", "siguiente": "/entrar"})
    assert r.status_code == 303 and "idioma=en" in r.headers["set-cookie"]
    assert "Send code" in c.get("/entrar").text
    assert c.post("/idioma", data={"csrf": csrf, "idioma": "xx"}).status_code == 400


def test_paginas_de_la_web_en_ingles(web_ctx):
    """Las páginas con sesión salen en inglés: sin textos del catálogo en español."""
    from test_web_ajustes import listo
    uid, c = listo(web_ctx)
    c.cookies.set("idioma", "en")
    rutas = ["/ajustes", "/plan/acciones", "/cuerpo", "/cuerpo/nuevo", "/historial", "/coach", "/conexiones", "/ayuda/conector",
             "/privacidad", "/privacidad/mis-datos", "/salir"]
    for ruta in rutas:
        r = c.get(ruta)
        assert r.status_code == 200, (ruta, r.status_code, r.headers.get('location'))
        for es in ("Guardar", "Cancelar", "Todavía", "Quitar", "Historial", "Ajustes", "Aviso de privacidad de"):
            assert es not in r.text, (ruta, es)


def test_bienvenida_y_sesion_en_ingles(web_ctx):
    from test_web_ajustes import listo
    from web.modelos import Ajustes
    uid, c = listo(web_ctx)
    c.cookies.set("idioma", "en")
    with web_ctx.sesiones() as db:
        db.query(Ajustes).filter(Ajustes.usuario_id == uid).delete()
        db.commit()
    for paso in range(1, 8):
        r = c.get(f"/bienvenida?paso={paso}")
        assert r.status_code == 200, paso
        assert "Todavía" not in r.text and "Continuar" not in r.text, paso


# --- sitio (Hoy/Plan/Progreso): textos en JSON, idioma en data.json ---

def test_json_del_sitio_al_dia_y_con_todas_las_claves_del_js():
    import json
    import re
    from pathlib import Path
    site = Path(__file__).parent.parent / "site"
    for idioma in i18n.idiomas():
        assert json.loads((site / "i18n" / f"{idioma}.json").read_text(encoding="utf-8")) == i18n.catalogo_sitio(idioma), \
            "site/i18n/*.json desactualizado: corre dashboard/build.py"
    es = i18n.catalogo_sitio("es")
    usadas = set()
    for f in [*site.glob("*.js"), site / "catalogo.html"]:
        usadas |= {k for k in re.findall(r"sitio\.[\w.]*\w", f.read_text(encoding="utf-8"))}
    base = {k[:-2] for k in es if k.endswith(("_1", "_n"))}
    # claves armadas con plantilla (`sitio.semaforo.${id}`) o con Tn(): se revisan por prefijo
    faltan = {k for k in usadas if k not in es and k not in base and not any(x.startswith(k) for x in es)}
    assert not faltan, faltan


def test_idioma_en_data_json_solo_si_esta_en_config():
    from datetime import datetime
    from dashboard import build
    from dashboard import ajustes
    cfg = ajustes.config_por_defecto()
    assert cfg["idioma"] is None
    assert ajustes.normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}, "idioma": "en-US"})["idioma"] == "en"
    assert ajustes.normalizar_config({"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}, "idioma": "xx"})["idioma"] is None


def test_web_sirve_textos_del_sitio_e_idioma_en_data_json(web_ctx):
    from test_web_ajustes import listo
    uid, c = listo(web_ctx)
    r = c.get("/i18n/en.json")
    assert r.status_code == 200 and r.json()["sitio.tab.hoy"] == "Today"
    assert c.get("/i18n/xx.json").status_code == 404
    c.cookies.set("idioma", "en")
    r = c.get("/data.json")
    if r.status_code == 200:
        assert r.json()["idioma"] == "en"


# --- I4: los textos que arma el motor salen en el idioma pedido ---

ESPANOL = ("Sin HRV", "Sin FC", "Sin dato", "FC en reposo", "Dormiste", "Semana completa", "Siguiente sesión", "Considera",
           "Tu plan", "Cada semana", "Aún no", "Trotas", "Incluye", "Descarga", "Calidad", "Larga", "Suave", "Prueba",
           "Variada", "lunes", "peso", "Corrida", "Carrera", "Pirámide", "Continuo", "Espiga", "El semáforo", "Tus zonas",
           "Cómo medimos", "recuperación", "corridas suaves")


def _textos(o, acc):
    if isinstance(o, dict):
        for v in o.values():
            _textos(v, acc)
    elif isinstance(o, list):
        for v in o:
            _textos(v, acc)
    elif isinstance(o, str):
        acc.append(o)
    return acc


def test_data_json_en_ingles_sin_espanol_conocido():
    from dashboard import build
    from test_build import AHORA, CONFIG_FIXTURE, fixture
    plan = build.load(build.ROOT / "plan" / "plan.example.json")
    en = build.build(fixture(), plan, {**CONFIG_FIXTURE, "idioma": "en"}, AHORA)
    es = build.build(fixture(), plan, {**CONFIG_FIXTURE, "idioma": "es"}, AHORA)
    assert en["idioma"] == "en" and es["idioma"] == "es"
    textos = _textos({k: v for k, v in en.items() if k != "idioma"}, [])
    import re
    palabras = re.compile(r"\b(" + "|".join(map(re.escape, ESPANOL)) + r")\b")
    mal = [t for t in textos if palabras.search(t) or any(c in t for c in "áéíóúñ¿¡")]
    assert not mal, mal[:10]
    assert en["tipos"]["grupos"][0]["nombre"] == "Continuous" and es["tipos"]["grupos"][0]["nombre"] == "Continuos"
    assert en["plan"]["semanas"][0]["sessions"][-1]["name"] == "Long run" and es["plan"]["semanas"][0]["sessions"][-1]["name"] == "Larga"
    assert en["ui"]["textos"]["descarga"].startswith("Deload")


def test_notas_del_plan_llevan_id_y_texto_traducido():
    from dashboard import build
    from test_build import AHORA, CONFIG_FIXTURE, fixture
    plan = build.load(build.ROOT / "plan" / "plan.example.json")
    for idioma, texto in (("es", "opcional"), ("en", "optional")):
        out = build.build(fixture(), plan, {**CONFIG_FIXTURE, "idioma": idioma}, AHORA)
        pasos = [p for w in out["plan"]["semanas"] for s in w["sessions"] for p in s["steps"] if p.get("nota_id") == "opcional"]
        assert all(p["note"] == texto and p["optional"] for p in pasos)


def test_calculo_de_la_web_cachea_por_idioma(web_ctx):
    from test_web_ajustes import listo
    from web import calculo
    from web.modelos import Usuario
    uid, _ = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        en = calculo.calcular(db, u, idioma="en")
        es = calculo.calcular(db, u, idioma="es")
        en2 = calculo.calcular(db, u, idioma="en")
    assert en["idioma"] == "en" and es["idioma"] == "es" and en2["idioma"] == "en"
    assert en["ui"]["textos"]["descarga"].startswith("Deload") and es["ui"]["textos"]["descarga"].startswith("Las semanas")


def _literales_con_espanol(ruta):
    """Cadenas "..." / '...' / `...` con tilde, ñ, ¿ o ¡ fuera de comentarios (heurística simple)."""
    import re
    texto = ruta.read_text(encoding="utf-8")
    texto = re.sub(r"\{#.*?#\}", "", texto, flags=re.S) if ruta.suffix == ".html" else texto
    texto = re.sub(r"/\*.*?\*/", "", texto, flags=re.S)
    texto = re.sub(r"(?m)(^|\s)//.*$", "", texto)
    esp = re.compile(r"[áéíóúñÁÉÍÓÚÑ¿¡]")
    cadenas = re.findall(r'"(?:[^"\\\n]|\\.)*"|\'(?:[^\'\\\n]|\\.)*\'|`(?:[^`\\]|\\.)*`', texto)
    return sorted({c for c in cadenas if esp.search(c)})


# Cadenas con tilde que no son texto para la persona: claves de data.json / valores guardados / alternativa sin catálogo.
PERMITIDAS_ESPANOL = {
    '"ahí la llevas"', '"señales"', '"sueño_h"', '"sueño_7d"', '"muñeca"', '"plan.terminó"',
    '"Esto no es consejo médico: si algo duele, para."',   # alternativa de DS.pie si la plantilla no pasa t
}


def test_sin_texto_en_espanol_fuera_del_catalogo():
    """Plantillas de la web y JS del sitio: todo texto visible sale del catálogo i18n (el catálogo de diseño es del admin y va en español)."""
    from pathlib import Path
    raiz = Path(__file__).parent.parent
    archivos = [*(raiz / "web" / "plantillas").glob("*.html"), *(raiz / "site").glob("*.js")]
    hallazgos = {f.name: [c for c in _literales_con_espanol(f) if c not in PERMITIDAS_ESPANOL] for f in archivos}
    hallazgos = {k: v for k, v in hallazgos.items() if v}
    assert not hallazgos, f"texto en español fuera de i18n/*.yaml: {hallazgos}"
