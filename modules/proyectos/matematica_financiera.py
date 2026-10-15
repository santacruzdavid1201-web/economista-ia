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

from modules.base import formatear

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
