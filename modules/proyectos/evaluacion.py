"""
¿Me conviene el proyecto? VPN, TIR, TIRM, recuperación descontada e índice de
rentabilidad del flujo de caja libre, con la tasa de oportunidad del usuario.

Decisiones (SPEC-evaluacion-proyecto.md, aprobadas el 15/10/2026):
- La tasa es nominal, efectiva anual (como se cotizan las tasas en Colombia). El
  VPN descuenta los flujos en pesos corrientes con ella: es la misma cifra que
  descontar los flujos en pesos de hoy con la tasa real de cada año.
- La TIR es nominal, para compararla con la tasa que escribió el usuario.
- Con una tasa real o con el WACC (SPEC-costo-capital.md, 16/10/2026) se descuentan
  los flujos en pesos de hoy y la TIR sale real: flujos y tasa en la misma moneda.
  Con el WACC, el proyecto se compara con lo que cuesta su capital.
- Manda el VPN. "Crea valor" es un criterio de decisión, no una recomendación,
  y el hallazgo lo dice: el 7B tiende a pasar de "crea valor" a "le conviene".
"""
from __future__ import annotations

from typing import NamedTuple

from modules.base import Indicador, ResultadoModulo, formatear
from modules.proyectos.flujo import Flujo
from modules.proyectos.matematica_financiera import (
    como_la_escribio,
    indice_rentabilidad,
    recuperacion_descontada,
    tir,
    tirm,
    vpn,
)

CRITERIO = ("Crear valor es un criterio de decisión, no una recomendación: falta mirar el riesgo "
            "del proyecto y la caja de la empresa.")
SUPUESTO_WACC = ("El WACC es la tasa adecuada si el proyecto tiene el mismo riesgo del negocio de "
                 "siempre y se financia con la misma mezcla de deuda y patrimonio de la empresa.")


class Tasa(NamedTuple):
    """Con qué flujos va la tasa de descuento y cómo se nombra en los hallazgos."""
    real: bool                    # descuenta los flujos en pesos de hoy; la TIR sale real
    con: str                      # "Con {con}, el proyecto crea valor…"
    frente: str                   # contra qué crea valor el VPN
    nombre: str                   # con qué se compara la TIR
    rinde: str                    # "el proyecto rinde más {rinde}"
    costo: str                    # "Recupera la inversión, {costo}, en…"
    reinversion: str              # a qué tasa reinvierte la TIRM


ALTERNATIVA = "que invertir esa plata en la alternativa"
TASAS = {
    "nominal": Tasa(False, "una tasa de oportunidad de {} efectiva anual", ALTERNATIVA,
                    "la tasa de oportunidad de {}", "que la alternativa",
                    "con su costo de oportunidad", "la tasa de oportunidad"),
    "real": Tasa(True, "una tasa de oportunidad de {} real", ALTERNATIVA,
                 "la tasa de oportunidad de {} real", "que la alternativa",
                 "con su costo de oportunidad", "la tasa de oportunidad"),
    "wacc": Tasa(True, "el costo de capital de la empresa (WACC) de {} real",
                 "de lo que exigen los dueños y los bancos que lo financian", "el WACC de {}",
                 "de lo que cuesta su capital", "con el costo de su capital", "el WACC"),
}


def evaluar(flujo: Flujo, tasa: float, tipo: str = "nominal") -> ResultadoModulo:
    """
    Indicadores y hallazgos del proyecto con la tasa de descuento `tasa` (fracción),
    de tipo "nominal" (efectiva anual), "real" o "wacc" (el WACC real de la empresa).
    """
    t = TASAS[tipo]
    flujos = [f.flujo_libre for f in (flujo.real if t.real else flujo.corriente)]
    n = len(flujos) - 1
    valor = vpn(tasa, flujos)
    la_tir, avisos = tir(flujos)
    recuperacion = recuperacion_descontada(tasa, flujos)
    indice = indice_rentabilidad(tasa, flujos)
    escrita = como_la_escribio(tasa)
    la_tir_es = "La TIR real es" if t.real else "La TIR es"

    # El VPN en palabras y con la cifra en positivo: el 7B pierde el signo de "$ -4.174.372"
    hallazgos = [
        f"Con {t.con.format(escrita)}, el proyecto "
        + (f"crea valor: deja {formatear(valor, 'pesos')} más" if valor >= 0
           else f"no crea valor: deja {formatear(-valor, 'pesos')} menos")
        + f", en pesos de hoy, {t.frente}."]
    # "No crea valor" no es "no rinde": el 7B escribió "no es rentable en términos absolutos"
    # con una TIR de 13,75 %. La distinción va aquí, en palabras.
    if la_tir is not None and la_tir < 0:
        hallazgos.append(f"{la_tir_es} {formatear(la_tir, 'tasa')}: el proyecto no devuelve ni "
                         "siquiera la inversión.")
    elif la_tir is not None:
        nombre = t.nombre.format(escrita)
        hallazgos.append(
            f"{la_tir_es} {formatear(la_tir, 'tasa')}, "
            + (f"mayor que {nombre}: el proyecto rinde más {t.rinde}." if la_tir > tasa else
               f"menor que {nombre}: el proyecto rinde, pero menos {t.rinde}."))
    # El 7B leyó un índice de 0,97 como "sugiere rendimiento": menos de uno es devolver menos
    if indice is not None:
        hallazgos.append(f"Devuelve {formatear(indice, 'veces').removesuffix(' veces')} pesos de "
                         "hoy por cada peso invertido (índice de rentabilidad): "
                         + ("más de uno, por eso crea valor." if indice >= 1 else
                            "menos de uno, por eso no crea valor."))
    hallazgos.append(
        f"Recupera la inversión, {t.costo}, en {formatear(recuperacion, 'anios')} de {n}."
        if recuperacion is not None else
        f"No recupera la inversión, {t.costo}, dentro de los {n} años del horizonte.")
    hallazgos.append(CRITERIO)

    indicadores = [
        Indicador(clave="vpn", nombre="Valor presente neto (VPN)", valor=valor, unidad="pesos",
                  formula="Σ flujo de caja libre_t / (1 + tasa de oportunidad)^t, en pesos de hoy"),
        Indicador(clave="tir", nombre=f"Tasa interna de retorno (TIR{' real' if t.real else ''})",
                  valor=la_tir, unidad="tasa",
                  formula="la tasa con la que el VPN es cero " + (
                      "(real, con los flujos en pesos de hoy, comparable con "
                      f"{t.reinversion})" if t.real else
                      "(nominal, efectiva anual, comparable con la tasa de oportunidad)")),
        Indicador(clave="tirm", nombre="TIR modificada (TIRM)", valor=tirm(tasa, flujos),
                  unidad="tasa", formula="(valor futuro de los flujos positivos / valor presente "
                                         f"de los negativos)^(1/n) − 1, a {t.reinversion}"),
        Indicador(clave="recuperacion", nombre="Recuperación descontada", valor=recuperacion,
                  unidad="anios", formula="años hasta que el flujo descontado acumulado llega a "
                                          "cero"),
        Indicador(clave="indice_rentabilidad", nombre="Índice de rentabilidad",
                  valor=indice, unidad="veces",
                  formula="valor presente de los flujos desde el año 1 / inversión del año 0"),
    ]
    return ResultadoModulo(modulo="proyectos", analisis="evaluacion", indicadores=indicadores,
                           hallazgos=hallazgos, advertencias=avisos,
                           supuestos=[f"La TIRM supone que los flujos positivos se reinvierten a "
                                      f"{t.reinversion}, y no a la TIR.",
                                      *([SUPUESTO_WACC] if tipo == "wacc" else []),
                                      *flujo.resultado.supuestos])
