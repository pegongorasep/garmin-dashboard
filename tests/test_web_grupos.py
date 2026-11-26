"""G2: grupos (crear, unirse, salir, quitar, pausar) y foto para quienes comparten grupo."""
import re

from test_web_cuentas import csrf_de, entrar, crear_usuario
from test_web_perfil import con_exif_gps
from web import perfil
from web.modelos import FotoPerfil, Grupo, InvitacionGrupo, MiembroGrupo, Usuario


def sesion(ctx, correo):
    crear_usuario(ctx, correo)
    return entrar(ctx, ctx.cliente(), correo)


def post(cl, url, **campos):
    return cl.post(url, data={"csrf": csrf_de(cl.get("/grupos/nuevo").text), **campos})


def crear(cl, nombre="Los Fieras"):
    r = post(cl, "/grupos/nuevo", nombre=nombre)
    assert r.status_code == 303
    return int(r.headers["location"].rsplit("/", 1)[1])


def liga(cl, gid):
    t = post(cl, f"/grupos/{gid}/invitar").text
    return re.search(r"/grupos/unirse/([\w-]+)", t).group(1)


def test_crear_y_unirse(web_ctx):
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    assert "Los Fieras" in a.get(f"/grupos/{gid}").text
    tk = liga(a, gid)
    assert b.get(f"/grupos/{gid}").status_code == 404           # aún no es miembro
    assert "Los Fieras" in b.get(f"/grupos/unirse/{tk}").text    # GET no une
    assert b.get(f"/grupos/{gid}").status_code == 404
    assert post(b, f"/grupos/unirse/{tk}").headers["location"] == f"/grupos/{gid}"
    assert b.get(f"/grupos/{gid}").status_code == 200
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).filter_by(grupo_id=gid).count() == 2
        assert tk not in {i.token_hash for i in db.query(InvitacionGrupo)}   # solo hash


def test_unirse_requiere_sesion_y_liga_valida(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    tk = liga(a, gid)
    anon = web_ctx.cliente()
    assert anon.get(f"/grupos/unirse/{tk}").status_code == 401
    assert anon.get("/grupos").headers["location"] == "/entrar"
    b = sesion(web_ctx, "b@x.com")
    assert b.get("/grupos/unirse/malo").status_code == 404
    assert post(b, "/grupos/unirse/malo").status_code == 404


def test_solo_cuerpo_no_puede_unirse(web_ctx):
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    with web_ctx.sesiones() as db:
        db.query(Usuario).filter_by(correo="b@x.com").one().uso = "cuerpo"
        db.commit()
    gid = crear(a)
    tk = liga(a, gid)
    assert post(b, f"/grupos/unirse/{tk}").status_code == 403
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).filter_by(grupo_id=gid).count() == 1


def test_no_miembro_recibe_404_en_todo(web_ctx):
    a, c = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "c@x.com")
    gid = crear(a)
    assert c.get(f"/grupos/{gid}").status_code == 404
    for ruta in ("invitar", "pausar", "salir"):
        assert post(c, f"/grupos/{gid}/{ruta}").status_code == 404
    assert post(c, f"/grupos/{gid}/quitar/1").status_code == 404
    assert "Los Fieras" not in c.get("/grupos").text


def test_post_sin_csrf_es_403(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    assert a.post("/grupos/nuevo", data={"nombre": "X"}).status_code == 403


def test_quitar_y_salir(web_ctx):
    a, b, c = (sesion(web_ctx, f"{x}@x.com") for x in "abc")
    gid = crear(a)
    tk = liga(a, gid)
    post(b, f"/grupos/unirse/{tk}"), post(c, f"/grupos/unirse/{tk}")
    with web_ctx.sesiones() as db:
        ub = db.query(Usuario).filter_by(correo="b@x.com").one().id
    assert post(b, f"/grupos/{gid}/quitar/{ub}").status_code == 403   # no es admin
    assert post(a, f"/grupos/{gid}/quitar/{ub}").status_code == 303
    assert b.get(f"/grupos/{gid}").status_code == 404
    # la admin sale: c (la más antigua que queda) pasa a admin
    assert post(a, f"/grupos/{gid}/salir").headers["location"] == "/grupos"
    with web_ctx.sesiones() as db:
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid).one()
        assert m.rol == "admin"
    post(c, f"/grupos/{gid}/salir")
    with web_ctx.sesiones() as db:
        assert db.get(Grupo, gid) is None and db.query(InvitacionGrupo).count() == 0


def test_pausar(web_ctx):
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    post(a, f"/grupos/{gid}/pausar", pausado="1")
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().pausado is True
    assert "grupo" in a.get(f"/grupos/{gid}").text.lower()
    post(a, f"/grupos/{gid}/pausar", pausado="0")
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().pausado is False


def test_foto_la_ven_quienes_comparten_grupo(web_ctx):
    a, b, c = (sesion(web_ctx, f"{x}@x.com") for x in "abc")
    with web_ctx.sesiones() as db:
        ua = db.query(Usuario).filter_by(correo="a@x.com").one().id
        perfil.guardar_foto(db, ua, perfil.procesar_foto(con_exif_gps()))
        db.commit()
    assert b.get(f"/perfil/foto/{ua}").status_code == 404
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    assert b.get(f"/perfil/foto/{ua}").status_code == 200
    assert c.get(f"/perfil/foto/{ua}").status_code == 404
    assert f"/perfil/foto/{ua}" in b.get(f"/grupos/{gid}").text


def test_borrar_cuenta_limpia_grupos(web_ctx):
    from web import cuenta
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        cuenta.borrar_cuenta(db, db.query(Usuario).filter_by(correo="a@x.com").one())
    with web_ctx.sesiones() as db:
        assert db.query(MiembroGrupo).one().rol == "admin"
        assert db.get(Grupo, gid).creado_por is None
    assert b.get(f"/grupos/{gid}").status_code == 200


def test_tarjetas_pausa_y_sin_plan_solo_campos_permitidos(web_ctx):
    from web import grupos_resumen
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    pag = a.get(f"/grupos/{gid}").text
    assert pag.count("Sin plan todavía") == 2
    post(b, f"/grupos/{gid}/pausar", pausado="1")
    pag = a.get(f"/grupos/{gid}").text
    assert "En pausa" in pag and pag.count("Sin plan todavía") == 1
    with web_ctx.sesiones() as db:
        ms = [(m, db.get(Usuario, m.usuario_id)) for m in db.query(MiembroGrupo).filter_by(grupo_id=gid)]
        for c in grupos_resumen.tarjetas(db, ms).values():
            assert set(c) == grupos_resumen.CAMPOS
            if c["estado"] != "ok":
                assert c["meta"] is None and c["adherencia"] is None and c["dias"] == [] and c["ultima"] is None


def test_tarjeta_con_plan_solo_campos_permitidos(web_ctx, monkeypatch):
    from web import grupos_resumen
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    data = {"generado": "2026-11-26T08:00", "semana_hoy_idx": 0, "ultima_corrida": {"fecha": "2026-11-24", "fc_prom": 150},
            "plan": {"eventos": [{"tipo": "carrera", "desde": "2027-01-10", "nombre": "10K"}]},
            "semanas_hoy": [{"estado": "actual", "n": 5, "plan": {"total": 3, "hechas": 2},
                             "dias": [{"fecha": f"2026-11-{23 + i}", "corrida": {"minutos": 30} if i in (1, 3) else None} for i in range(7)]}]}
    monkeypatch.setattr(grupos_resumen.calculo, "calcular", lambda db, u: data)
    with web_ctx.sesiones() as db:
        from web.modelos import Ajustes, Plan
        u = db.query(Usuario).filter_by(correo="a@x.com").one()
        db.add(Ajustes(usuario_id=u.id, config={})); db.add(Plan(usuario_id=u.id, plan={"weeks": []})); db.commit()
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid).one()
        c = grupos_resumen.tarjeta_de(db, u, m)
    assert set(c) == grupos_resumen.CAMPOS and c["estado"] == "ok"
    assert c["meta"] == "10K" and c["etapa_n"] == 5 and c["ultima"] == "2026-11-24"
    assert c["dias"][1] == "hecha" and c["dias"][2] == "libre" and c["dias"][4] == "futuro"
    pag = a.get(f"/grupos/{gid}").text
    assert "10K" in pag and "Semana 5" in pag and "Adherencia 67%" in pag and "2026-11-24" in pag
    assert not re.search(r"\b150\b", pag)   # la FC no sale (\b: un token CSRF al azar puede llevar "150" dentro)


def test_reacciones(web_ctx):
    from web import cuenta
    from web.modelos import Reaccion
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        ua = db.query(Usuario).filter_by(correo="a@x.com").one().id
        ub = db.query(Usuario).filter_by(correo="b@x.com").one().id
    assert post(a, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥").status_code == 400   # a sí misma
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="x").status_code == 400
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥").status_code == 303
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 1
    assert "🔥 1" in b.get(f"/grupos/{gid}").text
    assert "te reaccionaron" in a.get(f"/grupos/{gid}").text
    post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥")                              # toggle
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 0
    post(a, f"/grupos/{gid}/pausar", pausado="1")                                     # pausada: no recibe
    assert post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏").status_code == 400
    post(a, f"/grupos/{gid}/pausar", pausado="0")
    post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏")
    post(a, f"/grupos/{gid}/reaccionar/{ub}", emoji="💪")
    c = sesion(web_ctx, "c@x.com")
    assert post(c, f"/grupos/{gid}/reaccionar/{ua}", emoji="👏").status_code == 404
    with web_ctx.sesiones() as db:
        cuenta.borrar_cuenta(db, db.query(Usuario).filter_by(correo="a@x.com").one())
    with web_ctx.sesiones() as db:
        assert db.query(Reaccion).count() == 0


def test_tarjeta_sin_plan_usa_semana_libre(web_ctx, monkeypatch):
    from web import grupos_resumen
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    sl = {"actividades": 3, "minutos": 95.4, "racha_semanas": 4, "km": 9, "nombre": "Ruta secreta",
          "dias": [{"actividades": [{"nombre": "Correr", "minutos": 30}] if i in (0, 2, 3) else [], "futuro": i > 3} for i in range(7)]}
    monkeypatch.setattr(grupos_resumen.calculo, "calcular", lambda db, u: {"semana_libre": sl})
    with web_ctx.sesiones() as db:
        u = db.query(Usuario).filter_by(correo="a@x.com").one()
        u.sin_plan, u.repo_id = True, 1
        db.commit()
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid).one()
        c = grupos_resumen.tarjeta_de(db, u, m)
    assert set(c) == grupos_resumen.CAMPOS and c["estado"] == "libre"
    assert c["dias"] == ["hecha", "libre", "hecha", "hecha", "futuro", "futuro", "futuro"]
    assert c["libre"] == {"actividades": 3, "minutos": 95, "racha": 4}
    pag = a.get(f"/grupos/{gid}").text
    assert "3 actividades · 95 min esta semana" in pag and "Racha: 4 semanas activas" in pag
    assert "Ruta secreta" not in pag


def _t(uid, km=0, minutos=0, otras=None, hechas=None, total=3, estado="ok", carrera=None, racha=0):
    return {"usuario_id": uid, "estado": estado, "carrera": carrera, "racha": racha,
            "semana": None if estado == "pausa" else {"km": km, "minutos": minutos, "otras": otras or {}, "extra_min": 0},
            "progreso": {"hechas": hechas, "total": total} if hechas is not None else None}


def test_total_e_insignias_empates_y_ceros():
    from web import grupos_resumen as g
    ts = [_t(1, 10, 60, hechas=2), _t(2, 10, 50, hechas=2), _t(3, 0, 0), _t(4, 99, 99, estado="pausa")]
    assert g.total_grupo(ts) == {"km": 20.0, "minutos": 110}   # la pausa no suma
    ins = {i["clave"]: i["usuario_ids"] for i in g.insignias(ts, {1: {"larga": 40}, 2: {"larga": 40}, 3: {"larga": 0}})}
    assert ins == {"mas_constante": [1, 2], "mas_km": [1, 2], "corrida_mas_larga": [1, 2]}   # empate: todos; el 0 no gana
    assert g.insignias([_t(1, 5, 30, hechas=1), _t(2)], {}) == []                              # solo 1 con actividad
    assert g.insignias([_t(1, 5, 30), _t(2, 3, 20, estado="pausa")], {}) == []                 # la pausa no cuenta
    assert [i["clave"] for i in g.insignias([_t(1, 5, 30), _t(2, 0, 20)], {1: {"larga": 30}, 2: {"larga": 0}})] == ["mas_km", "corrida_mas_larga"]


def test_novedades_cada_tipo_max_3_y_pausa():
    from web import grupos_resumen as g
    h = {"hoy": "2026-11-26", "ini_sem": "2026-11-23", "completa_ahora": True, "completa_antes": False, "record": 8.5,
         "racha": 3, "n": 5, "n_antes": 4, "total": 12, "larga": 40}
    t = _t(1, 8, 60, hechas=3, carrera={"nombre": "10K", "dias": 5}, racha=3)
    nov = g.novedades([t], {1: h})
    assert [n["tipo"] for n in nov] == ["semana_completa", "record_distancia", "carrera_cerca"]   # máx. 3, lo más nuevo primero (racha, de la semana pasada, queda fuera)
    assert nov[0]["datos"] == {"n": 5, "total": 12} and nov[1]["datos"] == {"km": 8.5} and nov[2]["datos"] == {"dias": 5}
    assert [n["tipo"] for n in g.novedades([_t(1, racha=3)], {1: {**h, "completa_ahora": False, "record": None}})] == ["racha"]
    assert [n["tipo"] for n in g.novedades([_t(1, carrera={"nombre": "10K", "dias": 7})], {1: {**h, "completa_ahora": False, "record": None, "racha": 1}})] == ["carrera_cerca"]
    assert g.novedades([_t(1, carrera={"nombre": "x", "dias": 8})], {1: {**h, "completa_ahora": False, "record": None, "racha": 0}}) == []
    antes = g.novedades([t], {1: {**h, "completa_ahora": False, "completa_antes": True, "record": None, "racha": 0}})
    assert next(n for n in antes if n["tipo"] == "semana_completa")["datos"] == {"n": 4, "total": 12}                                    # semana pasada completada
    pausa = {**t, "estado": "pausa"}
    assert g.novedades([pausa], {1: h}) == []                                            # la pausa no aparece


def test_tarjeta_nuevos_campos_racha_record_carrera(web_ctx, monkeypatch):
    from web import grupos_resumen
    a = sesion(web_ctx, "a@x.com")
    gid = crear(a)
    def sem(est, n, hechas, total=3, **extra):
        return {"estado": est, "n": n, "inicio": f"2026-11-{2 + 7 * (n - 1):02d}", "plan": {"total": total, "hechas": hechas},
                "stats": {"km": 12.34, "minutos": 80}, "dias": [{"fecha": "x", "corrida": {"minutos": 40} if i == 0 else None,
                                                                 "otras": [{"cat": "fuerza", "minutos": 30}] if i == 2 else []} for i in range(7)], **extra}
    data = {"generado": "2026-11-26T08:00", "semana_hoy_idx": 3, "ultima_corrida": None,
            "plan": {"inicio": "2026-11-02", "eventos": [{"tipo": "carrera", "desde": "2026-12-01", "nombre": "10K"}],
                     "semanas": [{}] * 12},
            "progreso": {"corridas": [{"fecha": "2026-11-05", "km": 5.0}, {"fecha": "2026-11-24", "km": 7.0}]},
            "semanas_hoy": [sem("pasada", 1, 1), sem("pasada", 2, 3), sem("pasada", 3, 2), sem("actual", 4, 3, inicio="2026-11-23")]}
    monkeypatch.setattr(grupos_resumen.calculo, "calcular", lambda db, u: data)
    with web_ctx.sesiones() as db:
        from web.modelos import Ajustes, Plan
        u = db.query(Usuario).filter_by(correo="a@x.com").one()
        db.add(Ajustes(usuario_id=u.id, config={})); db.add(Plan(usuario_id=u.id, plan={"weeks": []})); db.commit()
        ms = [(m, u) for m in db.query(MiembroGrupo).filter_by(grupo_id=gid)]
        r = grupos_resumen.resumen(db, ms)
    c = r["tarjetas"][u.id]
    assert set(c) == grupos_resumen.CAMPOS
    assert c["semana"] == {"km": 12.3, "minutos": 80, "otras": {"fuerza": 1}, "extra_min": 30}
    assert c["plan"] == {"n": 4, "total": 12} and c["progreso"] == {"hechas": 3, "total": 3}
    assert c["racha"] == 2 and c["carrera"] == {"nombre": "10K", "dias": 5}
    assert len(r["novedades"]) == 3
    assert {n["tipo"] for n in r["novedades"]} <= {"semana_completa", "record_distancia", "racha", "carrera_cerca"}
    assert all(set(n) == {"tipo", "usuario_id", "datos"} for n in r["novedades"])
    assert r["total"] == {"km": 12.3, "minutos": 110} and r["insignias"] == []   # una sola persona: sin insignias


def test_reacciones_ocho_emojis_y_quienes_por_emoji(web_ctx):
    from web import grupos
    assert len(grupos.EMOJIS) == 8 and set(grupos.EMOJIS) >= {"❤️", "🫡", "🚀", "🏆", "😂"}
    a, b, c = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com"), sesion(web_ctx, "c@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}"); post(c, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        ua, ub, uc = (db.query(Usuario).filter_by(correo=f"{x}@x.com").one().id for x in "abc")
    for cl, e in ((b, "❤️"), (c, "❤️"), (c, "🫡")):
        assert post(cl, f"/grupos/{gid}/reaccionar/{ua}", emoji=e).status_code == 303
    with web_ctx.sesiones() as db:
        r = grupos.reacciones_de(db, gid, grupos.semana_iso(), ub)[ua]
        assert r["por_emoji"] == {"❤️": [ub, uc], "🫡": [uc]} and r["cuentas"]["❤️"] == 2 and r["mias"] == {"❤️"}
    post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="❤️")   # toggle
    with web_ctx.sesiones() as db:
        assert grupos.reacciones_de(db, gid, grupos.semana_iso(), ub)[ua]["por_emoji"]["❤️"] == [uc]


# --- G2 (parte 2): API JSON y ui.grupos ---

def _dos(web_ctx):
    a, b = sesion(web_ctx, "a@x.com"), sesion(web_ctx, "b@x.com")
    gid = crear(a)
    post(b, f"/grupos/unirse/{liga(a, gid)}")
    with web_ctx.sesiones() as db:
        ua = db.query(Usuario).filter_by(correo="a@x.com").one().id
        ub = db.query(Usuario).filter_by(correo="b@x.com").one().id
    return a, b, gid, ua, ub


def test_api_requiere_sesion_y_miembro(web_ctx):
    a, b, gid, ua, ub = _dos(web_ctx)
    anon = web_ctx.cliente()
    assert anon.get("/api/grupos").status_code == 401 and anon.get(f"/api/grupos/{gid}").status_code == 401
    c = sesion(web_ctx, "c@x.com")
    assert c.get(f"/api/grupos/{gid}").status_code == 404 and c.get("/api/grupos").json() == []
    assert a.get("/api/grupos").json() == [{"id": gid, "nombre": "Los Fieras", "miembros_n": 2}]


def test_api_forma_y_lista_blanca(web_ctx):
    from web import grupos_resumen
    a, b, gid, ua, ub = _dos(web_ctx)
    d = a.get(f"/api/grupos/{gid}").json()
    assert set(d) == {"grupo", "yo", "miembros", "total", "insignias", "novedades", "emojis", "admin_url"}
    assert d["grupo"] == {"id": gid, "nombre": "Los Fieras"} and d["yo"] == ua and d["admin_url"] == f"/grupos/{gid}"
    assert len(d["emojis"]) == 8
    for m in d["miembros"]:
        assert set(m) == {"usuario_id", "nombre", "foto", "tarjeta", "reacciones"}
        assert set(m["tarjeta"]) <= grupos_resumen.CAMPOS
        assert m["foto"] is None


def test_api_pausado_sin_reacciones_y_reaccion_json(web_ctx):
    a, b, gid, ua, ub = _dos(web_ctx)
    r = post(b, f"/grupos/{gid}/reaccionar/{ua}", emoji="🔥")           # sin Accept: redirección de siempre
    assert r.status_code == 303
    cs = csrf_de(b.get("/grupos/nuevo").text)
    j = b.post(f"/grupos/{gid}/reaccionar/{ua}", data={"csrf": cs, "emoji": "🏆"}, headers={"accept": "application/json"})
    assert j.status_code == 200
    rr = j.json()
    assert rr["para_id"] == ua and rr["reacciones"]["🔥"] == {"n": 1, "quienes": ["Ana Prueba"], "mia": True}
    assert rr["reacciones"]["🏆"]["mia"] is True
    d = a.get(f"/api/grupos/{gid}").json()
    mia = next(m for m in d["miembros"] if m["usuario_id"] == ua)
    assert mia["reacciones"]["🔥"]["mia"] is False and mia["reacciones"]["🔥"]["n"] == 1
    j = b.post(f"/grupos/{gid}/reaccionar/{ua}", data={"csrf": cs, "emoji": "🏆"}, headers={"accept": "application/json"})
    assert "🏆" not in j.json()["reacciones"]                           # toggle
    post(a, f"/grupos/{gid}/pausar", pausado="1")
    mia = next(m for m in a.get(f"/api/grupos/{gid}").json()["miembros"] if m["usuario_id"] == ua)
    assert mia["reacciones"] == {} and mia["tarjeta"]["estado"] == "pausa"


def test_reaccion_json_exige_csrf(web_ctx):
    a, b, gid, ua, ub = _dos(web_ctx)
    h = {"accept": "application/json"}
    assert b.post(f"/grupos/{gid}/reaccionar/{ua}", data={"emoji": "🔥"}, headers=h).status_code == 403
    assert b.post(f"/grupos/{gid}/reaccionar/{ua}", data={"csrf": "malo", "emoji": "🔥"}, headers=h).status_code == 403
    c = sesion(web_ctx, "c@x.com")
    cs = csrf_de(c.get("/grupos/nuevo").text)
    assert c.post(f"/grupos/{gid}/reaccionar/{ua}", data={"csrf": cs, "emoji": "🔥"}, headers=h).status_code == 404


def test_ui_grupos_0_1_2(web_ctx):
    crear_usuario(web_ctx, "a@x.com", con_ajustes=True)
    a = entrar(web_ctx, web_ctx.cliente(), "a@x.com")
    n = lambda: a.get("/data.json").json()["ui"]["grupos"]   # noqa: E731
    assert n() == 0
    crear(a)
    assert n() == 1                     # fuera de la caché: se ve al momento
    crear(a, "Otro")
    assert n() == 2
