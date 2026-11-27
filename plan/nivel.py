"""Nivel de la persona calculado desde sus actividades de Garmin (Motor v6, F2).

`nivel_desde_datos(actividades, hoy) -> {nivel, evidencia, inicio_minutos}`. Funciones puras: no leen archivos ni red.
Reglas de docs/INVESTIGACION_PLANES.md §3.1 (la «Base corta» se junta con «Base») y §1.11 (desentrenamiento).
Todos los umbrales están en `UMBRALES`: ahí se afinan.

Ventanas: se cuentan hacia atrás desde `hoy` (semana 1 = los 7 días anteriores a `hoy`, semana 2 = los 7 previos...).
"""
import statistics
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

RAIZ = Path(__file__).parent.parent
if str(RAIZ / "dashboard") not in sys.path:
    sys.path.insert(0, str(RAIZ / "dashboard"))
import metrics  # noqa: E402

NIVELES = ("empezando", "base", "corredor")

UMBRALES = {
    # Ventanas (en semanas, hacia atrás desde hoy)
    "semanas_frecuencia": 6,        # F: corridas por semana, promedio de estas semanas
    "semanas_volumen": 4,           # V: minutos por semana, promedio de estas semanas (con las semanas en 0)
    "semanas_activas": 8,           # S: semanas con al menos una corrida entre estas
    "dias_continuo": 56,            # C: trote continuo más largo en estos días
    "dias_sesion_max": 30,          # sesión más larga en estos días (tope de la larga)
    "semanas_intensos": 4,          # días intensos (no corrida) por semana, promedio de estas semanas
    "semanas_dias_intensos": 8,     # días de la semana «habituales» de entrenamiento intenso: se miran estas semanas
    # Empezando: se cumple cualquiera
    "empezando_continuo_min": 10,   # C < 10'
    "empezando_corridas_sem": 1,    # F < 1
    # Corredor: se cumplen todas (si no, Base)
    "corredor_continuo_min": 50,
    "corredor_corridas_sem": 3,
    "corredor_min_sem": 150,        # V > 150
    "corredor_semanas_activas": 7,
    # Una semana «consistente» (para las semanas seguidas que piden la calidad y la regla de desbloqueo de F3)
    "consistente_corridas": 2,
    "consistente_min": 30,
    # Desentrenamiento (días desde la última corrida)
    "pausa_leve_dias": 14,          # más de esto: el arranque se recorta
    "pausa_leve_factor": 0.8,
    "pausa_baja_nivel_dias": 28,    # más de esto: se baja un nivel (§1.11: «reclasificar»)
    # Minutos de la semana 1
    "inicio_pct": 0.10,             # ≤ 110 % del promedio real de las últimas `semanas_volumen` semanas
    "inicio_sin_historial_min": 60, # sin corridas recientes: arranque de la escalera de trote/caminata (3 × 20')
    "inicio_redondeo": 5,           # se redondea hacia abajo a múltiplos de 5' (si pasa de 10')
}


def _fecha(a: dict) -> datetime:
    return datetime.fromisoformat(a["startTimeLocal"])


def _hoy(hoy) -> datetime:
    return datetime(hoy.year, hoy.month, hoy.day) if isinstance(hoy, date) and not isinstance(hoy, datetime) else hoy


def _semana(a: dict, hoy: datetime) -> int | None:
    """1 = los 7 días anteriores a `hoy`; None si es futura."""
    dias = (hoy - _fecha(a)).total_seconds() / 86400
    return None if dias < 0 else int(dias // 7) + 1


def _config(config: dict | None) -> dict:
    if config:
        return config
    from ajustes import categorias_por_defecto
    return {"run_types": ["running", "treadmill_running", "trail_running", "track_running"],
            "categorias": categorias_por_defecto()}


def trote_continuo_min(a: dict, detalles: dict | None = None) -> float:
    """Trote seguido de una corrida, en minutos: el tramo típico de trote si hay trote/caminata; si no, toda la corrida."""
    rw = metrics.run_walk(a, detalles or {})
    if rw is None:
        return (a.get("duration") or 0) / 60
    return rw["patron_trote_min"] or 0.0


def _bajar(nivel: str) -> str:
    return NIVELES[max(0, NIVELES.index(nivel) - 1)]


def nivel_desde_datos(actividades: list, hoy, config: dict | None = None, detalles: dict | None = None) -> dict:
    """Nivel (`empezando` | `base` | `corredor`), evidencia y minutos recomendados de la semana 1."""
    u = UMBRALES
    cfg, hoy = _config(config), _hoy(hoy)
    todas = [a for a in actividades if _fecha(a) <= hoy]
    corridas = [a for a in todas if metrics.classify(a, cfg) == "run"]
    ids_intensas = {c["id"] for c in metrics.categorias_intensas(cfg)}
    intensas = [a for a in metrics.unir_encadenadas(todas, cfg) if metrics.classify(a, cfg) in ids_intensas]

    def en_semanas(lista, n):
        return [a for a in lista if (s := _semana(a, hoy)) is not None and s <= n]

    def min_sem(n):   # minutos por semana de corrida (promedio de las n últimas, con ceros)
        return sum((a.get("duration") or 0) / 60 for a in en_semanas(corridas, n)) / n

    por_semana = {}   # semana -> (n corridas, minutos)
    for a in corridas:
        s = _semana(a, hoy)
        n, m = por_semana.get(s, (0, 0.0))
        por_semana[s] = (n + 1, m + (a.get("duration") or 0) / 60)
    minutos_4 = [por_semana.get(s, (0, 0.0))[1] for s in range(1, u["semanas_volumen"] + 1)]
    consistentes = 0
    for s in range(1, u["semanas_activas"] + 1):
        n, m = por_semana.get(s, (0, 0.0))
        if n >= u["consistente_corridas"] and m >= u["consistente_min"]:
            consistentes += 1
        else:
            break

    recientes_c = [a for a in corridas if 0 <= (hoy - _fecha(a)).days < u["dias_continuo"]]
    recientes_s = [a for a in corridas if 0 <= (hoy - _fecha(a)).days < u["dias_sesion_max"]]
    ultima = max((_fecha(a) for a in corridas), default=None)
    dias_pausa = (hoy - ultima).days if ultima else None
    sem_int = u["semanas_dias_intensos"]
    hab = [0] * 7
    for a in en_semanas(intensas, sem_int):
        hab[_fecha(a).weekday()] += 1
    ev = {
        "corridas_sem_4": round(len(en_semanas(corridas, 4)) / 4, 2),
        "corridas_sem_8": round(len(en_semanas(corridas, 8)) / 8, 2),
        "minutos_sem_prom": round(sum(minutos_4) / len(minutos_4), 1),
        "minutos_sem_mediana": round(statistics.median(minutos_4), 1),
        "trote_continuo_min": round(max((trote_continuo_min(a, detalles) for a in recientes_c), default=0.0), 1),
        "semanas_activas": len({_semana(a, hoy) for a in en_semanas(corridas, u["semanas_activas"])}),
        "semanas_consistentes": consistentes,
        "dias_desde_ultima": dias_pausa,
        "intensos_sem": round(len(en_semanas(intensas, u["semanas_intensos"])) / u["semanas_intensos"], 2),
        "dias_intensos": [d for d in range(7) if hab[d] >= sem_int / 2],   # lunes = 0
        "sesion_max_30d": round(max(((a.get("duration") or 0) / 60 for a in recientes_s), default=0.0), 1),
    }
    f = len(en_semanas(corridas, u["semanas_frecuencia"])) / u["semanas_frecuencia"]
    v, c, s_act = min_sem(u["semanas_volumen"]), ev["trote_continuo_min"], ev["semanas_activas"]

    if s_act == 0 or c < u["empezando_continuo_min"] or f < u["empezando_corridas_sem"]:
        nivel = "empezando"
    elif (c >= u["corredor_continuo_min"] and f >= u["corredor_corridas_sem"] and v > u["corredor_min_sem"]
          and s_act >= u["corredor_semanas_activas"]):
        nivel = "corredor"
    else:
        nivel = "base"
    ev["nivel_sin_pausa"] = nivel
    pausa = None
    if dias_pausa is not None and dias_pausa > u["pausa_baja_nivel_dias"]:
        nivel, pausa = _bajar(nivel), "baja_nivel"
    elif dias_pausa is not None and dias_pausa > u["pausa_leve_dias"]:
        pausa = "leve"
    ev["desentrenamiento"] = pausa

    prom = ev["minutos_sem_prom"]
    if prom <= 0:
        inicio = u["inicio_sin_historial_min"]
    else:
        inicio = prom * (1 + u["inicio_pct"]) * (u["pausa_leve_factor"] if pausa else 1.0)
        inicio = int(inicio // u["inicio_redondeo"] * u["inicio_redondeo"]) if inicio > 10 else int(inicio)
    return {"nivel": nivel, "evidencia": ev, "inicio_minutos": inicio}
