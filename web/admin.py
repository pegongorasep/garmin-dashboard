"""F7b: panel de admin (/admin). Solo el admin; a los demás un 404. No muestra datos de entrenamiento de nadie."""
from datetime import timedelta

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, permisos
from .modelos import Invitacion, Subida, Usuario, ahora

DIAS_ATRASADO = 2


def es_admin(usuario: Usuario | None, settings) -> bool:
    if usuario is None or usuario.borrado is not None:
        return False
    return bool(usuario.es_admin) or bool(settings.admin_correo and
                                          auth.normalizar_correo(usuario.correo) == auth.normalizar_correo(settings.admin_correo))


def usuarios_de(db: Session, admin: Usuario) -> list[dict]:
    """Solo las columnas del panel: correo, apodo, repo, última subida, versión del motor, atrasado."""
    subidas = db.scalars(select(Subida).where(Subida.ok.is_(True)).order_by(Subida.fecha.desc(), Subida.id.desc())).all()
    ultima: dict[int, Subida] = {}
    for s in subidas:
        ultima.setdefault(s.usuario_id, s)
    actual = subidas[0].motor if subidas else None   # la versión "vigente" es la de la subida más reciente de todos
    limite = ahora() - timedelta(days=DIAS_ATRASADO)
    filas = []
    for u in db.scalars(select(Usuario).where(Usuario.borrado.is_(None)).order_by(Usuario.id)):
        s = ultima.get(u.id)
        atrasado = s is not None and (s.fecha < limite or (actual is not None and s.motor != actual))
        filas.append({"id": u.id, "correo": u.correo, "apodo": u.apodo, "repo": u.repo,
                      "ultima_subida": s.fecha.strftime("%Y-%m-%d %H:%M") if s else None,
                      "motor": s.motor if s else None, "atrasado": atrasado,
                      "liga": f"/a/{u.id}/ajustes" if permisos.puede_ver(db, admin, u.id) and u.id != admin.id else None})
    return filas


def invitaciones_de(db: Session) -> list[dict]:
    """Pendientes (sin usar y vigentes) y el total de usadas; el token en claro no se guarda, solo se ve al crearla."""
    pend = db.scalars(select(Invitacion).where(Invitacion.usada_en.is_(None), Invitacion.expira > ahora())
                      .order_by(Invitacion.creada.desc())).all()
    return [{"id": i.token_hash, "nota": i.nota, "creada": i.creada.strftime("%Y-%m-%d"),
             "expira": i.expira.strftime("%Y-%m-%d")} for i in pend]


def revocar_invitacion(db: Session, token_hash: str) -> bool:
    inv = db.get(Invitacion, token_hash)
    if inv is None or inv.usada_en is not None:
        return False
    db.delete(inv)
    db.commit()
    return True


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def admin_de(usuario) -> Usuario:
        if not es_admin(usuario, settings):
            raise HTTPException(404)
        return usuario

    def pagina(request, db, admin, **extra):
        return render(request, "admin.html", atleta=admin, pref="", invitaciones=invitaciones_de(db),
                      usuarios=usuarios_de(db, admin), dias=DIAS_ATRASADO, **extra)

    @app.get("/admin")
    def panel(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        return pagina(request, db, admin_de(usuario))

    @app.post("/admin/invitar")
    async def invitar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        form = await formulario(request)
        admin = admin_de(usuario)
        nota = str(form.get("nota", "")).strip()[:200] or None
        token = auth.crear_invitacion(db, admin.id, nota)
        # sin redirigir: el token en claro solo existe en esta respuesta
        return pagina(request, db, admin, liga_nueva=f"{settings.base_url}/invitacion/{token}")

    @app.post("/admin/revocar")
    async def revocar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        form = await formulario(request)
        admin = admin_de(usuario)
        ok = revocar_invitacion(db, str(form.get("id", "")))
        return pagina(request, db, admin, mensaje="Invitación revocada." if ok else "Esa invitación ya no está pendiente.")
