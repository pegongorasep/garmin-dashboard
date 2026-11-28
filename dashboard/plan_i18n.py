"""Textos que el plan trae en español (nombres de sesión, notas de paso, resumen de la semana) puestos en el idioma en curso.

El plan guardado (plan.json / base de la web) sigue en español: aquí se reconoce cada texto conocido (por el catálogo `es`)
y se pide su equivalente con `tt`. Un texto que no se reconoce (p. ej. una nota que escribió la persona) queda como está.
"""
import re
from functools import lru_cache

from dashboard import i18n
from dashboard.i18n import tt


@lru_cache(maxsize=None)
def _inv(prefijo: str) -> dict:
    """{texto en español: id} de las claves del catálogo `es` con ese prefijo."""
    return {v: k[len(prefijo):] for k, v in i18n.cargar("es").items() if k.startswith(prefijo)}


def nota_id(nota: str) -> str | None:
    return _inv("motor.nota.").get(nota or "")


def nota(texto: str) -> str:
    """La nota de un paso/sesión en el idioma en curso (si es una de las del motor)."""
    k = nota_id(texto)
    return tt(f"motor.nota.{k}") if k else texto


def nombre(texto: str) -> str:
    """Nombre de sesión ("Z2 #1", "Larga", "Calidad · Tempo Z3", "Variada · Espiga", "Prueba · 5 km")."""
    k = _inv("motor.nombre.").get(texto)
    if k and k not in ("calidad_x", "variada_x"):
        return tt(f"motor.nombre.{k}")
    if texto.startswith("Calidad · "):
        x = texto[len("Calidad · "):]
        k = _inv("motor.cal.").get(x)
        return tt("motor.nombre.calidad_x", x=tt(f"motor.cal.{k}") if k else x)
    if texto.startswith("Variada · "):
        return tt("motor.nombre.variada_x", x=_tipo_nombre(texto[len("Variada · "):]))
    return texto


def _tipo_nombre(x: str) -> str:
    """Nombre del tipo de corrida (Espiga, Pirámide…) en el idioma en curso."""
    for k, v in i18n.cargar("es").items():
        if k.startswith("motor.tipo.") and k.endswith(".nombre") and v == x:
            return tt(k)
    return x


def focus(texto: str) -> str:
    """Resumen de la semana ("Larga 40' · calidad: Threshold · trote 5'/camina 1'"), pieza por pieza."""
    partes = []
    for p in texto.split(" · "):
        m = re.fullmatch(r"Larga (\d+)'", p)
        if m:
            partes.append(tt("motor.focus.larga", n=m[1]))
            continue
        m = re.fullmatch(r"trote (\d+)'/camina (\d+)'", p)
        if m:
            partes.append(tt("motor.focus.trote", n=m[1]) if m[2] == "1" else tt("motor.focus.trote_w", n=m[1], w=m[2]))
            continue
        m = re.fullmatch(r"(calidad|variada): (.+)", p)
        if m:
            x = _inv("motor.cal.").get(m[2])
            partes.append(tt(f"motor.focus.{m[1]}", x=tt(f"motor.cal.{x}") if x else _tipo_nombre(m[2])))
            continue
        fijo = {"Descarga": "descarga", "Prueba": "prueba", "prueba": "prueba_min", "picos Z3 opcionales": "picos", "aceleraciones": "aceleraciones"}.get(p)
        partes.append(tt(f"motor.focus.{fijo}") if fijo else p)
    return " · ".join(partes)
