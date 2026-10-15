"""
Flujo de caja libre del proyecto, año por año.

Decisiones (SPEC-flujo-proyecto.md, aprobadas el 15/10/2026):
- Sin la financiación: intereses y cuotas entran en la tasa de descuento.
- Precios de hoy por fuera, inflación por dentro: el flujo se arma en pesos
  corrientes (así se pagan los impuestos) y se devuelve en pesos de hoy. La
  inflación le quita valor real al ahorro de impuestos de la depreciación, y el
  capital de trabajo crece con los precios aunque las ventas reales no crezcan.
- Inflación: el pronóstico del último Informe de Política Monetaria del BanRep
  y la meta después de su horizonte, o una tasa fija que escriba el usuario.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple

from modules.base import formatear


class Senda(NamedTuple):
    tasas: list[float]           # inflación de los años 1 a n del proyecto (fracción)
    supuestos: list[str]


def _pct(valor: float) -> str:
    return formatear(valor, "proporcion")          # "4,3 %": como la publica el BanRep


def senda_inflacion(hoy: date, horizonte: int, pronostico: dict[int, float] | None,
                    meta: float, fija: float | None = None) -> Senda:
    """
    Inflación de cada año del proyecto. El año t se asocia al año calendario
    actual + t (supuesto): el pronóstico del año en curso no se usa.
    """
    if fija is not None:
        return Senda([fija] * horizonte,
                     [f"Se usó una inflación fija de {_pct(fija)} al año, escrita por el usuario."])
    anios = [hoy.year + t for t in range(1, horizonte + 1)]
    supuestos = [f"Cada año del proyecto se asocia a un año calendario: el año 1 es {anios[0]}."]
    if pronostico is None:
        supuestos.append(f"No hay pronóstico del BanRep cargado: se usó la meta de inflación de "
                         f"{_pct(meta)} para todos los años.")
        return Senda([meta] * horizonte, supuestos)
    return Senda([pronostico.get(a, meta) for a in anios], supuestos)
