"""Primer inicio (ui.primer_inicio): las barras de los primeros pasos, «+ Registrar actividad» y la lista del coach."""
import copy

from dashboard import validar
from web import primer_inicio
from web.modelos import Ajustes, Consentimiento, InBody, Grupo, MiembroGrupo, Usuario
from web.privacidad import VERSION_AVISO
from ayudas import CONFIG, crear_usuario, dar, entrar, listo


def nuevo(ctx, correo="n@x.com"):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        db.add(Consentimiento(usuario_id=uid, version_aviso=VERSION_AVISO))
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def pi(cl, url="/data.json"):
    d = cl.get(url).json()
    assert validar.problemas(d) == []
    return d["ui"]["primer_inicio"]


def test_cuenta_nueva_registra_primera_corrida_desde_hoy(web_ctx):
    from ayudas import datos, enviar

    _, cl = nuevo(web_ctx)
    antes = cl.get("/data.json").json()
    assert antes["datos_al"] is None
    assert antes["hoy"]["tarjeta"]["tipo"] != "primera_sync"
    assert antes["semana_libre"]["actividades"] == 0
    registrar = antes["ui"]["primer_inicio"]["registrar"]
    respuesta = enviar(cl, registrar, datos(fecha=antes["generado"][:10]))
    assert respuesta.status_code == 303 and respuesta.headers["location"] == "/#hoy"
    despues = cl.get("/data.json").json()
    assert despues["datos_al"] is None
    assert despues["semana_libre"]["actividades"] == 1
    assert despues["semana_libre"]["minutos"] == 30
    assert antes["ui"]["primer_inicio"]["sin_actividad"] is True and despues["ui"]["primer_inicio"]["sin_actividad"] is False


def barras(cl):
    return pi(cl)["barras"]


def saltar(cl, aviso):
    token = cl.get("/").text.split('data-csrf="')[1].split('"')[0]
    assert cl.post("/avisos/ocultar", data={"id": aviso, "huella": "0", "csrf": token}).json() == {"ok": True}


def cambiar(ctx, uid, **campos):
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        for k, v in campos.items():
            setattr(u, k, v)
        db.commit()


def poner_plan(ctx, uid):
    with ctx.sesiones() as db:
        db.add(Ajustes(usuario_id=uid, config=copy.deepcopy(CONFIG)))
        db.commit()


def poner_grupo(ctx, uid):
    with ctx.sesiones() as db:
        g = Grupo(nombre="G", creado_por=uid)
        db.add(g)
        db.commit()
        db.add(MiembroGrupo(grupo_id=g.id, usuario_id=uid))
        db.commit()


def poner_inbody(ctx, uid):
    with ctx.sesiones() as db:
        db.add(InBody(usuario_id=uid, fecha="2026-11-20", valores={"fecha": "2026-11-20", "peso_kg": 80.0}))
        db.commit()


def resumen(b):
    return b["vista"], b["hechos"], b["siguiente"], b["lista"]


def test_cuenta_nueva_cinco_pasos_y_garmin_primero(web_ctx):
    uid, cl = nuevo(web_ctx)
    b = barras(cl)
    assert resumen(b) == ("garmin", 1, "garmin", ["plan", "grupo", "inbody"])
    assert b["llave"] == uid and b["liga"] == "/bienvenida/liga" and b["ocultar"] == "/avisos/ocultar"
    assert b["pasos"] == [{"id": "cuenta", "hecho": True, "url": None, "saltar": None},
                          {"id": "garmin", "hecho": False, "url": "/bienvenida", "saltar": "garmin"},
                          {"id": "plan", "hecho": False, "url": "/plan/nuevo", "saltar": "paso_plan"},
                          {"id": "grupo", "hecho": False, "url": "/grupos", "saltar": "paso_grupo"},
                          {"id": "inbody", "hecho": False, "url": "/cuerpo", "saltar": "paso_inbody"}]
    assert "pasos" not in pi(cl) and "garmin" not in pi(cl)


def test_saltar_cada_uno_en_orden_hasta_cinco(web_ctx):
    _, cl = nuevo(web_ctx)
    token = cl.get("/").text.split('data-csrf="')[1].split('"')[0]
    assert cl.post("/avisos/ocultar", data={"id": "garmin", "huella": "0"}).status_code == 403   # sin CSRF
    assert barras(cl)["hechos"] == 1 and token
    vistos = []
    for aviso in ("garmin", "paso_plan", "paso_grupo", "paso_inbody"):
        saltar(cl, aviso)
        vistos.append(resumen(barras(cl)))
    assert vistos == [("compacta", 2, "plan", []), ("compacta", 3, "grupo", []), ("compacta", 4, "inbody", []), ("completa", 5, None, [])]
    assert all(p["hecho"] for p in barras(cl)["pasos"])


def test_el_siguiente_es_el_primero_pendiente_y_cada_paso_se_cumple(web_ctx):
    uid, cl = nuevo(web_ctx)
    poner_inbody(web_ctx, uid)
    assert resumen(barras(cl)) == ("garmin", 2, "garmin", ["plan", "grupo"])
    cambiar(web_ctx, uid, repo_id=5)
    assert resumen(barras(cl)) == ("compacta", 3, "plan", [])
    poner_plan(web_ctx, uid)
    assert resumen(barras(cl)) == ("compacta", 4, "grupo", [])
    poner_grupo(web_ctx, uid)
    assert resumen(barras(cl)) == ("completa", 5, None, [])
    assert pi(cl)["registrar"] == "/actividad/nueva"   # registrar no se va nunca


def test_mientras_llega_el_historial_el_plan_espera(web_ctx):
    uid, cl = nuevo(web_ctx)
    cambiar(web_ctx, uid, repo_id=5, historial_pendiente=True)
    assert resumen(barras(cl)) == ("historial", 2, None, ["grupo", "inbody"])
    cambiar(web_ctx, uid, historial_pendiente=False)   # fuera de la caché: se ve al momento
    assert resumen(barras(cl)) == ("compacta", 2, "plan", [])


def test_cuenta_que_ya_existia_con_pendientes_ve_la_compacta(web_ctx):
    uid, cl = listo(web_ctx, "vieja@x.com")
    cambiar(web_ctx, uid, repo_id=9)
    assert resumen(barras(cl)) == ("compacta", 3, "grupo", [])   # ya tenía Garmin y plan
    assert pi(cl)["sin_actividad"] is True
    poner_grupo(web_ctx, uid)
    poner_inbody(web_ctx, uid)
    assert barras(cl)["vista"] == "completa"


def test_garmin_saltado_y_luego_conectado_vuelve_a_esperar_si_faltan_pasos(web_ctx):
    uid, cl = nuevo(web_ctx)
    saltar(cl, "garmin")
    assert barras(cl)["vista"] == "compacta"
    cambiar(web_ctx, uid, repo_id=5, historial_pendiente=True)
    assert resumen(barras(cl))[:2] == ("historial", 2)


def test_coach_ve_la_lista_sin_barras(web_ctx):
    uid_a, atleta = listo(web_ctx, "atleta@x.com")
    _, coach = listo(web_ctx, "coach@x.com", con_plan=False)
    dar(atleta, "coach@x.com")
    saltar(atleta, "paso_inbody")   # saltar es de la tarjeta del atleta: al coach le sigue saliendo lo que falta
    assert pi(coach, f"/a/{uid_a}/data.json") == {"registrar": f"/a/{uid_a}/actividad/nueva",
                                                  "pasos": [{"id": "inbody", "url": f"/a/{uid_a}/cuerpo"}]}
    with web_ctx.sesiones() as db:
        assert primer_inicio.de(db, db.get(Usuario, uid_a), f"/a/{uid_a}", editable=False) == {"registrar": None, "pasos": []}


def test_conexiones_de_ajustes_muestra_conectar_sin_copia(web_ctx):
    uid, cl = nuevo(web_ctx)
    cl.post("/avisos/ocultar", data={"id": "garmin", "huella": "0", "csrf": cl.get("/").text.split('data-csrf="')[1].split('"')[0]})
    html = cl.get("/ajustes").text
    assert 'href="/bienvenida"' in html and "Conectar Garmin" in html   # también si quitó la tarjeta


def test_guia_activa_ya_no_exige_sin_ajustes():
    from types import SimpleNamespace as S
    from web.onboarding import guia_activa
    e = {"consentimiento": True, "datos": False, "vinculado": False, "ajustes": True}
    assert guia_activa(S(app_github=True), S(gh_instalacion=None), e)
