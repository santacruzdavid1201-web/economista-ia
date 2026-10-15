"""Flujo de caja libre del proyecto: casos calculados a mano (SPEC-flujo-proyecto.md)."""
from datetime import date

import pytest

from modules.proyectos.flujo import (
    ErrorProyecto,
    Senda,
    crear_proyecto,
    flujo_caja,
    senda_inflacion,
)

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


# --------------------------------------------------------------------------- #
# Proyecto y flujo de caja libre
# --------------------------------------------------------------------------- #
EJEMPLO = dict(nombre="Remodelación", inversion=100_000_000, vida_util=5, horizonte=5,
               ingresos=60_000_000, crecimiento_real=0, costos_variables=0.30,
               costos_fijos=10_000_000, capital_trabajo=0.10, tarifa_renta=0.35)


def flujo_con(pi: float, **cambios):
    p = crear_proyecto(**{**EJEMPLO, **cambios})
    return flujo_caja(p, Senda([pi] * p.horizonte, []))


def libres(f) -> list[float]:
    return [fila.flujo_libre for fila in f.real]


def test_caso_a_mano_sin_inflacion():
    f = flujo_con(0)
    assert libres(f) == pytest.approx([-106_000_000, 27_800_000, 27_800_000, 27_800_000,
                                       27_800_000, 33_800_000])
    uno = f.real[1]
    assert (uno.utilidad_operativa, uno.impuesto, uno.depreciacion) == pytest.approx(
        (12_000_000, 4_200_000, 20_000_000))
    assert libres(f) == pytest.approx([fila.flujo_libre for fila in f.corriente])


def test_caso_a_mano_con_inflacion_de_3_por_ciento():
    assert libres(flujo_con(0.03)) == pytest.approx(
        [-106_180_000, 27_416_117, 27_218_171, 27_025_992, 26_839_409, 32_838_261], abs=1)


def test_la_inflacion_baja_el_flujo_en_pesos_de_hoy():
    sin, con = libres(flujo_con(0)), libres(flujo_con(0.05))
    assert all(c < s for c, s in zip(con[1:], sin[1:]))


def test_la_inflacion_le_quita_valor_al_ahorro_de_impuestos_de_la_depreciacion():
    f = flujo_con(0.03)
    assert any("ahorro de impuestos de la depreciación" in h for h in f.resultado.hallazgos)
    assert not any("depreciación" in h for h in flujo_con(0).resultado.hallazgos)


def test_vida_util_mayor_que_el_horizonte_pasa_el_valor_en_libros_al_salvamento():
    f = flujo_con(0, vida_util=10)
    assert f.real[-1].salvamento == pytest.approx(50_000_000)
    assert any("en libros" in s for s in f.resultado.supuestos)


def test_salvamento_de_mercado_paga_la_tarifa_sobre_la_ganancia():
    f = flujo_con(0, vida_util=10, salvamento=60_000_000)
    assert f.real[-1].salvamento == pytest.approx(60_000_000 - 0.35 * 10_000_000)
    assert any("ganancia ocasional" in s for s in f.resultado.supuestos)


def test_un_anio_con_perdida_da_impuesto_negativo():
    f = flujo_con(0, ingresos=20_000_000)
    assert f.real[1].utilidad_operativa < 0 and f.real[1].impuesto < 0
    assert any("pérdida" in s for s in f.resultado.supuestos)


def test_el_crecimiento_real_sube_los_ingresos_en_pesos_de_hoy():
    f = flujo_con(0.03, crecimiento_real=0.10)
    assert [fila.ingresos for fila in f.real[1:3]] == pytest.approx([60_000_000, 66_000_000])


@pytest.mark.parametrize("cambio, mensaje", [
    ({"horizonte": 0}, "El horizonte debe estar entre 1 y 30 años."),
    ({"horizonte": 31}, "El horizonte debe estar entre 1 y 30 años."),
    ({"inversion": 0}, "La inversión debe ser mayor que cero."),
    ({"costos_variables": 1.2}, "Los costos variables deben estar entre 0 % y 100 % de los ingresos."),
])
def test_validacion_con_mensajes_utiles(cambio, mensaje):
    with pytest.raises(ErrorProyecto) as e:
        crear_proyecto(**{**EJEMPLO, **cambio})
    assert mensaje in e.value.mensajes
