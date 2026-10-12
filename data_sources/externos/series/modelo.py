"""
Serie de tiempo externa en formato común (IPC, tasas, MMH...).

Ningún análisis sabe de dónde vino la serie: recibe una `Serie` con su fuente,
unidad, geografía y fecha de consulta. Las operaciones son puras.
"""
from __future__ import annotations

from bisect import bisect_right
from datetime import date

from pydantic import BaseModel, Field, field_validator


class Serie(BaseModel):
    clave: str                    # "ipc_nacional", "ipc_pasto"
    nombre: str
    fuente: str                   # texto para `fuentes` del ResultadoModulo
    unidad: str                   # "Indice, base dic/2018=100"
    frecuencia: str               # "mensual", "diaria"
    geografia: str                # "nacional" o la ciudad
    consultada: date              # fecha de descarga
    observaciones: list[tuple[date, float]]
    # Los llena el catálogo al entregar la serie (nunca se guardan en caché):
    # p. ej. "se usó el IPC nacional porque no hay IPC de Ipiales".
    supuestos: list[str] = Field(default_factory=list, exclude=True)
    advertencias: list[str] = Field(default_factory=list, exclude=True)

    @field_validator("observaciones")
    @classmethod
    def _ordenar(cls, obs: list[tuple[date, float]]) -> list[tuple[date, float]]:
        """Ordenadas por fecha; ante fechas repetidas queda la última."""
        return sorted(dict(obs).items())

    def promedio_mensual(self, desde: date, hasta: date) -> float | None:
        """
        Promedio de los meses entre `desde` y `hasta` (incluidos, por año y mes).
        None si falta alguno: un promedio con huecos no es el del periodo.
        """
        por_mes = {(f.year, f.month): v for f, v in self.observaciones}
        meses = [(a, m) for a in range(desde.year, hasta.year + 1) for m in range(1, 13)
                 if (desde.year, desde.month) <= (a, m) <= (hasta.year, hasta.month)]
        if not meses or any(m not in por_mes for m in meses):
            return None
        return sum(por_mes[m] for m in meses) / len(meses)

    def valor_al(self, fecha: date) -> float | None:
        """Último dato en o antes de `fecha` (series diarias con días sin dato); None si
        la serie empieza después."""
        k = bisect_right(self.observaciones, fecha, key=lambda o: o[0])
        return self.observaciones[k - 1][1] if k else None

    def fin_de_mes(self) -> list[tuple[date, float]]:
        """Último dato de cada mes, para comparar a 12 meses una serie diaria."""
        por_mes = {(f.year, f.month): (f, v) for f, v in self.observaciones}
        return list(por_mes.values())
