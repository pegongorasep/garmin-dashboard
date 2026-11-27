"""Social S3: el feed de actividades de «Juntos» y las reacciones por actividad.

Sale del data.json ya calculado (y en caché) de cada persona: la misma fila de actividad del detalle del día del calendario
(`dashboard/build.actividades_del_dia`), así no hay una segunda lógica. Quién aparece lo decide `permisos`: comparten un grupo
(`puede_ver_social`) Y la persona comparte sus actividades (`puede_ver_actividades`), más las propias. Nunca sale el nombre que
Garmin le puso a la actividad, GPS, IDs de Garmin ni fecha de nacimiento: la clave de cada actividad es un HMAC con la SECRET_KEY.
"""
import hashlib
import hmac
import logging
from datetime import date, timedelta

import sqlalchemy as sa
from fastapi import Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import calculo, grupos, grupos_resumen, permisos
from .modelos import MiembroGrupo, ReaccionActividad, Usuario, ahora

log = logging.getLogger("web.feed")

POR_PAGINA = 20
DIAS_ATRAS = 84            # el feed mira las últimas 12 semanas
MAX_PERSONAS = 60          # 5 grupos de 12 como tope: acota el trabajo por petición
MAX_POR_PERSONA = 120
EMOJIS = ("👏", "🔥", "💪", "🚀", "❤️", "😂", "🫡", "🏆")
MAX_REACCIONES_HORA = 60
# Lo único del detalle de la actividad que sale al feed (nada de curvas ni ritmos por km).
CAMPOS_DETALLE = ("fc_max", "kcal", "desnivel_m", "te_etiqueta", "zonas", "ritmo_s", "vel_kmh", "cadencia")


def clave_actividad(secret: str, uid: int, fecha: str, cat: str, minutos, n: int) -> str:
    """Clave opaca y estable de una actividad: HMAC(SECRET_KEY, persona, día, tipo, minutos, n-ésima igual ese día)."""
    msg = f"{uid}|{fecha}|{cat}|{minutos}|{n}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()[:24]


def duenos_visibles(db: Session, viewer: Usuario) -> list[Usuario]:
    """Quién aparece en el feed de `viewer`: él mismo y quienes comparten grupo con él, con `compartir_actividades` encendido
    y sin estar en pausa en todos los grupos que comparten."""
    mios = select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == viewer.id)
    filas = db.execute(select(MiembroGrupo.usuario_id, MiembroGrupo.pausado)
                       .where(MiembroGrupo.grupo_id.in_(mios), MiembroGrupo.usuario_id != viewer.id)).all()
    activos: dict[int, bool] = {}
    for uid, pausado in filas:
        activos[uid] = activos.get(uid, False) or not pausado
    ids = [uid for uid, ok in sorted(activos.items()) if ok][:MAX_PERSONAS]
    out = [viewer]
    for uid in ids:
        if permisos.puede_ver_social(db, viewer, uid) and permisos.puede_ver_actividades(db, viewer, uid):
            out.append(db.get(Usuario, uid))
    return out


def _emoji(cat: str, carrera: bool) -> str:
    if carrera:
        return "🏅"
    return "🏃" if cat == "run" else grupos_resumen.EMOJI_CATEGORIA.get(cat) or grupos_resumen.EMOJI_CATEGORIA["otra"]


def actividades_de(db: Session, dueno: Usuario, secret: str, con_plan: bool) -> list[dict]:
    """Actividades recientes de una persona, de la más nueva a la más vieja (su fila del calendario + clave opaca).
    `con_plan`: el que mira puede ver el plan de ella, y entonces sale «✓ sesión, semana N»."""
    try:
        data = calculo.calcular(db, dueno)
    except Exception:   # sin ajustes, sin datos o data.json inválido: simplemente no aporta al feed
        log.info("feed: usuario %s sin data.json", dueno.id, exc_info=True)
        return []
    desde = (date.today() - timedelta(days=DIAS_ATRAS)).isoformat()
    vistas: dict = {}
    out = []
    for semana in data.get("semanas_hoy") or []:
        for dia in semana.get("dias") or []:
            if dia["fecha"] < desde:
                continue
            for idx, a in enumerate(dia.get("actividades") or []):
                k = (dia["fecha"], a["cat"], a["minutos"])
                vistas[k] = vistas.get(k, -1) + 1
                ses = a.get("sesion") if con_plan else None
                det = a.get("detalle") or {}
                out.append({
                    "clave": clave_actividad(secret, dueno.id, dia["fecha"], a["cat"], a["minutos"], vistas[k]),
                    "usuario_id": dueno.id, "fecha": dia["fecha"], "orden": idx, "cat": a["cat"], "tipo": a["nombre"],
                    "icono": a["icono"], "emoji": _emoji(a["cat"], a.get("carrera", False)), "carrera": bool(a.get("carrera")),
                    "minutos": a["minutos"], "km": a.get("km"), "fc_prom": a.get("fc_prom"),
                    "esfuerzo": a.get("esfuerzo"), "rpe": a.get("rpe"), "trote": a.get("trote"),
                    "partes": [p["minutos"] for p in a.get("partes") or []],
                    "sesion": {"nombre": ses["nombre"], "n": semana.get("n")} if ses and semana.get("n") else None,
                    "detalle": {c: det.get(c) for c in CAMPOS_DETALLE}})
    out.sort(key=lambda x: (x["fecha"], x["orden"]), reverse=True)
    return out[:MAX_POR_PERSONA]


def _cursor(it: dict) -> str:
    return f'{it["fecha"]}~{it["orden"]}~{it["usuario_id"]}'


def _tras(it: dict, cursor: str | None) -> bool:
    if not cursor:
        return True
    try:
        f, o, u = cursor.split("~")
        return (it["fecha"], it["orden"], it["usuario_id"]) < (f, int(o), int(u))
    except ValueError:
        return True


def reacciones_de(db: Session, viewer: Usuario, claves: list[str]) -> dict:
    """{clave: {emoji: {n, quienes [nombres de quienes el que mira ve en sus grupos], mia}}} (solo n >= 1)."""
    if not claves:
        return {}
    filas = db.scalars(select(ReaccionActividad).where(ReaccionActividad.clave.in_(claves)).order_by(ReaccionActividad.id)).all()
    nombres: dict[int, str] = {}
    out: dict = {}
    for r in filas:
        if r.emoji not in EMOJIS:
            continue
        if r.de_id not in nombres:
            nombres[r.de_id] = (grupos.nombre_de(db.get(Usuario, r.de_id)) if permisos.puede_ver_social(db, viewer, r.de_id) else "")
        e = out.setdefault(r.clave, {}).setdefault(r.emoji, {"n": 0, "quienes": [], "mia": False})
        e["n"] += 1
        if nombres[r.de_id]:
            e["quienes"].append(nombres[r.de_id])
        e["mia"] = e["mia"] or r.de_id == viewer.id
    return {k: {e: v[e] for e in EMOJIS if e in v} for k, v in out.items()}


def feed(db: Session, viewer: Usuario, secret: str, antes: str | None = None) -> dict:
    duenos = duenos_visibles(db, viewer)
    items: list[dict] = []
    for d in duenos:
        items += actividades_de(db, d, secret, d.id == viewer.id or permisos.puede_ver_plan(db, viewer, d.id))
    items.sort(key=lambda x: (x["fecha"], x["orden"], x["usuario_id"]), reverse=True)
    items = [x for x in items if _tras(x, antes)]
    pagina, hay_mas = items[:POR_PAGINA], len(items) > POR_PAGINA
    por_id = {d.id: d for d in duenos}
    reac = reacciones_de(db, viewer, [x["clave"] for x in pagina])
    salida = []
    for x in pagina:
        u = por_id[x["usuario_id"]]
        salida.append({**{k: v for k, v in x.items() if k != "orden"}, "nombre": grupos.nombre_de(u),
                       "foto": f"/perfil/foto/{u.id}" if grupos.perfil_tiene_foto(db, u.id) else None,
                       "mia": u.id == viewer.id, "reacciones": reac.get(x["clave"], {})})
    return {"items": salida, "siguiente": _cursor(pagina[-1]) if hay_mas else None, "emojis": list(EMOJIS), "yo": viewer.id}


def montar(app, get_db, actual, formulario, settings) -> None:
    @app.get("/api/juntos/feed")
    def api_feed(antes: str | None = None, usuario=Depends(actual), db: Session = Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        return feed(db, usuario, settings.secret_key, antes)

    @app.post("/api/juntos/reaccionar")
    async def api_reaccionar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db)):
        form = await formulario(request)
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        try:
            dueno_id = int(form.get("dueno", ""))
        except ValueError:
            return JSONResponse({"error": "No encontrado."}, status_code=404)
        clave, emoji = str(form.get("clave", "")), str(form.get("emoji", ""))
        dueno = next((d for d in duenos_visibles(db, usuario) if d.id == dueno_id), None)
        if dueno is None:
            return JSONResponse({"error": "No encontrado."}, status_code=404)
        mia = next((x for x in actividades_de(db, dueno, settings.secret_key, False) if x["clave"] == clave), None)
        if mia is None:
            return JSONResponse({"error": "No encontrado."}, status_code=404)
        if emoji not in EMOJIS:
            return JSONResponse({"error": "Emoji no válido."}, status_code=400)
        previa = db.scalar(select(ReaccionActividad).where(ReaccionActividad.clave == clave, ReaccionActividad.dueno_id == dueno_id,
                                                           ReaccionActividad.de_id == usuario.id, ReaccionActividad.emoji == emoji))
        if previa is not None:
            db.delete(previa)
        else:
            recientes = db.scalar(select(sa.func.count()).select_from(ReaccionActividad).where(
                ReaccionActividad.de_id == usuario.id, ReaccionActividad.creada > ahora() - timedelta(hours=1)))
            if recientes >= MAX_REACCIONES_HORA:
                return JSONResponse({"error": "Demasiadas reacciones."}, status_code=429)
            db.add(ReaccionActividad(clave=clave, dueno_id=dueno_id, de_id=usuario.id, emoji=emoji))
        db.commit()
        return {"clave": clave, "reacciones": reacciones_de(db, usuario, [clave]).get(clave, {})}
