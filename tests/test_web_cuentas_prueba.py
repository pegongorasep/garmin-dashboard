"""Cuentas de prueba (`@prueba.test`) desde /admin."""
import re
from datetime import date

import httpx

from dashboard import paquete
from web import auth, correo, cuentas_prueba
from web.config import Settings
from web.modelos import Consentimiento, DatoGarmin, LigaLogin, Usuario
from web.privacidad import VERSION_AVISO
from ayudas import HOY, csrf_de, listo, post


def admin_listo(ctx):
    return listo(ctx, "pedro@example.com")   # ADMIN_CORREO de la prueba


def cuenta_de(ctx, mail):
    with ctx.sesiones() as db:
        return db.query(Usuario).filter(Usuario.correo == mail).one_or_none()


def liga_en(html):
    return re.search(r"https://ahilallevas\.test(/entrar/liga/[^<\s]+)", html).group(1)


def test_dominio_de_prueba():
    assert auth.es_correo_prueba(" Ana@Prueba.TEST ")
    assert auth.es_correo_prueba("a@otro.test")
    for real in ("a@x.com", "a.test@gmail.com", "a@test.com", "a@mi-test", "sin-arroba.test"):
        assert not auth.es_correo_prueba(real)


def test_a_un_correo_de_prueba_no_se_le_manda_nada(monkeypatch):
    llamadas = []

    def post_falso(*a, **k):
        llamadas.append(k["json"]["to"])
        return httpx.Response(200, request=httpx.Request("POST", "https://api.resend.com/emails"))

    monkeypatch.setattr(httpx, "post", post_falso)
    s = Settings(database_url="sqlite://", resend_api_key="x")
    assert correo.enviar(s, "ana@prueba.test", "a", "b") is False and llamadas == []
    assert correo.enviar(s, "ana@example.com", "a", "b") is True and llamadas == [["ana@example.com"]]


def test_crear_entrar_y_borrar(web_ctx):
    _, cl = admin_listo(web_ctx)
    r = cl.post("/admin/prueba/crear", data={"csrf": csrf_de(cl.get("/admin").text), "nombre": " Ana "})
    assert r.status_code == 200
    u = cuenta_de(web_ctx, "ana@prueba.test")
    assert u is not None and not u.es_admin
    otro = web_ctx.cliente()
    ruta = liga_en(r.text)
    assert post(otro, ruta).status_code == 303
    assert otro.get("/").headers["location"] == "/perfil"   # entra como alguien que recién llega
    assert [para for para, *_ in web_ctx.enviados] == ["pedro@example.com"]   # solo el código con que entró el admin
    assert post(web_ctx.cliente(), ruta).status_code == 400   # un solo uso
    csrf = csrf_de(cl.get("/admin").text)
    for _ in range(auth.LIGAS_POR_HORA + 1):   # sin el límite de las ligas por correo
        liga_en(cl.post("/admin/prueba/liga", data={"csrf": csrf, "id": u.id}).text)
    r2 = cl.post("/admin/prueba/borrar", data={"csrf": csrf, "id": u.id})
    assert "ana@prueba.test borrada" in r2.text
    assert cuenta_de(web_ctx, "ana@prueba.test") is None
    assert otro.get("/privacidad/mis-datos").status_code == 303   # su sesión se fue con la cuenta
    with web_ctx.sesiones() as db:
        assert db.query(LigaLogin).count() == 0


def test_nombre_malo_o_repetido(web_ctx):
    _, cl = admin_listo(web_ctx)
    csrf = csrf_de(cl.get("/admin").text)
    for malo in ("", "a@gmail.com", "ñandú", "-a", "a" * 31, "a b"):
        r = cl.post("/admin/prueba/crear", data={"csrf": csrf, "nombre": malo})
        assert "Usa de 1 a 30" in r.text and "/entrar/liga/" not in r.text
    cl.post("/admin/prueba/crear", data={"csrf": csrf, "nombre": "ana"})
    r = cl.post("/admin/prueba/crear", data={"csrf": csrf, "nombre": "ANA"})
    assert "Ya existe ana@prueba.test" in r.text and "/entrar/liga/" not in r.text
    with web_ctx.sesiones() as db:
        assert db.query(Usuario).count() == 2


def test_nunca_sobre_cuentas_reales_ni_de_admin(web_ctx):
    admin_id, cl = admin_listo(web_ctx)
    real, _ = listo(web_ctx, "b@x.com")
    otro_admin, _ = listo(web_ctx, "jefa@prueba.test")
    with web_ctx.sesiones() as db:
        db.get(Usuario, otro_admin).es_admin = True
        db.commit()
        antes = db.query(LigaLogin).count()
    html = cl.get("/admin").text
    assert 'action="/admin/prueba/liga"' not in html   # ni siquiera se ofrece
    for ident in (admin_id, real, otro_admin, 9999, "x", ""):
        for ruta in ("liga", "borrar"):
            assert cl.post(f"/admin/prueba/{ruta}", data={"csrf": csrf_de(html), "id": ident}).status_code == 404
    with web_ctx.sesiones() as db:
        assert db.query(Usuario).count() == 3 and db.query(LigaLogin).count() == antes


def test_no_admin_recibe_404(web_ctx):
    _, cl = listo(web_ctx, "a@x.com")
    victima, _ = listo(web_ctx, "c@prueba.test")
    csrf = csrf_de(cl.get("/privacidad/mis-datos").text)
    for ruta, datos in (("crear", {"nombre": "z"}), ("liga", {"id": victima}), ("borrar", {"id": victima})):
        assert cl.post(f"/admin/prueba/{ruta}", data={"csrf": csrf, **datos}).status_code == 404
        assert cl.post(f"/admin/prueba/{ruta}", data=datos).status_code == 403   # sin CSRF
    with web_ctx.sesiones() as db:
        assert db.query(Usuario).count() == 2


def test_historial_inventado():
    hoy = date(2026, 11, 26)   # jueves
    assert cuentas_prueba.inventar_historial("vacia", hoy, "a") == ([], {})
    for nombre in ("empezando", "constante", "crossfit"):
        acts, detalles = cuentas_prueba.inventar_historial(nombre, hoy, "a@prueba.test")
        assert (acts, detalles) == cuentas_prueba.inventar_historial(nombre, hoy, "a@prueba.test")
        assert len({a["id"] for a in acts}) == len(acts) > 5
        fechas = [a["startTimeLocal"][:10] for a in acts]
        assert max(fechas) < "2026-11-26" and max(fechas) >= "2026-11-23" and min(fechas) >= "2026-09-28"
        # pasa la misma revisión que lo que sube un tubo de verdad
        assert paquete.validar({"esquema": paquete.ESQUEMA, "motor": "x",
                                "archivos": {"activities": acts, "activity_details": detalles}}) == []
        for a in acts:
            assert sum(a[f"hrTimeInZone_{z}"] for z in range(1, 6)) <= a["duration"]
            assert a["activityType"]["typeKey"] != "running" or a["distance"] > 0
    tipos = {a["activityType"]["typeKey"] for a in cuentas_prueba.inventar_historial("crossfit", hoy, "a")[0]}
    assert tipos == {"running", "hiit"}
    assert cuentas_prueba.inventar_historial("empezando", hoy, "a")[1]   # trae tramos de trote y caminata


def test_cada_historial_se_ve_en_su_data_json(web_ctx):
    _, cl = admin_listo(web_ctx)
    web_ctx.app.state.reloj = lambda: HOY
    for nombre in cuentas_prueba.HISTORIALES:
        r = cl.post("/admin/prueba/crear", data={"csrf": csrf_de(cl.get("/admin").text), "nombre": nombre, "historial": nombre})
        u = cuenta_de(web_ctx, f"{nombre}@prueba.test")
        with web_ctx.sesiones() as db:
            filas = db.query(DatoGarmin).filter(DatoGarmin.usuario_id == u.id).count()
            assert (filas == 0) == (nombre == "vacia")
            fila = db.get(Usuario, u.id)
            fila.nombre, fila.apellido = "Ana", "Prueba"
            db.add(Consentimiento(usuario_id=u.id, version_aviso=VERSION_AVISO))
            db.commit()
        suyo = web_ctx.cliente()
        post(suyo, liga_en(r.text))
        assert suyo.get("/").status_code == 200
        assert suyo.get("/data.json").status_code == 200
    r = cl.post("/admin/prueba/crear", data={"csrf": csrf_de(cl.get("/admin").text), "nombre": "z", "historial": "otro"})
    assert r.status_code == 422 and cuenta_de(web_ctx, "z@prueba.test") is None
