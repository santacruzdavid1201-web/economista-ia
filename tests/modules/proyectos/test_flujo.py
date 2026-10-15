"""Flujo de caja libre del proyecto: casos calculados a mano (SPEC-flujo-proyecto.md)."""
from datetime import date

import pytest

from modules.proyectos.flujo import senda_inflacion

OCTUBRE = date(2026, 10, 15)
JULIO_2026 = {2025: 0.051, 2026: 0.069, 2027: 0.043}      # informe de julio de 2026


# --------------------------------------------------------------------------- #
# Senda de inflación
# --------------------------------------------------------------------------- #
def test_senda_usa_el_pronostico_y_despues_la_meta():
    s = senda_inflacion(OCTUBRE, 4, JULIO_2026, 0.03)
    assert s.tasas == [0.043, 0.03, 0.03, 0.03]
    assert any("el año 1 es 2027" in x for x in s.supuestos)


def test_senda_no_usa_el_anio_en_curso():
    # En enero de 2027 el año 1 es 2028: el pronóstico de 2027 ya no aplica
    assert senda_inflacion(date(2027, 1, 20), 2, JULIO_2026, 0.03).tasas == [0.03, 0.03]


def test_senda_fija_del_usuario():
    s = senda_inflacion(OCTUBRE, 3, JULIO_2026, 0.03, fija=0.05)
    assert s.tasas == [0.05, 0.05, 0.05]
    assert s.supuestos == ["Se usó una inflación fija de 5,0 % al año, escrita por el usuario."]


def test_senda_sin_pronostico_usa_la_meta_con_supuesto():
    s = senda_inflacion(OCTUBRE, 2, None, 0.03)
    assert s.tasas == [0.03, 0.03]
    assert any("No hay pronóstico del BanRep cargado" in x for x in s.supuestos)
