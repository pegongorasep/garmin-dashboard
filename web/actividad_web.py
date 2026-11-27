"""Formulario de actividad a mano (parte 2, E5): /actividad/nueva, /actividad/{id} y /actividad/{id}/borrar.
También bajo `/a/<id>` para el coach. `ajustes_web.resolver` decide con `puede_editar` (404 si no hay acceso);
una actividad que no es de la persona también da 404. Todo POST lleva CSRF (`formulario`)."""
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import manual
from .ajustes_web import crudo_de, hoy_de, prefijo, resolver
from .modelos import ActividadManual, ahora

PRINCIPALES = ("correr", "caminar", "crossfit", "gimnasio")
OTROS = tuple(k for k in manual.TIPOS if k not in PRINCIPALES)


def _tipos():
    return {k: v["unidad"] for k, v in manual.TIPOS.items()}


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def pantalla(request, db, usuario, atleta, valores, errores=None, fila=None, status=200):
        tipo = valores.get("tipo") or "correr"
        grupo = tipo if tipo in PRINCIPALES else "otra"
        return render(request, "actividad_form.html", status=status, atleta=atleta, pref=prefijo(usuario, atleta),
                      v=valores, errores=errores or {}, fila=fila, grupo=grupo, otro=tipo if tipo in OTROS else "otra",
                      principales=PRINCIPALES, otros=OTROS, unidades=_tipos(),
                      ritmo=manual.ritmo(fila) if fila else None,
                      unidad_ritmo=manual.unidad_ritmo(fila.tipo) if fila else "km")

    def propia(db, atleta, actividad_id):
        fila = db.get(ActividadManual, actividad_id)
        if fila is None or fila.usuario_id != atleta.id:
            raise HTTPException(404)
        return fila

    def ver(request, usuario, db, atleta_id, actividad_id=None):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        if actividad_id is not None:
            fila = propia(db, atleta, actividad_id)
            return pantalla(request, db, usuario, atleta, manual.valores_de(fila), fila=fila)
        hoy = hoy_de(request.app.state.reloj, crudo_de(db, atleta))
        q = request.query_params
        tipo = q.get("tipo") if q.get("tipo") in manual.TIPOS else "correr"
        fecha = q.get("fecha") or hoy.isoformat()
        return pantalla(request, db, usuario, atleta, {"tipo": tipo, "fecha": fecha})

    async def guardar(request, usuario, db, atleta_id, actividad_id=None):
        form = await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        fila = propia(db, atleta, actividad_id) if actividad_id is not None else None
        campos = dict(form.items())
        if campos.get("tipo") == "otra":   # «Otra» abre la lista con los demás tipos
            campos["tipo"] = campos.get("otro") or "otra"
        hoy = hoy_de(request.app.state.reloj, crudo_de(db, atleta))
        datos, errores = manual.validar(campos, hoy)
        if errores:
            return pantalla(request, db, usuario, atleta, campos, errores, fila, status=400)
        if fila is None:
            fila = ActividadManual(usuario_id=atleta.id, **datos)
            db.add(fila)
        else:
            for k, v in datos.items():
                setattr(fila, k, v)
            fila.actualizada = ahora()
        db.commit()
        return RedirectResponse(f"{prefijo(usuario, atleta)}/#hoy", 303)

    async def borrar(request, usuario, db, atleta_id, actividad_id):
        await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        db.delete(propia(db, atleta, actividad_id))
        db.commit()
        return RedirectResponse(f"{prefijo(usuario, atleta)}/#hoy", 303)

    for base in ("", "/a/{atleta_id}"):
        def rutas(base=base):
            @app.get(f"{base}/actividad/nueva")
            def _nueva(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return ver(request, usuario, db, atleta_id)

            @app.post(f"{base}/actividad/nueva")
            async def _nueva_post(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await guardar(request, usuario, db, atleta_id)

            @app.get(base + "/actividad/{actividad_id}")
            def _editar(request: Request, actividad_id: int, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return ver(request, usuario, db, atleta_id, actividad_id)

            @app.post(base + "/actividad/{actividad_id}")
            async def _editar_post(request: Request, actividad_id: int, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await guardar(request, usuario, db, atleta_id, actividad_id)

            @app.post(base + "/actividad/{actividad_id}/borrar")
            async def _borrar(request: Request, actividad_id: int, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await borrar(request, usuario, db, atleta_id, actividad_id)
        rutas()
