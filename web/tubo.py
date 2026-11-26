"""El tubo de datos: cada repo manda su paquete con un token OIDC de GitHub Actions (sin tokens extra).

Verificación: firma RS256 con el JWKS de GitHub (caché 1 h), `iss`, `aud` (= OIDC_AUDIENCE), `exp` y que el workflow
llamado sea `motor.yml` del repo de Pedro en `stable` o `main`. El usuario es el dueño del `repository_id`; si ninguno,
se vincula un usuario sin repo con ese `repository_owner` que ya aceptó el aviso."""
import gzip
import hashlib
import hmac
import json
import logging
import secrets
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
from .modelos import Ajustes, Cambio, Consentimiento, Subida, Usuario, VinculoPendiente, ahora

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


MINUTOS_CODIGO = 60
MAX_INTENTOS = 5


def codigo_de(secret_key: str, nonce: str) -> str:
    """Código de 6 dígitos derivado del nonce (así se puede mostrar otra vez sin guardarlo)."""
    d = hmac.new(secret_key.encode(), f"codigo:{nonce}".encode(), hashlib.sha256).digest()
    return f"{int.from_bytes(d[:8], 'big') % 1_000_000:06d}"


def hash_codigo(codigo: str) -> str:
    return hashlib.sha256(codigo.encode()).hexdigest()


def vincular(db: Session, u: Usuario, repo: str, repo_id: int, owner_id, descripcion: str) -> None:
    """Deja al usuario ligado a ese repo y registra el cambio de sistema. No hace commit."""
    u.repo, u.repo_id = repo, repo_id
    try:
        u.github_owner_id = int(owner_id)
    except (TypeError, ValueError):
        pass
    db.add(Cambio(atleta_id=u.id, autor_id=None, via="sistema", visto=True, descripcion=descripcion,
                  antes=None, despues={"repo": repo, "repo_id": repo_id}))


def pendiente_vigente(db: Session, usuario_id: int) -> VinculoPendiente | None:
    p = db.get(VinculoPendiente, usuario_id)
    if p and (p.expira < ahora() or p.intentos >= MAX_INTENTOS):
        db.delete(p)
        db.commit()
        return None
    return p


def usuario_del_token(db: Session, claims: dict, secret_key: str = "") -> Usuario:
    """Dueño del repo del token. Un repo nuevo NO se vincula por coincidir el owner (cualquiera podría escribir el
    usuario de otra persona): se genera un código de 6 dígitos que solo se ve en el resumen de la corrida del repo
    privado, y la persona lo escribe en la web (ver `onboarding`). Repos no privados no se vinculan solos
    (`web.cli vincular`). TuboError 403 si no hay usuario; trae `codigo` cuando hay uno pendiente."""
    try:
        repo_id = int(claims["repository_id"])
    except (TypeError, ValueError):
        raise TuboError(401, "token sin repositorio") from None
    u = db.scalar(select(Usuario).where(Usuario.repo_id == repo_id, Usuario.borrado.is_(None)))
    if u:
        return u
    if claims.get("repository_visibility") != "private":
        raise TuboError(403, "repo no vinculado")   # público o sin dato: solo con `web.cli vincular`
    owner = str(claims["repository_owner"]).lower()
    candidatos = [c for c in db.scalars(select(Usuario).where(Usuario.repo_id.is_(None), Usuario.borrado.is_(None)))
                  if (c.github_owner or "").lower() == owner]
    if len(candidatos) != 1:
        raise TuboError(403, "repo no vinculado")
    u = candidatos[0]
    if db.scalar(select(Consentimiento.id).where(Consentimiento.usuario_id == u.id)) is None:
        raise TuboError(403, "repo no vinculado")   # sin consentimiento expreso no se vincula nada
    p = pendiente_vigente(db, u.id)
    if p is None or p.repo_id != repo_id:
        nonce = secrets.token_hex(16)
        codigo = codigo_de(secret_key, nonce)
        if p:
            db.delete(p)
            db.flush()
        p = VinculoPendiente(usuario_id=u.id, repo=str(claims.get("repository") or ""), repo_id=repo_id,
                             owner_id=_entero(claims.get("repository_owner_id")), nonce=nonce,
                             codigo_hash=hash_codigo(codigo), expira=ahora() + timedelta(minutes=MINUTOS_CODIGO))
        db.add(p)
        db.commit()
    raise TuboError(403, "repo no vinculado", {"codigo": codigo_de(secret_key, p.nonce), "vence_en_min": MINUTOS_CODIGO})


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
        return usuario_del_token(db, claims, settings.secret_key)

    def error(e: TuboError):
        return JSONResponse({"error": e.mensaje, **e.extra}, status_code=e.status)

    @app.post("/api/tubo/instrucciones")
    def instrucciones(request: Request, db=Depends(get_db)):
        try:
            return instrucciones_de(db, autenticar(request, db))
        except TuboError as e:
            return error(e)

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
            return JSONResponse({"error": "paquete no válido", "problemas": problemas}, status_code=422)
        try:
            datos.guardar_paquete(db, u.id, pq)
        except Exception as e:   # no se guarda a medias
            db.rollback()
            log.exception("falló guardar el paquete de %s", u.id)
            db.add(Subida(usuario_id=u.id, motor=motor, bytes=len(crudo), ok=False, error=type(e).__name__))
            db.commit()
            return JSONResponse({"error": "no se pudo guardar"}, status_code=500)
        _importar_personales(db, u, pq.get("personales"))
        db.add(Subida(usuario_id=u.id, motor=motor, bytes=len(crudo), ok=True))
        u.historial_desde = None   # el pedido pendiente se cumplió con esta subida
        db.commit()
        return {"ok": True, "publicar_pages": not u.migrado}
