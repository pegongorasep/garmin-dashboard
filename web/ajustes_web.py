"""Páginas de edición: /ajustes (lo que hacía /ajustar), /historial (con deshacer) y /cuerpo (InBody).
Cada ruta existe para uno mismo (`/ajustes`) y para el atleta de un coach (`/a/<id>/ajustes`); `resolver` decide con
`puede_editar` y responde 404 si no hay acceso (no confirma que exista)."""
import copy
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ajustes import SENSORES, ConfigError, normalizar_config

from . import cambios
from .modelos import Ajustes, Cambio, Plan, Subida, Usuario, ahora
from .errores import ErrorT, texto
from .onboarding import ZONAS
from .permisos import puede_editar

ETIQUETAS = {"titulo": "el título", "timezone": "la zona horaria", "edad": "la edad", "max_hr": "la FC máxima",
             "sensor": "el sensor", "inbody": "InBody"}
# Dónde mostrar un error de `normalizar_config`: (fragmento del mensaje, campo del formulario)
ERROR_CAMPO = [("zona", "zona"), ("fc_max", "fc_max"), ("edad", "edad"), ("sensor", "sensor")]


def resolver(db: Session, usuario: Usuario | None, atleta_id: int | None):
    """(atleta, None) si `usuario` puede editarlo; (None, respuesta) si hay que ir a /entrar. 404 si no puede."""
    if usuario is None:
        return None, RedirectResponse("/entrar", 303)
    aid = atleta_id or usuario.id
    if not puede_editar(db, usuario, aid):
        raise HTTPException(404)
    return db.get(Usuario, aid), None


def prefijo(usuario: Usuario, atleta: Usuario) -> str:
    return "" if usuario.id == atleta.id else f"/a/{atleta.id}"


def hoy_de(reloj, crudo: dict) -> date:
    tz = ((crudo or {}).get("perfil") or {}).get("zona_horaria") or "America/Merida"
    return reloj().astimezone(ZoneInfo(tz)).date()


def crudo_de(db: Session, atleta: Usuario) -> dict | None:
    fila = db.get(Ajustes, atleta.id)
    return copy.deepcopy(fila.config) if fila else None


def plan_guardado(db: Session, atleta: Usuario) -> dict | None:
    fila = db.get(Plan, atleta.id)
    return copy.deepcopy(fila.plan) if fila else None


# --- formulario de ajustes <-> crudo ---

def valores_form(crudo: dict, atleta: Usuario) -> dict:
    perfil = crudo.get("perfil") or {}
    cfg = normalizar_config({**crudo, "perfil": {**perfil, "sensor": perfil.get("sensor") or atleta.sensor or "banda"}})
    return {"titulo": perfil.get("titulo", "Mi entreno"), "zona": perfil.get("zona_horaria", "America/Merida"),
            "edad": perfil.get("edad") or "", "fc_max": perfil.get("fc_max") or "", "sensor": cfg["sensor"], "inbody": cfg["inbody"]}


def _entero(f, campo: str, nombre: str, vacio_ok: bool = False):
    v = str(f.get(campo, "")).strip()
    if not v and vacio_ok:
        return None
    try:
        n = int(v)
    except ValueError:
        raise ErrorT("err.entero", campo if campo in ("edad", "fc_max") else None, nombre="@campo." + nombre) from None
    if n <= 0:
        raise ErrorT("err.mayor0", campo if campo in ("edad", "fc_max") else None, nombre="@campo." + nombre)
    return n


def crudo_general(crudo: dict, f) -> dict:
    """Parte «general» de Ajustes: perfil, actividades, cuerpo. No toca nada de la corrida (eso es «Ajustar mi plan»)."""
    nuevo = copy.deepcopy(crudo)
    perfil, act = (nuevo.setdefault(k, {}) for k in ("perfil", "actividades"))
    zona = str(f.get("zona", "")).strip()
    try:
        ZoneInfo(zona)
    except Exception:
        raise ErrorT("err.zona", "zona", zona=zona) from None
    perfil["titulo"] = (str(f.get("titulo", "")).strip() or "Mi entreno")[:60]
    perfil["zona_horaria"] = zona
    # el sensor ya no se pide: se detecta por actividad (banda o muñeca); el valor guardado queda de respaldo
    sensor = f.get("sensor") or perfil.get("sensor") or "banda"
    if sensor not in SENSORES:
        raise ErrorT("err.sensor", "sensor")
    perfil["sensor"] = sensor
    # las categorías de actividad ya no se eligen (se usan todas); las propias de configs viejas se conservan tal cual
    nuevo["inbody"] = f.get("inbody") == "on"
    return nuevo


def diferencias(viejo: dict, nuevo: dict) -> list[str]:  # etiquetas en español (para el historial y el MCP)
    a, b = normalizar_config(viejo), normalizar_config(nuevo)
    return [ETIQUETAS[k] for k in ETIQUETAS if a.get(k) != b.get(k)]


def contexto_ajustes(db, atleta: Usuario, usuario: Usuario, crudo: dict, valores: dict | None = None, **extra) -> dict:
    return {"atleta": atleta, "pref": prefijo(usuario, atleta), "v": valores or valores_form(crudo, atleta), "zonas":
            sorted(set(ZONAS) | {(crudo.get("perfil") or {}).get("zona_horaria", "America/Merida")}),
            "sensores": SENSORES, "errores": {}, "error": None, **extra}


def campo_del_error(mensaje: str):
    return next((c for frag, c in ERROR_CAMPO if frag in mensaje), None)


def hace_texto(t, desde) -> str:
    seg = max(0, int((ahora() - desde).total_seconds()))
    if seg < 90:
        return t("sitio.hace_momento")
    if seg < 3600 * 2:
        return t("sitio.hace_min", n=seg // 60)
    if seg < 86400 * 2:
        return t("sitio.hace_h", n=seg // 3600)
    return t("sitio.hace_d", n=seg // 86400)


def desconectar_garmin(db: Session, u: Usuario) -> None:
    """Suelta la conexión con la copia de GitHub (repo, instalación, historial pendiente). Los datos se quedan. No hace commit."""
    antes = {"repo": u.repo, "repo_id": u.repo_id, "gh_instalacion": u.gh_instalacion}
    u.repo = u.repo_id = u.gh_instalacion = None
    u.historial_pendiente = False
    db.add(Cambio(atleta_id=u.id, autor_id=None, via="sistema", visto=True, descripcion="Garmin desconectado",
                  antes=antes, despues={"repo": None, "repo_id": None}))


def contexto_garmin(db: Session, u: Usuario, t, settings) -> dict:
    """Estado de la sección «Garmin» de Ajustes: sin_conectar | con_app | sin_app."""
    ultima = db.scalar(select(func.max(Subida.fecha)).where(Subida.usuario_id == u.id, Subida.ok.is_(True)))
    app = bool(settings.app_github)
    if not u.repo_id:
        estado = "sin_conectar"
    elif u.gh_instalacion and app:
        estado = "con_app"
    else:
        estado = "sin_app" if app else "solo_estado"
    return {"estado": estado, "repo": u.repo, "ultima": hace_texto(t, ultima) if ultima else None}


def montar(app, get_db, actual, render, formulario, settings) -> None:
    # ---------- ajustes ----------
    def pantalla_ajustes(request, usuario, db, atleta_id, **extra):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = crudo_de(db, atleta)
        if crudo is None:
            return render(request, "ajustes_sin_plan.html", atleta=atleta, pref=prefijo(usuario, atleta),
                          **garmin_extra(request, db, usuario, atleta))
        return render(request, "ajustes.html", **contexto_ajustes(db, atleta, usuario, crudo, ok=request.query_params.get("ok"),
                      **garmin_extra(request, db, usuario, atleta), **extra))

    def garmin_extra(request, db, usuario, atleta) -> dict:
        if atleta.id != usuario.id:   # un coach viendo a su atleta no ve ni toca su conexión
            return {}
        return {"garmin": contexto_garmin(db, atleta, request.state.t, settings),
                "garmin_aviso": request.query_params.get("garmin")}

    @app.get("/ajustes")
    def ajustes_get(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_ajustes(request, usuario, db, None)

    @app.get("/a/{atleta_id}/ajustes")
    def ajustes_get_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_ajustes(request, usuario, db, atleta_id)

    @app.post("/ajustes/garmin/desconectar")
    async def ajustes_garmin_desconectar(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """«Sí, desconectar»: solo la propia persona. Los datos se quedan; se pierde el vínculo con la copia y la app."""
        await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if usuario.repo_id or usuario.gh_instalacion:
            desconectar_garmin(db, usuario)
            db.commit()
        return RedirectResponse("/ajustes?garmin=desconectado", 303)

    @app.post("/ajustes/compartir")
    async def ajustes_compartir(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """Los dos interruptores sociales (actividades y plan). Solo la propia persona: un coach no los cambia."""
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        usuario.compartir_actividades = form.get("compartir_actividades") == "1"
        usuario.compartir_plan = form.get("compartir_plan") == "1"
        db.commit()
        return RedirectResponse("/ajustes?ok=1", 303)

    @app.post("/ajustes/plan")
    async def ajustes_plan(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """«Quiero un plan de running» (lleva a /plan/nuevo) o «Quitar mi plan» (sin_plan=True;
        el plan guardado se queda). Solo la propia persona."""
        form = await formulario(request)
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        if form.get("accion") == "quitar":
            usuario.sin_plan = True
            db.commit()
            return RedirectResponse("/", 303)
        return RedirectResponse("/plan/nuevo", 303)   # el plan se arma ahí; sin_plan pasa a False al confirmar

    async def guardar_ajustes(request: Request, usuario, db, atleta_id):
        """Guardar los ajustes generales: nunca rehace el plan ni pide confirmación."""
        form = await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        pref = prefijo(usuario, atleta)
        valores = {k: form.get(k, "") for k in form.keys()}
        for k in ("inbody",):
            valores[k] = form.get(k) == "on"
        try:
            nuevo = crudo_general(crudo, form)
            cambios_txt = diferencias(crudo, nuevo)
            if not cambios_txt:
                return RedirectResponse(f"{pref}/ajustes?ok=sin", 303)
        except (ConfigError, ValueError) as ex:
            msg = texto(ex, request.state.t)
            campo = ex.campo if hasattr(ex, "clave") else campo_del_error(str(ex))
            extra = {"errores": {campo: msg}} if campo else {"error": msg}
            return render(request, "ajustes.html", status=400, **contexto_ajustes(db, atleta, usuario, crudo, {**valores_form(crudo, atleta), **valores}, **extra))
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), "Ajustes: cambió " + ", ".join(cambios_txt), {"ajustes": nuevo})
        if (nuevo.get("perfil") or {}).get("sensor") in SENSORES and atleta.sensor != nuevo["perfil"]["sensor"]:
            atleta.sensor = nuevo["perfil"]["sensor"]   # copia de consulta rápida; la verdad está en los ajustes
            db.commit()
        return RedirectResponse(f"{pref}/ajustes?ok=1", 303)

    @app.post("/ajustes")
    async def ajustes_post(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        return await guardar_ajustes(request, usuario, db, None)

    @app.post("/a/{atleta_id}/ajustes")
    async def ajustes_post_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return await guardar_ajustes(request, usuario, db, atleta_id)

    # ---------- historial ----------
    def fila_historial(db, c, tz):
        return {"c": c, "quien": cambios.autor_texto(db, c), "cuando": c.fecha.replace(tzinfo=ZoneInfo("UTC")).astimezone(tz).strftime("%d/%m/%Y %H:%M"),
                "puede": cambios.puede_deshacer(c), "via": c.via}

    def pantalla_historial(request, usuario, db, atleta_id, **extra):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = crudo_de(db, atleta) or {}
        tz = ZoneInfo((crudo.get("perfil") or {}).get("zona_horaria") or "America/Merida")
        filas = [fila_historial(db, c, tz) for c in cambios.historial(db, atleta.id)]
        return render(request, "historial.html", atleta=atleta, pref=prefijo(usuario, atleta), filas=filas,
                      hay_nuevos=any(not f["c"].visto for f in filas), **extra)

    @app.get("/historial")
    def historial_get(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_historial(request, usuario, db, None, ok=request.query_params.get("ok"))

    @app.get("/a/{atleta_id}/historial")
    def historial_get_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_historial(request, usuario, db, atleta_id, ok=request.query_params.get("ok"))

    async def historial_accion(request: Request, usuario, db, atleta_id, accion: str, cambio_id: int | None = None):
        await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        pref = prefijo(usuario, atleta)
        if accion == "visto":
            if usuario.id == atleta.id:   # el coach no consume los avisos del atleta
                cambios.marcar_vistos(db, atleta.id)
            return RedirectResponse(f"{pref}/historial?ok=visto", 303)
        try:
            cambios.deshacer(db, usuario, cambio_id)
        except cambios.SinPermiso:
            raise HTTPException(404) from None
        except cambios.NoSeDeshace as ex:
            return pantalla_historial(request, usuario, db, atleta_id, error=texto(ex, request.state.t))
        return RedirectResponse(f"{pref}/historial?ok=deshecho", 303)

    @app.post("/historial/visto")
    async def historial_visto(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        return await historial_accion(request, usuario, db, None, "visto")

    @app.post("/historial/{cambio_id}/deshacer")
    async def historial_deshacer(request: Request, cambio_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return await historial_accion(request, usuario, db, None, "deshacer", cambio_id)

    @app.post("/a/{atleta_id}/historial/visto")
    async def historial_visto_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return await historial_accion(request, usuario, db, atleta_id, "visto")

    @app.post("/a/{atleta_id}/historial/{cambio_id}/deshacer")
    async def historial_deshacer_atleta(request: Request, atleta_id: int, cambio_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return await historial_accion(request, usuario, db, atleta_id, "deshacer", cambio_id)

    # ---------- InBody ----------
    montar_cuerpo(app, get_db, actual, render, formulario)


CAMPOS_CUERPO = [("peso_kg", "Peso (kg)", True, 20, 400), ("pgc", "Grasa corporal (%)", False, 1, 70),
                 ("mme_kg", "Masa muscular esquelética (kg)", False, 5, 120), ("masa_grasa_kg", "Masa grasa (kg)", False, 1, 250),
                 ("grasa_visceral", "Grasa visceral (nivel)", False, 0, 40), ("puntuacion", "Puntuación InBody", False, 0, 100),
                 ("altura_cm", "Estatura (cm)", False, 100, 250), ("imc", "IMC", False, 8, 70)]


def medicion_desde_form(f, previa: dict | None = None) -> dict:
    """Medición nueva = la previa (si se edita; conserva lo que el formulario no maneja, como la hoja) + lo escrito."""
    fecha = str(f.get("fecha", "")).strip()
    try:
        d = date.fromisoformat(fecha)
    except ValueError:
        raise ErrorT("err.fecha") from None
    if d > date.today() + timedelta(days=366):
        raise ErrorT("err.fecha_futuro")
    med = dict(previa or {})
    med["fecha"] = fecha
    for clave, nombre, obligatorio, lo, hi in CAMPOS_CUERPO:
        v = str(f.get(clave, "")).strip().replace(",", ".")
        if not v:
            if obligatorio:
                raise ErrorT("err.obligatorio", nombre="@cm." + clave)
            med.pop(clave, None)
            continue
        try:
            n = float(v)
        except ValueError:
            raise ErrorT("err.numero", nombre="@cm." + clave) from None
        if not lo <= n <= hi:
            raise ErrorT("err.rango", nombre="@cm." + clave, lo=lo, hi=hi)
        med[clave] = int(n) if clave in ("grasa_visceral", "puntuacion", "altura_cm") and n == int(n) else n
    hora = str(f.get("hora", "")).strip()
    if hora:
        med["hora"] = hora[:5]
    else:
        med.pop("hora", None)
    return med


def montar_cuerpo(app, get_db, actual, render, formulario) -> None:
    def cargar(db, atleta):
        return cambios.instantanea(db, atleta.id, ("inbody",))["inbody"]

    def ctx(db, usuario, atleta, **extra):
        crudo = crudo_de(db, atleta) or {}
        return {"atleta": atleta, "pref": prefijo(usuario, atleta), "campos": CAMPOS_CUERPO,
                "inbody_activo": (crudo.get("inbody", True)), **extra}

    def lista(request, usuario, db, atleta_id):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        meds = sorted(cargar(db, atleta), key=lambda x: x["fecha"], reverse=True)
        completas = lambda x: all(x.get(k) is not None for k in ("peso_kg", "mme_kg", "pgc"))  # noqa: E731
        return render(request, "cuerpo.html", meds=meds, completas=completas, ok=request.query_params.get("ok"),
                      **ctx(db, usuario, atleta))

    def formulario_get(request, usuario, db, atleta_id, fecha=None):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        med = None
        if fecha:
            med = next((x for x in cargar(db, atleta) if x["fecha"] == fecha), None)
            if med is None:
                raise HTTPException(404)
        return render(request, "cuerpo_form.html", med=med or {"fecha": date.today().isoformat()}, editando=bool(fecha), orig=fecha,
                      error=None, **ctx(db, usuario, atleta))

    async def guardar(request, usuario, db, atleta_id, fecha=None):
        form = await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        meds = cargar(db, atleta)
        previa = next((x for x in meds if x["fecha"] == fecha), None) if fecha else None
        if fecha and previa is None:
            raise HTTPException(404)
        try:
            med = medicion_desde_form(form, previa)
            if med["fecha"] != fecha and any(x["fecha"] == med["fecha"] for x in meds):
                raise ErrorT("err.fecha_dup")
        except ConfigError as ex:
            return render(request, "cuerpo_form.html", status=400, med=dict(form.items()), editando=bool(fecha), orig=fecha, error=texto(ex, request.state.t),
                          **ctx(db, usuario, atleta))
        nuevas = [x for x in meds if x["fecha"] != fecha] + [med]
        nuevas.sort(key=lambda x: x["fecha"])
        verbo = "Editó" if fecha else "Agregó"
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta),
                               f"{verbo} la medición InBody del {med['fecha']} (peso {med['peso_kg']} kg)", {"inbody": nuevas})
        return RedirectResponse(f"{prefijo(usuario, atleta)}/cuerpo?ok=1", 303)

    async def borrar(request, usuario, db, atleta_id, fecha):
        await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        meds = cargar(db, atleta)
        if not any(x["fecha"] == fecha for x in meds):
            raise HTTPException(404)
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta),
                               f"Borró la medición InBody del {fecha}", {"inbody": [x for x in meds if x["fecha"] != fecha]})
        return RedirectResponse(f"{prefijo(usuario, atleta)}/cuerpo?ok=borrada", 303)

    for base, param in (("", None), ("/a/{atleta_id}", "atleta_id")):
        def rutas(base=base):
            @app.get(f"{base}/cuerpo")
            def _lista(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return lista(request, usuario, db, atleta_id)

            @app.get(f"{base}/cuerpo/nuevo")
            def _nuevo(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return formulario_get(request, usuario, db, atleta_id)

            @app.post(f"{base}/cuerpo/nuevo")
            async def _nuevo_post(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await guardar(request, usuario, db, atleta_id)

            @app.get(base + "/cuerpo/{fecha}/editar")
            def _editar(request: Request, fecha: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return formulario_get(request, usuario, db, atleta_id, fecha)

            @app.post(base + "/cuerpo/{fecha}/editar")
            async def _editar_post(request: Request, fecha: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await guardar(request, usuario, db, atleta_id, fecha)

            @app.post(base + "/cuerpo/{fecha}/borrar")
            async def _borrar(request: Request, fecha: str, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
                return await borrar(request, usuario, db, atleta_id, fecha)
        rutas()
