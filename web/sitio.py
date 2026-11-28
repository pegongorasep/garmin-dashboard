"""El sitio: inicio, `data.json` por persona, el sitio del coach (`/a/<id>/`), textos i18n, fuentes, el catálogo de diseño y
los archivos estáticos de `site/`. Va al final del orden: `/{archivo}` atiende lo que no atendió ninguna otra ruta."""
import json
import logging
import re
import secrets
from datetime import timezone
from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from markupsafe import Markup
from sqlalchemy import select

from dashboard import i18n
from dashboard.ajustes import ConfigError

from . import ROOT, auth, calculo, oauth, onboarding, sync_web
from .deps import actual, formulario, get_db, render
from .modelos import AvisoOculto, Usuario
from .permisos import puede_editar, puede_ver

log = logging.getLogger("web")
router = APIRouter()
SITE = ROOT / "site"
# Archivos del sitio que se sirven tal cual. `data.json` NO está aquí a propósito: sale de /data.json, por usuario.
# `catalogo.html` tampoco está aquí: solo sale por /diseno, para el admin.
ESTATICOS_SITE = {"base.js": "text/javascript", "app.js": "text/javascript", "charts.js": "text/javascript",
                  "iconos.js": "text/javascript", "componentes.js": "text/javascript", "arte.js": "text/javascript", "actualizar.js": "text/javascript", "franja.js": "text/javascript", "vista_comun.js": "text/javascript", "vista_plan.js": "text/javascript", "vista_progreso.js": "text/javascript", "vista_grupo.js": "text/javascript", "vistas.js": "text/javascript", "tema.js": "text/javascript", "catalogo.js": "text/javascript",
                  "styles.css": "text/css", "tokens.css": "text/css", "componentes.css": "text/css",
                  "sw.js": "text/javascript", "manifest.webmanifest": "application/manifest+json",
                  "icono-192.png": "image/png", "icono-512.png": "image/png", "icono-maskable-512.png": "image/png",
                  "apple-touch-icon.png": "image/png", "dibujo-github.svg": "image/svg+xml"}
FUENTES = {"Lexend-latin.woff2"}
def negritas(texto) -> Markup:
    """Escapa el texto y convierte **x** en <strong>x</strong> (para los textos de i18n que llevan negritas)."""
    return Markup(re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", str(escape(texto))))


def pie_sitio(idioma: str, csrf: str = "", ruta: str = "/") -> str:
    """Pie y registro del service worker que la web agrega al sitio, en el idioma de quien lo ve."""
    opciones = "".join(
        f'<option value="{c}" lang="{c}"{" selected" if c == idioma else ""}>{i18n.t("idioma." + c, idioma)}</option>' for c in ("es", "en"))
    form = (f'<form class="pie-idioma" method="post" action="/idioma"><input type="hidden" name="csrf" value="{escape(csrf, quote=True)}">'
            f'<input type="hidden" name="siguiente" value="{escape(ruta, quote=True)}">'
            f'<label for="pie-idioma-sel" class="sr">{i18n.t("idioma.titulo", idioma)}</label>'
            f'<svg class="ico-svg" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" focusable="false" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17"/><path d="M12 3.5c2.4 2.4 3.6 5.2 3.6 8.5s-1.2 6.1-3.6 8.5c-2.4-2.4-3.6-5.2-3.6-8.5S9.6 5.9 12 3.5z"/></svg><select id="pie-idioma-sel" name="idioma">{opciones}</select>'
            f'<noscript><button type="submit">{i18n.t("idioma.guardar", idioma)}</button></noscript></form>') if csrf else ""
    return (f'<footer class="pie"><p>{i18n.t("pie.consejo", idioma)}</p>'
            f'<div class="pie-fila">{form}<p>{i18n.t("pie.datos", idioma)} · <a href="/privacidad">{i18n.t("pie.privacidad", idioma)}</a></p></div></footer>'
            f'<script src="/actualizar.js" data-texto="{i18n.t("sitio.version_nueva", idioma)}" data-accion="{i18n.t("sitio.version_actualizar", idioma)}" '
            f'data-cuerpo="{i18n.t("sitio.version_cuerpo", idioma)}" data-luego="{i18n.t("sitio.version_luego", idioma)}" '
            f'data-actualizando="{i18n.t("sitio.version_actualizando", idioma)}"></script>'
            f'<script src="/franja.js" data-campo="{escape(csrf, quote=True)}" data-solicitando="{escape(i18n.t("sync.solicitando", idioma), quote=True)}" data-fallo="{escape(i18n.t("sync.solicitud_error", idioma), quote=True)}"></script>')


@router.get("/instalar")
def instalar(request: Request, siguiente: str = "/"):
    return render(request, "instalar.html", siguiente=oauth.ruta_relativa(siguiente))

@router.get("/")
def inicio(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    if usuario is None:
        return render(request, "inicio.html")
    if not onboarding.completo(db, usuario):
        return RedirectResponse("/perfil", 303)   # nombre y aviso de privacidad, una vez (E1)
    cookie = request.cookies.get(auth.COOKIE_CSRF)
    nueva = cookie is None
    cookie = cookie or secrets.token_urlsafe(24)
    campo = auth.campo_csrf(request.app.state.settings.secret_key, cookie)
    html = (SITE / "index.html").read_text().replace("</main>", "</main>" + pie_sitio(request.state.idioma, campo, "/"), 1)
    # Nombre, avisos ya entendidos y token CSRF van solo en esta página (nunca en data.json). Las páginas no se
    # guardan en el service worker; no-store por si acaso.
    ocultos = {a.aviso_id: a.huella for a in db.scalars(select(AvisoOculto).where(AvisoOculto.usuario_id == usuario.id))}
    attrs = {"data-nombre": usuario.nombre or "", "data-avisos-ocultos": json.dumps(ocultos), "data-csrf": campo,
             "data-grupos": str(calculo.contar_grupos(db, usuario))}
    html = html.replace('<main id="app">', '<main id="app" ' + " ".join(f'{k}="{escape(v, quote=True)}"' for k, v in attrs.items()) + ">", 1)
    resp = HTMLResponse(html, headers={"Cache-Control": "no-store"})
    if nueva:
        resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=request.app.state.settings.cookie_segura, samesite="lax", path="/")
    return resp

@router.post("/avisos/ocultar")
async def ocultar_aviso(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    """«Entendido»: la persona da por visto un aviso hasta que cambie su huella. Solo en su propia cuenta."""
    form = await formulario(request)
    if usuario is None or not puede_editar(db, usuario, usuario.id):
        raise HTTPException(403)
    aviso_id, huella = str(form.get("id", "")), str(form.get("huella", ""))
    if not re.fullmatch(r"[a-z_]{1,20}", aviso_id) or not re.fullmatch(r"[0-9a-f]{1,16}", huella):
        raise HTTPException(422)
    fila = db.get(AvisoOculto, (usuario.id, aviso_id))
    if fila is None:
        db.add(AvisoOculto(usuario_id=usuario.id, aviso_id=aviso_id, huella=huella))
    else:
        fila.huella = huella
    db.commit()
    return JSONResponse({"ok": True})

@router.get("/diseno")
def diseno(usuario=Depends(actual)):
    """Catálogo del sistema de diseño: solo el admin; a los demás (y sin sesión) un 404 como si no existiera."""
    if usuario is None or not usuario.es_admin:
        raise HTTPException(404)
    return FileResponse(SITE / "catalogo.html", media_type="text/html")

def data_de(request: Request, db, usuario, atleta_id: int, pref: str = "") -> Response:
    if not puede_ver(db, usuario, atleta_id):
        raise HTTPException(404)   # 404 y no 403: no confirma que exista
    atleta = db.get(Usuario, atleta_id)
    try:
        salida = calculo.calcular(db, atleta, request.app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None), pref,
                                  request.state.idioma,
                                  sync=sync_web.sync_ui(request.app.state.settings, atleta) if atleta.id == getattr(usuario, 'id', None) else None,
                                  editable=puede_editar(db, usuario, atleta_id))
        return JSONResponse({**salida, "idioma": request.state.idioma})   # el sitio se pinta en el idioma de quien lo ve
    except calculo.SinConfig:
        raise HTTPException(404)
    except ConfigError as e:
        log.error("config inválida de %s: %s", atleta_id, e)
        return JSONResponse({"error": "Tus ajustes no son válidos."}, status_code=500)
    except calculo.DataInvalido:
        return JSONResponse({"error": "No se pudo preparar tu información."}, status_code=500)

@router.get("/data.json")
def data_json(request: Request, usuario=Depends(actual), db=Depends(get_db)):
    if usuario is None:
        return JSONResponse({"error": "Entra primero."}, status_code=401)
    return data_de(request, db, usuario, usuario.id)

@router.get("/a/{atleta_id}/data.json")
def data_atleta(request: Request, atleta_id: int, usuario=Depends(actual), db=Depends(get_db)):
    return data_de(request, db, usuario, atleta_id, "" if usuario is not None and usuario.id == atleta_id else f"/a/{atleta_id}")

@router.get("/a/{atleta_id}")
def sitio_atleta_sin_slash(atleta_id: int):
    return RedirectResponse(f"/a/{atleta_id}/", 308)

@router.get("/a/{atleta_id}/")
def sitio_atleta(atleta_id: int, request: Request, usuario=Depends(actual), db=Depends(get_db)):
    """El mismo sitio, visto por el coach: los archivos van con ruta absoluta y data.json sigue relativo (/a/<id>/data.json)."""
    if not puede_ver(db, usuario, atleta_id):
        raise HTTPException(404)
    cookie = request.cookies.get(auth.COOKIE_CSRF)
    nueva = cookie is None
    cookie = cookie or secrets.token_urlsafe(24)
    pie = pie_sitio(request.state.idioma, auth.campo_csrf(request.app.state.settings.secret_key, cookie), request.url.path)
    html = (SITE / "index.html").read_text().replace("</main>", "</main>" + pie, 1)
    html = re.sub(r'(href|src)="([\w.-]+\.(?:css|js))"', r'\1="/\2"', html)
    resp = HTMLResponse(html)
    if nueva:
        resp.set_cookie(auth.COOKIE_CSRF, cookie, httponly=True, secure=request.app.state.settings.cookie_segura, samesite="lax", path="/")
    return resp

@router.get("/fuentes/{archivo}")
def fuente(archivo: str):
    if archivo not in FUENTES:
        raise HTTPException(404)
    return FileResponse(SITE / "fuentes" / archivo, media_type="font/woff2",
                        headers={"Cache-Control": "public, max-age=31536000, immutable"})

@router.get("/i18n/{archivo}")
@router.get("/a/{atleta_id}/i18n/{archivo}")   # el sitio del coach pide los textos con ruta relativa
def textos_sitio(archivo: str, atleta_id: int | None = None):
    """Los textos del sitio (JS) en un idioma: salen del catálogo, nunca atrasados. Son públicos (no llevan datos)."""
    idioma = archivo[:-5] if archivo.endswith(".json") else ""
    if idioma not in i18n.idiomas():
        raise HTTPException(404)
    return JSONResponse(i18n.catalogo_sitio(idioma), headers={"Cache-Control": "no-cache"})

@router.get("/{archivo}")   # siempre al final: el resto del sitio, solo la lista de arriba
def sitio(archivo: str):
    tipo = ESTATICOS_SITE.get(archivo)
    if tipo is None:
        raise HTTPException(404)
    return FileResponse(SITE / archivo, media_type=tipo)
