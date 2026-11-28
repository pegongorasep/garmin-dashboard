"""Convierte data/ + plan + config en site/data.json (solo campos de una lista blanca).

Uso: python dashboard/build.py [--day YYYY-MM-DD] [--plan-start YYYY-MM-DD] [--out data.json]
Es el único lugar con reloj: "hoy" se calcula en la zona horaria del config.
"""
import argparse
import hashlib  # noqa: F401
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # se corre como archivo: la raíz del repo al path
from dashboard import i18n  # noqa: E402
from dashboard import metrics as m
from dashboard import plan_i18n  # noqa: F401
from dashboard import semanal
from dashboard import tipos
from dashboard.i18n import tt
from dashboard.ajustes import CLASES, USER_DIR, cargar_config  # noqa: F401
from dashboard.ayuda import armar_ayuda

ROOT = Path(__file__).parent.parent  # el motor (aquí vive site/)
DIAS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]   # español (referencia); lo que sale usa i18n.csv("motor.dias_cortos")
from dashboard.construir.cargar import (  # noqa: F401
    load,
    load_data,
    load_plan,
)
from dashboard.construir.comun import (  # noqa: F401
    r1,
    monday,
    light_on,
    week_runs,
    week_assignment,
    rw_json,
    r2,
    _total_semanas,
    ultima_semana,
    plan_terminado,
)
from dashboard.construir.sesiones import (  # noqa: F401
    lpm_range,
    convert_steps,
    rampas_de,
    rachas_de,
    ETIQUETA_CALIDAD,
    estructura_calidad,
    convert_session,
    convert_week,
    etiqueta_sesion,
)
from dashboard.construir.semanas import (  # noqa: F401
    MARCAS_SEMANA,
    marca_semana,
    marcas_semana,
    detalle_marcas,
    semanas_plan,
    signals_list,
    day_type,
    build_week,
    dia_de_semana,
    intensidad_semana,
    build_semana_libre,
    build_semana,
    resumen_semana_pasada,
    SEMANAS_ANTES_PLAN,
    build_semanas,
    build_weeks,
    entrenos_semana,
    DIAS_SIN_CORRER,
    retomar_sugerido,
)
from dashboard.construir.actividades import (  # noqa: F401
    last_run,
    registro_esfuerzo,
    datos_serie,
    corrida_json,
    corrida_plana,
    corrida_de_sesion,
    otras_del_dia,
    TE_ETIQUETAS,
    CURVA_PUNTOS,
    curva_fc,
    detalle_actividad,
    _trote_corto,
    actividades_del_dia,
    session_names,
    build_runs,
    historial_corridas,
    build_carreras,
)
from dashboard.construir.progreso import (  # noqa: F401
    base_prueba,
    prueba_resultado,
    _tiempo,
    texto_prueba,
    build_mejora,
    build_numeros,
    build_days,
    build_details,
)
from dashboard.construir.ui import (  # noqa: F401
    texto_inicio_plan,
    lista_es,
    categorias_presentes,
    build_ui,
    eventos_plan,
    huella,
    huellas_avisos,
    titular_hoy,
)


def build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    """data.json de una persona. Los textos que arma el motor salen en `config["idioma"]` (es si no lo trae)."""
    with i18n.usar(config.get("idioma")):
        return _build(data, plan, config, ahora)


def _build(data: dict, plan: dict, config: dict, ahora: datetime) -> dict:
    # La FC máx viene del reloj; config["max_hr"] es solo respaldo si Garmin no la da.
    reloj = m.watch_max_hr(data["hr_zones"])
    config = {**config, "max_hr": reloj or config["max_hr"]}
    # La FC en reposo solo cuenta si esa noche hubo sueño registrado (señal, promedio 7 días, zonas y gráfica).
    data = {**data, "daily_summaries": m.rhr_con_sueno(data["daily_summaries"], data["sleep"])}
    fc_max = m.max_hr_progress(data["activities"], config, data["details"])
    # Una sesión grabada en varias partes seguidas (fuerza + hiit) es UNA para todo lo que cuenta sesiones.
    data = {**data, "activities": m.unir_encadenadas(data["activities"], config)}
    hoy = ahora.date()
    ayer = hoy - timedelta(days=1)
    rhr = m.rhr_7d(data["daily_summaries"], hoy) or 60
    # Las zonas son las que Garmin dice (running, o DEFAULT); sin ellas, las calculadas con Karvonen como siempre.
    zonas_g = m.zonas_garmin(data["hr_zones"])
    zonas = zonas_g or m.zones(config["max_hr"], rhr, config["zone_pcts"])
    zonas_origen = "garmin" if zonas_g else "calculadas"
    zonas_plan = zonas_g or []
    # El aviso «configura tus zonas en Garmin» sale con zonas calculadas o con las de fábrica de Garmin.
    sugerir_zonas = (zonas_origen == "calculadas" or m.zonas_de_fabrica(data["hr_zones"])) and config.get("garmin_conectado", True)
    config = {**config, "zonas": zonas}   # derivadas de este día: esfuerzo, ritmo a FC ref y plan vs real las leen de aquí

    sigs = m.signals(hoy, data, config)
    prev = light_on(ayer, data, config)["color"]
    luz = m.traffic_light(sigs, prev)

    repetidas = config.get("semanas_repetidas", [])
    semana_plan, estado = week_assignment(hoy, data, config, plan)
    n = semana_plan["n"] if semana_plan else None

    tarjeta = m.today_card(hoy, luz, estado, data["activities"], config)
    if tarjeta["sesion_id"] and semana_plan:
        ses = next(s for s in semana_plan["sessions"] if s["id"] == tarjeta["sesion_id"])
        tarjeta["sesion"] = convert_session(ses, zonas_plan)
    sin_datos = not any(data[k] for k in ("activities", "daily_summaries", "sleep", "hrv"))
    inicio_plan = date.fromisoformat(config["plan_start"])
    if sin_datos and (config.get("garmin_ultima_subida") and config.get("garmin_historial_pendiente")):
        texto = tt("motor.build.primera")
        if hoy < inicio_plan:
            texto += f". {texto_inicio_plan(inicio_plan)}"
        tarjeta = {**tarjeta, "tipo": "primera_sync", "texto": texto, "version": None, "sesion_id": None}
    elif tarjeta["tipo"] == "sin_plan" and hoy < inicio_plan:
        tarjeta = {**tarjeta, "texto": texto_inicio_plan(inicio_plan)}
    elif plan_terminado(hoy, config, plan):   # pasó la última semana: resultado de la prueba y a pedir el siguiente bloque
        tarjeta = {**tarjeta, "tipo": "plan_terminado", "texto": tt("motor.build.plan_terminado"), "version": None, "sesion_id": None,
                   "prueba": prueba_resultado(data, config, plan),
                   "siguiente": tt("motor.build.siguiente_bloque"), "siguiente_url": "/plan/acciones#siguiente"}
    elif m.en_pausa(hoy, config):   # semana de viaje sin correr o de enfermedad: el plan espera
        tarjeta = {**tarjeta, "tipo": "pausa", "texto": tt("motor.build.pausa"),
                   "version": None, "sesion_id": None}
    ayer_dato = m.ayer_duro(hoy, data["activities"], data["details"], config)
    tarjeta["repetir"] = bool(luz.get("repetir_semana"))
    tarjeta["motivo"] = m.motivo(sigs, config, ayer_dato) if tarjeta["version"] in ("suave", "descanso") else None
    tarjeta["opciones"] = m.opciones_hoy(tarjeta["version"], tarjeta.get("sesion"))
    tarjeta["recomendada"] = tarjeta["version"] if tarjeta["opciones"] else None
    manana_id = tarjeta.get("proxima_id") or ((m._elegir_pendiente(hoy + timedelta(days=1), estado)[0] or {}).get("id")
                                              if estado and tarjeta["version"] == "descanso" else None)

    pulled = data["meta"].get("pulled_at_utc")
    datos_al = None
    if pulled:
        datos_al = datetime.fromisoformat(pulled).astimezone(ahora.tzinfo).isoformat(timespec="minutes")
    if "garmin_ultima_subida" in config:   # la web la pone siempre (None sin repo); el build local usa el pull de Garmin
        ultima = config.get("garmin_ultima_subida")
        datos_al = ultima.replace(tzinfo=ZoneInfo("UTC")).astimezone(ahora.tzinfo).isoformat(timespec="minutes") if ultima else None
    filas = m.run_rows(data["activities"], data["details"], config)
    semanas_hoy, semana_hoy_idx = build_semanas(hoy, data, config, plan)
    semanas_12 = build_weeks(hoy, data, config, plan)
    periodos_p = semanal.periodos_progreso(hoy, plan, config)
    claves_p = sorted({4, 8, 12} | {p["n"] for p in periodos_p})   # los fijos de siempre y el largo del plan
    mejora = build_mejora(hoy, filas, zonas, data, config, plan)
    racha_json = semanal.racha_semanas(semanas_hoy, semana_hoy_idx, hoy, data, config, libre=bool(config.get("sin_plan")))
    sem_pasada = resumen_semana_pasada(hoy, data, config, plan, semanas_hoy)
    retomar = retomar_sugerido(hoy, data, config, plan, semanas_hoy, n, m.en_pausa(hoy, config))
    # Sin Garmin conectado no hay reloj donde configurar la FC máx: el aviso no aplica.
    aviso_fc = m.max_hr_above_watch(fc_max["estimacion"], reloj, fc_max.get("pulso_pico") or "banda", fc_max.get("pico")) \
        if config.get("garmin_conectado", True) else None
    return {
        "generado": ahora.isoformat(timespec="minutes"),
        "datos_al": datos_al,
        "zonas": [{"zona": z, "piso": lo, "techo": hi} for z, lo, hi in zonas],
        "rhr_promedio_7d": r1(rhr),
        "aviso_zonas": aviso_fc,
        "hoy": {"semaforo": luz, "señales": signals_list(sigs), "ayer": ayer_dato, "tarjeta": tarjeta,
                "titular": titular_hoy(tarjeta, (semana_plan or {}).get("sessions"), manana_id),
                "semana_pasada": sem_pasada, "retomar": retomar},
        "ultima_corrida": last_run(data, config, plan),
        "semana": build_week(hoy, data, config, estado, plan),
        "semanas_hoy": semanas_hoy, "semana_hoy_idx": semana_hoy_idx,
        **({"semana_libre": build_semana_libre(hoy, data, config)} if config.get("sin_plan") else {}),
        "racha": racha_json,
        "plan": {"inicio": plan["start"], "semana_actual": n, "semanas_repetidas": repetidas,
                 "nivel": (plan.get("meta") or {}).get("nivel"), "largo": len(plan["weeks"]),
                 "bloques": sorted({w["block"] for w in plan["weeks"] if w.get("block") is not None}),
                 **({"faltan": m.faltan_texto(estado)} if m.faltan_texto(estado) else {}),
                 **eventos_plan(config),
                 "semanas": semanas_plan(plan, zonas_plan, hoy, semanas_hoy, config, semanal.ritmo_facil(filas, hoy)),
                 "estado_sesiones": [{**e, "minutos": r1(e["minutos"]),
                                         "corrida": corrida_de_sesion(e, semana_plan, data, config)} for e in estado]},
        "carreras": build_carreras(hoy, data, config),
        "mejores_marcas": m.mejores_marcas(historial_corridas(data, config), hoy, config),
        "progreso": {"fc_ref": m.fc_referencia(zonas),
                     "periodos": periodos_p,
                     "resumen": {str(k): m.progress_summary(filas, hoy, k, m.fc_referencia(zonas)) for k in (4, 8, 12)},
                     "corridas": build_runs(data, config, plan),
                     "semanas": semanas_12,
                     "mejora": mejora,
                     "intensidad_semanas": [{"inicio": i.isoformat(), "actual": i == monday(hoy), **intensidad_semana(data["activities"], i)}
                                            for i in semanal.serie_semanas(hoy, plan, config)],
                     "numeros": build_numeros(hoy, filas, mejora["modo"], claves_p),
                     "dias": build_days(hoy, data)},
        "composicion": m.composicion(data.get("inbody") if config.get("inbody", True) else None),
        "ui": {**build_ui(config, plan, categorias_presentes(config, data)), "zonas_origen": zonas_origen, "avisos": huellas_avisos(
            tarjeta, aviso_fc,
            fc_max, luz, n, (sem_pasada or {}).get("sugerencia"), (sem_pasada or {}).get("inicio"), sugerir_zonas, retomar)},
        "idioma": i18n.actual(),   # el sitio pinta en el mismo idioma que los textos del motor
        "ayuda": armar_ayuda(config, plan, zonas, m.fc_referencia(zonas)),
        "tipos": tipos.catalogo_json({tipos.forma_de(x) for w in plan["weeks"] for x in w["sessions"]}),
        "detalles": build_details(hoy, data, config, fc_max, reloj, plan),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="fecha local YYYY-MM-DD (para pruebas)")
    ap.add_argument("--out", help="archivo de salida (por defecto <motor>/site/data.json)")
    ap.add_argument("--plan-start", help="inicio del plan YYYY-MM-DD (solo pruebas visuales)")
    args = ap.parse_args()
    config = cargar_config()
    tz = ZoneInfo(config["timezone"])
    ahora = datetime.now(tz)
    if args.day:
        ahora = datetime.combine(date.fromisoformat(args.day), ahora.time(), tzinfo=tz)
    plan = load_plan()
    if args.plan_start:
        config = {**config, "plan_start": args.plan_start}
        plan = {**plan, "start": args.plan_start}
    out = build(load_data(), plan, config, ahora)
    destino = Path(args.out) if args.out else ROOT / "site" / "data.json"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    i18n.escribir_json(destino.parent / "i18n")   # los textos del sitio (es.json, en.json) junto al data.json
    print(f"OK: {destino} ({destino.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
