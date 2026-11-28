"""Sesiones del plan: pasos, rampas, rachas, estructura de calidad y etiquetas."""
from dashboard import plan_i18n, tipos
from dashboard.i18n import tt


# --- plan: zonas por nombre -> lpm ---

def lpm_range(zone: str, zonas: list):
    """'Z2' -> [piso, techo]; 'Z1-Z2' -> piso de Z1 a techo de Z2."""
    por_nombre = {z: (lo, hi) for z, lo, hi in zonas}
    try:
        a, b = zone.split("-")[0], zone.split("-")[-1]
        return [por_nombre[a][0], por_nombre[b][1]]
    except KeyError:
        return None


def convert_steps(steps: list, zonas: list) -> list:
    out = []
    for s in steps:
        if s["kind"] == "repeat":
            out.append({"kind": "repeat", "times": s["times"], "steps": convert_steps(s["steps"], zonas)})
        else:
            zona = tipos.zona_unica(s)
            # planes viejos: los 10' Z2 del inicio de una calidad venían como "calentamiento"; son un tramo normal
            kind = "run" if s["kind"] == "warmup" and zona not in ("Z0", "Z1") else s["kind"]
            out.append({"kind": kind, "minutes": s["minutes"], "zone": zona,
                        "lpm": lpm_range(zona, zonas), "note": plan_i18n.nota(s.get("note", "")),
                        "optional": s.get("optional", False),
                        **({"nota_id": plan_i18n.nota_id(s.get("note", ""))} if plan_i18n.nota_id(s.get("note", "")) else {})})
    return out


def rampas_de(steps: list) -> dict:
    """El sitio dibuja 5' de calentar y 5' de enfriar (no cuentan en los minutos), salvo que el plan ya los traiga:
    calentamiento = primer paso suave (Z0/Z1) marcado como tal; enfriamiento = último paso marcado como tal."""
    def marcado(p, kind, nota):
        return p["kind"] == kind or (p["kind"] != "repeat" and p.get("note") == nota)
    return {"con_calentamiento": bool(steps) and marcado(steps[0], "warmup", "calentamiento")
            and tipos.zona_unica(steps[0]) in ("Z0", "Z1"),
            "con_enfriamiento": bool(steps) and marcado(steps[-1], "cooldown", "enfriamiento")}


def rachas_de(steps: list, zonas: list) -> list:
    """Rachas de la silueta (tramos seguidos del mismo color) con lo que va escrito encima: minutos, la zona como la
    dice el plan (una sola: "Z2"; si la racha mezcla zonas, la de la silueta) y sus lpm.
    Suman lo mismo que `silueta`."""
    planos = []
    def aplanar(pasos):
        for p in pasos:
            if p["kind"] == "repeat":
                for _ in range(p["times"]):
                    aplanar(p["steps"])
            else:
                planos.append(p)
    aplanar(steps)
    out = []
    for p, (mins, zs, *_) in zip(planos, tipos.silueta_de(planos)):
        if out and out[-1]["_zs"] == zs:
            out[-1]["min"] += mins
            out[-1]["_zonas"].add(tipos.zona_unica(p))
            out[-1]["opcional"] = out[-1]["opcional"] and bool(p.get("optional"))
        else:
            out.append({"min": mins, "_zs": zs, "_zonas": {tipos.zona_unica(p)}, "opcional": bool(p.get("optional"))})
    for r in out:
        zona = r["_zonas"].pop() if len(r["_zonas"]) == 1 else r["_zs"]
        r.update({"zona": zona, "lpm": lpm_range(zona, zonas)})
        del r["_zs"], r["_zonas"]
    return out


ETIQUETA_CALIDAD = {"tempo_z3": "tempo Z3", "threshold": "threshold", "intervalos": "intervalos",
                    "progresivo": "progresivo", "fartlek": "fartlek"}


def estructura_calidad(s: dict) -> str:
    """"10' Z2 · 4×5' threshold (2' suave)" a partir de los pasos de una sesión de calidad. Los planes viejos traen
    además un enfriamiento al final (" · 5' suave")."""
    extras = s["steps"]
    calen = extras[0]
    enfria = next((p for p in extras if p["kind"] == "cooldown"), None)
    suave = tt("motor.suave")
    fin = f" · {enfria['minutes']}' {suave}" if enfria else ""
    if s.get("calidad_tipo") == "progresivo":
        medio = [p for p in extras[1:] if p["kind"] != "cooldown"]
        return (f"{calen['minutes']}' {calen['zone']} · " + " · ".join(f"{p['minutes']}' {tipos.zona_unica(p)}" for p in medio)
                + f" {tt('motor.estructura.progresivo')}{fin}")
    if s.get("calidad_tipo") == "fartlek":
        trabajo = [p["minutes"] for p in extras if p["kind"] == "run" and p["zone"] == "Z3"]
        return f"{calen['minutes']}' {calen['zone']} · " + tt("motor.estructura.fartlek", t="-".join(str(t) for t in trabajo)) + fin
    rep = next(p for p in extras if p["kind"] == "repeat")
    trabajo, rec = rep["steps"][0], rep["steps"][1]
    return (f"{calen['minutes']}' {calen['zone']} · {rep['times']}×{trabajo['minutes']}' "
            f"{tt('motor.estructura.' + s['calidad_tipo']) if s.get('calidad_tipo') in ETIQUETA_CALIDAD else tt('motor.calidad_min')} ({rec['minutes']}' {suave}){fin}")


def convert_session(s: dict, zonas: list) -> dict:
    easy = s["easy"]
    extra = {k: s[k] for k in ("nota", "calidad_tipo", "variada_tipo", "carrera") if k in s}
    if "nota" in extra:
        extra["nota"] = plan_i18n.nota(extra["nota"])
    if "objetivo" in s:
        extra["objetivo"] = {**s["objetivo"], "lpm": lpm_range(s["objetivo"]["zona"], zonas)}
        extra["estructura"] = estructura_calidad(s)
    forma, sil, sil_easy = tipos.forma_de(s), tipos.silueta_de(s["steps"]), tipos.silueta_de(easy["steps"])
    return {"id": s["id"], "tipo": s.get("tipo"), "name": plan_i18n.nombre(s["name"]), "minutes": s["minutes"], **extra,
            "forma": forma, "silueta": sil, "titulo": tipos.titulo_de(forma, tipos.silueta_de(s["steps"], False)), "rachas": rachas_de(s["steps"], zonas), **rampas_de(s["steps"]),
            "steps": convert_steps(s["steps"], zonas),
            "easy": {"name": plan_i18n.nombre(easy["name"]), "minutes": easy["minutes"],
                     "silueta": sil_easy, "titulo": tipos.titulo_de(tipos.forma_de({"steps": easy["steps"]}), tipos.silueta_de(easy["steps"], False)),
                     "rachas": rachas_de(easy["steps"], zonas), **rampas_de(easy["steps"]),
                     "steps": convert_steps(easy["steps"], zonas)}}


def convert_week(w: dict, zonas: list) -> dict:
    extra = {"evento": w["evento"]} if w.get("evento") else {}   # semana que un viaje o una carrera cambió (solo la web)
    return {"n": w["n"], "block": w["block"], "kind": w["kind"], "etiqueta": w["kind"] if w["kind"] == "descarga" else "carga",
            "focus": plan_i18n.focus(w["focus"]), **extra,
            "sessions": [convert_session(s, zonas) for s in w["sessions"]]}


def etiqueta_sesion(ses: dict, suave: bool = False) -> str:
    """«Z2 #1 · 20 min», «Larga suave · Z2 · 15 min»: nombre, zona (si el nombre no la dice) y minutos."""
    base = ses["easy"] if suave and ses.get("easy") else ses
    nombre = plan_i18n.nombre(ses["name"]) + (f" {tt('motor.version.suave')}" if suave and ses.get("easy") else "")
    zona = None if suave else (ses.get("objetivo") or {}).get("zona")
    if not zona:
        por_zona: dict = {}
        for minutos, z, *_ in tipos.silueta_de(base["steps"]):
            por_zona[z] = por_zona.get(z, 0) + minutos
        zona = max(por_zona, key=por_zona.get) if por_zona else None
    partes = [nombre] + ([zona] if zona and zona not in nombre else []) + [tt("motor.titular.min", n=f"{base['minutes']:g}")]
    return " · ".join(partes)
