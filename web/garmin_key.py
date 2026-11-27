"""Conexión C11: «Garmin rechazó tu key» -> /garmin/key (guía corta para cambiarla y detección sola del cambio)."""
from datetime import datetime, timezone

from fastapi import Depends, Request
from fastapi.responses import JSONResponse, RedirectResponse

from . import conexion, onboarding, sincronizar


def _fecha(texto) -> datetime | None:
    try:
        d = datetime.fromisoformat(str(texto).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d


def secreto_cambiado(secretos: list[dict], desde: datetime | None) -> bool:
    """True si PERSONAL_API_KEY se actualizó después de que Garmin rechazó la key."""
    for s in secretos:
        if s.get("name") == conexion.SECRETO:
            f = _fecha(s.get("updated_at"))
            return bool(f and desde and f > desde)
    return False


def montar(app, get_db, actual, render, settings, formulario) -> None:
    def con_app(u) -> bool:
        return bool(settings.app_github) and conexion._gh_listo(u)

    @app.get("/garmin/key")
    def pagina(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return RedirectResponse("/entrar", 303)
        repo = usuario.repo or ""
        liga = {"secreto": f"https://github.com/{repo}/settings/secrets/actions" if repo else "https://github.com/settings/repositories",
                "key": onboarding.KEY_GARMIN_URL}
        return render(request, "garmin_key.html", u=usuario, repo=repo, liga=liga, con_app=con_app(usuario),
                      incidente=usuario.key_rechazada_desde is not None)

    @app.get("/api/garmin/key")
    def estado(usuario=Depends(actual), db=Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        viva = sincronizar.actual(db, usuario.id)
        sinc = viva or sincronizar.ultima_terminada(db, usuario.id)
        db.refresh(usuario)
        out = {"resuelta": usuario.key_rechazada_desde is None, "cambiada": False, "viva": viva is not None,
               "sinc": conexion.sinc_json(sinc), "error": None}
        if out["resuelta"]:
            return out
        if con_app(usuario):
            try:
                out["cambiada"] = secreto_cambiado(
                    conexion.app_de(app, settings).secretos(usuario.gh_instalacion, usuario.repo), usuario.key_rechazada_desde)
            except Exception:   # noqa: BLE001
                out["error"] = "otra"
        return out

    @app.post("/api/garmin/key/comprobar")
    async def comprobar(request: Request, usuario=Depends(actual), db=Depends(get_db)):
        """Corre una sincronización normal (trae también los días que faltaron). Sin `forzar` exige que el secreto haya cambiado."""
        form = await formulario(request)
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        if not con_app(usuario):
            return JSONResponse({"error": "sin_conexion"}, status_code=409)
        gh = conexion.app_de(app, settings)
        if not (form or {}).get("forzar"):
            try:
                cambiada = secreto_cambiado(gh.secretos(usuario.gh_instalacion, usuario.repo), usuario.key_rechazada_desde)
            except Exception:   # noqa: BLE001
                return JSONResponse({"error": "otra"}, status_code=502)
            if not cambiada:
                return JSONResponse({"error": "sin_cambio"}, status_code=409)
        viva = sincronizar.actual(db, usuario.id)
        sinc = conexion.disparar(db, usuario, "normal", gh)
        return {"sinc": conexion.sinc_json(sinc), "nueva": sinc is not None and (viva is None or sinc.id != viva.id)}
