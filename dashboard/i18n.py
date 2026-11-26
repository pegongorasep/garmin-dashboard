"""Catálogo de textos es/en (como strings.xml). Los comparten el motor y la web.

`i18n/es.yaml` es la referencia; las claves son planas con puntos (`entrar.titulo`) y las variables van como `{nombre}`.
Una clave que falta en otro idioma cae a `es`; con ESTRICTO (pruebas) lanza KeyError.
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

DIR = Path(__file__).parent.parent / "i18n"
DEFECTO = "es"
ESTRICTO = False
_VARS = re.compile(r"\{(\w+)\}")


def idiomas() -> list[str]:
    return sorted(p.stem for p in DIR.glob("*.yaml"))


@lru_cache(maxsize=None)
def cargar(idioma: str) -> dict:
    p = DIR / f"{idioma}.yaml"
    if not p.exists():
        return {}
    return {str(k): str(v) for k, v in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).items()}


def variables(texto: str) -> set[str]:
    return set(_VARS.findall(texto))


def t(clave: str, idioma: str = DEFECTO, **vars) -> str:
    cat = cargar(idioma if idioma in idiomas() else DEFECTO)
    texto = cat.get(clave)
    if texto is None:
        if ESTRICTO:
            raise KeyError(f"falta la clave {clave!r} en i18n/{idioma}.yaml")
        texto = cargar(DEFECTO).get(clave, clave)
    return texto.format_map(_Seguro(vars)) if vars or "{" in texto else texto


class _Seguro(dict):
    def __missing__(self, k):
        return "{" + k + "}"


def elegir(accept_language: str | None) -> str | None:
    """Primer idioma de la cabecera Accept-Language que tengamos (por orden de q); None si ninguno."""
    if not accept_language:
        return None
    disponibles = set(idiomas())
    pares = []
    for i, parte in enumerate(accept_language.split(",")):
        tag, _, q = parte.strip().partition(";q=")
        try:
            peso = float(q) if q else 1.0
        except ValueError:
            peso = 0.0
        pares.append((-peso, i, tag.strip().lower().split("-")[0]))
    for _, _, base in sorted(pares):
        if base in disponibles:
            return base
    return None


PREFIJO_SITIO = "sitio."


def catalogo_sitio(idioma: str) -> dict:
    """Las claves `sitio.*` de un idioma (lo que usa el JS del sitio); lo que falte se completa con `es`."""
    base = {k: v for k, v in cargar(DEFECTO).items() if k.startswith(PREFIJO_SITIO)}
    if idioma not in idiomas():
        return base
    return {**base, **{k: v for k, v in cargar(idioma).items() if k.startswith(PREFIJO_SITIO)}}


def escribir_json(destino: Path) -> None:
    """Escribe <destino>/<idioma>.json con `catalogo_sitio` de cada idioma."""
    import json
    destino.mkdir(parents=True, exist_ok=True)
    for idioma in idiomas():
        (destino / f"{idioma}.json").write_text(
            json.dumps(catalogo_sitio(idioma), ensure_ascii=False, indent=0, sort_keys=True) + "\n", encoding="utf-8")
