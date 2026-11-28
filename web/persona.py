"""Social S5: el perfil de una persona dentro de Juntos (`GET /api/juntos/persona/<id>`).

Todo sale del data.json ya calculado (y en caché) de esa persona, igual que `feed.py` y `grupos_resumen.py`, y solo una lista blanca:
nombre, foto, nivel, grupos en común, minutos de la semana, qué le falta del plan, el plan por bloques (sesiones del plan, no nombres de
Garmin), minutos por semana, racha, carreras (distancia y fecha) y actividades (las del feed). Nunca nombres de Garmin, GPS, IDs, fecha
de nacimiento, correo, peso/InBody, HRV ni FC en reposo. Quién la ve lo decide `permisos` (grupo en común + interruptores);
sin grupo en común es 404. El perfil propio sale como lo vería un miembro de tus grupos (respeta tus interruptores).
"""
import logging
from datetime import date

from fastapi import Depends
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

import semanal

from . import calculo, feed, grupos, permisos, semana_plan
from .modelos import Grupo, MiembroGrupo, Plan, Usuario

log = logging.getLogger("web.persona")

MAX_CARRERAS = 3
NIVELES = ("empezando", "base", "corredor")
ACTIVIDADES_PERFIL = 10


def _en_comun(db: Session, viewer: Usuario, dueno: Usuario) -> list[dict]:
    """Grupos que comparten (para sí mismo: todos los suyos), por nombre."""
    mios = select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == viewer.id)
    suyos = select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == dueno.id)
    filas = db.scalars(select(Grupo).where(Grupo.id.in_(mios), Grupo.id.in_(suyos)).order_by(Grupo.nombre)).all()
    return [{"id": g.id, "nombre": g.nombre} for g in filas]


def _en_pausa(db: Session, viewer: Usuario, dueno: Usuario) -> bool:
    """En pausa en todos los grupos que comparten con quien mira (igual que el feed): sus datos no salen."""
    if viewer.id == dueno.id:
        return False
    mios = select(MiembroGrupo.grupo_id).where(MiembroGrupo.usuario_id == viewer.id)
    pausas = db.scalars(select(MiembroGrupo.pausado).where(MiembroGrupo.usuario_id == dueno.id, MiembroGrupo.grupo_id.in_(mios))).all()
    return bool(pausas) and all(pausas)


def _nivel(db: Session, uid: int) -> str | None:
    p = db.get(Plan, uid)
    n = ((p.plan or {}).get("meta") or {}).get("nivel") if p else None
    return n if n in NIVELES else None


def _datos(db: Session, dueno: Usuario) -> dict | None:
    try:
        return calculo.calcular(db, dueno)
    except Exception:   # sin ajustes, sin datos o data.json inválido: el perfil sale sin esas secciones
        log.info("persona: usuario %s sin data.json", dueno.id, exc_info=True)
        return None


def perfil(db: Session, viewer: Usuario, dueno_id: int, secret: str) -> dict | None:
    """El perfil de `dueno_id` visto por `viewer`; None = 404."""
    if not permisos.puede_ver_social(db, viewer, dueno_id):
        return None
    dueno = db.get(Usuario, dueno_id)
    mia = viewer.id == dueno.id
    pausa = _en_pausa(db, viewer, dueno)
    # Verlo uno mismo respeta los interruptores: así lo ve un miembro de tus grupos.
    ver_plan = False if pausa else bool(dueno.compartir_plan) if mia else permisos.puede_ver_plan(db, viewer, dueno.id)
    ver_act = False if pausa else bool(dueno.compartir_actividades) if mia else permisos.puede_ver_actividades(db, viewer, dueno.id)
    out = {"usuario_id": dueno.id, "nombre": grupos.nombre_de(dueno), "mia": mia, "pausa": pausa,
           "foto": f"/perfil/foto/{dueno.id}" if grupos.perfil_tiene_foto(db, dueno.id) else None,
           "nivel": _nivel(db, dueno.id), "grupos": _en_comun(db, viewer, dueno),
           "comparte": {"plan": ver_plan, "actividades": ver_act},
           "interruptores": {"plan": bool(dueno.compartir_plan), "actividades": bool(dueno.compartir_actividades)},
           "semana": None, "plan": None, "progreso": None, "actividades": None}
    data = None if pausa else _datos(db, dueno)
    if data and (data.get("plan") or {}).get("nivel") in NIVELES:
        out["nivel"] = data["plan"]["nivel"]   # misma fuente que el sitio; sin data.json (pausa) queda el de la base
    if data:
        hoy = (data.get("generado") or date.today().isoformat())[:10]
        semanas, idx = data.get("semanas_hoy") or [], data.get("semana_hoy_idx") or 0
        actual = semanas[idx] if idx < len(semanas) else None
        libre = data.get("semana_libre")
        if actual and actual.get("plan"):
            out["semana"] = semana_plan.semana_vs_plan(actual, False)
            if ver_plan:
                out["semana"] = semana_plan.semana_vs_plan(actual, True)
                out["plan"] = semanal.plan_visible(data.get("plan"), ver_act)   # el mismo plan de la pestaña Plan, sin lo privado
        elif libre:
            out["semana"] = {"minutos": round(libre.get("minutos") or 0), "objetivo": None, "faltan": []}
        prog = {"semanas": [{"inicio": s["inicio"], "actual": bool(s.get("actual")), "minutos": round(s.get("minutos") or 0), "km": round(s.get("km") or 0, 1)}
                            for s in (data.get("progreso") or {}).get("semanas") or []],   # el largo lo decide semanal.serie_semanas
                "periodos": [{k: v for k, v in o.items() if k in ("n", "todo", "desde", "hasta")}
                             for o in (data.get("progreso") or {}).get("periodos") or [] if ver_plan or not o.get("todo")],   # 4/8/12 y (si comparte el plan) todo el plan
                "racha": None, "carreras": None}
        if ver_plan:
            prog["racha"] = (data.get("racha") or {}).get("semanas") or 0
            prog["carreras"] = [{"fecha": e["desde"][:10], "distancia_km": e.get("distancia_km")}
                                for e in (data.get("plan") or {}).get("eventos") or [] if e["tipo"] == "carrera" and e["desde"][:10] >= hoy][:MAX_CARRERAS]
        out["progreso"] = prog
    if ver_act:
        f = feed.feed(db, viewer, secret, None, persona=dueno.id, por_pagina=ACTIVIDADES_PERFIL)
        out["actividades"] = {"items": f["items"], "siguiente": f["siguiente"]}
        out["emojis"] = f["emojis"]
    return out


def montar(app, get_db, actual, settings) -> None:
    @app.get("/api/juntos/persona/{uid}")
    def api_persona(uid: int, usuario=Depends(actual), db: Session = Depends(get_db)):
        if usuario is None:
            return JSONResponse({"error": "Entra primero."}, status_code=401)
        p = perfil(db, usuario, uid, settings.secret_key)
        if p is None:
            return JSONResponse({"error": "No encontrado."}, status_code=404)
        return {**p, "yo": usuario.id}
