"""Onboarding (/bienvenida): aviso y consentimiento -> usuario de GitHub -> copia, key y Actions -> espera de datos ->
preguntas del plan. El avance sale de la base (se puede salir y volver al paso donde iba)."""
import hmac
import re
from datetime import date, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import gen_plan
from ajustes import (CALIDAD_TIPOS, INTENSIDADES, NIVELES, ConfigError, categorias_por_defecto, normalizar_config)

from . import cambios, importar, tubo
from .modelos import Ajustes, Cambio, Consentimiento, Usuario
from .privacidad import VERSION_AVISO

PASOS = ["Aviso", "GitHub", "Tu copia", "Tu key", "Actívalo", "Tus datos", "Tu plan"]
RE_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
KEY_GARMIN_URL = "https://connect.garmin.com/app/settings/personalApiToken"
ZONAS = ["America/Merida", "America/Mexico_City", "America/Monterrey", "America/Cancun", "America/Tijuana",
         "America/Bogota", "America/Lima", "America/Santiago", "America/Argentina/Buenos_Aires", "Europe/Madrid", "UTC"]
DIAS = [("lun", "Lunes"), ("mar", "Martes"), ("mié", "Miércoles"), ("jue", "Jueves"), ("vie", "Viernes"),
        ("sáb", "Sábado"), ("dom", "Domingo")]


def estado(db: Session, u: Usuario) -> dict:
    return {"consentimiento": db.scalar(select(Consentimiento.id).where(
                Consentimiento.usuario_id == u.id, Consentimiento.version_aviso == VERSION_AVISO).limit(1)) is not None,
            "owner": bool(u.github_owner), "vinculado": bool(u.repo_id),
            "datos": tubo.tuvo_subida_ok(db, u.id), "ajustes": db.get(Ajustes, u.id) is not None,
            "pendiente": tubo.pendiente_vigente(db, u.id) is not None}


def paso_maximo(e: dict) -> int:
    if not e["consentimiento"]:
        return 1
    if e["ajustes"]:
        return 1   # ya tiene plan: no hay nada más que hacer aquí
    if not e["owner"]:
        return 2
    return 7 if e["datos"] else 6


def paso_inicial(e: dict) -> int:
    if not e["consentimiento"]:
        return 1
    if not e["owner"]:
        return 2
    if e["datos"]:
        return 7
    return 6 if (e["vinculado"] or e["pendiente"]) else 3


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


def crudo_desde_formulario(f) -> dict:
    """Arma el `config.yaml` crudo de las respuestas del paso 7 (ConfigError con mensaje en español si algo no vale)."""
    def entero(campo, nombre, vacio_ok=False):
        v = str(f.get(campo, "")).strip()
        if not v and vacio_ok:
            return None
        try:
            n = int(v)
        except ValueError:
            raise ConfigError(f"{nombre}: escribe un número entero") from None
        if n <= 0:
            raise ConfigError(f"{nombre}: debe ser mayor que cero")
        return n
    zona = str(f.get("zona", "America/Merida")).strip()
    try:
        ZoneInfo(zona)
    except (ZoneInfoNotFoundError, ValueError):
        raise ConfigError(f"Zona horaria '{zona}' no válida") from None
    edad, fc_max = entero("edad", "Edad", True), entero("fc_max", "FC máxima", True)
    if edad is None and fc_max is None:
        raise ConfigError("Escribe tu edad o tu FC máxima")
    perfil = {"titulo": (str(f.get("titulo", "")).strip() or "Mi entreno")[:60], "zona_horaria": zona}
    if edad:
        perfil["edad"] = edad
    if fc_max:
        perfil["fc_max"] = fc_max
    intensidad = f.get("intensidad", "z2_poca_z3")
    calidad = [t for t in f.getlist("calidad") if t in CALIDAD_TIPOS] if intensidad == "calidad" else []
    corrida = {"nivel": f.get("nivel", "intermedio"), "intensidad": intensidad, "calidad_tipos": calidad,
               "variada": True, "caminatas": f.get("caminatas") == "on", "inicio": str(f.get("inicio", "")),
               "semanas": 12, "base_min": {"z2": entero("z2", "Minutos de la Z2"), "larga": entero("larga", "Minutos de la larga")}}
    elegidas = set(f.getlist("cats"))
    categorias = [c for c in categorias_por_defecto() if c["id"] in elegidas]
    actividades = {"dias_pierna": [d for d in f.getlist("pierna") if d in dict(DIAS)]}
    if categorias:
        actividades["categorias"] = categorias
    return {"perfil": perfil, "corrida": corrida, "actividades": actividades, "inbody": f.get("inbody") == "on"}


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def requiere(usuario):
        if usuario is None:
            return RedirectResponse("/entrar", 303)

    @app.get("/bienvenida")
    def bienvenida(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        e = estado(db, usuario)
        if e["ajustes"] and e["consentimiento"]:
            return RedirectResponse("/", 303)
        try:
            pedido = int(request.query_params.get("paso", ""))
        except ValueError:
            pedido = paso_inicial(e)
        paso = max(1, min(pedido, paso_maximo(e)))
        return render(request, "bienvenida.html", paso=paso, pasos=PASOS, e=e, u=usuario, version=VERSION_AVISO,
                      liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), proximo_lunes=proximo_lunes().isoformat(),
                      zonas=ZONAS, categorias=categorias_por_defecto(), dias=DIAS, niveles=NIVELES,
                      intensidades=INTENSIDADES, tipos_calidad=CALIDAD_TIPOS, error=None, valores={})

    @app.post("/bienvenida/consentimiento")
    async def consentimiento(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if form.get("acepto") != "on":
            return RedirectResponse("/bienvenida?paso=1", 303)
        db.add(Consentimiento(usuario_id=usuario.id, version_aviso=VERSION_AVISO))
        db.commit()
        return RedirectResponse("/bienvenida", 303)

    @app.post("/bienvenida/github")
    async def github(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        e = estado(db, usuario)
        if not e["consentimiento"]:
            raise HTTPException(403, "Primero acepta el aviso de privacidad")
        if usuario.repo_id:
            return RedirectResponse("/bienvenida?paso=3", 303)   # ya vinculado: el usuario de GitHub ya no se cambia aquí
        owner = str(form.get("usuario", "")).strip().lstrip("@")
        error = None
        if not RE_OWNER.match(owner):
            error = "Escribe tu usuario de GitHub (letras, números y guiones)."
        elif db.scalar(select(Usuario.id).where(Usuario.id != usuario.id, Usuario.borrado.is_(None),
                                                 Usuario.github_owner.ilike(owner))):
            error = "Ese usuario de GitHub ya está ligado a otra cuenta."
        if error:
            return render(request, "bienvenida.html", status=400, paso=2, pasos=PASOS, e=e, u=usuario,
                          version=VERSION_AVISO, liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), error=error,
                          proximo_lunes="", zonas=[], categorias=[], dias=[], niveles=[], intensidades=[],
                          tipos_calidad=[], valores={})
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
            error = "No hay un código vigente. Corre «Run workflow» en tu repo para generar uno nuevo."
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
                error = "Demasiados intentos. Corre «Run workflow» otra vez en tu repo para generar un código nuevo."
            else:
                error = f"Ese código no coincide ({tubo.MAX_INTENTOS - p.intentos} intentos más)."
            db.commit()
        e = estado(db, usuario)
        return render(request, "bienvenida.html", status=400, paso=6, pasos=PASOS, e=e, u=usuario, version=VERSION_AVISO,
                      liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), error=error,
                      proximo_lunes="", zonas=[], categorias=[], dias=[], niveles=[], intensidades=[],
                      tipos_calidad=[], valores={})

    @app.post("/bienvenida/plan")
    async def plan(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        e = estado(db, usuario)
        if not (e["consentimiento"] and e["owner"] and e["datos"]) or e["ajustes"]:
            raise HTTPException(403, "Todavía no puedes crear tu plan")
        try:
            crudo = crudo_desde_formulario(form)
            cfg = normalizar_config(crudo)
            nuevo_plan = gen_plan.generar(cfg)
        except (ConfigError, ValueError) as ex:
            return render(request, "bienvenida.html", status=400, paso=7, pasos=PASOS, e=e, u=usuario,
                          version=VERSION_AVISO, liga=liga_repo(usuario, settings, tubo.pendiente_vigente(db, usuario.id)), error=str(ex),
                          proximo_lunes=proximo_lunes().isoformat(), zonas=ZONAS, categorias=categorias_por_defecto(),
                          dias=DIAS, niveles=NIVELES, intensidades=INTENSIDADES, tipos_calidad=CALIDAD_TIPOS,
                          valores=dict(form.multi_items()) if hasattr(form, "multi_items") else dict(form))
        usuario.sensor = "muñeca" if form.get("sensor") == "muñeca" else "banda"
        crudo["perfil"]["sensor"] = usuario.sensor
        cambios.aplicar_cambio(db, usuario, usuario, "sistema", "Plan creado en el onboarding",
                               {"ajustes": crudo, "plan": nuevo_plan})
        return RedirectResponse("/", 303)

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
