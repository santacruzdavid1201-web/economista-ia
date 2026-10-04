"""
Razones financieras: liquidez y endeudamiento.

Todas las razones de este archivo comparan saldo con saldo o flujo con flujo
del mismo periodo, así que no necesitan saldos promedio. Las de rentabilidad y
actividad (siguiente paso) sí los necesitan.

El módulo no juzga si un valor es "bueno" o "malo" con umbrales genéricos:
eso lo hará la comparación sectorial. Solo advierte hechos objetivos
(p. ej. el pasivo corriente supera al activo corriente).
"""
from __future__ import annotations

from modules.base import Indicador, ResultadoModulo, division_segura
from modules.esquema_financiero import EstadoFinanciero, HistorialFinanciero


def _base(historial: HistorialFinanciero, ef: EstadoFinanciero) -> tuple[list[str], list[str], list[str]]:
    """Fuentes, supuestos y advertencias comunes a cualquier análisis."""
    fuentes = [
        f"Estados financieros de {historial.empresa.razon_social} "
        f"con corte al {ef.fecha_corte:%d/%m/%Y}"
    ]
    supuestos = list(ef.supuestos_carga)
    advertencias = ef.advertencias()
    return fuentes, supuestos, advertencias


def liquidez(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    ef = historial.periodos[i]
    b = ef.balance
    ac, pc = b.activo_corriente, b.pasivo_corriente
    fuentes, supuestos, advertencias = _base(historial, ef)

    indicadores = [
        Indicador(clave="razon_corriente", nombre="Razón corriente",
                  valor=division_segura(ac, pc), unidad="veces",
                  formula="Activo corriente / Pasivo corriente"),
        Indicador(clave="prueba_acida", nombre="Prueba ácida",
                  valor=division_segura(ac - b.inventarios, pc), unidad="veces",
                  formula="(Activo corriente − Inventarios) / Pasivo corriente"),
        Indicador(clave="razon_efectivo", nombre="Razón de efectivo",
                  valor=division_segura(b.efectivo + b.inversiones_cp, pc), unidad="veces",
                  formula="(Efectivo + Inversiones CP) / Pasivo corriente"),
        Indicador(clave="capital_trabajo", nombre="Capital de trabajo neto",
                  valor=ac - pc, unidad="pesos",
                  formula="Activo corriente − Pasivo corriente"),
    ]

    supuestos.append("Saldos al cierre del periodo: no reflejan la liquidez dentro del año.")
    if pc == 0:
        advertencias.append("No hay pasivo corriente: las razones de liquidez no se pueden calcular.")
    elif ac < pc:
        advertencias.append(
            "El pasivo corriente supera al activo corriente: los activos de corto "
            "plazo no alcanzan para cubrir las deudas de corto plazo."
        )

    return ResultadoModulo(modulo="balance", analisis="liquidez",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           supuestos=supuestos, fuentes=fuentes, advertencias=advertencias)


def endeudamiento(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    ef = historial.periodos[i]
    b, r = ef.balance, ef.resultados
    fuentes, supuestos, advertencias = _base(historial, ef)

    patrimonio = b.patrimonio_total
    apalancamiento = division_segura(b.pasivo_total, patrimonio) if patrimonio > 0 else None

    # EBITDA anualizado si el periodo tiene menos de 12 meses (deuda es un saldo).
    ebitda_anual = r.ebitda * 12 / ef.meses
    deuda_ebitda = division_segura(b.deuda_financiera, ebitda_anual) if ebitda_anual > 0 else None

    cobertura = division_segura(r.utilidad_operacional, r.gastos_financieros)

    indicadores = [
        Indicador(clave="nivel_endeudamiento", nombre="Nivel de endeudamiento",
                  valor=division_segura(b.pasivo_total, b.activo_total), unidad="proporcion",
                  formula="Pasivo total / Activo total"),
        Indicador(clave="concentracion_cp", nombre="Concentración del pasivo en el corto plazo",
                  valor=division_segura(b.pasivo_corriente, b.pasivo_total), unidad="proporcion",
                  formula="Pasivo corriente / Pasivo total"),
        Indicador(clave="apalancamiento", nombre="Apalancamiento",
                  valor=apalancamiento, unidad="veces",
                  formula="Pasivo total / Patrimonio"),
        Indicador(clave="deuda_ebitda", nombre="Deuda financiera / EBITDA",
                  valor=deuda_ebitda, unidad="veces",
                  formula="(Obligaciones financieras CP + LP) / EBITDA anual"),
        Indicador(clave="cobertura_intereses", nombre="Cobertura de intereses",
                  valor=cobertura, unidad="veces",
                  formula="Utilidad operacional / Gastos financieros"),
        Indicador(clave="carga_financiera", nombre="Carga financiera",
                  valor=division_segura(r.gastos_financieros, r.ingresos_operacionales),
                  unidad="proporcion",
                  formula="Gastos financieros / Ingresos operacionales"),
    ]

    if ef.meses < 12:
        supuestos.append(f"EBITDA anualizado a partir de {ef.meses} meses (× 12 / {ef.meses}).")
    if patrimonio <= 0:
        advertencias.append("Patrimonio nulo o negativo: el apalancamiento no tiene interpretación.")
    if ebitda_anual <= 0:
        advertencias.append("EBITDA nulo o negativo: la operación no genera caja para pagar deuda.")
    if r.gastos_financieros == 0:
        advertencias.append("Sin gastos financieros en el periodo: la cobertura de intereses no aplica.")
    elif cobertura is not None and cobertura < 1:
        advertencias.append(
            "La utilidad operacional no alcanza para cubrir los gastos financieros."
        )

    return ResultadoModulo(modulo="balance", analisis="endeudamiento",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           supuestos=supuestos, fuentes=fuentes, advertencias=advertencias)
