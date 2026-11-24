"""Catálogo de tipos de entreno (para conocerlos en el sitio) y silueta de cada sesión.

`forma` describe solo el patrón de la FC en el tiempo: lista de tramos [duración_relativa, nivel] con nivel
0–1 (0 = reposo, 1 = máximo), o [duración, nivel_inicial, nivel_final] para una rampa. No lleva zonas ni colores.
"""

CALENTAR = [1, 0.15, 0.45]
ENFRIAR = [1, 0.45, 0.15]

CATALOGO = [
    {"id": "continuo", "nombre": "Continuo", "grupo": "continuos",
     "descripcion": "Un ritmo cómodo y parejo todo el tiempo. La Larga es un continuo más largo.",
     "forma": [CALENTAR, [8, 0.45], ENFRIAR]},
    {"id": "trote_caminata", "nombre": "Trote y caminata", "grupo": "continuos",
     "descripcion": "Trotas un rato, caminas un poco y repites: el cuerpo se acostumbra sin pasarte.",
     "forma": [[2, 0.5], [1, 0.12]] * 5},
    {"id": "espiga", "nombre": "Espiga", "grupo": "variados",
     "descripcion": "Subes por escalones hasta un pico corto y bajas igual.",
     "forma": [[2, 0.25], [2, 0.4], [2, 0.55], [2, 0.7], [1, 0.95], [2, 0.7], [2, 0.55], [2, 0.4], [2, 0.25]]},
    {"id": "piramide", "nombre": "Pirámide", "grupo": "variados",
     "descripcion": "Bloques de esfuerzo cada vez más largos y luego más cortos (1-2-3-2-1), con pausas suaves.",
     "forma": [[1, 0.7], [1, 0.2], [2, 0.7], [1, 0.2], [3, 0.7], [1, 0.2], [2, 0.7], [1, 0.2], [1, 0.7]]},
    {"id": "ascendente", "nombre": "Ascendente", "grupo": "variados",
     "descripcion": "Una escalera que sube: cada tramo es un poco más intenso que el anterior.",
     "forma": [[2, 0.25], [2, 0.4], [2, 0.55], [2, 0.7], [2, 0.85]]},
    {"id": "descendente", "nombre": "Descendente", "grupo": "variados",
     "descripcion": "Una escalera que baja: empiezas más fuerte y cada tramo es más suave.",
     "forma": [[2, 0.85], [2, 0.7], [2, 0.55], [2, 0.4], [2, 0.25]]},
    {"id": "densidad", "nombre": "Densidad", "grupo": "variados",
     "descripcion": "Picos iguales con descansos de la misma duración y luego del doble.",
     "forma": [[1, 0.85], [1, 0.2], [1, 0.85], [1, 0.2], [1, 0.85], [2, 0.2], [1, 0.85], [2, 0.2], [1, 0.85]]},
    {"id": "rotativo", "nombre": "Rotativo", "grupo": "variados",
     "descripcion": "Un ciclo bajo, medio y alto que se repite varias veces.",
     "forma": [[1, 0.2], [1, 0.5], [1, 0.8]] * 3},
    {"id": "progresivo", "nombre": "Progresivo", "grupo": "calidad",
     "descripcion": "Empiezas suave y aceleras poco a poco hasta terminar en lo más fuerte.",
     "forma": [[1, 0.2, 0.9]]},
    {"id": "tempo", "nombre": "Tempo", "grupo": "calidad",
     "descripcion": "Subes a un ritmo fuerte pero sostenible y lo aguantas un buen rato.",
     "forma": [[1, 0.2, 0.75], [6, 0.75], [1, 0.75, 0.2]]},
    {"id": "umbral", "nombre": "Umbral", "grupo": "calidad",
     "descripcion": "Dos o tres bloques largos y fuertes con descansos cortos entre ellos.",
     "forma": [[1, 0.2, 0.4], [3, 0.8], [1, 0.3], [3, 0.8], [1, 0.3], [3, 0.8], [1, 0.4, 0.2]]},
    {"id": "vo2", "nombre": "Intervalos VO2", "grupo": "calidad",
     "descripcion": "Picos muy fuertes y cortos con pausas para recuperar.",
     "forma": [[1, 0.2, 0.4], [1, 0.97], [1, 0.25], [1, 0.97], [1, 0.25], [1, 0.97], [1, 0.25], [1, 0.97], [1, 0.25],
               [1, 0.97], [1, 0.4, 0.2]]},
    {"id": "fartlek", "nombre": "Fartlek", "grupo": "calidad",
     "descripcion": "Cambios de ritmo a tu gusto, largos y cortos, sin un orden fijo.",
     "forma": [[2, 0.35], [1, 0.8], [2, 0.35], [3, 0.7], [1, 0.3], [1, 0.9], [2, 0.4], [2, 0.75], [2, 0.3]]},
    {"id": "carrera", "nombre": "Ritmo de carrera", "grupo": "calidad",
     "descripcion": "Sostienes el ritmo de tu carrera y remata con un empujón al final.",
     "forma": [[1, 0.2, 0.7], [7, 0.75], [1, 0.97]]},
]

GRUPOS = [("continuos", "Continuos"), ("variados", "Variados"), ("calidad", "De calidad")]
POR_ID = {t["id"]: t for t in CATALOGO}

# calidad_tipo (del plan) -> tipo del catálogo
FORMA_CALIDAD = {"tempo_z3": "tempo", "threshold": "umbral", "intervalos": "vo2",
                 "progresivo": "progresivo", "fartlek": "fartlek"}

NIVEL_ZONA = {"Z1": 0.25, "Z2": 0.45, "Z3": 0.65, "Z4": 0.82, "Z5": 0.97}


def _tiene_caminata(pasos: list) -> bool:
    return any(_tiene_caminata(p["steps"]) if p["kind"] == "repeat" else p["kind"] == "walk" for p in pasos)


def forma_de(sesion: dict) -> str:
    """Id del catálogo de una sesión del plan (se deriva; no se guarda en plan.json)."""
    if sesion.get("variada_tipo"):
        return sesion["variada_tipo"]
    if sesion.get("calidad_tipo"):
        return FORMA_CALIDAD.get(sesion["calidad_tipo"], "fartlek")
    return "trote_caminata" if _tiene_caminata(sesion.get("steps", [])) else "continuo"


def silueta_de(pasos: list) -> list:
    """Pasos del plan -> [[minutos, zona]] plano (con `repeat` desplegado). Caminata = Z1; Z1-Z2 = Z2;
    un paso opcional lleva un tercer elemento `true`."""
    out = []
    for p in pasos:
        if p["kind"] == "repeat":
            for _ in range(p["times"]):
                out += silueta_de(p["steps"])
            continue
        zona = "Z1" if p["kind"] == "walk" else "Z2" if p["zone"] == "Z1-Z2" else p["zone"]
        out.append([p["minutes"], zona, True] if p.get("optional") else [p["minutes"], zona])
    return out


def titulo_de(forma: str, silueta: list) -> str:
    """Título corto de la silueta de una sesión: nombre del tipo y sus zonas ("Continuo en Z2", "Espiga en Z1–Z3")."""
    zonas = sorted({z for _, z, *_ in silueta})
    nombre = POR_ID[forma]["nombre"] if forma in POR_ID else "Sesión"
    if not zonas:
        return nombre
    return f"{nombre} en {zonas[0] if len(zonas) == 1 else f'{zonas[0]}–{zonas[-1]}'}"


def catalogo_json(ids_en_plan: set) -> dict:
    """Catálogo para data.json: tipos en orden, con los ids que aparecen en el plan de la persona."""
    return {"catalogo": [dict(t) for t in CATALOGO],
            "grupos": [{"id": i, "nombre": n} for i, n in GRUPOS],
            "en_plan": [t["id"] for t in CATALOGO if t["id"] in ids_en_plan]}
