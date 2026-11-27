"""Simulador de planes (Motor v6, fase 0): personas sintéticas + reglas de seguridad sobre un plan.

Corre un motor de planes sobre personas inventadas (plan/personas.yaml), recorre las semanas aplicando su adherencia y
revisa reglas de seguridad (las de docs/INVESTIGACION_PLANES.md, §3.9). Las reglas REPORTAN, no truenan: sirven para ver
dónde falla un motor y comparar uno contra otro.

Interfaz de motor: `motor(nombre) -> callable(persona) -> plan`. El plan es el de `gen_plan.generar`
({"start", "weeks": [{n, kind, focus, sessions: [{name, tipo, minutes, steps}]}]}); una sesión puede traer además
`dia` (0 = lunes … 6 = domingo): sin él, la regla `post_intenso` no aplica (los planes v6 ya no traen día: el plan es un orden de sesiones, y lo del día intenso de ayer es un texto en Hoy, no una regla del plan). Hoy solo existe "actual" (gen_plan.generar).

Cómo se simula (simple a propósito):
- Semana n: hecho = minutos planeados × adherencia de esa semana. Cada sesión se escala por igual (redondeo a minuto);
  con adherencia 0 no se hace ninguna. El trote seguido hecho de una sesión también se escala.
- La «ventana de 30 días» son las 4 semanas anteriores (historial real + lo hecho en el plan).
- Una semana cuenta como «consistente» si tuvo ≥ 2 sesiones y (historial) ≥ 30', o (plan) se hizo ≥ 80 % de lo planeado.
- La calidad (Z3+) se «desbloquea» cuando las últimas 6 semanas fueron consistentes, hubo ≥ 30' de trote seguido
  en las últimas 4 y el promedio de esas 4 es ≥ 90'/semana (docs/INVESTIGACION_PLANES.md §3.4, sin lesiones ni opt-in).

Uso: python -m plan.simulador [--persona id] [--motor actual]
"""
import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

RAIZ = Path(__file__).parent.parent
for _p in (RAIZ / "dashboard", RAIZ / "plan"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import gen_plan  # noqa: E402
import motor_v6  # noqa: E402
import nivel as nivel_mod  # noqa: E402
from ajustes import _DIA_IDX, crudo_desde_respuestas, normalizar_config  # noqa: E402

PERSONAS_YAML = Path(__file__).with_name("personas.yaml")
INICIO = "2026-11-30"   # lunes fijo: la simulación es determinista
ZONAS_ALTAS = ("Z3", "Z4", "Z5")

# Todos los umbrales de las reglas, en un solo lugar.
UMBRALES = {
    "sube_pct": 0.10,                 # sube_10: máx. subida semanal de minutos planeados vs la última semana que no fue descarga
    "sube_real_pct": 0.10,            # sube_real_10: máx. vs lo hecho la semana anterior
    "repite_desde": 0.50,             # sube_real_10: con 50–90 % de lo planeado la semana anterior se permite repetirla (sin subir)
    "sube_desde": 0.90,               # ... con ≥ 90 % sube hasta 110 % de lo hecho
    "baja_pct": 0.70,                 # ... con < 50 % basta un paso atrás: máx(110 % de lo hecho, 70 % de lo planeado)
    "reinicio_semanas": 2,            # ... tras ≥ 2 semanas en 0 se permite reiniciar desde el arranque de la persona
    "espiral_baja_pct": 0.30,         # sin_espiral: ninguna semana de carga cae más de 30 % vs la anterior (salvo adherencia < 50 %)
    "sesion_pct": 0.10,               # sesion_110: sesión más larga ≤ 110 % de la mayor de la ventana
    "ventana_semanas": 4,             # «30 días» = 4 semanas
    "larga_pct": {1: 1.0, 2: 0.67, 3: 0.40, 4: 0.33, 5: 0.30},   # larga_40: tope según nº de sesiones (2 = ≤ 2× la otra)
    "base_semanas": 6,                # sin_z3_novato: semanas consistentes seguidas para tener base
    "base_continuo_min": 30,          # ... trote seguido mínimo (en las últimas `ventana_semanas`)
    "base_volumen_min": 90,           # ... minutos por semana (promedio de las últimas `ventana_semanas`)
    "consistente_sesiones": 2,        # una semana consistente tiene al menos estas sesiones
    "consistente_min_historial": 30,  # ... y (historial) al menos estos minutos
    "consistente_hecho_pct": 0.80,    # ... o (plan) se hizo al menos esta fracción
    "descarga_cada": 4,               # descarga: una semana de descarga al menos cada 4 semanas
    "descarga_cada_mayor": 3,         # ... cada 3 si tiene 50+ años o 3+ días intensos por semana
    "mayor_edad": 50,
    "intensos_dias": 3,
    "inicio_pct": 0.10,               # inicio_real: semana 1 ≤ 110 % del promedio reciente
    "inicio_semanas": 4,              # ... promedio de las últimas 4 semanas del historial
    "inicio_sin_historial": {"total": 90, "sesion": 30},   # sin historial: 3 sesiones de escalera de 20–30'
    "taper_min": 0.30,                # taper: la semana de la carrera baja al menos 30 % vs el pico anterior
    "taper_max": 0.60,                # ... y no más de 60 % (tolerancia sobre el 50 % de la investigación)
}


# --- personas ---

def actividades_sinteticas(persona: dict, hoy: str = INICIO) -> list:
    """El historial de la persona como actividades de Garmin inventadas (las 8 semanas anteriores a `hoy`, un lunes).
    Cada sesión es una corrida; si el trote seguido (`continuo`) es menor que la sesión, trae tramos de trote y 1' de caminata.
    Los días intensos de `intensos_semana` son una actividad HIIT de 45' cada semana (cuenta como día intenso, sea CrossFit, gym o clases)."""
    lunes = datetime.fromisoformat(hoy)
    out = []
    hist = persona["historial"]
    for i, h in enumerate(hist):
        inicio = lunes - timedelta(days=7 * (len(hist) - i))
        sesiones = h["sesiones"]
        mayor = max(sesiones, default=0)
        for j, minutos in enumerate(sesiones):
            dia = inicio + timedelta(days=round(j * 7 / len(sesiones)), hours=7)
            a = {"startTimeLocal": dia.isoformat(sep=" "), "duration": minutos * 60.0,
                 "activityType": {"typeKey": "running"}}
            if minutos == mayor and 0 < h["continuo"] < minutos:   # la sesión que trae el trote seguido de la semana
                n = max(1, round(minutos / (h["continuo"] + 1)))
                a["splitSummaries"] = [{"splitType": "RWD_RUN", "duration": n * h["continuo"] * 60, "noOfSplits": n},
                                       {"splitType": "RWD_WALK", "duration": n * 60, "noOfSplits": n}]
            out.append(a)
        for d in persona["intensos_semana"]["dias"]:
            out.append({"startTimeLocal": (inicio + timedelta(days=d, hours=18)).isoformat(sep=" "), "duration": 2700.0,
                        "activityType": {"typeKey": "hiit"}})
    return out


def _normalizar_persona(p: dict) -> dict:
    """Rellena lo que falte con valores por defecto (para personas armadas a mano en pruebas) y arma `config_actual`."""
    p = dict(p)
    p["_normalizada"] = True
    p.setdefault("nombre", p.get("id", "persona"))
    p.setdefault("descripcion", "")
    p.setdefault("edad", 35)
    p.setdefault("dias_semana", 3)
    p["historial"] = [{"sesiones": list(h.get("sesiones") or []), "continuo": int(h.get("continuo") or 0)}
                      for h in p.get("historial") or []]
    intensos = p.get("intensos_semana") or {}
    p["intensos_semana"] = {"dias": [_DIA_IDX[d] for d in intensos.get("dias") or []], "tipo": intensos.get("tipo", "")}
    ad = p.get("adherencia") or {}
    p["adherencia"] = {"base": float(ad.get("base", 1.0)), "huecos": [tuple(h) for h in ad.get("huecos") or []]}
    p.setdefault("meta", None)
    p["actividades"] = actividades_sinteticas(p)
    p["nivel"] = nivel_mod.nivel_desde_datos(p["actividades"], datetime.fromisoformat(INICIO))
    if "config_actual" not in p:
        crudo = crudo_desde_respuestas(INICIO, edad=p["edad"], **(p.get("formulario") or {}))
        p["config_actual"] = normalizar_config(crudo)
    return p


def _completa(p: dict) -> dict:
    """Persona ya normalizada (la de `cargar_personas`) o cruda: normaliza solo la cruda."""
    return p if p.get("_normalizada") else _normalizar_persona(p)


def cargar_personas(ruta=PERSONAS_YAML) -> list:
    """Las personas del yaml, con `config_actual` armado por el mismo camino que el formulario de la web."""
    crudas = yaml.safe_load(Path(ruta).read_text(encoding="utf-8"))["personas"]
    return [_normalizar_persona(p) for p in crudas]


def persona_por_id(id_: str) -> dict:
    for p in cargar_personas():
        if p["id"] == id_:
            return p
    raise KeyError(f"persona '{id_}' no existe")


def fraccion(persona: dict, n: int) -> float:
    """Adherencia de la semana n del plan (1-based)."""
    ad = persona["adherencia"]
    if any(a <= n <= b for a, b in ad["huecos"]):
        return 0.0
    return ad["base"]


# --- motores ---

def _motor_actual(persona: dict) -> dict:
    return gen_plan.generar(persona["config_actual"])


def entrada_v6(persona: dict) -> dict:
    """La entrada de `motor_v6.generar_v6` para una persona: nivel y evidencia de F2, sus días, intensos y meta. Todo viene de la persona (nada del formulario viejo)."""
    nv = persona["nivel"]
    meta = persona.get("meta")
    return {"nivel": nv["nivel"], "evidencia": nv["evidencia"], "inicio_minutos": nv["inicio_minutos"], "dias": persona["dias_semana"],
            "dias_intensos": persona["intensos_semana"]["dias"], "edad": persona["edad"], "inicio": INICIO,
            "meta": {"tipo": "carrera", "km": meta["distancia_km"], "semanas_hasta": meta["semanas_hasta"]} if meta else None,
            "objetivo": "velocidad" if (persona.get("formulario") or {}).get("intensidad") == "calidad" else None}


def _motor_v6(persona: dict) -> dict:
    return motor_v6.generar_v6(entrada_v6(persona))


MOTORES = {"actual": _motor_actual, "v6": _motor_v6}
# Motores que ajustan cada semana a lo que la persona de verdad hizo (motor_v6.ajustar_semana); el actual no ajusta nada.
AJUSTAN = {"v6"}


def obtener_motor(nombre: str):
    """`motor(nombre) -> callable(persona) -> plan`."""
    try:
        return MOTORES[nombre]
    except KeyError:
        raise ValueError(f"motor '{nombre}' no existe; hay: {', '.join(MOTORES)}") from None


motor = obtener_motor


# --- medidas de una sesión ---

def _planos(pasos):
    for p in pasos:
        if p["kind"] == "repeat":
            for _ in range(p["times"]):
                yield from _planos(p["steps"])
        else:
            yield p


def zonas_min(pasos: list) -> dict:
    """{zona: minutos} de los pasos (las repeticiones se expanden)."""
    z = {}
    for p in _planos(pasos):
        z[p["zone"]] = z.get(p["zone"], 0) + p["minutes"]
    return dict(sorted(z.items()))


def continuo(pasos: list) -> int:
    """Trote seguido más largo (minutos): la caminata lo corta."""
    mejor = act = 0
    for p in _planos(pasos):
        if p["kind"] == "walk":
            act = 0
        else:
            act += p["minutes"]
            mejor = max(mejor, act)
    return mejor


def _sesion(s: dict) -> dict:
    z = zonas_min(s["steps"])
    return {"nombre": s["name"], "tipo": s.get("tipo", ""), "min": s["minutes"], "zonas": z,
            "resumen": " · ".join(f"{k} {v}'" for k, v in z.items()),
            "z3mas": sum(z.get(k, 0) for k in ZONAS_ALTAS), "continuo": continuo(s["steps"]), "dia": s.get("dia")}


def _escalar(x: int, f: float) -> int:
    return int(x * f + 0.5)


# --- línea de tiempo (historial + lo hecho) y desbloqueo ---

def _semana_historial(h: dict) -> dict:
    s = h["sesiones"]
    return {"sesiones": list(s), "min": sum(s), "continuo": h["continuo"],
            "consistente": len(s) >= UMBRALES["consistente_sesiones"] and sum(s) >= UMBRALES["consistente_min_historial"]}


def desbloqueado(linea: list) -> bool:
    """¿La persona ya tiene base para Z3+ al empezar la semana que sigue a `linea`? (ver la nota del módulo)"""
    u = UMBRALES
    if len(linea) < u["base_semanas"] or not all(w["consistente"] for w in linea[-u["base_semanas"]:]):
        return False
    ult = linea[-u["ventana_semanas"]:]
    return max(w["continuo"] for w in ult) >= u["base_continuo_min"] and \
        sum(w["min"] for w in ult) / u["ventana_semanas"] >= u["base_volumen_min"]


def _pct(a, b):
    return None if not b else round((a / b - 1) * 100, 1)


# --- simulación ---

def analizar(persona: dict, plan: dict, motor_nombre: str = "?") -> dict:
    """Recorre las semanas del `plan` aplicando la adherencia y revisa las reglas. Determinista."""
    persona = _completa(persona)
    linea = [_semana_historial(h) for h in persona["historial"]]
    inicial = list(linea)
    filas, ventana = [], UMBRALES["ventana_semanas"]
    for w in plan["weeks"]:
        n, f = w["n"], fraccion(persona, w["n"])
        ses = [_sesion(s) for s in w["sessions"]]
        total = sum(s["min"] for s in ses)
        mayor = max((s["min"] for s in ses), default=0)
        previos = [x for x in linea[-ventana:]]
        max30 = max((m for x in previos for m in x["sesiones"]), default=0)
        hechas = [_escalar(s["min"], f) for s in ses] if f > 0 else []
        hecho = sum(hechas)
        prev, prev_carga = (filas[-1] if filas else None), next((r for r in reversed(filas) if r["kind"] != "descarga"), None)
        filas.append({
            "n": n, "kind": w["kind"], "focus": w.get("focus", ""), "min": total, "larga_min": mayor,
            "larga_pct": round(mayor / total * 100, 1) if total else 0.0,
            "z3mas_min": sum(s["z3mas"] for s in ses),
            "z45_min": sum(s["zonas"].get("Z4", 0) + s["zonas"].get("Z5", 0) for s in ses),
            "d_prev": _pct(total, prev["min"]) if prev else None,
            "d_carga": _pct(total, prev_carga["min"]) if prev_carga else None,
            "max_sesion": mayor, "max30": max30,
            "tope_sesion": round(max30 * (1 + UMBRALES["sesion_pct"]), 1) if max30 else None,
            "desbloqueado": desbloqueado(linea),
            "sesiones": ses, "fraccion": f, "hecho_min": hecho, "hechas": hechas,
            "ok": [], "falla": [],   # claves de reglas que esta semana cumple / incumple (se llenan abajo)
        })
        cont = max((_escalar(s["continuo"], f) for s in ses), default=0) if f > 0 else 0
        linea.append({"sesiones": hechas, "min": hecho, "continuo": cont,
                      "consistente": f >= UMBRALES["consistente_hecho_pct"] and len(ses) >= UMBRALES["consistente_sesiones"]})
    ctx = {"persona": persona, "filas": filas, "plan": plan, "inicial": inicial}
    reglas = []
    for clave, texto, fn in REGLAS:
        ok, fallan, detalle = fn(ctx)
        reglas.append({"clave": clave, "texto": texto, "ok": ok, "semanas_fallan": fallan, "detalle": detalle})
        for r in filas:
            if r["n"] in fallan:
                r["falla"].append(clave)
    cuenta = {"ok": sum(r["ok"] is True for r in reglas), "fallan": sum(r["ok"] is False for r in reglas),
              "no_aplica": sum(r["ok"] is None for r in reglas)}
    return {"persona": {k: persona.get(k, "") for k in ("id", "nombre", "descripcion", "edad")},
            "nivel": persona["nivel"], "motor": motor_nombre, "sin_base": not desbloqueado(inicial), "semanas": filas, "reglas": reglas, "resumen": cuenta}


def aplicar_ajuste(persona: dict, plan: dict) -> dict:
    """El plan tal como se vive con el ajuste semanal: la semana n se topa a lo que de verdad se hizo la n−1 y a 110 % de la sesión más larga hecha
    en las últimas 4 semanas (hecho = planeado × adherencia, igual que en `analizar`). La semana 1 no se ajusta (su tope es `inicio_real`)."""
    semanas, real_prev, real_normal, ceros = [], None, None, 0
    linea = [list(h["sesiones"]) for h in persona["historial"]]   # sesiones hechas por semana (historial + plan)
    for w in plan["weeks"]:
        mayor = max((m for sem in linea[-UMBRALES["ventana_semanas"]:] for m in sem), default=0)
        w2 = motor_v6.ajustar_semana({**plan, "weeks": semanas + [w]}, w["n"], real_prev, mayor or None, real_normal, ceros) if semanas else w
        semanas.append(w2)
        f = fraccion(persona, w["n"])
        hechas = [_escalar(s["minutes"], f) for s in w2["sessions"]] if f > 0 else []
        linea.append(hechas)
        real_prev = sum(hechas)
        ceros = ceros + 1 if real_prev == 0 else 0
        if w2["kind"] != "descarga":
            real_normal = real_prev
    return {**plan, "weeks": semanas}


def simular(persona: dict, motor: str = "actual") -> dict:  # noqa: A002
    """Genera el plan de `persona` con el motor `motor` (con el ajuste semanal si ese motor lo hace) y lo analiza."""
    p = _completa(persona)
    plan = obtener_motor(motor)(p)
    return analizar(p, aplicar_ajuste(p, plan) if motor in AJUSTAN else plan, motor)


def simular_todas(motor_nombre: str = "actual") -> list:
    return [simular(p, motor_nombre) for p in cargar_personas()]


def matriz(resultados: list) -> list:
    """[{"persona": id, "celdas": {clave: True|False|None}}] en el orden de REGLAS."""
    return [{"persona": r["persona"]["id"], "celdas": {x["clave"]: x["ok"] for x in r["reglas"]}} for r in resultados]


# --- reglas: cada una devuelve (ok True|False|None=no aplica, semanas que fallan, detalle) ---

def _veredicto(fallan: list, mal: list, bien: str) -> tuple:
    if not fallan:
        return True, [], bien
    extra = " …" if len(mal) > 4 else ""
    return False, fallan, "; ".join(mal[:4]) + extra


def r_sube_10(c):
    lim, fallan, mal = UMBRALES["sube_pct"], [], []
    filas = c["filas"]
    for i, r in enumerate(filas):
        if r["kind"] == "descarga":
            continue
        ref = next((x for x in reversed(filas[:i]) if x["kind"] != "descarga"), None)
        if ref and r["min"] > ref["min"] * (1 + lim) + 1e-9:
            tras = " (tras descarga)" if filas[i - 1]["kind"] == "descarga" else ""
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: {r['min']}' vs {ref['min']}' de la sem {ref['n']} (+{_pct(r['min'], ref['min'])} %){tras}")
    return _veredicto(fallan, mal, "Ninguna semana sube más de 10 % sobre la última que no fue descarga.")


def _piso(c):
    """Piso duro del motor v6 por nivel de la persona (0 si el plan no es v6)."""
    nv = c["persona"].get("nivel") or {}
    return motor_v6.UMBRALES["ajuste_piso"].get(nv.get("nivel"), 0) if (c["plan"].get("meta") or {}).get("motor") == "v6" else 0


def r_sube_real_10(c):
    """Nunca se planea SUBIR por encima de lo que se hizo. Con ≥ 90 % de lo planeado la semana anterior: ≤ 110 % de lo hecho; con 50–90 %: se
    permite repetir (≤ lo planeado esa semana); con < 50 %: ≤ máx(110 % de lo hecho, 70 % de lo planeado); tras ≥ 2 semanas en 0: ≤ el arranque
    de la persona. En todos los casos se permite el piso del nivel. (El «≤ 110 % de lo hecho» a secas empujaba al plan a encogerse cada semana.)"""
    u, fallan, mal = UMBRALES, [], []
    filas, piso = c["filas"], _piso(c)
    arranque = (c["persona"].get("nivel") or {}).get("inicio_minutos", 0)
    for i, r in enumerate(filas[1:], 1):
        j = i - 1
        while j > 0 and filas[j]["kind"] == "descarga":   # tras una descarga se compara con la última semana normal
            j -= 1
        hecho, obj = filas[j]["hecho_min"], filas[j]["min"]
        ratio = hecho / obj if obj else 1.0
        if ratio >= u["sube_desde"]:
            tope = hecho * (1 + u["sube_real_pct"])
        elif ratio >= u["repite_desde"]:
            tope = max(obj, hecho * (1 + u["sube_real_pct"]))
        else:
            tope = max(hecho * (1 + u["sube_real_pct"]), obj * u["baja_pct"])
        ceros = 0
        for x in reversed(filas[:i]):
            if x["hecho_min"] != 0:
                break
            ceros += 1
        if ceros >= u["reinicio_semanas"]:
            tope = max(tope, arranque)
        tope = max(tope, piso)
        if r["kind"] != "descarga" and r["min"] > tope + 1e-9:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: planea {r['min']}' y en la sem {filas[j]['n']} hizo {hecho}' de {obj}' (tope {tope:g}')")
    return _veredicto(fallan, mal, "Nunca planea subir por encima de lo hecho: sube, repite o da un paso atrás según lo cumplido.")


def r_sin_espiral(c):
    """Solo para planes v6 (los demás: no aplica). Una semana de carga nunca queda por debajo del piso del nivel (o de lo que el plan traía,
    si era menos) y nunca cae más de 30 % vs la semana de carga anterior, salvo que esa semana se hiciera < 50 % de lo planeado o que la caída la fuerce el tope de sesión (110 % de lo hecho)."""
    if (c["plan"].get("meta") or {}).get("motor") != "v6":
        return None, [], "Solo aplica a los planes del motor v6."
    u, piso, fallan, mal = UMBRALES, _piso(c), [], []
    filas = c["filas"]
    for i, r in enumerate(filas):
        if i == 0 or r["kind"] != "carga":
            continue
        original = (c["plan"]["weeks"][i].get("ajuste") or {}).get("planeado", r["min"])
        if r["min"] < min(piso, original):
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: {r['min']}' está bajo el piso de {piso}'")
        prev = filas[i - 1]
        piso_caida = min(prev["min"] * (1 - u["espiral_baja_pct"]), prev["hecho_min"] * (1 + u["sesion_pct"])) - len(r["sesiones"])   # lo que fuerza el tope de sesión (110 % de lo hecho) no cuenta
        if prev["kind"] == "carga" and prev["fraccion"] >= u["repite_desde"] and r["min"] < piso_caida:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: cae de {prev['min']}' a {r['min']}' habiendo hecho ≥ 50 %")
    return _veredicto(sorted(set(fallan)), mal, "El objetivo semanal no baja del piso ni se desploma.")


def r_sesion_110(c):
    """Ninguna sesión pasa de 110 % de la más larga de 30 días. Excepción (solo v6): el piso del nivel dividido entre las sesiones de la semana,
    para que el piso (el mínimo seguro) se pueda cumplir aunque lo hecho haya sido poco."""
    fallan, mal, piso = [], [], _piso(c)
    for r in c["filas"]:
        tope = r["tope_sesion"]
        if tope is not None and piso and r["sesiones"]:
            tope = max(tope, -(-piso // len(r["sesiones"])))
        if tope is not None and r["max_sesion"] > tope + 1e-9:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: sesión de {r['max_sesion']}' y el tope era {r['tope_sesion']:g}' (110 % de {r['max30']}')")
    return _veredicto(fallan, mal, "Ninguna sesión pasa de 110 % de la más larga de los últimos 30 días.")


def r_larga_40(c):
    fallan, mal = [], []
    for r in c["filas"]:
        n_ses = len(r["sesiones"])
        if n_ses < 2:
            continue
        lim = UMBRALES["larga_pct"].get(min(n_ses, 5), 0.30)
        if r["larga_pct"] / 100 > lim + 1e-9:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: la larga es {r['larga_pct']:g} % con {n_ses} sesiones (tope {lim * 100:g} %)")
    return _veredicto(fallan, mal, "La larga nunca pasa de su tope (40 % con 3 sesiones).")


def r_sin_z3_novato(c):
    sin_base = not desbloqueado(c["inicial"])
    if not sin_base:
        return None, [], "Ya tiene base (≥ 6 semanas consistentes, ≥ 30' seguidos, ≥ 90'/semana): la regla no aplica."
    fallan, mal = [], []
    for r in c["filas"]:
        if not r["desbloqueado"] and r["z3mas_min"] > 0:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: {r['z3mas_min']}' en Z3+ sin base")
    return _veredicto(fallan, mal, "Sin Z3+ mientras no hay base.")


def r_descarga(c):
    u = UMBRALES
    p = c["persona"]
    mayor = p["edad"] >= u["mayor_edad"] or len(p["intensos_semana"]["dias"]) >= u["intensos_dias"]
    maxc = (u["descarga_cada_mayor"] if mayor else u["descarga_cada"]) - 1   # semanas de carga seguidas permitidas
    fallan, mal, racha = [], [], 0
    for r in c["filas"]:
        racha = 0 if r["kind"] == "descarga" else racha + 1
        if racha > maxc:
            fallan.append(r["n"])
            mal.append(f"sem {r['n']}: {racha} semanas seguidas sin descarga (máx. {maxc})")
    return _veredicto(fallan, mal, f"Hay descarga al menos cada {maxc + 1} semanas.")


def r_inicio_real(c):
    u, filas = UMBRALES, c["filas"]
    if not filas:
        return None, [], "El plan no tiene semanas."
    r = filas[0]
    semanas_h = [sum(h["sesiones"]) for h in c["persona"]["historial"]]
    ceros = 0   # semanas en 0 al final del historial: tras una pausa de ≥ 2 semanas el promedio es el de las semanas ANTERIORES a ella (igual que nivel.py)
    while ceros < len(semanas_h) and semanas_h[-1 - ceros] == 0:
        ceros += 1
    recientes = (semanas_h[:len(semanas_h) - ceros] if ceros >= 2 else semanas_h)[-u["inicio_semanas"]:]
    prom = sum(recientes) / u["inicio_semanas"] if recientes else 0
    if prom > 0:
        lim = max(prom * (1 + u["inicio_pct"]), _piso(c))   # excepción (solo v6): el piso del nivel
        if r["min"] <= lim + 1e-9:
            return True, [], f"Semana 1: {r['min']}' ≤ 110 % de su promedio reciente ({prom:g}')."
        return False, [1], f"Semana 1: {r['min']}' y su promedio reciente es {prom:g}' (tope {lim:g}')."
    s = u["inicio_sin_historial"]
    if r["min"] <= s["total"] and r["max_sesion"] <= s["sesion"]:
        return True, [], f"Semana 1: {r['min']}' y sesión máx. {r['max_sesion']}', como una escalera de trote/caminata."
    return False, [1], (f"Semana 1 sin historial: {r['min']}' y sesión máx. {r['max_sesion']}' "
                        f"(la escalera de inicio es ≤ {s['total']}' y ≤ {s['sesion']}' por sesión).")


def r_taper(c):
    meta, filas = c["persona"]["meta"], c["filas"]
    if not meta:
        return None, [], "Sin carrera: la regla no aplica."
    R = int(meta["semanas_hasta"])
    if R > len(filas) or R < 3:
        return None, [], f"La carrera (semana {R}) no cabe en el plan."
    cargas = [r["min"] for r in filas[:R - 2] if r["kind"] == "carga"]   # el pico es el de las últimas 3 semanas de carga (ya ajustadas)
    pico = max(cargas[-3:]) if cargas else max(r["min"] for r in filas[:R - 2])
    baja = 1 - filas[R - 1]["min"] / pico
    u = UMBRALES
    if u["taper_min"] <= baja <= u["taper_max"] + 1e-9:
        return True, [], f"La semana de la carrera ({R}) baja {baja * 100:.0f} % vs el pico de {pico}'."
    return False, [R], f"La semana de la carrera ({R}) baja {baja * 100:.0f} % vs el pico de {pico}' (debe bajar 30–60 %)."


def r_post_intenso(c):
    filas = [s for r in c["filas"] for s in r["sesiones"]]
    if not any(s["dia"] is not None for s in filas):
        return None, [], "El plan no pone las sesiones en días de la semana: la regla no aplica."
    intensos, fallan, mal = set(c["persona"]["intensos_semana"]["dias"]), [], []
    for r in c["filas"]:
        for s in r["sesiones"]:
            if s["dia"] is not None and s["tipo"] in ("larga", "calidad", "variada") and (s["dia"] - 1) % 7 in intensos:
                fallan.append(r["n"])
                mal.append(f"sem {r['n']}: {s['nombre']} el día siguiente a un día intenso")
    return _veredicto(sorted(set(fallan)), mal, "Ninguna larga ni calidad cae el día después de un día intenso.")


REGLAS = [
    ("sube_10", "Los minutos semanales no suben más de 10 % sobre la última semana que no fue descarga (ni al volver de una).", r_sube_10),
    ("sube_real_10", "Lo planeado no sube por encima de lo que de verdad hizo la semana anterior (sube ≤ 110 % si cumplió; repite si hizo 50–90 %; paso atrás si < 50 %).", r_sube_real_10),
    ("sesion_110", "Ninguna sesión pasa de 110 % de la más larga de los últimos 30 días.", r_sesion_110),
    ("larga_40", "La larga no pasa de 40 % de la semana (con 3 días).", r_larga_40),
    ("sin_z3_novato", "Sin minutos en Z3 o más para quien no tiene base, antes de desbloquear la calidad.", r_sin_z3_novato),
    ("descarga", "Hay una semana de descarga al menos cada 4 semanas (cada 3 con 50+ años o 3+ días intensos).", r_descarga),
    ("inicio_real", "La semana 1 no pasa de 110 % de lo que ya corría (o de la escalera de inicio sin historial).", r_inicio_real),
    ("sin_espiral", "El objetivo semanal del plan v6 no baja del piso del nivel ni cae más de 30 % en una semana (salvo adherencia < 50 %).", r_sin_espiral),
    ("taper", "Con carrera, la semana de la carrera baja 30–50 % de minutos.", r_taper),
    ("post_intenso", "Ni larga ni calidad el día después de un día intenso (no aplica a planes v6: no fijan días).", r_post_intenso),
]
CLAVES = [k for k, _, _ in REGLAS]


# --- CLI ---

def _marca(ok):
    return "–" if ok is None else ("✓" if ok else "✗")


def _imprimir(res: dict) -> None:
    p = res["persona"]
    print(f"\n== {p['nombre']} ({p['id']}) · {p['edad']} años · motor {res['motor']} · "
          f"{'sin base' if res['sin_base'] else 'con base'} ==")
    print(" sem tipo      min    Δ%  Δ%car larga  lg%  Z3+  sesión/tope  hecho  falla")
    for r in res["semanas"]:
        d = lambda x: "    ." if x is None else f"{x:+5.0f}"  # noqa: E731
        tope = "  ." if r["tope_sesion"] is None else f"{r['tope_sesion']:g}"
        print(f" {r['n']:>3} {r['kind']:<9} {r['min']:>4} {d(r['d_prev'])} {d(r['d_carga'])} {r['larga_min']:>5} "
              f"{r['larga_pct']:>4.0f} {r['z3mas_min']:>4} {r['max_sesion']:>5}/{tope:<6} {r['hecho_min']:>5}  {','.join(r['falla'])}")
    for x in res["reglas"]:
        print(f"  {_marca(x['ok'])} {x['clave']:<14} {x['detalle']}")


def _imprimir_matriz(resultados: list) -> None:
    print("\nMatriz (✓ cumple, ✗ falla, – no aplica)")
    print(f"{'persona':<24}" + " ".join(f"{k[:9]:<9}" for k in CLAVES))
    for r in resultados:
        print(f"{r['persona']['id']:<24}" + " ".join(f"{_marca(x['ok']):<9}" for x in r["reglas"]))


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description="Simula personas sintéticas sobre un motor de planes y revisa las reglas.")
    ap.add_argument("--persona", help="id de una persona (por defecto, todas)")
    ap.add_argument("--motor", default="actual", help=f"motor: {', '.join(MOTORES)}")
    args = ap.parse_args(argv)
    personas = [persona_por_id(args.persona)] if args.persona else cargar_personas()
    resultados = [simular(p, args.motor) for p in personas]
    for r in resultados:
        _imprimir(r)
    _imprimir_matriz(resultados)


if __name__ == "__main__":
    main()
