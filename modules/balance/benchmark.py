"""
Benchmark sectorial: ubica los indicadores de la empresa dentro de la
distribución de su sector.

Este archivo NO descarga datos. Recibe una `ReferenciaSectorial` ya construida
(valores de cada indicador para las empresas pares, calculados con las MISMAS
funciones del módulo de balance) y la compara con los resultados de la empresa.
La construcción de la referencia a partir de Supersociedades vive en
data_sources/externos/.

Decisiones metodológicas:
- Percentil de rango medio: (pares por debajo + ½ de los empatados) / n × 100.
- Se usan percentiles y mediana, no media: son estadísticos de rango, robustos
  a valores extremos (p. ej. una razón corriente de 500 por un pasivo ≈ 0).
- Cada indicador tiene una DIRECCIÓN: en endeudamiento, un percentil alto es
  malo. Sin esto, el LLM podría celebrar un percentil 90 de apalancamiento.
- Los indicadores en pesos (capital de trabajo) no se comparan: dependen del
  tamaño de la empresa, no de su desempeño.
- El universo de comparación siempre se declara: no es "todo el sector", sino
  las empresas que reportan a Supersociedades con los filtros aplicados.
"""
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field

from modules.base import Indicador, ResultadoModulo

Direccion = Literal["mayor", "menor", "neutral"]

# mayor = más alto es mejor | menor = más bajo es mejor
# neutral = ni muy alto ni muy bajo es bueno; se describe sin juzgar
DIRECCION: dict[str, Direccion] = {
    # Liquidez: demasiada liquidez también es un problema (recursos ociosos)
    "razon_corriente": "neutral", "prueba_acida": "neutral", "razon_efectivo": "neutral",
    # Endeudamiento
    "nivel_endeudamiento": "menor", "concentracion_cp": "menor", "apalancamiento": "menor",
    "deuda_ebitda": "menor", "cobertura_intereses": "mayor", "carga_financiera": "menor",
    # Rentabilidad
    "margen_bruto": "mayor", "margen_operacional": "mayor", "margen_ebitda": "mayor",
    "margen_neto": "mayor", "roa": "mayor", "roe": "mayor",
    # Actividad: pagar tarde a proveedores financia a la empresa pero tensiona la relación
    "rotacion_activos": "mayor", "dias_cartera": "menor", "dias_inventario": "menor",
    "dias_proveedores": "neutral", "ciclo_conversion_efectivo": "menor",
    # Altman
    "em_score": "mayor",
}

MUESTRA_MINIMA = 10      # por debajo no se calcula percentil
MUESTRA_ADECUADA = 30    # entre 10 y 29 se calcula, pero con advertencia


class ReferenciaSectorial(BaseModel):
    """Distribución de indicadores de las empresas pares para un año."""

    universo: str             # descripción legible del grupo de comparación
    anio: int
    ciius: list[str]
    fuente: str = "Superintendencia de Sociedades (SIIS / Datos Abiertos Colombia)"
    filtros: list[str] = Field(default_factory=list)   # reglas de limpieza aplicadas
    valores: dict[str, list[float | None]]              # clave del indicador -> valores de los pares
    # Indicadores que no se comparan en este grupo, con el motivo (p. ej. días de
    # proveedores en servicios, donde las compras no se pueden estimar).
    no_comparables: dict[str, str] = Field(default_factory=dict)


def limpiar(valores: list[float | None]) -> list[float]:
    """Descarta faltantes e infinitos."""
    return [v for v in valores if v is not None and math.isfinite(v)]


def percentil_rango_medio(valor: float, muestra: list[float]) -> float:
    debajo = sum(1 for v in muestra if v < valor)
    iguales = sum(1 for v in muestra if v == valor)
    return (debajo + 0.5 * iguales) / len(muestra) * 100


def cuantil(muestra: list[float], q: float) -> float:
    """Cuantil con interpolación lineal (equivale al método por defecto de numpy)."""
    ordenada = sorted(muestra)
    posicion = (len(ordenada) - 1) * q
    abajo, arriba = math.floor(posicion), math.ceil(posicion)
    peso = posicion - abajo
    return ordenada[abajo] * (1 - peso) + ordenada[arriba] * peso


def formatear(valor: float, unidad: str) -> str:
    """Valor legible según su unidad, con coma decimal: un 8B lee mal "0.02"."""
    if unidad == "proporcion":
        texto = f"{valor * 100:.1f} %"
    elif unidad == "dias":
        texto = f"{valor:.0f} días"
    elif unidad == "veces":
        texto = f"{valor:.2f} veces"
    else:
        texto = f"{valor:,.2f}"
    return texto.replace(".", ",") if unidad != "pesos" else texto


def _frase(ind: Indicador, pct: float, n: int, mediana: float, direccion: Direccion) -> str:
    base = (f"{ind.nombre}: {formatear(ind.valor, ind.unidad)}, percentil {pct:.0f} frente a "
            f"{n} empresas (mediana del sector {formatear(mediana, ind.unidad)})")
    if direccion == "mayor":
        return f"{base}; está mejor que el {pct:.0f} % de los pares en este indicador."
    if direccion == "menor":
        return f"{base}; está mejor que el {100 - pct:.0f} % de los pares en este indicador."
    posicion = "por encima" if pct > 50 else "por debajo" if pct < 50 else "en"
    return f"{base}; se ubica {posicion} de la mediana."


def comparar(resultados: list[ResultadoModulo], ref: ReferenciaSectorial) -> ResultadoModulo:
    indicadores: list[Indicador] = []
    hallazgos: list[str] = []
    advertencias: list[str] = []
    fecha = resultados[0].fecha_corte if resultados else None

    if fecha is not None and fecha.year != ref.anio:
        advertencias.append(
            f"La empresa tiene corte {fecha.year} y la referencia sectorial es de {ref.anio}: "
            "la comparación mezcla años distintos."
        )

    pequenas: list[str] = []
    for res in resultados:
        for ind in res.indicadores:
            if ind.clave not in DIRECCION or ind.unidad == "pesos" or ind.valor is None:
                continue
            if ind.clave in ref.no_comparables:
                advertencias.append(
                    f"{ind.nombre}: no se compara con el sector ({ref.no_comparables[ind.clave]})."
                )
                continue
            muestra = limpiar(ref.valores.get(ind.clave, []))
            n = len(muestra)
            if n < MUESTRA_MINIMA:
                advertencias.append(
                    f"{ind.nombre}: solo {n} empresas comparables, no se calcula percentil."
                )
                continue
            if n < MUESTRA_ADECUADA:
                pequenas.append(ind.nombre)

            pct = percentil_rango_medio(ind.valor, muestra)
            mediana = cuantil(muestra, 0.5)
            indicadores += [
                Indicador(clave=f"{ind.clave}_percentil", nombre=f"{ind.nombre} · percentil",
                          valor=pct, unidad="percentil",
                          formula="(pares por debajo + ½ empatados) / n × 100"),
                Indicador(clave=f"{ind.clave}_p25", nombre=f"{ind.nombre} · P25 del sector",
                          valor=cuantil(muestra, 0.25), unidad=ind.unidad,
                          formula="Cuartil 1 de los pares"),
                Indicador(clave=f"{ind.clave}_mediana", nombre=f"{ind.nombre} · mediana del sector",
                          valor=mediana, unidad=ind.unidad, formula="Mediana de los pares"),
                Indicador(clave=f"{ind.clave}_p75", nombre=f"{ind.nombre} · P75 del sector",
                          valor=cuantil(muestra, 0.75), unidad=ind.unidad,
                          formula="Cuartil 3 de los pares"),
            ]
            hallazgos.append(_frase(ind, pct, n, mediana, DIRECCION[ind.clave]))

    if pequenas:
        advertencias.append(
            "Muestra pequeña (menos de 30 empresas) en: " + ", ".join(pequenas)
            + ". Los percentiles son orientativos."
        )

    supuestos = [
        f"Universo de comparación: {ref.universo}, año {ref.anio}.",
        "La cobertura de Supersociedades no es censal: incluye sociedades vigiladas, "
        "controladas y algunas inspeccionadas, no todas las empresas del sector.",
        "Los indicadores de los pares se calculan con las mismas fórmulas que los de la empresa.",
        *ref.filtros,
    ]
    return ResultadoModulo(
        modulo="balance", analisis="benchmark", fecha_corte=fecha,
        indicadores=indicadores, hallazgos=hallazgos, supuestos=supuestos,
        fuentes=[f"{ref.fuente}; CIIU {', '.join(ref.ciius)}; año {ref.anio}."],
        advertencias=advertencias,
    )
