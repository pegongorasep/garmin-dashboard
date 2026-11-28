"""Cuentas de prueba (`algo@prueba.test`) desde /admin: crear, entrar con una liga y borrar. Solo el admin, y solo sobre
cuentas `.test`: ninguna de estas rutas toca la cuenta de una persona real (a lo demás, 404)."""
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import admin, auth, cuenta
from .deps import actual, formulario, get_db, settings as get_settings
from .modelos import Usuario

DOMINIO = "prueba.test"
RE_NOMBRE = re.compile(r"[a-z0-9][a-z0-9._-]{0,29}")

router = APIRouter()


def de_prueba(db: Session, ident, settings) -> Usuario:
    """La cuenta de prueba con ese id; 404 si no existe, no es `.test` o es de un admin."""
    ident = str(ident or "")
    u = db.get(Usuario, int(ident)) if re.fullmatch(r"[0-9]{1,9}", ident) else None
    if u is None or u.borrado is not None or not auth.es_correo_prueba(u.correo) or admin.es_admin(u, settings):
        raise HTTPException(404)
    return u


def _con_liga(request, db, quien_admin, u: Usuario, settings, **extra):
    # sin redirigir: el token en claro solo existe en esta respuesta
    token = auth.crear_liga(db, u, limitar=False)
    return admin.pagina(request, db, quien_admin, prueba_liga=f"{settings.base_url}/entrar/liga/{token}",
                        prueba_para=u.correo, **extra)


@router.post("/admin/prueba/crear")
async def crear(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    nombre = str(form.get("nombre", "")).strip().lower()
    if not RE_NOMBRE.fullmatch(nombre):
        return admin.pagina(request, db, quien, prueba_error=request.state.t("admin.prueba_nombre_malo"))
    correo = f"{nombre}@{DOMINIO}"
    if db.scalar(select(Usuario.id).where(Usuario.correo == correo)) is not None:
        return admin.pagina(request, db, quien, prueba_error=request.state.t("admin.prueba_ya_existe", correo=correo))
    u = Usuario(correo=correo)
    db.add(u)
    db.commit()
    return _con_liga(request, db, quien, u, settings)


@router.post("/admin/prueba/liga")
async def liga(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    return _con_liga(request, db, quien, de_prueba(db, form.get("id"), settings), settings)


@router.post("/admin/prueba/borrar")
async def borrar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    u = de_prueba(db, form.get("id"), settings)
    correo = u.correo
    cuenta.borrar_cuenta(db, u)
    return admin.pagina(request, db, quien, mensaje=request.state.t("admin.prueba_borrada", correo=correo))
