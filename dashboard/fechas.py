"""Utilerías de fechas compartidas por el motor, el plan y la web."""
from datetime import date, timedelta


def lunes(d: date) -> date:
    """El lunes de la semana de `d`."""
    return d - timedelta(days=d.weekday())
