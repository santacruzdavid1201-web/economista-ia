"""
Z'' de Altman para mercados emergentes (EM-Score).

    EM = 3,25 + 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4

    X1 = Capital de trabajo / Activo total            (liquidez)
    X2 = Utilidades retenidas / Activo total           (rentabilidad acumulada)
    X3 = EBIT / Activo total                           (rentabilidad operativa)
    X4 = Patrimonio contable / Pasivo total            (solvencia)

Versión Z'' (sin la razón ventas/activos, apta para empresas no manufactureras
y no cotizadas) con la constante 3,25 de Altman para emisores de mercados
emergentes. La constante desplaza las zonas del Z'' original (1,10 y 2,60) a
4,35 y 5,85. La tabla de equivalencia con calificaciones de bonos es la de
Altman y Hotchkiss (2005).

Es una señal de alerta, no una probabilidad de quiebra: fue calibrado con
muestras de otras economías y otra época, y no aplica a entidades financieras.
"""
from __future__ import annotations

from modules.balance.comun import contexto_base, factor_anual
from modules.base import Indicador, ResultadoModulo, division_segura
from modules.esquema_financiero import HistorialFinanciero

CONSTANTE = 3.25
PESOS = {"x1": 6.56, "x2": 3.26, "x3": 6.72, "x4": 1.05}
ZONA_RIESGO, ZONA_SEGURA = 4.35, 5.85

# (límite inferior, calificación equivalente) — Altman y Hotchkiss (2005)
EQUIVALENCIA_CALIFICACION = [
    (8.15, "AAA"), (7.60, "AA+"), (7.30, "AA"), (7.00, "AA-"), (6.85, "A+"),
    (6.65, "A"), (6.40, "A-"), (6.25, "BBB+"), (5.85, "BBB"), (5.65, "BBB-"),
    (5.25, "BB+"), (4.95, "BB"), (4.75, "BB-"), (4.50, "B+"), (4.15, "B"),
    (3.75, "B-"), (3.20, "CCC+"), (2.50, "CCC"), (1.75, "CCC-"),
]

# CIIU Rev. 4 A.C.: divisiones 64-66 = actividades financieras y de seguros
DIVISIONES_FINANCIERAS = {"64", "65", "66"}


def calificacion_equivalente(em: float) -> str:
    for limite, calificacion in EQUIVALENCIA_CALIFICACION:
        if em >= limite:
            return calificacion
    return "D"


def zona(em: float) -> str:
    if em > ZONA_SEGURA:
        return "segura"
    if em >= ZONA_RIESGO:
        return "gris"
    return "riesgo"


def altman(historial: HistorialFinanciero, i: int = -1) -> ResultadoModulo:
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    b, r = ef.balance, ef.resultados
    fuentes, supuestos, advertencias = contexto_base(historial, ef)
    fuentes.append("Altman y Hotchkiss (2005), Corporate Financial Distress and Bankruptcy.")
    hallazgos: list[str] = []

    at = b.activo_total
    utilidades_retenidas = b.reservas + b.resultados_acumulados + b.resultado_ejercicio
    ebit_anual = r.utilidad_operacional * factor_anual(ef)

    x = {
        "x1": division_segura(b.activo_corriente - b.pasivo_corriente, at),
        "x2": division_segura(utilidades_retenidas, at),
        "x3": division_segura(ebit_anual, at),
        "x4": division_segura(b.patrimonio_total, b.pasivo_total),
    }
    calculable = all(v is not None for v in x.values())
    em = CONSTANTE + sum(PESOS[k] * x[k] for k in x) if calculable else None

    descripciones = {
        "x1": ("X1 · Capital de trabajo / Activo total", "(Activo corriente − Pasivo corriente) / Activo total"),
        "x2": ("X2 · Utilidades retenidas / Activo total", "(Reservas + Resultados acumulados + Resultado del ejercicio) / Activo total"),
        "x3": ("X3 · EBIT / Activo total", "Utilidad operacional anual / Activo total"),
        "x4": ("X4 · Patrimonio / Pasivo total", "Patrimonio contable / Pasivo total"),
    }
    indicadores = [
        Indicador(clave=k, nombre=descripciones[k][0], valor=x[k],
                  unidad="proporcion" if k != "x4" else "veces", formula=descripciones[k][1])
        for k in x
    ]
    indicadores.append(Indicador(
        clave="em_score", nombre="Z'' de Altman (mercados emergentes)", valor=em,
        unidad="veces", formula="3,25 + 6,56·X1 + 3,26·X2 + 6,72·X3 + 1,05·X4"))

    supuestos += [
        "Utilidades retenidas = reservas + resultados acumulados + resultado del ejercicio.",
        "EBIT aproximado con la utilidad operacional (excluye otros ingresos y gastos).",
        "X4 usa el patrimonio contable porque la empresa no cotiza en bolsa.",
    ]
    if ef.meses < 12:
        supuestos.append(f"EBIT anualizado a partir de {ef.meses} meses.")
    advertencias.append(
        "El Z'' es una señal de alerta temprana, no una probabilidad de quiebra: "
        "fue calibrado con empresas de otras economías y épocas."
    )
    if historial.empresa.ciiu[:2] in DIVISIONES_FINANCIERAS:
        advertencias.append(
            "La empresa es del sector financiero (CIIU 64-66): el Z'' no aplica a "
            "entidades financieras por su estructura de balance."
        )

    if em is None:
        advertencias.append("Faltan datos para calcular el Z'' (activo o pasivo total en cero).")
    else:
        cal = calificacion_equivalente(em)
        z = zona(em)
        hallazgos.append(
            f"Z'' = {em:.2f}: zona {z}, equivalente a una calificación {cal} "
            f"en la escala de Altman y Hotchkiss."
        )
        if z == "gris":
            hallazgos.append(
                f"Está entre {ZONA_RIESGO} y {ZONA_SEGURA}: no hay señal clara, conviene "
                "seguir la tendencia en los próximos periodos."
            )

    return ResultadoModulo(modulo="balance", analisis="altman", fecha_corte=ef.fecha_corte,
                           indicadores=indicadores, hallazgos=hallazgos, supuestos=supuestos,
                           fuentes=fuentes, advertencias=advertencias)
