"""
¿Me conviene el proyecto? VPN, TIR, TIRM, recuperación descontada e índice de
rentabilidad del flujo de caja libre, con la tasa de oportunidad del usuario.

Decisiones (SPEC-evaluacion-proyecto.md, aprobadas el 15/10/2026):
- La tasa es nominal, efectiva anual (como se cotizan las tasas en Colombia). El
  VPN descuenta los flujos en pesos corrientes con ella: es la misma cifra que
  descontar los flujos en pesos de hoy con la tasa real de cada año.
- La TIR es nominal, para compararla con la tasa que escribió el usuario.
- Manda el VPN. "Crea valor" es un criterio de decisión, no una recomendación,
  y el hallazgo lo dice: el 7B tiende a pasar de "crea valor" a "le conviene".
"""
from __future__ import annotations

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
SUPUESTO_TIRM = ("La TIRM supone que los flujos positivos se reinvierten a la tasa de oportunidad, "
                 "y no a la TIR.")


def evaluar(flujo: Flujo, tasa: float) -> ResultadoModulo:
    """Indicadores y hallazgos del proyecto con la tasa de oportunidad `tasa` (fracción)."""
    flujos = [f.flujo_libre for f in flujo.corriente]
    n = len(flujos) - 1
    valor = vpn(tasa, flujos)
    la_tir, avisos = tir(flujos)
    recuperacion = recuperacion_descontada(tasa, flujos)
    escrita = como_la_escribio(tasa)

    # El VPN en palabras y con la cifra en positivo: el 7B pierde el signo de "$ -4.174.372"
    hallazgos = [
        f"Con una tasa de oportunidad de {escrita} efectiva anual, el proyecto "
        + (f"crea valor: deja {formatear(valor, 'pesos')} más" if valor >= 0
           else f"no crea valor: deja {formatear(-valor, 'pesos')} menos")
        + ", en pesos de hoy, que invertir esa plata en la alternativa."]
    if la_tir is not None:
        hallazgos.append(f"La TIR es {formatear(la_tir, 'tasa')}, "
                         f"{'mayor' if la_tir > tasa else 'menor'} que la tasa de oportunidad de "
                         f"{escrita}.")
    hallazgos.append(
        f"Recupera la inversión, con su costo de oportunidad, en "
        f"{formatear(recuperacion, 'anios')} de {n}." if recuperacion is not None else
        f"No recupera la inversión, con su costo de oportunidad, dentro de los {n} años del "
        "horizonte.")
    hallazgos.append(CRITERIO)

    indicadores = [
        Indicador(clave="vpn", nombre="Valor presente neto (VPN)", valor=valor, unidad="pesos",
                  formula="Σ flujo de caja libre_t / (1 + tasa de oportunidad)^t, en pesos de hoy"),
        Indicador(clave="tir", nombre="Tasa interna de retorno (TIR)", valor=la_tir,
                  unidad="tasa", formula="la tasa con la que el VPN es cero (nominal, efectiva "
                                         "anual, comparable con la tasa de oportunidad)"),
        Indicador(clave="tirm", nombre="TIR modificada (TIRM)", valor=tirm(tasa, flujos),
                  unidad="tasa", formula="(valor futuro de los flujos positivos / valor presente "
                                         "de los negativos)^(1/n) − 1, a la tasa de oportunidad"),
        Indicador(clave="recuperacion", nombre="Recuperación descontada", valor=recuperacion,
                  unidad="anios", formula="años hasta que el flujo descontado acumulado llega a "
                                          "cero"),
        Indicador(clave="indice_rentabilidad", nombre="Índice de rentabilidad",
                  valor=indice_rentabilidad(tasa, flujos), unidad="veces",
                  formula="valor presente de los flujos desde el año 1 / inversión del año 0"),
    ]
    return ResultadoModulo(modulo="proyectos", analisis="evaluacion", indicadores=indicadores,
                           hallazgos=hallazgos, advertencias=avisos,
                           supuestos=[SUPUESTO_TIRM, *flujo.resultado.supuestos])
