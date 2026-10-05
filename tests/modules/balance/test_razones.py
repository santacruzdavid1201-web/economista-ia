"""
Empresa de referencia (ver tests/conftest.py):
Activo corriente 550 | Inventarios 50 | Efectivo 300 | Pasivo corriente 270
Pasivo total 870 | Activo total 2.050 | Patrimonio 1.180 | Deuda financiera 750
Ingresos 1.000 | Utilidad operacional 250 | EBITDA 330 | Gastos financieros 50
"""
import pytest

from modules.balance.razones import endeudamiento, liquidez
from tests.conftest import hacer_historial


# ------------------------------ Liquidez ---------------------------------- #
def test_liquidez_valores(historial):
    res = liquidez(historial)
    assert res.valor("razon_corriente") == pytest.approx(550 / 270)
    assert res.valor("prueba_acida") == pytest.approx(500 / 270)
    assert res.valor("razon_efectivo") == pytest.approx(300 / 270)
    assert res.valor("capital_trabajo") == 280
    assert res.modulo == "balance" and res.analisis == "liquidez"
    assert "Hotel Demo" in res.fuentes[0]


def test_liquidez_advierte_pasivo_corriente_mayor(historial):
    # +400 en proveedores, compensado con −400 en resultados acumulados
    h = hacer_historial(balance={"proveedores": 520, "resultados_acumulados": -360})
    res = liquidez(h)
    assert res.valor("razon_corriente") < 1
    assert any("supera al activo corriente" in a for a in res.advertencias)


def test_liquidez_sin_pasivo_corriente_devuelve_none():
    h = hacer_historial(balance={"obligaciones_financieras_cp": 0, "proveedores": 0,
                                 "resultados_acumulados": 310})
    res = liquidez(h)
    assert res.valor("razon_corriente") is None
    assert any("No hay pasivo corriente" in a for a in res.advertencias)


# ---------------------------- Endeudamiento ------------------------------- #
def test_endeudamiento_valores(historial):
    res = endeudamiento(historial)
    assert res.valor("nivel_endeudamiento") == pytest.approx(870 / 2_050)
    assert res.valor("concentracion_cp") == pytest.approx(270 / 870)
    assert res.valor("apalancamiento") == pytest.approx(870 / 1_180)
    assert res.valor("deuda_ebitda") == pytest.approx(750 / 330)
    assert res.valor("cobertura_intereses") == pytest.approx(5)
    assert res.valor("carga_financiera") == pytest.approx(0.05)


def test_endeudamiento_anualiza_ebitda_en_periodo_corto():
    res = endeudamiento(hacer_historial(meses=6))
    assert res.valor("deuda_ebitda") == pytest.approx(750 / (330 * 2))
    assert any("anualizado" in s for s in res.supuestos)


def test_endeudamiento_patrimonio_negativo():
    # +1.400 en deuda LP, patrimonio pasa a −220
    h = hacer_historial(balance={"obligaciones_financieras_lp": 2_000,
                                 "resultados_acumulados": -1_360})
    res = endeudamiento(h)
    assert res.valor("apalancamiento") is None
    assert any("Patrimonio nulo o negativo" in a for a in res.advertencias)


def test_endeudamiento_sin_gastos_financieros():
    h = hacer_historial(resultados={"gastos_financieros": 0},
                        balance={"resultado_ejercicio": 190, "resultados_acumulados": -10})
    res = endeudamiento(h)
    assert res.valor("cobertura_intereses") is None
    assert any("no aplica" in a for a in res.advertencias)


def test_endeudamiento_cobertura_insuficiente():
    h = hacer_historial(resultados={"gastos_financieros": 300},
                        balance={"resultado_ejercicio": -110, "resultados_acumulados": 290})
    res = endeudamiento(h)
    assert res.valor("cobertura_intereses") == pytest.approx(250 / 300)
    assert any("no alcanza para cubrir" in a for a in res.advertencias)


def test_supuestos_del_cargador_pasan_al_resultado(historial):
    historial.ultimo.supuestos_carga.append("Cuenta 21 asumida como corto plazo.")
    res = endeudamiento(historial)
    assert "Cuenta 21 asumida como corto plazo." in res.supuestos


def test_sin_depreciacion_no_calcula_ebitda():
    h = hacer_historial(resultados={"depreciacion_amortizacion": None})
    res = endeudamiento(h)
    assert res.valor("deuda_ebitda") is None
    assert any("depreciación" in a for a in res.advertencias)
    assert res.valor("cobertura_intereses") == pytest.approx(5)
