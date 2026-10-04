"""Utilidades compartidas por los análisis del módulo de balance."""
from __future__ import annotations

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
