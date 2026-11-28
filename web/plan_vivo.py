"""Plan vivo: metas (carreras con fecha), eventos (viaje, enfermedad, lesión), escalera de trote/caminata y sesiones
flexibles. Lógica pura (sin base de datos): recibe y devuelve dicts; las rutas y `aplicar_cambio` están en otros módulos.

Dónde vive cada cosa:
- `ajustes.config` (crudo) guarda `corrida.metas`, `corrida.eventos`, `corrida.escalon`, `corrida.semanas_repetidas` y `corrida.saltos` (repetir / retomar).
- `planes.plan` es el plan que sale de `motor_v6` (más lo que la persona edite a mano). NO lleva los eventos:
  `plan_efectivo` los aplica al calcular (así quitar un evento o deshacerlo no deja restos en el plan).
- Una semana de **pausa** (viaje sin correr, enfermedad o lesión) no gasta semana del plan: el plan se reanuda donde iba
  (equivale a repetir la semana). Una semana **ligera** (viaje con correr) o de **carrera** sustituye a la semana n.
"""
import copy
import secrets
from datetime import date, timedelta

from plan import motor_v6
from plan import pasos as ps
from dashboard.metricas import semana as mt_semana
from dashboard.ajustes import normalizar_config
from .errores import ErrorT

TIPOS_EDITABLES = ("z2", "larga", "variada")
ZONAS = ("Z1", "Z2", "Z3", "Z4", "Z5")
MAX_GRUPOS = 4


def lunes(d: date) -> date:
    return d - timedelta(days=d.weekday())


# --- plan generado + semanas ya pasadas ---

def semana_tope(cfg: dict, hoy: date) -> int:
    """Primer número de semana del plan que todavía no pasa: las anteriores no se tocan al regenerar.
    Antes del inicio = 1; después del final = total + 1."""
    inicio = date.fromisoformat(cfg["plan_start"])
    sec = mt_semana.secuencia_de(cfg)
    i = (hoy - inicio).days // 7
    if i < 0:
        return 1
    for n in sec[i:]:
        if n is not None:
            return n
    return cfg["plan_semanas"] + 1


# --- eventos -> pausas y semanas distintas ---

def _fin_evento(e: dict, hoy: date) -> date:
    """Un evento abierto (sin `hasta`) llega hasta hoy."""
    desde = date.fromisoformat(e["desde"])
    return date.fromisoformat(e["hasta"]) if e["hasta"] else max(hoy, desde)


def pausa_el_plan(e: dict) -> bool:
    return e["tipo"] in ("enfermedad", "lesion") or (e["tipo"] == "viaje" and e["modo"] == "pausa")


def semanas_de(e: dict, hoy: date) -> list[date]:
    """Lunes de las semanas que toca el evento."""
    ini, fin = lunes(date.fromisoformat(e["desde"])), lunes(_fin_evento(e, hoy))
    return [ini + timedelta(weeks=i) for i in range((fin - ini).days // 7 + 1)]


def pausas_de(cfg: dict, hoy: date) -> list[str]:
    return sorted({d.isoformat() for e in cfg["eventos"] if pausa_el_plan(e) for d in semanas_de(e, hoy)})


def con_pausas(cfg: dict, hoy: date) -> dict:
    """La config con `pausas` (lunes sin semana del plan) calculadas de los eventos y de hoy."""
    return {**cfg, "pausas": pausas_de(cfg, hoy)}


LETRAS_Z2 = "abcdefgh"


def _z2_cortas(w: dict, cuantas: int) -> list:
    """`cuantas` Z2 cortas: la versión suave de la sesión Z2 de la semana (con trote/camina si ya va por escalones)."""
    base = next((x for x in w["sessions"] if x.get("tipo") == "z2"), w["sessions"][0])["easy"]
    return [{"id": f"z2{LETRAS_Z2[i]}", "tipo": "z2", "name": f"Z2 #{i + 1}", "minutes": base["minutes"],
             "steps": copy.deepcopy(base["steps"]), "easy": copy.deepcopy(base)} for i in range(cuantas)]


def _sesion_carrera(w: dict, meta: dict) -> dict:
    """La semana `w` con su sesión larga (si no hay, la de más minutos) cambiada por la carrera: mismo `id` y tipo `larga`, así las corridas
    de la semana se asignan igual (la más larga que alcance la meta cuenta como la carrera). Con km, los minutos son los de correrlos
    a 5 min/km (nunca más que la sesión que reemplaza); sin versión suave propia (la «suave» es la misma carrera)."""
    ses = w["sessions"]
    reemplazada = next((s for s in ses if s.get("tipo") == "larga"), None) or max(ses, key=lambda s: s["minutes"])
    km = meta.get("distancia_km")
    minutos = min(reemplazada["minutes"], max(5, round(km * 5))) if km else reemplazada["minutes"]
    pasos = [ps.paso(minutos)]
    nueva = {"id": reemplazada["id"], "tipo": "larga", "name": f"Carrera: {meta['nombre']}", "minutes": minutos, "steps": pasos,
             "easy": {"name": "Suave", "minutes": minutos, "steps": copy.deepcopy(pasos)}, "carrera": True,
             **({"km": km} if km else {})}
    return {**w, "sessions": [nueva if s is reemplazada else s for s in ses]}


def plan_efectivo(plan: dict, cfg: dict) -> dict:
    """El plan guardado con los viajes y las carreras de paso aplicados a sus semanas, por fecha y sobre la secuencia ya con saltos y pausas
    (las carreras de un plan v6 ya vienen dentro del plan). `cfg` ya trae `pausas`. El plan guardado no se toca: sin viajes ni carreras de
    paso devuelve el mismo plan (idéntico). Una carrera de paso reemplaza la larga de su semana; si esa semana está en pausa o la fecha cae
    fuera del plan, solo sale como evento."""
    viajes = [e for e in cfg["eventos"] if e["tipo"] == "viaje" and e["modo"] != "pausa"]
    de_paso = [x for x in cfg.get("metas", []) if x.get("de_paso")]
    if not viajes and not de_paso:
        return plan
    inicio = date.fromisoformat(cfg["plan_start"])
    sec = mt_semana.secuencia_de(cfg)
    ligera, igual = set(), set()   # n de semanas de viaje con correr menos / «sigo igual» (solo se marca)
    for e in viajes:
        for d in semanas_de(e, date.fromisoformat(e["hasta"])):
            i = (d - inicio).days // 7
            if 0 <= i < len(sec) and sec[i] is not None:
                (ligera if e["modo"] == "menos" else igual).add(sec[i])
    carreras: dict[int, dict] = {}   # n de semana -> carrera de paso (la primera por fecha)
    for x in de_paso:
        i = (lunes(date.fromisoformat(x["fecha"])) - lunes(inicio)).days // 7
        if 0 <= i < len(sec) and sec[i] is not None:
            carreras.setdefault(sec[i], x)
    semanas = []
    for w in plan["weeks"]:
        if w["n"] in ligera:
            w = {**w, "kind": "descarga", "evento": "viaje", "focus": "Viaje · 2 Z2 cortas", "sessions": _z2_cortas(w, 2)}
        elif w["n"] in igual:
            w = {**w, "evento": "viaje_igual"}
        if w["n"] in carreras and w["sessions"]:
            w = _sesion_carrera(w, carreras[w["n"]])
        semanas.append(w)
    return {**plan, "weeks": semanas}


# --- cambios al crudo de los ajustes (cada uno devuelve un crudo nuevo ya validado) ---

def _corrida(crudo: dict) -> tuple[dict, dict]:
    nuevo = copy.deepcopy(crudo)
    nuevo["corrida"] = nuevo.get("corrida") or {}
    return nuevo, nuevo["corrida"]


def _validado(crudo: dict) -> dict:
    normalizar_config(crudo)   # ConfigError con mensaje en español si algo no vale
    return crudo


def _id_nuevo() -> str:
    return secrets.token_hex(4)


def agregar_carrera(crudo: dict, fecha: str, distancia_km, nombre: str) -> dict:
    """Carrera de paso: solo una meta con fecha (`de_paso`); no rehace el plan ni toca sus semanas."""
    nuevo, c = _corrida(crudo)
    c["metas"] = list(c.get("metas") or []) + [{"id": _id_nuevo(), "tipo": "carrera", "fecha": fecha, "de_paso": True,
                                               "distancia_km": distancia_km or None, "nombre": (nombre or "Carrera").strip()}]
    return _validado(nuevo)


def quitar_meta_en_plan(crudo: dict, plan: dict | None, cfg: dict, meta_id: str, hoy: date) -> tuple[dict, dict | None]:
    """(ajustes, plan nuevo o None). Una carrera de paso solo se quita de las metas. Solo las metas viejas con `en_plan` (carrera construida
    dentro de un plan v6 por la versión anterior) rehacen la cola del plan sin ella (misma duración)."""
    nuevo = quitar_meta(crudo, meta_id)
    meta = next((x for x in cfg["metas"] if x["id"] == meta_id), None)
    if not meta or not meta.get("en_plan") or not plan or not motor_v6.es_v6(plan) or not (plan.get("meta") or {}).get("carrera"):
        return nuevo, None
    try:
        plan_nuevo = motor_v6.con_carrera(plan, min(semana_tope(cfg, hoy), len(plan["weeks"])), None)
    except ValueError:
        return nuevo, None
    nuevo["corrida"]["semanas"] = len(plan_nuevo["weeks"])
    return _validado(nuevo), plan_nuevo


def quitar_meta(crudo: dict, meta_id: str) -> dict:
    nuevo, c = _corrida(crudo)
    metas = normalizar_config(crudo)["metas"]   # con ids ya asignados
    if not any(x["id"] == meta_id for x in metas):
        raise ErrorT("err.no_carrera")
    c["metas"] = [x for x in metas if x["id"] != meta_id]
    return _validado(nuevo)


def agregar_evento(crudo: dict, tipo: str, desde: str, hasta: str | None, correr: bool = False, modo: str | None = None) -> dict:
    nuevo, c = _corrida(crudo)
    c["eventos"] = normalizar_config(crudo)["eventos"] + [
        {"id": _id_nuevo(), "tipo": tipo, "desde": desde, "hasta": hasta or None,
         "modo": modo or ("menos" if correr else "pausa")}]
    return _validado(nuevo)


def cambiar_modo_viaje(crudo: dict, evento_id: str, modo: str) -> dict:
    """Cambia cómo afecta un viaje al plan: pausa, menos o igual."""
    nuevo, c = _corrida(crudo)
    eventos = normalizar_config(crudo)["eventos"]
    if modo not in ("pausa", "menos", "igual") or not any(e["id"] == evento_id and e["tipo"] == "viaje" for e in eventos):
        raise ErrorT("err.no_viaje")
    c["eventos"] = [{**e, "modo": modo} if e["id"] == evento_id else e for e in eventos]
    return _validado(nuevo)


def cerrar_evento(crudo: dict, evento_id: str, hasta: str) -> dict:
    """«Ya estoy bien»: el evento abierto termina `hasta`."""
    nuevo, c = _corrida(crudo)
    eventos = normalizar_config(crudo)["eventos"]
    if not any(e["id"] == evento_id for e in eventos):
        raise ErrorT("err.no_evento")
    c["eventos"] = [{**e, "hasta": max(hasta, e["desde"])} if e["id"] == evento_id else e for e in eventos]
    return _validado(nuevo)


def quitar_evento(crudo: dict, evento_id: str) -> dict:
    nuevo, c = _corrida(crudo)
    eventos = normalizar_config(crudo)["eventos"]
    if not any(e["id"] == evento_id for e in eventos):
        raise ErrorT("err.no_evento")
    c["eventos"] = [e for e in eventos if e["id"] != evento_id]
    return _validado(nuevo)


def carrera_objetivo(plan: dict | None, cfg: dict) -> dict | None:
    """La carrera para la que está armado el plan (plan v6 con `meta.carrera`): su meta en `cfg["metas"]` (`en_plan`) o, si no
    está, la del plan ({km, ...}). None si el plan no es de carrera. Una carrera de paso (meta suelta) no cuenta."""
    carrera = ((plan or {}).get("meta") or {}).get("carrera")
    if not carrera:
        return None
    en_plan = [x for x in cfg.get("metas", []) if x.get("en_plan")]
    return en_plan[0] if en_plan else dict(carrera)


def _semanas_taper(plan: dict, carrera: dict) -> set[int]:
    """Números de semana de taper y carrera: las que el plan marca (`evento` descarga_carrera / carrera) y, como mínimo,
    las últimas `len(taper[km más cercano])`."""
    marcadas = {w["n"] for w in plan["weeks"] if w.get("evento") in ("descarga_carrera", "carrera") or w.get("kind") in ("taper", "carrera")}
    km = int(float(carrera.get("km") or carrera.get("distancia_km") or 0))
    cerca = min(motor_v6.UMBRALES["taper"], key=lambda k: abs(k - km))
    return marcadas | {w["n"] for w in plan["weeks"][-len(motor_v6.UMBRALES["taper"][cerca]):]}


def _saltar(crudo: dict, plan: dict, cfg: dict, hoy: date, x: int | None) -> tuple[dict, dict]:
    """Repetir (x None: la semana en curso, desde el próximo lunes) o retomar desde x (desde este lunes)."""
    n = mt_semana.semana_del_plan(hoy, cfg)
    if n is None:
        raise ErrorT("err.sin_semana")
    if x is None:
        x, desde = n, lunes(hoy) + timedelta(weeks=1)
    else:
        if not 1 <= x <= n:
            raise ErrorT("err.retomar_rango", n=n)
        desde = lunes(hoy)
    k = n - x if desde == lunes(hoy) else 1   # semanas que se alarga el plan (retomar la actual: 0)
    carrera = carrera_objetivo(plan, cfg)
    quita: list[int] = []
    if carrera:
        taper = _semanas_taper(plan, carrera)
        ya = {q for s in cfg.get("saltos", []) for q in s["quita"]}
        carga = [w["n"] for w in plan["weeks"] if w["n"] > n and w["n"] not in taper and w["n"] not in ya
                 and w.get("kind", "carga") == "carga"]
        if len(carga) < k:
            raise ErrorT("err.sin_carga_antes_taper")
        quita = carga[len(carga) - k:] if k else []
    nuevo, c = _corrida(crudo)
    c["saltos"] = list(c.get("saltos") or []) + [{"lunes": desde.isoformat(), "semana": x, "quita": quita}]
    nuevo = _validado(nuevo)
    sec = mt_semana.secuencia_de(con_pausas(normalizar_config(nuevo), hoy))
    fin = lunes(date.fromisoformat(cfg["plan_start"])) + timedelta(weeks=len(sec)) - timedelta(days=1)
    return nuevo, {"k": k, "quita": quita, "fin": fin.isoformat(), "objetivo": carrera is not None}


def repetir(crudo: dict, plan: dict, cfg: dict, hoy: date) -> tuple[dict, dict]:
    """Repite la semana en curso: la próxima vuelve a ser la misma y el resto se recorre. (crudo nuevo, info para la vista previa)."""
    return _saltar(crudo, plan, cfg, hoy, None)


def retomar(crudo: dict, plan: dict, cfg: dict, hoy: date, x: int) -> tuple[dict, dict]:
    """Retoma desde la semana x (1 ≤ x ≤ la actual): desde este lunes toca la x y el resto se recorre."""
    try:
        x = int(x)
    except (TypeError, ValueError):
        raise ErrorT("err.retomar_rango", n=mt_semana.semana_del_plan(hoy, cfg) or 0) from None
    return _saltar(crudo, plan, cfg, hoy, x)


# --- sesiones flexibles (editor) ---

def filas_de(pasos: list) -> tuple[list[dict], dict]:
    """Pasos del plan -> (filas planas del formulario, {grupo: veces}). Un `repeat` es un grupo. Truena con ConfigError si
    hay repeticiones dentro de repeticiones (el formulario no las representa)."""
    filas, veces = [], {}

    def fila(p, grupo):
        return {"tipo": "caminata" if p["kind"] == "walk" else "trote", "min": p["minutes"], "zona": p["zone"],
                "grupo": grupo, "nota": p.get("note", ""), "opcional": bool(p.get("optional"))}
    for p in pasos:
        if p["kind"] == "repeat":
            if any(q["kind"] == "repeat" for q in p["steps"]):
                raise ErrorT("err.rep_anidada")
            g = len(veces) + 1
            veces[g] = p["times"]
            filas += [fila(q, g) for q in p["steps"]]
        else:
            filas.append(fila(p, 0))
    return filas, veces


def pasos_de_filas(filas: list[dict], veces: dict) -> list:
    """Filas del formulario -> pasos del plan. Cada fila: tipo (trote|caminata), min, zona, grupo (0 = sin grupo), nota,
    opcional. Las filas de un mismo grupo deben ir juntas; `veces[g]` repeticiones del grupo."""
    pasos, vistos, actual = [], set(), None
    for i, f in enumerate(filas, 1):
        try:
            minutos = int(f["min"])
        except (TypeError, ValueError):
            raise ErrorT("err.f_min_int", i=i) from None
        if not 1 <= minutos <= 240:
            raise ErrorT("err.f_min_rango", i=i)
        if f["zona"] not in ZONAS:
            raise ErrorT("err.f_zona", i=i)
        if f["tipo"] not in ("trote", "caminata"):
            raise ErrorT("err.f_tipo", i=i)
        paso = {"kind": "walk" if f["tipo"] == "caminata" else "run", "minutes": minutos, "zone": f["zona"],
                "note": f.get("nota") or ""}
        if f.get("opcional"):
            paso["optional"] = True
        g = int(f.get("grupo") or 0)
        if g == 0:
            pasos.append(paso)
            actual = None
            continue
        if g != actual:
            if g in vistos:
                raise ErrorT("err.f_grupo", i=i, g=g)
            vistos.add(g)
            n = veces.get(g)
            if not isinstance(n, int) or not 2 <= n <= 30:
                raise ErrorT("err.g_veces", g=g)
            pasos.append({"kind": "repeat", "times": n, "steps": []})
            actual = g
        pasos[-1]["steps"].append(paso)
    if not pasos:
        raise ErrorT("err.sin_pasos")
    return pasos


def editar_sesion(plan: dict, n: int, sesion_id: str, pasos: list) -> dict:
    """Plan nuevo con los `pasos` en esa sesión (minutos = suma). Solo Z2, Larga y variadas: una calidad o una prueba
    tienen estructura propia. La versión suave de la sesión no cambia."""
    nuevo = copy.deepcopy(plan)
    w = next((x for x in nuevo["weeks"] if x["n"] == n), None)
    s = next((x for x in w["sessions"] if x["id"] == sesion_id), None) if w else None
    if s is None:
        raise ErrorT("err.no_sesion")
    if s.get("tipo") not in TIPOS_EDITABLES:
        raise ErrorT("err.no_edita")
    s["steps"], s["minutes"] = pasos, ps.suma(pasos)
    s.pop("variada_tipo", None)
    return nuevo
