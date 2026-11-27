"""Páginas del plan vivo: /plan (metas, eventos, escalón, siguiente bloque) y /plan/sesion/<n>/<id> (editor de pasos).
Todo cambio pasa por `aplicar_cambio`; las rutas valen para uno mismo y para el atleta de un coach (`/a/<id>/plan`)."""
import json
from datetime import date

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, Response

import build
import gen_plan
from ajustes import ConfigError, normalizar_config
from .errores import ErrorT, texto

from . import ajustes_web as aw
from . import calculo, cambios, plan_vivo
from .modelos import Usuario
from .permisos import puede_ver

TIPOS_EVENTO = {"enfermedad": "Enfermedad", "lesion": "Lesión"}
NOMBRE_ESCALON = {"3/1": "3' trote · 1' caminata", "5/1": "5' trote · 1' caminata", "8/1": "8' trote · 1' caminata",
                  "12/1": "12' trote · 1' caminata", "continuo": "correr continuo"}


def _fecha(valor, campo: str) -> str:
    try:
        return date.fromisoformat(str(valor).strip()).isoformat()
    except ValueError:
        raise ErrorT("err.fecha_c", campo="@campo." + campo) from None


def montar(app, get_db, actual, render, formulario, settings) -> None:
    def doble(metodo: str, ruta: str, fn) -> None:
        for base in ("", "/a/{atleta_id}"):
            getattr(app, metodo)(base + ruta)(fn)

    def contexto(db, atleta, crudo, hoy, idioma=None):
        """Lo que muestra /plan: config con pausas, plan guardado, estado de hoy y sugerencias."""
        cfg = plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), hoy)
        plan = aw.plan_guardado(db, atleta) or {"start": cfg["plan_start"], "weeks": []}
        data = None
        try:
            data = calculo.calcular(db, atleta, app.state.reloj().replace(tzinfo=None), idioma=idioma)
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
        ctx = {**aw.contexto_ajustes(db, atleta, usuario, crudo), **contexto(db, atleta, crudo, hoy, request.state.idioma), **extra}
        return render(request, "plan.html", status=status, ok=request.query_params.get("ok"), **ctx)

    async def rehacer(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        """«Rehacer mi plan»: los campos base del plan. Si el plan cambia, pasa por la pantalla de confirmación; nunca rehace a ciegas."""
        form = await formulario(request)
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = aw.crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        pref = aw.prefijo(usuario, atleta)
        hoy = aw.hoy_de(app.state.reloj, crudo)
        valores = {k: (form.getlist(k) if k in ("calidad", "pierna") else form.get(k, "")) for k in form.keys()}
        for k in ("caminatas", "variada"):
            valores[k] = form.get(k) == "on"
        try:
            nuevo = aw.crudo_plan(crudo, form)
            cfg_viejo, cfg_nuevo = normalizar_config(crudo), normalizar_config(nuevo)
            cambios_txt = aw.diferencias(crudo, nuevo)
            if not cambios_txt:
                return RedirectResponse(f"{pref}/plan/acciones?ok=sin#rehacer", 303)
            nuevo_plan, desde = None, None
            if plan_vivo.cambia_plan(cfg_viejo, cfg_nuevo):
                nuevo_plan, desde = plan_vivo.construir_plan(nuevo, aw.plan_guardado(db, atleta), hoy)
        except (ConfigError, ValueError) as ex:
            msg = texto(ex, request.state.t)
            campo = ex.campo if hasattr(ex, "clave") else aw.campo_del_error(str(ex))
            extra = {"errores": {campo: msg}} if campo else {"error": msg}
            return pagina(request, usuario, db, atleta_id, status=400, v={**aw.valores_form(crudo, atleta), **valores}, **extra)
        if nuevo_plan is not None and form.get("confirmo") != "1":
            tt = request.state.t
            frase = tt("conf.frase_1") if desde == 1 else tt("conf.frase_n", desde=desde)
            etiq = {v: k for k, v in aw.ETIQUETAS.items()}
            return render(request, "ajustes_confirmar.html", atleta=atleta, pref=pref, frase=frase,
                          accion=f"{pref}/plan/rehacer", volver=f"{pref}/plan/acciones#rehacer",
                          cambios=[tt("et." + etiq[c]) for c in cambios_txt],
                          pares=[(k, v) for k, v in form.multi_items() if k not in ("csrf", "confirmo")])
        desc = "Ajustes: cambió " + ", ".join(cambios_txt) + (f"; plan rehecho desde la semana {desde}" if nuevo_plan else "")
        paquete = {"ajustes": nuevo, **({"plan": nuevo_plan} if nuevo_plan else {})}
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), desc, paquete)
        return RedirectResponse(f"{pref}/plan/acciones?ok=rehecho#rehacer", 303)
    doble("post", "/plan/rehacer", rehacer)

    def ver_acciones(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        return pagina(request, usuario, db, atleta_id)
    doble("get", "/plan/acciones", ver_acciones)

    def plan_reloj(atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
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
        hoy = aw.hoy_de(app.state.reloj, crudo)
        cfg = plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), hoy)
        cuerpo = json.dumps(plan_vivo.plan_efectivo(plan, cfg), ensure_ascii=False, indent=1)
        return Response(cuerpo, media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="plan.json"', "Cache-Control": "no-store"})
    doble("get", "/plan/reloj.json", plan_reloj)

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
        nuevo = plan_vivo.agregar_carrera(crudo, fecha, km or None, nombre)
        return nuevo, None, f"Agregó la carrera «{nombre}» el {lindo(fecha)}"

    def repetir(db, atleta, crudo, cfg, plan, f, hoy):
        n = build.m.semana_del_plan(hoy, cfg)
        if n is None:
            raise ErrorT("err.sin_semana")
        return plan_vivo.repetir_semana(crudo, n), None, f"Repitió la semana {n}"

    def subir(db, atleta, crudo, cfg, plan, f, hoy):
        plan = plan or {"start": cfg["plan_start"], "weeks": []}
        nuevo = plan_vivo.subir_escalon(crudo, cfg, plan, hoy)
        nuevo_plan, desde = plan_vivo.construir_plan(nuevo, plan, hoy)
        return nuevo, nuevo_plan, f"Subió el escalón de trote/caminata a {nuevo['corrida']['escalon']} (plan rehecho desde la semana {desde})"

    def bloque(db, atleta, crudo, cfg, plan, f, hoy):
        ctx = contexto(db, atleta, crudo, hoy)
        if not ctx["terminado"]:
            raise ErrorT("err.no_termina")
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
                return pagina(request, usuario, db, atleta_id, status=400, error=texto(ex, request.state.t))
            cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), descripcion, {"ajustes": nuevo})
            return RedirectResponse(volver(usuario, atleta), 303)
        doble("post", f"/plan/{sufijo}", ruta)

    con_id("evento/{ident}/cerrar", lambda c, i, hoy: plan_vivo.cerrar_evento(c, i, hoy.isoformat()),
           "Marcó que ya estás bien: el plan se reanuda")
    con_id("evento/{ident}/quitar", lambda c, i, hoy: plan_vivo.quitar_evento(c, i), "Quitó un evento del plan")
    for m_, txt in (("igual", "sigo entrenando igual"), ("menos", "voy a correr menos"), ("pausa", "no voy a correr")):
        con_id(f"evento/{{ident}}/modo-{m_}", lambda c, i, hoy, m_=m_: plan_vivo.cambiar_modo_viaje(c, i, m_),
               f"Cambió el viaje a: {txt}")
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
                puede, filas, veces, error = False, [], {}, texto(ex, request.state.t)
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
            return editor(request, usuario, db, atleta_id, n, sid, status=400, filas=filas, veces=veces, error=texto(ex, request.state.t))
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta),
                               f"Cambió la sesión «{s['name']}» de la semana {n}", {"plan": nuevo_plan})
        return RedirectResponse(volver(usuario, atleta), 303)
    doble("post", "/plan/sesion/{n}/{sid}", sesion_post)
