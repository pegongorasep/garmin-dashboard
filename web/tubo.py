"""El tubo de datos: cada repo manda su paquete con un token OIDC de GitHub Actions (sin tokens extra).

Verificación: firma RS256 con el JWKS de GitHub (caché 1 h), `iss`, `aud` (= OIDC_AUDIENCE), `exp` y que el workflow
llamado sea `motor.yml` del repo de Pedro en `stable` o `main`. El repositorio debe estar vinculado antes mediante
la GitHub App."""
import gzip
import hashlib
import json
import logging
import time
import zlib
from datetime import timedelta

import httpx
import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import paquete as paquete_mod

from . import cambios, datos, importar
from .modelos import Ajustes, Cambio, Sincronizacion, Subida, Usuario, ahora

log = logging.getLogger("web.tubo")
ISSUER = "https://token.actions.githubusercontent.com"
WORKFLOW = "pegongorasep/garmin-dashboard/.github/workflows/motor.yml@"
REFS_OK = ("refs/tags/stable", "refs/heads/main")
DIAS_ACTIVIDADES = 120
DIAS_PRIMERA = 365
MAX_COMPRIMIDO = 10 * 1024 * 1024
MAX_DESCOMPRIMIDO = 12 * 1024 * 1024
JWKS_SEGUNDOS = 3600


class TuboError(Exception):
    def __init__(self, status: int, mensaje: str, extra: dict | None = None):
        super().__init__(mensaje)
        self.status, self.mensaje, self.extra = status, mensaje, extra or {}


def jwks_de_github(url: str) -> dict:
    r = httpx.get(url, timeout=10)
    r.raise_for_status()
    return r.json()


def _jwks(app, settings) -> dict:
    cache = app.state.__dict__.setdefault("jwks_cache", {"t": 0.0, "datos": None})
    if cache["datos"] is None or time.time() - cache["t"] > JWKS_SEGUNDOS:
        fetch = getattr(app.state, "jwks_fetch", None) or jwks_de_github
        cache["datos"], cache["t"] = fetch(settings.jwks_url), time.time()
    return cache["datos"]


def verificar_token(token: str, settings, jwks: dict) -> dict:
    """Claims del token de GitHub Actions o TuboError."""
    try:
        kid = jwt.get_unverified_header(token).get("kid")
        llaves = {k.key_id: k for k in jwt.PyJWKSet.from_dict(jwks).keys}
        if kid not in llaves:
            raise TuboError(401, "llave desconocida")
        claims = jwt.decode(token, llaves[kid].key, algorithms=["RS256"], audience=settings.oidc_audience,
                            issuer=ISSUER, options={"require": ["exp", "iss", "aud"]})
    except jwt.PyJWTError:
        raise TuboError(401, "token no válido") from None
    ref = claims.get("job_workflow_ref") or ""
    if not (ref.startswith(WORKFLOW) and ref.endswith(REFS_OK)):
        raise TuboError(403, "workflow no autorizado")
    if not claims.get("repository_id") or not claims.get("repository_owner"):
        raise TuboError(401, "token sin repositorio")
    return claims


def vincular(db: Session, u: Usuario, repo: str, repo_id: int, owner_id, descripcion: str) -> None:
    """Deja al usuario ligado a ese repo y registra el cambio de sistema. No hace commit."""
    u.repo, u.repo_id = repo, repo_id
    try:
        u.github_owner_id = int(owner_id)
    except (TypeError, ValueError):
        pass
    db.add(Cambio(atleta_id=u.id, autor_id=None, via="sistema", visto=True, descripcion=descripcion,
                  antes=None, despues={"repo": repo, "repo_id": repo_id}))


def usuario_del_token(db: Session, claims: dict) -> Usuario:
    """Busca al dueño de un repo ya vinculado. La autorización de repos nuevos ocurre mediante GitHub App."""
    try:
        repo_id = int(claims["repository_id"])
    except (TypeError, ValueError):
        raise TuboError(401, "token sin repositorio") from None
    u = db.scalar(select(Usuario).where(Usuario.repo_id == repo_id, Usuario.borrado.is_(None)))
    if u is None:
        raise TuboError(403, "repo no vinculado")
    return u


def _entero(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def tuvo_subida_ok(db: Session, usuario_id: int) -> bool:
    return db.scalar(select(Subida.id).where(Subida.usuario_id == usuario_id, Subida.ok.is_(True)).limit(1)) is not None


def ultima_subida(db: Session, usuario_id: int):
    return db.scalar(select(Subida.fecha).where(Subida.usuario_id == usuario_id, Subida.ok.is_(True))
                     .order_by(Subida.fecha.desc()).limit(1))


def instrucciones_de(db: Session, u: Usuario) -> dict:
    primera = not tuvo_subida_ok(db, u.id)
    return {"vinculado": True, "historial_desde": u.historial_desde or ((ahora().date() - timedelta(days=DIAS_PRIMERA)).isoformat() if primera else None),
            "dias_actividades": DIAS_PRIMERA if primera else DIAS_ACTIVIDADES}


PASOS = ("arranca", "prepara", "busca", "encuentra", "detalles", "salud", "sube", "termina")
ERRORES = ("sin_key", "nombre_mal", "key_rechazada", "otra")
MAX_CUENTA = 100000


def _entero_acotado(v):
    """Entero 0..MAX_CUENTA o None (los booleanos no cuentan)."""
    if isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_CUENTA:
        return None
    return v


def sinc_del_run(db: Session, u: Usuario, claims: dict):
    """Sincronización viva de esa corrida; si no hay (o la corrida no se conoce), la viva sin corrida asignada."""
    from . import sincronizar
    run_id = _entero(claims.get("run_id"))
    if run_id is not None:
        s = db.scalar(select(Sincronizacion).where(Sincronizacion.usuario_id == u.id, Sincronizacion.run_id == run_id,
                                                   Sincronizacion.estado.in_(sincronizar.VIVAS))
                      .order_by(Sincronizacion.id.desc()).limit(1))
        if s is not None:
            return s
    sincronizar.actual(db, u.id, incluir_programadas=True)   # caduca las vivas viejas
    programada = claims.get("event_name") == "schedule"
    vivas = [x for x in sincronizar._vivas(db, u.id, True) if (x.tipo == "programada") == programada
             and (run_id is None or x.run_id is None or x.run_id == run_id)]
    return vivas[0] if vivas else None


def avisar_key_rechazada(enviar, settings, u: Usuario) -> None:
    """Correo único del incidente «Garmin rechazó tu key» (con liga a /garmin/key). Nunca tumba la petición."""
    import i18n
    idioma = u.idioma or "es"
    try:
        enviar(settings, u.correo, i18n.t("conexion.key_asunto", idioma),
               i18n.t("conexion.key_texto", idioma, liga=settings.base_url.rstrip("/") + "/garmin/key"))
    except Exception:   # noqa: BLE001
        log.warning("no se mandó el correo de key rechazada a %s", u.id, exc_info=True)


def instrucciones_v2(db: Session, u: Usuario, claims: dict) -> dict:
    """Instrucciones del motor nuevo: según la sincronización viva (o una nueva), con rangos por tipo."""
    from . import sincronizar
    run_id = _entero(claims.get("run_id"))
    primera = not tuvo_subida_ok(db, u.id)
    sinc = sinc_del_run(db, u, claims)
    if sinc is None:
        if u.historial_pendiente:
            tipo = "historial"
        elif claims.get("event_name") == "schedule":
            tipo = "programada"
        else:
            tipo = "normal"
        sinc = Sincronizacion(usuario_id=u.id, tipo=tipo, estado="esperando")
        db.add(sinc)
        db.flush()
    if run_id is not None:
        sinc.run_id = run_id
    sincronizar.avanzar(db, sinc, "prepara")
    dias, semanas = sincronizar.rango(sinc.tipo, db, u)
    if primera and sinc.tipo != "comprobacion":
        dias, semanas = DIAS_PRIMERA, 16
    desde = u.historial_desde
    if not desde and (sinc.tipo == "historial" or (primera and sinc.tipo != "comprobacion")):
        desde = (ahora().date() - timedelta(days=DIAS_PRIMERA)).isoformat()
    return {"vinculado": True, "historial_desde": desde, "dias_actividades": dias, "semanas_salud": semanas}


def _descomprimir(cuerpo: bytes, encabezado: str) -> bytes:
    if len(cuerpo) > MAX_COMPRIMIDO:
        raise TuboError(413, "paquete demasiado grande")
    if "gzip" not in (encabezado or "").lower():
        if len(cuerpo) > MAX_DESCOMPRIMIDO:
            raise TuboError(413, "paquete demasiado grande")
        return cuerpo
    try:
        d = zlib.decompressobj(16 + zlib.MAX_WBITS)
        salida = d.decompress(cuerpo, MAX_DESCOMPRIMIDO + 1)
    except (zlib.error, gzip.BadGzipFile):
        raise TuboError(400, "gzip no válido") from None
    if len(salida) > MAX_DESCOMPRIMIDO or d.unconsumed_tail:
        raise TuboError(413, "paquete demasiado grande")
    return salida


def _importar_personales(db, u, pers) -> None:
    """Primera subida: si la web aún no tiene ajustes de esta persona, importa su config/plan/InBody. Nunca pisa y nunca
    tumba la subida (un config inválido se salta y queda en el log)."""
    if not pers or db.get(Ajustes, u.id) is not None:
        return
    try:
        nuevo, _ = importar.cambio_de_personales(pers.get("config"), pers.get("plan"), pers.get("inbody"))
        if nuevo:
            cambios.aplicar_cambio(db, u, None, "sistema", "Importado desde el repo en la primera subida", nuevo)
    except Exception:   # noqa: BLE001
        db.rollback()
        log.warning("no se importaron los archivos personales de %s", u.id, exc_info=True)


def montar(app, get_db, settings) -> None:
    def autenticar(request: Request, db: Session) -> Usuario:
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            raise TuboError(401, "falta el token")
        try:
            claims = verificar_token(auth[7:].strip(), settings, _jwks(app, settings))
        except TuboError:
            raise
        except Exception:   # JWKS inalcanzable u otro fallo: no se adivina
            log.exception("no se pudo verificar el token")
            raise TuboError(503, "no se pudo verificar el token") from None
        request.state.claims = claims
        return usuario_del_token(db, claims)

    def error(e: TuboError):
        return JSONResponse({"error": e.mensaje, **e.extra}, status_code=e.status)

    def _cerrar_sinc(db, u, request, ok, nuevas=None):
        from . import sincronizar
        try:
            sinc = sinc_del_run(db, u, request.state.claims)
            if sinc is not None:
                era_comprobacion = sinc.tipo == "comprobacion"
                sincronizar.terminar(db, sinc, ok=ok, error=None if ok else "otra", nuevas=nuevas)
                if ok and era_comprobacion and settings.app_github and u.gh_instalacion:
                    from . import conexion   # tras la comprobación se pide el historial; si falla, queda en error
                    conexion.disparar(db, u, "historial", conexion.app_de(request.app, settings))
        except Exception:   # noqa: BLE001  cerrar la sincronización nunca tumba la subida
            db.rollback()
            log.warning("no se cerró la sincronización de %s", u.id, exc_info=True)

    @app.post("/api/tubo/instrucciones")
    async def instrucciones(request: Request, db=Depends(get_db)):
        try:
            u = autenticar(request, db)
            v2 = request.headers.get("x-motor-version", "").strip() == "2"
            if not v2:
                try:
                    cuerpo = json.loads(await request.body() or b"null")
                except ValueError:
                    cuerpo = None
                v2 = isinstance(cuerpo, dict) and cuerpo.get("motor_version") == 2
            if not v2:
                return instrucciones_de(db, u)   # motor viejo: exactamente lo de siempre
            return instrucciones_v2(db, u, request.state.claims)
        except TuboError as e:
            return error(e)

    @app.post("/api/tubo/avance")
    async def avance(request: Request, db=Depends(get_db)):
        from . import sincronizar
        try:
            u = autenticar(request, db)
            try:
                c = json.loads(await request.body() or b"null")
            except ValueError:
                c = None
            if not isinstance(c, dict) or c.get("paso") not in PASOS:
                raise TuboError(422, "avance no válido")
            nums = {}
            for k in ("hechos", "total"):
                if c.get(k) is not None:
                    nums[k] = _entero_acotado(c[k])
                    if nums[k] is None:
                        raise TuboError(422, "avance no válido")
            err = c.get("error")
            if err is not None and not isinstance(err, str):
                raise TuboError(422, "avance no válido")
        except TuboError as e:
            return error(e)
        sinc = sinc_del_run(db, u, request.state.claims)
        nuevo_incidente = False
        if err == "key_rechazada":
            nuevo_incidente = u.key_rechazada_desde is None   # uno por incidente, haya o no sincronización
        if sinc is not None:
            sincronizar.avanzar(db, sinc, c["paso"], **nums)
            if err:
                sincronizar.terminar(db, sinc, ok=False, error=err if err in ERRORES else "otra")
        elif err == "key_rechazada":
            sincronizar.marcar_key_rechazada(u)
            db.commit()
        if nuevo_incidente:
            avisar_key_rechazada(request.app.state.enviar, settings, u)
        return {"ok": True}

    @app.post("/api/tubo/subida")
    async def subida(request: Request, db=Depends(get_db)):
        try:
            u = autenticar(request, db)
            crudo = _descomprimir(await request.body(), request.headers.get("content-encoding", ""))
            try:
                pq = json.loads(crudo)
            except ValueError:
                raise TuboError(400, "JSON no válido") from None
        except TuboError as e:
            return error(e)
        problemas = paquete_mod.validar(pq)
        motor = pq.get("motor") if isinstance(pq, dict) and isinstance(pq.get("motor"), str) else None
        if problemas:
            db.add(Subida(usuario_id=u.id, motor=motor, bytes=len(crudo), ok=False, error="; ".join(problemas)[:2000]))
            db.commit()
            _cerrar_sinc(db, u, request, False)
            return JSONResponse({"error": "paquete no válido", "problemas": problemas}, status_code=422)
        try:
            cuentas = datos.guardar_paquete(db, u.id, pq)
        except Exception as e:   # no se guarda a medias
            db.rollback()
            log.exception("falló guardar el paquete de %s", u.id)
            db.add(Subida(usuario_id=u.id, motor=motor, bytes=len(crudo), ok=False, error=type(e).__name__))
            db.commit()
            _cerrar_sinc(db, u, request, False)
            return JSONResponse({"error": "no se pudo guardar"}, status_code=500)
        db.commit()   # el paquete queda guardado antes de importar (un rollback ahí no debe tirarlo)
        _importar_personales(db, u, pq.get("personales"))
        db.add(Subida(usuario_id=u.id, motor=motor, bytes=len(crudo), ok=True))
        u.key_rechazada_desde = None   # una subida buena: la key vuelve a servir
        u.historial_desde = None   # el pedido pendiente se cumplió con esta subida
        db.commit()
        _cerrar_sinc(db, u, request, True, (cuentas.get("actividad") or {}).get("nuevos"))
        return {"ok": True, "publicar_pages": not u.migrado}
