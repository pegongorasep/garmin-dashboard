"""Social S5: perfil de una persona en Juntos (404 sin grupo, interruptores, perfil propio = vista de miembro, lista blanca)."""
import json
from datetime import date, timedelta

from test_web_feed import act, dia, tres, uid_de
from web import feed
from web.modelos import Plan, Usuario

HOY = date.today()
LUN = HOY - timedelta(days=HOY.weekday())


def semana(i, estado, hechas, n):
    ini = LUN + timedelta(weeks=i)
    ses = [{"id": "z2a", "name": "Z2 #1", "tipo": "z2", "estado": "hecha" if hechas else "pendiente", "fecha": (ini + timedelta(days=1)).isoformat() if hechas else None},
           {"id": "z2b", "name": "Z2 #2", "tipo": "z2", "estado": "pendiente", "fecha": None},
           {"id": "larga", "name": "Larga", "tipo": "larga", "estado": "pendiente", "fecha": None}]
    return {"inicio": ini.isoformat(), "n": n, "estado": estado, "stats": {"minutos": 24.0 if hechas else 0},
            "plan": {"total": 3, "hechas": hechas, "plan_min": 95}, "sesiones": ses,
            "dias": [{"fecha": (ini + timedelta(days=k)).isoformat(), "dia_semana": "lmxjvsd"[k], "plan_ses": "Larga" if k == 5 else ""} for k in range(7)]}


def datos_falsos(uid, acts):
    dias = {}
    for i, a in acts:
        dias.setdefault(dia(i), []).append(a)
    pasada = {**semana(-1, "pasada", 3, 2)}
    actual = {**semana(0, "actual", 1, 3), "dias": [{"fecha": d, "actividades": v, "dia_semana": "x", "plan_ses": ""} for d, v in dias.items()]
              + semana(0, "actual", 1, 3)["dias"]}
    return {"generado": HOY.isoformat(), "semanas_hoy": [pasada, actual, semana(1, "futura", 0, 4)], "semana_hoy_idx": 1,
            "racha": {"semanas": 1, "modo": "plan"},
            "plan": {"semanas": [{}] * 10, "largo": 10, "eventos": [{"tipo": "carrera", "desde": (HOY + timedelta(days=30)).isoformat(), "hasta": "x",
                                                         "nombre": "Maraton Secreto", "distancia_km": 10},
                                {"tipo": "viaje", "desde": HOY.isoformat(), "hasta": HOY.isoformat()}]},
            "progreso": {"semanas": [{"inicio": (LUN - timedelta(weeks=k)).isoformat(), "minutos": 30 + k, "km": 5, "plan_min": 60} for k in range(11, -1, -1)]},
            # nada de esto debe salir
            "composicion": {"peso": 80.1}, "rhr_promedio_7d": 51, "hrv": 77, "ultima_corrida": {"nombre": "Ruta Secreta"}}


def falso(monkeypatch, por_usuario):
    def f(db, u, *a, **k):
        return datos_falsos(u.id, por_usuario.get(u.id, []))
    monkeypatch.setattr(feed.calculo, "calcular", f)


def get(cl, uid, **q):
    return cl.get(f"/api/juntos/persona/{uid}", params=q)


def escenario(web_ctx, monkeypatch):
    a, b, c, gid = tres(web_ctx)
    ua, ub, uc = (uid_de(web_ctx, f"{x}@x.com") for x in "abc")
    with web_ctx.sesiones() as db:
        db.add(Plan(usuario_id=ua, plan={"meta": {"motor": "v6", "nivel": "base"}}))
        db.commit()
    falso(monkeypatch, {ua: [(1, act()), (2, act("fuerza", 45, None))], ub: [(1, act())]})
    return a, b, c, ua, ub, uc


def test_404_sin_grupo_en_comun_y_sin_sesion(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    assert get(c, ua).status_code == 404            # c no comparte grupo
    assert get(a, uc).status_code == 404
    assert get(a, 99999).status_code == 404
    assert get(web_ctx.cliente(), ua).status_code == 401
    assert get(b, ua).status_code == 200


def test_perfil_completo_de_un_miembro(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    p = get(b, ua).json()
    assert p["usuario_id"] == ua and p["mia"] is False and p["nivel"] == "base" and len(p["grupos"]) == 1
    assert p["semana"]["minutos"] == 24 and p["semana"]["objetivo"] == 95
    assert p["semana"]["faltan"] == [{"k": "facil", "n": 1}, {"k": "larga"}]
    assert [s["n"] for s in p["calendario"]] == [3, 4]
    assert len(p["progreso"]["semanas"]) == 12 and p["progreso"]["racha"] == 1
    assert p["progreso"]["carreras"] == [{"fecha": (HOY + timedelta(days=30)).isoformat(), "distancia_km": 10}]
    assert len(p["actividades"]["items"]) == 2 and all(x["usuario_id"] == ua for x in p["actividades"]["items"])


def test_matriz_de_interruptores(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    with web_ctx.sesiones() as db:
        db.get(Usuario, ua).compartir_plan = False
        db.commit()
    p = get(b, ua).json()
    assert p["calendario"] is None and p["plan"] is None and p["semana"]["objetivo"] is None and p["semana"]["faltan"] == []
    assert p["progreso"]["racha"] is None and p["progreso"]["carreras"] is None and len(p["progreso"]["semanas"]) == 12   # totales sí
    assert p["actividades"] is not None
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, ua)
        u.compartir_plan, u.compartir_actividades = True, False
        db.commit()
    p = get(b, ua).json()
    assert p["actividades"] is None and p["calendario"] is not None
    assert not any(d["hecha"] for w in p["calendario"] for d in w["dias"])   # sin días llenos ni nombres de actividades
    assert all(x["estado"] != "hecha" for w in p["calendario"] for x in w["sesiones"])
    assert b.get("/api/juntos/feed", params={"persona": ua}).json()["items"] == []   # el feed tampoco la muestra


def test_perfil_propio_igual_a_vista_de_miembro_y_respeta_interruptores(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    yo, ellos = get(a, ua).json(), get(b, ua).json()
    def igual(x):
        x = {k: v for k, v in x.items() if k not in ("mia", "yo")}
        x["actividades"] = [{k: v for k, v in i.items() if k != "mia"} for i in x["actividades"]["items"]]
        return x
    assert igual(yo) == igual(ellos)
    assert yo["mia"] is True
    with web_ctx.sesiones() as db:
        db.get(Usuario, ua).compartir_actividades = False
        db.commit()
    yo, ellos = get(a, ua).json(), get(b, ua).json()
    assert yo["actividades"] is None and yo["comparte"] == ellos["comparte"] == {"plan": True, "actividades": False}
    assert yo["interruptores"]["actividades"] is False


def test_feed_con_persona_filtra_y_pagina(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    falso(monkeypatch, {ua: [(i, act(minutos=30 + i)) for i in range(1, 25)], ub: [(1, act())]})
    r = b.get("/api/juntos/feed", params={"persona": ua}).json()
    assert len(r["items"]) == 20 and {x["usuario_id"] for x in r["items"]} == {ua}
    p = get(b, ua).json()["actividades"]
    assert len(p["items"]) == 10 and p["siguiente"]
    sig = b.get("/api/juntos/feed", params={"persona": ua, "antes": p["siguiente"]}).json()
    assert not {x["clave"] for x in p["items"]} & {x["clave"] for x in sig["items"]}
    assert b.get("/api/juntos/feed", params={"persona": uc}).json()["items"] == []


def test_perfil_sin_campos_prohibidos(web_ctx, monkeypatch):
    a, b, c, ua, ub, uc = escenario(web_ctx, monkeypatch)
    for cl in (a, b):
        crudo = get(cl, ua).text
        for prohibido in ("Secreto", "Maraton", "Ruta", "activityId", "activityName", "ownerDisplayName", "startLatitude", "birthDate",
                          "correo", "a@x.com", "peso", "80.1", "hrv", "rhr", "composicion", "inbody", "fecha_nacimiento", "latitud", "gps"):
            assert prohibido.lower() not in crudo.lower(), prohibido
        assert set(json.loads(crudo)) <= {"usuario_id", "nombre", "mia", "pausa", "foto", "nivel", "grupos", "comparte", "interruptores", "semana",
                                          "plan", "calendario", "progreso", "actividades", "emojis", "yo"}


# ---- S6: tarjetas del grupo con semana vs plan y mini calendario ----
def _tarjeta(web_ctx, monkeypatch, *, act_on=True, plan_on=True, sesiones=None):
    from web import grupos_resumen
    from web.modelos import Ajustes, MiembroGrupo
    a, b, c, gid = tres(web_ctx)
    ua = uid_de(web_ctx, "a@x.com")
    ini = LUN
    ses = sesiones or [{"name": "Z2 #1", "tipo": "z2", "estado": "hecha"}, {"name": "Z2 #2", "tipo": "z2", "estado": "pendiente"},
                       {"name": "Larga", "tipo": "larga", "estado": "pendiente"}]
    dias = [{"fecha": (ini + timedelta(days=k)).isoformat(), "corrida": {"minutos": 30} if k == 0 else None,
             "otras": [{"cat": "crossfit", "minutos": 40}] if k == 1 else []} for k in range(7)]
    data = {"generado": (ini + timedelta(days=2)).isoformat(), "semana_hoy_idx": 0, "plan": {"eventos": []},
            "semanas_hoy": [{"estado": "actual", "inicio": ini.isoformat(), "n": 3, "stats": {"minutos": 30.0, "km": 4},
                             "plan": {"total": 3, "hechas": 1, "plan_min": 95}, "sesiones": ses, "dias": dias}]}
    monkeypatch.setattr(grupos_resumen.calculo, "calcular", lambda db, u: data)
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, ua)
        u.compartir_actividades, u.compartir_plan = act_on, plan_on
        db.add(Ajustes(usuario_id=ua, config={})); db.add(Plan(usuario_id=ua, plan={"weeks": []})); db.commit()
        m = db.query(MiembroGrupo).filter_by(grupo_id=gid, usuario_id=ua).one()
        return grupos_resumen.tarjeta_de(db, u, m)


def test_tarjeta_semana_vs_plan_y_calendario(web_ctx, monkeypatch):
    t = _tarjeta(web_ctx, monkeypatch)
    assert t["sem_plan"] == {"minutos": 30, "objetivo": 95, "faltan": [{"k": "facil", "n": 1}, {"k": "larga"}]}
    assert [d["cats"] for d in t["cal"][:3]] == [["run"], ["crossfit"], []]
    assert [d["hecha"] for d in t["cal"][:3]] == [True, True, False] and [d["hoy"] for d in t["cal"]].index(True) == 2


def test_tarjeta_semana_completa_sin_faltan(web_ctx, monkeypatch):
    t = _tarjeta(web_ctx, monkeypatch, sesiones=[{"name": "Z2", "tipo": "z2", "estado": "hecha"}])
    assert t["sem_plan"]["objetivo"] == 95 and t["sem_plan"]["faltan"] == []


def test_faltan_texto_calidad_y_orden():
    from web import semana_plan
    ses = [{"tipo": "z2", "estado": "pendiente"}, {"tipo": "z2", "estado": "pendiente"}, {"tipo": "calidad", "estado": "pendiente"},
           {"tipo": "prueba", "estado": "pendiente"}, {"tipo": "larga", "estado": "hecha"}]
    assert semana_plan.faltan(ses) == [{"k": "facil", "n": 2}, {"k": "calidad"}, {"k": "larga"}]


import pytest


@pytest.mark.parametrize("act_on,plan_on", [(True, False), (False, True), (False, False)])
def test_matriz_de_interruptores_en_la_tarjeta(web_ctx, monkeypatch, act_on, plan_on):
    t = _tarjeta(web_ctx, monkeypatch, act_on=act_on, plan_on=plan_on)
    if not plan_on:   # plan apagado: solo minutos
        assert t["sem_plan"] == {"minutos": 30, "objetivo": None, "faltan": []}
    else:
        assert t["sem_plan"]["objetivo"] == 95 and t["sem_plan"]["faltan"]
    if act_on:
        assert t["cal"][0]["cats"] == ["run"]
    else:   # actividades apagadas: nada por día (solo totales)
        assert t["cal"] is None and t["dias"] == [] and t["ultima"] is None
