"""/coach: el atleta da y quita acceso a su coach. Quitar corta de inmediato (puede_ver se revisa en cada petición)."""
from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from . import auth, calculo
from .modelos import Coach, Usuario

NEUTRO = "Si esa persona tiene cuenta, ya tiene acceso."


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def coaches_de(db, usuario):
        filas = db.execute(select(Coach, Usuario).join(Usuario, Usuario.id == Coach.coach_id)
                           .where(Coach.atleta_id == usuario.id, Usuario.borrado.is_(None)).order_by(Coach.creado)).all()
        return [{"id": c.id, "nombre": u.apodo or u.correo} for c, u in filas]

    def atletas_de(db, usuario):
        filas = db.execute(select(Coach, Usuario).join(Usuario, Usuario.id == Coach.atleta_id)
                           .where(Coach.coach_id == usuario.id, Usuario.borrado.is_(None)).order_by(Coach.creado)).all()
        out = []
        for _, a in filas:
            fila = {"id": a.id, "nombre": a.apodo or a.correo, "datos_al": None, "semana": None, "semaforo": None}
            try:
                d = calculo.calcular(db, a)
                fila.update(datos_al=(d.get("datos_al") or "")[:10] or None, semana=(d.get("plan") or {}).get("semana_actual"),
                            semaforo=(d.get("hoy") or {}).get("semaforo"))
            except Exception:   # sin ajustes todavía o datos inválidos: se lista igual, sin cifras
                pass
            out.append(fila)
        return out

    def pagina(request, usuario, db, status=200, **extra):
        return render(request, "coach.html", status=status, atleta=usuario, pref="", coaches=coaches_de(db, usuario), atletas=atletas_de(db, usuario),
                      ok=request.query_params.get("ok"), error=None, **extra)

    @app.get("/coach")
    def coach_ver(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        return pagina(request, usuario, db)

    @app.post("/coach/dar")
    async def coach_dar(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        correo = str(form.get("correo", ""))
        if not auth.correo_valido(correo):
            return pagina(request, usuario, db, status=400, error=request.state.t("err.correo"))
        otro = auth.buscar_por_correo(db, correo)
        if otro is not None and otro.id != usuario.id and db.scalar(
                select(Coach.id).where(Coach.atleta_id == usuario.id, Coach.coach_id == otro.id)) is None:
            db.add(Coach(atleta_id=usuario.id, coach_id=otro.id))
            db.commit()
        return RedirectResponse("/coach?ok=1", 303)   # mismo mensaje exista o no la cuenta (o seas tú)

    @app.post("/coach/quitar/{coach_id}")
    async def coach_quitar(request: Request, coach_id: int, usuario=Depends(actual), db=Depends(get_db)):
        await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        fila = db.get(Coach, coach_id)
        if fila is not None and fila.atleta_id == usuario.id:
            db.delete(fila)
            db.commit()
        return RedirectResponse("/coach?ok=quitado", 303)
