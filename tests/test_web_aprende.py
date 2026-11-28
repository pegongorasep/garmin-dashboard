"""«Aprende»: artículos de teoría en aprende/es/*.yaml (carga, índice, página, 404, login, slug seguro)."""
import pytest

from web import aprende
from ayudas import crear_usuario, entrar

SLUGS = ["zonas", "zona-2", "long-run", "volumen", "semana", "calidad", "trote-caminata", "fuerza",
         "recuperacion", "dolor", "carrera"]


def sesion(ctx, correo="a@x.com"):
    crear_usuario(ctx, correo)
    return entrar(ctx, ctx.cliente(), correo)


def test_estan_los_once_articulos_en_orden():
    assert aprende.slugs() == SLUGS


@pytest.mark.parametrize("slug", SLUGS)
def test_cada_articulo_carga_con_sus_campos(slug):
    a = aprende.articulo(slug)
    assert a and a["titulo"] and a["resumen"] and a["minutos"] >= 1
    assert a["secciones"] and all(s["titulo"] and (s["parrafos"] or s["lista"]) for s in a["secciones"])
    palabras = sum(len(p.split()) for s in a["secciones"] for p in s["parrafos"] + s["lista"])
    assert 300 <= palabras <= 700, palabras


def test_el_indice_los_lista_todos(web_ctx):
    cl = sesion(web_ctx)
    t = cl.get("/aprende").text
    for s in SLUGS:
        assert f'href="/aprende/{s}"' in t
        assert aprende.articulo(s)["titulo"] in t
    assert "min" in t


def test_la_pagina_del_articulo_se_pinta(web_ctx):
    cl = sesion(web_ctx)
    r = cl.get("/aprende/zona-2")
    assert r.status_code == 200
    assert aprende.articulo("zona-2")["titulo"] in r.text
    assert "Esto no es consejo médico: si algo duele, para." in r.text


def test_slug_desconocido_da_404(web_ctx):
    cl = sesion(web_ctx)
    assert cl.get("/aprende/no-existe").status_code == 404


def test_pide_sesion(web_ctx):
    anon = web_ctx.cliente()
    assert anon.get("/aprende").headers["location"] == "/entrar"
    assert anon.get("/aprende/zonas").headers["location"] == "/entrar"


@pytest.mark.parametrize("slug", ["../config", "..%2Fconfig", "Zonas", "zonas.yaml", "a/b", "zonas%00"])
def test_el_slug_no_puede_escapar_de_la_carpeta(web_ctx, slug):
    assert aprende.articulo(slug) is None
    cl = sesion(web_ctx)
    assert cl.get(f"/aprende/{slug}").status_code in (404, 307, 308)


def test_en_ingles_muestra_el_articulo_en_espanol_con_aviso(web_ctx):
    cl = sesion(web_ctx)
    cl.cookies.set("idioma", "en")
    r = cl.get("/aprende/zonas")
    assert aprende.articulo("zonas")["titulo"] in r.text
    assert "only available in Spanish for now" in r.text
    assert "only available in Spanish for now" in cl.get("/aprende").text
