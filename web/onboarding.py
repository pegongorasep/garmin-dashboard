"""Guía de Garmin (/bienvenida): usuario de GitHub -> copia, key y Actions -> espera de datos -> el plan (asistente
`/plan/nuevo`). El aviso y el nombre se piden en /perfil (E1). El avance sale de la base (se puede salir y volver)."""
import hmac
import re
from datetime import date, timedelta

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session


from . import importar, tubo
from .modelos import Ajustes, Cambio, Consentimiento, Usuario
from .privacidad import VERSION_AVISO

PASOS = ["GitHub", "Tu copia", "Tu key", "Actívalo", "Tus datos", "Tu plan"]
RE_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
KEY_GARMIN_URL = "https://connect.garmin.com/app/settings/personalApiToken"
ZONAS = ["America/Merida", "America/Mexico_City", "America/Monterrey", "America/Cancun", "America/Tijuana",
         "America/Bogota", "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires", "Europe/Madrid", "UTC"]
DIAS = [("lun", "Lunes"), ("mar", "Martes"), ("mié", "Miércoles"), ("jue", "Jueves"), ("vie", "Viernes"),
        ("sáb", "Sábado"), ("dom", "Domingo")]


ERRORES_CONEXION = ("estado", "cancelado", "instalacion", "repos", "otra_copia", "ajena", "publica", "github")


def _error_conexion(request):
    c = request.query_params.get("error", "")
    return request.state.t(f"conexion.err_{c}") if c in ERRORES_CONEXION else None


def tiene_aviso(db: Session, u: Usuario) -> bool:
    """Aceptó la versión vigente del aviso de privacidad."""
    return db.scalar(select(Consentimiento.id).where(
        Consentimiento.usuario_id == u.id, Consentimiento.version_aviso == VERSION_AVISO).limit(1)) is not None


def estado(db: Session, u: Usuario) -> dict:
    return {"consentimiento": tiene_aviso(db, u),
            "owner": bool(u.github_owner), "vinculado": bool(u.repo_id),
            "datos": tubo.tuvo_subida_ok(db, u.id), "ajustes": db.get(Ajustes, u.id) is not None,
            "pendiente": tubo.pendiente_vigente(db, u.id) is not None, "uso": u.uso or "completo",
            "uso_elegido": u.uso is not None, "sin_plan": bool(u.sin_plan)}


def completo(db: Session, u: Usuario) -> bool:
    """Nombre + apellido + aviso vigente. Nada más: Garmin, plan y datos se piden después, desde la app."""
    return bool(u.nombre and u.apellido and tiene_aviso(db, u))


def paso_maximo(e: dict) -> int:
    """Último paso de la guía vieja (2 a 7) al que se puede entrar. El 7 es el asistente del plan."""
    if not e["owner"]:
        return 2
    return 7 if (e["datos"] and not e["sin_plan"] and not e["ajustes"]) else 6


def paso_inicial(e: dict) -> int:
    if not e["owner"]:
        return 2
    if e["datos"] and not e["sin_plan"] and not e["ajustes"]:
        return 7
    return 6 if (e["vinculado"] or e["pendiente"]) else 3


GUIA_MAX = 4   # pantallas de la guía nueva: 0 Antes de empezar, 1 Cuenta, 2 Tu copia, 3 Permiso, 4 Tu key
COOKIE_GUIA = "guia_paso"


def guia_activa(settings, u: Usuario, e: dict) -> bool:
    """La guía nueva (GitHub App) aplica con la app encendida, aviso aceptado, uso completo y sin datos ni plan aún.
    Quien ya vinculó su copia por el camino viejo (sin instalación) sigue con la guía de siempre."""
    return bool(settings.app_github and e["consentimiento"] and e["uso"] != "cuerpo" and not e["ajustes"]
                and not e["datos"] and (not e["vinculado"] or u.gh_instalacion))


def guia_paso_maximo(u: Usuario) -> int:
    return GUIA_MAX if u.gh_instalacion else GUIA_MAX - 1


def guia_paso(u: Usuario, pedido, recordado) -> int:
    """Pantalla de la guía nueva: con instalación, la 4; si no, la pedida o la recordada (cookie), de 0 a 3."""
    if u.gh_instalacion:
        return GUIA_MAX
    for v in (pedido, recordado):
        try:
            return max(0, min(int(v), guia_paso_maximo(u)))
        except (TypeError, ValueError):
            continue
    return 0


def proximo_lunes(hoy: date | None = None) -> date:
    hoy = hoy or date.today()
    return hoy + timedelta(days=(7 - hoy.weekday()) % 7 or 7)


def liga_repo(u: Usuario, settings, pendiente=None) -> dict:
    """Ligas del paso a paso. El nombre del repo es el sugerido hasta que haya uno real (vinculado o pendiente)."""
    owner = u.github_owner or ""
    repo = u.repo or (pendiente.repo if pendiente and pendiente.repo else f"{owner}/{settings.nombre_repo_sugerido}")
    return {"repo": repo,
            "copia": (f"https://github.com/new?template_owner=pegongorasep&template_name={settings.plantilla_repo}"
                      f"&name={settings.nombre_repo_sugerido}&visibility=private"),
            "secreto": f"https://github.com/{repo}/settings/secrets/actions/new",
            "actions": f"https://github.com/{repo}/actions",
            "key": KEY_GARMIN_URL}


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def requiere(usuario):
        if usuario is None:
            return RedirectResponse("/entrar", 303)

    @app.get("/bienvenida")
    def bienvenida(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if not completo(db, usuario):
            return RedirectResponse("/perfil", 303)   # nombre y aviso primero (E1)
        e = estado(db, usuario)
        if guia_activa(settings, usuario, e):
            n = guia_paso(usuario, request.query_params.get("paso"), request.cookies.get(COOKIE_GUIA))
            resp = render(request, "bienvenida.html", guia=True, paso=n, pasos=PASOS, e=e, u=usuario,
                          version=VERSION_AVISO, liga=liga_repo(usuario, settings, None), error=_error_conexion(request),
                          liga_enviada=request.query_params.get("liga", ""))
            resp.set_cookie(COOKIE_GUIA, str(n), max_age=30 * 86400, httponly=True, secure=settings.cookie_segura,
                            samesite="lax", path="/bienvenida")
            return resp
        try:
            pedido = int(request.query_params.get("paso", ""))
        except ValueError:
            pedido = paso_inicial(e)
        paso = max(2, min(pedido, paso_maximo(e)))
        if paso == 7:   # «Tu plan»: lo arma el asistente del motor v6 (con lo que vio tu Garmin)
            return RedirectResponse("/plan/nuevo", 303)
        return render(request, "bienvenida.html", paso=paso, pasos=PASOS, e=e, u=usuario, version=VERSION_AVISO,
                      liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)),
                      error=_error_conexion(request))

    @app.post("/bienvenida/github")
    async def github(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        e = estado(db, usuario)
        if not e["consentimiento"]:
            raise HTTPException(403, request.state.t("err.primero_aviso"))
        if usuario.repo_id:
            return RedirectResponse("/bienvenida?paso=3", 303)   # ya vinculado: el usuario de GitHub ya no se cambia aquí
        owner = str(form.get("usuario", "")).strip().lstrip("@")
        error = None
        if not RE_OWNER.match(owner):
            error = request.state.t("err.gh_usuario")
        elif db.scalar(select(Usuario.id).where(Usuario.id != usuario.id, Usuario.borrado.is_(None),
                                                 Usuario.github_owner.ilike(owner))):
            error = request.state.t("err.gh_ligado")
        if error:
            return render(request, "bienvenida.html", status=400, paso=2, pasos=PASOS, e=e, u=usuario,
                          version=VERSION_AVISO, liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), error=error)
        usuario.github_owner = owner
        db.commit()
        return RedirectResponse("/bienvenida?paso=3", 303)

    @app.post("/bienvenida/codigo")
    async def codigo(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """La persona escribe el código que vio en el resumen de la corrida de su repo privado: prueba que lo controla."""
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if usuario.repo_id:
            return RedirectResponse("/bienvenida?paso=6", 303)
        p = tubo.pendiente_vigente(db, usuario.id)
        error = None
        if p is None:
            error = request.state.t("err.cod_no_hay")
        else:
            p.intentos += 1
            intento = "".join(ch for ch in str(form.get("codigo", "")) if ch.isdigit())
            if hmac.compare_digest(tubo.hash_codigo(intento), p.codigo_hash):
                tubo.vincular(db, usuario, p.repo, p.repo_id, p.owner_id, f"Repo vinculado con código: {p.repo}")
                db.delete(p)
                db.commit()
                return RedirectResponse("/bienvenida?paso=6", 303)
            if p.intentos >= tubo.MAX_INTENTOS:
                db.delete(p)
                error = request.state.t("err.cod_intentos")
            else:
                error = request.state.t("err.cod_mal", n=tubo.MAX_INTENTOS - p.intentos)
            db.commit()
        e = estado(db, usuario)
        return render(request, "bienvenida.html", status=400, paso=6, pasos=PASOS, e=e, u=usuario, version=VERSION_AVISO,
                      liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), error=error)

    @app.get("/api/estado")
    def api_estado(usuario=Depends(actual), db=Depends(get_db)):
        from fastapi.responses import JSONResponse
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        e = estado(db, usuario)
        ultima = tubo.ultima_subida(db, usuario.id)
        return {"vinculado": e["vinculado"], "repo": usuario.repo, "datos": e["datos"],
                "ultima_subida": ultima.isoformat() + "Z" if ultima else None,
                "consentimiento": e["consentimiento"], "plan": e["ajustes"]}
