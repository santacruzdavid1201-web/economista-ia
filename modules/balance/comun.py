"""Utilidades compartidas por los análisis del módulo de balance."""
from __future__ import annotations

from modules.base import division_segura
from modules.esquema_financiero import EstadoFinanciero, HistorialFinanciero

SUPUESTO_SIN_PROMEDIO = (
    "No hay periodo anterior: se usaron saldos de cierre en lugar de saldos "
    "promedio, lo que puede distorsionar las razones si la empresa creció o se "
    "contrajo durante el año."
)


def contexto_base(historial: HistorialFinanciero,
                  ef: EstadoFinanciero) -> tuple[list[str], list[str], list[str]]:
    """Fuentes, supuestos y advertencias comunes a cualquier análisis."""
    fuentes = [
        f"Estados financieros de {historial.empresa.razon_social} "
        f"con corte al {ef.fecha_corte:%d/%m/%Y}"
    ]
    supuestos = list(ef.supuestos_carga)
    advertencias = ef.advertencias()
    return fuentes, supuestos, advertencias


def factor_anual(ef: EstadoFinanciero) -> float:
    """Multiplicador para llevar los flujos del periodo a base anual."""
    return 12 / ef.meses


def promedios(historial: HistorialFinanciero, i: int,
              cuentas: list[str]) -> tuple[dict[str, float], bool]:
    """
    Saldos promedio de varias cuentas de balance para el periodo i.

    Devuelve el diccionario de promedios y True si todos son promedios reales
    (existe periodo anterior); False si se usaron saldos de cierre.
    """
    valores: dict[str, float] = {}
    todos_reales = True
    for cuenta in cuentas:
        valor, es_promedio = historial.saldo_promedio(cuenta, i)
        valores[cuenta] = valor
        todos_reales = todos_reales and es_promedio
    return valores, todos_reales


def tasa_implicita(historial: HistorialFinanciero, i: int) -> tuple[float | None, bool]:
    """
    Gastos financieros anuales / deuda financiera promedio, y True si el saldo es
    un promedio real. None sin deuda, o con deuda y sin gastos financieros: los
    intereses quedaron en otra cuenta y la tasa no se conoce.
    """
    ef = historial.periodos[i]
    deuda_prom, es_promedio = historial.saldo_promedio("deuda_financiera", i)
    if ef.balance.deuda_financiera <= 0 or ef.resultados.gastos_financieros == 0:
        return None, es_promedio
    gastos = ef.resultados.gastos_financieros * factor_anual(ef)
    return division_segura(gastos, deuda_prom), es_promedio
