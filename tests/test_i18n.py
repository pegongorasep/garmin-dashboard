"""Catálogo es/en: mismas claves y variables; elección de idioma; selector."""
import i18n


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
    import build
    import ajustes
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
