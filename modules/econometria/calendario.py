"""
Calendario que mueve la demanda hotelera (SPEC-calendario.md): festivos de Colombia
(Ley Emiliani y las que la modifican), vísperas, puentes, Semana Santa y eventos
locales por ciudad, como el Carnaval de Negros y Blancos en Pasto. Las reglas y los
eventos están en config/calendario.yaml, cada regla con su vigencia.

La noche es la del día: el PMS cuenta cada noche vendida en la fecha en que empieza,
y por eso importa la víspera de un festivo (el domingo antes de un lunes festivo se
llena como un sábado).
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import cache
from pathlib import Path

import yaml
from dateutil.easter import easter

CONFIG = Path(__file__).resolve().parents[2] / "config" / "calendario.yaml"
PRIMER_ANIO, ULTIMO_ANIO = 1984, 2100            # la Ley Emiliani rige desde 1984


class ErrorCalendario(ValueError):
    """Fechas fuera de lo que el calendario sabe calcular; el mensaje dice por qué."""


@cache
def _config() -> dict:
    # ponytail: se lee una vez por proceso; si se edita el YAML, reiniciar la interfaz
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def _validar(anio: int) -> None:
    if not PRIMER_ANIO <= anio <= ULTIMO_ANIO:
        raise ErrorCalendario(f"El calendario cubre de {PRIMER_ANIO} (desde cuando rige la Ley "
                              f"Emiliani) a {ULTIMO_ANIO}; se pidió {anio}.")


def _mes_dia(texto: str, anio: int) -> date:
    mes, dia = map(int, texto.split("-"))
    return date(anio, mes, dia)


def _lunes(d: date) -> date:
    """El mismo día si es lunes; si no, el lunes siguiente."""
    return d + timedelta(days=(7 - d.weekday()) % 7)


def _rige(regla: dict, anio: int) -> bool:
    return regla.get("desde", PRIMER_ANIO) <= anio <= regla.get("hasta", ULTIMO_ANIO)


def festivos(anio: int) -> dict[date, str]:
    """
    Festivos del año, de la fecha al nombre y en orden. Si dos caen el mismo día
    (el 30/6/2025, San Pedro y San Pablo y el Sagrado Corazón), es un solo día con
    los dos nombres.
    """
    _validar(anio)
    reglas, pascua, dias = _config()["festivos"], easter(anio), {}

    def agregar(d: date, nombre: str) -> None:
        dias[d] = f"{dias[d]}; {nombre}" if d in dias else nombre

    for r in (r for r in reglas["fijos"] if _rige(r, anio)):
        agregar(_mes_dia(r["fecha"], anio), r["nombre"])
    for r in (r for r in reglas["trasladables"] if _rige(r, anio)):
        agregar(_lunes(_mes_dia(r["fecha"], anio)), r["nombre"])
    for r in (r for r in reglas["pascua"] if _rige(r, anio)):
        d = pascua + timedelta(days=r["dias"])
        agregar(_lunes(d) if r.get("trasladable") else d, r["nombre"])
    return dict(sorted(dias.items()))
