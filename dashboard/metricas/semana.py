"""Secuencia de semanas del plan, asignación de sesiones, tarjeta de hoy y plan contra real."""

from datetime import date, timedelta

from dashboard import plan_i18n
from dashboard import tipos
from dashboard.i18n import tt
from dashboard.metricas.comun import ZONAS, classify, day_of
from dashboard.metricas.zonas import zone_minutes


def secuencia_semanas(plan_start: date, repetidas=(), total: int = 12, pausas=(), saltos=()) -> list:
    """Semanas del calendario desde `plan_start`: el número de semana del plan que toca en cada una (o None si esa
    semana está en pausa). `repetidas` repite semanas del plan (formato viejo); `pausas` son lunes (AAAA-MM-DD) que no
    gastan semana del plan (viaje sin correr, enfermedad): el plan se reanuda donde iba. `saltos` [{lunes, semana, quita}]:
    desde su lunes toca la semana `semana`, luego la siguiente… hasta `total`, sin las de `quita` (las de saltos anteriores
    tampoco). Se aplican en orden de fecha; los mal formados se ignoran."""
    secuencia = []
    for n in range(1, total + 1):
        secuencia += [n] * (1 + list(repetidas).count(n))
    pausas_i = sorted({(date.fromisoformat(str(p)) - plan_start).days // 7 for p in pausas})
    validos = []
    for s in saltos or ():
        try:
            validos.append((date.fromisoformat(str(s["lunes"])), int(s["semana"]), {int(q) for q in s.get("quita") or []}))
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
    quitadas = set()
    for lunes, semana, quita in sorted(validos, key=lambda v: v[0]):
        quitadas |= quita
        j = (lunes - plan_start).days // 7                      # semana del calendario del salto
        p = j - sum(1 for i in pausas_i if i < j)               # lugar en la secuencia sin pausas
        if 0 <= p <= len(secuencia) and 1 <= semana <= total:
            secuencia = secuencia[:p] + [n for n in range(semana, total + 1) if n not in quitadas]
    for i in pausas_i:
        if 0 <= i <= len(secuencia):
            secuencia.insert(i, None)
    return secuencia


def secuencia_de(config: dict) -> list:
    """`secuencia_semanas` con lo que dice la config (inicio, repetidas, total, pausas y saltos)."""
    return secuencia_semanas(date.fromisoformat(config["plan_start"]), config.get("semanas_repetidas", []),
                             config.get("plan_semanas", 12), config.get("pausas", []), config.get("saltos", []))


def week_index(day: date, plan_start: date, repetidas=(), total: int = 12, pausas=(), saltos=()):
    """Semana del plan (1–`total`) que toca en `day`, o None si está fuera (o en pausa).

    `repetidas`: números de semana del plan que se repitieron (una semana puede
    aparecer más de una vez). Cada repetición empuja el resto una semana. `pausas` y `saltos`: ver `secuencia_semanas`.
    """
    secuencia = secuencia_semanas(plan_start, repetidas, total, pausas, saltos)
    i = (day - plan_start).days // 7
    return secuencia[i] if 0 <= i < len(secuencia) else None


def semana_del_plan(day: date, config: dict):
    """`week_index` con lo que dice la config (inicio, semanas repetidas, total, pausas y saltos)."""
    sec = secuencia_de(config)
    i = (day - date.fromisoformat(config["plan_start"])).days // 7
    return sec[i] if 0 <= i < len(sec) else None


def en_pausa(day: date, config: dict) -> bool:
    """Hoy cae en una semana de pausa del plan (viaje sin correr o enfermedad)."""
    i = (day - date.fromisoformat(config["plan_start"])).days // 7
    sec = secuencia_de(config)
    return 0 <= i < len(sec) and sec[i] is None


def _ref_minutos(sesion: dict, luz) -> int:
    """Minutos de referencia: los de la versión suave si ese día fue amarillo/rojo."""
    return sesion["easy"]["minutes"] if luz in ("amarillo", "rojo") else sesion["minutes"]


def _estado_sesion(sesion: dict, corrida, config: dict) -> dict:
    base = {"id": sesion["id"], "name": plan_i18n.nombre(sesion["name"]), "tipo": sesion.get("tipo")}
    if corrida is None:
        return {**base, "estado": "pendiente", "ajustada": False, "fecha": None, "minutos": None}
    suave = corrida.get("luz") in ("amarillo", "rojo")
    hecha = corrida["minutos"] + 0.5 >= config["done_ratio"] * _ref_minutos(sesion, corrida.get("luz"))
    return {**base, "estado": "hecha" if hecha else "incompleta", "ajustada": hecha and suave,
            "fecha": corrida["fecha"], "minutos": corrida["minutos"]}


def assign_sessions(week: dict, runs: list, config: dict) -> list:
    """Asigna las corridas de la semana a sus sesiones (sin mirar nombres).

    runs: [{"fecha", "minutos", "luz"}] en orden cronológico. La semana es un orden de sesiones, no días fijos: la corrida
    más larga con minutos + 0.5 ≥ done_ratio × larga (en CUALQUIER día) → Larga (la prueba de la última semana igual).
    La calidad se reconoce por su Z3+; las demás, en orden, llenan las fáciles; las sobrantes son "extra" y no se asignan. `luz` "sin_datos" cuenta
    como verde. Devuelve un dict por sesión, en el orden de la semana.
    """
    sesiones = week["sessions"]
    larga = next((s for s in sesiones if s.get("tipo") in ("larga", "prueba")), None)   # la prueba ocupa su lugar
    calidad = next((s for s in sesiones if s.get("tipo") == "calidad"), None)
    elegida = None
    if larga:
        candidatas = [r for r in runs if r["minutos"] + 0.5 >= config["done_ratio"] * larga["minutes"]]
        elegida = max(candidatas, key=lambda r: r["minutos"], default=None)
    resto = [r for r in runs if r is not elegida]
    # La calidad es la primera corrida (no Larga) con >= 50 % de los minutos objetivo en Z3 o más.
    de_calidad = None
    if calidad:
        meta = (calidad.get("objetivo") or {}).get("minutos", 0)
        de_calidad = next((r for r in resto if sum((r.get("zonas") or {}).get(z, 0) for z in ("Z3", "Z4", "Z5")) >= 0.5 * meta
                           and meta > 0), None)
        if de_calidad:
            resto = [r for r in resto if r is not de_calidad]
    asignadas = {}
    for s in sesiones:
        if s is larga:
            asignadas[s["id"]] = elegida
        elif s is calidad:
            asignadas[s["id"]] = de_calidad
        else:
            asignadas[s["id"]] = resto.pop(0) if resto else None
    return [_estado_sesion(s, asignadas[s["id"]], config) for s in sesiones]


def _unir_avisos(*avisos):
    unidos = " · ".join(a for a in avisos if a)
    return unidos or None


def _elegir_pendiente(day: date, status: list):
    """(sesión pendiente, aviso). La semana es un orden, no días fijos: toca la primera sesión pendiente del orden del plan."""
    return next((s for s in status if s["estado"] == "pendiente"), None), None


def aviso_intenso_ayer(day: date, sesion: dict, activities: list, config: dict):
    """Si ayer hubo una actividad intensa que no fue correr (HIIT, gym, pierna…), y hoy tocaría la larga o la calidad,
    sugiere (solo texto) hacer hoy una fácil y dejarla para otro día. Sale de las categorías de actividad ya clasificadas."""
    if sesion.get("tipo") not in ("larga", "calidad"):
        return None
    ayer = day - timedelta(days=1)
    cats = {c["id"]: c for c in config.get("categorias", [])}
    pierna = ayer.weekday() in config.get("dias_pierna", [])   # día de pierna: cualquier categoría registrada cuenta como intensa
    if not any((c := classify(a, config)) in cats and (cats[c].get("intensa") or pierna) for a in activities if day_of(a) == ayer):
        return None
    resto = tt("motor.aviso.resto_larga") if sesion["tipo"] == "larga" else tt("motor.aviso.resto_calidad")
    return tt("motor.aviso.pierna", resto=resto)


def faltan(status: list) -> list:
    """Lo que falta de la semana, estructurado y en orden del plan: [{k: facil, n}, {k: calidad}, {k: larga}]. Única fuente:
    `faltan_texto` (Hoy y Plan) y la web (perfil, tarjetas del grupo) lo leen."""
    pend = [s for s in status if s["estado"] == "pendiente"]
    facil = sum(1 for s in pend if s["tipo"] not in ("larga", "calidad", "prueba"))
    out = [{"k": "facil", "n": facil}] if facil else []
    if any(s["tipo"] == "calidad" for s in pend):
        out.append({"k": "calidad"})
    if any(s["tipo"] in ("larga", "prueba") for s in pend):
        out.append({"k": "larga"})
    return out


def faltan_texto(status: list) -> str:
    """«Te faltan: 1 fácil y la larga» (en orden del plan). "" si no falta ninguna."""
    partes = [(tt("motor.faltan.facil_uno") if f["n"] == 1 else tt("motor.faltan.facil_n", n=f["n"])) if f["k"] == "facil"
              else tt("motor.faltan.calidad") if f["k"] == "calidad" else tt("motor.faltan.larga") for f in faltan(status)]
    if not partes:
        return ""
    lista = partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " " + tt("motor.faltan.y") + " " + partes[-1]
    return tt("motor.faltan.frase", lista=lista)


def today_card(day: date, light: dict, status: list, activities: list, config: dict) -> dict:
    """Qué mostrar hoy. light = resultado de traffic_light; status = assign_sessions."""
    hoy = [a for a in activities if day_of(a) == day]
    cats = {c["id"]: c for c in config.get("categorias", [])}
    hechas = [classify(a, config) for a in hoy]
    hay_run = "run" in hechas
    # Solo una actividad intensa que Garmin ya registró hoy ocupa el día; nunca se adivina por el día de la semana.
    otra = next((i for i in hechas if i in cats and cats[i]["intensa"]), None)
    aviso = tt("motor.aviso.repetir") if light.get("repetir_semana") else None
    base = {"version": None, "sesion_id": None, "aviso": aviso, "proxima_id": None}
    manana = (_elegir_pendiente(day + timedelta(days=1), status)[0] or {}).get("id") if status else None
    if otra:
        nombre = cats[otra]["nombre"]
        return {"tipo": "otra", "categoria": nombre, "texto": tt("motor.hoy.otra", nombre=nombre), **{**base, "proxima_id": manana}}
    if hay_run:
        return {"tipo": "hecha_hoy", "texto": tt("motor.hoy.hecha"), **{**base, "proxima_id": manana}}
    if not status:
        return {"tipo": "sin_plan", "texto": tt("motor.hoy.sin_plan"), **base}
    sesion, aviso_larga = _elegir_pendiente(day, status)
    if sesion is None:
        return {"tipo": "completa", "texto": tt("motor.hoy.completa"), **base}
    sin_datos = light["color"] == "sin_datos"
    version = "normal" if sin_datos else {"verde": "normal", "amarillo": "suave", "rojo": "descanso"}[light["color"]]
    aviso = _unir_avisos(aviso, aviso_larga, aviso_intenso_ayer(day, sesion, activities, config),
                         tt("motor.aviso.sin_datos") if sin_datos else None)
    return {"tipo": "sesion", "texto": tt("motor.hoy.siguiente", version=tt(f"motor.version.{version}")),
            "version": version, "sesion_id": sesion["id"], "aviso": aviso, "proxima_id": None}


def opciones_hoy(version: str | None, sesion: dict | None) -> list[str]:
    """Versiones que se pueden elegir hoy, en orden. Sin versión suave en el plan no hay nada que elegir."""
    if version not in ("normal", "suave", "descanso") or not sesion or not sesion.get("easy") or sesion.get("carrera"):
        return []
    return ["descanso", "suave", "normal"] if version == "descanso" else ["suave", "normal"]


def _tiene_opcionales(pasos: list) -> bool:
    return any(p.get("optional") or _tiene_opcionales(p.get("steps", [])) for p in pasos)


def _min_z3_planeados(pasos: list) -> int:
    return sum(p["times"] * _min_z3_planeados(p["steps"]) if p["kind"] == "repeat"
               else p["minutes"] if p["zone"] in ("Z3", "Z4", "Z5") else 0 for p in pasos)


def minutos_planeados(pasos: list) -> dict:
    """Minutos por zona de los pasos de una sesión (con `repeat`; una sola zona por paso: zona_unica). Los pasos
    opcionales no cuentan: si los haces, suman a lo hecho pero no los exige el plan."""
    out = {}
    for p in pasos:
        if p["kind"] == "repeat":
            for z, mi in minutos_planeados(p["steps"]).items():
                out[z] = out.get(z, 0) + p["times"] * mi
        elif not p.get("optional"):
            z = tipos.zona_unica(p)
            out[z] = out.get(z, 0) + p["minutes"]
    return out


def plan_vs_real(pasos: list, minutos_z: dict, done_ratio: float = 0.7) -> list:
    """Plan vs real por zona. Para cada zona planeada Z ≥ Z2, lo planeado en Z o más contra lo hecho en Z o más (lo que
    haces en una zona más alta cuenta para la de abajo). `ok` = hecho ≥ done_ratio × plan (la FC tarda en subir).
    [{zona, plan_min, hecho_min, pct, ok}] de la zona más alta a la más baja."""
    plan = minutos_planeados(pasos)
    out = []
    for z in reversed(ZONAS[1:]):
        if not plan.get(z):
            continue
        arriba = ZONAS[ZONAS.index(z):]
        plan_acum = sum(plan.get(k, 0) for k in arriba)
        hecho = sum(minutos_z.get(k, 0.0) for k in arriba)
        out.append({"zona": z, "plan_min": round(plan_acum, 1), "hecho_min": round(hecho, 1),
                    "pct": round(hecho / plan_acum * 100), "ok": hecho + 0.05 >= done_ratio * plan_acum})
    if out and out[0]["zona"] in ("Z3", "Z4"):   # zona alta planeada: avisa si pasaste mucho por encima de ella
        tope = out[0]
        arriba = sum(minutos_z.get(k, 0.0) for k in ZONAS[ZONAS.index(tope["zona"]) + 1:])
        tope["arriba_min"] = round(arriba, 1)
        tope["mucho_arriba"] = arriba > max(2.0, 0.25 * tope["plan_min"])
    return out


def run_check(activity: dict, session, config=None, minutos_z=None, suave: bool = False) -> dict:
    """¿Lo hice bien?: minutos sobre el techo de Z2 (Z3+Z4+Z5) vs la tolerancia, y el plan vs real por zona
    (si la corrida tiene sesión y minutos por zona; con `suave`, contra la versión suave)."""
    zm = minutos_z if minutos_z is not None else zone_minutes(activity)
    sobre = round(zm["Z3"] + zm["Z4"] + zm["Z5"], 1)
    tolerancia = (config or {}).get("ceiling_tolerance_min", 2)
    if session and _tiene_opcionales(session.get("steps", [])):
        tolerancia += 2
    if (session or {}).get("tipo") in ("variada", "calidad"):   # su Z3+ es parte del plan
        tolerancia += _min_z3_planeados(session.get("steps", []))
    es_5k = (session or {}).get("prueba") == "5k"
    if es_5k:   # 5 km a tope: pasarse de Z2 es la idea
        tolerancia = activity["duration"] / 60
    out = {"min_sobre_techo": sobre, "tolerancia_min": round(tolerancia, 1), "techo_ok": sobre <= tolerancia}
    if session and minutos_z is not None and not es_5k:
        pasos = session["easy"]["steps"] if suave else session["steps"]
        out["plan_vs_real"] = plan_vs_real(pasos, minutos_z, (config or {}).get("done_ratio", 0.7))
    return out


def sugerencia_semana(hechas, total, dias_rojos: int, carga, carga_anterior, config: dict):
    """Sugerencia por reglas conservadoras del resumen de la semana pasada: {"tipo", "texto"} o None. En orden:
    pocas sesiones hechas (con plan) o muchos días rojos → repetir; carga muy por encima de la anterior → semana pesada;
    todo hecho y sin rojos → seguir el plan. Solo sugiere: repetir la semana se hace desde Ajustes."""
    pocas = total is not None and hechas < config.get("resumen_min_sesiones", 2)
    if pocas or dias_rojos >= config.get("resumen_dias_rojos", 2):
        tipo = "repetir"
    elif carga_anterior and carga > config.get("resumen_carga_alta", 1.3) * carga_anterior:
        tipo = "pesada"
    elif total and hechas >= total and dias_rojos == 0:
        tipo = "sigue"
    else:
        return None
    texto = tt(f"motor.sugerencia.{tipo}")
    return {"tipo": tipo, "titulo": tt(f"motor.sugerencia_t.{tipo}"), "texto": texto}
