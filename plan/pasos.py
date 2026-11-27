"""Piezas básicas de un plan: pasos (zona + minutos), sesiones con su versión suave y los redondeos. Las usan `motor_v6`
y la web (editor de sesiones). Un paso es {"kind": "run"|"walk"|"repeat", "minutes", "zone", "note"}."""

SUAVE = {20: 15, 25: 20, 30: 20, 40: 30, 45: 30, 50: 35, 55: 40, 60: 40, 65: 45, 70: 50}
NOTA_LARGA = "ritmo cómodo; si pasas el techo, camina hasta bajar"


def redondea5(x: float) -> int:
    return int(x / 5 + 0.5) * 5


def suave(minutos: int) -> int:
    return SUAVE.get(minutos) or max(10, redondea5(minutos * 0.72))


def paso(minutos, zona="Z2", nota="", kind="run", **extra):
    return {"kind": kind, "minutes": minutos, "zone": zona, "note": nota, **extra}


def suma(pasos: list) -> int:
    return sum(p["times"] * suma(p["steps"]) if p["kind"] == "repeat" else p["minutes"] for p in pasos)


def zonas_de(pasos: list) -> set:
    return {z for p in pasos for z in (zonas_de(p["steps"]) if p["kind"] == "repeat" else {p["zone"]})}


def sesion(id_, tipo, nombre, minutos, pasos, **extra):
    s = suave(minutos)
    return {"id": id_, "tipo": tipo, "name": nombre, "minutes": minutos, "steps": pasos, **extra,
            "easy": {"name": "Suave", "minutes": s, "steps": [paso(s)]}}
