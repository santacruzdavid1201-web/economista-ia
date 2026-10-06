"""
Verificación de la redacción: cada cifra que escriba el LLM debe estar en los
datos que recibió. Es la red de seguridad del principio central (el LLM no
calcula): si redondea, resta o inventa, se detecta aquí.
"""
from __future__ import annotations

import re

from modules.base import ResultadoModulo, formatear

# "0,67", "148.000.000", "12,3", "2024"; el signo y el símbolo $ no importan
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
# Enteros pequeños que aparecen en redacción normal ("dos años", "3 indicadores")
LIBRES = {str(n) for n in range(11)}


def numeros(texto: str) -> set[str]:
    return set(NUMERO.findall(texto))


def cifras_no_respaldadas(respuesta: str, *fuentes: str) -> list[str]:
    """Cifras de la respuesta que no aparecen en ninguna de las fuentes."""
    permitidas = set().union(*(numeros(f) for f in fuentes)) | LIBRES
    return sorted(n for n in numeros(respuesta) if n not in permitidas)


def respaldo(resultados: list[ResultadoModulo]) -> str:
    """Respuesta armada solo con Python cuando el LLM no está disponible o falla."""
    lineas: list[str] = []
    for res in resultados:
        if res.hallazgos:
            lineas += [f"- {h}" for h in res.hallazgos]
        if res.analisis != "benchmark":
            lineas += [f"- {i.nombre}: {formatear(i.valor, i.unidad)}"
                       for i in res.indicadores if i.valor is not None]
    return "\n".join(lineas) if lineas else "No hay resultados para mostrar."
