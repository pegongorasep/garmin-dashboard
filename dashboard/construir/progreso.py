"""Pruebas, mejora, números, días y detalles."""
from dashboard import metrics as m, semanal
from dashboard.i18n import tt
from datetime import date, timedelta
from dashboard.construir.actividades import historial_corridas
from dashboard.construir.comun import monday, r1, r2, ultima_semana, week_assignment


def base_prueba(tipo: str, filas: list, data: dict, config: dict):
    """Contra qué se compara la primera prueba: ritmo a FC ref (fc_fija) o % de trote (trote_continuo) promedio de las
    semanas 1–2 del plan; en 5k, la mejor marca de 5 km antes del inicio del plan. None si no hay."""
    inicio = date.fromisoformat(config["plan_start"])
    if tipo == "5k":
        previas = [(a["fastestSplit_5000"], a["startTimeLocal"][:10]) for a in historial_corridas(data, config)
                   if a.get("fastestSplit_5000") and a["startTimeLocal"][:10] < inicio.isoformat()]
        mejor = min(previas, default=None)
        return None if mejor is None else {"fuente": "mejor_5k", "fecha": mejor[1], "valor": round(mejor[0])}
    primeras = [f for f in filas if inicio <= date.fromisoformat(f["fecha"]) < inicio + timedelta(days=14)]
    v = m.promedio([f["ritmo_ref_s"] if tipo == "fc_fija" else f["pct_trote"] for f in primeras])
    return None if v is None else {"fuente": "inicio", "fecha": None, "valor": round(v, 1 if tipo == "trote_continuo" else 0)}


def prueba_resultado(data: dict, config: dict, plan: dict):
    """Resultado de la prueba de la última semana del plan y su comparación; None si el plan no trae prueba o no se hizo.
    {tipo, fecha, estado, valor, km, base, dif, mejor}. Se compara contra la última prueba del mismo tipo de
    `corrida.pruebas` y, si no hay, contra la base (semanas 1–2, o la mejor marca de 5 km)."""
    ini = ultima_semana(config, plan)
    semana, estado = week_assignment(ini, data, config, plan, hasta=ini + timedelta(days=6))
    ses = next((s for s in (semana or {}).get("sessions", []) if s.get("tipo") == "prueba"), None)
    e = next((e for e in estado if ses and e["id"] == "prueba" and e["fecha"]), None)
    if ses is None or e is None:
        return None
    a = next(a for a in data["activities"] if m.classify(a, config) == "run"
             and m.day_of(a).isoformat() == e["fecha"] and a["duration"] / 60 == e["minutos"])
    fila = m.run_rows([a], data["details"], config)[0]
    serie = (data["details"].get(str(m.id_de(a))) or {}).get("serie") or []
    medido = m.valor_prueba(ses["prueba"], serie, fila["pct_trote"])
    km = (data["details"].get(str(m.id_de(a))) or {}).get("ritmos_km") or []
    if medido is None and ses["prueba"] == "5k" and len(km) >= 5:   # sin serie, el ritmo por km de una carrera sirve
        medido = {"valor": sum(km[:5]), "km": 5.0}
    previas = [p for p in config.get("pruebas", []) if p["tipo"] == ses["prueba"] and p["fecha"] < e["fecha"]]
    base = ({"fuente": "prueba", "fecha": previas[-1]["fecha"], "valor": previas[-1]["valor"]} if previas
            else base_prueba(ses["prueba"], m.run_rows([a2 for a2 in data["activities"] if m.classify(a2, config) == "run"],
                                                         data["details"], config), data, config))
    out = {"tipo": ses["prueba"], "fecha": e["fecha"], "estado": e["estado"], "valor": None, "km": None,
           "base": base, "dif": None, "mejor": None}
    if medido:
        out.update(valor=medido["valor"], km=medido["km"], seguido=medido.get("seguido"), **(m.comparar_prueba(ses["prueba"], medido["valor"], base) or {}))
    return out


def _tiempo(seg: float) -> str:
    """mm:ss, o h:mm:ss si pasa de una hora."""
    t = round(seg)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else m._mmss(t)


def texto_prueba(p: dict) -> dict:
    """Textos ya armados de la prueba para los cuadritos: valor, comparación y si mejoró (None = igual o sin base)."""
    tipo, v, base = p["tipo"], p["valor"], p.get("base")
    nombre = tt(f"motor.prueba.{tipo}")
    fmt = (lambda x: (tt("motor.prueba.seguidos", x=f"{x:.0f}") if x >= m.PRUEBA_SEGUIDO_PCT else tt("motor.prueba.pct_trote", x=f"{x:.0f}")) if tipo == "trote_continuo"
           else _tiempo(x) if tipo == "5k" else f"{m._mmss(x)} /km")
    out = {"nombre": nombre, "valor": None if v is None else fmt(v), "cambio": None, "mejor": p.get("mejor")}
    if v is None:
        out["cambio"] = tt("motor.cuadro.sin_resultado")
    elif base is None or p.get("dif") is None:
        out["cambio"] = tt("motor.cuadro.sin_base")
    else:
        donde = tt({"prueba": "motor.cuadro.donde_prueba", "mejor_5k": "motor.cuadro.donde_mejor_5k"}.get(base["fuente"], "motor.cuadro.donde_inicio"))
        mag = (tt("motor.cuadro.puntos", n=f"{abs(p['dif']):.0f}") if tipo == "trote_continuo" else _tiempo(abs(p["dif"])) if tipo == "5k" else f"{abs(p['dif']):.0f} s/km")
        if p["mejor"] is None:
            out["cambio"] = tt("motor.cuadro.igual", donde=donde)
        else:
            out["cambio"] = tt("motor.cuadro.vs", flecha="▲" if p["dif"] > 0 else "▼", mag=mag, donde=donde,
                              res=tt("motor.cuadro.mejor" if p["mejor"] else "motor.cuadro.peor"))
    return out


def build_mejora(hoy: date, filas: list, zonas: list, data=None, config=None, plan=None) -> dict:
    """Cómo vas mejorando, ya calculado para los cuadritos: ritmo a la FC de referencia (promedio de las últimas 4 corridas
    válidas contra las semanas 1–2 del plan), última deriva válida y, si ya hay, el resultado de la prueba.
    `modo` ("ritmo" sin caminatas recientes, si no "trote") lo usa la fila de números. Cada cuadrito trae su `motivo`
    cuando no hay dato."""
    desde = monday(hoy) - timedelta(weeks=4)
    recientes = [f for f in filas if date.fromisoformat(f["fecha"]) >= desde]
    modo = "ritmo" if recientes and not any((f["caminatas"] or 0) > 0 for f in recientes) else "trote"
    ref = m.fc_referencia(zonas)
    validas = [f for f in filas if f["ritmo_ref_s"]]
    ult4 = validas[-4:]
    actual = m.promedio([f["ritmo_ref_s"] for f in ult4])
    inicio = None
    if config is not None:
        ini = date.fromisoformat(config["plan_start"])
        inicio = m.promedio([f["ritmo_ref_s"] for f in validas if ini <= date.fromisoformat(f["fecha"]) < ini + timedelta(days=14)])
    ritmo = {"fc_ref": ref, "n": len(ult4), "actual_s": None, "inicio_s": None, "dif_s": None, "mejora": None,
             "valor": None, "cambio": None, "motivo": None}
    if actual is None:
        ritmo["motivo"] = tt("motor.mejora.sin_aire", ref=ref)
    else:
        ritmo.update(actual_s=round(actual), valor=f"{m._mmss(actual)} /km",
                     motivo=tt("motor.mejora.promedio", n=len(ult4)) if len(ult4) > 1 else tt("motor.mejora.ultima"))
        if inicio is None:
            ritmo["cambio"] = None
            ritmo["motivo"] += tt("motor.mejora.sin_inicio")
        else:
            dif = round(actual) - round(inicio)
            ritmo.update(inicio_s=round(inicio), dif_s=dif, mejora=None if dif == 0 else dif < 0,
                         cambio=tt("motor.mejora.igual_inicio") if dif == 0 else tt("motor.mejora.vs_inicio", flecha="▲" if dif > 0 else "▼", n=abs(dif)))
    der = next((f for f in reversed(filas) if f["deriva_pct"] is not None), None)
    deriva = {"valor": None, "fecha": None, "ok": None, "motivo": None}
    if der is None and (config.get("sensor") == "muñeca" or any(f.get("pulso") == "muñeca" for f in filas)):
        deriva["motivo"] = tt("motor.mejora.deriva_muneca")
    elif der is None:
        deriva["motivo"] = tt("motor.mejora.deriva_sin")
    else:
        deriva.update(valor=f"{der['deriva_pct']:.1f} %", fecha=der["fecha"], ok=der["deriva_ok"],
                      motivo=tt("motor.mejora.deriva_ok"))
    prueba = None
    if data is not None and config is not None and plan is not None and plan.get("weeks"):
        res = prueba_resultado(data, config, plan)
        prueba = None if res is None else {**res, **texto_prueba(res)}
    return {"modo": modo, "ritmo": ritmo, "deriva": deriva, "prueba": prueba}


def build_numeros(hoy: date, filas: list, modo: str, periodos=(4, 8, 12)) -> dict:
    """Fila de números de Progreso por periodo (4, 8 o 12 semanas): corridas, minutos y km por semana y ritmo a la FC de
    referencia (modo "ritmo") o % trote (modo "trote"), con el valor del periodo anterior y el cambio. `filas` es run_rows;
    usa el mismo conjunto de corridas por periodo que la frase del periodo (m.periodo_filas)."""
    def periodo(k, atras):
        g = m.periodo_filas(filas, hoy, k, atras)
        if not g:
            return None
        clave = "ritmo_ref_s" if modo == "ritmo" else "pct_trote"
        return {"corridas": len(g) / k, "minutos": sum(f["minutos"] for f in g) / k, "km": sum(f["km"] for f in g) / k,
                "extra": m.promedio([f.get(clave) for f in g])}
    campos = [("corridas", "corridas"), ("minutos", "minutos"), ("km", "km"), ("extra", "ritmo_ref" if modo == "ritmo" else "pct_trote")]
    out = {}
    for k in periodos:
        ahora, antes = periodo(k, 0), periodo(k, 1)
        items = []
        for campo, id_ in campos:
            v = None if ahora is None else ahora[campo]
            a = None if antes is None else antes[campo]
            delta = None if v is None or a is None else v - a
            if id_ == "ritmo_ref":
                v, a, delta = (None if x is None else round(x) for x in (v, a, delta))
            else:
                v, a, delta = (None if x is None else round(x, 1) for x in (v, a, delta))
            mejor = None if not delta else (delta < 0 if id_ == "ritmo_ref" else delta > 0)
            items.append({"id": id_, "valor": v, "anterior": a, "delta": delta, "bueno": mejor})
        out[str(k)] = items
    caminatas = {str(k): any((f["caminatas"] or 0) > 0 for f in m.periodo_filas(filas, hoy, k)) for k in periodos}
    return {"modo": modo, "periodos": out, "caminatas": caminatas}


def build_days(hoy: date, data: dict) -> list:
    """84 días de recuperación con promedios de 7 días (se calculan con 6 días extra antes)."""
    hrv = {r["calendarDate"]: r for r in data["hrv"]}
    daily = {r["calendarDate"]: r for r in data["daily_summaries"]}
    sleep = {r["calendarDate"]: r for r in data["sleep"]}
    fechas = [(hoy - timedelta(days=i)).isoformat() for i in range(89, -1, -1)]
    horas = lambda f: None if (seg := (sleep.get(f) or {}).get("sleepTimeSeconds")) is None else round(seg / 3600, 2)  # noqa: E731
    v_hrv = [hrv.get(f, {}).get("lastNightAvg") for f in fechas]
    v_rhr = [((daily.get(f) or {}).get("heartRate") or {}).get("restingValue") for f in fechas]
    v_sue = [horas(f) for f in fechas]
    p_hrv, p_rhr, p_sue = (m.rolling_mean(v) for v in (v_hrv, v_rhr, v_sue))
    dias = []
    for i in range(6, 90):
        base = hrv.get(fechas[i], {}).get("baseline") or {}
        dias.append({"fecha": fechas[i], "hrv": v_hrv[i], "hrv_7d": r1(p_hrv[i]),
                     "hrv_base_baja": base.get("balancedLow"), "hrv_base_alta": base.get("balancedUpper"),
                     "rhr": v_rhr[i], "rhr_7d": r1(p_rhr[i]), "sueño_h": v_sue[i], "sueño_7d": r2(p_sue[i])})
    return dias


def build_details(hoy: date, data: dict, config: dict, fc_max: dict, reloj, plan: dict = None) -> dict:
    ini, acts = monday(hoy), data["activities"]
    carga = lambda s: {k: r1(v) for k, v in m.week_load(acts, data["details"], s, config).items()}  # noqa: E731
    dist = m.week_distribution(acts, ini)
    semanas = []
    for s in semanal.serie_semanas(hoy, plan, config):
        c = m.week_load(acts, data["details"], s, config)
        semanas.append({"inicio": s.isoformat(), "actual": s == ini,
                        "cargas": {k["id"]: r1(c[k["id"]]) for k in config["categorias"]},
                        "carga_corrida": r1(c["run"])})
    return {
        "distribucion": {"minutos": {z: r1(v) for z, v in dist["minutos"].items()},
                         "bajo": r1(dist["bajo"]), "limbo": r1(dist["limbo"]), "alto": r1(dist["alto"])},
        "carga": carga(ini), "carga_anterior": carga(ini - timedelta(days=7)), "carga_semanas": semanas,
        "fc_max": {**fc_max, "config": config["max_hr"], "fuente": "reloj" if reloj else "respaldo"},
        "umbrales": {k: config[k] for k in ("rhr_tolerance_bpm", "sleep_min_hours", "esfuerzo_duro",
                                            "max_hr", "max_hr_floor", "max_hr_review_above", "zone_pcts",
                                            "ceiling_tolerance_min", "done_ratio")},
    }
