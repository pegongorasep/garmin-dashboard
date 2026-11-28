"""G2: grupos de amigos (crear, unirse con liga, salir, quitar, pausar lo que comparto).

Solo miembros ven un grupo (a los demás, 404). La liga de invitación se guarda como hash y vale hasta que expira.
Aquí NO se muestran datos de entrenamiento: G3 agrega las tarjetas de avance, que respetan `MiembroGrupo.pausado`.
"""
from datetime import timedelta

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth, grupos_resumen, permisos
from .deps import actual, formulario, get_db, render, settings as get_settings
from .modelos import Grupo, InvitacionGrupo, MiembroGrupo, Comentario, ReaccionActividad, Usuario, ahora

MAX_MIEMBROS = 12
MAX_GRUPOS = 5          # por persona (los que crea o a los que se une)
DIAS_LIGA = 7


def nombre_de(u: Usuario) -> str:
    return ((u.nombre or "") + " " + (u.apellido or "")).strip() or u.correo


def miembros_de(db: Session, grupo_id: int) -> list[tuple[MiembroGrupo, Usuario]]:
    filas = db.execute(select(MiembroGrupo, Usuario).join(Usuario, Usuario.id == MiembroGrupo.usuario_id)
                       .where(MiembroGrupo.grupo_id == grupo_id, Usuario.borrado.is_(None))
                       .order_by(MiembroGrupo.unido, MiembroGrupo.id)).all()
    return [(m, u) for m, u in filas]


def grupos_de(db: Session, usuario_id: int) -> list[Grupo]:
    return list(db.scalars(select(Grupo).join(MiembroGrupo, MiembroGrupo.grupo_id == Grupo.id)
                           .where(MiembroGrupo.usuario_id == usuario_id).order_by(Grupo.creado, Grupo.id)))


def _borrar_grupo(db: Session, grupo_id: int) -> None:
    db.execute(sa.delete(InvitacionGrupo).where(InvitacionGrupo.grupo_id == grupo_id))
    db.execute(sa.delete(MiembroGrupo).where(MiembroGrupo.grupo_id == grupo_id))
    db.execute(sa.delete(Grupo).where(Grupo.id == grupo_id))


def _salir(db: Session, grupo_id: int, usuario_id: int) -> None:
    """Quita a la persona; si era la única se borra el grupo; si era la admin, la más antigua pasa a admin."""
    db.execute(sa.delete(MiembroGrupo).where(MiembroGrupo.grupo_id == grupo_id, MiembroGrupo.usuario_id == usuario_id))
    db.flush()
    resto = db.scalars(select(MiembroGrupo).where(MiembroGrupo.grupo_id == grupo_id)
                       .order_by(MiembroGrupo.unido, MiembroGrupo.id)).all()
    if not resto:
        _borrar_grupo(db, grupo_id)
        return
    if not any(m.rol == "admin" for m in resto):
        resto[0].rol = "admin"
    db.execute(sa.update(InvitacionGrupo).where(InvitacionGrupo.creada_por == usuario_id).values(creada_por=None))
    db.execute(sa.update(Grupo).where(Grupo.id == grupo_id, Grupo.creado_por == usuario_id).values(creado_por=None))


def quitar_de_todos(db: Session, usuario_id: int) -> None:
    """Para borrar la cuenta: sale de todos sus grupos y no deja referencias."""
    for gid in db.scalars(select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == usuario_id)).all():
        _salir(db, gid, usuario_id)
    db.execute(sa.delete(ReaccionActividad).where(sa.or_(ReaccionActividad.de_id == usuario_id, ReaccionActividad.dueno_id == usuario_id)))
    db.execute(sa.delete(Comentario).where(sa.or_(Comentario.autor_id == usuario_id, Comentario.dueno_id == usuario_id)))
    db.execute(sa.update(InvitacionGrupo).where(InvitacionGrupo.creada_por == usuario_id).values(creada_por=None))
    db.execute(sa.update(Grupo).where(Grupo.creado_por == usuario_id).values(creado_por=None))


def nueva_liga(db: Session, grupo_id: int, por: int) -> str:
    token = auth.nuevo_token()
    db.add(InvitacionGrupo(token_hash=auth.hash_token(token), grupo_id=grupo_id, creada_por=por,
                           expira=ahora() + timedelta(days=DIAS_LIGA)))
    return token


def liga_vigente(db: Session, token: str) -> InvitacionGrupo | None:
    inv = db.get(InvitacionGrupo, auth.hash_token(token))
    return inv if inv is not None and inv.expira > ahora() else None

router = APIRouter()


def pagina(request, usuario, db, grupo, settings, status=200, liga=None, error=None):
    miembros = miembros_de(db, grupo.id)
    yo = next((m for m, u in miembros if u.id == usuario.id), None)
    res = grupos_resumen.resumen(db, miembros)
    fotos = {u.id for _, u in miembros if perfil_tiene_foto(db, u.id)}
    return render(request, "grupo.html", status=status, atleta=usuario, pref="", grupo=grupo, miembros=miembros,
                  yo=yo, fotos=fotos, por_id={u.id: u for _, u in miembros}, tarjetas=res["tarjetas"], total=res["total"], insignias=res["insignias"], novedades=res["novedades"], liga=(f"{settings.base_url.rstrip('/')}/grupos/unirse/{liga}" if liga else None),
                  error=error, lleno=len(miembros) >= MAX_MIEMBROS)

def propio(request, usuario, db, gid):
    """(grupo, mi membresía) o None si no soy miembro (404 igual que si no existe)."""
    m = db.scalar(select(MiembroGrupo).where(MiembroGrupo.grupo_id == gid, MiembroGrupo.usuario_id == usuario.id))
    return (db.get(Grupo, gid), m) if m is not None else None

def sin_sesion():
    return RedirectResponse("/entrar", 303)


@router.get("/grupos")
def lista(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    if usuario is None:
        return sin_sesion()
    gs = grupos_de(db, usuario.id)
    cuantos = {g.id: len(miembros_de(db, g.id)) for g in gs}
    return render(request, "grupos.html", atleta=usuario, pref="", grupos=gs, cuantos=cuantos)


@router.get("/api/grupos")
def api_lista(usuario=Depends(actual), db: Session = Depends(get_db)):
    if usuario is None:
        return JSONResponse({"error": "Entra primero."}, status_code=401)
    return [{"id": g.id, "nombre": g.nombre, "miembros_n": len(miembros_de(db, g.id))} for g in grupos_de(db, usuario.id)]


@router.get("/api/grupos/{gid}")
def api_grupo(gid: int, usuario=Depends(actual), db: Session = Depends(get_db)):
    if usuario is None:
        return JSONResponse({"error": "Entra primero."}, status_code=401)
    if propio(None, usuario, db, gid) is None:
        return JSONResponse({"error": "No encontrado."}, status_code=404)
    miembros = miembros_de(db, gid)
    res = grupos_resumen.resumen(db, miembros)
    nombres = {u.id: nombre_de(u) for _, u in miembros}
    return {"grupo": {"id": gid, "nombre": db.get(Grupo, gid).nombre}, "yo": usuario.id,
            "miembros": [{"usuario_id": u.id, "nombre": nombres[u.id],
                          "foto": f"/perfil/foto/{u.id}" if perfil_tiene_foto(db, u.id) else None,
                          "tarjeta": res["tarjetas"][u.id]}
                         for m, u in miembros],
            "total": res["total"], "insignias": res["insignias"], "novedades": res["novedades"],
            "emoji_cat": grupos_resumen.EMOJI_CATEGORIA, "admin_url": f"/grupos/{gid}"}


@router.get("/grupos/nuevo")
def nuevo_get(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    if usuario is None:
        return sin_sesion()
    return render(request, "grupo_nuevo.html", atleta=usuario, pref="", error=None, valor="")


@router.post("/grupos/nuevo")
async def nuevo_post(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    form = await formulario(request)
    if usuario is None:
        return sin_sesion()
    nombre = str(form.get("nombre", "")).strip()[:60]
    t = request.state.t
    if not nombre:
        return render(request, "grupo_nuevo.html", status=400, atleta=usuario, pref="", error=t("grupos.err_nombre"), valor="")
    if len(grupos_de(db, usuario.id)) >= MAX_GRUPOS:
        return render(request, "grupo_nuevo.html", status=400, atleta=usuario, pref="",
                      error=t("grupos.err_muchos", n=MAX_GRUPOS), valor=nombre)
    g = Grupo(nombre=nombre, creado_por=usuario.id)
    db.add(g)
    db.flush()
    db.add(MiembroGrupo(grupo_id=g.id, usuario_id=usuario.id, rol="admin"))
    db.commit()
    return RedirectResponse(f"/grupos/{g.id}", 303)


@router.get("/grupos/unirse/{token}")
def unirse_get(token: str, request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    if usuario is None:
        return render(request, "grupo_unirse.html", status=401, atleta=None, pref="", estado="sin_sesion", grupo=None, token=token)
    inv = liga_vigente(db, token)
    if inv is None:
        return render(request, "grupo_unirse.html", status=404, atleta=usuario, pref="", estado="invalida", grupo=None, token=token)
    grupo = db.get(Grupo, inv.grupo_id)
    if permisos.es_miembro(db, usuario, grupo.id):
        return RedirectResponse(f"/grupos/{grupo.id}", 303)
    estado = "ok"
    return render(request, "grupo_unirse.html", atleta=usuario, pref="", estado=estado, grupo=grupo, token=token)


@router.post("/grupos/unirse/{token}")
async def unirse_post(token: str, request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    await formulario(request)
    if usuario is None:
        return sin_sesion()
    inv = liga_vigente(db, token)
    if inv is None:
        return render(request, "grupo_unirse.html", status=404, atleta=usuario, pref="", estado="invalida", grupo=None, token=token)
    grupo = db.get(Grupo, inv.grupo_id)
    if permisos.es_miembro(db, usuario, grupo.id):
        return RedirectResponse(f"/grupos/{grupo.id}", 303)

    def rechazo(estado):
        return render(request, "grupo_unirse.html", status=403, atleta=usuario, pref="", estado=estado, grupo=grupo, token=token)
    if not (usuario.nombre and usuario.apellido):
        return RedirectResponse("/perfil", 303)
    if len(miembros_de(db, grupo.id)) >= MAX_MIEMBROS:
        return rechazo("lleno")
    if len(grupos_de(db, usuario.id)) >= MAX_GRUPOS:
        return rechazo("muchos")
    db.add(MiembroGrupo(grupo_id=grupo.id, usuario_id=usuario.id))
    db.commit()
    return RedirectResponse(f"/grupos/{grupo.id}", 303)


@router.get("/grupos/{gid}")
def ver(gid: int, request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    if usuario is None:
        return sin_sesion()
    p = propio(request, usuario, db, gid)
    if p is None:
        return Response(status_code=404)
    return pagina(request, usuario, db, p[0], settings)


@router.post("/grupos/{gid}/invitar")
async def invitar(gid: int, request: Request, usuario=Depends(actual), db: Session = Depends(get_db),
                  settings=Depends(get_settings)):
    await formulario(request)
    if usuario is None:
        return sin_sesion()
    p = propio(request, usuario, db, gid)
    if p is None:
        return Response(status_code=404)
    token = nueva_liga(db, gid, usuario.id)
    db.commit()
    return pagina(request, usuario, db, p[0], settings, liga=token)


@router.post("/grupos/{gid}/pausar")
async def pausar(gid: int, request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    form = await formulario(request)
    if usuario is None:
        return sin_sesion()
    p = propio(request, usuario, db, gid)
    if p is None:
        return Response(status_code=404)
    p[1].pausado = form.get("pausado") == "1"
    db.commit()
    return RedirectResponse(f"/grupos/{gid}", 303)


@router.post("/grupos/{gid}/salir")
async def salir(gid: int, request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    await formulario(request)
    if usuario is None:
        return sin_sesion()
    if propio(request, usuario, db, gid) is None:
        return Response(status_code=404)
    _salir(db, gid, usuario.id)
    db.commit()
    return RedirectResponse("/grupos", 303)


@router.post("/grupos/{gid}/quitar/{uid}")
async def quitar(gid: int, uid: int, request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
    await formulario(request)
    if usuario is None:
        return sin_sesion()
    p = propio(request, usuario, db, gid)
    if p is None:
        return Response(status_code=404)
    if p[1].rol != "admin":
        return Response(status_code=403)
    if uid == usuario.id or not db.scalar(select(MiembroGrupo.id).where(MiembroGrupo.grupo_id == gid, MiembroGrupo.usuario_id == uid)):
        return Response(status_code=404)
    _salir(db, gid, uid)
    db.commit()
    return RedirectResponse(f"/grupos/{gid}", 303)


def perfil_tiene_foto(db: Session, uid: int) -> bool:
    from .perfil import tiene_foto
    return tiene_foto(db, uid)
