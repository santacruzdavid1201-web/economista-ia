"""
Análisis DuPont: descompone el ROE en tres palancas.

    ROE = Margen neto × Rotación de activos × Multiplicador del capital
        = (UN / Ventas) × (Ventas / Activo prom.) × (Activo prom. / Patrimonio prom.)

Responde POR QUÉ una empresa es rentable: porque vende con buen margen, porque
vende mucho con pocos activos, o porque está apalancada (la palanca más riesgosa).

Con dos o más periodos también descompone el cambio del ROE entre periodos
(ver `variacion`), usando logaritmos: ln ROE = ln m + ln r + ln a, de modo que
la variación se reparte de forma exacta y sin depender del orden de los factores.
"""
from __future__ import annotations

import math

from modules.balance.comun import (
    SUPUESTO_SIN_PROMEDIO,
    contexto_base,
    factor_anual,
    promedios,
)
from modules.base import Indicador, ResultadoModulo, division_segura, formatear
from modules.esquema_financiero import HistorialFinanciero

PALANCAS = ("margen_neto", "rotacion_activos", "multiplicador_capital")


def _componentes(historial: HistorialFinanciero, i: int) -> tuple[dict[str, float | None], bool]:
    ef = historial.periodos[i]
    r = ef.resultados
    f = factor_anual(ef)
    prom, son_promedios = promedios(historial, i, ["activo_total", "patrimonio_total"])
    patrimonio = prom["patrimonio_total"]

    margen = division_segura(r.utilidad_neta, r.ingresos_operacionales)
    rotacion = division_segura(r.ingresos_operacionales * f, prom["activo_total"])
    multiplicador = (division_segura(prom["activo_total"], patrimonio)
                     if patrimonio > 0 else None)
    partes = (margen, rotacion, multiplicador)
    roe = None if any(p is None for p in partes) else margen * rotacion * multiplicador
    return {"margen_neto": margen, "rotacion_activos": rotacion,
            "multiplicador_capital": multiplicador, "roe": roe}, son_promedios


def dupont(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    fuentes, supuestos, advertencias = contexto_base(historial, ef)
    c, son_promedios = _componentes(historial, i)

    indicadores = [
        Indicador(clave="margen_neto", nombre="Margen neto", valor=c["margen_neto"],
                  unidad="proporcion", formula="Utilidad neta / Ingresos operacionales"),
        Indicador(clave="rotacion_activos", nombre="Rotación de activos",
                  valor=c["rotacion_activos"], unidad="veces",
                  formula="Ingresos anuales / Activo total promedio"),
        Indicador(clave="multiplicador_capital", nombre="Multiplicador del capital",
                  valor=c["multiplicador_capital"], unidad="veces",
                  formula="Activo total promedio / Patrimonio promedio"),
        Indicador(clave="roe", nombre="ROE (DuPont)", valor=c["roe"], unidad="proporcion",
                  formula="Margen neto × Rotación de activos × Multiplicador del capital"),
    ]

    if not son_promedios:
        supuestos.append(SUPUESTO_SIN_PROMEDIO)
    if c["multiplicador_capital"] is None:
        advertencias.append("Patrimonio promedio nulo o negativo: el DuPont no tiene interpretación.")

    return ResultadoModulo(modulo="balance", analisis="dupont", fecha_corte=ef.fecha_corte,
                           indicadores=indicadores, supuestos=supuestos,
                           fuentes=fuentes, advertencias=advertencias)


def variacion(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    """
    Descompone el cambio del ROE entre el periodo i−1 y el i.

    Cada indicador `participacion_*` es la fracción del cambio de ln(ROE) que
    explica esa palanca; las tres suman exactamente 1 (100 %). Se presenta como
    participación y no como diferencia logarítmica porque esta última, mostrada
    en %, se lee como "% del cambio" y no lo es. Solo se puede calcular si el
    ROE y las tres palancas son positivos en ambos periodos.
    """
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    fuentes, supuestos, advertencias = contexto_base(historial, ef)
    hallazgos: list[str] = []
    nombres = {"margen_neto": "margen neto", "rotacion_activos": "rotación de activos",
               "multiplicador_capital": "multiplicador del capital"}

    if i == 0:
        advertencias.append("Se necesitan al menos dos periodos para analizar la variación del ROE.")
        return ResultadoModulo(modulo="balance", analisis="dupont_variacion",
                               fecha_corte=ef.fecha_corte, supuestos=supuestos,
                               fuentes=fuentes, advertencias=advertencias)

    actual, _ = _componentes(historial, i)
    anterior, prom_anterior = _componentes(historial, i - 1)
    fecha_anterior = historial.periodos[i - 1].fecha_corte
    fuentes.append(f"Periodo de comparación con corte al {fecha_anterior:%d/%m/%Y}")
    if not prom_anterior:
        supuestos.append("El periodo de comparación usa saldos de cierre (no tiene periodo previo).")

    calculable = all(
        actual[k] is not None and anterior[k] is not None and actual[k] > 0 and anterior[k] > 0
        for k in (*PALANCAS, "roe")
    )
    indicadores = [
        Indicador(clave="roe_anterior", nombre="ROE periodo anterior", valor=anterior["roe"],
                  unidad="proporcion", formula="DuPont del periodo anterior"),
        Indicador(clave="roe_actual", nombre="ROE periodo actual", valor=actual["roe"],
                  unidad="proporcion", formula="DuPont del periodo actual"),
    ]
    cambio = math.log(actual["roe"] / anterior["roe"]) if calculable else 0
    if calculable and abs(cambio) > 1e-9:
        # Participación de cada palanca en el cambio de ln(ROE): suman 100 %.
        # Una participación negativa es una palanca que jugó en contra.
        participacion = {k: math.log(actual[k] / anterior[k]) / cambio for k in PALANCAS}
        for k, v in participacion.items():
            indicadores.append(Indicador(
                clave=f"participacion_{k}",
                nombre=f"Parte del cambio del ROE explicada por el {nombres[k]}",
                valor=v, unidad="proporcion",
                formula=f"ln({nombres[k]} actual / anterior) / ln(ROE actual / anterior)"))
        principal = max(participacion, key=lambda k: abs(participacion[k]))
        sentido = "subió" if actual["roe"] > anterior["roe"] else "bajó"
        detalle = ", ".join(f"el {nombres[k]} {formatear(v, 'proporcion')}"
                            for k, v in participacion.items())
        hallazgos.append(
            f"El ROE {sentido} de {formatear(anterior['roe'], 'proporcion')} a "
            f"{formatear(actual['roe'], 'proporcion')}; la palanca que más explica el cambio "
            f"es el {nombres[principal]}. Participación en el cambio: {detalle}."
        )
    elif calculable:
        advertencias.append("El ROE no cambió entre los dos periodos: no hay variación que descomponer.")
    else:
        advertencias.append(
            "La descomposición logarítmica requiere ROE y palancas positivos en ambos "
            "periodos (p. ej. falla con pérdidas o patrimonio negativo)."
        )

    return ResultadoModulo(modulo="balance", analisis="dupont_variacion",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           hallazgos=hallazgos, supuestos=supuestos, fuentes=fuentes,
                           advertencias=advertencias)
