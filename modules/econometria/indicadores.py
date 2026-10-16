"""
Indicadores hoteleros por día, semana o mes a partir de la serie diaria del PMS
(SPEC-series-empresa.md). Se calculan de las sumas, no promediando los indicadores
diarios: la ocupación de una semana con habitaciones en mantenimiento queda ponderada.

- Ocupación = Σ vendidas / Σ disponibles
- ADR = Σ ingresos / Σ vendidas
- RevPAR = Σ ingresos / Σ disponibles = ocupación × ADR
"""
from __future__ import annotations

import pandas as pd

# Las semanas van de lunes a domingo y se nombran por su lunes
PERIODOS = {"diaria": "D", "semanal": "W-SUN", "mensual": "M"}
SUMAS = ["habitaciones_disponibles", "habitaciones_vendidas", "ingresos_habitaciones"]


def agregar(serie: pd.DataFrame, frecuencia: str = "mensual") -> pd.DataFrame:
    """
    `serie`: la del almacén (índice de fechas). Una fila por periodo, nombrada por su
    primer día, con las sumas, la ocupación, el ADR, el RevPAR, cuántos días tienen dato
    y si el periodo está completo (un mes en curso o una semana con huecos no lo está).
    """
    if frecuencia not in PERIODOS:
        raise ValueError(f"Frecuencia «{frecuencia}»: use diaria, semanal o mensual.")
    periodos = serie.index.to_period(PERIODOS[frecuencia])
    grupos = serie[SUMAS].groupby(periodos)
    s = grupos.sum()
    s["dias"] = grupos.size()
    s["completo"] = s["dias"] == [(p.end_time.normalize() - p.start_time).days + 1 for p in s.index]
    vendidas = s["habitaciones_vendidas"].where(s["habitaciones_vendidas"] > 0)
    s["ocupacion"] = s["habitaciones_vendidas"] / s["habitaciones_disponibles"]
    s["adr"] = s["ingresos_habitaciones"] / vendidas            # sin ventas, sin ADR (NaN)
    s["revpar"] = s["ingresos_habitaciones"] / s["habitaciones_disponibles"]
    s.index = pd.DatetimeIndex([p.start_time for p in s.index], name="fecha")
    return s
