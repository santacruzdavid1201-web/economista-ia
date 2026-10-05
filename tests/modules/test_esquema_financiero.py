from datetime import date

import pytest
from pydantic import ValidationError

from modules.esquema_financiero import (
    BalanceGeneral,
    Empresa,
    EstadoFinanciero,
    EstadoResultados,
    HistorialFinanciero,
)

EMPRESA = Empresa(empresa_id="demo-001", razon_social="Hotel Demo S.A.S.",
                  ciiu="5511", departamento="Nariño", municipio="Pasto")


def resultados(utilidad_extra: float = 0) -> EstadoResultados:
    # Utilidad neta = 1.000 − 400 − 250 − 100 − 50 − 60 + utilidad_extra = 140
    return EstadoResultados(
        ingresos_operacionales=1_000 + utilidad_extra, costo_ventas=400,
        gastos_administracion=250, gastos_ventas=100, otros_ingresos=0,
        otros_gastos=0, ingresos_financieros=0, gastos_financieros=50,
        impuesto_renta=60, depreciacion_amortizacion=80,
    )


def balance(efectivo: float = 300) -> BalanceGeneral:
    # Activo = efectivo + 200 + 50 + 1.500 ; Pasivo = 150 + 120 + 600 ; Patrimonio = resto
    return BalanceGeneral(
        efectivo=efectivo, deudores_comerciales=200, inventarios=50, ppe=1_500,
        obligaciones_financieras_cp=150, proveedores=120,
        obligaciones_financieras_lp=600,
        capital=1_000, resultados_acumulados=efectivo - 260, resultado_ejercicio=140,
    )


def test_totales_calculados():
    b = balance()
    assert b.activo_corriente == 550
    assert b.activo_total == 2_050
    assert b.pasivo_total == 870
    assert b.deuda_financiera == 750
    assert b.patrimonio_total == 1_180


def test_utilidades_en_cascada():
    r = resultados()
    assert r.utilidad_bruta == 600
    assert r.utilidad_operacional == 250
    assert r.ebitda == 330
    assert r.utilidad_neta == 140


def test_balance_que_no_cuadra_se_rechaza():
    b = balance()
    b_malo = b.model_copy(update={"capital": 900})
    with pytest.raises(ValidationError, match="no cuadra"):
        EstadoFinanciero(fecha_corte=date(2024, 12, 31), balance=b_malo,
                         resultados=resultados())


def test_advierte_utilidad_no_conciliada():
    ef = EstadoFinanciero(fecha_corte=date(2024, 12, 31), balance=balance(),
                          resultados=resultados(utilidad_extra=100))
    assert any("no coincide" in a for a in ef.advertencias())


def test_advierte_cuentas_no_reportadas():
    ef = EstadoFinanciero(fecha_corte=date(2024, 12, 31), balance=balance(),
                          resultados=resultados())
    avisos = " ".join(ef.advertencias())
    assert "intangibles" in avisos
    assert "efectivo" not in avisos


def test_historial_ordena_y_promedia():
    p2024 = EstadoFinanciero(fecha_corte=date(2024, 12, 31), balance=balance(400),
                             resultados=resultados())
    p2023 = EstadoFinanciero(fecha_corte=date(2023, 12, 31), balance=balance(200),
                             resultados=resultados())
    h = HistorialFinanciero(empresa=EMPRESA, periodos=[p2024, p2023])
    assert h.ultimo.fecha_corte.year == 2024
    assert h.saldo_promedio("efectivo") == (300, True)
    assert h.saldo_promedio("activo_total") == ((2_150 + 1_950) / 2, True)
    assert h.saldo_promedio("efectivo", 0) == (200, False)


def test_sin_depreciacion_no_hay_ebitda():
    r = resultados().model_copy(update={"depreciacion_amortizacion": None})
    assert r.ebitda is None
    assert r.utilidad_operacional == 250


def test_impuesto_negativo_es_beneficio():
    r = resultados().model_copy(update={"impuesto_renta": -20})
    # Utilidad antes de impuestos 200; con beneficio de 20 la neta es 220
    assert r.utilidad_antes_impuestos == 200
    assert r.utilidad_neta == 220
