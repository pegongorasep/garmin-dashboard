"""F6b: servidor MCP (HTTP streamable) en /mcp, con las herramientas de lectura.

Exige un token de acceso OAuth vigente (F6a). Las lecturas devuelven lo mismo que el data.json (ya pasó por la
lista blanca: jamás `serie`); cada una acepta `atleta` y se revisa con `puede_ver`.
"""
import contextlib
import contextvars
import inspect
import json
from datetime import date, timezone

from ajustes import ConfigError, normalizar_config
from sqlalchemy import select

import build

from . import ajustes_web as aw
from . import calculo, cambios, oauth, plan_vivo
from .modelos import Coach, Usuario
from .permisos import puede_editar, puede_ver
from .plan_web import _fecha

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


def _con_plan(a: Usuario) -> None:
    if a.sin_plan:
        raise Rechazo("Esa persona no tiene plan de running (solo ve cómo va). Usa resumen_hoy, corridas_recientes o progreso; "
                      "para tener plan, ella misma debe pedirlo en Ajustes.")


def _trozo(d: dict, *claves) -> dict:
    return {k: d[k] for k in claves if k in d}


def resumen_hoy(db, actor, atleta, ahora) -> dict:
    _, d = _data(db, actor, atleta, ahora)
    return {**_trozo(d, "generado", "datos_al", "hoy", "ultima_corrida", "rhr_promedio_7d", "aviso_zonas", "carreras")}


def semana(db, actor, atleta, ahora) -> dict:
    _con_plan(resolver(db, actor, atleta))
    _, d = _data(db, actor, atleta, ahora)
    return _trozo(d, "semana", "semana_hoy_idx")


def plan(db, actor, atleta, ahora) -> dict:
    _con_plan(resolver(db, actor, atleta))
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
    crudo = aw.crudo_de(db, a)
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


# ---------- escrituras (F6c): mismas funciones que los botones, vía "ia" ----------

def _editable(db, actor, atleta) -> tuple[Usuario, dict, dict | None, date]:
    a = resolver(db, actor, atleta)
    if not puede_editar(db, actor, a.id):
        raise Rechazo("Solo puedes ver a esa persona, no cambiarle el plan.")
    _con_plan(a)
    crudo = aw.crudo_de(db, a)
    if crudo is None:
        raise Rechazo("Esa persona aún no tiene ajustes ni plan.")
    return a, crudo, aw.plan_guardado(db, a), None


def _guardar(db, actor, a, desc, paquete) -> dict:
    try:
        c = cambios.aplicar_cambio(db, a, actor, "ia", desc, paquete)
    except cambios.SinPermiso:
        raise Rechazo("No tienes permiso para cambiar a esa persona.")
    return {"hecho": desc, "cambio_id": c.id,
            "para_deshacer": f"Llama a la herramienta `deshacer` con cambio_id={c.id}" +
                             ("" if cambios.puede_deshacer(c) else " (este cambio no se puede deshacer: avísale a la persona)")}


def _hoy(ahora, crudo) -> date:
    return aw.hoy_de(lambda: ahora.replace(tzinfo=timezone.utc), crudo)


def agregar_carrera(db, actor, ahora, atleta, *, fecha: str, nombre: str = "Carrera", distancia_km: float | None = None) -> dict:
    """Agrega una carrera objetivo (fecha AAAA-MM-DD, hoy o después)."""
    a, crudo, plan, _ = _editable(db, actor, atleta)
    try:
        f = _fecha(fecha, "fecha de la carrera")
        if f < _hoy(ahora, crudo).isoformat():
            raise ConfigError("fecha de la carrera: debe ser hoy o después")
        hoy = _hoy(ahora, crudo)
        cfg = plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), hoy)
        nuevo, plan_nuevo = plan_vivo.agregar_carrera_en_plan(crudo, plan, cfg, f, str(distancia_km) if distancia_km else None,
                                                              nombre.strip() or "Carrera", hoy)
    except (ConfigError, ValueError) as ex:
        raise Rechazo(str(ex)) from None
    return _guardar(db, actor, a, f"Agregó la carrera «{nombre.strip() or 'Carrera'}» el {f} (IA)",
                    {"ajustes": nuevo, **({"plan": plan_nuevo} if plan_nuevo is not None else {})})


def agregar_evento(db, actor, ahora, atleta, *, tipo: str, desde: str, hasta: str | None = None, modo: str | None = None) -> dict:
    """Agrega un evento al plan: tipo `viaje`, `enfermedad` o `lesion`. Para viaje, `modo`: `pausa` (sin correr, el plan espera),
    `menos` (semana ligera) o `igual` (sigue entrenando igual; es lo que se usa si la persona dice que va a seguir entrenando).
    Enfermedad y lesión siempre pausan el plan; sin `hasta` queda abierto hasta que la persona esté bien."""
    a, crudo, plan, _ = _editable(db, actor, atleta)
    if tipo not in ("viaje", "enfermedad", "lesion"):
        raise Rechazo("tipo: elige viaje, enfermedad o lesion.")
    try:
        d = _fecha(desde, "desde")
        h = _fecha(hasta, "hasta") if hasta else None
        if tipo == "viaje":
            if not h:
                raise ConfigError("Un viaje necesita fecha de regreso (`hasta`).")
            modo = modo or "igual"
            if modo not in ("pausa", "menos", "igual"):
                raise ConfigError("modo: pausa, menos o igual.")
        else:
            modo = None
        nuevo = plan_vivo.agregar_evento(crudo, tipo, d, h, modo=modo)
    except (ConfigError, ValueError) as ex:
        raise Rechazo(str(ex)) from None
    return _guardar(db, actor, a, f"Agregó {tipo} desde {d}" + (f" hasta {h}" if h else "") + (f" (modo {modo})" if modo else "") + " (IA)",
                    {"ajustes": nuevo})


def editar_sesion(db, actor, ahora, atleta, *, semana: int, sesion_id: str, filas: list[dict], veces: dict[str, int] | None = None) -> dict:
    """Reemplaza los pasos de una sesión Z2, larga o variada. Cada fila: {tipo: trote|caminata, min, zona: Z1..Z5, grupo: 0-4,
    nota, opcional}. Las filas con el mismo `grupo` (1-4) se repiten `veces[grupo]` veces."""
    a, crudo, plan, _ = _editable(db, actor, atleta)
    try:
        if not plan:
            raise ConfigError("Esa persona aún no tiene plan.")
        nuevo = plan_vivo.editar_sesion(plan, semana, sesion_id,
                                        plan_vivo.pasos_de_filas(filas, {int(k): int(x) for k, x in (veces or {}).items()}))
    except (ConfigError, ValueError, KeyError, TypeError) as ex:
        raise Rechazo(str(ex) if not isinstance(ex, KeyError) else "Faltan datos.") from None
    return _guardar(db, actor, a, f"Cambió la sesión {sesion_id} de la semana {semana} (IA)", {"plan": nuevo})


def repetir_semana(db, actor, ahora, atleta) -> dict:
    """Repite la semana del plan en curso (el plan se recorre una semana)."""
    a, crudo, plan, _ = _editable(db, actor, atleta)
    try:
        cfg = plan_vivo.con_pausas(normalizar_config({**crudo, "modo": "web"}), _hoy(ahora, crudo))
        n = build.m.semana_del_plan(_hoy(ahora, crudo), cfg)
        if n is None:
            raise ConfigError("Hoy no hay una semana de plan para repetir.")
        nuevo = plan_vivo.repetir_semana(crudo, n)
    except (ConfigError, ValueError) as ex:
        raise Rechazo(str(ex)) from None
    return _guardar(db, actor, a, f"Repitió la semana {n} (IA)", {"ajustes": nuevo})


def registrar_inbody(db, actor, ahora, atleta, *, fecha: str, peso_kg: float, mme_kg: float | None = None,
                     pgc: float | None = None, grasa_kg: float | None = None) -> dict:
    """Agrega o reemplaza la medición InBody de un día (peso, masa muscular esquelética, % de grasa)."""
    a, crudo, plan, _ = _editable(db, actor, atleta)
    campos = {"fecha": fecha, "peso_kg": peso_kg, "mme_kg": mme_kg, "pgc": pgc, "grasa_kg": grasa_kg}
    form = {k: str(v) for k, v in campos.items() if v is not None}
    meds = cambios.instantanea(db, a.id, ("inbody",))["inbody"]
    try:
        previa = next((x for x in meds if x["fecha"] == fecha), None)
        med = aw.medicion_desde_form(form, previa)
    except (ConfigError, ValueError) as ex:
        raise Rechazo(str(ex)) from None
    nuevas = sorted([x for x in meds if x["fecha"] != med["fecha"]] + [med], key=lambda x: x["fecha"])
    return _guardar(db, actor, a, f"{'Editó' if previa else 'Agregó'} la medición InBody del {med['fecha']} (IA)", {"inbody": nuevas})


def deshacer(db, actor, ahora, atleta, *, cambio_id: int) -> dict:
    """Deshace un cambio (el `cambio_id` viene en la respuesta de cada escritura o en `historial`)."""
    try:
        nuevo = cambios.deshacer(db, actor, cambio_id, via="ia")
    except cambios.SinPermiso:
        raise Rechazo("No encontré ese cambio o no tienes permiso.") from None
    except cambios.NoSeDeshace as ex:
        raise Rechazo(str(ex)) from None
    return {"hecho": "Deshizo el cambio.", "cambio_id": nuevo.id}


ESCRITURAS = [("agregar_carrera", agregar_carrera), ("agregar_evento", agregar_evento),
              ("editar_sesion", editar_sesion), ("repetir_semana", repetir_semana),
              ("registrar_inbody", registrar_inbody), ("deshacer", deshacer)]



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

    def registrar_escritura(nombre, fn):
        params = list(inspect.signature(fn).parameters.values())[4:]   # tras db, actor, ahora, atleta
        firma = inspect.Signature([inspect.Parameter("atleta", inspect.Parameter.KEYWORD_ONLY, default=None, annotation=int | None),
                                   *params])

        def herramienta(**kw):
            actor_id = _ACTOR.get()
            with app.state.sesiones() as db:
                actor = db.get(Usuario, actor_id) if actor_id else None
                if actor is None:
                    raise Rechazo("Sin sesión.")
                ahora = app.state.reloj().astimezone(timezone.utc).replace(tzinfo=None)
                return json.dumps(fn(db, actor, ahora, kw.pop("atleta", None), **kw), ensure_ascii=False, default=str)
        herramienta.__signature__ = firma
        herramienta.__annotations__ = {p.name: p.annotation for p in firma.parameters.values()}
        herramienta.__name__ = nombre
        doc = " ".join((fn.__doc__ or "").split())
        srv.add_tool(herramienta, name=nombre, description=f"{doc} Devuelve qué cambió y cómo deshacerlo. `atleta` (opcional): "
                     f"id de otra persona a la que entrenas. {REGLAS}")

    for n, f, d in LECTURAS:
        registrar(n, f, d)
    for n, f in ESCRITURAS:
        registrar_escritura(n, f)
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

    class _Exacta:   # Claude y ChatGPT llaman a BASE_URL/mcp sin diagonal; el Mount solo atiende /mcp/…
        async def __call__(self, scope, receive, send):
            raiz = scope.get("root_path", "")
            await con_token(dict(scope, path=raiz + "/mcp/", raw_path=(raiz + "/mcp/").encode(), root_path=raiz + "/mcp"),
                            receive, send)

    from starlette.routing import Route
    app.router.routes.insert(0, Route("/mcp", _Exacta()))
