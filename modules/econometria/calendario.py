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

import pandas as pd
import yaml
from dateutil.easter import easter

from data_sources.externos.series.catalogo import sin_tildes

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


def _puente(d: date, fes: dict[date, str]) -> bool:
    """Sábado, domingo o lunes de un fin de semana con lunes festivo, o viernes, sábado o
    domingo de uno con viernes festivo."""
    dia = d.weekday()
    if dia in (5, 6, 0) and _lunes(d) in fes:                  # el lunes de ese fin de semana
        return True
    return dia in (4, 5, 6) and d - timedelta(days=dia - 4) in fes   # su viernes


def _eventos(ciudad: str | None) -> list[dict]:
    if not ciudad:
        return []
    eventos = _config().get("eventos", {})
    return next((lista for nombre, lista in eventos.items()
                 if sin_tildes(nombre) == sin_tildes(ciudad)), [])


def calendario(desde: date, hasta: date, ciudad: str | None = None) -> pd.DataFrame:
    """
    Un día por fila (índice: fecha) con el día de la semana (0 lunes), si es festivo y
    cuál, si es víspera de festivo, si es puente, si es Semana Santa y, si la ciudad los
    tiene, sus eventos (`evento_<clave>`). Sin ciudad o sin eventos, sin esas columnas.
    """
    if hasta < desde:
        raise ErrorCalendario(f"El rango está invertido: {desde:%d/%m/%Y} es después de "
                              f"{hasta:%d/%m/%Y}.")
    _validar(desde.year)
    _validar(hasta.year)
    # Los años vecinos, para las vísperas y los puentes de los bordes del rango
    fes: dict[date, str] = {}
    for anio in range(max(desde.year - 1, PRIMER_ANIO), min(hasta.year + 1, ULTIMO_ANIO) + 1):
        fes.update(festivos(anio))
    dias = [desde + timedelta(days=k) for k in range((hasta - desde).days + 1)]
    pascuas = {a: easter(a) for a in range(desde.year, hasta.year + 1)}
    c = pd.DataFrame({
        "dia_semana": [d.weekday() for d in dias],
        "festivo": [d in fes for d in dias],
        "nombre_festivo": [fes.get(d) for d in dias],
        "vispera_festivo": [d + timedelta(days=1) in fes for d in dias],
        "puente": [_puente(d, fes) for d in dias],
        # Del Domingo de Ramos al Domingo de Resurrección
        "semana_santa": [pascuas[d.year] - timedelta(days=7) <= d <= pascuas[d.year]
                         for d in dias],
    }, index=pd.DatetimeIndex(dias, name="fecha"))
    for e in _eventos(ciudad):
        inicio, fin = (tuple(map(int, e[k].split("-"))) for k in ("desde", "hasta"))
        c[f"evento_{e['clave']}"] = [inicio <= (d.month, d.day) <= fin for d in dias]
    return c
