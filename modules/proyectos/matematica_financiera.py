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
