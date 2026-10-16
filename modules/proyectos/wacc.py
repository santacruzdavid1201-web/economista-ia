"""
¿Con qué tasa descuento mi proyecto? Costo de capital promedio ponderado (WACC)
de la empresa, en términos reales, para no escribir la tasa de oportunidad "a ojo".

Decisiones (SPEC-costo-capital.md, aprobadas el 16/10/2026):
- Todo en real con el TES en UVR: los flujos del proyecto van en pesos de hoy con
  la senda del BanRep, y el TES en pesos traería otra inflación (la del mercado).
- Costo del patrimonio por CAPM con el método de Damodaran: al TES se le resta el
  spread de incumplimiento de Colombia y el riesgo país entra en la prima total,
  multiplicado por la beta del sector ajustada a la deuda de la empresa (Hamada).
- Costo de la deuda: la tasa implícita del balance, después de impuestos, pasada a
  real con la inflación de ese mismo año (Fisher ex post).
- Pesos en valores en libros: una pyme no tiene valor de mercado.
- Sin estados financieros, o con patrimonio en libros ≤ 0, no hay WACC: se da el
  costo de capital de los activos (un negocio del sector sin deuda) como referencia.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple

from data_sources.externos.series.modelo import Serie
from modules.balance.comun import SUPUESTO_SIN_PROMEDIO, contexto_base, tasa_implicita
from modules.base import Indicador, ResultadoModulo, formatear
from modules.esquema_financiero import HistorialFinanciero
from modules.proyectos.matematica_financiera import como_la_escribio

REFERENCIA = ("Es una referencia, no una regla: a un proyecto más riesgoso que el negocio de "
              "siempre se le puede exigir más.")


class Parametros(NamedTuple):
    beta_sin_deuda: float         # beta del sector sin deuda, corregida por caja
    spread: float                 # spread de incumplimiento de Colombia (fracción)
    prima_total: float            # prima de riesgo de las acciones en Colombia (madura + país)
    fuente: str                   # "Damodaran, actualización del 5 de enero de 2026"
    sector: str                   # "Hotel/Gaming" de Damodaran


def _pct(valor: float) -> str:
    return formatear(valor, "tasa")


def _inflacion(valor: float) -> str:
    return formatear(valor, "proporcion")          # "4,3 %": como la publican el BanRep y el DANE


def _uso(nombre: str, tasa: float) -> str:
    """Con qué tasa se descuenta: el 7B contestó "debes usar 12,82 %, equivalente nominal del
    primer año" para descontar flujos en pesos de hoy."""
    # Dicho como referencia: el 7B copia la redacción y la pregunta trae "¿con qué tasa debo…?"
    return (f"La referencia para descontar los flujos en pesos de hoy es {nombre}, {_pct(tasa)}; "
            "el equivalente nominal del primer año solo sirve para compararlo con tasas en pesos "
            "corrientes, como las de los bancos.")


def _nominal(real: float, inflacion_1: float) -> float:
    return (1 + real) * (1 + inflacion_1) - 1


def _indicadores_wacc(wacc: float | None, inflacion_1: float) -> list[Indicador]:
    return [
        Indicador(clave="wacc", nombre="Costo de capital promedio ponderado (WACC, real)",
                  valor=wacc, unidad="tasa", formula="peso del patrimonio × costo del patrimonio "
                                                     "+ peso de la deuda × costo real de la deuda"),
        Indicador(clave="wacc_nominal", nombre="WACC, equivalente nominal del primer año",
                  valor=_nominal(wacc, inflacion_1) if wacc is not None else None, unidad="tasa",
                  formula="(1 + WACC real) × (1 + inflación esperada del primer año) − 1"),
    ]


def costo_capital(tes_uvr: Serie, p: Parametros, tarifa: float, inflacion_1: float,
                  historial: HistorialFinanciero | None = None, i: int = -1,
                  ipc: Serie | None = None) -> ResultadoModulo:
    """
    WACC real de la empresa del periodo i y su equivalente nominal del primer año
    (con `inflacion_1`), o el costo de los activos sin estados financieros.
    `tarifa` es la de renta (fracción); `ipc` da la inflación del año del balance.
    """
    fecha_tes, tes = tes_uvr.observaciones[-1]
    rf = tes / 100 - p.spread
    fuentes = [f"{tes_uvr.nombre}: {tes_uvr.fuente}; consultado el {tes_uvr.consultada:%d/%m/%Y}",
               f"Primas de riesgo y beta del sector: {p.fuente}"]
    supuestos = [
        f"Tasa sin riesgo: TES cero cupón en UVR a 10 años ({_pct(tes / 100)} al "
        f"{fecha_tes:%d/%m/%Y}), que ya es real, menos el spread de incumplimiento de Colombia "
        f"({_pct(p.spread)}).",
        f"Prima de riesgo de las acciones en Colombia: {_pct(p.prima_total)} (mercado maduro más "
        "riesgo país); aplicar primas medidas en dólares a una tasa real en pesos es una "
        "aproximación.",
        f"Beta sin deuda de {p.sector} en mercados emergentes: "
        f"{formatear(p.beta_sin_deuda, 'veces').removesuffix(' veces')}. Una pyme no cotiza en "
        "bolsa y no tiene beta propia.",
        f"El equivalente nominal usa la inflación esperada del primer año "
        f"({_inflacion(inflacion_1)}).",
    ]
    advertencias: list[str] = []
    comunes = [
        Indicador(clave="tasa_sin_riesgo", nombre="Tasa sin riesgo real", valor=rf, unidad="tasa",
                  formula="TES cero cupón UVR 10 años − spread de incumplimiento de Colombia"),
        Indicador(clave="prima_riesgo", nombre="Prima de riesgo de las acciones en Colombia",
                  valor=p.prima_total, unidad="tasa",
                  formula="prima de un mercado maduro + prima de riesgo país (Damodaran)"),
    ]
    ku = rf + p.beta_sin_deuda * p.prima_total

    def sin_wacc(hallazgo: str, fecha_corte: date | None = None) -> ResultadoModulo:
        indicadores = comunes + [
            Indicador(clave="beta_sin_deuda", nombre="Beta del sector sin deuda",
                      valor=p.beta_sin_deuda, unidad="veces", formula=f"{p.sector}, mercados "
                                                                       "emergentes (Damodaran)"),
            Indicador(clave="costo_activos", nombre="Costo de capital de los activos (real)",
                      valor=ku, unidad="tasa",
                      formula="tasa sin riesgo real + beta sin deuda × prima de riesgo"),
            Indicador(clave="costo_activos_nominal",
                      nombre="Costo de capital de los activos, equivalente nominal del primer año",
                      valor=_nominal(ku, inflacion_1), unidad="tasa",
                      formula="(1 + costo real) × (1 + inflación esperada del primer año) − 1"),
        ]
        if fecha_corte is not None:          # hay estados financieros, pero el WACC no se calcula
            indicadores += _indicadores_wacc(None, inflacion_1)
        return ResultadoModulo(
            modulo="proyectos", analisis="costo_capital", fecha_corte=fecha_corte,
            indicadores=indicadores, fuentes=fuentes, supuestos=supuestos,
            advertencias=advertencias,
            hallazgos=[hallazgo + f" Como referencia, el costo de capital de un negocio del sector "
                       f"sin deuda (costo de los activos) es {_pct(ku)} en términos reales; "
                       f"equivale a {_pct(_nominal(ku, inflacion_1))} en pesos corrientes el "
                       "primer año.", _uso("el costo de los activos", ku), REFERENCIA])

    if historial is None:
        return sin_wacc("Sin estados financieros no se puede calcular el costo de capital de su "
                        "empresa (WACC): faltan su deuda, lo que le cuesta y su patrimonio.")

    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    base_fuentes, base_supuestos, base_avisos = contexto_base(historial, ef)
    fuentes[:0] = base_fuentes
    supuestos[:0] = base_supuestos
    advertencias += base_avisos
    deuda, patrimonio = ef.balance.deuda_financiera, ef.balance.patrimonio_total
    if patrimonio <= 0:
        advertencias.append(
            f"El patrimonio en libros al {ef.fecha_corte:%d/%m/%Y} es cero o negativo: la relación "
            "deuda/patrimonio y la beta de la empresa no tienen sentido, así que no se calcula el "
            "WACC.")
        return sin_wacc("No se puede calcular el costo de capital de la empresa (WACC).",
                        ef.fecha_corte)

    supuestos += [
        f"Deuda financiera y patrimonio en valores en libros del balance al "
        f"{ef.fecha_corte:%d/%m/%Y}: una pyme no tiene valor de mercado.",
        "La beta del sector se ajusta a la deuda de la empresa con la fórmula de Hamada.",
    ]
    dp = deuda / patrimonio
    beta = p.beta_sin_deuda * (1 + (1 - tarifa) * dp)
    ke = rf + beta * p.prima_total
    peso_deuda = deuda / (deuda + patrimonio)
    indicadores = comunes + [
        Indicador(clave="deuda_patrimonio", nombre="Deuda financiera / patrimonio", valor=dp,
                  unidad="veces", formula="deuda financiera / patrimonio, en libros"),
        Indicador(clave="beta_apalancada", nombre="Beta de la empresa (con su deuda)", valor=beta,
                  unidad="veces",
                  formula="beta sin deuda × (1 + (1 − tarifa de renta) × deuda / patrimonio)"),
        Indicador(clave="costo_patrimonio", nombre="Costo del patrimonio (real)", valor=ke,
                  unidad="tasa", formula="tasa sin riesgo real + beta de la empresa × prima de "
                                         "riesgo"),
    ]

    if deuda <= 0:
        hallazgos = [f"La empresa no tiene deuda financiera: su costo de capital es el de sus "
                     f"dueños, {_pct(ke)} en términos reales; equivale a "
                     f"{_pct(_nominal(ke, inflacion_1))} en pesos corrientes el primer año.",
                     _uso("el WACC real", ke)]
        wacc = ke
    else:
        kd, es_promedio = tasa_implicita(historial, i)
        if not es_promedio:
            supuestos.append(SUPUESTO_SIN_PROMEDIO)
        supuestos.append(f"El ahorro de impuestos de la deuda usa la tarifa de renta de "
                         f"{como_la_escribio(tarifa)}.")
        corte = ef.fecha_corte
        anterior = date(corte.year - 1, corte.month, 1)
        ipc_hoy = ipc.promedio_mensual(corte, corte) if ipc else None
        ipc_ant = ipc.promedio_mensual(anterior, anterior) if ipc else None
        inflacion = ipc_hoy / ipc_ant - 1 if ipc_hoy and ipc_ant else None
        if ipc is not None:
            fuentes.append(f"IPC nacional: {ipc.fuente}; consultado el {ipc.consultada:%d/%m/%Y}")
        if kd is None:
            advertencias.append(
                "La empresa tiene deuda financiera, pero no se identificaron gastos financieros (los "
                "intereses quedaron en otra cuenta): no se puede calcular el costo de la deuda ni "
                "el WACC.")
        if inflacion is None:
            advertencias.append(f"No hay IPC de {corte:%m/%Y} y del mismo mes un año antes: no se "
                                "puede pasar a real el costo de la deuda ni calcular el WACC.")
        else:
            supuestos.append(f"El costo de la deuda se pasa a real con la inflación de los 12 meses "
                             f"al corte del balance ({_inflacion(inflacion)}): la tasa de ese año entre "
                             "la inflación de ese año.")
        if ef.resultados.utilidad_antes_impuestos <= 0:
            advertencias.append(
                f"La empresa no tuvo utilidad antes de impuestos en el periodo al "
                f"{corte:%d/%m/%Y}: no aprovecha el ahorro de impuestos de la deuda, y su costo "
                "real puede ser mayor que el calculado.")
        kd_real = ((1 + kd * (1 - tarifa)) / (1 + inflacion) - 1
                   if kd is not None and inflacion is not None else None)
        wacc = (1 - peso_deuda) * ke + peso_deuda * kd_real if kd_real is not None else None
        indicadores += [
            Indicador(clave="costo_deuda_nominal", nombre="Tasa implícita de la deuda", valor=kd,
                      unidad="tasa", formula="Gastos financieros anuales / Deuda financiera "
                                             "promedio"),
            Indicador(clave="inflacion_balance", nombre="Inflación de los 12 meses al corte",
                      valor=inflacion, unidad="proporcion", formula="IPC del mes del corte / IPC del "
                                                              "mismo mes un año antes − 1"),
            Indicador(clave="costo_deuda_real",
                      nombre="Costo de la deuda después de impuestos (real)", valor=kd_real,
                      unidad="tasa", formula="(1 + tasa implícita × (1 − tarifa de renta)) / "
                                             "(1 + inflación del año) − 1"),
            Indicador(clave="peso_deuda", nombre="Peso de la deuda en el capital",
                      valor=peso_deuda, unidad="proporcion",
                      formula="deuda financiera / (deuda financiera + patrimonio), en libros"),
        ]
        hallazgos = ([] if wacc is None else [
            f"El costo de capital de la empresa (WACC) es {_pct(wacc)} en términos reales; "
            f"equivale a {_pct(_nominal(wacc, inflacion_1))} en pesos corrientes el primer año.",
            _uso("el WACC real", wacc),
            f"Es lo mínimo que debe rendir un proyecto con el riesgo del negocio de siempre para "
            f"pagarles a los dueños y a los bancos lo que exigen: los dueños exigen {_pct(ke)} "
            f"real (costo del patrimonio) y la deuda cuesta {_pct(kd_real)} real después de "
            f"impuestos; la deuda financia el {formatear(peso_deuda, 'proporcion')} del "
            "capital, en libros."])
        if wacc is None:
            hallazgos = [f"No se puede calcular el costo de capital de la empresa (WACC); el costo "
                         f"del patrimonio es {_pct(ke)} en términos reales."]

    indicadores += _indicadores_wacc(wacc, inflacion_1)
    return ResultadoModulo(modulo="proyectos", analisis="costo_capital",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           hallazgos=hallazgos + [REFERENCIA], supuestos=supuestos,
                           fuentes=fuentes, advertencias=advertencias)
