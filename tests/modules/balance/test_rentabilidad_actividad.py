"""
Con dos periodos (2023 → 2024) los saldos promedio son:
Activo 1.945 | Patrimonio 1.070 | Deudores 180 | Inventarios 40 | Proveedores 110
2024: Ingresos 1.000 | Costo de ventas 400 | Utilidad neta 140
Compras 2024 = 400 + 50 − 30 = 420
"""
import pytest

from modules.balance.comun import SUPUESTO_SIN_PROMEDIO
from modules.balance.razones import actividad, rentabilidad
from tests.conftest import hacer_historial


# ----------------------------- Rentabilidad ------------------------------- #
def test_margenes(historial):
    res = rentabilidad(historial)
    assert res.valor("margen_bruto") == pytest.approx(0.60)
    assert res.valor("margen_operacional") == pytest.approx(0.25)
    assert res.valor("margen_ebitda") == pytest.approx(0.33)
    assert res.valor("margen_neto") == pytest.approx(0.14)


def test_ebitda_en_pesos(historial):
    # Utilidad operacional 250 + depreciación 80; el margen solo no responde "¿cuál es mi EBITDA?"
    res = rentabilidad(historial)
    assert res.valor("ebitda") == pytest.approx(330)
    # El hallazgo separa el monto del margen, que es lo que se compara con el sector
    assert "$ 330" in res.hallazgos[-1] and "no se compara con el sector" in res.hallazgos[-1]
    sin_dep = rentabilidad(hacer_historial(resultados={"depreciacion_amortizacion": None}))
    assert sin_dep.valor("ebitda") is None
    assert not any("EBITDA" in h for h in sin_dep.hallazgos)


def test_hallazgo_lo_que_queda_es_el_margen_neto(historial):
    assert "es el margen neto: 14,0 %" in rentabilidad(historial).hallazgos[0]
    sin_ventas = rentabilidad(hacer_historial(resultados={"ingresos_operacionales": 0}))
    assert not any("margen neto" in h for h in sin_ventas.hallazgos)


def test_roa_roe_con_promedios(historial_dos_periodos):
    res = rentabilidad(historial_dos_periodos)
    assert res.valor("roa") == pytest.approx(140 / 1_945)
    assert res.valor("roe") == pytest.approx(140 / 1_070)
    assert SUPUESTO_SIN_PROMEDIO not in res.supuestos


def test_roa_sin_periodo_anterior_usa_cierre(historial):
    res = rentabilidad(historial)
    assert res.valor("roa") == pytest.approx(140 / 2_050)
    assert SUPUESTO_SIN_PROMEDIO in res.supuestos


def test_rentabilidad_anualiza_semestre():
    res = rentabilidad(hacer_historial(meses=6))
    assert res.valor("roa") == pytest.approx(280 / 2_050)
    assert res.valor("margen_neto") == pytest.approx(0.14)  # los márgenes no cambian


# ------------------------------ Actividad --------------------------------- #
def test_actividad_con_promedios(historial_dos_periodos):
    res = actividad(historial_dos_periodos)
    assert res.valor("rotacion_activos") == pytest.approx(1_000 / 1_945)
    assert res.valor("dias_cartera") == pytest.approx(180 / 1_000 * 365)
    assert res.valor("dias_inventario") == pytest.approx(40 / 400 * 365)
    assert res.valor("dias_proveedores") == pytest.approx(110 / 420 * 365)
    ciclo = 65.7 + 36.5 - 110 / 420 * 365
    assert res.valor("ciclo_conversion_efectivo") == pytest.approx(ciclo)


def test_actividad_sin_periodo_anterior_aproxima_compras(historial):
    res = actividad(historial)
    assert res.valor("dias_proveedores") == pytest.approx(120 / 400 * 365)
    assert any("compras se aproximan" in s for s in res.supuestos)


def test_actividad_sin_costo_de_ventas():
    h = hacer_historial(resultados={"costo_ventas": 0},
                        balance={"resultado_ejercicio": 540, "resultados_acumulados": -360})
    res = actividad(h)
    assert res.valor("dias_inventario") is None
    assert res.valor("ciclo_conversion_efectivo") is None
    assert any("Sin costo de ventas" in a for a in res.advertencias)
