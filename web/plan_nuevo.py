"""«Quiero un plan» (Motor v6, F4): páginas guiadas /plan/nuevo (y /a/<id>/plan/nuevo para el coach).
Paso 1 «Lo que vimos en tu Garmin» + nivel; paso 2 preguntas según el nivel; paso 3 vista previa; Confirmar guarda el plan.
Todo se decide en Python (qué preguntas, validación, plan); las plantillas solo pintan. Las respuestas viajan en campos ocultos
y al confirmar el plan se vuelve a generar (es determinista), así que lo que se guarda es lo que se vio.
Cada ruta pasa por `ajustes_web.resolver` (`puede_editar`; 404 si no hay acceso) y todo POST lleva CSRF (`formulario`)."""
import copy
import re
import secrets
from datetime import date, timedelta

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

import i18n
import motor_v6
import plan_i18n
from ajustes import ConfigError, crudo_desde_respuestas, normalizar_config
from nivel import NIVELES as NIVELES_V6, nivel_desde_datos

from . import ajustes_web as aw
from . import cambios, datos
from .errores import ErrorT, texto
from .onboarding import DIAS, ZONAS, proximo_lunes

DISTANCIAS = (5, 10, 21, 42)
MAX_SEMANAS_CARRERA = 52          # la config del plan acepta de 4 a 52 semanas
MIN_SEMANAS_CARRERA = 1           # una carrera a menos de 4 semanas se permite con aviso (motor_v6: `carrera_semanas_cortas`)
OBJETIVOS = {"empezando": (), "base": ("mas_tiempo", "carrera"), "corredor": ("base", "velocidad", "carrera")}
RE_TIEMPO = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
AVISOS_CON_TEXTO = ("dias_limitados", "carrera_no_recomendada", "carrera_poco_tiempo", "carrera_cerca", "pausa")
PORQUES_CON_TEXTO = ("inicio", "sube", "descarga", "calidad_si", "calidad_no", "escalera", "carrera")
# TODO(F4+): «1 o 2 sesiones de calidad» (2 solo con >= 4 días y < 3 días intensos). Hoy motor_v6.verificar permite a lo más una
# sesión con Z3+ por semana, así que por ahora solo se ofrece 1 y no se pregunta.


def lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ───────────────────────────── lógica pura ─────────────────────────────

def campos_de(nivel: str, tiene_ajustes: bool) -> list[str]:
    """Qué preguntas se hacen (y se pintan) en el paso 2 de ese nivel. Lo que no está aquí no existe en la página."""
    campos = ["dias", "pierna", "dolor"]
    if nivel in ("base", "corredor"):
        campos += ["objetivo", "carrera"]
    if nivel == "corredor":
        campos += ["tiempo"]
    campos += ["inicio", "edad"]
    if not tiene_ajustes:
        campos += ["zona", "fc_max"]
    return campos


def valores_iniciales(nivel: str, ev: dict, crudo: dict | None, hoy: date) -> dict:
    perfil = (crudo or {}).get("perfil") or {}
    return {"nivel": nivel, "dias": "3", "pierna": [DIAS[d][0] for d in ev.get("dias_intensos", [])], "dolor": "no",
            "objetivo": OBJETIVOS[nivel][0] if OBJETIVOS[nivel] else "", "km": "10", "fecha": "", "tiempo": "",
            "inicio": proximo_lunes(hoy).isoformat(), "edad": str(perfil.get("edad") or ""), "zona": perfil.get("zona_horaria") or "America/Merida",
            "fc_max": str(perfil.get("fc_max") or "")}


def _entero(v, campo: str, lo: int, hi: int, clave: str = "err.pn_rango") -> int:
    try:
        n = int(str(v).strip())
    except ValueError:
        raise ErrorT(clave, campo, lo=lo, hi=hi) from None
    if not lo <= n <= hi:
        raise ErrorT(clave, campo, lo=lo, hi=hi)
    return n


def _fecha(v, campo: str) -> date:
    try:
        return date.fromisoformat(str(v).strip())
    except ValueError:
        raise ErrorT("err.pn_fecha", campo) from None


def leer_respuestas(form, nivel: str, campos: list[str], hoy: date) -> dict:
    """Respuestas validadas (ErrorT con el campo si algo no vale). Solo se leen los `campos` del nivel."""
    v = {"nivel": nivel}
    v["dias"] = str(_entero(form.get("dias", "3"), "dias", 2, 5))
    v["pierna"] = [d for d in form.getlist("pierna") if d in dict(DIAS)]
    v["dolor"] = "si" if form.get("dolor") == "si" else "no"
    objetivo = str(form.get("objetivo", "")).strip()
    v["objetivo"] = objetivo if objetivo in OBJETIVOS[nivel] else (OBJETIVOS[nivel][0] if OBJETIVOS[nivel] else "")
    v["km"], v["fecha"] = str(form.get("km", "10")), str(form.get("fecha", "")).strip()
    v["tiempo"] = str(form.get("tiempo", "")).strip()
    v["inicio"] = str(form.get("inicio", "")).strip()
    v["edad"], v["zona"], v["fc_max"] = (str(form.get(k, "")).strip() for k in ("edad", "zona", "fc_max"))
    d_inicio = _fecha(v["inicio"], "inicio")
    if lunes(d_inicio) < lunes(hoy):
        raise ErrorT("err.pn_inicio_pasado", "inicio")
    if "carrera" in campos and v["objetivo"] == "carrera":
        if int(v["km"] or 0) not in DISTANCIAS:
            raise ErrorT("err.pn_distancia", "km")
        d_carrera = _fecha(v["fecha"], "fecha")
        semanas = (d_carrera - lunes(d_inicio)).days // 7 + 1
        if semanas < MIN_SEMANAS_CARRERA:
            raise ErrorT("err.pn_carrera_cerca", "fecha", n=MIN_SEMANAS_CARRERA)
        if semanas > MAX_SEMANAS_CARRERA:
            raise ErrorT("err.pn_carrera_lejos", "fecha", n=MAX_SEMANAS_CARRERA)
    if "tiempo" in campos and v["tiempo"] and not RE_TIEMPO.match(v["tiempo"]):
        raise ErrorT("err.pn_tiempo", "tiempo")
    if v["edad"]:
        _entero(v["edad"], "edad", 10, 99)
    if v["fc_max"]:
        _entero(v["fc_max"], "fc_max", 120, 230)
    if "edad" in campos and "zona" in campos and not v["edad"] and not v["fc_max"]:
        raise ErrorT("err.edad_o_fc", "edad")
    return v


def entrada_v6(v: dict, nivel: str, ev: dict, inicio_minutos: int) -> dict:
    """La entrada de `motor_v6.generar_v6`. El nivel elegido cambia la estructura y la calidad, nunca el volumen inicial
    (`inicio_minutos` sale siempre de los datos)."""
    quiere_carrera = v.get("objetivo") == "carrera" and nivel in ("base", "corredor")
    if quiere_carrera:
        meta = {"km": int(v["km"]), "fecha": v["fecha"]}
    elif nivel == "corredor" and v.get("objetivo") == "velocidad":
        meta = "velocidad"
    else:
        meta = "base"
    return {"nivel": nivel, "dias": int(v["dias"]), "dias_intensos": [i for i, (k, _) in enumerate(DIAS) if k in v["pierna"]],
            "meta": meta, "inicio": lunes(date.fromisoformat(v["inicio"])).isoformat(), "evidencia": ev,
            "inicio_minutos": inicio_minutos, "edad": int(v["edad"]) if v["edad"] else 35}


def armar_plan(v: dict, nivel: str, calculado: dict) -> dict:
    """Plan v6 con lo que la vista previa y el historial necesitan en `meta` (dolor, nivel calculado, tiempo de carrera)."""
    try:
        plan = motor_v6.generar_v6(entrada_v6(v, nivel, calculado["evidencia"], calculado["inicio_minutos"]))
    except (ValueError, AssertionError) as ex:
        raise ErrorT("err.pn_generar", None, detalle=str(ex) or "—") from None
    plan["meta"]["nivel_calculado"] = calculado["nivel"]
    plan["meta"]["dolor"] = v["dolor"] == "si"
    if v.get("tiempo"):
        plan["meta"]["tiempo_carrera"] = v["tiempo"]   # guardado; el motor aún no lo usa
    return plan


def crudo_nuevo(crudo: dict | None, plan: dict, v: dict, sensor: str | None) -> dict:
    """Ajustes que acompañan al plan: los de la persona (si ya tiene) con inicio, semanas y días de pierna del plan nuevo,
    o unos nuevos con lo que pidió el formulario. La carrera del plan va a `metas` con `en_plan: true`
    (cuenta regresiva, lista de carreras, grupo «carrera»; `plan_efectivo` no la vuelve a aplicar porque el plan ya trae su taper)."""
    semanas = max(len(plan["weeks"]), 1)
    pierna = list(v["pierna"])
    if crudo is None:
        nuevo = crudo_desde_respuestas(plan["start"], edad=int(v["edad"]) if v["edad"] else None,
                                       fc_max=int(v["fc_max"]) if v["fc_max"] else None, zona=v["zona"] or "America/Merida",
                                       pierna=pierna)
        nuevo["perfil"]["sensor"] = sensor or "banda"
    else:
        nuevo = copy.deepcopy(crudo)
        if v["edad"]:
            nuevo.setdefault("perfil", {})["edad"] = int(v["edad"])
        nuevo.setdefault("actividades", {})["dias_pierna"] = pierna
    nuevo.setdefault("corrida", {}).update({"inicio": plan["start"], "semanas": semanas})
    nuevo["corrida"].pop("semanas_repetidas", None)
    metas = [x for x in nuevo["corrida"].get("metas") or [] if not x.get("en_plan")]
    if plan["meta"].get("carrera"):
        km = plan["meta"]["carrera"]["km"]
        metas.append({"id": secrets.token_hex(4), "tipo": "carrera", "fecha": v["fecha"], "distancia_km": km, "nombre": f"{km}K", "en_plan": True})
    nuevo["corrida"]["metas"] = metas
    normalizar_config(nuevo)   # ConfigError si algo no cuadra: no se guarda nada
    return nuevo


def evidencia_en_palabras(calculado: dict, t) -> list[str]:
    """Las líneas de «Lo que vimos en tu Garmin» en el idioma de `t`."""
    ev = calculado["evidencia"]
    if not ev.get("semanas_activas"):
        return [t("pn.ev.nada")]
    lineas = [t("pn.ev.corridas", n=f"{ev['corridas_sem_4']:g}"), t("pn.ev.minutos", n=f"{ev['minutos_sem_prom']:g}"),
              t("pn.ev.continuo", n=f"{ev['trote_continuo_min']:g}")]
    if ev.get("dias_desde_ultima") is not None:
        lineas.append(t("pn.ev.ultima", n=ev["dias_desde_ultima"]))
    if ev.get("sesion_max_30d"):
        lineas.append(t("pn.ev.larga", n=f"{ev['sesion_max_30d']:g}"))
    if ev.get("intensos_sem"):
        lineas.append(t("pn.ev.intensos", n=f"{ev['intensos_sem']:g}"))
    if ev.get("desentrenamiento"):
        lineas.append(t("pn.ev.pausa"))
    return lineas


def vista_previa(plan: dict, t, idioma: str) -> dict:
    """Lo que pinta el paso 3: barras de minutos por semana, semanas 1 y 2 en detalle, por qué y avisos (en el idioma de la persona)."""
    meta = plan["meta"]
    semanas = [{"n": w["n"], "min": motor_v6.minutos_semana(w), "kind": w["kind"], "evento": w.get("evento", "")} for w in plan["weeks"]]
    tope = max(s["min"] for s in semanas) or 1
    with i18n.usar(idioma):
        detalle = [{"n": w["n"], "sesiones": [{"nombre": plan_i18n.nombre(s["name"]), "min": s["minutes"]}
                                               for s in w["sessions"]]}
                   for w in plan["weeks"][:2]]
    avisos = [t("pn.av." + a["clave"], **{k: val for k, val in a.items() if k not in ("clave", "texto")}) if a["clave"] in AVISOS_CON_TEXTO else a["texto"]
              for a in meta["avisos"]]
    porques = []
    for p in meta["porque"]:
        clave, pr = p["clave"], dict(p["params"])
        if clave not in PORQUES_CON_TEXTO:
            porques.append(p["texto"])
            continue
        if clave == "inicio" and not pr.get("promedio"):
            clave = "inicio_suave"
        if "pct" in pr:
            pr["pct"] = f"{pr['pct']:g}"
        if "promedio" in pr and pr["promedio"]:
            pr["promedio"] = f"{pr['promedio']:g}"
        porques.append(t("pn.por." + clave, **pr))
    return {"semanas": semanas, "tope": tope, "detalle": detalle, "avisos": avisos, "porques": porques, "meta": meta}


# ───────────────────────────── rutas ─────────────────────────────

def montar(app, get_db, actual, render, formulario, settings) -> None:
    def doble(metodo: str, ruta: str, fn) -> None:
        for base in ("", "/a/{atleta_id}"):
            getattr(app, metodo)(base + ruta)(fn)

    def contexto(request, db, usuario, atleta_id):
        """(atleta, contexto base) o (None, respuesta). Calcula el nivel desde las actividades guardadas (barato: se hace por petición)."""
        atleta, redir = aw.resolver(db, usuario, atleta_id)
        if redir:
            return None, redir
        crudo = aw.crudo_de(db, atleta)
        hoy = aw.hoy_de(app.state.reloj, crudo or {})
        base = crudo or {"perfil": {"zona_horaria": "America/Merida", "fc_max": 190}, "corrida": {"inicio": "2026-01-05"}}
        d = datos.leer_archivos(db, atleta.id)
        calculado = nivel_desde_datos(d["activities"], hoy, normalizar_config({**base, "modo": "web"}), d["details"])
        return atleta, {"atleta": atleta, "pref": aw.prefijo(usuario, atleta), "crudo": crudo, "hoy": hoy, "calculado": calculado,
                        "niveles": NIVELES_V6, "dias": DIAS, "zonas": sorted(set(ZONAS)), "evidencia": evidencia_en_palabras(calculado, request.state.t),
                        "opciones_km": [(str(d), request.state.t("pn.km_op", km=d)) for d in DISTANCIAS],
                        "error": None, "errores": {}}

    def elegido(form, calculado) -> str:
        n = form.get("nivel")
        return n if n in NIVELES_V6 else calculado["nivel"]

    def avisos_nivel(nivel, calculado, t) -> list[str]:
        out = []
        if NIVELES_V6.index(nivel) > NIVELES_V6.index(calculado["nivel"]):
            out.append(t("pn.nivel_alto", nivel=t("pn.nivel." + nivel), calculado=t("pn.nivel." + calculado["nivel"])))
        return out

    def pantalla(request, ctx, paso, nivel=None, valores=None, status=200, **extra):
        nivel = nivel or ctx["calculado"]["nivel"]
        campos = campos_de(nivel, ctx["crudo"] is not None)
        v = valores or valores_iniciales(nivel, ctx["calculado"]["evidencia"], ctx["crudo"], ctx["hoy"])
        return render(request, "plan_nuevo.html", status=status, paso=paso, nivel=nivel, campos=campos, v=v,
                      avisos_nivel=avisos_nivel(nivel, ctx["calculado"], request.state.t),
                      objetivos=OBJETIVOS[nivel], **{**ctx, **extra})

    def paso1(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        atleta, ctx = contexto(request, db, usuario, atleta_id)
        if atleta is None:
            return ctx
        return pantalla(request, ctx, 1)
    doble("get", "/plan/nuevo", paso1)

    async def paso2(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        """Paso 2: las preguntas del nivel elegido. Llega desde el paso 1 (solo trae el nivel) o desde «Cambiar respuestas» (trae todo)."""
        form = await formulario(request)
        atleta, ctx = contexto(request, db, usuario, atleta_id)
        if atleta is None:
            return ctx
        nivel = elegido(form, ctx["calculado"])
        v = valores_iniciales(nivel, ctx["calculado"]["evidencia"], ctx["crudo"], ctx["hoy"])
        if "dias" in form:   # vuelve de la vista previa: se conservan sus respuestas
            v.update({k: (form.getlist(k) if k == "pierna" else str(form.get(k, ""))) for k in v if k != "nivel" and (k in form or k == "pierna")})
        return pantalla(request, ctx, 2, nivel, v)
    doble("post", "/plan/nuevo/preguntas", paso2)

    def generar_o_error(request, ctx, form):
        """(nivel, respuestas, plan) o lanza ErrorT/ConfigError."""
        nivel = elegido(form, ctx["calculado"])
        v = leer_respuestas(form, nivel, campos_de(nivel, ctx["crudo"] is not None), ctx["hoy"])
        return nivel, v, armar_plan(v, nivel, ctx["calculado"])

    async def vista(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        """Paso 3: la vista previa. No guarda nada."""
        form = await formulario(request)
        atleta, ctx = contexto(request, db, usuario, atleta_id)
        if atleta is None:
            return ctx
        t = request.state.t
        try:
            nivel, v, plan = generar_o_error(request, ctx, form)
        except ConfigError as ex:
            nivel = elegido(form, ctx["calculado"])
            campo = getattr(ex, "campo", None)
            vals = valores_iniciales(nivel, ctx["calculado"]["evidencia"], ctx["crudo"], ctx["hoy"])
            vals.update({k: (form.getlist(k) if k == "pierna" else str(form.get(k, ""))) for k in vals if k != "nivel" and (k in form or k == "pierna")})
            return pantalla(request, ctx, 2, nivel, vals, status=400, **({"errores": {campo: texto(ex, t)}} if campo else {"error": texto(ex, t)}))
        return pantalla(request, ctx, 3, nivel, v, prev=vista_previa(plan, t, request.state.idioma))
    doble("post", "/plan/nuevo/vista", vista)

    async def confirmar(request: Request, atleta_id: int | None = None, usuario=Depends(actual), db=Depends(get_db)):
        """Guarda el plan como el plan vivo (queda en el historial, se puede deshacer) y manda a la pestaña Plan."""
        form = await formulario(request)
        atleta, ctx = contexto(request, db, usuario, atleta_id)
        if atleta is None:
            return ctx
        t = request.state.t
        try:
            nivel, v, plan = generar_o_error(request, ctx, form)
            ajustes = crudo_nuevo(ctx["crudo"], plan, v, atleta.sensor)
        except ConfigError as ex:
            return pantalla(request, ctx, 2, elegido(form, ctx["calculado"]), None, status=400, error=texto(ex, t))
        meta = plan["meta"]
        desc = (f"Plan nuevo (motor v6): nivel {nivel}, {meta['dias']} días por semana, {len(plan['weeks'])} semanas"
                + (f", carrera de {meta['carrera']['km']} km" if meta.get("carrera") else ""))
        cambios.aplicar_cambio(db, atleta, usuario, cambios.via_de(usuario, atleta), desc, {"ajustes": ajustes, "plan": plan})
        if atleta.sin_plan:
            atleta.sin_plan = False
            db.commit()
        pref = aw.prefijo(usuario, atleta)
        return RedirectResponse(f"{pref}/plan/acciones?ok=nuevo" if pref else "/?ok=plan#plan", 303)
    doble("post", "/plan/nuevo/confirmar", confirmar)
