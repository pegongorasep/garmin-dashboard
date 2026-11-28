"""Motor v6 F4: «Quiero un plan» (/plan/nuevo): nivel desde Garmin, preguntas por nivel, vista previa, confirmar, coach y CSRF."""
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from plan import motor_v6

from dashboard import validar
from test_web_cuentas import crear_usuario, csrf_de, entrar
from web.modelos import Ajustes, CacheData, Cambio, Coach, DatoGarmin, Plan, Usuario


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
    return cl.post(f"{pref}/plan/nuevo/preguntas", data={"csrf": csrf_de(r.text), "nivel": nivel, "frecuencia_actual": "3", "corrida_larga": "5"})


def respuestas(**extra):
    return {"dias": "3", "frecuencia_actual": "3", "corrida_larga": "5", "inicio": lunes_siguiente().isoformat(), "edad": "35", "zona": "America/Merida", **extra}


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
    assert r.status_code == 200 and "Lo que vimos en tu Garmin" not in r.text
    # sin corridas de Garmin: el nivel se elige primero, con descripciones; no hay «automático» ni preguntas de frecuencia todavía
    assert 'value="automatico"' not in r.text and 'name="frecuencia_actual"' not in r.text and 'name="corrida_larga"' not in r.text
    for n, d in (("empezando", "No corro o apenas empiezo"), ("base", "Corro algo, pero no muy seguido"), ("corredor", "Corro varias veces por semana")):
        assert f'value="{n}"' in r.text and d in r.text


def test_nivel_calculado_desde_las_actividades_guardadas(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid)
    r = cl.get("/plan/nuevo")
    assert "Calculado con tu Garmin: Corredor" in r.text and "veces por semana" in r.text and "minutos por semana" in r.text


def test_preguntas_segun_el_nivel(web_ctx):
    uid, cl = nueva(web_ctx)
    emp = preguntas(cl, "empezando").text
    assert 'name="dias"' in emp and 'name="intensos"' in emp and 'name="inicio"' in emp
    assert 'name="pierna"' not in emp and 'name="dolor"' not in emp and "no ponemos la larga" not in emp
    assert 'name="objetivo"' not in emp and 'name="km"' not in emp and 'name="tiempo"' not in emp and 'name="calidad_desde"' not in emp
    assert 'name="frecuencia_actual"' not in emp and 'name="corrida_larga"' not in emp   # Empezando no responde nada de lo que corre
    base = preguntas(cl, "base").text
    assert 'name="frecuencia_actual"' in base and 'name="corrida_larga"' in base
    assert 'name="objetivo"' in base and 'value="base"' in base and 'value="velocidad"' in base and 'value="carrera"' in base and 'name="km"' in base
    assert 'value="mas_tiempo"' not in base and 'name="tiempo"' not in base
    assert 'name="calidad_desde"' in base and 'option value="4" selected' in base and "Todavía no" in base
    cor = preguntas(cl, "corredor").text
    assert 'value="velocidad"' in cor and 'name="tiempo"' not in cor and 'value="mas_tiempo"' not in cor
    assert 'option value="2" selected' in cor
    assert 'name="zona"' in emp and 'name="fc_max"' not in emp and "FC máxima" not in emp   # sin ajustes todavía: zona y edad; la FC máx ya no se pide
    sel = cor.split('name="calidad_desde"')[1].split("</select>")[0]
    assert '<option value="2"' in sel and '<option value="8"' in sel and 'option value="9"' not in sel and 'option value="1"' not in sel


def test_nivel_mas_alto_que_el_calculado_avisa(web_ctx):
    uid, cl = nueva(web_ctx)
    assert "tus datos dicen" not in preguntas(cl, "corredor").text   # sin Garmin el aviso sale con las respuestas (vista previa)
    assert "tus datos dicen Base" in vista(cl, "corredor", frecuencia_actual="2", corrida_larga="30").text
    assert "tus datos dicen" not in vista(cl, "corredor", frecuencia_actual="3", corrida_larga="60").text
    assert "tus datos dicen Empezando" in vista(cl, "base", frecuencia_actual="2", corrida_larga="5").text
    assert "tus datos dicen" not in vista(cl, "empezando").text


def test_vista_previa_empezando_no_guarda_y_avisa_de_dias(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "empezando", dias="5", intensos="2")
    assert r.status_code == 200 and "<progress" in r.text and "Nada se guarda hasta que confirmes" in r.text
    assert "lo más seguro son 3 días" in r.text and "consulta a un profesional" not in r.text
    assert "Por qué así" in r.text and "Sube como máximo 10 % por semana" in r.text and "Ver el plan completo" in r.text and "Tus dos primeras semanas" not in r.text
    assert "Confirmar mi plan" in r.text and "Cambiar respuestas" in r.text
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid) is None and db.get(Ajustes, uid) is None


def test_confirmar_guarda_plan_v6_ajustes_y_historial(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid, semanas=6, por_semana=3, minutos=25)
    r = confirmar(cl, "base", tiempo="x", corrida_larga="30")   # tiempo no es de Base: se ignora
    assert r.status_code == 303 and r.headers["location"] == "/?ok=plan#plan"
    with web_ctx.sesiones() as db:
        p, a, u = db.get(Plan, uid), db.get(Ajustes, uid), db.get(Usuario, uid)
        assert p.plan["meta"]["motor"] == "v6" and p.plan["meta"]["nivel"] == "base" and "dolor" not in p.plan["meta"]
        assert p.plan["meta"]["calidad_desde"] == 4 and p.plan["meta"]["ajuste_pct"] == 0
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
    r = confirmar(cl, "corredor", objetivo="carrera", km="10", fecha=fecha, tiempo="52:30", dias="4")   # tiempo ya no existe: se ignora
    assert r.status_code == 303
    with web_ctx.sesiones() as db:
        p, a = db.get(Plan, uid), db.get(Ajustes, uid)
        assert p.plan["meta"]["carrera"]["km"] == 10 and len(p.plan["weeks"]) == 12 and "tiempo_carrera" not in p.plan["meta"]
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
                       (dict(edad="", fc_max="190"), "Escribe tu edad"),
                       (dict(dias="9"), "entre 2 y 5")):
        r = vista(cl, "base", **extra)
        assert r.status_code == 400 and msg in r.text and 'name="dias"' in r.text, (extra, r.text[:200])
    assert vista(cl, "corredor", tiempo="rápido").status_code == 200   # el tiempo de carrera ya no se pregunta ni se valida


def test_cambiar_respuestas_conserva_lo_escrito(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "base", dias="4", intensos="2", edad="41", calidad_desde="6", ajuste_pct="10")
    r2 = cl.post("/plan/nuevo/preguntas", data={"csrf": csrf_de(r.text), "nivel": "base", **respuestas(dias="4", intensos="2", edad="41", calidad_desde="6")})
    assert 'option value="4" selected' in r2.text and 'value="41"' in r2.text and 'option value="2" selected' in r2.text
    assert 'option value="6" selected' in r2.text


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


# ───────────────────────────── formulario nuevo: nivel primero, calidad a elegir, ajuste de volumen ─────────────────────────────

def plan_de(web_ctx, uid):
    with web_ctx.sesiones() as db:
        return db.get(Plan, uid).plan


def semanas_con_calidad(plan):
    return {w["n"] for w in plan["weeks"] if any(x["tipo"] == "calidad" or "aceleraciones" in str(x.get("notas", "")).lower() for x in w["sessions"])}


def otra_persona(web_ctx, correo):
    crear_usuario(web_ctx, correo)
    return entrar(web_ctx, web_ctx.cliente(), correo)


def test_empezando_sin_garmin_arranca_en_el_piso_sin_preguntar_frecuencia(web_ctx):
    uid, cl = nueva(web_ctx)
    # aunque lleguen respuestas de frecuencia/larga (viejas), Empezando las ignora
    assert confirmar(cl, "empezando", frecuencia_actual="7", corrida_larga="120").status_code == 303
    p = plan_de(web_ctx, uid)
    assert p["meta"]["nivel"] == "empezando" and p["meta"]["inicio_minutos"] == 45 and p["meta"]["calidad"] is False


def test_base_sin_garmin_pide_frecuencia_y_larga(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "base", frecuencia_actual="", corrida_larga="")
    assert r.status_code == 400 and 'name="frecuencia_actual"' in r.text and "entre 1 y 7" in r.text
    r = vista(cl, "base", frecuencia_actual="3", corrida_larga="40")
    assert r.status_code == 200 and "tus datos dicen" not in r.text
    assert confirmar(cl, "base", frecuencia_actual="3", corrida_larga="40").status_code == 303
    p = plan_de(web_ctx, uid)
    assert p["meta"]["nivel"] == "base" and p["meta"]["inicio_minutos"] == 95   # 3 × 40 × 0.8 = 96 -> 95


def test_dias_3_por_defecto_y_conteo_de_intensos(web_ctx):
    uid, cl = nueva(web_ctx)
    assert 'option value="3" selected' in preguntas(cl, "base").text
    assert confirmar(cl, "base", intensos="3", edad="30", corrida_larga="30").status_code == 303
    p = plan_de(web_ctx, uid)
    assert len(p["meta"]["entrada"]["dias_intensos"]) == 3 and p["meta"]["ciclo"] == 3   # 3+ intensos: descarga 2:1
    assert vista(cl, "base", intensos="6").status_code == 400
    cl2 = otra_persona(web_ctx, "i0@x.com")
    assert confirmar(cl2, "base", intensos="0", edad="30", corrida_larga="30").status_code == 303


def test_intensos_se_prellena_con_lo_que_vio_garmin(web_ctx):
    uid, cl = nueva(web_ctx)
    hoy = datetime.now().replace(hour=7, minute=0, second=0, microsecond=0)
    sembrar(web_ctx, uid, semanas=8, por_semana=3, minutos=30)
    with web_ctx.sesiones() as db:
        n = 1000
        for s in range(8):
            for d in (1, 3):   # martes y jueves de cada semana
                f = hoy - timedelta(days=7 * s + (hoy.weekday() - d) % 7 + 7)
                n += 1
                db.add(DatoGarmin(usuario_id=uid, tipo="actividad", clave=str(n), contenido={
                    "id": n, "startTimeLocal": f.isoformat(sep=" "), "duration": 3000.0, "activityType": {"typeKey": "hiit"}}))
        db.commit()
    r = cl.post("/plan/nuevo/preguntas", data={"csrf": csrf_de(cl.get("/plan/nuevo").text), "nivel": "base"})
    sel = r.text.split('name="intensos"')[1].split("</select>")[0]
    assert 'option value="2" selected' in sel


def test_calidad_desde_elegida_vs_todavia_no(web_ctx):
    uid, cl = nueva(web_ctx)
    assert confirmar(cl, "corredor", frecuencia_actual="4", corrida_larga="50", calidad_desde="3", dias="5").status_code == 303
    p = plan_de(web_ctx, uid)
    assert p["meta"]["calidad"] is True and p["meta"]["calidad_desde"] == 3 and p["meta"]["dias"] == 5
    sem = semanas_con_calidad(p)
    assert sem and min(sem) == 3
    cl2 = otra_persona(web_ctx, "nc@x.com")
    assert "lo más seguro son 4 días" in vista(cl2, "base", calidad_desde="no", dias="5", corrida_larga="30").text   # sin calidad Base topa en 4
    assert "lo más seguro son" not in vista(cl2, "base", calidad_desde="4", dias="5", corrida_larga="30").text      # con calidad elegida, 5
    assert vista(cl2, "base", calidad_desde="1", corrida_larga="30").status_code == 400
    assert vista(cl2, "base", calidad_desde="9", corrida_larga="30").status_code == 400
    assert confirmar(cl2, "base", calidad_desde="no", corrida_larga="30").status_code == 303
    p2 = plan_de(web_ctx, crear_id(web_ctx, "nc@x.com"))
    assert p2["meta"]["calidad"] is False and p2["meta"]["calidad_desde"] is None and not semanas_con_calidad(p2)


def crear_id(web_ctx, correo):
    with web_ctx.sesiones() as db:
        return db.query(Usuario).filter_by(correo=correo).one().id


def test_aviso_calidad_con_corrida_larga_corta(web_ctx):
    uid, cl = nueva(web_ctx)
    assert "menos de 20 min" in vista(cl, "base", calidad_desde="4", corrida_larga="15").text
    assert "menos de 20 min" not in vista(cl, "base", calidad_desde="4", corrida_larga="25").text
    assert "menos de 20 min" not in vista(cl, "base", calidad_desde="no", corrida_larga="15").text


def test_objetivos_unificados_y_el_viejo_mas_tiempo_es_base(web_ctx):
    uid, cl = nueva(web_ctx)
    assert vista(cl, "base", objetivo="mas_tiempo", corrida_larga="30").status_code == 200
    assert confirmar(cl, "base", objetivo="velocidad", corrida_larga="30").status_code == 303
    assert plan_de(web_ctx, uid)["meta"]["objetivo"] == "velocidad"


def volumen_texto(r):
    m = re.search(r"Volumen de inicio: (\d+) min/semana \(([^)]*)\)", r.text)
    return int(m.group(1)), m.group(2)


def fila_volumen(r):
    return r.text.split('class="pn-volumen"')[1].split("</form>")[0]


def test_ajuste_de_volumen_limites_avisos_y_confirmar_identico(web_ctx):
    uid, cl = nueva(web_ctx)
    kw = dict(frecuencia_actual="3", corrida_larga="40")   # inicio 95 en Base (piso 60)
    r0 = vista(cl, "base", **kw)
    assert volumen_texto(r0) == (95, "0 %") and "Subir más de 10 %" not in r0.text
    assert 'value="5"' in fila_volumen(r0) and 'value="-5"' in fila_volumen(r0) and "pn-ranura" in r0.text
    r1 = vista(cl, "base", ajuste_pct="10", **kw)
    assert volumen_texto(r1) == (105, "+10 %") and "Subir más de 10 %" not in r1.text
    r2 = vista(cl, "base", ajuste_pct="20", **kw)
    assert volumen_texto(r2) == (115, "+20 %") and "Subir más de 10 % de golpe" in r2.text and "no pasar de +20 %" not in r2.text
    r3 = vista(cl, "base", ajuste_pct="30", **kw)
    assert volumen_texto(r3)[1] == "+30 %" and "no pasar de +20 %" in r3.text
    assert "disabled" in fila_volumen(r3) and 'name="ajuste_pct" value="35"' not in fila_volumen(r3)   # «+ 5 %» deshabilitado en +30
    assert volumen_texto(vista(cl, "base", ajuste_pct="90", **kw))[1] == "+30 %"    # fuera de rango o no múltiplo de 5: se acomoda
    assert volumen_texto(vista(cl, "base", ajuste_pct="7", **kw))[1] == "+5 %"
    assert volumen_texto(vista(cl, "base", ajuste_pct="x", **kw))[1] == "0 %"
    rb = vista(cl, "base", ajuste_pct="-35", **kw)   # hacia abajo hasta el piso de Base (60)
    assert volumen_texto(rb)[0] == 60 and 'value="-40"' not in fila_volumen(rb) and "disabled" in fila_volumen(rb)
    assert volumen_texto(vista(cl, "base", ajuste_pct="-80", **kw))[0] == 60
    assert confirmar(cl, "base", ajuste_pct="20", **kw).status_code == 303   # lo guardado es lo visto
    p = plan_de(web_ctx, uid)
    assert p["meta"]["ajuste_pct"] == 20 and p["meta"]["inicio_minutos"] == 115


def test_ajuste_en_el_piso_no_baja_y_aviso_de_maximo_del_nivel(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "empezando", ajuste_pct="-10")   # Empezando arranca en su piso (45): no se baja
    assert volumen_texto(r) == (45, "0 %") and 'value="-5"' not in fila_volumen(r) and "disabled" in fila_volumen(r)
    r = vista(cl, "corredor", frecuencia_actual="4", corrida_larga="60", ajuste_pct="30", dias="5", edad="30", semanas="40")
    assert "Llegaste al máximo de tu nivel" in r.text   # 12 semanas desde 90 +30 % topan con los 240 min del nivel
    assert "Llegaste al máximo de tu nivel" not in vista(cl, "empezando", ajuste_pct="0").text


def test_ajuste_confirmar_regenera_el_mismo_plan_de_la_vista(web_ctx):
    uid, cl = nueva(web_ctx)
    kw = dict(frecuencia_actual="3", corrida_larga="40", ajuste_pct="15", calidad_desde="5", intensos="1")
    r = vista(cl, "base", **kw)
    vistas = [int(x) for x in re.findall(r'<span class="pn-min">(\d+) min', r.text)]
    assert confirmar(cl, "base", **kw).status_code == 303
    p = plan_de(web_ctx, uid)
    assert vistas and [motor_v6.minutos_semana(w) for w in p["weeks"]] == vistas


# ───────────────────────────── ronda 2: carrera solo si se elige, sin FC máx, volumen que sí cambia, plan completo ─────────────────────────────

def datos_json(cl, nivel, pref="", **extra):
    """POST a vista.json con las mismas respuestas que la vista."""
    r = preguntas(cl, nivel, pref)
    return cl.post(f"{pref}/plan/nuevo/vista.json", data={"csrf": csrf_de(r.text), "nivel": nivel, **respuestas(**extra)})


def incrusto(r):
    import json
    return json.loads(r.text.split('<script type="application/json" id="pn-datos">')[1].split("</script>")[0].replace("\\u0026", "&").replace("\\u003c", "<").replace("\\u003e", ">").replace("\\u0027", "'"))


def test_carrera_solo_se_ve_con_objetivo_carrera(web_ctx):
    uid, cl = nueva(web_ctx)
    base = preguntas(cl, "base").text
    assert 'class="pn-carrera"' in base and 'name="km"' in base and 'name="fecha"' in base      # los campos existen (sin JS el servidor los ignora)
    assert 'value="carrera" checked' not in base                                                 # y no están elegidos
    css = (Path(__file__).parent.parent / "web" / "estaticos" / "paginas.css").read_text(encoding="utf-8")
    assert ".pn-carrera { display: none; }" in css and 'input[name="objetivo"][value="carrera"]:checked) .pn-carrera' in css
    cor = preguntas(cl, "corredor").text
    assert 'class="pn-carrera"' in cor
    assert 'class="pn-carrera"' not in preguntas(cl, "empezando").text                         # Empezando no tiene objetivo
    # otro objetivo con km/fecha basura: se ignoran; carrera sin fecha: error en el campo
    assert vista(cl, "base", objetivo="base", km="7", fecha="no es fecha", corrida_larga="30").status_code == 200
    r = vista(cl, "base", objetivo="carrera", km="10", fecha="", corrida_larga="30")
    assert r.status_code == 400 and "Escribe una fecha válida" in r.text and 'name="fecha"' in r.text
    # la carrera del preset llega marcada
    fecha = (lunes_siguiente() + timedelta(weeks=12)).isoformat()
    r = cl.post("/plan/nuevo/preguntas", data={"csrf": csrf_de(cl.get("/plan/nuevo").text), "nivel": "base", "carrera": "1", "fecha": fecha, "km": "10"})
    assert 'value="carrera" checked' in r.text


def test_sin_fc_max_ni_tiempo_y_edad_obligatoria_sin_ajustes(web_ctx):
    uid, cl = nueva(web_ctx)
    for nivel in ("empezando", "base", "corredor"):
        h = preguntas(cl, nivel).text
        assert 'name="fc_max"' not in h and 'name="tiempo"' not in h and "FC máxima" not in h
        assert re.search(r'name="edad"[^>]*required', h)
    r = vista(cl, "empezando", edad="")
    assert r.status_code == 400 and "Escribe tu edad" in r.text
    assert vista(cl, "empezando", edad="30", fc_max="150").status_code == 200   # un fc_max viejo en el POST se ignora
    assert confirmar(cl, "empezando", edad="30", fc_max="150").status_code == 303
    with web_ctx.sesiones() as db:
        assert "fc_max" not in db.get(Ajustes, uid).config["perfil"] and db.get(Ajustes, uid).config["perfil"]["edad"] == 30
    # con ajustes: edad opcional y su fc_max guardada se conserva
    uid2 = crear_usuario(web_ctx, "fc@x.com", con_ajustes=True)
    cl2 = entrar(web_ctx, web_ctx.cliente(), "fc@x.com")
    with web_ctx.sesiones() as db:
        db.get(Ajustes, uid2).config = {**db.get(Ajustes, uid2).config, "perfil": {**db.get(Ajustes, uid2).config["perfil"], "fc_max": 187}}
        db.get(Usuario, uid2).sin_plan = True
        db.commit()
    assert 'name="edad"' in preguntas(cl2, "base").text and not re.search(r'name="edad"[^>]*required', preguntas(cl2, "base").text)
    assert confirmar(cl2, "base", edad="").status_code == 303
    with web_ctx.sesiones() as db:
        assert db.get(Ajustes, uid2).config["perfil"]["fc_max"] == 187


def test_planes_viejos_con_tiempo_carrera_y_fc_max_siguen_funcionando(web_ctx):
    uid = crear_usuario(web_ctx, "viejo@x.com", con_ajustes=True)
    cl = entrar(web_ctx, web_ctx.cliente(), "viejo@x.com")
    with web_ctx.sesiones() as db:
        a = db.get(Ajustes, uid)
        a.config = {**a.config, "perfil": {**a.config["perfil"], "fc_max": 181}, "corrida": {**a.config["corrida"], "tiempo_carrera": "50:00"}}
        db.add(Plan(usuario_id=uid, plan={**motor_v6.generar_v6(entrada_v6_de(45)), "meta": {**motor_v6.generar_v6(entrada_v6_de(45))["meta"], "tiempo_carrera": "52:30"}}))
        db.commit()
    assert validar.problemas(cl.get("/data.json").json()) == [] and cl.get("/plan/nuevo").status_code == 200


def entrada_v6_de(inicio_minutos):
    from web import plan_nuevo
    ev = {"corridas_sem_4": 0, "minutos_sem_prom": 0, "trote_continuo_min": 0, "semanas_activas": 0}
    v = {"dias": "3", "intensos": "0", "objetivo": "base", "km": "10", "fecha": "", "calidad_desde": "", "inicio": lunes_siguiente().isoformat(), "edad": "35"}
    return plan_nuevo.entrada_v6(v, "empezando", ev, inicio_minutos)


def paquete(r):
    assert r.status_code == 200, r.text[:300]
    return r.json()


def test_mas_salta_hasta_un_valor_que_cambia_la_semana_1_empezando_45(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "empezando")
    inicio, _ = volumen_texto(r)
    assert inicio == 45
    d = incrusto(r)
    mas = d["volumen"]["mas"]
    assert mas and mas["valor"] > 5                                    # +5 % seguiría en 45: salta más lejos
    assert mas["etiqueta"] == f"+ {mas['valor']} %"                   # la etiqueta muestra el salto real
    p = paquete(datos_json(cl, "empezando", ajuste_pct=str(mas["valor"])))
    assert p["ajuste_pct"] == mas["valor"] and int(re.search(r"(\d+) min/semana", p["volumen"]["texto"]).group(1)) > 45
    assert p["semanas"][0]["min"] > 45 and p["volumen"]["menos"]["valor"] < mas["valor"] and p["volumen"]["menos"]["etiqueta"] == f"− {mas['valor'] - p['volumen']['menos']['valor']} %"


def subir_hasta_el_tope(cl, nivel, **kw):
    """Aprieta «+» (a donde lleve) hasta que se desactiva; devuelve (paquete, saltos)."""
    pct, saltos = 0, []
    for _ in range(12):
        p = paquete(datos_json(cl, nivel, ajuste_pct=str(pct), **kw))
        if p["volumen"]["mas"] is None:
            return p, saltos
        assert p["volumen"]["mas"]["valor"] > pct
        pct = p["volumen"]["mas"]["valor"]
        saltos.append(pct)
    raise AssertionError("el botón + nunca se desactivó")


def test_mas_se_desactiva_con_mensaje_cuando_no_sube_base_2_dias(web_ctx):
    uid, cl = nueva(web_ctx)
    # Base sin calidad con 2 días y 3 × 40 min: la semana 1 no pasa de 100 min (tope por sesión) aunque se pida +30 %
    kw = dict(frecuencia_actual="3", corrida_larga="40", calidad_desde="no")
    p, saltos = subir_hasta_el_tope(cl, "base", dias="2", **kw)
    assert p["semanas"][0]["min"] == 100 and p["volumen"]["maximo"] == "Con 2 días por semana no sube más; con más días sí." and saltos[0] == 5
    r = vista(cl, "base", dias="2", ajuste_pct=str(p["ajuste_pct"]), **kw)
    assert "Con 2 días por semana no sube más" in r.text and "disabled" in fila_volumen(r) and volumen_texto(r)[0] == 100
    # con 5 días la semana 1 sí sube hasta +30 %; ahí el tope ya es el del nivel
    p5, _ = subir_hasta_el_tope(cl, "base", dias="5", **kw)
    assert p5["semanas"][0]["min"] == 125 and p5["volumen"]["maximo"] == "Llegaste al máximo de tu nivel."


def test_el_texto_usa_los_minutos_reales_de_la_semana_1(web_ctx):
    uid, cl = nueva(web_ctx)
    kw = dict(frecuencia_actual="3", corrida_larga="40", dias="2")
    for pct in ("0", "10", "20", "30"):
        r = vista(cl, "base", ajuste_pct=pct, **kw)
        d = incrusto(r)
        assert volumen_texto(r)[0] == d["semanas"][0]["min"], pct
    kw = dict(frecuencia_actual="3", corrida_larga="40")
    r = vista(cl, "base", ajuste_pct="20", **kw)
    assert volumen_texto(r)[0] == incrusto(r)["semanas"][0]["min"]


def test_recomendacion_siempre_visible_y_aviso_desde_15(web_ctx):
    uid, cl = nueva(web_ctx)
    kw = dict(frecuencia_actual="3", corrida_larga="40")
    d0 = incrusto(vista(cl, "base", **kw))["volumen"]["recomendacion"]
    assert d0["clase"] == "nota" and "Recomendado: no subir más de 10–20 %" in d0["texto"]
    assert "Recomendado: no subir más de 10–20 %" in vista(cl, "base", **kw).text
    assert incrusto(vista(cl, "base", ajuste_pct="10", **kw))["volumen"]["recomendacion"]["clase"] == "nota"
    d15 = incrusto(vista(cl, "base", ajuste_pct="15", **kw))["volumen"]["recomendacion"]
    assert d15["clase"] == "warn" and "no pasar de +20 %" not in d15["texto"]
    d25 = incrusto(vista(cl, "base", ajuste_pct="25", **kw))["volumen"]["recomendacion"]
    assert d25["clase"] == "warn" and "no pasar de +20 %" in d25["texto"]


def test_vista_previa_orden_y_plan_completo(web_ctx):
    uid, cl = nueva(web_ctx)
    r = vista(cl, "base", frecuencia_actual="3", corrida_larga="40")
    t = r.text
    pos = [t.index(x) for x in ('id="pn-volumen"', 'id="pn-ranura"', 'id="pn-barras"', 'id="pn-plan"', 'id="pn-porques"', "Confirmar mi plan")]
    assert pos == sorted(pos) and "Tus dos primeras semanas" not in t
    assert 'data-titulo="Ver el plan completo"' in t and "/estaticos/plan_nuevo.js" in t and '/vistas.js' in t
    d = incrusto(r)
    plan = d["plan"]
    assert plan and plan["semanas"] and len(plan["semanas"]) == len(d["semanas"]) and plan["largo"] == len(d["semanas"])
    assert not any("editar" in str(k) for k in plan)                 # solo lectura
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid) is None and db.get(Ajustes, uid) is None and db.get(CacheData, uid) is None


def test_vista_json_permisos_csrf_y_no_guarda(web_ctx):
    uid_a = crear_usuario(web_ctx, "atleta2@x.com")
    uid_c = crear_usuario(web_ctx, "coach2@x.com")
    crear_usuario(web_ctx, "otro2@x.com")
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid_a, coach_id=uid_c))
        db.commit()
    anonimo = web_ctx.cliente()
    tok = csrf_de(anonimo.get("/entrar").text)
    r = anonimo.post("/plan/nuevo/vista.json", data={"csrf": tok, "nivel": "base", **respuestas()}, follow_redirects=False)
    assert r.status_code in (303, 302) and r.headers["location"] == "/entrar"
    otro = entrar(web_ctx, web_ctx.cliente(), "otro2@x.com")
    tok = csrf_de(otro.get("/plan/nuevo").text)
    assert otro.post(f"/a/{uid_a}/plan/nuevo/vista.json", data={"csrf": tok, "nivel": "base", **respuestas()}).status_code == 404
    assert otro.post("/plan/nuevo/vista.json", data={"nivel": "base", **respuestas()}).status_code == 403   # sin CSRF
    coach = entrar(web_ctx, web_ctx.cliente(), "coach2@x.com")
    r = datos_json(coach, "base", pref=f"/a/{uid_a}")
    assert r.status_code == 200 and r.json()["plan"]["semanas"]
    # error de respuestas: 400 con texto
    e = datos_json(coach, "base", pref=f"/a/{uid_a}", dias="9")
    assert e.status_code == 400 and "entre 2 y 5" in e.json()["error"]
    with web_ctx.sesiones() as db:
        assert db.get(Plan, uid_a) is None and db.get(Ajustes, uid_a) is None and db.get(CacheData, uid_a) is None
        assert db.query(Cambio).filter_by(atleta_id=uid_a).count() == 0


def test_vista_json_pasa_la_lista_blanca_y_confirmar_guarda_lo_que_se_ve(web_ctx):
    uid, cl = nueva(web_ctx)
    sembrar(web_ctx, uid, semanas=6, por_semana=3, minutos=25)
    kw = dict(corrida_larga="30")
    p = paquete(datos_json(cl, "base", ajuste_pct="10", **kw))
    from dashboard import validar as v
    texto_json = str(p["plan"])
    assert "activityType" not in texto_json and "startTimeLocal" not in texto_json
    assert p["plan"]["semanas"] and v.problemas({"plan": p["plan"]}) is not None
    visto = [s["min"] for s in p["semanas"]]
    assert confirmar(cl, "base", ajuste_pct=str(p["ajuste_pct"]), **kw).status_code == 303
    guardado = plan_de(web_ctx, uid)
    assert [motor_v6.minutos_semana(w) for w in guardado["weeks"]] == visto and guardado["meta"]["ajuste_pct"] == p["ajuste_pct"]
    assert motor_v6.minutos_semana(guardado["weeks"][0]) == int(re.search(r"(\d+) min/semana", p["volumen"]["texto"]).group(1))


def test_la_pagina_del_sitio_sigue_arrancando_sin_la_vista_previa():
    sitio = Path(__file__).parent.parent / "site"
    v = (sitio / "vistas.js").read_text(encoding="utf-8")
    assert 'const ES_SITIO = !!$("app");' in v and "if (ES_SITIO) iniciar();" in v and "if (ES_SITIO) {" in v
    assert '<script src="vistas.js"></script>' in (sitio / "index.html").read_text(encoding="utf-8") and 'id="app"' in (sitio / "index.html").read_text(encoding="utf-8")
