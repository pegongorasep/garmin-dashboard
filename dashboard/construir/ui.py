"""Textos y categorías de la interfaz, eventos del plan, huellas/avisos y titular de hoy."""
import hashlib
from dashboard import i18n, plan_i18n
from dashboard.metricas import comun
from dashboard.ajustes import CLASES
from dashboard.i18n import tt
from datetime import date
from dashboard.construir.sesiones import etiqueta_sesion


def texto_inicio_plan(inicio: date) -> str:
    return tt("motor.inicio_plan", dia=i18n.csv("motor.dias_cortos")[inicio.weekday()], n=inicio.day,
              mes=i18n.csv("motor.meses_cortos")[inicio.month - 1])


lista_es = i18n.lista   # "a, b y c" / "a, b and c" según el idioma en curso


def categorias_presentes(config: dict, data: dict) -> list:
    """Categorías que de verdad aparecen en las actividades de la persona (leyendas y listas no muestran el resto),
    con el color según cuántas son."""
    vistas = {comun.classify(a, config) for a in data.get("activities") or []}
    cats = [c for c in config["categorias"] if c["id"] in vistas]
    clases = CLASES[min(len(cats), 4)] if cats else []
    return [{**c, "clase": clases[i % len(clases)]} for i, c in enumerate(cats)]


def build_ui(config: dict, plan: dict, cats: list | None = None) -> dict:
    """Todo lo que el sitio necesita de la config: título, categorías y textos ya armados."""
    cats = config["categorias"] if cats is None else cats
    nombre = comun.nombre_intensa(config)
    sesiones = [(tt("motor.nombre.calidad") if s.get("tipo") == "calidad" else plan_i18n.nombre(s["name"])) for s in plan["weeks"][0]["sessions"]] if plan.get("weeks") else []
    partes = []
    if sesiones:
        lista = (tt("motor.ui.cada_semana_y", ini=", ".join(sesiones[:-1]), ult=sesiones[-1]) if len(sesiones) > 1 else sesiones[0])
        partes.append(tt("motor.ui.cada_semana", lista=lista))
    if config["dias_pierna"]:
        partes.append(tt("motor.ui.pierna", dias=lista_es([i18n.csv("motor.dias_largos")[d] for d in config["dias_pierna"]])))
    acciones = config.get("acciones_url")   # la liga la pone quien llama
    return {
        "titulo": i18n.tt("sitio.titulo_defecto") if config["titulo"] == "Mi entreno" else config["titulo"],   # el título de fábrica, traducido
        "categorias": [{k: c[k] for k in ("id", "nombre", "letra", "clase", "icono")} for c in cats],
        "nombre_intensa": nombre,
        "acciones_url": acciones,
        "sin_plan": bool(config.get("sin_plan", False)),
        "sync": {"puede": False, "url_autorizar": None, "historial_pendiente": False, "key_rechazada": False, "migrar": False, "repo": None},   # solo en la web (la pone web/sync_web.sync_ui): botón «Sincronizar»; sin ella el sitio pinta lo de siempre
        "plan_acciones": list(config.get("plan_acciones") or []),   # solo en la web: [{texto, url}] sobre el plan
        "repetir_url": "/plan/repetir" if config.get("plan_url") else None,   # solo en la web: POST del botón «Repetir esta semana» de Hoy
        "propuesta_url": None, "plan_nuevo_url": None, "retomar_url": None, "retomar_opciones": [],   # solo en la web (calculo.calcular, fuera de la caché y solo si puede editar): vista previa y POST de «Repetir o retomar», y las semanas 1..N-1 con sus fechas [{semana, desde, hasta}]
        "plan_url": config.get("plan_url") or None,   # solo en la web: url del plan (botón «Ajustar mi plan»; null = sin botón
        "cuerpo_nuevo": config.get("cuerpo_nuevo") or None,   # solo en la web: url de «Agregar medición»; null = sin botón
        "coach": None,   # solo en la web: {nombre, volver} cuando un coach ve a su atleta (la web lo pone al servir; nunca en la caché)
        "grupos": int(config.get("grupos") or 0),   # solo en la web: en cuántos grupos está la persona (la pestaña Grupos la pone ui.vacios.grupos, que agrega la web)
        "editar_manual": {},   # solo en la web: {"m<id>": ruta} para editar cada actividad a mano (la pone calculo.calcular, fuera de la caché; solo si puede editar)
        "editar_urls": {str(k): str(v) for k, v in (config.get("editar_urls") or {}).items()},   # solo en la web: {"<n>/<id>": url} de las sesiones editables
        "menu": [{"texto": i["texto"], "url": i["url"]} for i in config.get("menu") or []],   # solo en la web: [{texto, url relativa}]
        "textos": {
            "semana": ". ".join(partes) + ".",
            "descarga": tt("motor.ui.descarga" if config["caminatas"] else "motor.ui.descarga_cont"),
            "incluye": tt("motor.ui.incluye", lista=lista_es([c["nombre"] for c in cats] + [tt("motor.ui.corridas")])),
            "fcmax_vacia": (tt("motor.ui.fcmax_vacia_n", nombre=nombre) if nombre else tt("motor.ui.fcmax_vacia"))
            if config["fc_max_correa_desde"] else
            tt("motor.ui.fcmax_sin_fecha", donde=tt("motor.ui.donde_web")),
        },
    }


def eventos_plan(config: dict) -> dict:
    """`plan.eventos` (viajes, enfermedades, carreras con fecha) para el calendario del Plan. Sin eventos ni metas la
    clave no existe (así el data.json de quien no los usa queda idéntico)."""
    out = [{"tipo": e["tipo"], "desde": e["desde"], "hasta": e["hasta"], "correr": e["correr"], "modo": e["modo"]}
           for e in config.get("eventos") or []]
    out += [{"tipo": "carrera", "desde": x["fecha"], "hasta": x["fecha"], "nombre": x["nombre"],
             "distancia_km": x["distancia_km"]} for x in config.get("metas") or []]
    return {"eventos": sorted(out, key=lambda e: e["desde"])} if out else {}


def huella(contenido) -> str:
    """Huella corta y estable de lo que dice un aviso: quien lo dio por entendido lo ve de nuevo solo si ella cambia."""
    return hashlib.sha1(str(contenido).encode("utf-8")).hexdigest()[:10]


def huellas_avisos(tarjeta: dict, aviso_zonas, fc_max: dict, semaforo: dict, semana_n, sugerencia=None, semana_inicio=None, sugerir_zonas=False,
                   retomar=None) -> dict:
    """{id: huella} de los avisos que hoy están activos (los que el sitio puede cerrar con «Entendido»). Sin aviso, sin clave."""
    out = {}
    if tarjeta.get("aviso"):
        out["hoy"] = huella(tarjeta["aviso"])
    if aviso_zonas:
        out["zonas"] = huella(aviso_zonas)
    if sugerir_zonas:   # «configura tus zonas en Garmin»: texto fijo, así que «Entendido» lo cierra para siempre
        out["zonas_garmin"] = huella("zonas_garmin")
    if fc_max.get("revisar"):
        out["fcmax"] = huella(round(fc_max["estimacion"]))
    if semaforo.get("repetir_semana"):
        out["repetir"] = huella(semana_n)
    if retomar:   # la última corrida cambia la huella: otra racha sin correr vuelve a avisar
        out["retomar"] = huella(f"retomar|{retomar.get('ultima')}")
    if sugerencia and sugerencia.get("tipo") != "sigue":   # «sigue así» no es aviso: no se cierra
        out["sugerencia"] = huella(f"{sugerencia['tipo']}|{semana_inicio}")   # tipo + semana, no el texto: en la web y en el sitio el texto cambia de forma
    return out


def titular_hoy(tarjeta: dict, sesiones: list, manana_id: str | None = None) -> str | None:
    """Línea 2 de Hoy: la sesión completa (nombre, zona, minutos) y, si ya está planeada, la de mañana.
    `sesiones` = sesiones del plan de esta semana. None = el sitio la deja vacía (plan terminado)."""
    tipo = tarjeta.get("tipo")
    por_id = {s["id"]: s for s in sesiones or []}
    sig = por_id.get(manana_id)
    manana = lambda base: f"{base} · " + tt("motor.titular.manana", sesion=etiqueta_sesion(sig)) if sig else base   # noqa: E731
    if tipo == "sesion":
        if tarjeta.get("version") == "descanso":
            return manana(tt("motor.titular.descanso"))
        ses = por_id.get(tarjeta.get("sesion_id"))
        return tt("motor.titular.toca", sesion=etiqueta_sesion(ses, tarjeta.get("version") == "suave")) if ses else None
    if tipo == "hecha_hoy":
        return manana(tt("motor.titular.hecha"))
    if tipo == "otra":
        return manana(tt("motor.titular.otra", cat=tarjeta.get("categoria")))
    if tipo == "completa":
        return tt("motor.titular.completa")
    if tipo in ("sin_plan", "primera_sync", "pausa"):
        return tarjeta.get("texto")
    return None
