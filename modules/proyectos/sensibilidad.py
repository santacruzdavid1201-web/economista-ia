"""
¿Qué tan frágil es el proyecto? Cuánto se mueve el VPN si cada variable sale
distinta de lo previsto (tornado) y hasta dónde puede moverse antes de que el
proyecto deje de crear valor (valor crítico).

Decisiones (SPEC-sensibilidad-proyecto.md, aprobadas el 15/10/2026):
- Una variable a la vez, lo demás igual; cambios relativos de ±10 % y ±20 %.
- El valor crítico se busca por bisección entre −99 % y +200 %; la tasa crítica
  es la TIR. Tasas y costos variables se dicen en nivel ("sube a 11,11 %"): un
  cambio relativo de una tasa confunde.
- Pocas cifras para el chat (el VPN base y los hallazgos); la tabla completa va
  aparte, para el tablero. Los VPN se dicen en palabras: el 7B pierde el signo.
- Con una tasa real o el WACC se usan los flujos en pesos de hoy y la tasa se dice
  "real". Sigue siendo "la tasa de oportunidad": el WACC es el costo de
  oportunidad del capital (lo que se ganaría en otra inversión de igual riesgo).
"""
from __future__ import annotations

from typing import NamedTuple

from modules.base import Indicador, ResultadoModulo, formatear
from modules.proyectos.flujo import Proyecto, Senda, flujo_caja
from modules.proyectos.matematica_financiera import biseccion, como_la_escribio, vpn

CAMBIOS = (-0.2, -0.1, 0.1, 0.2)
RANGO = (0.01, 3.0)                    # factor sobre el valor actual: de −99 % a +200 %
SUPUESTO = ("Cada variable se mueve sola, con todo lo demás igual: el efecto de que varias "
            "salgan distintas a la vez no se mide aquí.")


class Variable(NamedTuple):
    clave: str            # campo del proyecto, o "tasa"
    nombre: str           # en la tabla
    sujeto: str           # en las frases: "los ingresos"
    plural: bool
    en_nivel: bool        # el valor crítico se dice como nivel ("sube a 32,1 %")


VARIABLES = (
    Variable("ingresos", "Ingresos", "los ingresos", True, False),
    Variable("costos_variables", "Costos variables", "los costos variables", True, True),
    Variable("costos_fijos", "Costos fijos", "los costos fijos", True, False),
    Variable("inversion", "Inversión", "la inversión", False, False),
    Variable("tasa", "Tasa de oportunidad", "la tasa de oportunidad", False, True),
)
POR_CLAVE = {v.clave: v for v in VARIABLES}
TASA_REAL = Variable("tasa", "Tasa de oportunidad real", "la tasa de oportunidad real", False, True)


def _variable(clave: str, real: bool) -> Variable:
    return TASA_REAL if real and clave == "tasa" else POR_CLAVE[clave]


class FilaTornado(NamedTuple):
    variable: str
    nombre: str
    actual: float                 # valor de la variable en el proyecto
    vpn: dict[float, float]       # cambio relativo → VPN
    critico: float | None         # cambio relativo que deja el VPN en cero
    valor_critico: float | None   # la variable en ese punto

    @property
    def rango(self) -> float:
        return max(self.vpn.values()) - min(self.vpn.values())


class Sensibilidad(NamedTuple):
    vpn_base: float
    filas: list[FilaTornado]      # de la variable que más mueve el VPN a la que menos
    resultado: ResultadoModulo
    real: bool = False            # tasa real o WACC: flujos en pesos de hoy


def vpn_con(proyecto: Proyecto, senda: Senda, tasa: float, variable: str, factor: float,
            real: bool = False) -> float:
    """VPN con una variable multiplicada por `factor` y todo lo demás igual. `real`: la tasa
    es real y descuenta los flujos en pesos de hoy."""
    if variable == "tasa":
        tasa *= factor
    else:
        proyecto = proyecto.model_copy(update={variable: getattr(proyecto, variable) * factor})
    f = flujo_caja(proyecto, senda)
    return vpn(tasa, [fila.flujo_libre for fila in (f.real if real else f.corriente)])


def deja(valor: float) -> str:
    """El VPN en palabras, con la cifra en positivo."""
    return (f"dejaría {formatear(abs(valor), 'pesos')} "
            + ("más" if valor >= 0 else "menos") + " que la alternativa")


def _nivel(variable: Variable, valor: float) -> str:
    unidad = "de los ingresos" if variable.clave == "costos_variables" else ""
    return f"{formatear(valor, 'tasa')} {unidad}".strip()


def movimiento(variable: Variable, cambio: float, valor: float | None = None,
               exacto: bool = False) -> str:
    """'los ingresos caen 3,1 %', 'la tasa de oportunidad sube a 11,11 %'. `exacto`: el cambio
    como lo escribió el usuario ("10 %"), que es como el 7B lo repite."""
    verbo = ("suben" if variable.plural else "sube") if cambio > 0 else \
        ("caen" if variable.plural else "baja")
    if variable.en_nivel and valor is not None:
        return f"{variable.sujeto} {verbo} a {_nivel(variable, valor)}"
    texto = como_la_escribio(abs(cambio)) if exacto else formatear(abs(cambio), "proporcion")
    return f"{variable.sujeto} {verbo} {texto}"


def sensibilidad(proyecto: Proyecto, senda: Senda, tasa: float, real: bool = False) -> Sensibilidad:
    base = vpn_con(proyecto, senda, tasa, "tasa", 1, real)
    filas = []
    for v in (_variable(clave, real) for clave in POR_CLAVE):
        actual = tasa if v.clave == "tasa" else getattr(proyecto, v.clave)

        def f(factor: float, clave: str = v.clave) -> float:
            return vpn_con(proyecto, senda, tasa, clave, factor, real)

        cruza = f(RANGO[0]) * f(RANGO[1]) <= 0
        factor = biseccion(f, *RANGO) if cruza else None
        filas.append(FilaTornado(v.clave, v.nombre, actual, {c: f(1 + c) for c in CAMBIOS},
                                 None if factor is None else factor - 1,
                                 None if factor is None else actual * factor))
    filas.sort(key=lambda fila: fila.rango, reverse=True)

    mayor = filas[0]
    variable = _variable(mayor.variable, real)
    hallazgos = [f"Lo que más mueve el VPN {'son' if variable.plural else 'es'} {variable.sujeto}: "
                 f"con un 10 % menos, el proyecto {deja(mayor.vpn[-0.1])}; con un 10 % más, "
                 f"{deja(mayor.vpn[0.1]).removesuffix(' que la alternativa')}."]
    cercanas = sorted((fila for fila in filas if fila.critico is not None),
                      key=lambda fila: abs(fila.critico))[:2]
    if cercanas:
        partes = [movimiento(_variable(c.variable, real), c.critico, c.valor_critico)
                  for c in cercanas]
        if base >= 0:
            hallazgos.append("El proyecto deja de crear valor si " + " o si ".join(partes)
                             + (", cada una por separado." if len(partes) > 1 else "."))
        else:
            mejoras = [f"{_variable(c.variable, real).sujeto} "
                       f"{'tendrían' if _variable(c.variable, real).plural else 'tendría'} que "
                       f"{'subir' if c.critico > 0 else 'bajar'} "
                       + (f"a {_nivel(_variable(c.variable, real), c.valor_critico)}"
                          if _variable(c.variable, real).en_nivel
                          else formatear(abs(c.critico), "proporcion"))
                       for c in cercanas]
            hallazgos.append("Para que el proyecto cree valor, " + ", o ".join(mejoras)
                             + (", cada una por separado." if len(mejoras) > 1 else "."))
    resultado = ResultadoModulo(
        modulo="proyectos", analisis="sensibilidad",
        indicadores=[Indicador(clave="vpn", nombre="Valor presente neto (VPN)", valor=base,
                               unidad="pesos", formula="VPN con los datos del proyecto, sin "
                                                       "cambios")],
        hallazgos=hallazgos, supuestos=[SUPUESTO])
    return Sensibilidad(base, filas, resultado, real)


def texto_critico(fila: FilaTornado, real: bool = False) -> str | None:
    """'los ingresos caen 3,1 % (a $ 58.157.973)'; None si no llega a cero en el rango."""
    if fila.critico is None:
        return None
    variable = _variable(fila.variable, real)
    texto = movimiento(variable, fila.critico, fila.valor_critico)
    return texto if variable.en_nivel else \
        f"{texto} (a {formatear(fila.valor_critico, 'pesos')})"


def critico_de(s: Sensibilidad, variable: str) -> str | None:
    """El valor crítico de un dato, en una frase ("¿hasta cuánto pueden caer las ventas?")."""
    fila = next((f for f in s.filas if f.variable == variable), None)
    texto = texto_critico(fila, s.real) if fila else None
    if texto is None:
        return None
    efecto = "deja de crear valor" if s.vpn_base >= 0 else "pasa a crear valor"
    return f"El proyecto {efecto} si {texto}, con todo lo demás igual."


def escenario(proyecto: Proyecto, senda: Senda, tasa: float, variable: str,
              cambio: float, real: bool = False) -> ResultadoModulo:
    """Un cambio puntual ("¿y si vendo 10 % menos?"), dicho en palabras."""
    v = _variable(variable, real)
    base = vpn_con(proyecto, senda, tasa, "tasa", 1, real)
    nuevo = vpn_con(proyecto, senda, tasa, variable, 1 + cambio, real)
    actual = tasa if variable == "tasa" else getattr(proyecto, variable)
    # Primero el estado actual, en su propia frase: con "el proyecto sigue sin crear valor" el 7B
    # concluyó que "dejaría de crear valor", como si hoy lo creara
    if base >= 0:
        actual_texto = f"crea valor: deja {formatear(base, 'pesos')} más"
        estado = "seguiría creando valor" if nuevo >= 0 else "dejaría de crear valor"
    else:
        actual_texto = f"no crea valor: deja {formatear(-base, 'pesos')} menos"
        estado = "pasaría a crear valor" if nuevo >= 0 else "seguiría sin crear valor"
    cambio_texto = movimiento(v, cambio, actual * (1 + cambio), exacto=True)
    return ResultadoModulo(
        modulo="proyectos", analisis="escenario",
        indicadores=[
            Indicador(clave="vpn", nombre="Valor presente neto (VPN)", valor=base, unidad="pesos",
                      formula="VPN con los datos del proyecto, sin cambios"),
            Indicador(clave="vpn_escenario", nombre=f"VPN si {cambio_texto}", valor=nuevo,
                      unidad="pesos", formula="VPN con ese cambio y todo lo demás igual")],
        hallazgos=[f"Con los datos actuales, el proyecto {actual_texto} que la alternativa.",
                   f"Si {cambio_texto}, {estado}: {deja(nuevo)}."],
        supuestos=[SUPUESTO])
