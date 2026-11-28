"""F3: ajustes, historial y deshacer, avisos, InBody."""
import copy
import json
from datetime import datetime, timezone

import pytest

import planes_v6
from dashboard import validar
from dashboard.ajustes import normalizar_config
from test_web_cuentas import CONFIG, csrf_de, entrar, post
from web import cambios
from web.modelos import Ajustes, Cambio, Coach, Consentimiento, DatoGarmin, InBody, Plan, Usuario
from web.privacidad import VERSION_AVISO

HOY = datetime(2026, 11, 25, 18, 0, tzinfo=timezone.utc)   # miércoles de la semana 3 (el plan empieza el 2026-11-09)


def tok(cl):
    return csrf_de(cl.get("/ajustes").text)


def listo(ctx, correo="a@x.com", con_plan=True):
    """Usuario con consentimiento, ajustes y plan; devuelve (id, cliente con sesión)."""
    ctx.app.state.reloj = lambda: HOY
    with ctx.sesiones() as db:
        u = Usuario(correo=correo, nombre="Ana", apellido="Prueba")
        db.add(u)
        db.commit()
        db.add(Ajustes(usuario_id=u.id, config=copy.deepcopy(CONFIG)))
        db.add(Consentimiento(usuario_id=u.id, version_aviso=VERSION_AVISO))
        db.add(DatoGarmin(usuario_id=u.id, tipo="dia", clave="2026-11-24",   # algo de datos: si no, la tarjeta de hoy es «primera sincronización»
                          contenido={"calendarDate": "2026-11-24", "heartRate": {"restingValue": 55}}))
        if con_plan:
            db.add(Plan(usuario_id=u.id, plan=planes_v6.generar(normalizar_config(CONFIG))))
        db.commit()
        uid = u.id
    return uid, entrar(ctx, ctx.cliente(), correo)


def form_ajustes(**cambia):
    """Formulario de Ajustes (solo lo general)."""
    base = {"titulo": "Mi entreno", "zona": "America/Merida", "edad": "29", "fc_max": "189", "sensor": "banda",
            "inbody": "on"}
    base.update(cambia)
    return {k: v for k, v in base.items() if v != ""} | {k: "" for k in ("fc_max",) if base[k] == ""}


def guardar(cl, url="/ajustes", **cambia):
    r = cl.get(url)
    return cl.post(url, data={"csrf": csrf_de(r.text), **form_ajustes(**cambia)})


def crudo(ctx, uid):
    with ctx.sesiones() as db:
        return copy.deepcopy(db.get(Ajustes, uid).config)


def plan_de(ctx, uid):
    with ctx.sesiones() as db:
        return copy.deepcopy(db.get(Plan, uid).plan)


def test_ajustes_se_ve_con_los_valores(web_ctx):
    _, cl = listo(web_ctx)
    r = cl.get("/ajustes")
    assert r.status_code == 200 and 'name="titulo"' in r.text and 'type="password"' not in r.text
    assert 'name="nivel"' not in r.text and 'name="inicio"' not in r.text   # la corrida vive en «Ajustar mi plan»
    r = cl.get("/plan/acciones")
    assert r.status_code == 200 and 'name="nivel"' not in r.text and "Rehacer mi plan" not in r.text and "motor anterior" not in r.text
    assert 'action="/plan/nuevo"' in r.text or 'href="/plan/nuevo"' in r.text   # cambiar el plan = armar uno nuevo con el motor v6
    assert cl.post("/plan/rehacer", data={"csrf": tok(cl)}).status_code in (404, 405)   # el formulario del motor anterior ya no existe
    assert 'name="sensor"' not in cl.get("/ajustes").text                       # el pulso se detecta por actividad


def test_cambio_sin_plan_deja_historial_y_se_deshace_exacto(web_ctx):
    uid, cl = listo(web_ctx)
    antes, plan_antes = crudo(web_ctx, uid), plan_de(web_ctx, uid)
    r = guardar(cl, titulo="Otro título", sensor="muñeca")
    assert r.status_code == 303 and r.headers["location"] == "/ajustes?ok=1"
    despues = crudo(web_ctx, uid)
    assert despues["perfil"]["titulo"] == "Otro título" and despues["perfil"]["sensor"] == "muñeca"
    assert plan_de(web_ctx, uid) == plan_antes   # el título no rehace el plan
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
        assert c.via == "web" and c.autor_id == uid and c.antes["ajustes"] == antes and c.despues["ajustes"] == despues
        assert "título" in c.descripcion and c.visto
        cid = c.id
    assert "Ajustes: cambió el título, el sensor" in cl.get("/historial").text
    r = cl.post(f"/historial/{cid}/deshacer", data={"csrf": tok(cl)})
    assert r.status_code == 303
    assert crudo(web_ctx, uid) == antes   # exacto
    with web_ctx.sesiones() as db:
        assert db.get(Cambio, cid).deshecho_por is not None
        assert db.query(Cambio).count() == 2
    # no se deshace dos veces
    r = cl.post(f"/historial/{cid}/deshacer", data={"csrf": tok(cl)})
    assert "ya se deshizo" in r.text and crudo(web_ctx, uid) == antes


def test_errores_junto_al_campo(web_ctx):
    uid, cl = listo(web_ctx)
    r = guardar(cl, zona="Marte/Base")
    assert r.status_code == 400 and "zona" in r.text
    assert crudo(web_ctx, uid) == CONFIG
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).count() == 0


def test_sin_cambios_no_guarda_nada(web_ctx):
    uid, cl = listo(web_ctx)
    r = guardar(cl)
    assert r.status_code == 303 and "ok=sin" in r.headers["location"]
    with web_ctx.sesiones() as db:
        assert db.query(Cambio).count() == 0 and db.get(Ajustes, uid).version == 1


def test_post_sin_csrf_es_403(web_ctx):
    _, cl = listo(web_ctx)
    cl.get("/ajustes")
    assert cl.post("/ajustes", data=form_ajustes()).status_code == 403
    assert cl.post("/historial/visto", data={}).status_code == 403
    assert cl.post("/cuerpo/nuevo", data={"fecha": "2026-11-20", "peso_kg": "80"}).status_code == 403


def test_sin_sesion_va_a_entrar(web_ctx):
    listo(web_ctx)
    cl = web_ctx.cliente()
    for url in ("/ajustes", "/historial", "/cuerpo", "/cuerpo/nuevo", "/plan"):
        assert cl.get(url).headers["location"] == "/entrar"


def test_otro_usuario_recibe_404_en_todo(web_ctx):
    uid_a, cl_a = listo(web_ctx, "a@x.com")
    uid_b, cl_b = listo(web_ctx, "b@x.com")
    guardar(cl_a, titulo="De A")
    with web_ctx.sesiones() as db:
        cid = db.query(Cambio).one().id
    for url in (f"/a/{uid_a}/ajustes", f"/a/{uid_a}/historial", f"/a/{uid_a}/cuerpo", f"/a/{uid_a}/cuerpo/nuevo", f"/a/{uid_a}/plan"):
        assert cl_b.get(url).status_code == 404
    csrf = tok(cl_b)
    assert cl_b.post(f"/a/{uid_a}/ajustes", data={"csrf": csrf, **form_ajustes(titulo="Hackeado")}).status_code == 404
    assert cl_b.post(f"/historial/{cid}/deshacer", data={"csrf": csrf}).status_code == 404   # cambio ajeno
    assert cl_b.post(f"/a/{uid_a}/historial/{cid}/deshacer", data={"csrf": csrf}).status_code == 404
    assert cl_b.post(f"/a/{uid_a}/plan/viaje", data={"csrf": csrf, "desde": "2026-12-01", "hasta": "2026-12-05"}).status_code == 404
    assert crudo(web_ctx, uid_a)["perfil"]["titulo"] == "De A"
    with web_ctx.sesiones() as db:
        assert db.get(Cambio, cid).deshecho_por is None


def test_aplicar_cambio_exige_permiso(web_ctx):
    uid_a, _ = listo(web_ctx, "a@x.com")
    uid_b, _ = listo(web_ctx, "b@x.com")
    with web_ctx.sesiones() as db:
        a, b = db.get(Usuario, uid_a), db.get(Usuario, uid_b)
        with pytest.raises(cambios.SinPermiso):
            cambios.aplicar_cambio(db, a, b, "web", "x", {"ajustes": {}})
        with pytest.raises(cambios.SinPermiso):
            cambios.aplicar_cambio(db, a, None, "web", "x", {"ajustes": {}})
        assert db.query(Cambio).count() == 0 and db.get(Ajustes, uid_a).config == CONFIG


def test_el_coach_edita_y_el_atleta_ve_aviso_con_deshacer(web_ctx):
    uid_a, cl_a = listo(web_ctx, "atleta@x.com")
    uid_c, cl_c = listo(web_ctx, "coach@x.com")
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid_c).apodo = "Pedro"
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    antes = crudo(web_ctx, uid_a)
    r = guardar(cl_c, f"/a/{uid_a}/ajustes", titulo="Semana de Pedro")
    assert r.status_code == 303 and r.headers["location"] == f"/a/{uid_a}/ajustes?ok=1"
    with web_ctx.sesiones() as db:
        c = db.query(Cambio).one()
        assert c.via == "coach" and c.autor_id == uid_c and c.atleta_id == uid_a and not c.visto
    d = cl_a.get("/data.json").json()
    assert validar.problemas(d) == []
    assert len(d["avisos"]) == 1 and d["avisos"][0]["texto"] == "Pedro cambió tus ajustes" and d["avisos"][0]["url"] == f"/historial#c{d['avisos'][0]['id']}"
    assert "avisos" not in cl_c.get("/data.json").json()
    # el atleta deshace desde el historial
    cl_a.post(f"/historial/{d['avisos'][0]['id']}/deshacer", data={"csrf": tok(cl_a)})
    assert crudo(web_ctx, uid_a) == antes
    assert "avisos" not in cl_a.get("/data.json").json()   # deshecho: ya no avisa
    # otro cambio del coach, el atleta lo marca visto
    guardar(cl_c, f"/a/{uid_a}/ajustes", titulo="Otra vez")
    assert len(cl_a.get("/data.json").json()["avisos"]) == 1
    cl_a.post("/historial/visto", data={"csrf": tok(cl_a)})
    assert "avisos" not in cl_a.get("/data.json").json()
    # el coach pierde el acceso: 404 de inmediato
    with web_ctx.sesiones() as db:
        db.query(Coach).delete()
        db.commit()
    assert cl_c.get(f"/a/{uid_a}/ajustes").status_code == 404


def test_avisos_de_la_ia_los_ve_el_atleta(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        cambios.aplicar_cambio(db, u, u, "ia", "Agregó un viaje", {"ajustes": {**CONFIG, "perfil": {**CONFIG["perfil"], "titulo": "IA"}}})
    d = cl.get("/data.json").json()
    assert d["avisos"][0]["texto"] == "Tu IA cambió tus ajustes"


# --- InBody ---

def form_cuerpo(**c):
    return {"fecha": "2026-11-20", "peso_kg": "82,5", "pgc": "20.1", "mme_kg": "38", "hora": "08:30", **c}


def test_inbody_alta_edicion_borrado_y_deshacer(web_ctx):
    uid, cl = listo(web_ctx)
    post_c = lambda url, **c: cl.post(url, data={"csrf": csrf_de(cl.get("/cuerpo/nuevo").text), **c})  # noqa: E731
    assert "Todavía no hay mediciones" in cl.get("/cuerpo").text
    r = post_c("/cuerpo/nuevo", **form_cuerpo())
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        (f,) = db.query(InBody).all()
        assert f.fecha == "2026-11-20" and f.valores["peso_kg"] == 82.5 and f.valores["pgc"] == 20.1
        c = db.query(Cambio).one()
        assert c.antes["inbody"] == [] and len(c.despues["inbody"]) == 1 and "InBody" in c.descripcion
    d = cl.get("/data.json").json()
    assert d["composicion"]["ultima"]["peso_kg"] == 82.5 and validar.problemas(d) == []
    # misma fecha otra vez: error
    assert post_c("/cuerpo/nuevo", **form_cuerpo()).status_code == 400
    # validaciones
    for malo in ({"peso_kg": ""}, {"peso_kg": "abc"}, {"peso_kg": "5"}, {"fecha": "ayer"}, {"pgc": "300"}):
        assert post_c("/cuerpo/nuevo", **form_cuerpo(**{"fecha": "2026-11-21", **malo})).status_code == 400
    # solo peso: se guarda, pero todavía no sale en el dashboard
    assert post_c("/cuerpo/nuevo", fecha="2026-11-22", peso_kg="81").status_code == 303
    assert "Falta % de grasa" in cl.get("/cuerpo").text
    d = cl.get("/data.json").json()
    assert [x["fecha"] for x in d["composicion"]["mediciones"]] == ["2026-11-20"]
    # editar
    r = cl.post("/cuerpo/2026-11-20/editar", data={"csrf": csrf_de(cl.get("/cuerpo/2026-11-20/editar").text), **form_cuerpo(peso_kg="83")})
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        assert {f.fecha: f.valores["peso_kg"] for f in db.query(InBody)} == {"2026-11-20": 83, "2026-11-22": 81}
    # borrar y deshacer
    r = cl.post("/cuerpo/2026-11-22/borrar", data={"csrf": csrf_de(cl.get("/cuerpo").text)})
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        assert db.query(InBody).count() == 1
        cid = db.query(Cambio).order_by(Cambio.id.desc()).first().id
    cl.post(f"/historial/{cid}/deshacer", data={"csrf": tok(cl)})
    with web_ctx.sesiones() as db:
        assert db.query(InBody).count() == 2
    assert cl.get("/cuerpo/2026-01-01/editar").status_code == 404


def test_inbody_de_otro_usuario_404(web_ctx):
    uid_a, cl_a = listo(web_ctx, "a@x.com")
    uid_b, cl_b = listo(web_ctx, "b@x.com")
    cl_a.post("/cuerpo/nuevo", data={"csrf": csrf_de(cl_a.get("/cuerpo/nuevo").text), **form_cuerpo()})
    csrf = csrf_de(cl_b.get("/cuerpo/nuevo").text)
    assert cl_b.get(f"/a/{uid_a}/cuerpo").status_code == 404
    assert cl_b.post(f"/a/{uid_a}/cuerpo/2026-11-20/borrar", data={"csrf": csrf}).status_code == 404
    assert cl_b.post(f"/a/{uid_a}/cuerpo/nuevo", data={"csrf": csrf, **form_cuerpo(fecha="2026-11-23")}).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.query(InBody).count() == 1
    assert "2026-11-20" not in cl_b.get("/cuerpo").text


def test_el_menu_de_la_web_trae_las_nuevas_paginas(web_ctx):
    _, cl = listo(web_ctx)
    urls = [i["url"] for i in cl.get("/data.json").json()["ui"]["menu"]]
    assert urls == ["/ajustes", "/historial", "/cuerpo", "/coach", "/aprende", "/privacidad", "/salir"]


def test_ajustes_de_pedro_sin_tocar_no_cambian_nada(web_ctx):
    """El formulario no pierde ni agrega nada de la config real de Pedro (categorías propias, fechas, plan editado a mano)."""
    from pathlib import Path
    from dashboard.ajustes import leer_config_yaml
    raiz = Path(__file__).parent.parent
    if not (raiz / "config.yaml").exists():
        pytest.skip("no hay archivos personales")
    from web import ajustes_web as aw
    pedro = json.loads(json.dumps(leer_config_yaml(raiz / "config.yaml"), default=str))
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        db.get(Ajustes, uid).config = copy.deepcopy(pedro)
        db.commit()
        u = db.get(Usuario, uid)
        v = aw.valores_form(pedro, u)
    general = {"csrf": tok(cl), "titulo": v["titulo"], "zona": v["zona"], "sensor": v["sensor"]}
    if v["inbody"]:
        general["inbody"] = "on"
    r = cl.post("/ajustes", data=general)
    assert r.status_code == 303 and "ok=sin" in r.headers["location"], r.text[:500]
    assert crudo(web_ctx, uid) == pedro


def test_descargar_plan_para_el_reloj(web_ctx):
    uid_a, cl_a = listo(web_ctx, "atleta@x.com")
    uid_c, cl_c = listo(web_ctx, "coach@x.com")
    uid_o, cl_o = listo(web_ctx, "otro@x.com")
    r = cl_a.get("/plan/reloj.json")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    assert r.json()["weeks"] and "Descargar plan para el reloj" in cl_a.get("/plan/acciones").text
    assert cl_o.get(f"/a/{uid_a}/plan/reloj.json").status_code == 404
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    assert cl_c.get(f"/a/{uid_a}/plan/reloj.json").json() == r.json()
    assert web_ctx.cliente().get("/plan/reloj.json", follow_redirects=False).status_code == 303


def test_ajustes_ya_no_edita_fc_max_ni_edad(web_ctx):
    uid, cl = listo(web_ctx)
    html = cl.get("/ajustes").text
    assert 'name="titulo"' in html and 'name="fc_max"' not in html and 'name="edad"' not in html
    assert guardar(cl, edad="", fc_max="").status_code in (200, 302, 303)
    assert crudo(web_ctx, uid)["perfil"].get("fc_max") == 189   # lo guardado se conserva


def test_guardar_ajustes_nunca_rehace_el_plan(web_ctx):
    """Guardar en Ajustes no pide confirmación ni toca el plan; la pierna ya no está ahí."""
    uid, cl = listo(web_ctx)
    plan0 = plan_de(web_ctx, uid)
    assert 'name="pierna"' not in cl.get("/ajustes").text
    r = guardar(cl, pierna=["lun", "jue"], titulo="Otro")
    assert r.status_code == 303 and r.headers["location"] == "/ajustes?ok=1"
    assert plan_de(web_ctx, uid) == plan0 and crudo(web_ctx, uid)["perfil"]["titulo"] == "Otro"
    assert "dias_pierna" not in crudo(web_ctx, uid).get("actividades", {}) or crudo(web_ctx, uid)["actividades"]["dias_pierna"] == CONFIG.get("actividades", {}).get("dias_pierna")


def test_hoy_saludo_el_nombre_va_en_la_pagina_y_nunca_en_data_json(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        db.get(Usuario, uid).nombre = 'Ana"<b>'
        db.commit()
    r = cl.get("/")
    assert 'data-nombre="Ana&quot;&lt;b&gt;"' in r.text and "no-store" in r.headers["cache-control"]
    datos = cl.get("/data.json")
    assert "Ana" not in datos.text and validar.problemas(datos.json()) == []
    assert datos.json()["hoy"]["titular"]


def test_avisos_entendido_requiere_csrf_y_sesion_y_se_guarda_por_cuenta(web_ctx):
    from web.modelos import AvisoOculto
    uid, cl = listo(web_ctx)
    pag = cl.get("/").text
    assert 'data-avisos-ocultos="{}"' in pag and "data-csrf=" in pag
    token = csrf_de(pag) if False else pag.split('data-csrf="')[1].split('"')[0]
    assert cl.post("/avisos/ocultar", data={"id": "zonas", "huella": "ab12"}).status_code == 403   # sin CSRF
    assert web_ctx.cliente().post("/avisos/ocultar", data={"id": "zonas", "huella": "ab12", "csrf": token}).status_code == 403   # sin sesión
    assert cl.post("/avisos/ocultar", data={"id": "Zonas!", "huella": "ab12", "csrf": token}).status_code == 422
    assert cl.post("/avisos/ocultar", data={"id": "zonas", "huella": "ab12", "csrf": token}).json() == {"ok": True}
    assert cl.post("/avisos/ocultar", data={"id": "zonas", "huella": "cd34", "csrf": token}).status_code == 200   # cambia la huella: se actualiza
    with web_ctx.sesiones() as db:
        assert [(a.aviso_id, a.huella) for a in db.query(AvisoOculto).filter_by(usuario_id=uid)] == [("zonas", "cd34")]
    assert '&quot;zonas&quot;: &quot;cd34&quot;' in cl.get("/").text
    # otra cuenta no ve lo de esta
    _, otra = listo(web_ctx, correo="b@x.com")
    assert 'data-avisos-ocultos="{}"' in otra.get("/").text
    # el coach que mira /a/<id>/ no recibe botón ni mapa
    assert "data-csrf" not in cl.get(f"/a/{uid}/").text


def test_resumen_del_plan_ajustes_e_inbody_sin_ids_internos():
    from types import SimpleNamespace
    ses = lambda m, **x: {"id": "z2b", "tipo": "z2", "name": "Z2 #2", "minutes": m, "steps": [{"kind": "run", "minutes": m, "zone": "Z2"}], **x}  # noqa: E731
    plan = lambda m: {"weeks": [{"n": 2, "sessions": [ses(m)]}]}
    c = SimpleNamespace(antes={"plan": plan(30)}, despues={"plan": plan(40)})
    r = cambios.resumen(c)
    assert r[0] == "Semana 2 · Z2 #2: minutos 30 → 40" and not any("z2b" in x for x in r)
    c = SimpleNamespace(antes={"ajustes": {"perfil": {"edad": 40}}}, despues={"ajustes": {"perfil": {"edad": 41}}})
    assert cambios.resumen(c) == ["la edad: 40 → 41"]
    c = SimpleNamespace(antes={"inbody": []}, despues={"inbody": [{"fecha": "2026-11-20", "peso_kg": 80}]})
    assert cambios.resumen(c) == ["InBody 2026-11-20: se agregó"]
    grande = {"weeks": [{"n": 1, "sessions": [{**ses(10), "id": f"s{i}", "name": f"S{i}"} for i in range(9)]}]}
    r = cambios.resumen(SimpleNamespace(antes={"plan": {"weeks": [{"n": 1, "sessions": []}]}}, despues={"plan": grande}))
    assert len(r) == 6 and r[-1] == "y 4 más"
    assert cambios.resumen(SimpleNamespace(antes=None, despues=None)) == []


def test_entendido_marca_solo_ese_y_lo_visto_de_la_ia_no_se_deshace(web_ctx):
    uid, cl = listo(web_ctx)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        c1 = cambios.aplicar_cambio(db, u, u, "ia", "Uno", {"ajustes": {**CONFIG, "perfil": {**CONFIG["perfil"], "titulo": "A"}}}).id
        c2 = cambios.aplicar_cambio(db, u, u, "ia", "Dos", {"ajustes": {**CONFIG, "perfil": {**CONFIG["perfil"], "titulo": "B"}}}).id
    h = cl.get("/historial")
    assert f'id="c{c1}"' in h.text and "Entendido" in h.text and "Marcar todo" not in h.text
    assert cl.post(f"/historial/{c1}/visto", data={"csrf": tok(cl)}).status_code == 303
    with web_ctx.sesiones() as db:
        assert db.get(Cambio, c1).visto and not db.get(Cambio, c2).visto
        assert not cambios.puede_deshacer(db.get(Cambio, c1)) and cambios.puede_deshacer(db.get(Cambio, c2))
        with pytest.raises(cambios.NoSeDeshace):
            cambios.deshacer(db, db.get(Usuario, uid), c1)
