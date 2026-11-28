"""Plan v6 para las pruebas que antes usaban el generador viejo: `generar(cfg)` arma un plan del motor v6 con lo que dice la config
(nivel viejo -> nivel v6, semanas e inicio). Reexporta las piezas de `pasos`."""
from pathlib import Path

ROOT = Path(__file__).parent.parent
from plan import motor_v6
from plan.pasos import redondea5, suave, suma, zonas_de   # noqa: F401

NIVEL_V6 = {"novato": "empezando", "intermedio": "base", "corredor": "corredor"}
EVIDENCIA = {"empezando": {"semanas_consistentes": 0, "trote_continuo_min": 0, "minutos_sem_prom": 0, "sesion_max_30d": 0},
             "base": {"semanas_consistentes": 8, "trote_continuo_min": 35, "minutos_sem_prom": 95, "sesion_max_30d": 35},
             "corredor": {"semanas_consistentes": 12, "trote_continuo_min": 60, "minutos_sem_prom": 170, "sesion_max_30d": 60}}
INICIO_MIN = {"empezando": 60, "base": 100, "corredor": 170}
verificar = motor_v6.verificar


def generar(cfg: dict, dias: int = 3, **extra) -> dict:
    nivel = NIVEL_V6.get(cfg.get("nivel"), "base")
    return motor_v6.generar_v6({"nivel": nivel, "dias": dias, "inicio": cfg["plan_start"], "semanas": cfg["plan_semanas"],
                                "evidencia": dict(EVIDENCIA[nivel]), "inicio_minutos": INICIO_MIN[nivel], "edad": 35,
                                "objetivo": "velocidad" if cfg.get("intensidad") == "calidad" and nivel != "empezando" else None, **extra})
