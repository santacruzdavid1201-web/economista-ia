"""
Contrato común de salida para todos los módulos de cálculo.

Cada módulo devuelve un `ResultadoModulo`. El LLM nunca calcula: recibe este
objeto y lo redacta. Por eso cada indicador viaja con su nombre, unidad y
fórmula, y cada resultado con sus supuestos, fuentes y advertencias.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

# "proporcion" se guarda como fracción (0.42); la interfaz la muestra como 42 %.
Unidad = Literal["veces", "proporcion", "dias", "pesos"]


class Indicador(BaseModel):
    clave: str            # identificador estable, p. ej. "razon_corriente"
    nombre: str           # nombre legible, p. ej. "Razón corriente"
    valor: float | None   # None cuando no se puede calcular (ver advertencias)
    unidad: Unidad
    formula: str


class ResultadoModulo(BaseModel):
    modulo: str                          # "balance", "proyectos", ...
    analisis: str                        # "liquidez", "endeudamiento", ...
    fecha_corte: date | None = None
    indicadores: list[Indicador] = Field(default_factory=list)
    supuestos: list[str] = Field(default_factory=list)
    fuentes: list[str] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)

    def valor(self, clave: str) -> float | None:
        for ind in self.indicadores:
            if ind.clave == clave:
                return ind.valor
        raise KeyError(f"El resultado no tiene el indicador '{clave}'.")


def division_segura(numerador: float, denominador: float) -> float | None:
    """Devuelve None en vez de fallar cuando el denominador es cero."""
    if denominador == 0:
        return None
    return numerador / denominador
