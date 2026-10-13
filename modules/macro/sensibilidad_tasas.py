"""
¿Cómo me afectan las tasas de interés? Cuánto cambiarían los gastos
financieros y la cobertura de intereses si la tasa de la deuda sube o baja,
con la deuda que la empresa tiene al corte.

Decisiones (SPEC-sensibilidad-tasas.md, aprobadas el 12/10/2026):
- Aritmética de sensibilidad, no pronóstico: misma deuda, misma utilidad
  operacional; los puntos se suman directamente a la tasa de la deuda.
- Un punto cuesta 1 % de la deuda financiera AL CORTE (la que se va a
  repreciar), no del promedio. La tasa implícita sí usa el promedio
  (convención flujo/saldo).
- Exposición máxima: toda la deuda se reprecia, porque el balance no dice
  qué parte es a tasa fija.
- Escenarios ±1, ±2, ±3 puntos, el que pida el gerente y el histórico: la
  mayor alza de la IBR a 3 meses en 12 meses (fin de mes).
- Antes de impuestos y solo por el canal de los intereses.
"""
from __future__ import annotations

from datetime import date

from data_sources.externos.series.modelo import Serie
from modules.balance.comun import SUPUESTO_SIN_PROMEDIO, contexto_base, factor_anual
from modules.base import Indicador, ResultadoModulo, division_segura, formatear
from modules.esquema_financiero import HistorialFinanciero

ESCENARIOS = (1, 2, 3)
MAX_PUNTOS = 10
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]

# Sin referencia sectorial de esta sensibilidad, el 7B la calificaba ("aumento
# significativo"); la distinción va en un hallazgo, como con el EBITDA en pesos
NO_ES_PRONOSTICO = ("Son escenarios hipotéticos sobre la tasa de la deuda, no un pronóstico "
                    "de las tasas, y no hay referencia del sector para calificar si el efecto "
                    "es alto o bajo.")
SUPUESTO_EXPOSICION = (
    "Se supuso que toda la deuda financiera cambia de tasa en el año (créditos a tasa "
    "variable o que se renuevan): con créditos a tasa fija el efecto es menor y llega solo "
    "al renovarlos.")
SUPUESTO_ESCENARIOS = (
    "Los escenarios suman los puntos directamente a la tasa de la deuda y mantienen la deuda "
    "del corte ({corte}) y la utilidad operacional del periodo; si la deuda cambió desde "
    "entonces, el efecto cambia en proporción. Los efectos son antes de impuestos.")
SUPUESTO_5305 = (
    "Los gastos financieros incluyen comisiones y gastos bancarios además de intereses: la "
    "tasa implícita de la deuda puede estar sobrestimada.")
SUPUESTO_CANAL = (
    "Solo se mide el efecto sobre los intereses de la deuda; las tasas también afectan la "
    "demanda de los clientes, que no se mide aquí.")


class ErrorPuntos(ValueError):
    """El escenario pedido está fuera de rango; el mensaje lo explica."""


def mayor_alza_12m(serie: Serie) -> tuple[date, float] | None:
    """Mayor cambio a 12 meses con datos de fin de mes, en las unidades de la serie."""
    por_mes = {(f.year, f.month): (f, v) for f, v in serie.fin_de_mes()}
    cambios = [(v - por_mes[(a - 1, m)][1], f) for (a, m), (f, v) in por_mes.items()
               if (a - 1, m) in por_mes]
    if not cambios:
        return None
    alza, fecha = max(cambios)
    return fecha, alza


def _pesos(valor: float) -> str:
    return formatear(valor, "pesos")


def _veces(valor: float) -> str:
    return formatear(valor, "veces")


def _n(puntos: float) -> str:
    """'3', '1,5': el número de puntos como lo diría el gerente."""
    return f"{abs(puntos):g}".replace(".", ",")


def _sentido(puntos: float) -> str:
    return "más" if puntos > 0 else "menos"


def _puntos(puntos: float) -> str:
    """'1 punto más', '2,5 puntos menos'."""
    return f"{_n(puntos)} punto{'' if abs(puntos) == 1 else 's'} {_sentido(puntos)}"


def sensibilidad_tasas(historial: HistorialFinanciero, i: int, tasa_politica: Serie, ibr: Serie,
                       puntos: float | None = None) -> ResultadoModulo:
    if puntos is not None and not (0 < abs(puntos) <= MAX_PUNTOS):
        raise ErrorPuntos(f"El cambio de tasa debe estar entre −{MAX_PUNTOS} y {MAX_PUNTOS} "
                          f"puntos y ser distinto de cero (se pidió {_n(puntos)}).")
    i = i % len(historial.periodos)
    ef = historial.periodos[i]
    r = ef.resultados
    fuentes, supuestos, advertencias = contexto_base(historial, ef)
    for s in (tasa_politica, ibr):
        fuentes.append(f"{s.nombre}: {s.fuente}; unidad: {s.unidad}; consultada el "
                       f"{s.consultada:%d/%m/%Y}")
        supuestos += s.supuestos
        advertencias += s.advertencias

    deuda = ef.balance.deuda_financiera
    deuda_prom, es_promedio = historial.saldo_promedio("deuda_financiera", i)
    gastos = r.gastos_financieros * factor_anual(ef)
    uo = r.utilidad_operacional * factor_anual(ef)
    hay_deuda = deuda > 0
    # Con deuda y sin gastos financieros, los intereses quedaron en otra cuenta: la base de
    # los escenarios no se conoce (mismo criterio que el módulo 1)
    sin_intereses = hay_deuda and r.gastos_financieros == 0
    con_base = hay_deuda and not sin_intereses

    def gastos_con(delta: float) -> float | None:
        if not con_base:
            return None
        g = gastos + deuda * delta
        return g if g >= 0 else None          # una baja no deja intereses negativos

    def cobertura(g: float | None) -> float | None:
        return division_segura(uo, g) if g is not None and uo > 0 else None

    por_punto = deuda * 0.01 if hay_deuda else None
    implicita = division_segura(gastos, deuda_prom) if con_base else None
    cobertura_hoy = cobertura(gastos) if con_base else None
    alza_uno = (division_segura(uo - gastos, deuda)
                if cobertura_hoy is not None and cobertura_hoy >= 1 else None)
    historico = mayor_alza_12m(ibr)
    alza_hist = historico[1] / 100 if historico else None

    indicadores = [
        Indicador(clave="deuda_financiera", nombre="Deuda financiera al corte", valor=deuda,
                  unidad="pesos", formula="Obligaciones financieras CP + LP al corte"),
        Indicador(clave="tasa_implicita_deuda", nombre="Tasa implícita de la deuda",
                  valor=implicita, unidad="tasa",
                  formula="Gastos financieros anuales / Deuda financiera promedio"),
        Indicador(clave="intereses_por_punto",
                  nombre="Aumento de los gastos financieros por cada punto de tasa",
                  valor=por_punto, unidad="pesos", formula="Deuda financiera al corte × 1 punto"),
        Indicador(clave="gastos_financieros_anuales", nombre="Gastos financieros del periodo",
                  valor=gastos if con_base else None, unidad="pesos",
                  formula="Gastos financieros (anualizados si < 12 meses)"),
        Indicador(clave="cobertura_intereses", nombre="Cobertura de intereses actual",
                  valor=cobertura_hoy, unidad="veces",
                  formula="Utilidad operacional / Gastos financieros"),
    ]
    def escenario(sufijo: str, cambio: str, delta: float | None) -> list[Indicador]:
        g = gastos_con(delta) if delta is not None else None
        return [Indicador(clave=f"gastos_financieros_{sufijo}",
                          nombre=f"Gastos financieros con {cambio}", valor=g, unidad="pesos",
                          formula="Gastos financieros + deuda al corte × cambio de tasa"),
                Indicador(clave=f"cobertura_{sufijo}", nombre=f"Cobertura de intereses con {cambio}",
                          valor=cobertura(g), unidad="veces",
                          formula="Utilidad operacional / Gastos financieros del escenario")]

    # Con un escenario pedido, solo ese: con todos a la vez el 7B los comparaba por su
    # cuenta ("+5 es similar a la mayor alza histórica, por lo que estaría preparado")
    if puntos is not None:
        sufijo = (f"{'mas' if puntos > 0 else 'menos'}_{abs(puntos):g}"
                  if abs(puntos) in ESCENARIOS else "pedido")
        indicadores += escenario(sufijo, f"{_puntos(puntos)} de tasa", puntos / 100)
    else:
        for n in ESCENARIOS:
            for signo in (1, -1):
                indicadores += escenario(f"{'mas' if signo > 0 else 'menos'}_{n}",
                                         f"{_puntos(signo * n)} de tasa", signo * n / 100)
        indicadores.append(
            Indicador(clave="mayor_alza_ibr_12m",
                      nombre="Mayor alza de la IBR a 3 meses en 12 meses", valor=alza_hist,
                      unidad="puntos",
                      formula="Máximo cambio a 12 meses de la IBR a 3 meses (fin de mes)"))
        indicadores += escenario("historico", "la mayor alza histórica de la IBR", alza_hist)
    # El punto de quiebre no es indicador: su nombre ("apenas cubre") llevó al 7B a
    # decir que otro escenario "apenas cubriría" los intereses. Va solo en el hallazgo,
    # y con cifra solo si está dentro de lo observado.

    # Contexto de mercado: niveles del último dato publicado, no del corte del balance.
    # Sin el cambio a 12 meses: el 7B lo confundía con los escenarios ("alza de 3,00 puntos")
    fecha_tp, tp = tasa_politica.observaciones[-1]
    fecha_ibr, valor_ibr = ibr.observaciones[-1]
    indicadores += [
        Indicador(clave="tasa_politica", nombre="Tasa de política monetaria", valor=tp / 100,
                  unidad="tasa", formula=f"Último dato publicado ({fecha_tp:%d/%m/%Y})"),
        Indicador(clave="ibr_3m", nombre="IBR a 3 meses", valor=valor_ibr / 100, unidad="tasa",
                  formula=f"Último dato publicado ({fecha_ibr:%d/%m/%Y})"),
    ]

    # Hallazgos: cada comparación queda redactada aquí, no en el modelo
    hallazgos: list[str] = []
    if not hay_deuda:
        hallazgos.append("La empresa no tiene deuda financiera al corte: un cambio en las "
                         "tasas no le cambia los gastos financieros.")
    else:
        hallazgos.append(f"Cada punto que suba la tasa de la deuda le suma {_pesos(por_punto)} "
                         f"al año en gastos financieros (1 % de la deuda financiera de "
                         f"{_pesos(deuda)}).")
    def frase_escenario(cambio: float) -> str:
        """Aumento y nivel por separado: sin el aumento, el 7B lo calculaba por su cuenta
        (2 × $ 6.800.000) y el verificador rechazaba la respuesta."""
        g = gastos_con(cambio / 100)
        if g is None:
            return f"Con {_puntos(cambio)}, los gastos financieros llegarían a cero."
        sube = cambio > 0
        frase = (f"Con {_puntos(cambio)}, los gastos financieros "
                 f"{'aumentarían' if sube else 'disminuirían'} {_pesos(abs(g - gastos))} al "
                 f"año, hasta {_pesos(g)}")
        if cobertura(g) is not None:
            frase += (f", y la cobertura de intereses {'bajaría' if sube else 'subiría'} a "
                      f"{_veces(cobertura(g))}")
        return frase + "."

    if con_base:
        actual = f"En {ef.fecha_corte.year} los gastos financieros fueron {_pesos(gastos)}"
        if cobertura_hoy is not None:
            actual += f" y la cobertura de intereses {_veces(cobertura_hoy)}"
        hallazgos.append(actual + ".")
    if con_base and puntos is not None:
        hallazgos.append(frase_escenario(puntos))
    elif con_base:
        hallazgos += [frase_escenario(3), frase_escenario(-3)]
        # El año del alza histórica va primero y explícito: el 7B la presentó como "del
        # último año"
        g_hist = gastos_con(alza_hist) if alza_hist is not None else None
        if g_hist is not None:
            fecha, alza = historico
            mes = MESES[fecha.month - 1]
            frase = (f"La mayor alza de la IBR a 3 meses en un año fue de "
                     f"{formatear(alza_hist, 'puntos')}, en {fecha.year} (de {mes} de "
                     f"{fecha.year - 1} a {mes} de {fecha.year}): si la tasa de la deuda subiera "
                     f"eso, los gastos financieros aumentarían {_pesos(g_hist - gastos)} al "
                     f"año, hasta {_pesos(g_hist)}")
            # Aumento y nivel por separado: el 7B llamó "aumento" al nivel
            if cobertura(g_hist) is not None:
                frase += f", y la cobertura bajaría a {_veces(cobertura(g_hist))}"
            hallazgos.append(frase + ".")
        # El punto de quiebre se compara con lo observado: lejos de ahí, la cifra solo
        # confundía al 7B (la mezcló con la cobertura de otro escenario)
        if alza_uno is not None and alza_hist is not None:
            if alza_uno <= alza_hist:
                hallazgos.append(
                    f"Con un alza de {formatear(alza_uno, 'puntos')}, menor que la de "
                    f"{historico[0].year} ({formatear(alza_hist, 'puntos')}), la utilidad "
                    "operacional apenas alcanzaría para pagar los gastos financieros.")
            else:
                hallazgos.append(f"Aun con un alza como la de {historico[0].year}, la utilidad "
                                 "operacional seguiría alcanzando para pagar los gastos "
                                 "financieros.")
    hallazgos.append(f"Al {fecha_tp:%d/%m/%Y} la tasa de política monetaria del Banco de la "
                     f"República es {formatear(tp / 100, 'tasa')}; la IBR a 3 meses, referencia "
                     f"de muchos créditos a tasa variable, estaba en "
                     f"{formatear(valor_ibr / 100, 'tasa')} al {fecha_ibr:%d/%m/%Y}.")
    if hay_deuda:
        hallazgos.append(NO_ES_PRONOSTICO)

    # Supuestos y advertencias
    if hay_deuda:
        supuestos += [SUPUESTO_EXPOSICION,
                      SUPUESTO_ESCENARIOS.format(corte=f"{ef.fecha_corte:%d/%m/%Y}")]
        if con_base:
            supuestos.append(SUPUESTO_5305)
            if not es_promedio:
                supuestos.append(SUPUESTO_SIN_PROMEDIO)
        supuestos.append(SUPUESTO_CANAL)
    if ef.meses < 12:
        supuestos.append(f"Gastos financieros y utilidad operacional anualizados a partir de "
                         f"{ef.meses} meses.")
    if sin_intereses:
        advertencias.append(
            "Hay deuda financiera pero no se identificaron gastos financieros: los intereses "
            "pueden estar registrados en otra cuenta. Solo se calcula cuánto cuesta cada punto.")
    elif con_base and uo <= 0:
        advertencias.append("La utilidad operacional es nula o negativa: no cubre los gastos "
                            "financieros, con o sin cambios en las tasas.")
    elif cobertura_hoy is not None and cobertura_hoy < 1:
        advertencias.append("La utilidad operacional ya no alcanza para cubrir los gastos "
                            "financieros, sin necesidad de un alza de tasas.")

    return ResultadoModulo(modulo="macro", analisis="sensibilidad_tasas",
                           fecha_corte=ef.fecha_corte, indicadores=indicadores,
                           hallazgos=hallazgos, supuestos=supuestos, fuentes=fuentes,
                           advertencias=advertencias)
