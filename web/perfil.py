"""G1: perfil de la persona (nombre, apellido, foto opcional).

La foto se recodifica con Pillow (256x256, recorte al centro, WebP): eso borra el EXIF/GPS. Se guarda en la base y solo
la sirve la ruta autenticada `/perfil/foto/{id}` (hoy: la dueña y su coach; G2 la extiende a quienes comparten grupo).
"""
import io

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session

from . import permisos
from .modelos import FotoPerfil, Usuario, ahora

MAX_BYTES = 5 * 1024 * 1024
LADO = 256
FORMATOS = {"JPEG", "PNG", "WEBP"}
MAX_PIXELES = 50_000_000
COLORES = 6   # clases av-0..av-5 (tokens del sistema de diseño)
Image.MAX_IMAGE_PIXELS = MAX_PIXELES


class FotoInvalida(ValueError):
    """`args[0]` es la clave i18n del error."""


def iniciales(u) -> str:
    """Dos letras: nombre + apellido. Sin nombre, la inicial del correo."""
    n, a = (u.nombre or "").strip(), (u.apellido or "").strip()
    if n or a:
        return ((n[:1]) + (a[:1])).upper()
    return (u.correo or "?")[:1].upper()


def color_de(usuario_id: int) -> int:
    """Color estable (0..COLORES-1) derivado del id."""
    return usuario_id % COLORES


def nombre_completo(u) -> str:
    return " ".join(p for p in ((u.nombre or "").strip(), (u.apellido or "").strip()) if p)


def tiene_foto(db: Session, usuario_id: int) -> bool:
    return db.get(FotoPerfil, usuario_id) is not None


def procesar_foto(datos: bytes) -> bytes:
    """Valida y recodifica. Lanza FotoInvalida('perfil.err_...')."""
    if len(datos) > MAX_BYTES:
        raise FotoInvalida("perfil.err_grande")
    try:
        with Image.open(io.BytesIO(datos)) as im:
            if im.format not in FORMATOS:
                raise FotoInvalida("perfil.err_formato")
            im = ImageOps.exif_transpose(im)
            im = ImageOps.fit(im.convert("RGB"), (LADO, LADO), Image.Resampling.LANCZOS)
    except FotoInvalida:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError):
        raise FotoInvalida("perfil.err_formato")
    salida = io.BytesIO()
    im.save(salida, "WEBP", quality=85)   # sin pasar exif=: no se guarda ningún metadato
    return salida.getvalue()


def guardar_foto(db: Session, usuario_id: int, datos: bytes) -> None:
    f = db.get(FotoPerfil, usuario_id)
    if f is None:
        db.add(FotoPerfil(usuario_id=usuario_id, contenido=datos, tipo="image/webp", actualizada=ahora()))
    else:
        f.contenido, f.tipo, f.actualizada = datos, "image/webp", ahora()


def quitar_foto(db: Session, usuario_id: int) -> None:
    f = db.get(FotoPerfil, usuario_id)
    if f is not None:
        db.delete(f)


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def pantalla(request, usuario, db, status=200, error=None, valores=None):
        return render(request, "perfil.html", status=status, atleta=usuario, pref="", error=error,
                      v=valores or {"nombre": usuario.nombre or "", "apellido": usuario.apellido or ""},
                      foto=tiene_foto(db, usuario.id), primera_vez=not (usuario.nombre and usuario.apellido))

    @app.get("/perfil")
    def perfil_get(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        return pantalla(request, usuario, db)

    @app.post("/perfil")
    async def perfil_post(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        nombre, apellido = str(form.get("nombre", "")).strip()[:60], str(form.get("apellido", "")).strip()[:60]
        valores = {"nombre": nombre, "apellido": apellido}
        t = request.state.t
        if not nombre or not apellido:
            return pantalla(request, usuario, db, 400, t("perfil.err_nombre"), valores)
        archivo = form.get("foto")
        nueva = None
        if archivo is not None and getattr(archivo, "filename", ""):
            crudo = await archivo.read(MAX_BYTES + 1)
            if crudo:
                try:
                    nueva = procesar_foto(crudo)
                except FotoInvalida as e:
                    return pantalla(request, usuario, db, 400, t(e.args[0]), valores)
        era_primera = not (usuario.nombre and usuario.apellido)
        usuario.nombre, usuario.apellido = nombre, apellido
        if nueva is not None:
            guardar_foto(db, usuario.id, nueva)
        elif form.get("quitar_foto") == "on":
            quitar_foto(db, usuario.id)
        db.commit()
        return RedirectResponse("/" if era_primera else "/perfil?ok=1", 303)

    @app.get("/perfil/foto/{usuario_id}")
    def foto(usuario_id: int, usuario=Depends(actual), db: Session = Depends(get_db)):
        # G1: solo la dueña y su coach (permisos.puede_ver). G2 agrega a quienes comparten grupo.
        if not permisos.puede_ver(db, usuario, usuario_id):
            return Response(status_code=404)
        f = db.get(FotoPerfil, usuario_id)
        if f is None:
            return Response(status_code=404)
        return Response(f.contenido, media_type=f.tipo, headers={"Cache-Control": "private, no-store"})
