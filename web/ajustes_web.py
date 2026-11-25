"""Páginas de edición: /ajustes (lo que hacía /ajustar), /historial (con deshacer) y /cuerpo (InBody).
Cada ruta existe para uno mismo (`/ajustes`) y para el atleta de un coach (`/a/<id>/ajustes`); `resolver` decide con
`puede_editar` y responde 404 si no hay acceso (no confirma que exista)."""
import copy
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ajustes import (CALIDAD_TIPOS, ESCALERA, INTENSIDADES, NIVELES, SENSORES, ConfigError, categorias_por_defecto,
                     normalizar_config)

from . import cambios, plan_vivo
from .modelos import Ajustes, Plan, Usuario
from .onboarding import DIAS, ZONAS
from .permisos import puede_editar

ETIQUETAS = {"titulo": "el título", "timezone": "la zona horaria", "edad": "la edad", "max_hr": "la FC máxima",
             "sensor": "el sensor", "nivel": "el nivel", "intensidad": "la intensidad", "calidad_tipos": "los tipos de calidad",
             "caminatas": "las caminatas", "variada": "la corrida variada", "plan_semanas": "las semanas del plan",
             "plan_start": "la fecha de inicio", "base_min": "los minutos base", "semanas_repetidas": "las semanas repetidas",
             "carreras": "las carreras", "categorias": "las actividades", "dias_pierna": "los días de pierna",
             "inbody": "InBody", "escalon": "el escalón de trote/caminata"}
# Dónde mostrar un error de `normalizar_config`: (fragmento del mensaje, campo del formulario)
ERROR_CAMPO = [("corrida.inicio", "inicio"), ("lunes", "inicio"), ("zona", "zona"), ("fc_max", "fc_max"), ("edad", "edad"),
               ("nivel", "nivel"), ("calidad", "calidad"), ("intensidad", "intensidad"), ("semanas_repetidas", "repetidas"),
               ("corrida.carreras", "carreras"), ("categor", "cats"), ("sensor", "sensor"), ("escalon", "escalon")]


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
    perfil, corrida = crudo.get("perfil") or {}, crudo.get("corrida") or {}
    act = crudo.get("actividades") or {}
    cfg = normalizar_config({**crudo, "perfil": {**perfil, "sensor": perfil.get("sensor") or atleta.sensor or "banda"}})
    return {"titulo": perfil.get("titulo", "Mi entreno"), "zona": perfil.get("zona_horaria", "America/Merida"),
            "edad": perfil.get("edad") or "", "fc_max": perfil.get("fc_max") or "", "sensor": cfg["sensor"],
            "nivel": cfg["nivel"], "intensidad": cfg["intensidad"], "calidad": cfg["calidad_tipos"],
            "caminatas": cfg["caminatas"], "variada": cfg["variada"], "semanas": cfg["plan_semanas"],
            "inicio": cfg["plan_start"], "z2": cfg["base_min"]["z2"], "larga": cfg["base_min"]["larga"],
            "repetidas": ", ".join(str(n) for n in cfg["semanas_repetidas"]), "escalon": cfg["escalon"] or "",
            "carreras": ", ".join(corrida.get("carreras") or []), "cats": [c["id"] for c in cfg["categorias"]],
            "pierna": [clave for i, (clave, _) in enumerate(DIAS) if i in cfg["dias_pierna"]],
            "inbody": cfg["inbody"]}


def _entero(f, campo: str, nombre: str, vacio_ok: bool = False):
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


def crudo_desde_form(crudo: dict, f) -> dict:
    """Crudo nuevo = el actual con lo que cambió el formulario (lo que el formulario no maneja se conserva)."""
    nuevo = copy.deepcopy(crudo)
    perfil, corrida, act = (nuevo.setdefault(k, {}) for k in ("perfil", "corrida", "actividades"))
    zona = str(f.get("zona", "")).strip()
    try:
        ZoneInfo(zona)
    except Exception:
        raise ConfigError(f"zona horaria: '{zona}' no es una zona válida") from None
    perfil["titulo"] = (str(f.get("titulo", "")).strip() or "Mi entreno")[:60]
    perfil["zona_horaria"] = zona
    for campo, clave, nombre in (("edad", "edad", "edad"), ("fc_max", "fc_max", "fc_max")):
        v = _entero(f, campo, nombre, vacio_ok=True)
        if v is None:
            perfil.pop(clave, None)
        else:
            perfil[clave] = v
    sensor = f.get("sensor", "banda")
    if sensor not in SENSORES:
        raise ConfigError("sensor: elige banda o muñeca")
    perfil["sensor"] = sensor
    corrida["nivel"], corrida["intensidad"] = f.get("nivel", ""), f.get("intensidad", "")
    corrida["calidad_tipos"] = [t for t in f.getlist("calidad") if t in CALIDAD_TIPOS] if corrida["intensidad"] == "calidad" else []
    corrida["caminatas"], corrida["variada"] = f.get("caminatas") == "on", f.get("variada") == "on"
    corrida["semanas"] = _entero(f, "semanas", "semanas del plan")
    if not 4 <= corrida["semanas"] <= 52:
        raise ConfigError("semanas del plan: entre 4 y 52")
    corrida["inicio"] = str(f.get("inicio", "")).strip()
    corrida["base_min"] = {**(corrida.get("base_min") or {}), "z2": _entero(f, "z2", "minutos de la Z2"),
                           "larga": _entero(f, "larga", "minutos de la larga")}
    esc = str(f.get("escalon", "")).strip()
    if esc:
        corrida["escalon"] = esc
    else:
        corrida.pop("escalon", None)
    try:
        corrida["semanas_repetidas"] = [int(x) for x in str(f.get("repetidas", "")).replace(",", " ").split()]
    except ValueError:
        raise ConfigError("semanas_repetidas: escribe números de semana separados por comas") from None
    corrida["carreras"] = [x for x in str(f.get("carreras", "")).replace(",", " ").split()]
    # actividades: categorías elegidas (conserva las personalizadas que ya había) y días de pierna
    elegidas = f.getlist("cats")
    previas = {c["id"]: c for c in (act.get("categorias") or [])}
    defecto = {c["id"]: c for c in categorias_por_defecto()}
    if not elegidas:
        raise ConfigError("categorías: marca al menos una (si no haces otra actividad deja Fuerza)")
    cats = [previas.get(i) or defecto[i] for i in elegidas if i in previas or i in defecto]
    if "categorias" in act or {c["id"] for c in cats} != set(defecto):
        act["categorias"] = cats
    act["dias_pierna"] = [d for d in f.getlist("pierna") if d in dict(DIAS)]
    nuevo["inbody"] = f.get("inbody") == "on"
    return nuevo


def diferencias(viejo: dict, nuevo: dict) -> list[str]:
    a, b = normalizar_config(viejo), normalizar_config(nuevo)
    return [ETIQUETAS[k] for k in ETIQUETAS if a.get(k) != b.get(k)]


def contexto_ajustes(db, atleta: Usuario, usuario: Usuario, crudo: dict, valores: dict | None = None, **extra) -> dict:
    cats = {c["id"]: c for c in categorias_por_defecto()}
    for c in (crudo.get("actividades") or {}).get("categorias") or []:
        cats.setdefault(c["id"], c)
    return {"atleta": atleta, "pref": prefijo(usuario, atleta), "v": valores or valores_form(crudo, atleta), "zonas":
            sorted(set(ZONAS) | {(crudo.get("perfil") or {}).get("zona_horaria", "America/Merida")}),
            "niveles": NIVELES, "intensidades": INTENSIDADES, "tipos_calidad": CALIDAD_TIPOS, "escalera": ESCALERA,
            "categorias": list(cats.values()), "dias": DIAS, "sensores": SENSORES, "errores": {}, "error": None, **extra}


def campo_del_error(mensaje: str):
    return next((c for frag, c in ERROR_CAMPO if frag in mensaje), None)


def montar(app, get_db, actual, render, formulario, settings) -> None:
    # ---------- ajustes ----------
    def pantalla_ajustes(request, usuario, db, atleta_id, **extra):
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        return render(request, "ajustes.html", **contexto_ajustes(db, atleta, usuario, crudo, ok=request.query_params.get("ok"), **extra))

    @app.get("/ajustes")
    def ajustes_get(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_ajustes(request, usuario, db, None)

    @app.get("/a/{atleta_id}/ajustes")
    def ajustes_get_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
        return pantalla_ajustes(request, usuario, db, atleta_id)

    async def guardar_ajustes(request: Request, usuario, db, atleta_id):
        form = await formulario(request)
        atleta, redir = resolver(db, usuario, atleta_id)
        if redir:
            return redir
        crudo = crudo_de(db, atleta)
        if crudo is None:
            return RedirectResponse("/bienvenida", 303)
        pref = prefijo(usuario, atleta)
        hoy = hoy_de(app.state.reloj, crudo)
        valores = {k: (form.getlist(k) if k in ("calidad", "cats", "pierna") else form.get(k, "")) for k in form.keys()}
        for k in ("caminatas", "variada", "inbody"):
            valores[k] = form.get(k) == "on"
        try:
            nuevo = crudo_desde_form(crudo, form)
            cfg_viejo, cfg_nuevo = normalizar_config(crudo), normalizar_config(nuevo)
            cambios_txt = diferencias(crudo, nuevo)
            if not cambios_txt:
                return RedirectResponse(f"{pref}/ajustes?ok=sin", 303)
            nuevo_plan, desde = None, None
            if plan_vivo.cambia_plan(cfg_viejo, cfg_nuevo):
                nuevo_plan, desde = plan_vivo.construir_plan(nuevo, plan_guardado(db, atleta), hoy)
        except (ConfigError, ValueError) as ex:
            msg = str(ex)
            campo = campo_del_error(msg)
            extra = {"errores": {campo: msg}} if campo else {"error": msg}
            return render(request, "ajustes.html", status=400, **contexto_ajustes(db, atleta, usuario, crudo, valores, **extra))
        if nuevo_plan is not None and form.get("confirmo") != "1":
            frase = ("rehace tu plan completo desde la semana 1" if desde == 1 else
                     f"rehace tu plan desde la semana {desde}; las semanas ya pasadas no cambian")
            return render(request, "ajustes_confirmar.html", atleta=atleta, pref=pref, frase=frase, cambios=cambios_txt,
                          pares=[(k, v) for k, v in form.multi_items() if k not in ("csrf", "confirmo")])
        desc = "Ajustes: cambió " + ", ".join(cambios_txt) + (f"; plan rehecho desde la semana {desde}" if nuevo_plan else "")
        paquete = {"ajustes": nuevo, **({"plan": nuevo_plan} if nuevo_plan else {})}
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), desc, paquete)
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
            cambios.marcar_vistos(db, atleta.id)
            return RedirectResponse(f"{pref}/historial?ok=visto", 303)
        try:
            cambios.deshacer(db, usuario, cambio_id)
        except cambios.SinPermiso:
            raise HTTPException(404) from None
        except cambios.NoSeDeshace as ex:
            return pantalla_historial(request, usuario, db, atleta_id, error=str(ex))
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
        raise ConfigError("fecha: escribe una fecha válida") from None
    if d > date.today() + timedelta(days=366):
        raise ConfigError("fecha: no puede ser tan en el futuro")
    med = dict(previa or {})
    med["fecha"] = fecha
    for clave, nombre, obligatorio, lo, hi in CAMPOS_CUERPO:
        v = str(f.get(clave, "")).strip().replace(",", ".")
        if not v:
            if obligatorio:
                raise ConfigError(f"{nombre}: es obligatorio")
            med.pop(clave, None)
            continue
        try:
            n = float(v)
        except ValueError:
            raise ConfigError(f"{nombre}: escribe un número") from None
        if not lo <= n <= hi:
            raise ConfigError(f"{nombre}: debe estar entre {lo} y {hi}")
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
                raise ConfigError("fecha: ya hay una medición de ese día; edítala desde la lista")
        except ConfigError as ex:
            return render(request, "cuerpo_form.html", status=400, med=dict(form.items()), editando=bool(fecha), orig=fecha, error=str(ex),
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
