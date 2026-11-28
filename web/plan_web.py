"""Páginas del plan vivo: /plan (metas, eventos) y /plan/sesion/<n>/<id> (editor de pasos).
Todo cambio pasa por `aplicar_cambio`; las rutas valen para uno mismo y para el atleta de un coach (`/a/<id>/plan`)."""
import json
from datetime import date, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from dashboard.construir import comun as c_comun
from dashboard.metricas import semana as mt_semana
from plan import pasos
from dashboard.ajustes import ConfigError, normalizar_config
from .errores import ErrorT, texto

from . import ajustes_web as aw
from .deps import actual, doble, formulario, get_db, render
from . import calculo, cambios, plan_vivo
from .modelos import Usuario
from .permisos import puede_ver

TIPOS_EVENTO = {"enfermedad": "Enfermedad", "lesion": "Lesión"}


def _fecha(valor, campo: str) -> str:
    try:
        return date.fromisoformat(str(valor).strip()).isoformat()
    except ValueError:
        raise ErrorT("err.fecha_c", campo="@campo." + campo) from None


router = APIRouter()


def contexto(db, atleta, crudo, hoy, idioma=None):
    """Lo que muestra /plan: config con pausas, plan guardado y estado de hoy."""
    cfg = plan_vivo.con_pausas(normalizar_config(crudo), hoy)
    plan = aw.plan_guardado(db, atleta) or {"start": cfg["plan_start"], "weeks": []}
    efectivo = plan_vivo.plan_efectivo(plan, cfg)
    n = mt_semana.semana_del_plan(hoy, cfg)
    terminado = bool(plan["weeks"]) and c_comun.plan_terminado(hoy, cfg, efectivo)
    return {"cfg": cfg, "plan": plan, "n": n, "terminado": terminado, "hoy": hoy.isoformat(),
            "editables": plan_vivo.TIPOS_EDITABLES, "tipos_evento": TIPOS_EVENTO}

def pagina(request, usuario, db, atleta_id, status=200, **extra):
    atleta, redir = aw.resolver(db, usuario, atleta_id)
    if redir:
        return redir
    crudo = aw.crudo_de(db, atleta)
    if crudo is None:
        return RedirectResponse("/bienvenida", 303)
    hoy = aw.hoy_de(request.app.state.reloj, crudo)
    ctx = {**aw.contexto_ajustes(db, atleta, usuario, crudo), **contexto(db, atleta, crudo, hoy, request.state.idioma), **extra}
    return render(request, "plan.html", status=status, ok=request.query_params.get("ok"), **ctx)

def ver_acciones(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    return pagina(request, usuario, db, atleta_id)
doble(router, "get", "/plan/acciones", ver_acciones)

def plan_reloj(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    """Descarga el plan efectivo en el JSON que lee `reloj.py semana --plan`. Dueño o coach."""
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    aid = atleta_id or usuario.id
    if not puede_ver(db, usuario, aid):
        raise HTTPException(404)
    atleta = db.get(Usuario, aid)
    crudo = aw.crudo_de(db, atleta)
    plan = aw.plan_guardado(db, atleta)
    if crudo is None or not plan:
        raise HTTPException(404)
    hoy = aw.hoy_de(request.app.state.reloj, crudo)
    cfg = plan_vivo.con_pausas(normalizar_config(crudo), hoy)
    cuerpo = json.dumps(plan_vivo.plan_efectivo(plan, cfg), ensure_ascii=False, indent=1)
    return Response(cuerpo, media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="plan.json"', "Cache-Control": "no-store"})
doble(router, "get", "/plan/reloj.json", plan_reloj)

def ver_plan(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    """El plan vive en la pestaña Plan del sitio: /plan solo redirige (tras comprobar sesión y permiso)."""
    atleta, redir = aw.resolver(db, usuario, atleta_id)
    if redir:
        return redir
    pref = aw.prefijo(usuario, atleta)
    return RedirectResponse(f"{pref}/plan/acciones" if pref else "/#plan", 303)
doble(router, "get", "/plan", ver_plan)

def volver(usuario, atleta) -> str:
    """Adónde regresa un POST del plan: la pestaña Plan (para quien ve su propio sitio) o la página de acciones."""
    pref = aw.prefijo(usuario, atleta)
    return f"{pref}/plan/acciones?ok=1" if pref else "/?ok=plan#plan"

def accion(nombre: str, hacer, desc_de=None):
    """Registra POST /plan/<nombre>. `hacer(crudo, cfg, plan, form, hoy, data)` devuelve (crudo, plan o None, descripción)."""
    async def ruta(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = aw.crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        hoy = aw.hoy_de(request.app.state.reloj, crudo)
        try:
            cfg = normalizar_config(crudo)
            plan = aw.plan_guardado(db, atleta)
            nuevo_crudo, nuevo_plan, descripcion = hacer(db, atleta, crudo, plan_vivo.con_pausas(cfg, hoy), plan, form, hoy)
        except (ConfigError, ValueError, KeyError) as ex:
            return pagina(request, usuario, db, atleta_id, status=400, error=texto(ex, request.state.t) if not isinstance(ex, KeyError) else request.state.t("err.faltan"))
        paquete = {"ajustes": nuevo_crudo, **({"plan": nuevo_plan} if nuevo_plan is not None else {})}
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), descripcion, paquete)
        return RedirectResponse(volver(usuario, atleta), 303)
    return ruta

def lindo(d: str) -> str:
    return date.fromisoformat(d).strftime("%d/%m/%Y")

def viaje(db, atleta, crudo, cfg, plan, f, hoy):
    desde, hasta = _fecha(f.get("desde"), "salida"), _fecha(f.get("hasta"), "regreso")
    modo = f.get("modo") or ("menos" if f.get("correr") == "si" else "pausa")
    if modo not in ("pausa", "menos", "igual"):
        raise ErrorT("err.viaje")
    nuevo = plan_vivo.agregar_evento(crudo, "viaje", desde, hasta, modo=modo)
    return nuevo, None, (f"Agregó un viaje del {lindo(desde)} al {lindo(hasta)} "
                         f"({ {'menos': 'semana ligera: 2 Z2 cortas', 'igual': 'sigo entrenando igual', 'pausa': 'sin correr: el plan espera'}[modo] })")

def enfermo(db, atleta, crudo, cfg, plan, f, hoy):
    tipo = f.get("tipo", "enfermedad")
    if tipo not in TIPOS_EVENTO:
        raise ErrorT("err.enfermo")
    desde = _fecha(f.get("desde") or hoy.isoformat(), "desde")
    return (plan_vivo.agregar_evento(crudo, tipo, desde, None), None,
            f"Marcó {TIPOS_EVENTO[tipo].lower()} desde el {lindo(desde)}: el plan espera")

def carrera(db, atleta, crudo, cfg, plan, f, hoy):
    fecha = _fecha(f.get("fecha"), "fecha_carrera")
    if fecha < hoy.isoformat():
        raise ErrorT("err.fecha_carrera")
    km = str(f.get("distancia_km", "")).strip().replace(",", ".")
    nombre = str(f.get("nombre", "")).strip() or "Carrera"
    nuevo = plan_vivo.agregar_carrera(crudo, fecha, km or None, nombre)   # carrera de paso: el plan no cambia
    return nuevo, None, f"Agregó la carrera de paso «{nombre}» el {lindo(fecha)}"

def quitadas(info) -> str:
    return f"; se quitaron las semanas {', '.join(map(str, info['quita']))}" if info["quita"] else ""

def repetir(db, atleta, crudo, cfg, plan, f, hoy):
    n = mt_semana.semana_del_plan(hoy, cfg)
    nuevo, info = plan_vivo.repetir(crudo, plan or {"weeks": []}, cfg, hoy)
    return nuevo, None, f"Repitió la semana {n}{quitadas(info)}"

def retomar(db, atleta, crudo, cfg, plan, f, hoy):
    x = int(f.get("semana") or "x")   # ValueError -> 400
    nuevo, info = plan_vivo.retomar(crudo, plan or {"weeks": []}, cfg, hoy, x)
    return nuevo, None, f"Retomó desde la semana {x}{quitadas(info)}"

for nombre, fn in (("viaje", viaje), ("enfermedad", enfermo), ("carrera", carrera), ("repetir", repetir), ("retomar", retomar)):
    doble(router, "post", f"/plan/{nombre}", accion(nombre, fn))

def propuesta(request: Request, accion: str = "", semana: str = "", atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    """Vista previa de «Repetir o retomar»: calcula el plan que quedaría sin guardar nada (ni la caché)."""
    atleta, redir = aw.resolver(db, usuario, atleta_id)
    if redir:
        return redir
    crudo = aw.crudo_de(db, atleta)
    if crudo is None:
        raise HTTPException(404)
    hoy = aw.hoy_de(request.app.state.reloj, crudo)
    t = request.state.t
    sin_cache = {"Cache-Control": "no-store"}
    try:
        cfg = plan_vivo.con_pausas(normalizar_config(crudo), hoy)
        plan = aw.plan_guardado(db, atleta) or {"weeks": []}
        if accion == "repetir":
            nuevo, info = plan_vivo.repetir(crudo, plan, cfg, hoy)
            x = None
        elif accion == "retomar":
            try:
                x = int(semana)
            except ValueError:
                raise ErrorT("err.retomar_rango", n=mt_semana.semana_del_plan(hoy, cfg) or 0) from None
            nuevo, info = plan_vivo.retomar(crudo, plan, cfg, hoy, x)
        else:
            raise ErrorT("err.faltan")
        ahora_utc = request.app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None)
        data = calculo.calcular_propuesta(db, atleta, nuevo, ahora_utc, request.state.idioma)
    except ConfigError as ex:
        return JSONResponse({"error": texto(ex, t)}, status_code=400, headers=sin_cache)
    aviso = t("plan.aviso_carrera", quita=", ".join(map(str, info["quita"]))) if info["objetivo"] and info["quita"] else None
    pref = aw.prefijo(usuario, atleta)
    return JSONResponse({"plan": data["plan"], "info": info, "aviso": aviso,
                         "aplicar": {"url": f"{pref}/plan/{accion}", "semana": x}}, headers=sin_cache)
doble(router, "get", "/plan/propuesta.json", propuesta)

# rutas con id en la ruta: se registran aparte para leer el parámetro
def con_id(sufijo, que, descripcion, con_plan=False):
    async def ruta(request: Request, ident: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)  # noqa: F841 -- se llama por efecto (valida el CSRF)
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = aw.crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        hoy = aw.hoy_de(request.app.state.reloj, crudo)
        try:
            if con_plan:   # `que` devuelve (ajustes, plan nuevo o None)
                cfg = plan_vivo.con_pausas(normalizar_config(crudo), hoy)
                nuevo, nuevo_plan = que(crudo, ident, hoy, aw.plan_guardado(db, atleta), cfg)
            else:
                nuevo, nuevo_plan = que(crudo, ident, hoy), None
        except (ConfigError, ValueError) as ex:
            return pagina(request, usuario, db, atleta_id, status=400, error=texto(ex, request.state.t))
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), descripcion,
                               {"ajustes": nuevo, **({"plan": nuevo_plan} if nuevo_plan is not None else {})})
        return RedirectResponse(volver(usuario, atleta), 303)
    doble(router, "post", f"/plan/{sufijo}", ruta)

con_id("evento/{ident}/cerrar", lambda c, i, hoy: plan_vivo.cerrar_evento(c, i, hoy.isoformat()),
       "Marcó que ya estás bien: el plan se reanuda")
con_id("evento/{ident}/quitar", lambda c, i, hoy: plan_vivo.quitar_evento(c, i), "Quitó un evento del plan")
for m_, txt in (("igual", "sigo entrenando igual"), ("menos", "voy a correr menos"), ("pausa", "no voy a correr")):
    con_id(f"evento/{{ident}}/modo-{m_}", lambda c, i, hoy, m_=m_: plan_vivo.cambiar_modo_viaje(c, i, m_),
           f"Cambió el viaje a: {txt}")
con_id("meta/{ident}/quitar", lambda c, i, hoy, plan, cfg: plan_vivo.quitar_meta_en_plan(c, plan, cfg, i, hoy),
       "Quitó una carrera del plan", con_plan=True)

# ---------- editor de sesión ----------
def sesion_de(plan, n, sid):
    w = next((x for x in (plan or {}).get("weeks", []) if x["n"] == n), None)
    s = next((x for x in w["sessions"] if x["id"] == sid), None) if w else None
    if s is None:
        raise HTTPException(404)
    return w, s

def editor(request, usuario, db, atleta_id, n, sid, status=200, filas=None, veces=None, error=None):
    atleta, redir = aw.resolver(db, usuario, atleta_id)
    if redir:
        return redir
    plan = aw.plan_guardado(db, atleta)
    w, s = sesion_de(plan, n, sid)
    puede = s.get("tipo") in plan_vivo.TIPOS_EDITABLES
    if filas is None:
        try:
            filas, veces = plan_vivo.filas_de(s["steps"])
        except ConfigError as ex:
            puede, filas, veces, error = False, [], {}, texto(ex, request.state.t)
    vacias = max(0, 4 - len(filas)) if puede else 0
    filas = filas + [{"tipo": "trote", "min": "", "zona": "Z2", "grupo": 0, "nota": "", "opcional": False}] * vacias
    return render(request, "sesion.html", status=status, atleta=atleta, pref=aw.prefijo(usuario, atleta), n=n, w=w, s=s,
                  filas=filas, veces=veces or {}, puede=puede, error=error, grupos=range(1, plan_vivo.MAX_GRUPOS + 1),
                  zonas=plan_vivo.ZONAS, minutos=pasos.suma(s["steps"]))

def sesion_get(request: Request, n: int, sid: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    return editor(request, usuario, db, atleta_id, n, sid)
doble(router, "get", "/plan/sesion/{n}/{sid}", sesion_get)

async def sesion_post(request: Request, n: int, sid: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
    form = await formulario(request)
    atleta, redir = aw.resolver(db, usuario, atleta_id)
    if redir:
        return redir
    plan = aw.plan_guardado(db, atleta)
    w, s = sesion_de(plan, n, sid)
    filas, veces = [], {}
    for i in range(1, int(form.get("filas", 0) or 0) + 1):
        if not str(form.get(f"min_{i}", "")).strip():
            continue   # fila vacía
        filas.append({"tipo": form.get(f"tipo_{i}") or "trote", "min": form.get(f"min_{i}"), "zona": form.get(f"zona_{i}", "Z2"),
                      "grupo": int(form.get(f"grupo_{i}") or 0), "nota": form.get(f"nota_{i}", ""), "opcional": form.get(f"opc_{i}") == "1"})
    for g in range(1, plan_vivo.MAX_GRUPOS + 1):
        try:
            veces[g] = int(form.get(f"veces_{g}") or 0)
        except ValueError:
            veces[g] = 0
    try:
        nuevo_plan = plan_vivo.editar_sesion(plan, n, sid, plan_vivo.pasos_de_filas(filas, veces))
    except (ConfigError, ValueError) as ex:
        return editor(request, usuario, db, atleta_id, n, sid, status=400, filas=filas, veces=veces, error=texto(ex, request.state.t))
    cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta),
                           f"Cambió la sesión «{s['name']}» de la semana {n}", {"plan": nuevo_plan})
    return RedirectResponse(volver(usuario, atleta), 303)
doble(router, "post", "/plan/sesion/{n}/{sid}", sesion_post)
