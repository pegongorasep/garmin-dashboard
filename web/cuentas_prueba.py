"""Cuentas de prueba (`algo@prueba.test`) desde /admin: crear, entrar con una liga y borrar. Solo el admin, y solo sobre
cuentas `.test`: ninguna de estas rutas toca la cuenta de una persona real (a lo demás, 404). Al crearlas se pueden
llenar con actividades inventadas (sin sueño, HRV, FC en reposo ni FC por segundo)."""
import hashlib
import random
import re
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from dashboard.fechas import lunes
from plan import simulador

from . import admin, ajustes_web, auth, cuenta, datos
from .deps import actual, formulario, get_db, settings as get_settings
from .modelos import Usuario

DOMINIO = "prueba.test"
RE_NOMBRE = re.compile(r"[a-z0-9][a-z0-9._-]{0,29}")

# historial que se puede elegir -> persona del simulador de la que salen sus semanas (None = cuenta vacía)
HISTORIALES = {"vacia": None, "empezando": "novata_trota_camina", "constante": "base_intermedia", "crossfit": "pedro_like"}
RITMO_TROTE = {"empezando": (8.0, 9.5), "constante": (6.2, 7.2), "crossfit": (5.8, 6.8)}   # min/km
RITMO_CAMINATA = (11.0, 13.0)
FC_PROM = {"running": (134, 150), "hiit": (128, 150)}
ZONAS_PESO = {"running": (0.12, 0.68, 0.20, 0.0, 0.0), "hiit": (0.15, 0.25, 0.30, 0.22, 0.05)}   # fracción del tiempo en Z1..Z5

router = APIRouter()


def inventar_historial(historial: str, hoy: date, semilla: str) -> tuple[list, dict]:
    """(actividades, detalles) con la forma del paquete del tubo: las últimas 8 semanas más la actual hasta ayer.
    Misma semilla, mismos datos. Vacío para «vacia»."""
    if HISTORIALES[historial] is None:
        return [], {}
    persona = simulador.persona_por_id(HISTORIALES[historial])
    semanas = [*persona["historial"], persona["historial"][-1]]   # la última se repite como semana en curso
    base = simulador.actividades_sinteticas({**persona, "historial": semanas}, (lunes(hoy) + timedelta(days=7)).isoformat())
    azar = random.Random(semilla)
    actividades, detalles = [], {}
    for i, a in enumerate(base):
        if a["startTimeLocal"][:10] >= hoy.isoformat():
            continue
        tipo = a["activityType"]["typeKey"]
        factor = azar.uniform(0.9, 1.1)
        duracion = int(a["duration"] * factor)
        fc = azar.randint(*FC_PROM[tipo])
        ident = hashlib.sha256(f"{semilla}:{i}".encode()).hexdigest()[:16]
        nueva = {"id": ident, "es_carrera": False, "startTimeLocal": a["startTimeLocal"], "activityType": {"typeKey": tipo},
                 "duration": duracion, "averageHR": fc, "maxHR": fc + azar.randint(14, 28)}
        nueva.update({f"hrTimeInZone_{z}": int(duracion * peso) for z, peso in enumerate(ZONAS_PESO[tipo], 1)})
        if tipo == "running":
            ritmo = azar.uniform(*RITMO_TROTE[historial])
            tramos = []
            for t in a.get("splitSummaries") or []:
                seg = int(t["duration"] * factor)
                corre = t["splitType"] == "RWD_RUN"
                paso = ritmo if corre else azar.uniform(*RITMO_CAMINATA)
                tramos.append({"tipo": t["splitType"], "seg": seg, "m": round(seg / 60 / paso * 1000),
                               "fc": fc + (4 if corre else -10), "n": t["noOfSplits"]})
            if tramos:
                detalles[ident] = {"splits": tramos}
            nueva["distance"] = sum(t["m"] for t in tramos) if tramos else round(duracion / 60 / ritmo * 1000)
        actividades.append(nueva)
    return actividades, detalles


def de_prueba(db: Session, ident, settings) -> Usuario:
    """La cuenta de prueba con ese id; 404 si no existe, no es `.test` o es de un admin."""
    ident = str(ident or "")
    u = db.get(Usuario, int(ident)) if re.fullmatch(r"[0-9]{1,9}", ident) else None
    if u is None or u.borrado is not None or not auth.es_correo_prueba(u.correo) or admin.es_admin(u, settings):
        raise HTTPException(404)
    return u


def _con_liga(request, db, quien_admin, u: Usuario, settings, **extra):
    # sin redirigir: el token en claro solo existe en esta respuesta
    token = auth.crear_liga(db, u, limitar=False)
    return admin.pagina(request, db, quien_admin, prueba_liga=f"{settings.base_url}/entrar/liga/{token}",
                        prueba_para=u.correo, **extra)


@router.post("/admin/prueba/crear")
async def crear(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    nombre = str(form.get("nombre", "")).strip().lower()
    if not RE_NOMBRE.fullmatch(nombre):
        return admin.pagina(request, db, quien, prueba_error=request.state.t("admin.prueba_nombre_malo"))
    correo = f"{nombre}@{DOMINIO}"
    if db.scalar(select(Usuario.id).where(Usuario.correo == correo)) is not None:
        return admin.pagina(request, db, quien, prueba_error=request.state.t("admin.prueba_ya_existe", correo=correo))
    historial = str(form.get("historial", "") or "vacia")
    if historial not in HISTORIALES:
        raise HTTPException(422)
    u = Usuario(correo=correo)
    db.add(u)
    db.flush()
    actividades, detalles = inventar_historial(historial, ajustes_web.hoy_de(request.app.state.reloj, {}), correo)
    if actividades:
        datos.guardar_paquete(db, u.id, {"archivos": {"activities": actividades, "activity_details": detalles}})
    db.commit()
    return _con_liga(request, db, quien, u, settings)


@router.post("/admin/prueba/liga")
async def liga(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    return _con_liga(request, db, quien, de_prueba(db, form.get("id"), settings), settings)


@router.post("/admin/prueba/borrar")
async def borrar(request: Request, usuario=Depends(actual), db: Session = Depends(get_db), settings=Depends(get_settings)):
    form = await formulario(request)
    quien = admin.admin_de(usuario, settings)
    u = de_prueba(db, form.get("id"), settings)
    correo = u.correo
    cuenta.borrar_cuenta(db, u)
    return admin.pagina(request, db, quien, mensaje=request.state.t("admin.prueba_borrada", correo=correo))
