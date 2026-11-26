"""Páginas del plan vivo: /plan (metas, eventos, escalón, siguiente bloque) y /plan/sesion/<n>/<id> (editor de pasos).
Todo cambio pasa por `aplicar_cambio`; las rutas valen para uno mismo y para el atleta de un coach (`/a/<id>/plan`)."""
from datetime import date

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

import build
import gen_plan
from ajustes import ConfigError, normalizar_config

from . import ajustes_web as aw
from . import calculo, cambios, plan_vivo

TIPOS_EVENTO = {"enfermedad": "Enfermedad", "lesion": "Lesión"}
NOMBRE_ESCALON = {"3/1": "3' trote · 1' caminata", "5/1": "5' trote · 1' caminata", "8/1": "8' trote · 1' caminata",
                  "12/1": "12' trote · 1' caminata", "continuo": "correr continuo"}


def _fecha(valor, campo: str) -> str:
    try:
        return date.fromisoformat(str(valor).strip()).isoformat()
    except ValueError:
        raise ConfigError(f"{campo}: escribe una fecha válida") from None


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def doble(metodo: str, ruta: str, fn) -> None:
        for base in ("", "/a/{atleta_id}"):
            getattr(app, metodo)(base + ruta)(fn)

    def contexto(db, atleta, crudo, hoy):
        """Lo que muestra /plan: config con pausas, plan guardado, estado de hoy y sugerencias."""
        cfg = plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), hoy)
        plan = aw.plan_guardado(db, atleta) or {"start": cfg["plan_start"], "weeks": []}
        data = None
        try:
            data = calculo.calcular(db, atleta, app.state.reloj().replace(tzinfo=None))
        except Exception:   # sin datos o config rara: la página sigue sin sugerencias
            data = None
        efectivo = plan_vivo.plan_efectivo(plan, cfg)
        n = build.m.semana_del_plan(hoy, cfg)
        terminado = bool(plan["weeks"]) and build.plan_terminado(hoy, cfg, efectivo)
        tarjeta = (data or {}).get("hoy", {}).get("tarjeta") or {}
        esc = plan_vivo.escalon_actual(cfg, plan, hoy)
        return {"cfg": cfg, "plan": plan, "n": n, "terminado": terminado, "esc": esc, "esc_nombre": NOMBRE_ESCALON.get(esc),
                "esc_siguiente": plan_vivo.siguiente_escalon(esc),
                "sugerido": plan_vivo.sugerir_subir_escalon(data, cfg, plan, hoy) if data else None,
                "prueba": tarjeta.get("prueba") if terminado else None,
                "inicio_siguiente": plan_vivo.inicio_siguiente_bloque(cfg, efectivo).isoformat() if terminado else None,
                "hoy": hoy.isoformat(), "editables": plan_vivo.TIPOS_EDITABLES, "nombre_escalon": NOMBRE_ESCALON,
                "tipos_evento": TIPOS_EVENTO}

    def pagina(request, usuario, db, atleta_id, status=200, **extra):
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = aw.crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        hoy = aw.hoy_de(app.state.reloj, crudo)
        ctx = {"error": None, **contexto(db, atleta, crudo, hoy), **extra}
        return render(request, "plan.html", status=status, atleta=atleta, pref=aw.prefijo(usuario, atleta),
                      ok=request.query_params.get("ok"), **ctx)

    def ver_acciones(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        return pagina(request, usuario, db, atleta_id)
    doble("get", "/plan/acciones", ver_acciones)

    def ver_plan(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        """El plan vive en la pestaña Plan del sitio: /plan solo redirige (tras comprobar sesión y permiso)."""
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return redir
        pref = aw.prefijo(usuario, atleta)
        return RedirectResponse(f"{pref}/plan/acciones" if pref else "/#plan", 303)
    doble("get", "/plan", ver_plan)

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
            hoy = aw.hoy_de(app.state.reloj, crudo)
            try:
                cfg = normalizar_config({**crudo, "modo": "web"})
                plan = aw.plan_guardado(db, atleta)
                nuevo_crudo, nuevo_plan, descripcion = hacer(db, atleta, crudo, plan_vivo.con_pausas(cfg, hoy), plan, form, hoy)
            except (ConfigError, ValueError, KeyError) as ex:
                return pagina(request, usuario, db, atleta_id, status=400, error=str(ex) if not isinstance(ex, KeyError) else "Faltan datos.")
            paquete = {"ajustes": nuevo_crudo, **({"plan": nuevo_plan} if nuevo_plan is not None else {})}
            cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), descripcion, paquete)
            return RedirectResponse(volver(usuario, atleta), 303)
        return ruta

    def lindo(d: str) -> str:
        return date.fromisoformat(d).strftime("%d/%m/%Y")

    def viaje(db, atleta, crudo, cfg, plan, f, hoy):
        desde, hasta = _fecha(f.get("desde"), "salida"), _fecha(f.get("hasta"), "regreso")
        correr = f.get("correr") == "si"
        nuevo = plan_vivo.agregar_evento(crudo, "viaje", desde, hasta, correr)
        return nuevo, None, (f"Agregó un viaje del {lindo(desde)} al {lindo(hasta)} "
                             f"({'semana ligera: 2 Z2 cortas' if correr else 'sin correr: el plan espera'})")

    def enfermo(db, atleta, crudo, cfg, plan, f, hoy):
        tipo = f.get("tipo", "enfermedad")
        if tipo not in TIPOS_EVENTO:
            raise ConfigError("Elige enfermedad o lesión.")
        desde = _fecha(f.get("desde") or hoy.isoformat(), "desde")
        return (plan_vivo.agregar_evento(crudo, tipo, desde, None), None,
                f"Marcó {TIPOS_EVENTO[tipo].lower()} desde el {lindo(desde)}: el plan espera")

    def carrera(db, atleta, crudo, cfg, plan, f, hoy):
        fecha = _fecha(f.get("fecha"), "fecha de la carrera")
        if fecha < hoy.isoformat():
            raise ConfigError("fecha de la carrera: debe ser hoy o después")
        km = str(f.get("distancia_km", "")).strip().replace(",", ".")
        nombre = str(f.get("nombre", "")).strip() or "Carrera"
        nuevo = plan_vivo.agregar_carrera(crudo, fecha, km or None, nombre)
        return nuevo, None, f"Agregó la carrera «{nombre}» el {lindo(fecha)}"

    def repetir(db, atleta, crudo, cfg, plan, f, hoy):
        n = build.m.semana_del_plan(hoy, cfg)
        if n is None:
            raise ConfigError("Hoy no hay una semana de plan para repetir.")
        return plan_vivo.repetir_semana(crudo, n), None, f"Repitió la semana {n}"

    def subir(db, atleta, crudo, cfg, plan, f, hoy):
        plan = plan or {"start": cfg["plan_start"], "weeks": []}
        nuevo = plan_vivo.subir_escalon(crudo, cfg, plan, hoy)
        nuevo_plan, desde = plan_vivo.construir_plan(nuevo, plan, hoy)
        return nuevo, nuevo_plan, f"Subió el escalón de trote/caminata a {nuevo['corrida']['escalon']} (plan rehecho desde la semana {desde})"

    def bloque(db, atleta, crudo, cfg, plan, f, hoy):
        ctx = contexto(db, atleta, crudo, hoy)
        if not ctx["terminado"]:
            raise ConfigError("Tu plan todavía no termina.")
        nuevo = plan_vivo.siguiente_bloque(crudo, cfg, plan, ctx["prueba"])
        nuevo_plan, _ = plan_vivo.construir_plan(nuevo, None, hoy)
        return nuevo, nuevo_plan, f"Armó el siguiente bloque: empieza el {lindo(nuevo['corrida']['inicio'])}"

    for nombre, fn in (("viaje", viaje), ("enfermedad", enfermo), ("carrera", carrera), ("repetir", repetir),
                       ("escalon/subir", subir), ("siguiente-bloque", bloque)):
        doble("post", f"/plan/{nombre}", accion(nombre, fn))

    # rutas con id en la ruta: se registran aparte para leer el parámetro
    def con_id(sufijo, que, descripcion):
        async def ruta(request: Request, ident: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
            form = await formulario(request)
            atleta, redir = aw.resolver(db, usuario, atleta_id)
            if redir:
                return redir
            crudo = aw.crudo_de(db, atleta)
            if crudo is None:
                return RedirectResponse("/bienvenida", 303)
            hoy = aw.hoy_de(app.state.reloj, crudo)
            try:
                nuevo = que(crudo, ident, hoy)
            except (ConfigError, ValueError) as ex:
                return pagina(request, usuario, db, atleta_id, status=400, error=str(ex))
            cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), descripcion, {"ajustes": nuevo})
            return RedirectResponse(volver(usuario, atleta), 303)
        doble("post", f"/plan/{sufijo}", ruta)

    con_id("evento/{ident}/cerrar", lambda c, i, hoy: plan_vivo.cerrar_evento(c, i, hoy.isoformat()),
           "Marcó que ya estás bien: el plan se reanuda")
    con_id("evento/{ident}/quitar", lambda c, i, hoy: plan_vivo.quitar_evento(c, i), "Quitó un evento del plan")
    con_id("meta/{ident}/quitar", lambda c, i, hoy: plan_vivo.quitar_meta(c, i), "Quitó una carrera del plan")

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
                puede, filas, veces, error = False, [], {}, str(ex)
        vacias = max(0, 4 - len(filas)) if puede else 0
        filas = filas + [{"tipo": "trote", "min": "", "zona": "Z2", "grupo": 0, "nota": "", "opcional": False}] * vacias
        return render(request, "sesion.html", status=status, atleta=atleta, pref=aw.prefijo(usuario, atleta), n=n, w=w, s=s,
                      filas=filas, veces=veces or {}, puede=puede, error=error, grupos=range(1, plan_vivo.MAX_GRUPOS + 1),
                      zonas=plan_vivo.ZONAS, minutos=gen_plan.suma(s["steps"]))

    def sesion_get(request: Request, n: int, sid: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        return editor(request, usuario, db, atleta_id, n, sid)
    doble("get", "/plan/sesion/{n}/{sid}", sesion_get)

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
            filas.append({"tipo": form.get(f"tipo_{i}", "trote"), "min": form.get(f"min_{i}"), "zona": form.get(f"zona_{i}", "Z2"),
                          "grupo": int(form.get(f"grupo_{i}") or 0), "nota": form.get(f"nota_{i}", ""), "opcional": form.get(f"opc_{i}") == "1"})
        for g in range(1, plan_vivo.MAX_GRUPOS + 1):
            try:
                veces[g] = int(form.get(f"veces_{g}") or 0)
            except ValueError:
                veces[g] = 0
        try:
            nuevo_plan = plan_vivo.editar_sesion(plan, n, sid, plan_vivo.pasos_de_filas(filas, veces))
        except (ConfigError, ValueError) as ex:
            return editor(request, usuario, db, atleta_id, n, sid, status=400, filas=filas, veces=veces, error=str(ex))
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta),
                               f"Cambió la sesión «{s['name']}» de la semana {n}", {"plan": nuevo_plan})
        return RedirectResponse(volver(usuario, atleta), 303)
    doble("post", "/plan/sesion/{n}/{sid}", sesion_post)
