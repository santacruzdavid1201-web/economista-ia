"""
Matemática financiera: tasas equivalentes, indicadores de proyectos y
amortización de créditos. Funciones puras; las piezas siguientes del módulo 3
(flujo, evaluación, sensibilidad, Monte Carlo) importan de aquí.

Decisiones (SPEC-matematica-financiera.md, aprobadas el 15/10/2026):
- Tasas en decimales (0,18) y siempre con su tipo. Toda conversión pasa por la
  tasa periódica vencida equivalente: dos funciones cubren cualquier par.
- El 7B confunde nominal con efectiva y mensual con anual; por eso el tipo lo
  lee Python y los hallazgos lo nombran.
"""
from __future__ import annotations

from typing import NamedTuple

from modules.base import Indicador, ResultadoModulo, formatear

# tipo → (nombre, periodos al año, nominal, anticipada)
TIPOS: dict[str, tuple[str, int, bool, bool]] = {
    "EA": ("efectiva anual", 1, False, False),
    "SV": ("semestral", 2, False, False),
    "TV": ("trimestral", 4, False, False),
    "MV": ("mensual", 12, False, False),
    "NSV": ("nominal semestre vencido", 2, True, False),
    "NTV": ("nominal trimestre vencido", 4, True, False),
    "NMV": ("nominal mes vencido", 12, True, False),
    "TA": ("trimestral anticipada", 4, False, True),
    "MA": ("mensual anticipada", 12, False, True),
    "NTA": ("nominal trimestre anticipado", 4, True, True),
    "NMA": ("nominal mes anticipado", 12, True, True),
}


class ErrorTasa(ValueError):
    """La tasa o su tipo no sirven; el mensaje dice por qué."""


def _tipo(tipo: str) -> tuple[str, int, bool, bool]:
    if tipo not in TIPOS:
        raise ErrorTasa(f"Tipo de tasa desconocido '{tipo}'. Tipos: {', '.join(TIPOS)}.")
    return TIPOS[tipo]


def a_periodica(tasa: float, tipo: str) -> tuple[float, int]:
    """Tasa de cualquier tipo → (tasa periódica vencida, periodos por año)."""
    nombre, m, nominal, anticipada = _tipo(tipo)
    i = tasa / m if nominal else tasa
    if anticipada:
        if i >= 1:
            raise ErrorTasa(f"Una tasa anticipada de 100 % o más en el periodo ({nombre}) no "
                            "tiene equivalente vencida: se pagaría todo el préstamo por adelantado.")
        i = i / (1 - i)
    if i <= -1:
        raise ErrorTasa("La tasa periódica debe ser mayor que -100 %.")
    return i, m


def desde_periodica(i: float, m: int, tipo: str) -> float:
    """Periódica vencida con `m` periodos al año → tasa equivalente del tipo pedido."""
    _, m2, nominal, anticipada = _tipo(tipo)
    j = (1 + i) ** (m / m2) - 1
    if anticipada:
        j = j / (1 + j)
    return j * m2 if nominal else j


def convertir(tasa: float, desde: str, hacia: str) -> float:
    """Tasa equivalente: misma plata al final del año con cualquier forma de cobrarla."""
    return desde_periodica(*a_periodica(tasa, desde), hacia)


# --------------------------------------------------------------------------- #
# Indicadores de proyectos: flujos por periodo, el 0 es hoy, tasa del periodo
# --------------------------------------------------------------------------- #
def vpn(tasa: float, flujos: list[float]) -> float:
    return sum(f / (1 + tasa) ** t for t, f in enumerate(flujos))


def _biseccion(f, a: float, b: float, iteraciones: int = 100) -> float:
    fa = f(a)
    for _ in range(iteraciones):
        m = (a + b) / 2
        fm = f(m)
        if fa * fm <= 0:
            b = m
        else:
            a, fa = m, fm
    return (a + b) / 2


def _enumerar(textos: list[str]) -> str:
    return textos[0] if len(textos) == 1 else ", ".join(textos[:-1]) + " y " + textos[-1]


def tir(flujos: list[float]) -> tuple[float | None, list[str]]:
    """
    TIR única, o None con la advertencia que explica por qué no hay una: un
    número solo sería engañoso si el VPN no llega a cero o llega más de una vez
    (p. ej. un hotel con una remodelación grande a mitad del proyecto).
    """
    def f(r: float) -> float:
        return vpn(r, flujos)

    # ponytail: malla de 4.000 tasas entre -99 % y 1.000 %; dos raíces dentro de una
    # misma celda (muy juntas) se verían como ninguna. Pensada para flujos anuales.
    puntos = []
    for k in range(4001):
        r = 0.01 * 1100 ** (k / 4000) - 1
        try:
            puntos.append((r, f(r)))
        except (OverflowError, ZeroDivisionError):
            continue
    raices = [a if fa == 0 else _biseccion(f, a, b)
              for (a, fa), (b, fb) in zip(puntos, puntos[1:]) if fa == 0 or fa * fb < 0]
    if len(raices) == 1:
        return raices[0], []
    if not raices:
        return None, ["El VPN no llega a cero con ninguna tasa entre -99 % y 1.000 %: no hay "
                      "TIR. La decisión se toma con el VPN."]
    return None, [f"El flujo cambia de signo más de una vez y tiene varias TIR "
                  f"({_enumerar([formatear(r, 'tasa') for r in raices])}): ninguna sirve sola "
                  "para decidir. La decisión se toma con el VPN o la TIRM."]


def tirm(tasa: float, flujos: list[float]) -> float | None:
    """
    TIR modificada: los flujos positivos se reinvierten y los negativos se
    financian a la misma tasa (supuesto). None si no hay inversión o retorno.
    """
    n = len(flujos) - 1
    futuro = sum(f * (1 + tasa) ** (n - t) for t, f in enumerate(flujos) if f > 0)
    presente = -sum(f / (1 + tasa) ** t for t, f in enumerate(flujos) if f < 0)
    if n < 1 or futuro == 0 or presente == 0:
        return None
    return (futuro / presente) ** (1 / n) - 1


def recuperacion_descontada(tasa: float, flujos: list[float]) -> float | None:
    """
    Periodos hasta que el flujo descontado acumulado llega a cero, interpolando
    dentro del periodo (supone el flujo repartido de forma pareja). None si no
    se recupera dentro de la vida del proyecto.
    """
    acumulado = flujos[0]
    for t, f in enumerate(flujos[1:], start=1):
        descontado = f / (1 + tasa) ** t
        if acumulado < 0 <= acumulado + descontado:
            return t - 1 + -acumulado / descontado
        acumulado += descontado
    return None


def indice_rentabilidad(tasa: float, flujos: list[float]) -> float | None:
    """Pesos de valor presente que devuelve cada peso invertido hoy. None sin inversión."""
    if flujos[0] >= 0:
        return None
    return vpn(tasa, [0, *flujos[1:]]) / -flujos[0]


def valor_anual_equivalente(tasa: float, flujos: list[float]) -> float:
    """El VPN repartido en cuotas iguales por periodo: compara proyectos de vida distinta."""
    n = len(flujos) - 1
    if tasa == 0:
        return vpn(0, flujos) / n
    return vpn(tasa, flujos) * tasa / (1 - (1 + tasa) ** -n)


# --------------------------------------------------------------------------- #
# Amortización de créditos
# --------------------------------------------------------------------------- #
SISTEMAS = {"cuota_fija": "cuota fija", "abono_constante": "abono constante a capital"}


class ErrorCredito(ValueError):
    """Monto, plazo o sistema que no sirven; el mensaje dice por qué."""


class Cuota(NamedTuple):
    periodo: int
    saldo_inicial: float
    interes: float
    abono: float
    cuota: float
    saldo_final: float


def amortizacion(monto: float, tasa_periodica: float, cuotas: int,
                 sistema: str = "cuota_fija") -> list[Cuota]:
    """
    Tabla del crédito. Cuota fija (francés): P · i / (1 − (1 + i)^−n).
    Abono constante: P / n de capital más el interés sobre el saldo, así que
    las cuotas bajan.
    """
    if monto <= 0:
        raise ErrorCredito("El monto del crédito debe ser mayor que cero.")
    if cuotas < 1:
        raise ErrorCredito("El crédito debe tener al menos una cuota.")
    if sistema not in SISTEMAS:
        raise ErrorCredito(f"Sistema de amortización desconocido '{sistema}'. "
                           f"Sistemas: {', '.join(SISTEMAS)}.")
    i = tasa_periodica
    fija = monto / cuotas if i == 0 else monto * i / (1 - (1 + i) ** -cuotas)
    tabla, saldo = [], monto
    for k in range(1, cuotas + 1):
        interes = saldo * i
        abono = fija - interes if sistema == "cuota_fija" else monto / cuotas
        tabla.append(Cuota(k, saldo, interes, abono, interes + abono, saldo - abono))
        saldo -= abono
    return tabla


# --------------------------------------------------------------------------- #
# Simulador de crédito: el análisis que ven el chat y el tablero
# --------------------------------------------------------------------------- #
# periodicidad de las cuotas → tipo de la tasa periódica que se cobra en cada una
PERIODICIDADES = {"mensual": "MV", "trimestral": "TV", "semestral": "SV", "anual": "EA"}
MAX_CUOTAS = 600                    # 50 años de cuotas mensuales
UNIDADES_PLAZO = ("años", "meses", "cuotas")
SUPUESTO_COSTOS = ("La cuota no incluye seguros, comisiones ni el 4 por mil (GMF): el costo "
                   "real del crédito puede ser mayor.")


def cuotas_del_plazo(plazo: float, unidad: str, periodicidad: str = "mensual") -> int:
    """Número de cuotas de un plazo en años, meses o cuotas, según cada cuánto se paga."""
    if unidad not in UNIDADES_PLAZO:
        raise ErrorCredito(f"Unidad de plazo desconocida '{unidad}'. Unidades: "
                           f"{', '.join(UNIDADES_PLAZO)}.")
    if periodicidad not in PERIODICIDADES:
        raise ErrorCredito(f"Periodicidad desconocida '{periodicidad}'. "
                           f"Periodicidades: {', '.join(PERIODICIDADES)}.")
    if plazo <= 0:
        raise ErrorCredito("El plazo debe ser mayor que cero.")
    por_anio = TIPOS[PERIODICIDADES[periodicidad]][1]
    cuotas = {"cuotas": plazo, "años": plazo * por_anio, "meses": plazo * por_anio / 12}[unidad]
    texto = f"{plazo:g}".replace(".", ",")
    if cuotas != int(cuotas):
        raise ErrorCredito(f"Un plazo de {texto} {unidad} no da un número entero de cuotas "
                           f"{periodicidad}es.")
    if cuotas > MAX_CUOTAS:
        raise ErrorCredito(f"El plazo es demasiado largo para simularlo (más de {MAX_CUOTAS} "
                           "cuotas).")
    return int(cuotas)


def _pesos(valor: float) -> str:
    return formatear(valor, "pesos")


def _en_millones(monto: float) -> str:
    """" (150 millones)" si el monto son millones exactos: el 7B repite el monto como lo escribió
    el usuario, y con "$ 150.000.000" solo, la cifra no estaba en el desplegable."""
    if monto < 1e6 or monto % 1e6:
        return ""
    return f" ({int(monto // 1e6):,} millones)".replace(",", ".")


def como_la_escribio(tasa: float) -> str:
    """La tasa del usuario sin ceros de más ("24 %", "1,5 %"): el 7B la repite así, y con
    "24,00 %" la cifra de la respuesta no estaría en el desplegable."""
    return f"{round(tasa * 100, 6):g}".replace(".", ",") + " %"


def simular_credito(monto: float, tasa: float, tipo: str, cuotas: int,
                    periodicidad: str = "mensual", sistema: str = "cuota_fija",
                    supuestos: list[str] | tuple[str, ...] = ()) -> ResultadoModulo:
    """
    Cuota, intereses y total de un crédito. La tasa (en decimales, con su tipo)
    se lleva a la del periodo de pago; los hallazgos dicen la efectiva anual y,
    si la tasa era nominal, que no es lo mismo (error típico del 7B).
    """
    if periodicidad not in PERIODICIDADES:
        raise ErrorCredito(f"Periodicidad desconocida '{periodicidad}'. "
                           f"Periodicidades: {', '.join(PERIODICIDADES)}.")
    periodo = PERIODICIDADES[periodicidad]
    i, ea = convertir(tasa, tipo, periodo), convertir(tasa, tipo, "EA")
    tabla = amortizacion(monto, i, cuotas, sistema)
    intereses = sum(c.interes for c in tabla)
    nombre, _, nominal, _ = TIPOS[tipo]
    m = TIPOS[periodo][1]

    hallazgos = []
    if tipo != "EA":
        hallazgos.append(f"La tasa de {como_la_escribio(tasa)} {nombre} equivale a "
                         f"{formatear(ea, 'tasa')} efectiva anual"
                         + (": la nominal no cuenta el interés sobre los intereses." if nominal
                            else "."))
    efectiva = como_la_escribio(tasa) if tipo == "EA" else formatear(ea, "tasa")
    tasa_texto = f"{efectiva} efectiva anual" + (
        "" if periodicidad == "anual" else f" ({formatear(i, 'tasa')} {periodicidad})")
    plazo = (f"{cuotas} cuotas {periodicidad}es" if cuotas > 1 else f"1 cuota {periodicidad}")
    base = f"Con una tasa de {tasa_texto}, un crédito de {_pesos(monto)}{_en_millones(monto)} a {plazo}"
    indicadores = [
        Indicador(clave="tasa_efectiva_anual", nombre="Tasa efectiva anual", valor=ea,
                  unidad="tasa", formula=f"(1 + i)^{m} − 1, con i la tasa {periodicidad}"),
        Indicador(clave="tasa_periodica", nombre=f"Tasa {periodicidad} equivalente", valor=i,
                  unidad="tasa", formula=f"(1 + tasa efectiva anual)^(1/{m}) − 1"),
    ]
    if sistema == "cuota_fija":
        hallazgos.append(f"{base} tiene una cuota fija de {_pesos(tabla[0].cuota)}.")
        indicadores.append(Indicador(clave="cuota", nombre="Cuota fija", valor=tabla[0].cuota,
                                     unidad="pesos", formula="monto × i / (1 − (1 + i)^−n)"))
    else:
        hallazgos.append(
            f"{base} con abono constante a capital de {_pesos(tabla[0].abono)} por cuota: la "
            f"primera cuota es de {_pesos(tabla[0].cuota)} y la última de "
            f"{_pesos(tabla[-1].cuota)}. Las cuotas bajan porque el interés se cobra sobre un "
            "saldo cada vez menor.")
        indicadores += [
            Indicador(clave="abono_capital", nombre="Abono a capital por cuota",
                      valor=tabla[0].abono, unidad="pesos", formula="monto / n"),
            Indicador(clave="primera_cuota", nombre="Primera cuota", valor=tabla[0].cuota,
                      unidad="pesos", formula="abono + monto × i"),
            Indicador(clave="ultima_cuota", nombre="Última cuota", valor=tabla[-1].cuota,
                      unidad="pesos", formula="abono + último saldo × i"),
        ]
    hallazgos.append(f"En total pagaría {_pesos(intereses)} de intereses, el "
                     f"{formatear(intereses / monto, 'proporcion')} del monto prestado.")
    indicadores += [
        Indicador(clave="intereses_totales", nombre="Intereses totales", valor=intereses,
                  unidad="pesos", formula="suma de los intereses de todas las cuotas"),
        Indicador(clave="total_pagado", nombre="Total pagado", valor=monto + intereses,
                  unidad="pesos", formula="monto + intereses totales"),
        Indicador(clave="proporcion_intereses", nombre="Intereses sobre el monto prestado",
                  valor=intereses / monto, unidad="proporcion",
                  formula="intereses totales / monto"),
    ]
    return ResultadoModulo(modulo="proyectos", analisis="credito", indicadores=indicadores,
                           hallazgos=hallazgos, supuestos=[*supuestos, SUPUESTO_COSTOS])


# --------------------------------------------------------------------------- #
# Conversor de tasas
# --------------------------------------------------------------------------- #
def _formula(desde: str, hacia: str) -> str:
    """Los pasos de la conversión, en el orden en que se hacen."""
    _, m1, nominal1, anticipada1 = TIPOS[desde]
    _, m2, nominal2, anticipada2 = TIPOS[hacia]
    pasos = [f"periódica = nominal / {m1}"] if nominal1 else []
    if anticipada1:
        pasos.append("vencida = anticipada / (1 − anticipada)")
    pasos.append(f"equivalente = (1 + i)^({m1}/{m2}) − 1")
    if anticipada2:
        pasos.append("anticipada = vencida / (1 + vencida)")
    if nominal2:
        pasos.append(f"nominal = periódica × {m2}")
    return "; ".join(pasos)


def convertir_tasa(tasa: float, desde: str, hacia: str,
                   supuestos: list[str] | tuple[str, ...] = ()) -> ResultadoModulo:
    """Una tasa en otro tipo, con la diferencia de sentido dicha en un hallazgo."""
    valor = convertir(tasa, desde, hacia)
    nombre1, _, nominal1, anticipada1 = TIPOS[desde]
    nombre2, _, nominal2, anticipada2 = TIPOS[hacia]
    hallazgos = [f"Una tasa de {como_la_escribio(tasa)} {nombre1} equivale a "
                 f"{formatear(valor, 'tasa')} {nombre2}."]
    if nominal1 != nominal2:
        hallazgos.append("La diferencia es que la nominal no cuenta el interés sobre los "
                         "intereses; la efectiva sí.")
    if anticipada1 != anticipada2:
        hallazgos.append("En la anticipada los intereses se pagan al inicio del periodo; por eso "
                         "equivale a una tasa vencida mayor.")
    # Neutral: el 7B supuso que la empresa "ganaría" con la tasa, y la pregunta no lo dice
    hallazgos.append("Es la misma tasa dicha de otra forma: con cualquiera de las dos se paga (o se "
                     "recibe) lo mismo en el año.")
    return ResultadoModulo(
        modulo="proyectos", analisis="conversion_tasa",
        indicadores=[Indicador(clave="tasa_convertida", nombre=f"Tasa {nombre2}", valor=valor,
                               unidad="tasa", formula=_formula(desde, hacia))],
        hallazgos=hallazgos, supuestos=list(supuestos))
