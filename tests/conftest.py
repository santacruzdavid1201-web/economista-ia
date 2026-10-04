"""Datos de prueba compartidos por todos los tests."""
from datetime import date

import pytest

from modules.esquema_financiero import (
    BalanceGeneral,
    Empresa,
    EstadoFinanciero,
    EstadoResultados,
    HistorialFinanciero,
)


def hacer_historial(balance: dict | None = None, resultados: dict | None = None,
                    meses: int = 12) -> HistorialFinanciero:
    """Empresa de referencia; los argumentos reemplazan cuentas puntuales."""
    b = dict(efectivo=300, deudores_comerciales=200, inventarios=50, ppe=1_500,
             obligaciones_financieras_cp=150, proveedores=120,
             obligaciones_financieras_lp=600,
             capital=1_000, resultados_acumulados=40, resultado_ejercicio=140)
    r = dict(ingresos_operacionales=1_000, costo_ventas=400, gastos_administracion=250,
             gastos_ventas=100, gastos_financieros=50, impuesto_renta=60,
             depreciacion_amortizacion=80)
    b.update(balance or {})
    r.update(resultados or {})
    ef = EstadoFinanciero(fecha_corte=date(2024, 12, 31), meses=meses,
                          balance=BalanceGeneral(**b), resultados=EstadoResultados(**r))
    empresa = Empresa(empresa_id="demo-001", razon_social="Hotel Demo S.A.S.", ciiu="5511")
    return HistorialFinanciero(empresa=empresa, periodos=[ef])


@pytest.fixture
def historial():
    return hacer_historial()


def periodo_2023() -> EstadoFinanciero:
    """
    Cierre anterior de la empresa de referencia.
    Activo 1.840 (corriente 390) | Pasivo 880 (corriente 230) | Patrimonio 960
    Ingresos 800 | Utilidad neta 60
    """
    return EstadoFinanciero(
        fecha_corte=date(2023, 12, 31),
        balance=BalanceGeneral(
            efectivo=200, deudores_comerciales=160, inventarios=30, ppe=1_450,
            obligaciones_financieras_cp=130, proveedores=100,
            obligaciones_financieras_lp=650,
            capital=1_000, resultados_acumulados=-100, resultado_ejercicio=60),
        resultados=EstadoResultados(
            ingresos_operacionales=800, costo_ventas=340, gastos_administracion=230,
            gastos_ventas=90, gastos_financieros=60, impuesto_renta=20,
            depreciacion_amortizacion=70),
    )


@pytest.fixture
def historial_dos_periodos():
    h = hacer_historial()
    return HistorialFinanciero(empresa=h.empresa, periodos=[periodo_2023(), h.ultimo])
