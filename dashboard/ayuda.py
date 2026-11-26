"""Página de ayuda armada con la config y el plan de cada persona (lógica pura, sin red ni archivos).

`armar_ayuda(config, plan, zonas, fc_ref)` devuelve una lista de bloques de texto plano:
    [{"titulo": str, "parrafos": [str], "lista": [{"t": str | None, "x": str}]}]
Solo habla de lo que su plan tiene: caminatas, picos de Z3, variada o calidad (con sus tipos) y su tipo de prueba.
El sitio solo pinta estos bloques.
"""

from i18n import lista as _lista, tt
from plan_i18n import nombre as _nombre_ses

PRUEBAS = ("fc_fija", "trote_continuo", "5k")   # los textos de cada prueba salen del catálogo (motor.ayuda.pru.*)


def _t(clave: str, **v) -> str:
    return tt("motor.ayuda." + clave, **v)


def _dias_pierna(c: dict) -> list:
    return [tt("motor.dias_largos").split(",")[d] for d in c["dias_pierna"]]


def _pasos(pasos: list):
    for p in pasos:
        if p["kind"] == "repeat":
            yield from _pasos(p["steps"])
        else:
            yield p


def _unicos(items) -> list:
    return list(dict.fromkeys(items))


def _item(titulo, texto) -> dict:
    return {"t": titulo, "x": texto}


def _semaforo(c: dict) -> dict:
    ok = lambda k: c.get(k)  # noqa: E731
    return {"titulo": _t("sem.titulo"), "parrafos": [_t("sem.intro")],
            "lista": [
        _item(_t("sem.hrv_t"), _t("sem.hrv")),
        _item(_t("sem.rhr_t"), _t("sem.rhr", x=f"{ok('rhr_tolerance_bpm'):g}")),
        _item(_t("sem.sueno_t"), _t("sem.sueno", x=f"{ok('sleep_min_hours'):g}")),
        _item(_t("sem.esfuerzo_t"), _t("sem.esfuerzo", x=f"{ok('esfuerzo_duro'):g}")),
        _item(_t("sem.verde_t"), _t("sem.verde")),
        _item(_t("sem.amarillo_t"), _t("sem.amarillo")),
        _item(_t("sem.rojo_t"), _t("sem.rojo")),
        _item(_t("sem.sin_t"), _t("sem.sin"))]}


def _sesiones(c: dict, plan: dict, zonas: dict) -> dict:
    semanas = plan.get("weeks") or []
    base = semanas[0]["sessions"] if semanas else []
    n = len(base)
    todas = [s for w in semanas for s in w["sessions"]]
    z2 = [_nombre_ses(s["name"]) for s in base if s.get("tipo") == "z2"]
    larga = next((s for s in base if s.get("tipo") == "larga"), None)
    variadas = _unicos(_nombre_ses(s["name"]).split(" · ", 1)[-1] for s in todas if s.get("tipo") == "variada")
    calidad = _unicos(_nombre_ses(s["name"]).split(" · ", 1)[-1] for s in todas if s.get("tipo") == "calidad")
    picos = any(p.get("optional") for s in todas for p in _pasos(s["steps"]))
    descargas = [w["n"] for w in semanas if w["kind"] == "descarga" and not (w["n"] == semanas[-1]["n"] and "prueba" in w["focus"].lower())]
    z2_txt = _t("ses.z2_txt", a=zonas["Z2"][0], b=zonas["Z2"][1])
    lista = []
    if z2:
        lista.append(_item(_lista(z2), _t("ses.z2", z2=z2_txt) + (_t("ses.z2_techo") if not c["caminatas"] else "")))
    if c["caminatas"]:
        reps = [(p["steps"][0]["minutes"], p["steps"][1]["minutes"]) for w in semanas for s in w["sessions"]
                for p in s["steps"] if p["kind"] == "repeat" and len(p["steps"]) >= 2]
        if reps:
            ini, fin = reps[0], max(reps)
            lista.append(_item(_t("ses.tc_t"), _t("ses.tc", a=ini[0], b=ini[1], c=fin[0], d=fin[1])))
    if variadas:
        lista.append(_item(_t("ses.var_t"), _t("ses.var", lista=_lista(variadas))))
    if calidad:
        lista.append(_item(_t("ses.cal_t"), _t("ses.cal", lista=_lista(calidad))))
    if larga:
        lista.append(_item(_t("ses.larga_t"), _t("ses.larga")
                           + (_t("ses.larga_pierna", dias=_lista(_dias_pierna(c))) if c["dias_pierna"] else "")))
    if picos:
        lista.append(_item(_t("ses.picos_t"), _t("ses.picos")))
    if descargas:
        lista.append(_item(_t("ses.desc_t"), _t("ses.desc", lista=_lista([str(x) for x in descargas]))
                           + (_t("ses.desc_punto") if c["caminatas"] else _t("ses.desc_cont"))))
    done = round(c["done_ratio"] * 100)
    generico = lambda s: _t("ses.generico_cal") if s.get("tipo") == "calidad" else _t("ses.generico_var") if s.get("tipo") == "variada" else _nombre_ses(s["name"])  # noqa: E731
    otras = [generico(s) for s in base if s.get("tipo") != "larga"]
    lista += [
        _item(_t("ses.asig_t"), _t("ses.asig", done=done, otras=_lista(otras) if otras else _t("ses.otras"))),
        _item(_t("ses.hecha_t"), _t("ses.hecha", done=done)),
        _item(_t("ses.bien_t"), _t("ses.bien", x=f"{c['ceiling_tolerance_min']:g}")
              + (_t("ses.bien_picos") if picos else "")
              + _t("ses.bien_pvr", done=done)),
        _item(_t("ses.tiempo_t"), _t("ses.tiempo") + (_t("ses.tiempo_cam") if c["caminatas"] else _t("ses.tiempo_punto")))]
    texto_n = _t("ses.n", n=n) if n != 1 else _t("ses.n1")
    nombres = [generico(s) for s in base]
    return {"titulo": _t("ses.titulo"), "parrafos": [f"{texto_n}: {_lista(nombres)}."], "lista": lista}


def _prueba(c: dict, plan: dict, fc_ref: int):
    semanas = plan.get("weeks") or []
    ses = next((s for s in (semanas[-1]["sessions"] if semanas else []) if s.get("tipo") == "prueba"), None)
    if not ses:
        return None
    tipo = ses["prueba"]
    como = _t(f"pru.{tipo}", fc_ref=fc_ref)
    previa = any(p["tipo"] == tipo for p in c.get("pruebas", []))
    base = _t("pru.previa") if previa else _t("pru.p2_b_base", base=_t(f"pru.base_{tipo}"))
    return {"titulo": _t("pru.titulo"), "parrafos": [
        _t("pru.p1", n=semanas[-1]["n"], como=como),
        _t("pru.p2_a", x=base, ir=_t("pru.ir_web" if c.get("modo") == "web" else "pru.ir_cli"))], "lista": []}


def _mejora(c: dict, fc_ref: int) -> dict:
    lista = [
        _item(_t("mej.ritmo_t", fc=fc_ref), _t("mej.ritmo", fc=fc_ref)
              + (_t("mej.ritmo_cal") if c["intensidad"] == "calidad" else "") + _t("mej.ritmo_fin")),
        _item(_t("mej.deriva_t"), _t("mej.deriva"))]
    if c["caminatas"]:
        lista.append(_item(_t("mej.trote_t"), _t("mej.trote")))
    lista.append(_item(_t("mej.esfuerzo_t"), _t("mej.esfuerzo")))
    return {"titulo": _t("mej.titulo"), "parrafos": [], "lista": lista}


def _zonas(c: dict, zonas: dict) -> dict:
    cats = [x["nombre"] for x in c["categorias"]]
    return {"titulo": _t("zon.titulo"), "parrafos": [
        _t("zon.p1", max=f"{c['max_hr']:g}"),
        _t("zon.p2", lista=_lista(cats + [tt("motor.ui.corridas")]))],
        "lista": [_item(z, _t("zon.fila", a=zonas[z][0], b=zonas[z][1], sig=_t(f"zon.{z}"))) for z in ("Z1", "Z2", "Z3", "Z4", "Z5")]}


def armar_ayuda(config: dict, plan: dict, zonas: list, fc_ref: int) -> list:
    """Bloques de ayuda de esta persona. `zonas`: [(zona, piso, techo)] (las de hoy). Sin plan, se omite lo que depende de él."""
    z = {nombre: (lo, hi) for nombre, lo, hi in zonas}
    bloques = [_semaforo(config)]
    if plan.get("weeks"):
        bloques.append(_sesiones(config, plan, z))
        prueba = _prueba(config, plan, fc_ref)
        if prueba:
            bloques.append(prueba)
    bloques += [_mejora(config, fc_ref), _zonas(config, z)]
    return bloques
