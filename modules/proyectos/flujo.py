"""
Flujo de caja libre del proyecto, año por año.

Decisiones (SPEC-flujo-proyecto.md, aprobadas el 15/10/2026):
- Sin la financiación: intereses y cuotas entran en la tasa de descuento.
- Precios de hoy por fuera, inflación por dentro: el flujo se arma en pesos
  corrientes (así se pagan los impuestos) y se devuelve en pesos de hoy. La
  inflación le quita valor real al ahorro de impuestos de la depreciación, y el
  capital de trabajo crece con los precios aunque las ventas reales no crezcan.
- Inflación: el pronóstico del último Informe de Política Monetaria del BanRep
  y la meta después de su horizonte, o una tasa fija que escriba el usuario.
"""
from __future__ import annotations

from datetime import date
from typing import NamedTuple

from pydantic import BaseModel, Field, ValidationError

from modules.base import ResultadoModulo, formatear


class Senda(NamedTuple):
    tasas: list[float]           # inflación de los años 1 a n del proyecto (fracción)
    supuestos: list[str]


def _pct(valor: float) -> str:
    return formatear(valor, "proporcion")          # "4,3 %": como la publica el BanRep


def senda_inflacion(hoy: date, horizonte: int, pronostico: dict[int, float] | None,
                    meta: float, fija: float | None = None) -> Senda:
    """
    Inflación de cada año del proyecto. El año t se asocia al año calendario
    actual + t (supuesto): el pronóstico del año en curso no se usa.
    """
    if fija is not None:
        return Senda([fija] * horizonte,
                     [f"Se usó una inflación fija de {_pct(fija)} al año, escrita por el usuario."])
    anios = [hoy.year + t for t in range(1, horizonte + 1)]
    supuestos = [f"Cada año del proyecto se asocia a un año calendario: el año 1 es {anios[0]}."]
    if pronostico is None:
        supuestos.append(f"No hay pronóstico del BanRep cargado: se usó la meta de inflación de "
                         f"{_pct(meta)} para todos los años.")
        return Senda([meta] * horizonte, supuestos)
    return Senda([pronostico.get(a, meta) for a in anios], supuestos)


# --------------------------------------------------------------------------- #
# Proyecto: lo que escribe el gerente, a precios de hoy (porcentajes en fracción)
# --------------------------------------------------------------------------- #
MENSAJES = {
    "nombre": "El nombre del proyecto debe tener máximo 120 caracteres.",
    "inversion": "La inversión debe ser mayor que cero.",
    "vida_util": "La vida útil debe ser un número entero de años entre 1 y 50.",
    "horizonte": "El horizonte debe estar entre 1 y 30 años.",
    "ingresos": "Los ingresos no pueden ser negativos.",
    "crecimiento_real": "El crecimiento real debe estar entre −50 % y 100 % al año.",
    "costos_variables": "Los costos variables deben estar entre 0 % y 100 % de los ingresos.",
    "costos_fijos": "Los costos fijos no pueden ser negativos.",
    "capital_trabajo": "El capital de trabajo debe estar entre 0 % y 100 % de los ingresos.",
    "tarifa_renta": "La tarifa de renta debe estar entre 0 % y 100 %.",
    "salvamento": "El valor de salvamento no puede ser negativo.",
}


class ErrorProyecto(ValueError):
    """Datos del proyecto fuera de rango; `mensajes` dice cuáles, uno por campo."""

    def __init__(self, mensajes: list[str]):
        super().__init__(" ".join(mensajes))
        self.mensajes = mensajes


class Proyecto(BaseModel):
    nombre: str = Field(default="Su proyecto", max_length=120)
    inversion: float = Field(gt=0)                     # año 0, en activos depreciables
    vida_util: int = Field(ge=1, le=50)
    horizonte: int = Field(ge=1, le=30)
    ingresos: float = Field(ge=0)                      # adicionales del año 1, precios de hoy
    crecimiento_real: float = Field(default=0, ge=-0.5, le=1)
    costos_variables: float = Field(ge=0, le=1)        # fracción de los ingresos
    costos_fijos: float = Field(ge=0)                  # adicionales por año, precios de hoy
    capital_trabajo: float = Field(default=0, ge=0, le=1)
    tarifa_renta: float = Field(default=0.35, ge=0, le=1)
    salvamento: float | None = Field(default=None, ge=0)   # de mercado, precios de hoy


def crear_proyecto(**datos) -> Proyecto:
    """El proyecto validado, o ErrorProyecto con un mensaje en español por campo."""
    try:
        return Proyecto(**datos)
    except ValidationError as e:
        campos = dict.fromkeys(str(err["loc"][0]) for err in e.errors())
        mensajes = [MENSAJES.get(c, f"El dato «{c}» no es válido.") for c in campos]
        raise ErrorProyecto(mensajes) from None


# --------------------------------------------------------------------------- #
# Flujo de caja libre
# --------------------------------------------------------------------------- #
SIN_FINANCIACION = ("Es el flujo de caja libre del proyecto, sin la financiación: los intereses "
                    "y las cuotas del crédito entran en la tasa de descuento.")
PRECIOS_DE_HOY = ("Ingresos y costos a precios de hoy; los impuestos se calculan en pesos "
                  "corrientes con la inflación esperada y el flujo se muestra en pesos de hoy.")


class Fila(NamedTuple):
    anio: int
    ingresos: float
    costos_variables: float
    costos_fijos: float
    depreciacion: float
    utilidad_operativa: float
    impuesto: float               # negativo si hay pérdida (ahorro de impuestos)
    inversion: float              # positivo: sale en el año 0
    capital_trabajo: float        # con signo: negativo al invertir, positivo al recuperar
    salvamento: float             # neto del impuesto sobre la ganancia
    flujo_libre: float

    def deflactada(self, indice: float) -> Fila:
        return Fila(self.anio, *(v / indice for v in self[1:]))


class Flujo(NamedTuple):
    corriente: list[Fila]         # pesos corrientes de cada año
    real: list[Fila]              # pesos de hoy
    inflacion: list[float]        # la senda usada, años 1 a n
    resultado: ResultadoModulo    # hallazgos y supuestos


def flujo_caja(p: Proyecto, senda: Senda) -> Flujo:
    """Flujo año por año en pesos corrientes y en pesos de hoy (SPEC-flujo-proyecto.md)."""
    n = p.horizonte
    indice = [1.0]
    for pi in senda.tasas[:n]:
        indice.append(indice[-1] * (1 + pi))
    ingresos = [0.0] + [p.ingresos * (1 + p.crecimiento_real) ** (t - 1) * indice[t]
                        for t in range(1, n + 1)]
    # Capital de trabajo de cada año, invertido al inicio del año; después de n, nada
    ct = [p.capital_trabajo * i for i in ingresos] + [0.0]
    depreciacion = p.inversion / p.vida_util
    libros = max(p.inversion - depreciacion * min(n, p.vida_util), 0.0)

    filas = [Fila(0, 0, 0, 0, 0, 0, 0, p.inversion, -ct[1], 0, -p.inversion - ct[1])]
    perdidas = []
    for t in range(1, n + 1):
        d = depreciacion if t <= p.vida_util else 0.0
        cv, cf = p.costos_variables * ingresos[t], p.costos_fijos * indice[t]
        utilidad = ingresos[t] - cv - cf - d
        impuesto = p.tarifa_renta * utilidad
        capital = -(ct[t + 1] - ct[t])                 # en n se recupera todo
        salvamento = 0.0
        if t == n:
            valor = libros if p.salvamento is None else p.salvamento * indice[n]
            salvamento = valor - p.tarifa_renta * (valor - libros)
        if utilidad < 0:
            perdidas.append(t)
        filas.append(Fila(t, ingresos[t], cv, cf, d, utilidad, impuesto, 0.0, capital, salvamento,
                          utilidad - impuesto + d + capital + salvamento))

    supuestos = [SIN_FINANCIACION, PRECIOS_DE_HOY, *senda.supuestos]
    if perdidas:
        anios = ", ".join(map(str, perdidas))
        supuestos.append(f"En {'el año' if len(perdidas) == 1 else 'los años'} {anios} el proyecto "
                         "da pérdida operativa: se supuso que la empresa tiene utilidades contra las "
                         "cuales descontarla, por eso el impuesto sale negativo. Si no las tiene, el "
                         "proyecto vale menos de lo que muestra el flujo.")
    if p.salvamento is None and libros > 0:
        supuestos.append(f"Al final del horizonte quedan {formatear(libros / indice[n], 'pesos')} "
                         "en libros por depreciar (en pesos de hoy): entran como salvamento, sin "
                         "impuesto.")
    if p.salvamento is not None:
        supuestos.append("La diferencia entre el valor de salvamento y el valor en libros paga la "
                         "tarifa de renta. Es una aproximación: la venta de activos puede tributar "
                         "como ganancia ocasional; consulte a su contador.")

    hallazgos = []
    con = sum(p.tarifa_renta * f.depreciacion / indice[f.anio] for f in filas)
    sin = sum(p.tarifa_renta * f.depreciacion for f in filas)
    if sin > 0 and con < sin - 0.5:
        hallazgos.append(f"El ahorro de impuestos de la depreciación suma {formatear(con, 'pesos')} "
                         f"en pesos de hoy, frente a {formatear(sin, 'pesos')} sin inflación: la "
                         "deducción es fija en pesos corrientes y la inflación le quita valor.")
    return Flujo(filas, [f.deflactada(indice[f.anio]) for f in filas], list(senda.tasas[:n]),
                 ResultadoModulo(modulo="proyectos", analisis="flujo", hallazgos=hallazgos,
                                 supuestos=supuestos))
