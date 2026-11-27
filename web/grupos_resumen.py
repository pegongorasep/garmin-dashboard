"""Tarjetas de avance de los miembros de un grupo: solo campos de lista blanca, calculados del data.json de cada quien
(el mismo que usa Hoy: `calculo.calcular`, así «hecha» y «no hecha» salen de la misma lógica)."""
import logging
from datetime import date, timedelta

from sqlalchemy.orm import Session

from dashboard.build import cumplimiento_semana

from . import calculo, semana_plan
from .modelos import Ajustes, MiembroGrupo, Plan, Usuario

log = logging.getLogger("web.grupos_resumen")

CAMPOS = {"usuario_id", "estado", "meta", "etapa_n", "adherencia", "dias", "ultima", "libre",
          "semana", "plan", "progreso", "racha", "carrera", "sem_plan", "cal"}   # lo único que sale de una tarjeta
MAX_NOVEDADES = 3
# Emoji de cada categoría de «otras sesiones» (la pestaña solo pinta). Lo que no esté aquí usa «otra».
EMOJI_CATEGORIA = {"crossfit": "🔥", "hiit": "🔥", "fuerza": "🏋️", "gym": "🏋️", "pesas": "🏋️", "bici": "🚴", "cardio": "🚴",
                   "nado": "🏊", "natacion": "🏊", "caminata": "🚶", "walking": "🚶", "movilidad": "🤸", "yoga": "🤸", "otra": "🤸"}
SEMANAS_ADHERENCIA = 4


def _adherencia(semanas: list) -> int | None:
    """% de sesiones hechas en las últimas semanas pasadas con plan (o en la actual si aún no hay pasadas)."""
    con_plan = [s for s in semanas if s.get("plan")]
    base = [s for s in con_plan if s["estado"] == "pasada"][-SEMANAS_ADHERENCIA:] or [s for s in con_plan if s["estado"] == "actual"]
    total = sum(s["plan"]["total"] for s in base)
    return round(100 * sum(s["plan"]["hechas"] for s in base) / total) if total else None


def _racha(semanas: list, idx: int) -> int:
    """Semanas pasadas seguidas, terminando con la anterior a la actual, con ✓ o ✓✓ (misma regla que las palomitas del Plan)."""
    n = 0
    for s in reversed(semanas[:idx]):
        p = s.get("plan")
        if s.get("estado") != "pasada" or not p or cumplimiento_semana(p["hechas"], p["total"]) not in ("completa", "casi"):
            break
        n += 1
    return n


def _otras(dias: list) -> dict:
    out: dict = {}
    for d in dias:
        for o in d.get("otras") or []:
            out[o["cat"]] = out.get(o["cat"], 0) + 1
    return out


def _tarjeta_cruda(db: Session, usuario: Usuario, miembro: MiembroGrupo) -> tuple[dict, dict]:
    """(tarjeta, hitos): los hitos (corrida más larga, récord, semana completa) alimentan insignias y novedades y no salen."""
    base = {"usuario_id": usuario.id, "estado": "ok", "meta": None, "etapa_n": None, "adherencia": None, "dias": [], "ultima": None,
            "libre": None, "semana": None, "plan": None, "progreso": None, "racha": None, "carrera": None,
            "sem_plan": None, "cal": None}
    if miembro.pausado:
        return {**base, "estado": "pausa"}, {}
    sin_plan = {**base, "estado": "sin_plan"}
    if usuario.sin_plan and usuario.repo_id:   # modo sin plan: su tarjeta sale de `semana_libre` (solo conteos, nada de nombres)
        try:
            sl = calculo.calcular(db, usuario).get("semana_libre")
        except Exception:
            log.warning("tarjeta libre de usuario %s sin datos", usuario.id, exc_info=True)
            return sin_plan, {}
        if not sl:
            return sin_plan, {}
        dias = ["hecha" if d["actividades"] else "futuro" if d["futuro"] else "libre" for d in sl["dias"]]
        items = [a for d in sl["dias"] for a in d["actividades"]]
        otras: dict = {}
        for a in items:
            if a.get("cat", "run") != "run":
                otras[a["cat"]] = otras.get(a["cat"], 0) + 1
        corridas = [a["minutos"] for a in items if a.get("cat", "run") == "run"]
        semana = {"km": round(sl.get("km") or 0, 1), "minutos": sum(a["minutos"] for a in items if a.get("cat", "run") == "run"),
                  "otras": otras, "extra_min": sum(a["minutos"] for a in items if a.get("cat", "run") != "run")}
        hoy_i = max((i for i, d in enumerate(sl["dias"]) if not d["futuro"]), default=-1)
        cal = [{"hoy": i == hoy_i, "hecha": bool(d["actividades"]), "cats": [a.get("cat", "run") for a in d["actividades"]]} for i, d in enumerate(sl["dias"])]
        return ({**base, "estado": "libre", "dias": dias, "semana": semana, "cal": cal,
                 "sem_plan": {"minutos": semana["minutos"] + semana["extra_min"], "objetivo": None, "faltan": []},
                 "libre": {"actividades": sl["actividades"], "minutos": round(sl["minutos"]), "racha": sl["racha_semanas"]}},
                {"larga": max(corridas, default=0)})
    if db.get(Ajustes, usuario.id) is None or db.get(Plan, usuario.id) is None:
        return sin_plan, {}
    try:
        data = calculo.calcular(db, usuario)
    except Exception:   # SinConfig, DataInvalido o lo que sea: la tarjeta no tumba la página del grupo
        log.warning("tarjeta de usuario %s sin datos", usuario.id, exc_info=True)
        return sin_plan, {}
    semanas = data.get("semanas_hoy") or []
    idx = data.get("semana_hoy_idx") or 0
    actual = semanas[idx] if semanas else None
    if not actual or not actual.get("plan"):
        return sin_plan, {}
    hoy = (data.get("generado") or "")[:10]
    dias = ["hecha" if d.get("corrida") else "futuro" if d["fecha"] > hoy else "libre" for d in actual["dias"]]
    carreras = [e for e in (data.get("plan") or {}).get("eventos", []) if e["tipo"] == "carrera" and e["desde"] >= hoy]
    carrera = None
    if carreras:
        try:
            carrera = {"nombre": carreras[0]["nombre"], "dias": (date.fromisoformat(carreras[0]["desde"][:10]) - date.fromisoformat(hoy)).days}
        except ValueError:
            carrera = None
    stats, p = actual.get("stats") or {}, actual["plan"]
    larga = max((d["corrida"]["minutos"] for d in actual["dias"] if d.get("corrida")), default=0)
    semana = {"km": round(stats.get("km") or 0, 1), "minutos": round(stats.get("minutos") or 0), "otras": _otras(actual["dias"]),
              "extra_min": round(sum(o.get("minutos") or 0 for d in actual["dias"] for o in d.get("otras") or []))}
    total_plan = len((data.get("plan") or {}).get("semanas") or []) or None
    racha = _racha(semanas, idx)
    # récord: la corrida más larga (km) de esta semana supera a todas las anteriores desde que empezó el plan
    inicio_plan, ini_sem = (data.get("plan") or {}).get("inicio"), actual.get("inicio")
    km_sem = max((c["km"] or 0 for c in (data.get("progreso") or {}).get("corridas") or [] if ini_sem and c["fecha"] >= ini_sem), default=0)
    previas = [c["km"] or 0 for c in (data.get("progreso") or {}).get("corridas") or []
               if ini_sem and inicio_plan and inicio_plan <= c["fecha"] < ini_sem]
    record = round(km_sem, 1) if previas and km_sem > max(previas) else None
    anterior = semanas[idx - 1] if idx > 0 else None
    pa = (anterior or {}).get("plan")
    hitos = {"larga": larga, "record": record, "racha": racha, "hoy": hoy, "ini_sem": ini_sem,
             "completa_ahora": p["total"] > 0 and p["hechas"] >= p["total"],
             "completa_antes": bool(pa and (anterior or {}).get("estado") == "pasada" and cumplimiento_semana(pa["hechas"], pa["total"]) == "completa"),
             "n": actual.get("n"), "n_antes": (anterior or {}).get("n"), "total": total_plan}
    return ({**base, "meta": carreras[0]["nombre"] if carreras else None, "etapa_n": actual.get("n"),
             "adherencia": _adherencia(semanas), "dias": dias, "ultima": ((data.get("ultima_corrida") or {}).get("fecha")),
             "semana": semana, "plan": {"n": actual.get("n"), "total": total_plan},
             "progreso": {"hechas": p["hechas"], "total": p["total"]}, "racha": racha, "carrera": carrera,
             "sem_plan": semana_plan.semana_vs_plan(actual, True), "cal": semana_plan.calendario_semana(actual["dias"], hoy)}, hitos)


def aplicar_privacidad(usuario: Usuario, t: dict, hitos: dict) -> tuple[dict, dict]:
    """Los dos interruptores de la persona. Sin `compartir_actividades` el grupo solo ve totales de la semana (km, minutos);
    sin `compartir_plan` no sale nada del plan (etapa, avance, adherencia, carrera, racha)."""
    t, hitos = dict(t), dict(hitos)
    if not usuario.compartir_actividades:
        t["dias"], t["ultima"] = [], None
        if t.get("cal"):
            t["cal"] = [{**d, "cats": []} for d in t["cal"]]   # solo días llenos o vacíos, sin categorías
        if t.get("semana"):
            t["semana"] = {**t["semana"], "otras": {}}
        if t.get("libre"):
            t["libre"] = {**t["libre"], "actividades": 0}
        hitos.update({k: v for k, v in (("larga", 0), ("record", None)) if k in hitos})
    if not usuario.compartir_plan:
        t.update(meta=None, etapa_n=None, adherencia=None, plan=None, progreso=None, racha=None, carrera=None)
        if t.get("sem_plan"):
            t["sem_plan"] = {**t["sem_plan"], "objetivo": None, "faltan": []}   # solo minutos
        if t.get("libre"):
            t["libre"] = {**t["libre"], "racha": 0}
        hitos.update({k: v for k, v in (("completa_ahora", False), ("completa_antes", False), ("racha", 0)) if k in hitos})
    return t, hitos


def _tarjeta(db: Session, usuario: Usuario, miembro: MiembroGrupo) -> tuple[dict, dict]:
    return aplicar_privacidad(usuario, *_tarjeta_cruda(db, usuario, miembro))


def tarjeta_de(db: Session, usuario: Usuario, miembro: MiembroGrupo) -> dict:
    return _tarjeta(db, usuario, miembro)[0]


def _con_actividad(t: dict) -> bool:
    s = t.get("semana")
    return bool(s and (s["km"] > 0 or s["minutos"] > 0 or s["extra_min"] > 0 or s["otras"]))


def _mejores(valores: dict) -> list:
    """Ids con el valor más alto (empates: todos); nadie con 0."""
    tope = max(valores.values(), default=0)
    return sorted(u for u, v in valores.items() if tope > 0 and v == tope)


def total_grupo(tarjetas: list) -> dict:
    """«Juntos llevan X km y Y h» esta semana, sin las personas en pausa: {km, minutos (corridas y otras)}."""
    vivas = [t for t in tarjetas if t["semana"]]
    return {"km": round(sum(t["semana"]["km"] for t in vivas), 1),
            "minutos": sum(t["semana"]["minutos"] + t["semana"]["extra_min"] for t in vivas)}


def insignias(tarjetas: list, hitos: dict) -> list:
    """[{clave, usuario_ids}] de la semana; solo si al menos 2 personas (sin pausa) tienen actividad."""
    activas = [t for t in tarjetas if t["estado"] in ("ok", "libre") and _con_actividad(t)]
    if len(activas) < 2:
        return []
    pct = {t["usuario_id"]: round(100 * t["progreso"]["hechas"] / t["progreso"]["total"])
           for t in activas if t["progreso"] and t["progreso"]["total"]}
    candidatas = [("mas_constante", pct),
                  ("mas_km", {t["usuario_id"]: t["semana"]["km"] for t in activas}),
                  ("corrida_mas_larga", {t["usuario_id"]: (hitos.get(t["usuario_id"]) or {}).get("larga", 0) for t in activas})]
    return [{"clave": c, "usuario_ids": ids} for c, v in candidatas if (ids := _mejores(v))]


def novedades(tarjetas: list, hitos: dict) -> list:
    """Lo notable de esta semana, de lo más nuevo a lo más viejo, máx. 3. Se deriva cada vez: se reinicia solo cada semana ISO."""
    out = []   # (fecha, prioridad, novedad)
    for t in tarjetas:
        h, uid = hitos.get(t["usuario_id"]) or {}, t["usuario_id"]
        if t["estado"] != "ok" or "hoy" not in h:
            continue
        hoy, ini = h["hoy"], h["ini_sem"]
        if h["completa_ahora"]:
            out.append((hoy, 0, {"tipo": "semana_completa", "usuario_id": uid, "datos": {"n": h["n"], "total": h["total"]}}))
        elif h["completa_antes"]:
            out.append((ini, 0, {"tipo": "semana_completa", "usuario_id": uid, "datos": {"n": h["n_antes"], "total": h["total"]}}))
        if h["record"]:
            out.append((hoy, 1, {"tipo": "record_distancia", "usuario_id": uid, "datos": {"km": h["record"]}}))
        if h["racha"] >= 2:
            out.append((ini, 2, {"tipo": "racha", "usuario_id": uid, "datos": {"semanas": h["racha"]}}))
        c = t["carrera"]
        if c and 0 <= c["dias"] <= 7:
            out.append((hoy, 3, {"tipo": "carrera_cerca", "usuario_id": uid, "datos": {"dias": c["dias"]}}))
    out.sort(key=lambda x: (x[0], -x[1]), reverse=True)
    return [n for _, _, n in out[:MAX_NOVEDADES]]


def resumen(db: Session, miembros: list[tuple[MiembroGrupo, Usuario]]) -> dict:
    """{tarjetas {uid: tarjeta}, total, insignias, novedades} del grupo."""
    pares = {u.id: _tarjeta(db, u, m) for m, u in miembros}
    tarjetas_l = [t for t, _ in pares.values()]
    hitos = {uid: h for uid, (_, h) in pares.items()}
    return {"tarjetas": {uid: t for uid, (t, _) in pares.items()}, "total": total_grupo(tarjetas_l),
            "insignias": insignias(tarjetas_l, hitos), "novedades": novedades(tarjetas_l, hitos)}


def tarjetas(db: Session, miembros: list[tuple[MiembroGrupo, Usuario]]) -> dict[int, dict]:
    return resumen(db, miembros)["tarjetas"]
