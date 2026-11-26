"""G1: nombre, apellido y foto de perfil."""
import io
import zipfile

from PIL import Image

from test_web_cuentas import csrf_de, entrar, crear_usuario
from web import perfil
from web.modelos import Coach, FotoPerfil, Usuario


def con_exif_gps(color=(200, 30, 30), tam=(640, 480), formato="JPEG") -> bytes:
    im = Image.new("RGB", tam, color)
    exif = Image.Exif()
    exif[0x010F] = "CamaraSecreta"   # Make
    exif[0x8825] = {1: "N", 2: (20.0, 58.0, 0.0), 3: "W", 4: (89.0, 37.0, 0.0)}   # GPS
    b = io.BytesIO()
    im.save(b, formato, exif=exif.tobytes()) if formato == "JPEG" else im.save(b, formato)
    return b.getvalue()


def usuario_sin_nombre(ctx, correo="n@x.com"):
    uid = crear_usuario(ctx, correo)
    with ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        u.nombre = u.apellido = None
        db.commit()
    return uid, entrar(ctx, ctx.cliente(), correo)


def enviar(cl, nombre="Luis", apellido="Pérez", foto=None, **extra):
    tk = csrf_de(cl.get("/perfil").text)
    archivos = {"foto": ("f.jpg", foto, "image/jpeg")} if foto is not None else None
    return cl.post("/perfil", data={"csrf": tk, "nombre": nombre, "apellido": apellido, **extra}, files=archivos)


def test_cuenta_existente_va_a_perfil_una_sola_vez(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    assert cl.get("/").headers["location"] == "/perfil"
    assert cl.get("/bienvenida").headers["location"] == "/perfil"
    r = enviar(cl)
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert cl.get("/").headers.get("location") != "/perfil"
    assert cl.get("/bienvenida").headers.get("location") != "/perfil"
    with web_ctx.sesiones() as db:
        u = db.get(Usuario, uid)
        assert (u.nombre, u.apellido) == ("Luis", "Pérez")


def test_nombre_y_apellido_son_obligatorios(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    assert enviar(cl, apellido="  ").status_code == 400
    with web_ctx.sesiones() as db:
        assert db.get(Usuario, uid).nombre is None


def test_la_foto_se_recodifica_sin_exif(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    original = con_exif_gps()
    assert b"CamaraSecreta" in original and b"Exif" in original
    assert enviar(cl, foto=original).status_code == 303
    with web_ctx.sesiones() as db:
        datos = db.get(FotoPerfil, uid).contenido
    assert b"CamaraSecreta" not in datos and b"Exif" not in datos and b"EXIF" not in datos
    im = Image.open(io.BytesIO(datos))
    assert im.size == (256, 256) and im.format == "WEBP" and not im.getexif()
    r = cl.get(f"/perfil/foto/{uid}")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp" and r.content == datos


def test_mas_de_5_mb_se_rechaza(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    r = enviar(cl, foto=b"\xff\xd8" + b"0" * (perfil.MAX_BYTES + 10))
    assert r.status_code == 400 and "5 MB" in r.text
    with web_ctx.sesiones() as db:
        assert db.get(FotoPerfil, uid) is None and db.get(Usuario, uid).nombre is None


def test_un_archivo_que_no_es_imagen_se_rechaza(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    assert enviar(cl, foto=b"<?php echo 1; ?>").status_code == 400
    assert enviar(cl, foto=con_exif_gps(formato="GIF") if False else b"GIF89a" + b"0" * 50).status_code == 400
    buf = io.BytesIO(); Image.new("RGB", (8, 8)).save(buf, "BMP")
    assert enviar(cl, foto=buf.getvalue()).status_code == 400   # imagen válida pero de formato no permitido
    with web_ctx.sesiones() as db:
        assert db.get(FotoPerfil, uid) is None


def test_quien_no_es_de_la_persona_recibe_404_en_la_foto(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    enviar(cl, foto=con_exif_gps())
    otro = crear_usuario(web_ctx, "o@x.com")
    cl_otro = entrar(web_ctx, web_ctx.cliente(), "o@x.com")
    assert cl_otro.get(f"/perfil/foto/{uid}").status_code == 404
    assert web_ctx.cliente().get(f"/perfil/foto/{uid}").status_code == 404   # sin sesión
    with web_ctx.sesiones() as db:
        db.add(Coach(atleta_id=uid, coach_id=otro))
        db.commit()
    assert cl_otro.get(f"/perfil/foto/{uid}").status_code == 200   # su coach sí
    assert cl_otro.get(f"/perfil/foto/{otro}").status_code == 404   # sin foto


def test_quitar_foto_y_cobertura_de_zip_y_borrado(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    enviar(cl, foto=con_exif_gps())
    z = zipfile.ZipFile(io.BytesIO(cl.get("/privacidad/mis-datos/descargar").content))
    assert "foto_perfil.webp" in z.namelist() and '"Luis"' in z.read("cuenta.json").decode()
    enviar(cl, quitar_foto="on")
    assert cl.get(f"/perfil/foto/{uid}").status_code == 404
    enviar(cl, foto=con_exif_gps())
    from web import cuenta
    with web_ctx.sesiones() as db:
        cuenta.borrar_cuenta(db, db.get(Usuario, uid))
        assert db.get(FotoPerfil, uid) is None


def test_iniciales_y_color_estable():
    u = Usuario(id=7, correo="x@x.com", nombre="ana", apellido="López")
    assert perfil.iniciales(u) == "AL"
    assert perfil.iniciales(Usuario(id=1, correo="zeta@x.com")) == "Z"
    assert perfil.color_de(7) == perfil.color_de(7) == 1 and perfil.color_de(13) == 1
    assert {perfil.color_de(i) for i in range(1, 20)} == set(range(perfil.COLORES))


def test_el_avatar_sin_foto_muestra_iniciales_y_clase_de_color(web_ctx):
    uid, cl = usuario_sin_nombre(web_ctx)
    enviar(cl, nombre="Marta", apellido="Ruiz")
    html = cl.get("/perfil").text
    assert f'avatar av-{uid % 6} g' in html and ">MR<" in html
    enviar(cl, foto=con_exif_gps())
    assert f'src="/perfil/foto/{uid}"' in cl.get("/perfil").text
