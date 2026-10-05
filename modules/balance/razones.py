"""
Razones financieras: liquidez, endeudamiento, rentabilidad y actividad.

- Liquidez y endeudamiento comparan saldo con saldo o flujo con flujo del
  mismo periodo: no necesitan saldos promedio.
- Rentabilidad y actividad mezclan un flujo del periodo (ventas, utilidad,
  costo) con un saldo (activos, patrimonio, cartera): usan el saldo promedio
  entre el cierre anterior y el actual, y anualizan los flujos si el periodo
  tiene menos de 12 meses.

El módulo no juzga si un valor es "bueno" o "malo" con umbrales genéricos:
eso lo hará la comparación sectorial. Solo advierte hechos objetivos.
"""
from __future__ import annotations

from modules.balance.comun import (
    SUPUESTO_SIN_PROMEDIO,
    contexto_base,
    factor_anual,
    promedios,
)
from modules.base import Indicador, ResultadoModulo, division_segura
from modules.esquema_financiero import HistorialFinanciero

DIAS_ANIO = 365
SIN_DEPRECIACION = (
    "No se reportó la depreciación y amortización: el EBITDA y las razones que "
    "lo usan no se pueden calcular."
)


def liquidez(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    ef = historial.periodos[i]
    b = ef.balance
    ac, pc = b.activo_corriente, b.pasivo_corriente
    fuentes, supuestos, advertencias = contexto_base(historial, ef)

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
    fuentes, supuestos, advertencias = contexto_base(historial, ef)

    patrimonio = b.patrimonio_total
    apalancamiento = division_segura(b.pasivo_total, patrimonio) if patrimonio > 0 else None

    # EBITDA anualizado si el periodo tiene menos de 12 meses (deuda es un saldo).
    ebitda_anual = None if r.ebitda is None else r.ebitda * factor_anual(ef)
    deuda_ebitda = (division_segura(b.deuda_financiera, ebitda_anual)
                    if ebitda_anual is not None and ebitda_anual > 0 else None)

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
    if ebitda_anual is None:
        advertencias.append(SIN_DEPRECIACION)
    elif ebitda_anual <= 0:
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


def rentabilidad(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    r = ef.resultados
    fuentes, supuestos, advertencias = contexto_base(historial, ef)

    ventas = r.ingresos_operacionales
    utilidad_neta_anual = r.utilidad_neta * factor_anual(ef)
    prom, son_promedios = promedios(historial, i, ["activo_total", "patrimonio_total"])
    patrimonio_prom = prom["patrimonio_total"]

    indicadores = [
        Indicador(clave="margen_bruto", nombre="Margen bruto",
                  valor=division_segura(r.utilidad_bruta, ventas), unidad="proporcion",
                  formula="Utilidad bruta / Ingresos operacionales"),
        Indicador(clave="margen_operacional", nombre="Margen operacional",
                  valor=division_segura(r.utilidad_operacional, ventas), unidad="proporcion",
                  formula="Utilidad operacional / Ingresos operacionales"),
        Indicador(clave="margen_ebitda", nombre="Margen EBITDA",
                  valor=None if r.ebitda is None else division_segura(r.ebitda, ventas),
                  unidad="proporcion",
                  formula="EBITDA / Ingresos operacionales"),
        Indicador(clave="margen_neto", nombre="Margen neto",
                  valor=division_segura(r.utilidad_neta, ventas), unidad="proporcion",
                  formula="Utilidad neta / Ingresos operacionales"),
        Indicador(clave="roa", nombre="Rentabilidad del activo (ROA)",
                  valor=division_segura(utilidad_neta_anual, prom["activo_total"]),
                  unidad="proporcion",
                  formula="Utilidad neta anual / Activo total promedio"),
        Indicador(clave="roe", nombre="Rentabilidad del patrimonio (ROE)",
                  valor=division_segura(utilidad_neta_anual, patrimonio_prom)
                  if patrimonio_prom > 0 else None,
                  unidad="proporcion",
                  formula="Utilidad neta anual / Patrimonio promedio"),
    ]

    if not son_promedios:
        supuestos.append(SUPUESTO_SIN_PROMEDIO)
    if ef.meses < 12:
        supuestos.append(f"ROA y ROE anualizados a partir de {ef.meses} meses.")
    if ventas == 0:
        advertencias.append("Sin ingresos operacionales: los márgenes no se pueden calcular.")
    if patrimonio_prom <= 0:
        advertencias.append("Patrimonio promedio nulo o negativo: el ROE no tiene interpretación.")
    if r.ebitda is None:
        advertencias.append(SIN_DEPRECIACION)
    if r.utilidad_neta < 0:
        advertencias.append("La empresa tuvo pérdida neta en el periodo.")

    return ResultadoModulo(modulo="balance", analisis="rentabilidad",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           supuestos=supuestos, fuentes=fuentes, advertencias=advertencias)


def actividad(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    r = ef.resultados
    fuentes, supuestos, advertencias = contexto_base(historial, ef)

    f = factor_anual(ef)
    ventas_anual = r.ingresos_operacionales * f
    costo_anual = r.costo_ventas * f
    prom, son_promedios = promedios(
        historial, i, ["activo_total", "deudores_comerciales", "inventarios", "proveedores"]
    )

    # Compras = costo de ventas + inventario final − inventario inicial.
    # Sin periodo anterior se aproximan con el costo de ventas.
    if i > 0:
        inv_inicial = historial.periodos[i - 1].balance.inventarios
        compras_anual = (r.costo_ventas + ef.balance.inventarios - inv_inicial) * f
    else:
        compras_anual = costo_anual
        supuestos.append("Sin periodo anterior: las compras se aproximan con el costo de ventas.")

    def dias(saldo: float, flujo: float) -> float | None:
        cociente = division_segura(saldo, flujo)
        return None if cociente is None else cociente * DIAS_ANIO

    dias_cartera = dias(prom["deudores_comerciales"], ventas_anual)
    dias_inventario = dias(prom["inventarios"], costo_anual)
    dias_proveedores = dias(prom["proveedores"], compras_anual) if compras_anual > 0 else None
    componentes = (dias_cartera, dias_inventario, dias_proveedores)
    ciclo = (None if any(c is None for c in componentes)
             else dias_cartera + dias_inventario - dias_proveedores)

    indicadores = [
        Indicador(clave="rotacion_activos", nombre="Rotación de activos",
                  valor=division_segura(ventas_anual, prom["activo_total"]), unidad="veces",
                  formula="Ingresos operacionales anuales / Activo total promedio"),
        Indicador(clave="dias_cartera", nombre="Días de cartera",
                  valor=dias_cartera, unidad="dias",
                  formula="Deudores comerciales promedio / Ingresos anuales × 365"),
        Indicador(clave="dias_inventario", nombre="Días de inventario",
                  valor=dias_inventario, unidad="dias",
                  formula="Inventarios promedio / Costo de ventas anual × 365"),
        Indicador(clave="dias_proveedores", nombre="Días de proveedores",
                  valor=dias_proveedores, unidad="dias",
                  formula="Proveedores promedio / Compras anuales × 365"),
        Indicador(clave="ciclo_conversion_efectivo", nombre="Ciclo de conversión de efectivo",
                  valor=ciclo, unidad="dias",
                  formula="Días de cartera + Días de inventario − Días de proveedores"),
    ]

    supuestos.append(
        "Días de cartera calculados sobre ventas totales: si parte de las ventas es "
        "de contado, los días reales de cobro son mayores."
    )
    supuestos.append("Año comercial de 365 días.")
    if not son_promedios:
        supuestos.append(SUPUESTO_SIN_PROMEDIO)
    if ef.meses < 12:
        supuestos.append(f"Flujos anualizados a partir de {ef.meses} meses.")
    if r.costo_ventas == 0:
        advertencias.append(
            "Sin costo de ventas: los días de inventario y de proveedores no se pueden calcular."
        )
    elif compras_anual <= 0:
        advertencias.append("Compras estimadas nulas o negativas: los días de proveedores no aplican.")

    return ResultadoModulo(modulo="balance", analisis="actividad",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           supuestos=supuestos, fuentes=fuentes, advertencias=advertencias)
