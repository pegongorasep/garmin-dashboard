"""Motor v6 F4: «Quiero un plan» (/plan/nuevo): nivel desde Garmin, preguntas por nivel, vista previa, confirmar, coach y CSRF."""
from datetime import date, datetime, timedelta

from dashboard import validar
from test_web_cuentas import crear_usuario, csrf_de, entrar
from web.modelos import Ajustes, Cambio, Coach, DatoGarmin, Plan, Usuario


def lunes_siguiente() -> date:
    hoy = date.today()
    return hoy + timedelta(days=(7 - hoy.weekday()) % 7 or 7)


def sembrar(ctx, uid, semanas=8, por_semana=4, minutos=50):
    """Corridas continuas de `minutos` en `por_semana` días de cada una de las últimas `semanas` semanas."""
    hoy = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    n = 0
    with ctx.sesiones() as db:
        for s in range(semanas):
            for j in range(por_semana):
                f = hoy - timedelta(days=7 * s + 1 + 2 * j)
                n += 1
                db.add(DatoGarmin(usuario_id=uid, tipo="actividad", clave=str(n), contenido={
                    "id": n, "startTimeLocal": f.isoformat(sep=" "), "duration": minutos * 60.0, "activityType": {"typeKey": "running"}}))
        db.commit()


def preguntas(cl, nivel, pref=""):
    r = cl.get(f"{pref}/plan/nuevo")
    return cl.post(f"{pref}/plan/nuevo/preguntas", data={"csrf": csrf_de(r.text), "nivel": nivel})


def respuestas(**extra):
    return {"dias": "3", "dolor": "no", "inicio": lunes_siguiente().isoformat(), "edad": "35", "zona": "America/Merida", **extra}


def vista(cl, nivel, pref="", **extra):
    r = preguntas(cl, nivel, pref)
    return cl.post(f"{pref}/plan/nuevo/vista", data={"csrf": csrf_de(r.text), "nivel": nivel, **respuestas(**extra)})


def confirmar(cl, nivel, pref="", **extra):
    r = preguntas(cl, nivel, pref)
    return cl.post(f"{pref}/plan/nuevo/confirmar", data={"csrf": csrf_de(r.text), "nivel": nivel, **respuestas(**extra)})


def nueva(web_ctx, correo="n@x.com"):
    uid = crear_usuario(web_ctx, correo)
    return uid, entrar(web_ctx, web_ctx.cliente(), correo)


def test_sin_sesion_va_a_entrar_y_sin_datos_propone_empezando(web_ctx):
    assert web_ctx.cliente().get("/plan/nuevo").headers["location"] == "/entrar"
    uid, cl = nueva(web_ctx)
    r = cl.get("/plan/nuevo")
    assert r.status_code == 200 and "Lo que vimos en tu Garmin" in r.text and "Todavía no vemos corridas" in r.text
    assert 'value="empezando"' in r.text and "checked" in r.text and "Calculado con tu Garmin: Empezando" in r.text


def test_nivel_calculado_desde_las_actividades_guardadas(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid)
    r = cl.get("/plan/nuevo")
    assert "Calculado con tu Garmin: Corredor" in r.text and "Corres 4 veces por semana" in r.text and "200 minutos por semana" in r.text


def test_preguntas_segun_el_nivel(web_ctx):
    uid, cl = nueva(web_ctx)
    emp = preguntas(cl, "empezando").text
    assert 'name="dias"' in emp and 'name="pierna"' in emp and 'name="dolor"' in emp and 'name="inicio"' in emp
    assert 'name="objetivo"' not in emp and 'name="km"' not in emp and 'name="tiempo"' not in emp
    base = preguntas(cl, "base").text
    assert 'name="objetivo"' in base and 'value="mas_tiempo"' in base and 'name="km"' in base
    assert 'value="velocidad"' not in base and 'name="tiempo"' not in base
    cor = preguntas(cl, "corredor").text
    assert 'value="velocidad"' in cor and 'name="tiempo"' in cor and 'value="mas_tiempo"' not in cor
    assert 'name="zona"' in emp and 'name="fc_max"' in emp   # sin ajustes todavía: se piden aquí


def test_nivel_mas_alto_que_el_calculado_avisa(web_ctx):
    uid, cl = nueva(web_ctx)
    assert "tus datos dicen Empezando" in preguntas(cl, "corredor").text
    assert "tus datos dicen" not in preguntas(cl, "empezando").text


def test_vista_previa_empezando_no_guarda_y_avisa_de_dias(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "empezando", dias="5", dolor="si", pierna=["lun", "mié"])
    assert r.status_code == 200 and "<progress" in r.text and "Nada se guarda hasta que confirmes" in r.text
    assert "lo más seguro son 3 días" in r.text and "consulta a un profesional" in r.text
    assert "Por qué así" in r.text and "Sube como máximo 10 % por semana" in r.text and "Tus dos primeras semanas" in r.text
    assert "Confirmar mi plan" in r.text and "Cambiar respuestas" in r.text
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid) is None and db.get(Ajustes, uid) is None


def test_confirmar_guarda_plan_v6_ajustes_y_historial(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid, semanas=6, por_semana=3, minutos=25)
    r = confirmar(cl, "base", dolor="si", tiempo="x")   # tiempo no es de Base: se ignora
    assert r.status_code == 303 and r.headers["location"] == "/?ok=plan#plan"
    with web_ctx.sesiones() as db:
        p, a, u = db.get(Plan, uid), db.get(Ajustes, uid), db.get(Usuario, uid)
        assert p.plan["meta"]["motor"] == "v6" and p.plan["meta"]["nivel"] == "base" and p.plan["meta"]["dolor"] is True
        assert p.plan["start"] == lunes_siguiente().isoformat() and a.config["corrida"]["inicio"] == p.plan["start"]
        assert a.config["corrida"]["semanas"] == len(p.plan["weeks"]) and u.sin_plan is False
        assert a.config["perfil"]["edad"] == 35
        assert db.query(Cambio).filter_by(atleta_id=uid).one().descripcion.startswith("Plan nuevo (motor v6)")
    assert validar.problemas(cl.get("/data.json").json()) == []
    assert cl.get("/historial").status_code == 200


def test_carrera_guarda_la_fecha_en_el_plan_y_no_en_metas(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid)
    fecha = (lunes_siguiente() + timedelta(weeks=11, days=5)).isoformat()
    r = confirmar(cl, "corredor", objetivo="carrera", km="10", fecha=fecha, tiempo="52:30", dias="4")
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        p, a = db.get(Plan, uid), db.get(Ajustes, uid)
        assert p.plan["meta"]["carrera"]["km"] == 10 and len(p.plan["weeks"]) == 12 and p.plan["meta"]["tiempo_carrera"] == "52:30"
        assert not (a.config["corrida"].get("carreras") or a.config.get("metas"))


def test_aviso_de_carrera_con_poco_tiempo_en_la_vista(web_ctx):
    uid, cl = nueva(web_ctx)
    fecha = (lunes_siguiente() + timedelta(weeks=5)).isoformat()
    r = vista(cl, "base", objetivo="carrera", km="21", fecha=fecha)
    assert r.status_code == 200 and "Si sigues, el plan va lo más suave posible" in r.text


def test_errores_vuelven_a_las_preguntas_con_400(web_ctx):
    uid, cl = nueva(web_ctx)
    cerca = (lunes_siguiente() + timedelta(days=10)).isoformat()
    for extra, msg in ((dict(objetivo="carrera", fecha="", km="10"), "Escribe una fecha válida"),
                       (dict(objetivo="carrera", fecha=cerca, km="7"), "Elige 5, 10, 21 o 42"),
                       (dict(inicio="2001-01-01"), "antes de esta semana"),
                       (dict(edad="", fc_max=""), "edad o tu FC"),
                       (dict(dias="9"), "entre 2 y 5")):
        r = vista(cl, "base", **extra)
        assert r.status_code == 400 and msg in r.text and 'name="dias"' in r.text, (extra, r.text[:200])
    assert vista(cl, "corredor", tiempo="rápido").status_code == 400


def test_cambiar_respuestas_conserva_lo_escrito(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "empezando", dias="4", pierna=["vie"], edad="41")
    r2 = cl.post("/plan/nuevo/preguntas", data={"csrf": csrf_de(r.text), "nivel": "empezando", **respuestas(dias="4", pierna=["vie"], edad="41")})
    assert 'option value="4" selected' in r2.text and 'value="41"' in r2.text and 'value="vie" checked' in r2.text


def test_todo_post_exige_csrf(web_ctx):
    uid, cl = nueva(web_ctx)
    for ruta in ("preguntas", "vista", "confirmar"):
        assert cl.post(f"/plan/nuevo/{ruta}", data={"nivel": "base", **respuestas()}).status_code == 403
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid) is None


def test_con_ajustes_los_conserva_y_cambia_el_plan(web_ctx):
    uid = crear_usuario(web_ctx, "c@x.com", con_ajustes=True)
    cl = entrar(web_ctx, web_ctx.cliente(), "c@x.com")
    with web_ctx.sesiones() as db:
        titulo = db.get(Ajustes, uid).config["perfil"]["titulo"]
        db.get(Usuario, uid).sin_plan = True
        db.commit()
    assert 'name="zona"' not in preguntas(cl, "base").text   # ya tiene zona y perfil
    assert confirmar(cl, "base").status_code == 303
    with web_ctx.sesiones() as db:
        assert db.get(Ajustes, uid).config["perfil"]["titulo"] == titulo
        assert db.get(Plan, uid).plan["meta"]["motor"] == "v6" and db.get(Usuario, uid).sin_plan is False
    pagina = cl.get("/plan/acciones")
    assert "Armar un plan nuevo" in pagina.text and "motor anterior" not in pagina.text and "Opciones avanzadas" not in pagina.text


def test_coach_edita_al_atleta_y_un_extrano_recibe_404(web_ctx):
    uid_a = crear_usuario(web_ctx, "atleta@x.com")
    uid_c = crear_usuario(web_ctx, "coach@x.com")
    crear_usuario(web_ctx, "otro@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    otro = entrar(web_ctx, web_ctx.cliente(), "otro@x.com")
    assert otro.get(f"/a/{uid_a}/plan/nuevo").status_code == 404
    tok = csrf_de(otro.get("/plan/nuevo").text)
    for ruta in ("preguntas", "vista", "confirmar"):
        assert otro.post(f"/a/{uid_a}/plan/nuevo/{ruta}", data={"csrf": tok, "nivel": "base", **respuestas()}).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid_a) is None
    coach = entrar(web_ctx, web_ctx.cliente(), "coach@x.com")
    assert coach.get(f"/a/{uid_a}/plan/nuevo").status_code == 200
    assert 'action="/a/%d/plan/nuevo/preguntas"' % uid_a in coach.get(f"/a/{uid_a}/plan/nuevo").text
    r = confirmar(coach, "empezando", pref=f"/a/{uid_a}")
    assert r.status_code == 303 and r.headers["location"] == f"/a/{uid_a}/plan/acciones?ok=nuevo"
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid_a).plan["meta"]["motor"] == "v6"
        assert db.query(Cambio).filter_by(atleta_id=uid_a).one().via == "coach"


def test_carrera_cercana_avisa_y_se_permite_y_queda_en_metas(web_ctx):
    uid, cl = nueva(web_ctx)
    fecha = (lunes_siguiente() + timedelta(days=10)).isoformat()   # 2 semanas
    r = vista(cl, "base", objetivo="carrera", km="10", fecha=fecha)
    assert r.status_code == 200 and "plan muy corto" in r.text
    assert confirmar(cl, "base", objetivo="carrera", km="10", fecha=fecha).status_code in (200, 303)
    with web_ctx.sesiones() as db:
        crudo = db.get(Ajustes, uid).config
        plan = db.get(Plan, uid).plan
    metas = crudo["corrida"]["metas"]
    assert len(metas) == 1 and metas[0]["en_plan"] is True and metas[0]["fecha"] == fecha and metas[0]["distancia_km"] == 10
    assert crudo["corrida"]["semanas"] == len(plan["weeks"]) == 2
