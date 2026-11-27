"""Conexión C8: API del botón «Sincronizar» y de la franja de avance (POST/GET /api/sync).
Reutiliza `conexion.disparar` y `conexion.estado_secreto`; nunca expone sincronizaciones programadas."""
import logging
from datetime import timedelta

from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import conexion, sincronizar
from .modelos import Sincronizacion, Usuario, ahora

log = logging.getLogger("web.sync")
DISPAROS_POR_HORA = 6
RECIENTE_S = 60          # cuánto sigue visible «✓ ¡Listo!»
SIN_AVISOS_S = 20        # sin avisos del motor: se mira la corrida en GitHub
CACHE_S = 10
PORCENTAJE = {"arranca": 5, "prepara": 15, "busca": 25, "encuentra": 30, "detalles": 30, "salud": 80, "sube": 90,
              "termina": 100}
URL_APP = "/conectar/github?para=conectado"
ACCIONES = {   # error -> (clave de texto, clave del botón, url | None, post tipo | None)
    "sin_key": ("sync.err_sin_key", "sync.b_poner", "/bienvenida?paso=4", None),
    "nombre_mal": ("sync.err_nombre_mal", "sync.b_corregir", "/bienvenida?paso=4", None),
    "key_rechazada": ("sync.err_key_rechazada", "sync.b_garmin", "https://connect.garmin.com/", None),
    "otra": ("sync.err_otra", "sync.b_otra", None, "normal"),
}


def porcentaje(s: Sincronizacion) -> int:
    if s.estado == "ok":
        return 100
    if s.paso == "detalles" and s.total:
        return 30 + round(45 * max(0, min(s.hechos or 0, s.total)) / s.total)
    return PORCENTAJE.get(s.paso or "arranca", 5) if s.estado != "esperando" else 5


def tope(s: Sincronizacion) -> int:
    """Porcentaje donde empieza el paso siguiente: la barra gatea hacia él sin llegar (el JS solo anima entre `porcentaje` y `tope`)."""
    pct = porcentaje(s)
    if s.estado in ("ok", "error"):
        return pct
    if s.estado != "esperando" and s.paso == "detalles" and s.total:
        i = max(0, min(s.hechos or 0, s.total))
        return 30 + round(45 * (i + 1) / s.total) if i < s.total else PORCENTAJE["salud"]
    return min((v for v in PORCENTAJE.values() if v > pct), default=100)


def texto(s: Sincronizacion, t) -> str:
    if s.estado == "ok":
        n = s.nuevas or 0
        base = t("sync.listo_n", n=n) if n > 1 else t("sync.listo_1") if n == 1 else t("sync.al_dia")
        return base
    if s.estado == "error":
        return t(ACCIONES.get(s.error or "otra", ACCIONES["otra"])[0]) if not (
            s.tipo == "historial" and s.error == "otra") else t("sync.falta_historial")
    paso = s.paso if s.estado == "corriendo" and s.paso in PORCENTAJE else "arranca"
    if paso == "encuentra" and s.total is not None:
        out = t("sync.encuentra", total=s.total)
    elif paso == "detalles" and s.total:
        out = t("sync.detalles", hechos=min(s.hechos or 0, s.total), total=s.total)
    else:
        out = t("sync.p_" + ("sube" if paso == "termina" else paso))
    if s.tipo == "historial" and paso in ("busca", "encuentra", "detalles"):
        out += t("sync.nota_historial")
    return out


def accion(s: Sincronizacion, t) -> dict | None:
    if s.estado != "error":
        return None
    err = s.error if s.error in ACCIONES else "otra"
    _, boton, url, post = ACCIONES[err]
    if s.tipo == "historial" and err == "otra":
        return {"texto": t("sync.b_reintentar"), "post": {"url": "/api/sync", "tipo": "historial"}}
    if url:
        return {"texto": t(boton), "url": url}
    return {"texto": t(boton), "post": {"url": "/api/sync", "tipo": post}}


def a_json(s: Sincronizacion, t) -> dict:
    hace = None
    if s.terminada is not None:
        hace = max(0, int((ahora() - s.terminada).total_seconds()))
    return {"estado": s.estado, "tipo": s.tipo, "paso": s.paso, "hechos": s.hechos, "total": s.total,
            "nuevas": s.nuevas, "error": s.error, "texto": texto(s, t), "porcentaje": porcentaje(s), "tope": tope(s),
            "terminada_hace_s": hace, "accion": accion(s, t)}


def _reciente(db: Session, uid: int) -> Sincronizacion | None:
    """La última terminada (no programada) dentro de RECIENTE_S."""
    s = db.scalar(select(Sincronizacion).where(
        Sincronizacion.usuario_id == uid, Sincronizacion.estado.in_(("ok", "error")),
        Sincronizacion.tipo != "programada").order_by(Sincronizacion.terminada.desc(), Sincronizacion.id.desc()).limit(1))
    if s is not None and s.terminada is not None and ahora() - s.terminada <= timedelta(seconds=RECIENTE_S):
        return s
    return None


def _corrida(cache: dict, gh, u: Usuario, s: Sincronizacion) -> dict | None:
    """La corrida de esta sincronización según GitHub (consulta cacheada CACHE_S por persona)."""
    ahora_t = ahora()
    previo = cache.get(u.id)
    if previo and (ahora_t - previo[0]).total_seconds() < CACHE_S:
        runs = previo[1]
    else:
        desde = (s.creada - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        runs = gh.corridas(u.gh_instalacion, u.repo, desde=desde)
        cache[u.id] = (ahora_t, runs)
    if s.run_id is not None:
        return next((r for r in runs if r["id"] == s.run_id), None)
    marca = (s.creada - timedelta(seconds=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    candidatas = [r for r in runs if (r.get("created_at") or "") >= marca and r.get("event") == "workflow_dispatch"]
    return min(candidatas, key=lambda r: r["created_at"]) if candidatas else None


def revisar_corrida(app, settings, cache: dict, db: Session, u: Usuario, viva: Sincronizacion) -> None:
    """Viva sin avisos del motor: si la corrida ya terminó mal, la sincronización termina en `otra`."""
    if (ahora() - viva.actualizada).total_seconds() <= SIN_AVISOS_S or not conexion._gh_listo(u):
        return
    try:
        r = _corrida(cache, conexion.app_de(app, settings), u, viva)
    except Exception as e:   # noqa: BLE001  GitHub caído: se sigue mostrando lo que hay
        log.warning("no se pudo leer la corrida de %s: %s", u.id, getattr(e, "status", type(e).__name__))
        return
    if r and r.get("status") == "completed" and r.get("conclusion") in ("failure", "cancelled", "timed_out"):
        db.refresh(viva)
        if viva.estado in sincronizar.VIVAS:
            sincronizar.terminar(db, viva, ok=False, error="otra")


def sync_ui(settings, u: Usuario) -> dict | None:
    """`ui.sync` del data.json: None (sin la GitHub App configurada) deja el default de siempre."""
    if not settings.app_github:
        return None
    listo = conexion._gh_listo(u)
    return {"puede": listo, "url_autorizar": None if listo else URL_APP, "historial_pendiente": bool(u.historial_pendiente),
            "key_rechazada": u.key_rechazada_desde is not None,
            "migrar": bool(u.repo_id and not u.gh_instalacion)}   # C11b: conectado a la manera vieja: se le guía a autorizar


def _historial_fallido(db: Session, u: Usuario) -> Sincronizacion | None:
    """«Falta tu historial»: la comprobación salió bien y la última bajada del historial terminó en error (sin límite de tiempo)."""
    if not u.historial_pendiente:
        return None
    s = db.scalar(select(Sincronizacion).where(Sincronizacion.usuario_id == u.id, Sincronizacion.tipo == "historial")
                  .order_by(Sincronizacion.id.desc()).limit(1))
    return s if s is not None and s.estado == "error" else None


def montar(app, get_db, actual, settings, formulario) -> None:
    cache: dict = {}

    @app.get("/api/sync")
    def api_sync_estado(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        viva = sincronizar.actual(db, usuario.id)
        if viva is not None:
            revisar_corrida(app, settings, cache, db, usuario, viva)
            db.refresh(viva)
        s = viva if viva is not None and viva.estado in sincronizar.VIVAS else _reciente(db, usuario.id)
        if s is None:
            s = _historial_fallido(db, usuario)
        return {"sinc": a_json(s, request.state.t) if s is not None else None}

    @app.post("/api/sync")
    async def api_sync_pedir(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        form = await formulario(request)   # CSRF
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        t = request.state.t
        if not conexion._gh_listo(usuario):
            return JSONResponse({"error": "sin_app", "url": URL_APP}, status_code=409)
        viva = sincronizar.actual(db, usuario.id)
        if viva is not None:
            return {"sinc": a_json(viva, t), "nueva": False}
        pedido = form.get("tipo")
        tipo = "treinta" if pedido == "treinta" else "historial" if pedido == "historial" and usuario.historial_pendiente \
            else "normal"
        desde = ahora() - timedelta(hours=1)
        hechos = db.scalar(select(func.count()).select_from(Sincronizacion).where(
            Sincronizacion.usuario_id == usuario.id, Sincronizacion.tipo != "programada", Sincronizacion.creada > desde))
        if hechos >= DISPAROS_POR_HORA:
            return JSONResponse({"error": "limite", "texto": t("sync.limite")}, status_code=429)
        gh = conexion.app_de(app, settings)
        try:
            secreto, _ = conexion.estado_secreto(gh.secretos(usuario.gh_instalacion, usuario.repo))
        except Exception as e:   # noqa: BLE001
            log.warning("no se pudieron leer los secretos de %s: %s", usuario.id, getattr(e, "status", type(e).__name__))
            secreto = "otra"
        if secreto != "listo":
            sinc, _ = sincronizar.pedir(db, usuario, tipo)
            sincronizar.terminar(db, sinc, ok=False, error={"falta": "sin_key", "nombre_mal": "nombre_mal"}.get(secreto, "otra"))
            return {"sinc": a_json(sinc, t), "nueva": True}
        sinc = conexion.disparar(db, usuario, tipo, gh)
        return {"sinc": a_json(sinc, t), "nueva": True}
