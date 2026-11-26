"""F6b: servidor MCP (HTTP streamable) en /mcp, con las herramientas de lectura.

Exige un token de acceso OAuth vigente (F6a). Las lecturas devuelven lo mismo que el data.json (ya pasó por la
lista blanca: jamás `serie`); cada una acepta `atleta` y se revisa con `puede_ver`.
"""
import contextlib
import contextvars
import json
from datetime import timezone

from sqlalchemy import select

from . import ajustes_web, calculo, cambios, oauth
from .modelos import Coach, Usuario
from .permisos import puede_ver

REGLAS = ("Reglas fijas: haz cambios conservadores (poco a poco, nunca saltos grandes); si la persona reporta dolor, "
          "dile que pare y descanse; esto no es consejo médico.")
_ACTOR: contextvars.ContextVar = contextvars.ContextVar("mcp_actor", default=None)


from mcp.server.mcpserver.exceptions import ToolError  # noqa: E402


class Rechazo(ToolError):
    """Mensaje en español que la IA le puede repetir a la persona (el SDK solo muestra el texto de ToolError)."""


def resolver(db, actor: Usuario, atleta: int | None) -> Usuario:
    """Por defecto, el propio actor; otra persona solo si puede_ver (404 equivalente: mismo mensaje exista o no)."""
    if atleta is None or atleta == actor.id:
        return actor
    if not puede_ver(db, actor, atleta):
        raise Rechazo("No tienes acceso a esa persona.")
    a = db.get(Usuario, atleta)
    if a is None or a.borrado is not None:
        raise Rechazo("No tienes acceso a esa persona.")
    return a


def _data(db, actor: Usuario, atleta: int | None, ahora_utc) -> tuple[Usuario, dict]:
    a = resolver(db, actor, atleta)
    try:
        return a, calculo.calcular(db, a, ahora_utc, "" if a.id == actor.id else f"/a/{a.id}")
    except calculo.SinConfig:
        raise Rechazo("Esa persona aún no tiene ajustes ni plan.")
    except Exception:
        raise Rechazo("No se pudo preparar la información.")


def _trozo(d: dict, *claves) -> dict:
    return {k: d[k] for k in claves if k in d}


def resumen_hoy(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    return {**_trozo(d, "generado", "datos_al", "hoy", "ultima_corrida", "rhr_promedio_7d", "aviso_zonas", "carreras")}


def semana(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    return _trozo(d, "semana", "semana_hoy_idx")


def plan(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    return _trozo(d, "plan", "semanas_hoy", "semana_hoy_idx", "carreras", "mejores_marcas")


def corridas_recientes(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    p = d.get("progreso") or {}
    return {"ultima_corrida": d.get("ultima_corrida"), "corridas": (p.get("corridas") or [])[-10:],
            "mejores_marcas": d.get("mejores_marcas")}


def progreso(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    return {"progreso": d.get("progreso"), "composicion": d.get("composicion"), "detalles": d.get("detalles")}


def ver_ajustes(db, actor, atleta, ahora) -> dict:
    a = resolver(db, actor, atleta)
    crudo = ajustes_web.crudo_de(db, a)
    if crudo is None:
        raise Rechazo("Esa persona aún no tiene ajustes.")
    return {"ajustes": crudo}


def historial(db, actor, atleta, ahora) -> dict:
    a = resolver(db, actor, atleta)
    return {"cambios": [{"id": c.id, "fecha": c.fecha.isoformat(timespec="minutes"), "quien": cambios.autor_texto(db, c),
                         "via": c.via, "descripcion": c.descripcion, "se_puede_deshacer": cambios.puede_deshacer(c)}
                        for c in cambios.historial(db, a.id, 30)]}


def mis_atletas(db, actor, atleta, ahora) -> dict:
    filas = db.execute(select(Usuario).join(Coach, Coach.atleta_id == Usuario.id)
                       .where(Coach.coach_id == actor.id, Usuario.borrado.is_(None)).order_by(Coach.creado)).scalars()
    return {"yo": {"id": actor.id, "nombre": cambios.nombre_de(db, actor.id)},
            "atletas": [{"id": u.id, "nombre": cambios.nombre_de(db, u.id)} for u in filas]}


# (nombre, función, descripción)
LECTURAS = [
    ("resumen_hoy", resumen_hoy, "Resumen de hoy: semáforo de recuperación, qué toca hoy y la última corrida."),
    ("semana", semana, "La semana en curso: sesiones del plan contra lo hecho, minutos y kilómetros."),
    ("plan", plan, "El plan completo por semanas, carreras y mejores marcas."),
    ("corridas_recientes", corridas_recientes, "Las últimas corridas con FC promedio, tiempo sobre el techo y plan contra real."),
    ("progreso", progreso, "Progreso de la base aeróbica y composición corporal (InBody)."),
    ("ver_ajustes", ver_ajustes, "Los ajustes actuales (nivel, actividades, días, carreras, eventos)."),
    ("historial", historial, "Los últimos cambios hechos al plan y a los ajustes, y quién los hizo."),
    ("mis_atletas", mis_atletas, "Las personas que entrenas como coach (la tuya siempre va incluida). Úsalo para obtener el `atleta` de las otras herramientas."),
]


def construir(app):
    """El MCPServer con las herramientas y la app ASGI con la verificación del token."""
    from mcp.server.mcpserver import MCPServer

    srv = MCPServer("Ahí la Llevas", instructions="Entrenamiento de la persona que te conectó. " + REGLAS)

    def registrar(nombre, fn, desc):
        def herramienta(atleta: int | None = None) -> str:
            actor_id = _ACTOR.get()
            with app.state.sesiones() as db:
                actor = db.get(Usuario, actor_id) if actor_id else None
                if actor is None:
                    raise Rechazo("Sin sesión.")
                ahora = app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None)
                return json.dumps(fn(db, actor, atleta, ahora), ensure_ascii=False, default=str)
        herramienta.__name__ = nombre
        srv.add_tool(herramienta, name=nombre, description=f"{desc} `atleta` (opcional): id de otra persona a la que entrenas. {REGLAS}")

    for n, f, d in LECTURAS:
        registrar(n, f, d)
    return srv


def montar(app, settings) -> None:
    base = settings.base_url.rstrip("/")
    srv = construir(app)
    from urllib.parse import urlsplit

    from mcp.server.transport_security import TransportSecuritySettings
    host = urlsplit(base).netloc
    seguridad = TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=[host, "localhost:*", "127.0.0.1:*"],
                                          allowed_origins=[base, "https://claude.ai", "https://chatgpt.com"])
    interna = srv.streamable_http_app(streamable_http_path="/", stateless_http=True, transport_security=seguridad)
    reto = f'Bearer resource_metadata="{base}/.well-known/oauth-protected-resource"'

    async def con_token(scope, receive, send):
        if scope["type"] != "http":
            return await interna(scope, receive, send)
        cab = {k.decode().lower(): v.decode("latin-1") for k, v in scope["headers"]}
        partes = cab.get("authorization", "").split(" ", 1)
        token = partes[1].strip() if len(partes) == 2 and partes[0].lower() == "bearer" else None
        with app.state.sesiones() as db:
            u = oauth.usuario_de_token(db, token, app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None))
            uid = u.id if u else None
        if uid is None:
            cuerpo = b'{"error":"invalid_token"}'
            await send({"type": "http.response.start", "status": 401, "headers": [
                (b"www-authenticate", reto.encode()), (b"content-type", b"application/json"),
                (b"content-length", str(len(cuerpo)).encode()), (b"cache-control", b"no-store")]})
            return await send({"type": "http.response.body", "body": cuerpo})
        tok = _ACTOR.set(uid)
        try:
            await interna(scope, receive, send)
        finally:
            _ACTOR.reset(tok)

    previo = app.router.lifespan_context

    @contextlib.asynccontextmanager
    async def vida(a):
        async with previo(a), srv.session_manager.run():
            yield

    app.router.lifespan_context = vida
    app.mount("/mcp", con_token)
