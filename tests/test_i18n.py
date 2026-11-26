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
