"""F7a: descargar mis datos (ZIP de JSON) y borrar mi cuenta (todo, sin dejar filas; solo queda un registro anónimo)."""
import io
import json
import zipfile

import sqlalchemy as sa
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth
from .modelos import (Ajustes, CacheData, Cambio, ClienteOAuth, CodigoOAuth, Coach, Consentimiento, DatoGarmin, InBody,
                      Invitacion, LigaLogin, Plan, Sesion, CuentaBorrada, Subida, TokenOAuth, Usuario, VinculoPendiente)

PALABRA = "BORRAR"


def _fecha(d):
    return d.isoformat(timespec="seconds") if d else None


def datos_de(db: Session, u: Usuario) -> dict[str, object]:
    """Todo lo que pertenece a la persona, y nada de otra (sin hashes ni ids de otras personas)."""
    ajustes, plan = db.get(Ajustes, u.id), db.get(Plan, u.id)
    coaches = db.scalars(select(Coach).where(Coach.atleta_id == u.id).order_by(Coach.creado)).all()
    atletas = db.scalars(select(Coach).where(Coach.coach_id == u.id).order_by(Coach.creado)).all()
    conex = db.execute(select(TokenOAuth, ClienteOAuth.nombre).join(ClienteOAuth, ClienteOAuth.client_id == TokenOAuth.client_id)
                       .where(TokenOAuth.usuario_id == u.id).order_by(TokenOAuth.creado)).all()
    return {
        "cuenta.json": {"correo": u.correo, "apodo": u.apodo, "repo": u.repo, "sensor": u.sensor, "creado": _fecha(u.creado)},
        "ajustes.json": ajustes.config if ajustes else None,
        "plan.json": plan.plan if plan else None,
        "inbody.json": [{"fecha": i.fecha, **i.valores} for i in
                        db.scalars(select(InBody).where(InBody.usuario_id == u.id).order_by(InBody.fecha))],
        "datos_garmin.json": [{"tipo": d.tipo, "clave": d.clave, "contenido": d.contenido} for d in
                              db.scalars(select(DatoGarmin).where(DatoGarmin.usuario_id == u.id).order_by(DatoGarmin.id))],
        "historial_cambios.json": [{"fecha": _fecha(c.fecha), "via": c.via, "hecho_por_ti": c.autor_id == u.id,
                                    "descripcion": c.descripcion, "antes": c.antes, "despues": c.despues}
                                   for c in db.scalars(select(Cambio).where(Cambio.atleta_id == u.id).order_by(Cambio.id))],
        "consentimientos.json": [{"version_aviso": c.version_aviso, "fecha": _fecha(c.fecha)} for c in
                                 db.scalars(select(Consentimiento).where(Consentimiento.usuario_id == u.id))],
        "accesos_coach.json": {"coaches_con_acceso_a_tus_datos": [{"desde": _fecha(c.creado)} for c in coaches],
                               "personas_cuyos_datos_ves_como_coach": [{"desde": _fecha(c.creado)} for c in atletas]},
        "conexiones_ia.json": [{"nombre": n, "creada": _fecha(t.creado), "ultimo_uso": _fecha(t.ultimo_uso)} for t, n in conex],
    }


def zip_de(db: Session, u: Usuario) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nombre, contenido in datos_de(db, u).items():
            z.writestr(nombre, json.dumps(contenido, ensure_ascii=False, indent=2, default=str))
    return buf.getvalue()


def borrar_cuenta(db: Session, u: Usuario) -> None:
    """Borra todas las filas de la persona (Coach en ambos sentidos, OAuth, sesiones, ligas, invitaciones...) y deja
    solo un registro anónimo con la fecha."""
    uid = u.id
    db.execute(sa.update(Cambio).where(Cambio.autor_id == uid).values(autor_id=None))   # lo que hizo en datos de otros queda sin autor
    db.execute(sa.update(Invitacion).where(Invitacion.usada_por == uid).values(usada_por=None))
    db.execute(sa.delete(CodigoOAuth).where(CodigoOAuth.usuario_id == uid))
    db.execute(sa.delete(TokenOAuth).where(TokenOAuth.usuario_id == uid))
    db.execute(sa.delete(Coach).where(sa.or_(Coach.atleta_id == uid, Coach.coach_id == uid)))
    db.execute(sa.delete(Cambio).where(Cambio.atleta_id == uid))
    db.execute(sa.delete(Invitacion).where(Invitacion.creada_por == uid))
    for modelo in (CacheData, LigaLogin, Sesion, Consentimiento, DatoGarmin, Subida, Ajustes, Plan, InBody, VinculoPendiente):
        db.execute(sa.delete(modelo).where(modelo.usuario_id == uid))
    db.delete(u)
    db.add(CuentaBorrada())
    db.commit()


def montar(app, get_db, actual, render, formulario, settings) -> None:
    @app.get("/privacidad/mis-datos")
    def mis_datos(request: Request, usuario=Depends(actual)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        return render(request, "mis_datos.html", atleta=usuario, pref="", palabra=PALABRA)

    @app.get("/privacidad/mis-datos/descargar")
    def descargar(usuario=Depends(actual), db: Session = Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        return Response(zip_de(db, usuario), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="mis-datos-ahi-la-llevas.zip"'})

    @app.post("/privacidad/mis-datos/borrar")
    async def borrar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if str(form.get("confirmar", "")).strip() != PALABRA:
            return render(request, "mis_datos.html", status=400, atleta=usuario, pref="", palabra=PALABRA,
                          error=f"Escribe {PALABRA} (en mayúsculas) para confirmar.")
        borrar_cuenta(db, usuario)
        resp = render(request, "cuenta_borrada.html")
        resp.delete_cookie(auth.COOKIE_SESION, path="/")
        return resp
