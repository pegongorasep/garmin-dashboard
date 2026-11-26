"""Plan vivo: metas (carreras con fecha), eventos (viaje, enfermedad, lesión), escalera de trote/caminata y sesiones
flexibles. Lógica pura (sin base de datos): recibe y devuelve dicts; las rutas y `aplicar_cambio` están en otros módulos.

Dónde vive cada cosa:
- `ajustes.config` (crudo) guarda `corrida.metas`, `corrida.eventos`, `corrida.escalon` y `corrida.semanas_repetidas`.
- `planes.plan` es el plan que sale de `gen_plan.generar` (más lo que la persona edite a mano). NO lleva los eventos:
  `plan_efectivo` los aplica al calcular (así quitar un evento o deshacerlo no deja restos en el plan).
- Una semana de **pausa** (viaje sin correr, enfermedad o lesión) no gasta semana del plan: el plan se reanuda donde iba
  (equivale a repetir la semana). Una semana **ligera** (viaje con correr) o de **carrera** sustituye a la semana n.
"""
import copy
import secrets
from datetime import date, timedelta

import gen_plan
import build
import metrics as m
from ajustes import ESCALERA, ConfigError, normalizar_config
from .errores import ErrorT

# Claves de la config normalizada que, si cambian, obligan a rehacer el plan desde la semana de hoy.
CLAVES_PLAN = ("nivel", "intensidad", "calidad_tipos", "caminatas", "variada", "plan_semanas", "base_min", "plan_start", "escalon")
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
    sec = m.secuencia_semanas(inicio, cfg["semanas_repetidas"], cfg["plan_semanas"], cfg.get("pausas", []))
    i = (hoy - inicio).days // 7
    if i < 0:
        return 1
    for n in sec[i:]:
        if n is not None:
            return n
    return cfg["plan_semanas"] + 1


def cambia_plan(viejo: dict, nuevo: dict) -> bool:
    """¿Cambió algo de la config normalizada que afecta cómo se genera el plan?"""
    return any(viejo.get(k) != nuevo.get(k) for k in CLAVES_PLAN)


def construir_plan(crudo: dict, plan_previo: dict | None, hoy: date) -> tuple[dict, int]:
    """(plan nuevo, primera semana que cambia). Genera con `gen_plan` y conserva las semanas ya pasadas del plan previo
    si el inicio es el mismo; si el inicio cambió se rehace todo (semana 1)."""
    cfg = normalizar_config(crudo)
    nuevo = gen_plan.generar(cfg)
    if not plan_previo or not plan_previo.get("weeks") or plan_previo.get("start") != nuevo["start"]:
        return nuevo, 1
    tope = semana_tope(con_pausas(cfg, hoy), hoy)
    pasadas = [w for w in plan_previo["weeks"] if w["n"] < tope]
    nuevo["weeks"] = pasadas + [w for w in nuevo["weeks"] if w["n"] >= tope]
    return nuevo, tope


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


def _z2_cortas(w: dict, minutos: int, cfg: dict) -> list:
    """Dos sesiones de Z2 continuas (o trote/caminata si la persona está en caminatas) de `minutos`."""
    def una(id_, nombre):
        pasos = gen_plan.pasos_z2(minutos, False, cfg["caminatas"], w["block"], cfg.get("escalon"))
        return gen_plan.con_suave_caminatas(gen_plan.sesion(id_, "z2", nombre, minutos, pasos),
                                            cfg["caminatas"], w["block"], cfg.get("escalon"))
    return [una("z2a", "Z2 #1"), una("z2b", "Z2 #2")]


def _minutos_z2(w: dict) -> int:
    s = next((x for x in w["sessions"] if x.get("tipo") == "z2"), w["sessions"][0])
    return s["minutes"]


def _suavizada(w: dict) -> list:
    """Cada sesión en su versión suave (descarga previa a una carrera). Calidad, variada y prueba pasan a Z2 / Larga."""
    out = []
    for s in w["sessions"]:
        e = s["easy"]
        tipo = s["tipo"] if s["tipo"] in ("z2", "larga") else ("larga" if s["tipo"] == "prueba" else "z2")
        id_ = s["id"] if s["tipo"] in ("z2", "larga") else ("larga" if tipo == "larga" else "z2b")
        nombre = s["name"] if s["tipo"] in ("z2", "larga") else ("Larga" if tipo == "larga" else "Z2 #2")
        nuevo = {"id": id_, "tipo": tipo, "name": nombre, "minutes": e["minutes"], "steps": copy.deepcopy(e["steps"]),
                 "easy": copy.deepcopy(e)}
        if "nota" in s:
            nuevo["nota"] = s["nota"]
        out.append(nuevo)
    return out


def plan_efectivo(plan: dict, cfg: dict) -> dict:
    """El plan guardado con las carreras y los viajes aplicados a sus semanas. `cfg` ya trae `pausas`. Sin metas ni
    eventos devuelve el mismo plan (idéntico)."""
    if not cfg["metas"] and not any(e["tipo"] == "viaje" and e["modo"] != "pausa" for e in cfg["eventos"]):
        return plan
    inicio = date.fromisoformat(cfg["plan_start"])
    sec = m.secuencia_semanas(inicio, cfg["semanas_repetidas"], cfg["plan_semanas"], cfg.get("pausas", []))
    carrera = {}       # n -> meta
    previa = set()     # n de la semana anterior a una carrera
    ligera = set()     # n de semanas de viaje con correr menos
    igual = set()      # n de semanas de viaje «sigo igual»: solo se marcan, el plan no cambia
    tipo = {w["n"]: w["kind"] for w in plan["weeks"]}
    for meta in cfg["metas"]:
        i = (lunes(date.fromisoformat(meta["fecha"])) - inicio).days // 7
        if 0 <= i < len(sec) and sec[i] is not None:
            carrera[sec[i]] = meta
            # Sin dos descargas seguidas: si la de antes de la previa ya fue de descarga, la previa queda normal
            if i > 0 and sec[i - 1] is not None and not (i > 1 and tipo.get(sec[i - 2]) == "descarga"):
                previa.add(sec[i - 1])
    for e in cfg["eventos"]:
        if e["tipo"] == "viaje" and e["modo"] != "pausa":
            for d in semanas_de(e, date.fromisoformat(e["hasta"])):
                i = (d - inicio).days // 7
                if 0 <= i < len(sec) and sec[i] is not None:
                    (ligera if e["modo"] == "menos" else igual).add(sec[i])
    semanas = []
    for w in plan["weeks"]:
        n = w["n"]
        if n in carrera:
            meta = carrera[n]
            minutos = max(10, gen_plan.redondea5(_minutos_z2(w) * 0.6))
            w = {**w, "kind": "descarga", "evento": "carrera", "focus": f"Semana de carrera · {meta['nombre']}",
                 "sessions": _z2_cortas(w, minutos, cfg)}
        elif n in ligera:
            w = {**w, "kind": "descarga", "evento": "viaje", "focus": "Viaje · 2 Z2 cortas",
                 "sessions": _z2_cortas(w, max(10, gen_plan.suave(_minutos_z2(w))), cfg)}
        elif n in igual and n not in previa:
            w = {**w, "evento": "viaje_igual"}
        elif n in previa:
            if w["kind"] == "descarga":
                w = {**w, "evento": "descarga_carrera"}
            else:
                w = {**w, "kind": "descarga", "evento": "descarga_carrera", "focus": "Descarga previa a la carrera",
                     "sessions": _suavizada(w)}
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
    nuevo, c = _corrida(crudo)
    c["metas"] = list(c.get("metas") or []) + [{"id": _id_nuevo(), "tipo": "carrera", "fecha": fecha,
                                               "distancia_km": distancia_km or None, "nombre": (nombre or "Carrera").strip()}]
    return _validado(nuevo)


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


def repetir_semana(crudo: dict, n: int) -> dict:
    nuevo, c = _corrida(crudo)
    c["semanas_repetidas"] = sorted(list(c.get("semanas_repetidas") or []) + [int(n)])
    return _validado(nuevo)


# --- escalera trote/caminata ---

def escalon_actual(cfg: dict, plan: dict, hoy: date) -> str | None:
    """El escalón de la persona; sin escalón explícito, el que da el bloque de la semana de hoy (si hace caminatas)."""
    if cfg.get("escalon"):
        return cfg["escalon"]
    if not cfg["caminatas"]:
        return None
    n = m.semana_del_plan(hoy, cfg) or semana_tope(cfg, hoy)
    semana = next((w for w in plan["weeks"] if w["n"] == n), plan["weeks"][-1] if plan.get("weeks") else None)
    bloque = semana["block"] if semana else 1
    return f"{gen_plan.trote_de(bloque)}/1"


def siguiente_escalon(actual: str | None) -> str | None:
    if actual not in ESCALERA or actual == ESCALERA[-1]:
        return None
    return ESCALERA[ESCALERA.index(actual) + 1]


def subir_escalon(crudo: dict, cfg: dict, plan: dict, hoy: date) -> dict:
    sig = siguiente_escalon(escalon_actual(cfg, plan, hoy))
    if sig is None:
        raise ErrorT("err.ultimo_escalon")
    nuevo, c = _corrida(crudo)
    c["escalon"] = sig
    return _validado(nuevo)


def sugerir_subir_escalon(data: dict, cfg: dict, plan: dict, hoy: date) -> str | None:
    """Solo sugiere (no cambia nada): las dos últimas semanas ya pasadas con todas las sesiones hechas y sin días rojos."""
    actual = escalon_actual(cfg, plan, hoy)
    sig = siguiente_escalon(actual)
    if sig is None:
        return None
    pasadas = [s for s in data.get("semanas_hoy") or [] if s["estado"] == "pasada" and s.get("plan")]
    if len(pasadas) < 2:
        return None
    for s in pasadas[-2:]:
        if s["plan"]["total"] == 0 or s["plan"]["hechas"] < s["plan"]["total"]:
            return None
        if any(d.get("luz") == "rojo" for d in s["dias"]):
            return None
    return sig


# --- siguiente bloque ---

def inicio_siguiente_bloque(cfg: dict, plan: dict) -> date:
    return build.ultima_semana(cfg, plan) + timedelta(days=7)


def siguiente_bloque(crudo: dict, cfg: dict, plan: dict, prueba: dict | None) -> dict:
    """Misma config, empieza el lunes siguiente al final del plan; la prueba de este bloque (si hubo) queda en
    `corrida.pruebas` para que la próxima se compare contra ella; las semanas repetidas empiezan de cero."""
    nuevo, c = _corrida(crudo)
    c["inicio"] = inicio_siguiente_bloque(cfg, plan).isoformat()
    c["semanas_repetidas"] = []
    if prueba and prueba.get("valor") is not None:
        c["pruebas"] = list(c.get("pruebas") or []) + [{"fecha": prueba["fecha"], "tipo": prueba["tipo"], "valor": prueba["valor"]}]
    return _validado(nuevo)


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
    s["steps"], s["minutes"] = pasos, gen_plan.suma(pasos)
    s.pop("variada_tipo", None)
    return nuevo
