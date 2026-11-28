"""Composición corporal y hoja InBody."""

from dashboard.i18n import tt


def _medicion(x: dict) -> dict:
    """Una medición InBody para publicar (lista blanca: sin nota ni hora); masa grasa calculada si falta."""
    grasa = x.get("masa_grasa_kg")
    out = {"fecha": x["fecha"], "peso_kg": x["peso_kg"], "mme_kg": x["mme_kg"], "pgc": x["pgc"],
           "masa_grasa_kg": grasa if grasa is not None else round(x["peso_kg"] * x["pgc"] / 100, 1)}
    for k in ("puntuacion", "grasa_visceral"):
        if x.get(k) is not None:
            out[k] = x[k]
    return out


def pos_escala(valor: float, escala: list) -> float:
    """Dónde cae `valor` en una escala de la hoja InBody, de 0 a 1. Los ticks ocupan el mismo ancho (la escala de
    grasa no es lineal) y dentro de cada tramo se interpola; fuera de la escala se recorta a los extremos."""
    n = len(escala) - 1
    if valor <= escala[0]:
        return 0.0
    if valor >= escala[-1]:
        return 1.0
    i = max(k for k in range(n) if escala[k] <= valor)
    return round((i + (valor - escala[i]) / (escala[i + 1] - escala[i])) / n, 4)


def zona_rango(valor: float, normal: list) -> str:
    """"bajo", "normal" o "alto" según el rango normal [min, max] (los bordes cuentan como normal)."""
    return "bajo" if valor < normal[0] else "alto" if valor > normal[1] else "normal"


def _barra_inbody(id_: str, nombre: str, unidad: str, d: dict, valor_pos: float, valor_txt: float) -> dict:
    out = {"id": id_, "nombre": nombre, "unidad": unidad, "valor": valor_txt, "escala": d["escala"], "normal": d["normal"],
           "normal_pos": [pos_escala(d["normal"][0], d["escala"]), pos_escala(d["normal"][1], d["escala"])],
           "pos": pos_escala(valor_pos, d["escala"]), "zona": zona_rango(valor_pos, d["normal"])}
    if d.get("pct") is not None:
        out["pct"] = d["pct"]
    if d.get("pct_estimado"):
        out["estimado"] = True
    return out


def hoja_inbody(med: dict) -> dict:
    """Lo que pinta la hoja InBody de una medición completa (todo precalculado): análisis músculo-grasa,
    obesidad, control de peso, investigación, composición y segmental. Cada parte se omite si la hoja no la trae."""
    out = {"fecha": med["fecha"]}
    mg = med.get("musculo_grasa")
    if mg:
        filas = [("peso", tt("motor.ib.peso"), "kg"), ("mme", tt("motor.ib.mme"), "kg"), ("masa_grasa", tt("motor.ib.masa_grasa"), "kg")]
        out["musculo_grasa"] = [_barra_inbody(i, n, u, mg[i], mg[i]["pct"], mg[i]["valor"]) for i, n, u in filas if i in mg]
    ob = med.get("obesidad")
    if ob:
        out["obesidad"] = [_barra_inbody(i, n, u, ob[i], ob[i]["valor"], ob[i]["valor"])
                           for i, n, u in (("imc", tt("motor.ib.imc"), "kg/m²"), ("pgc", tt("motor.ib.pgc"), "%")) if i in ob]
    rangos = []
    for grupo, clave, filas in ((tt("motor.ib.g_investigacion"), "investigacion",
                                 (("tmb_kcal", tt("motor.ib.tmb"), "kcal"), ("cintura_cadera", tt("motor.ib.cintura_cadera"), ""),
                                  ("grado_obesidad_pct", tt("motor.ib.grado_obesidad"), "%"))),
                                (tt("motor.ib.g_composicion"), "composicion",
                                 (("agua_l", tt("motor.ib.agua"), "L"), ("proteinas_kg", tt("motor.ib.proteinas"), "kg"),
                                  ("minerales_kg", tt("motor.ib.minerales"), "kg"), ("masa_grasa_kg", tt("motor.ib.masa_grasa"), "kg"),
                                  ("peso_kg", tt("motor.ib.peso"), "kg")))):
        for k, nombre, unidad in filas:
            v = (med.get(clave) or {}).get(k)
            if v:
                rangos.append({"grupo": grupo, "nombre": nombre, "unidad": unidad, "valor": v[0], "min": v[1], "max": v[2],
                               "zona": zona_rango(v[0], [v[1], v[2]])})
    if rangos:
        out["rangos"] = rangos
    for k in ("control_peso", "investigacion", "composicion", "segmental_magra", "segmental_grasa"):
        if med.get(k):
            out["composicion_corporal" if k == "composicion" else k] = med[k]
    return out


def composicion(inbody):
    """Composición corporal: mediciones por fecha, prime, última con deltas y meta de superar el prime, más lo de la
    hoja InBody (barras, historial, puntuación, visceral y secciones extra). None sin datos."""
    if not inbody or not inbody.get("mediciones"):
        return None
    crudas = sorted(inbody["mediciones"], key=lambda x: x["fecha"])
    meds = sorted((_medicion(x) for x in inbody["mediciones"]), key=lambda x: x["fecha"])
    prime = next((x for x in meds if x["fecha"] == inbody.get("prime")), None) or min(meds, key=lambda x: x["pgc"])
    ultima, previa = meds[-1], (meds[-2] if len(meds) > 1 else None)
    delta = lambda k: None if previa is None else round(ultima[k] - previa[k], 1)  # noqa: E731
    rango = next((x.get("grasa_visceral_rango") for x in reversed(crudas) if x.get("grasa_visceral_rango")), [1, 9])
    out = {"mediciones": meds,
           "prime": {k: prime[k] for k in ("fecha", "pgc", "mme_kg", "peso_kg", "masa_grasa_kg")},
           "ultima": {**ultima, "delta_pgc": delta("pgc"), "delta_mme": delta("mme_kg"), "delta_peso": delta("peso_kg")},
           "meta": {"faltan_pgc": max(0.0, round(ultima["pgc"] - prime["pgc"], 1)),
                    "mme_ok": ultima["mme_kg"] >= prime["mme_kg"],
                    "faltan_mme": max(0.0, round(prime["mme_kg"] - ultima["mme_kg"], 1))},
           "visceral_rango": rango,
           "historial": [{"fecha": x["fecha"], "peso_kg": x["peso_kg"], "mme_kg": x["mme_kg"], "pgc": x["pgc"],
                          "es_prime": x["fecha"] == prime["fecha"]} for x in meds]}
    # puntuación: todas las mediciones desde la primera con puntos; las que no la tienen van con puntos None (hueco)
    con = [i for i, x in enumerate(meds) if x.get("puntuacion") is not None]
    if con:
        out["puntuacion"], previo = [], None
        for x in meds[con[0]:]:
            p = x.get("puntuacion")
            out["puntuacion"].append({"fecha": x["fecha"], "puntos": p,
                                      "delta": p - previo if p is not None and previo is not None else None})
            previo = p if p is not None else previo
    visc = next((x for x in reversed(meds) if x.get("grasa_visceral") is not None), None)
    if visc:
        out["visceral"] = {"fecha": visc["fecha"], "valor": visc["grasa_visceral"], "rango": rango,
                           "zona": zona_rango(visc["grasa_visceral"], rango)}
    hoja = next((x for x in reversed(crudas) if x.get("musculo_grasa")), None)
    if hoja:
        out["hoja"] = hoja_inbody(hoja)
    return out
