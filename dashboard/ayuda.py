"""Página de ayuda armada con la config y el plan de cada persona (lógica pura, sin red ni archivos).

`armar_ayuda(config, plan, zonas, fc_ref)` devuelve una lista de bloques de texto plano:
    [{"titulo": str, "parrafos": [str], "lista": [{"t": str | None, "x": str}]}]
Solo habla de lo que su plan tiene: caminatas, picos de Z3, variada o calidad (con sus tipos) y su tipo de prueba.
El sitio solo pinta estos bloques.
"""

DIAS_PIERNA = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
PRUEBA_TEXTO = {
    "fc_fija": ("30 min a FC fija", "30 min a FC fija ({fc_ref} lpm, la mitad de tu Z2) en ruta plana y con alerta en el reloj; "
                                    "cuenta el ritmo de esos 30 min (y los km)."),
    "trote_continuo": ("trote continuo", "30 min trotando sin caminar, en Z2; cuenta el % de trote de la corrida."),
    "5k": ("5 km a tope", "5 km a tope; cuenta el tiempo."),
}
PRUEBA_BASE = {"fc_fija": "el ritmo de tus semanas 1–2", "trote_continuo": "el % de trote de tus semanas 1–2",
               "5k": "tu mejor 5 km de antes del plan"}


def _lista_es(items: list) -> str:
    """['a', 'b', 'c'] -> 'a, b y c'."""
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " y " + items[-1] if items else ""


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
    return {"titulo": "El semáforo de cada mañana", "parrafos": [
        "Cada mañana se revisan 3 señales de recuperación; según cuántas estén fuera, el semáforo decide la sesión de hoy. "
        "Una señal sin dato no cuenta como fuera."],
        "lista": [
        _item("HRV", "fuera si anoche quedó por debajo de tu rango base. Si el reloj la marca “baja”, el semáforo va directo a rojo."),
        _item("FC en reposo", f"fuera si supera el promedio de 7 días + {ok('rhr_tolerance_bpm'):g} lpm."),
        _item("Sueño", f"fuera si dormiste menos de {ok('sleep_min_hours'):g} h."),
        _item("Esfuerzo de ayer", f"no mueve el semáforo, se muestra como dato. Si hay una señal fuera después de un día con esfuerzo de "
                                  f"{ok('esfuerzo_duro'):g} o más, el motivo lo dice."),
        _item("Verde", "ninguna señal fuera: sesión normal."),
        _item("Amarillo", "una señal fuera: versión suave de la sesión."),
        _item("Rojo", "dos o más señales fuera, o HRV baja: descanso o caminata ligera. Dos días rojos seguidos: repite la semana."),
        _item("Sin datos", "HRV, FC en reposo y sueño sin dato de anoche: sesión normal; decide cómo te sientes.")]}


def _sesiones(c: dict, plan: dict, zonas: dict) -> dict:
    semanas = plan.get("weeks") or []
    base = semanas[0]["sessions"] if semanas else []
    n = len(base)
    todas = [s for w in semanas for s in w["sessions"]]
    z2 = [s["name"] for s in base if s.get("tipo") == "z2"]
    larga = next((s for s in base if s.get("tipo") == "larga"), None)
    variadas = _unicos(s["name"].split(" · ", 1)[-1] for s in todas if s.get("tipo") == "variada")
    calidad = _unicos(s["name"].split(" · ", 1)[-1] for s in todas if s.get("tipo") == "calidad")
    picos = any(p.get("optional") for s in todas for p in _pasos(s["steps"]))
    descargas = [w["n"] for w in semanas if w["kind"] == "descarga" and not (w["n"] == semanas[-1]["n"] and "prueba" in w["focus"].lower())]
    z2_txt = f"Z2 ({zonas['Z2'][0]}–{zonas['Z2'][1]} lpm)"
    lista = []
    if z2:
        lista.append(_item(_lista_es(z2), f"corridas suaves en {z2_txt}: puedes platicar mientras corres."
                           + (" Si te pasas del techo, camina hasta bajar." if not c["caminatas"] else "")))
    if c["caminatas"]:
        reps = [(p["steps"][0]["minutes"], p["steps"][1]["minutes"]) for w in semanas for s in w["sessions"]
                for p in s["steps"] if p["kind"] == "repeat" and len(p["steps"]) >= 2]
        if reps:
            ini, fin = reps[0], max(reps)
            lista.append(_item("Trote y caminata", f"alternas trotar y caminar (empiezas con trote {ini[0]}'/camina {ini[1]}' y llegas a "
                                                   f"trote {fin[0]}'/camina {fin[1]}'). Cuando te sientas bien puedes subir al siguiente escalón."))
    if variadas:
        lista.append(_item("Variada", f"una de tus sesiones cambia de ritmo dentro de tu zona; rota entre {_lista_es(variadas)}. En las semanas de descarga todo es continuo."))
    if calidad:
        lista.append(_item("Calidad", f"una sesión por semana con esfuerzo más fuerte; tus tipos: {_lista_es(calidad)}. "
                                      "Pasarte de la zona objetivo en esa sesión es parte de la idea."))
    if larga:
        lista.append(_item("Larga", "la más larga de la semana, a ritmo cómodo; va sábado o domingo."
                           + (f" Si entrenas pierna el {_lista_es([DIAS_PIERNA[d] for d in c['dias_pierna']])}, el día siguiente evita la larga." if c["dias_pierna"] else "")))
    if picos:
        lista.append(_item("Picos de Z3", "en algunas semanas, 1' en Z3 es opcional dentro de la sesión. Si los haces cuentan como lo hecho; si no, no pasa nada."))
    if descargas:
        lista.append(_item("Semanas de descarga", f"las semanas {_lista_es([str(x) for x in descargas])} bajan la carga"
                                                         + ("." if c["caminatas"] else ": todo continuo en Z2.")))
    done = round(c["done_ratio"] * 100)
    generico = lambda s: "Calidad" if s.get("tipo") == "calidad" else "Variada" if s.get("tipo") == "variada" else s["name"]  # noqa: E731
    otras = [generico(s) for s in base if s.get("tipo") != "larga"]
    lista += [
        _item("Asignación automática", f"una corrida de sábado o domingo que dure al menos el {done} % de la Larga cuenta como Larga; "
                                       f"las demás llenan {_lista_es(otras) if otras else 'tus otras sesiones'} en orden. Si haces más, las sobrantes no se asignan."),
        _item("Hecha o incompleta", f"hecha si duró al menos el {done} % de lo planeado (o de la versión suave si ese día era amarillo o rojo); si duró menos, incompleta."),
        _item("¿Lo hice bien?", f"los minutos sobre el techo de Z2 (zonas 3 a 5) deben ser {c['ceiling_tolerance_min']:g}' o menos"
                                + ("; las sesiones con picos de Z3 permiten 2' más" if picos else "")
                                + f". Además, plan vs real por zona: los minutos que hiciste en cada zona del plan contra los planeados; con el {done} % se cumple (la FC tarda en subir)."),
        _item("Tiempo", "es tiempo de reloj"
                        + (", caminatas incluidas. Trote y caminata vienen de los tramos que detecta Garmin; el ritmo trotando no cuenta la caminata." if c["caminatas"] else "."))]
    texto_n = f"Tu plan tiene {n} sesiones por semana" if n != 1 else "Tu plan tiene 1 sesión por semana"
    nombres = [generico(s) for s in base]
    return {"titulo": "Tus sesiones", "parrafos": [f"{texto_n}: {_lista_es(nombres)}."], "lista": lista}


def _prueba(c: dict, plan: dict, fc_ref: int):
    semanas = plan.get("weeks") or []
    ses = next((s for s in (semanas[-1]["sessions"] if semanas else []) if s.get("tipo") == "prueba"), None)
    if not ses:
        return None
    tipo = ses["prueba"]
    nombre, como = PRUEBA_TEXTO[tipo]
    previa = any(p["tipo"] == tipo for p in c.get("pruebas", []))
    return {"titulo": "La prueba de la última semana", "parrafos": [
        f"En la última semana de tu plan (la {semanas[-1]['n']}) una sesión se cambia por una prueba para medir tu mejora: {como.format(fc_ref=fc_ref)}",
        "Se compara con " + ("tu prueba anterior" if previa else PRUEBA_BASE[tipo] + " y, después, con tu prueba anterior")
        + ". Al terminar el plan, Hoy muestra el resultado y te dice que corras /ajustar para el siguiente bloque."], "lista": []}


def _mejora(c: dict, fc_ref: int) -> dict:
    lista = [
        _item(f"Ritmo a {fc_ref} lpm", f"llevamos el ritmo de cada corrida al aire libre a {fc_ref} lpm (la mitad de tu Z2): ritmo × FC que llevaste ÷ {fc_ref}. "
                                       "Es tu eficiencia aeróbica: si mejoras, a la misma FC vas más rápido. Solo cuentan corridas cuyo trote cayó en Z2; no carreras ni caminadora"
                                       + (", ni las sesiones de calidad" if c["intensidad"] == "calidad" else "")
                                       + ". El calor y el cansancio suben la FC: mira la tendencia, no una corrida suelta. En Progreso ves el promedio de tus últimas 4 corridas válidas contra tus semanas 1–2."),
        _item("Deriva cardiaca", "en corridas de 40 min o más, casi sin caminar, a ritmo parejo y con al menos 80 % del trote en Z2, comparamos velocidad ÷ FC de la primera mitad contra la segunda "
                                 "(sin los primeros 10 min). Menos de 5 % de caída es buena base aeróbica; más, aún te falta base.")]
    if c["caminatas"]:
        lista.append(_item("% de trote", "qué parte de la corrida fue trote: si sube, tu cuerpo ya aguanta trotar más tiempo seguido."))
    lista.append(_item("Esfuerzo", "calculado con tu FC, de 1 a 10 (Z2 = 3, Z3 = 5.5, Z4 = 7.5, Z5 = 9.5): el promedio de la mitad más dura de la sesión. "
                                   "Carga = esfuerzo × minutos; la fuerza con la FC baja da poca carga. El RPE que pones en el reloj se guarda aparte."))
    return {"titulo": "Cómo medimos tu mejora", "parrafos": [], "lista": lista}


def _zonas(c: dict, zonas: dict) -> dict:
    sig = {"Z1": "recuperación y calentar", "Z2": "tu base aeróbica: el grueso de tus corridas", "Z3": "medio, “el limbo”",
           "Z4": "fuerte", "Z5": "máximo"}
    cats = [x["nombre"] for x in c["categorias"]]
    return {"titulo": "Tus zonas y el 80/20", "parrafos": [
        f"Las zonas usan Karvonen (% de tu reserva de FC) con tu FC máx de {c['max_hr']:g} lpm. Se ajustan solas con tu FC en reposo.",
        "El 80/20: lo ideal es que al menos 80 % de tu tiempo en zonas sea suave (Z1–Z2), lo menos posible en Z3 y el resto fuerte (Z4–Z5). "
        f"Incluye {_lista_es(cats + ['corridas'])}. Es solo referencia: no cambia tu plan."],
        "lista": [_item(z, f"{zonas[z][0]}–{zonas[z][1]} lpm · {sig[z]}") for z in ("Z1", "Z2", "Z3", "Z4", "Z5")]}


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
