"""Cambios: aceptar y deshacer en orden por área, nota de la IA, detalle colapsable y ✕ del banner de InBody."""
import copy
import json

import pytest

from web import cambios
from web.modelos import Ajustes, Cambio, Usuario
from ayudas import crudo, cuerpo, listo, llamar, rpc, tok, token_para


def _titulo(db, uid, titulo, via="ia", nota=None):
    u = db.get(Usuario, uid)
    cfg = copy.deepcopy(db.get(Ajustes, uid).config)
    cfg["perfil"]["titulo"] = titulo
    return cambios.aplicar_cambio(db, u, u, via, f"Título {titulo}", {"ajustes": cfg}, nota=nota).id


def _inbody(db, uid, peso):
    u = db.get(Usuario, uid)
    return cambios.aplicar_cambio(db, u, u, "ia", f"InBody {peso}", {"inbody": [{"fecha": "2026-11-20", "peso_kg": peso}]}).id


def _botones(cl, cid):
    """(tiene Entendido, tiene Deshacer) de la tarjeta del cambio."""
    html = cl.get("/historial").text
    return (f"/historial/{cid}/visto" in html, f"/historial/{cid}/deshacer" in html)


def test_uno_dos_tres_aceptar_y_deshacer_en_orden(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        a, b, c = (_titulo(db, uid, x) for x in ("1", "2", "3"))
    assert _botones(cl, a) == (True, False)
    assert _botones(cl, b) == (False, False)
    assert _botones(cl, c) == (False, True)
    html = cl.get("/historial").text
    assert "Acepta primero el anterior" in html and "Deshaz primero el más reciente" in html
    # el servidor no deja aceptar fuera de orden ni deshacer fuera de orden
    cl.post(f"/historial/{b}/visto", data={"csrf": tok(cl)})
    cl.post(f"/historial/{a}/deshacer", data={"csrf": tok(cl)})
    with web_ctx.sesiones() as db:
        assert not db.get(Cambio, b).visto and db.get(Cambio, a).deshecho_por is None
    cl.post(f"/historial/{a}/visto", data={"csrf": tok(cl)})
    cl.post(f"/historial/{c}/deshacer", data={"csrf": tok(cl)})
    assert crudo(web_ctx, uid)["perfil"]["titulo"] == "2"
    assert _botones(cl, b) == (True, True)
    cl.post(f"/historial/{b}/visto", data={"csrf": tok(cl)})
    assert _botones(cl, a) == (False, False)
    with web_ctx.sesiones() as db:
        assert db.get(Cambio, c).deshecho_por is not None and db.get(Cambio, c).visto


def test_inbody_pendiente_no_bloquea_el_plan_y_edicion_propia_bloquea_deshacer(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        i = _inbody(db, uid, 70.0)
        a = _titulo(db, uid, "1")
    assert _botones(cl, a)[0] and _botones(cl, i)[0]
    with web_ctx.sesiones() as db:
        _titulo(db, uid, "2", via="web")   # edición propia por la web encima
    assert _botones(cl, a)[1] is False
    with web_ctx.sesiones() as db:
        with pytest.raises(cambios.NoSeDeshace) as ex:
            cambios.deshacer(db, db.get(Usuario, uid), a)
        assert ex.value.clave == "err.orden_deshacer"


def test_nota_detalle_colapsable_y_banner_de_inbody(web_ctx):
    uid, cl = listo(web_ctx)
    larga = "<b>línea</b>\n" * 8
    with web_ctx.sesiones() as db:
        i = _inbody(db, uid, 70.0)
        t = _titulo(db, uid, "x", nota=larga)
        assert db.get(Cambio, t).nota == larga.strip()
    html = cl.get("/historial").text
    assert "&lt;b&gt;línea" in html and "<b>línea" not in html
    assert 'class="nota-chk"' in html and "Ver más" in html and "Ver detalle" in html
    assert 'class="hist-detalle" open' not in html
    av = {a["id"]: a for a in cl.get("/data.json").json()["avisos"]}
    assert av[i].get("cerrable") is True and "cerrable" not in av[t]
    cl.post(f"/historial/{i}/visto", data={"csrf": tok(cl)})
    assert i not in {a["id"] for a in cl.get("/data.json").json()["avisos"]}


def test_inbody_mas_nuevo_no_es_cerrable_hasta_aceptar_el_viejo(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        i, j = _inbody(db, uid, 70.0), _inbody(db, uid, 71.0)
    av = {a["id"]: a for a in cl.get("/data.json").json()["avisos"]}
    assert av[i].get("cerrable") is True and "cerrable" not in av[j]


def test_mcp_resumen_nota_y_regla_de_orden(web_ctx):
    uid, cl = listo(web_ctx)
    tk = token_para(web_ctx, uid)
    with web_ctx.cliente() as c:
        tools = {t["name"]: t for t in cuerpo(rpc(c, tk, "tools/list"))["result"]["tools"]}
        for n in ("agregar_carrera", "agregar_evento", "editar_sesion", "repetir_semana", "registrar_inbody", "deshacer"):
            assert "resumen" in tools[n]["inputSchema"]["properties"] and "Siempre manda `resumen`" in tools[n]["description"]
        e1, r1 = llamar(c, tk, "registrar_inbody", fecha="2026-11-20", peso_kg=70, resumen="Anoté tu peso.\nGracias.")
        e2, r2 = llamar(c, tk, "registrar_inbody", fecha="2026-11-21", peso_kg=71)
        assert not e1 and not e2
        id1, id2 = json.loads(r1)["cambio_id"], json.loads(r2)["cambio_id"]
        assert "no se puede deshacer" not in json.loads(r2)["para_deshacer"]
        e, _ = llamar(c, tk, "deshacer", cambio_id=id1)
        assert e
        _, h = llamar(c, tk, "historial")
        por_id = {x["id"]: x for x in json.loads(h)["cambios"]}
        assert por_id[id1]["nota"] == "Anoté tu peso.\nGracias." and por_id[id2]["nota"] is None
        assert por_id[id1]["se_puede_deshacer"] is False and por_id[id2]["se_puede_deshacer"] is True
