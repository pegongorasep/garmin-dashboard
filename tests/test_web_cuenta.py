"""F7a: descargar mis datos y borrar mi cuenta."""
import io
import json
import zipfile

import sqlalchemy as sa

from web.modelos import Base, Cambio, Coach, CuentaBorrada, InBody, Sesion, Usuario
from ayudas import csrf_de, listo


def preparar(ctx):
    """a (con coach b), c ajena; a también es coach de c. Devuelve (a, b, c, cliente de a)."""
    a, cl = listo(ctx, "a@x.com")
    b, _ = listo(ctx, "b@x.com")
    c, _ = listo(ctx, "c@x.com")
    with ctx.sesiones() as db:
        db.add_all([Coach(atleta_id=a, coach_id=b), Coach(atleta_id=c, coach_id=a)])
        db.add(InBody(usuario_id=a, fecha="2026-11-01", valores={"peso": 70.5}))
        db.add(InBody(usuario_id=c, fecha="2026-11-01", valores={"peso": 99.9}))
        db.add(Cambio(atleta_id=a, autor_id=a, via="web", descripcion="cambio de a"))
        db.add(Cambio(atleta_id=c, autor_id=a, via="coach", descripcion="a edito a c"))
        db.add(Cambio(atleta_id=c, autor_id=c, via="web", descripcion="secreto de c"))
        db.commit()
    return a, b, c, cl


def test_descarga_tiene_lo_mio_y_nada_ajeno(web_ctx):
    a, b, c, cl = preparar(web_ctx)
    assert "/privacidad/mis-datos" in cl.get("/privacidad").text
    assert cl.get("/privacidad/mis-datos").status_code == 200
    r = cl.get("/privacidad/mis-datos/descargar")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    z = zipfile.ZipFile(io.BytesIO(r.content))
    nombres = set(z.namelist())
    assert {"cuenta.json", "ajustes.json", "plan.json", "inbody.json", "datos_garmin.json", "historial_cambios.json",
            "consentimientos.json", "accesos_coach.json", "conexiones_ia.json"} <= nombres
    todo = "".join(z.read(n).decode() for n in nombres)
    assert "a@x.com" in todo and "70.5" in todo and "cambio de a" in todo
    assert "b@x.com" not in todo and "c@x.com" not in todo and "99.9" not in todo and "secreto de c" not in todo
    assert "a edito a c" not in todo
    assert len(json.loads(z.read("accesos_coach.json"))["coaches_con_acceso_a_tus_datos"]) == 1


def test_descarga_exige_sesion(web_ctx):
    assert web_ctx.cliente().get("/privacidad/mis-datos/descargar").status_code == 303


def test_borrar_sin_palabra_falla(web_ctx):
    a, b, c, cl = preparar(web_ctx)
    tok = csrf_de(cl.get("/privacidad/mis-datos").text)
    for txt in ("", "borrar", "BORRAR YA"):
        r = cl.post("/privacidad/mis-datos/borrar", data={"csrf": tok, "confirmar": txt})
        assert r.status_code == 400
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, a) is not None


def test_borrar_no_deja_filas_y_cierra_sesion(web_ctx):
    a, b, c, cl = preparar(web_ctx)
    tok = csrf_de(cl.get("/privacidad/mis-datos").text)
    r = cl.post("/privacidad/mis-datos/borrar", data={"csrf": tok, "confirmar": "BORRAR"})
    assert r.status_code == 200 and "bórralo o quita la key" in r.text
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, a) is None
        assert db.scalar(sa.select(sa.func.count()).select_from(CuentaBorrada)) == 1
        assert db.scalar(sa.select(sa.func.count()).select_from(Sesion).where(Sesion.usuario_id == a)) == 0
        for t in Base.metadata.sorted_tables:
            for col in t.c:
                if any(fk.column.table.name == "usuarios" for fk in col.foreign_keys) or col.name == "usuario_id":
                    n = db.scalar(sa.select(sa.func.count()).select_from(t).where(col == a))
                    assert n == 0, (t.name, col.name)
        # lo de los demás sigue: b, c y el cambio propio de c
        assert db.get(Usuario, b) and db.get(Usuario, c)
        assert db.scalar(sa.select(sa.func.count()).select_from(Cambio).where(Cambio.atleta_id == c)) == 2
        assert db.scalar(sa.select(sa.func.count()).select_from(InBody).where(InBody.usuario_id == c)) == 1
    assert cl.get("/data.json").status_code == 401   # la sesión ya no vale
