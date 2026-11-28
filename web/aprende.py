"""«Aprende»: artículos cortos de teoría (aprende/es/<slug>.yaml), solo para quien tiene sesión."""
import re
from functools import lru_cache

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from . import ROOT
from .deps import actual, render

CARPETA = ROOT / "aprende"
SLUG = re.compile(r"[a-z0-9-]+")
IDIOMA_CONTENIDO = "es"   # por ahora solo hay artículos en español
ORDEN = ("zonas", "zona-2", "long-run", "volumen", "semana", "calidad", "trote-caminata", "fuerza",
         "recuperacion", "dolor", "carrera")   # el resto va al final, por orden alfabético


def slug_valido(slug: str) -> bool:
    return bool(SLUG.fullmatch(slug or ""))


@lru_cache(maxsize=None)
def articulo(slug: str, idioma: str = IDIOMA_CONTENIDO) -> dict | None:
    """El artículo ya leído, o None si el slug no es válido o no existe. Cacheado."""
    if not slug_valido(slug) or not re.fullmatch(r"[a-z]{2}", idioma):
        return None
    ruta = CARPETA / idioma / f"{slug}.yaml"
    if not ruta.is_file():
        return None
    d = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}
    return {"slug": slug, "titulo": d["titulo"], "resumen": d["resumen"], "minutos": int(d["minutos"]),
            "secciones": [{"titulo": s["titulo"], "parrafos": list(s.get("parrafos") or []), "lista": list(s.get("lista") or [])}
                          for s in d["secciones"]],
            "fuentes": list(d.get("fuentes") or [])}


def slugs(idioma: str = IDIOMA_CONTENIDO) -> list[str]:
    hay = sorted(p.stem for p in (CARPETA / idioma).glob("*.yaml") if slug_valido(p.stem))
    return [s for s in ORDEN if s in hay] + [s for s in hay if s not in ORDEN]


def todos(idioma: str = IDIOMA_CONTENIDO) -> list[dict]:
    return [a for a in (articulo(s, idioma) for s in slugs(idioma)) if a]

router = APIRouter()


@router.get("/aprende")
def aprende(request: Request, usuario=Depends(actual)):
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    return render(request, "aprende.html", atleta=usuario, pref="", articulos=todos())


@router.get("/aprende/{slug}")
def aprende_articulo(request: Request, slug: str, usuario=Depends(actual)):
    if usuario is None:
        return RedirectResponse("/entrar", 303)
    a = articulo(slug)
    if a is None:
        raise HTTPException(404, "Artículo no encontrado")
    return render(request, "aprende_articulo.html", atleta=usuario, pref="", a=a,
                  en_ingles=request.state.idioma != IDIOMA_CONTENIDO)
