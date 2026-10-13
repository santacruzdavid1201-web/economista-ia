"""
Verificación de la redacción: cada cifra que escriba el LLM debe estar en los
datos que recibió. Es la red de seguridad del principio central (el LLM no
calcula): si redondea, resta o inventa, se detecta aquí.
"""
from __future__ import annotations

import re
import unicodedata

from modules.base import ResultadoModulo, formatear

# "0,67", "148.000.000", "12,3", "2024"; el signo y el símbolo $ no importan
NUMERO = re.compile(r"\d+(?:[.,]\d+)*")
# La misma cifra con el $ que la precede o el % que la sigue, si los hay
CIFRA = re.compile(r"(\$\s*)?(\d+(?:[.,]\d+)*)(\s*%)?")
# Enteros pequeños que aparecen en redacción normal ("dos años", "3 indicadores");
# como porcentaje o monto ya no son libres: "5 %" es una cifra
LIBRES = {str(n) for n in range(11)}


def numeros(texto: str) -> set[str]:
    return set(NUMERO.findall(texto))


# Años sueltos: en la charla "el Mundial de 2022" no es un dato económico
ANIO = re.compile(r"(?:19|20)\d\d")


def cifras_no_respaldadas(respuesta: str, *fuentes: str, anios_libres: bool = False) -> list[str]:
    """Cifras de la respuesta que no aparecen en ninguna de las fuentes."""
    permitidas = set().union(*(numeros(f) for f in fuentes))
    return sorted({n for peso, n, pct in CIFRA.findall(respuesta) if n not in permitidas
                   and (n not in LIBRES or peso or pct)
                   and not (anios_libres and ANIO.fullmatch(n) and not (peso or pct))})


# Sin comparación sectorial no hay con qué calificar un resultado; el 7B lo hacía igual
# ("incremento significativo"), aunque el prompt y un hallazgo lo prohibían. Raíces, sin
# tildes; la lista crece con los errores que aparezcan en la evaluación.
CALIFICATIVOS = ("significativ", "preocupante", "alarmante", "grave")


def calificativos(texto: str) -> list[str]:
    """Raíces de CALIFICATIVOS presentes en el texto (sin distinguir tildes ni mayúsculas)."""
    normal = "".join(c for c in unicodedata.normalize("NFKD", texto.lower())
                     if not unicodedata.combining(c))
    return [c for c in CALIFICATIVOS if c in normal]


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
